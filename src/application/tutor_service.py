# -*- coding: utf-8 -*-
"""Tutor question answering, with streaming and non-streaming entry points."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import threading
import time
from typing import Any, AsyncIterator, Dict, Optional

from src.agents.tutor_node import TutorInput
from src.api_models.tutor_request import TutorRequest
from src.auth.rate_limiter import KeyedConcurrencyLimiter
from src.observability import bind_context, incr_metric, log_event, observe_metric
from src.validation.pipeline import get_validation_pipeline
from src.validation.result import ValidationResult

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
_TUTOR_REQUEST_CAPACITY = threading.BoundedSemaphore(
    _read_int_env("EDUAGENT_TUTOR_MAX_CONCURRENT", 2)
)
_TUTOR_REQUEST_USER_CAPACITY = KeyedConcurrencyLimiter(1)
_TUTOR_STREAM_CAPACITY = threading.BoundedSemaphore(
    _read_int_env("EDUAGENT_TUTOR_STREAM_MAX_CONCURRENT", 2)
)
_TUTOR_STREAM_USER_CAPACITY = KeyedConcurrencyLimiter(1)


def _fallback_tutor_response(request: TutorRequest, node_id: str = "") -> Dict[str, object]:
    title = get_node_title(node_id, node_id or "current node")
    text_explanation = (
        f"## {title}\n\n"
        "The live tutor is taking longer than expected, so here is a focused fallback: "
        f"break the question down, identify the key concept, and connect it to the current node. "
        f"For your question, start by writing one example input, one expected output, and the rule that links them."
    )
    if request.context_type == "code_debug":
        code_block = request.code_snippet or "(No code snippet was provided.)"
        error_block = request.error_message or "(No runtime error message was provided.)"
        text_explanation = (
            f"## {title}: debugging fallback\n\n"
            f"Question: {request.question}\n\n"
            "### Code under review\n"
            f"```\n{code_block}\n```\n\n"
            "### Reported error\n"
            f"{error_block}\n\n"
            "Trace the error from the smallest reproducible input and check the values immediately before the failing operation."
        )
    return {
        "text_explanation": text_explanation,
        "mermaid_src": (
            "graph TD\n"
            '    Q["Question"] --> C["Key concept"]\n'
            '    C --> E["Example"]\n'
            '    E --> R["Reasoning rule"]'
        ),
        "video_hydration": None,
        "query": request.question,
        "tutoring_mode": request.context_type,
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


def _coerce_tutor_request(
    question: str | TutorRequest,
    *,
    tutor_request: Optional[TutorRequest] = None,
    context_type: str = "general",
    code_snippet: str = "",
    error_message: str = "",
) -> TutorRequest:
    if tutor_request is not None:
        return tutor_request
    if isinstance(question, TutorRequest):
        return question
    return TutorRequest(
        question=question,
        context_type=context_type,
        code_snippet=code_snippet,
        error_message=error_message,
    )


def _validate_tutor_request(request: TutorRequest) -> tuple[TutorRequest, ValidationResult]:
    """Validate every user-controlled text field before it is added to a prompt."""
    validation = validate_service_input(payload=request.model_dump(mode="json"), field="tutor_request")
    updates: dict[str, str] = {}
    for field_name in ("question", "code_snippet", "error_message"):
        value = getattr(request, field_name)
        field_validation = validate_service_input(text=value, field=field_name)
        validation.merge(field_validation)
        updates[field_name] = field_validation.sanitized_text or value
    if not request.question:
        validation.add_issue("missing_question", "Tutor question is required.", field="question")
    return request.model_copy(update=updates), validation


def _stream_messages(request: TutorRequest) -> list[dict[str, str]]:
    from src.agents.prompt_registry import build_user_prompt, get_system_prompt

    return [
        {"role": "system", "content": get_system_prompt("tutor.mode")},
        {
            "role": "user",
            "content": build_user_prompt(
                "tutor.mode",
                mode=request.context_type,
                query=request.question,
                course_name="",
                student_context="",
                code_snippet=request.code_snippet,
                error_message=request.error_message,
            ),
        },
    ]


_TUTOR_STREAM_FIELD_LABELS = {
    "core_definition": "核心定义",
    "analogy": "类比",
    "detailed_explanation": "展开说明",
    "diagram": "图示说明",
    "code_example": "代码示例",
    "common_misconceptions": "常见误区",
    "extension_questions": "延伸思考",
    "learning_tip": "学习建议",
    "hints": "提示",
    "solution_approach": "解题思路",
    "common_mistakes": "常见错误",
    "check_points": "检查点",
    "error_analysis": "错误分析",
    "root_cause": "根因",
    "fix_guidance": "修复建议",
    "best_practices": "最佳实践",
    "debugging_tips": "调试提示",
    "key_topics": "重点主题",
    "review_strategy": "复习策略",
    "practice_questions": "练习问题",
    "common_exam_traps": "常见陷阱",
    "cheat_sheet": "速记清单",
    "follow_up_questions": "后续思考",
}


def _structured_stream_prefix_state(text: str) -> Optional[bool]:
    """Classify a stream prefix without exposing a split ```json fence."""
    stripped = text.lstrip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        return True

    lower = stripped.lower()
    json_fence = "```json"
    if lower.startswith(json_fence):
        return True
    if json_fence.startswith(lower):
        return None
    return False


def _parse_structured_stream_output(text: str) -> tuple[bool, Any]:
    """Parse a complete JSON response, including a fenced JSON block."""
    candidate = text.strip()
    if candidate.startswith("```"):
        first_newline = candidate.find("\n")
        if first_newline != -1 and candidate.endswith("```"):
            language = candidate[3:first_newline].strip().lower()
            if language in {"", "json"}:
                candidate = candidate[first_newline + 1:-3].strip()
    try:
        return True, json.loads(candidate)
    except (TypeError, ValueError):
        return False, None


def _render_tutor_stream_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "; ".join(filter(None, (_render_tutor_stream_value(item) for item in value)))
    if isinstance(value, dict):
        return "; ".join(
            filter(
                None,
                (
                    f"{_TUTOR_STREAM_FIELD_LABELS.get(str(key), str(key))}: {_render_tutor_stream_value(item)}"
                    for key, item in value.items()
                    if item not in (None, "", [], {})
                ),
            )
        )
    return ""


def _render_structured_tutor_stream(payload: Any) -> str:
    """Convert the Tutor JSON contract into the Markdown shown in the chat."""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        lines = [f"- {_render_tutor_stream_value(item)}" for item in payload]
        return "\n".join(line for line in lines if line != "- ")
    if not isinstance(payload, dict):
        return _render_tutor_stream_value(payload)

    sections: list[str] = []
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        rendered = _render_tutor_stream_value(value)
        if not rendered:
            continue
        if key in {"response", "text_explanation", "answer", "content"}:
            sections.append(rendered)
            continue
        label = _TUTOR_STREAM_FIELD_LABELS.get(str(key), str(key).replace("_", " "))
        if isinstance(value, list):
            items = [f"- {_render_tutor_stream_value(item)}" for item in value]
            body = "\n".join(item for item in items if item != "- ")
        else:
            body = rendered
        if body:
            sections.append(f"### {label}\n\n{body}")
    return "\n\n".join(sections).strip()


def _run_tutor_unlimited(
    user_id: str,
    course_id: str,
    question: str | TutorRequest,
    *,
    tutor_request: Optional[TutorRequest] = None,
    context_type: str = "general",
    code_snippet: str = "",
    error_message: str = "",
    persist_history: bool = True,
) -> Dict[str, object]:
    from src.orchestration_runtime import get_runtime

    with bind_context(user_id=user_id, course_id=course_id, operation="run_tutor"):
        started = time.perf_counter()
        request = _coerce_tutor_request(
            question,
            tutor_request=tutor_request,
            context_type=context_type,
            code_snippet=code_snippet,
            error_message=error_message,
        )
        request, input_validation = _validate_tutor_request(request)
        pipeline = get_validation_pipeline()
        if not input_validation.passed:
            incr_metric("tutor.block_total", reason="input_validation")
            return _blocked_tutor_payload(input_validation)

        session = get_session(user_id, course_id)
        state = session.agent_state
        runtime = get_runtime()
        future = _TUTOR_EXECUTOR.submit(runtime.tutor, TutorInput(agent_state=state, request=request))
        try:
            output = future.result(timeout=_tutor_timeout_sec())
            state = output.agent_state
        except concurrent.futures.TimeoutError:
            future.cancel()
            incr_metric("llm.timeout_total", operation="tutor")
            incr_metric("llm.fallback_total", operation="tutor", fallback="local_template")
            log_event("tutor.timeout", level="warning", timeout_sec=_tutor_timeout_sec())
            state.tutor_response = _fallback_tutor_response(request, state.current_node_id)
            state.record_error("tutor_timeout_fallback")
        except Exception as exc:
            incr_metric("llm.error_total", operation="tutor")
            incr_metric("llm.fallback_total", operation="tutor", fallback="local_template")
            log_event("tutor.exception", level="warning", error=str(exc))
            state.tutor_response = _fallback_tutor_response(request, state.current_node_id)
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
                    "query": request.question,
                    "context_type": request.context_type,
                    "validation": output_validation.to_contract_validation(),
                },
                artifacts={"mermaid_src": (state.tutor_response or {}).get("mermaid_src", "")},
            ),
            *[item for item in state.agent_feedback if item.agent != "Tutor"],
        ]
        if persist_history:
            try:
                from . import learning_assets_service

                learning_assets_service.record_tutor_exchange_asset(
                    state,
                    question=request.question,
                    response=state.tutor_response or {},
                    context_type=request.context_type,
                )
            except Exception as exc:
                # Conversation restoration is supplementary. A storage problem
                # must not turn a valid tutor response into an application error.
                state.record_error(f"tutor_history_asset_sync_failed:{type(exc).__name__}")
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


def run_tutor(
    user_id: str,
    course_id: str,
    question: str | TutorRequest,
    *,
    tutor_request: Optional[TutorRequest] = None,
    context_type: str = "general",
    code_snippet: str = "",
    error_message: str = "",
    persist_history: bool = True,
) -> Dict[str, object]:
    global_acquired = _TUTOR_REQUEST_CAPACITY.acquire(blocking=False)
    user_acquired = global_acquired and _TUTOR_REQUEST_USER_CAPACITY.acquire(user_id)
    if not global_acquired or not user_acquired:
        if global_acquired:
            _TUTOR_REQUEST_CAPACITY.release()
        incr_metric("tutor.capacity_reject_total", mode="request")
        return {
            "status": "capacity_exceeded",
            "detail": "TUTOR_CAPACITY_EXCEEDED",
            "retry_after": 1,
        }
    try:
        return _run_tutor_unlimited(
            user_id,
            course_id,
            question,
            tutor_request=tutor_request,
            context_type=context_type,
            code_snippet=code_snippet,
            error_message=error_message,
            persist_history=persist_history,
        )
    finally:
        _TUTOR_REQUEST_USER_CAPACITY.release(user_id)
        _TUTOR_REQUEST_CAPACITY.release()


async def _stream_tutor_unlimited(
    user_id: str,
    course_id: str,
    question: str | TutorRequest,
    *,
    tutor_request: Optional[TutorRequest] = None,
    context_type: str = "general",
    code_snippet: str = "",
    error_message: str = "",
) -> AsyncIterator[Dict[str, str]]:
    from src.orchestration_runtime import get_runtime

    with bind_context(user_id=user_id, course_id=course_id, operation="stream_tutor"):
        started = time.perf_counter()
        pipeline = get_validation_pipeline()
        request = _coerce_tutor_request(
            question,
            tutor_request=tutor_request,
            context_type=context_type,
            code_snippet=code_snippet,
            error_message=error_message,
        )
        request, input_validation = _validate_tutor_request(request)
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

        llm = get_runtime().get_llm()
        full_text: list[str] = []
        if llm is None:
            incr_metric("llm.fallback_total", operation="tutor_stream", fallback="run_tutor")
            fallback = run_tutor(
                user_id,
                course_id,
                request.question,
                tutor_request=request,
            ).get("tutor_response", {}) or {}
            text = fallback.get("text_explanation", "") or "Tutor is temporarily unavailable."
            for chunk in [text[i:i + 80] for i in range(0, len(text), 80)]:
                yield {"event": "token", "data": json.dumps({"token": chunk}, ensure_ascii=False)}
                await asyncio.sleep(0.02)
        else:
            messages = _stream_messages(request)
            raw_tokens: list[str] = []
            structured_stream: Optional[bool] = None
            emitted_text = False
            stream_fallback = False
            try:
                async with asyncio.timeout(_tutor_timeout_sec()):
                    async for token in llm.chat_stream(messages):
                        if not token:
                            continue
                        if token.strip().startswith("[Stream error:"):
                            raise RuntimeError(token.strip())

                        raw_tokens.append(token)
                        raw_text = "".join(raw_tokens)
                        if structured_stream is None:
                            if not raw_text.strip():
                                continue
                            structured_stream = _structured_stream_prefix_state(raw_text)
                            if structured_stream is None:
                                continue
                            if structured_stream:
                                continue
                            full_text = [raw_text]
                            emitted_text = True
                            yield {
                                "event": "token",
                                "data": json.dumps({"token": raw_text}, ensure_ascii=False),
                            }
                            continue

                        if not structured_stream:
                            full_text.append(token)
                            emitted_text = True
                            yield {
                                "event": "token",
                                "data": json.dumps({"token": token}, ensure_ascii=False),
                            }
            except Exception as exc:
                incr_metric("llm.timeout_total", operation="tutor_stream")
                incr_metric("llm.fallback_total", operation="tutor_stream", fallback="run_tutor")
                log_event("tutor.stream.fallback", level="warning", error=str(exc))
                fallback = run_tutor(
                    user_id,
                    course_id,
                    request.question,
                    tutor_request=request,
                    persist_history=False,
                ).get("tutor_response", {}) or {}
                text = fallback.get("text_explanation", "") or "Tutor is temporarily unavailable."
                full_text = [text]
                stream_fallback = True
                if emitted_text:
                    yield {
                        "event": "reset",
                        "data": json.dumps({"reason": "stream_fallback"}, ensure_ascii=False),
                    }
                for chunk in [text[i:i + 80] for i in range(0, len(text), 80)]:
                    yield {"event": "token", "data": json.dumps({"token": chunk}, ensure_ascii=False)}
                    await asyncio.sleep(0.02)
                yield {
                    "event": "warning",
                    "data": json.dumps({"message": f"stream_fallback:{exc}"}, ensure_ascii=False),
                }
            else:
                raw_text = "".join(raw_tokens)
                if structured_stream:
                    parsed, structured_payload = _parse_structured_stream_output(raw_text)
                    text = _render_structured_tutor_stream(structured_payload) if parsed else ""
                    if not text:
                        text = _fallback_tutor_response(request).get("text_explanation", "")
                        stream_fallback = True
                        incr_metric("llm.fallback_total", operation="tutor_stream", fallback="local_template")
                        log_event(
                            "tutor.stream.invalid_structured_output",
                            level="warning",
                            output_length=len(raw_text),
                        )
                    full_text = [text]
                    for chunk in [text[i:i + 80] for i in range(0, len(text), 80)]:
                        yield {"event": "token", "data": json.dumps({"token": chunk}, ensure_ascii=False)}
                        await asyncio.sleep(0.02)
                elif not full_text:
                    text = _fallback_tutor_response(request).get("text_explanation", "")
                    full_text = [text]
                    stream_fallback = True
                    incr_metric("llm.fallback_total", operation="tutor_stream", fallback="local_template")
                    for chunk in [text[i:i + 80] for i in range(0, len(text), 80)]:
                        yield {"event": "token", "data": json.dumps({"token": chunk}, ensure_ascii=False)}
                        await asyncio.sleep(0.02)

            session = get_session(user_id, course_id)
            raw_response = {
                "text_explanation": "".join(full_text),
                "mermaid_src": "",
                "query": request.question,
                "tutoring_mode": request.context_type,
            }
            if stream_fallback:
                raw_response["fallback"] = True
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
            try:
                from . import learning_assets_service

                learning_assets_service.record_tutor_exchange_asset(
                    session.agent_state,
                    question=request.question,
                    response=session.agent_state.tutor_response or {},
                    context_type=request.context_type,
                )
            except Exception as exc:
                session.agent_state.record_error(
                    f"tutor_history_asset_sync_failed:{type(exc).__name__}"
                )
            persist_session(session)

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        observe_metric("tutor.stream.duration_ms", duration_ms)
        log_event("tutor.stream.complete", duration_ms=duration_ms)
        yield {"event": "done", "data": json.dumps({"reference_count": 0}, ensure_ascii=False)}


async def stream_tutor(
    user_id: str,
    course_id: str,
    question: str | TutorRequest,
    *,
    tutor_request: Optional[TutorRequest] = None,
    context_type: str = "general",
    code_snippet: str = "",
    error_message: str = "",
) -> AsyncIterator[Dict[str, str]]:
    global_acquired = _TUTOR_STREAM_CAPACITY.acquire(blocking=False)
    user_acquired = global_acquired and _TUTOR_STREAM_USER_CAPACITY.acquire(user_id)
    if not global_acquired or not user_acquired:
        if global_acquired:
            _TUTOR_STREAM_CAPACITY.release()
        incr_metric("tutor.capacity_reject_total", mode="stream")
        yield {
            "event": "error",
            "data": json.dumps(
                {"detail": "TUTOR_STREAM_CAPACITY_EXCEEDED", "retry_after": 1},
                ensure_ascii=False,
            ),
        }
        return
    try:
        async for event in _stream_tutor_unlimited(
            user_id,
            course_id,
            question,
            tutor_request=tutor_request,
            context_type=context_type,
            code_snippet=code_snippet,
            error_message=error_message,
        ):
            yield event
    finally:
        _TUTOR_STREAM_USER_CAPACITY.release(user_id)
        _TUTOR_STREAM_CAPACITY.release()
