# -*- coding: utf-8 -*-
"""Tutor question answering, with streaming and non-streaming entry points."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Dict

from src.agents.tutor_node import TutorInput
from src.state.agent_state import LatestBehavior
from src.validation.pipeline import get_validation_pipeline

from ._common import AGENT_FEEDBACK_VERSION, feedback_item, get_session, persist_session


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


def run_tutor(user_id: str, course_id: str, question: str) -> Dict[str, object]:
    from src.orchestration_runtime import get_runtime

    pipeline = get_validation_pipeline()
    input_validation = pipeline.validate_input(question, field="question")
    if not input_validation.passed:
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
    output = get_runtime().tutor(TutorInput(agent_state=state))
    state = output.agent_state
    validated_response, output_validation = pipeline.validate_tutor_response(state.tutor_response or {})
    state.tutor_response = validated_response
    if not output_validation.passed:
        state.record_error("tutor_validation_rejected:" + ";".join(issue.message for issue in output_validation.issues))

    state.agent_feedback = [
        feedback_item(
            agent="Tutor",
            stage="tutor_question",
            status="success" if output_validation.passed else "error",
            headline="Tutor response updated" if output_validation.passed else "Tutor response blocked",
            summary="The tutor answer passed validation." if output_validation.passed else "The raw tutor answer was blocked by validation.",
            details_md=(state.tutor_response or {}).get("text_explanation", ""),
            structured_data={"query": question, "validation": output_validation.to_contract_validation()},
            artifacts={"mermaid_src": (state.tutor_response or {}).get("mermaid_src", "")},
        ),
        *[item for item in state.agent_feedback if item.agent != "Tutor"],
    ]
    session.agent_state = state
    persist_session(session)
    return {
        "tutor_response": state.tutor_response,
        "reference_count": 0,
        "agent_feedback_version": AGENT_FEEDBACK_VERSION,
        "agent_feedback": [item.model_dump() for item in state.agent_feedback],
    }


async def stream_tutor(user_id: str, course_id: str, question: str) -> AsyncIterator[Dict[str, str]]:
    from src.orchestration_runtime import get_runtime

    pipeline = get_validation_pipeline()
    input_validation = pipeline.validate_input(question, field="question")
    if not input_validation.passed:
        yield {"event": "error", "data": json.dumps({"validation": input_validation.to_contract_validation()}, ensure_ascii=False)}
        return
    question = input_validation.sanitized_text or question

    llm = get_runtime().get_llm()
    full_text: list[str] = []
    if llm is None:
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
        async for token in llm.chat_stream(messages):
            if token:
                full_text.append(token)
                yield {"event": "token", "data": json.dumps({"token": token}, ensure_ascii=False)}
        session = get_session(user_id, course_id)
        raw_response = {"text_explanation": "".join(full_text), "mermaid_src": ""}
        validated_response, validation = pipeline.validate_tutor_response(raw_response)
        session.agent_state.tutor_response = validated_response
        if not validation.passed:
            session.agent_state.record_error("tutor_validation_rejected:" + ";".join(issue.message for issue in validation.issues))
            yield {"event": "validation_error", "data": json.dumps({"validation": validation.to_contract_validation()}, ensure_ascii=False)}
        persist_session(session)
    yield {"event": "done", "data": json.dumps({"reference_count": 0}, ensure_ascii=False)}
