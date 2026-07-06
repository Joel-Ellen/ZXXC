# -*- coding: utf-8 -*-
"""Tutor question answering, with streaming and non-streaming entry points."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import time
from typing import AsyncIterator, Dict

from src.agents.tutor_node import TutorInput
from src.observability import bind_context, incr_metric, log_event, observe_metric
from src.state.agent_state import LatestBehavior
from src.validation.pipeline import get_validation_pipeline

from ._common import (
    AGENT_FEEDBACK_VERSION,
    feedback_item,
    get_node_title,
    get_session,
    persist_session,
    validate_service_input,
)


def _read_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _read_float_env(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _tutor_timeout_sec() -> float:
    return _read_float_env("EDUAGENT_TUTOR_TIMEOUT_SEC", 12.0)


_TUTOR_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=_read_int_env("EDUAGENT_TUTOR_WORKERS", 2),
    thread_name_prefix="eduagent-tutor",
)


def _fallback_tutor_response(question: str, node_id: str = "") -> Dict[str, object]:
    title = get_node_title(node_id, node_id or "current node")
    return {
        "text_explanation": (
            f"## {title}\n\n"
            "The live tutor is taking longer than expected, so here is a focused fallback: "
            f"break the question down, identify the key concept, and connect it to the current node. "
            f"For your question, start by writing one example input, one expected output, and the rule that links them."
        ),
        "mermaid_src": (
            "graph TD\n"
            '    Q["Question"] --> C["Key concept"]\n'
            '    C --> E["Example"]\n'
            '    E --> R["Reasoning rule"]'
        ),
        "video_hydration": None,
        "query": question,
        "fallback": True,
    }


def _blocked_tutor_payload(validation) -> Dict[str, object]:
    return {
        "tutor_response": {
            "text_explanation": "Tutor question was blocked by validation.",
            "blocked": True,
            "validation": validation.to_contract_validation(),
        },
        "reference_count": 0,
        "agent_feedback_version": AGENT_FEEDBACK_VERSION,
        "agent_feedback": [],
    }


def _validation_issue_codes(validation) -> list[str]:
    return [getattr(issue, "code", "") for issue in validation.issues]


def run_tutor(user_id: str, course_id: str, question: str) -> Dict[str, object]:
    from src.orchestration_runtime import get_runtime

    with bind_context(user_id=user_id, course_id=course_id, operation="run_tutor"):
        started = time.perf_counter()
        pipeline = get_validation_pipeline()
        input_validation = validate_service_input(
            payload={"question": question},
            text=question,
            field="question",
        )
        if not input_validation.passed:
            incr_metric("tutor.block_total", reason="input_validation")
            return _blocked_tutor_payload(input_validation)
        question = input_validation.sanitized_text or question

        session = get_session(user_id, course_id)
        state = session.agent_state
        state.latest_behavior = LatestBehavior(
            node_id=state.current_node_id,
            correctness=0.75,
            time_spent_ratio=1.0,
            error_types=[],
            resource_feedback={},
            help_request_count=1,
            tutor_query=question,
        )
        runtime = get_runtime()
        future = _TUTOR_EXECUTOR.submit(runtime.tutor, TutorInput(agent_state=state))
        try:
            output = future.result(timeout=_tutor_timeout_sec())
            state = output.agent_state
        except concurrent.futures.TimeoutError:
            future.cancel()
            incr_metric("llm.timeout_total", operation="tutor")
            incr_metric("llm.fallback_total", operation="tutor", fallback="local_template")
            log_event("tutor.timeout", level="warning", timeout_sec=_tutor_timeout_sec())
            state.tutor_response = _fallback_tutor_response(question, state.current_node_id)
            state.record_error("tutor_timeout_fallback")
        except Exception as exc:
            incr_metric("llm.error_total", operation="tutor")
            incr_metric("llm.fallback_total", operation="tutor", fallback="local_template")
            log_event("tutor.exception", level="warning", error=str(exc))
            state.tutor_response = _fallback_tutor_response(question, state.current_node_id)
            state.record_error(f"tutor_fallback:{exc}")

        validated_response, output_validation = pipeline.validate_tutor_response(state.tutor_response or {})
        state.tutor_response = validated_response
        if not output_validation.passed:
            issue_codes = _validation_issue_codes(output_validation)
            incr_metric("validation.reject_total", stage="tutor_output", code=issue_codes[0] if issue_codes else "validation_failed")
            incr_metric("tutor.block_total", reason="output_validation")
            log_event(
                "tutor.validation_reject",
                level="warning",
                issue_codes=issue_codes,
                issue_count=len(issue_codes),
            )
            state.record_error("tutor_validation_rejected:" + ";".join(issue.message for issue in output_validation.issues))
        if (state.tutor_response or {}).get("blocked"):
            incr_metric("tutor.block_total", reason="blocked_payload")

        state.agent_feedback = [
            feedback_item(
                agent="Tutor",
                stage="tutor_question",
                status="success" if output_validation.passed else "error",
                headline="Tutor response updated" if output_validation.passed else "Tutor response blocked",
                summary=(
                    "The tutor answer passed validation."
                    if output_validation.passed
                    else "The raw tutor answer was blocked by validation."
                ),
                details_md=(state.tutor_response or {}).get("text_explanation", ""),
                structured_data={
                    "query": question,
                    "validation": output_validation.to_contract_validation(),
                },
                artifacts={"mermaid_src": (state.tutor_response or {}).get("mermaid_src", "")},
            ),
            *[item for item in state.agent_feedback if item.agent != "Tutor"],
        ]
        session.agent_state = state
        persist_session(session)

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        observe_metric("tutor.run.duration_ms", duration_ms)
        log_event(
            "tutor.run.complete",
            blocked=bool((state.tutor_response or {}).get("blocked")),
            fallback=bool((state.tutor_response or {}).get("fallback")),
            duration_ms=duration_ms,
        )
        return {
            "tutor_response": state.tutor_response,
            "reference_count": 0,
            "agent_feedback_version": AGENT_FEEDBACK_VERSION,
            "agent_feedback": [item.model_dump() for item in state.agent_feedback],
        }


async def stream_tutor(user_id: str, course_id: str, question: str) -> AsyncIterator[Dict[str, str]]:
    from src.orchestration_runtime import get_runtime

    with bind_context(user_id=user_id, course_id=course_id, operation="stream_tutor"):
        started = time.perf_counter()
        pipeline = get_validation_pipeline()
        input_validation = validate_service_input(
            payload={"question": question},
            text=question,
            field="question",
        )
        if not input_validation.passed:
            incr_metric("tutor.block_total", reason="stream_input_validation")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"validation": input_validation.to_contract_validation()},
                    ensure_ascii=False,
                ),
            }
            return
        question = input_validation.sanitized_text or question

        llm = get_runtime().get_llm()
        full_text: list[str] = []
        if llm is None:
            incr_metric("llm.fallback_total", operation="tutor_stream", fallback="run_tutor")
            fallback = run_tutor(user_id, course_id, question).get("tutor_response", {}) or {}
            text = fallback.get("text_explanation", "") or "Tutor is temporarily unavailable."
            for chunk in [text[i:i + 80] for i in range(0, len(text), 80)]:
                yield {"event": "token", "data": json.dumps({"token": chunk}, ensure_ascii=False)}
                await asyncio.sleep(0.02)
        else:
            messages = [
                {"role": "system", "content": "You are a patient computer science tutor. Answer clearly in Markdown."},
                {"role": "user", "content": question},
            ]
            try:
                async with asyncio.timeout(_tutor_timeout_sec()):
                    async for token in llm.chat_stream(messages):
                        if token:
                            full_text.append(token)
                            yield {
                                "event": "token",
                                "data": json.dumps({"token": token}, ensure_ascii=False),
                            }
            except Exception as exc:
                incr_metric("llm.timeout_total", operation="tutor_stream")
                incr_metric("llm.fallback_total", operation="tutor_stream", fallback="run_tutor")
                log_event("tutor.stream.fallback", level="warning", error=str(exc))
                fallback = run_tutor(user_id, course_id, question).get("tutor_response", {}) or {}
                text = fallback.get("text_explanation", "") or "Tutor is temporarily unavailable."
                full_text = [text]
                for chunk in [text[i:i + 80] for i in range(0, len(text), 80)]:
                    yield {"event": "token", "data": json.dumps({"token": chunk}, ensure_ascii=False)}
                    await asyncio.sleep(0.02)
                yield {
                    "event": "warning",
                    "data": json.dumps({"message": f"stream_fallback:{exc}"}, ensure_ascii=False),
                }

            session = get_session(user_id, course_id)
            raw_response = {"text_explanation": "".join(full_text), "mermaid_src": ""}
            validated_response, validation = pipeline.validate_tutor_response(raw_response)
            session.agent_state.tutor_response = validated_response
            if not validation.passed:
                issue_codes = _validation_issue_codes(validation)
                incr_metric(
                    "validation.reject_total",
                    stage="tutor_stream_output",
                    code=issue_codes[0] if issue_codes else "validation_failed",
                )
                incr_metric("tutor.block_total", reason="stream_output_validation")
                session.agent_state.record_error(
                    "tutor_validation_rejected:"
                    + ";".join(issue.message for issue in validation.issues)
                )
                yield {
                    "event": "validation_error",
                    "data": json.dumps(
                        {"validation": validation.to_contract_validation()},
                        ensure_ascii=False,
                    ),
                }
            persist_session(session)

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        observe_metric("tutor.stream.duration_ms", duration_ms)
        log_event("tutor.stream.complete", duration_ms=duration_ms)
        yield {"event": "done", "data": json.dumps({"reference_count": 0}, ensure_ascii=False)}
