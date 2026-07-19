# -*- coding: utf-8 -*-
"""Session creation, restoration, and official learning advancement."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import Lock, RLock
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import ValidationError

from src.api_models.learning_event import LearningEventRequest, LearningEventType
from src.observability import bind_context, incr_metric, log_event, observe_metric
from src.orchestration_core import LearningStepResult, run_official_learning_step
from src.orchestration_runtime import get_runtime
from src.state.agent_state import AgentState

from . import code_practice_service
from ._common import (
    AGENT_FEEDBACK_VERSION,
    MASTERY_ADVANCE_THRESHOLD,
    RESOURCE_CONTRACT_VERSION,
    feedback_item,
    get_node_title,
    get_session,
    load_persisted_session,
    persist_session,
    reset_session,
    state_response,
    validate_service_input,
    validation_blocked_response,
)


# Event retries use the same id. Keep the duplicate lookup, ledger append,
# verification, and persistence in one per-session critical section so a
# timeout retry cannot evaluate the same evidence twice in this process.
_LEARNING_EVENT_LOCKS_GUARD = Lock()
_LEARNING_EVENT_LOCKS: dict[tuple[str, str], Any] = {}


def _learning_event_lock(user_id: str, course_id: str) -> RLock:
    key = (str(user_id), str(course_id))
    with _LEARNING_EVENT_LOCKS_GUARD:
        lock = _LEARNING_EVENT_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _LEARNING_EVENT_LOCKS[key] = lock
        return lock


def _event_history(state: AgentState) -> list[dict[str, Any]]:
    """Return the durable learning-event ledger, repairing old state safely."""
    history = state.internal_state.setdefault("learning_events", [])
    if not isinstance(history, list):
        history = []
        state.internal_state["learning_events"] = history
    return history


def _mastery_attributions(state: AgentState) -> list[dict[str, Any]]:
    """Return the durable per-mastery-change provenance ledger."""
    attributions = state.internal_state.setdefault("mastery_attributions", [])
    if not isinstance(attributions, list):
        attributions = []
        state.internal_state["mastery_attributions"] = attributions
    return attributions


def _event_response(
    event_record: dict[str, Any],
    *,
    attribution: Optional[dict[str, Any]] = None,
    idempotent: bool = False,
) -> Dict[str, Any]:
    mastery = event_record.get("mastery")
    if not isinstance(mastery, dict):
        mastery = {}
    learning_result = event_record.get("learning_result")
    if not isinstance(learning_result, dict):
        learning_result = {}
    return {
        "status": "ok",
        "event_id": event_record.get("event_id", ""),
        "event_type": event_record.get("event_type", ""),
        "event": event_record,
        "idempotent": idempotent,
        "evidence_accepted": bool(mastery.get("evidence_accepted", False)),
        "mastery_updated": bool(mastery.get("updated", False)),
        "mastery_attribution": attribution,
        "mastery_before": mastery.get("before"),
        "mastery_after": mastery.get("after"),
        "mastery_update_reason": mastery.get("reason", "event_recorded"),
        "current_node_id": event_record.get("current_node_id", event_record.get("node_id", "")),
        "evaluated_node_id": mastery.get("evaluated_node_id", event_record.get("node_id", "")),
        "advanced_to_next_node": bool(learning_result.get("advanced_to_next_node", False)),
        "next_node_id": learning_result.get("next_node_id"),
        "mastery_threshold": learning_result.get("mastery_threshold", MASTERY_ADVANCE_THRESHOLD),
        # This is only populated after a server-verified terminal event.
        "effective_correctness": learning_result.get("effective_correctness"),
        "knowledge_mastery": learning_result.get("knowledge_mastery"),
        # Keep the server-derived question outcomes available even when an
        # accepted diagnostic produces no mastery delta. The UI needs these
        # outcomes to show per-question feedback; client result payloads are
        # never used for that purpose.
        "verified_evidence": event_record.get("verified_evidence"),
        "practice_verification": event_record.get("practice_verification"),
        "review": event_record.get("review"),
    }


def _find_event_attribution(
    state: AgentState,
    event_id: str,
) -> Optional[dict[str, Any]]:
    return next(
        (
            dict(attribution)
            for attribution in reversed(_mastery_attributions(state))
            if attribution.get("event_id") == event_id
        ),
        None,
    )


def _latest_verified_evidence(
    state: AgentState,
    event: LearningEventRequest,
) -> dict[str, Any]:
    """Copy the server verifier's latest detail record into an attribution."""
    records = state.internal_state.get("verified_completion_events", [])
    if not isinstance(records, list):
        return {}
    resource_id = event.completion_evidence.resource_id if event.completion_evidence else ""
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        if record.get("node_id") != event.node_id:
            continue
        if resource_id and record.get("resource_id") != resource_id:
            continue
        return dict(record)
    return {}


def _record_verified_code_submission(
    state: AgentState,
    event: LearningEventRequest,
    *,
    user_id: str,
    course_id: str,
) -> tuple[dict[str, Any], Optional[dict[str, Any]], dict[str, Any]]:
    """Consume a server-issued code receipt and update mastery conservatively.

    ``event.result`` is never treated as a verdict.  It may only name a
    submission receipt created by the isolated execution endpoint.
    """
    submission_id = str((event.result or {}).get("submission_id") or "").strip()
    if not submission_id:
        return {
            "updated": False,
            "evidence_accepted": False,
            "reason": "code_submission_receipt_required",
            "before": state.dynamic_profile.knowledge_mastery.get(event.node_id, 0.0),
            "after": state.dynamic_profile.knowledge_mastery.get(event.node_id, 0.0),
            "evaluated_node_id": event.node_id,
        }, None, {"receipt_verified": False}

    verified = code_practice_service.verify_submission_receipt(
        state,
        user_id=user_id,
        course_id=course_id,
        node_id=event.node_id,
        resource_id=event.resource_id,
        submission_id=submission_id,
        event_id=event.event_id,
    )
    before = state.dynamic_profile.knowledge_mastery.get(event.node_id, 0.0)
    evidence = verified.get("evidence") if isinstance(verified.get("evidence"), dict) else {}
    if not verified.get("accepted"):
        return {
            "updated": False,
            "evidence_accepted": False,
            "reason": verified.get("reason", "code_submission_not_verified"),
            "before": before,
            "after": before,
            "evaluated_node_id": event.node_id,
            "evidence": evidence,
        }, None, verified

    # An accepted isolated submission is useful evidence, but one exercise
    # should not replace a full diagnostic.  Credit it once per resource and
    # leave navigation decisions to the usual review/quiz flow.
    after = min(1.0, round(before + 0.12, 6))
    updated = after > before
    if updated:
        state.dynamic_profile.knowledge_mastery[event.node_id] = after
    mastery = {
        "updated": updated,
        "evidence_accepted": True,
        "reason": "verified_code_submission",
        "before": before,
        "after": after,
        "evaluated_node_id": event.node_id,
        "evidence": evidence,
    }
    if not updated:
        return mastery, None, verified

    attribution = {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "user_id": user_id,
        "course_id": course_id,
        "node_id": event.node_id,
        "resource_id": event.resource_id,
        "question_id": event.question_id,
        "attempt_number": event.attempt_number,
        "used_hint": event.used_hint,
        "duration_ms": event.duration_ms,
        "mastery_before": before,
        "mastery_after": after,
        "mastery_delta": round(after - before, 6),
        "reason": "verified_code_submission",
        "evidence": evidence,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    return mastery, attribution, verified


def _practice_questions_from_card(card: Any) -> list[dict[str, Any]]:
    metadata = getattr(card, "metadata", None) or {}
    if not isinstance(metadata, dict):
        return []
    structured_payload = metadata.get("structured_payload")
    for candidate in (structured_payload, metadata):
        questions = candidate.get("questions") if isinstance(candidate, dict) else None
        if isinstance(questions, list):
            return [question for question in questions if isinstance(question, dict)]
    return []


def _verify_targeted_practice_answer(
    state: AgentState,
    event: LearningEventRequest,
) -> dict[str, Any]:
    """Verify a practice answer without treating it as mastery evidence."""
    result = event.result if isinstance(event.result, dict) else {}
    review_item_id = str(result.get("review_item_id") or "").strip()
    if not review_item_id:
        return {"verified": False, "correct": False, "reason": "review_item_id_required"}
    if not event.resource_id or not event.question_id:
        return {
            "verified": False,
            "correct": False,
            "reason": "targeted_practice_identity_required",
            "review_item_id": review_item_id,
        }

    card = next(
        (
            candidate
            for candidate in state.generated_resources.get(event.node_id, [])
            if getattr(candidate, "resource_id", "") == event.resource_id
            and getattr(candidate, "card_type", "") == "interactive_exercise"
        ),
        None,
    )
    if card is None:
        return {
            "verified": False,
            "correct": False,
            "reason": "targeted_practice_resource_not_found",
            "review_item_id": review_item_id,
            "resource_id": event.resource_id,
            "question_id": event.question_id,
        }

    question = next(
        (
            candidate
            for candidate in _practice_questions_from_card(card)
            if str(candidate.get("id") or "").strip() == event.question_id
        ),
        None,
    )
    if question is None:
        return {
            "verified": False,
            "correct": False,
            "reason": "targeted_practice_question_not_found",
            "review_item_id": review_item_id,
            "resource_id": event.resource_id,
            "question_id": event.question_id,
        }

    expected_index = question.get("answer_index")
    selected_index = result.get("answer_index", result.get("selected_option_index"))
    if (
        isinstance(expected_index, bool)
        or not isinstance(expected_index, int)
        or expected_index < 0
        or isinstance(selected_index, bool)
        or not isinstance(selected_index, int)
        or selected_index < 0
    ):
        return {
            "verified": False,
            "correct": False,
            "reason": "targeted_practice_answer_invalid",
            "review_item_id": review_item_id,
            "resource_id": event.resource_id,
            "question_id": event.question_id,
        }

    return {
        "verified": True,
        "correct": selected_index == expected_index,
        "reason": (
            "verified_targeted_practice_correct"
            if selected_index == expected_index
            else "verified_targeted_practice_incorrect"
        ),
        "review_item_id": review_item_id,
        "resource_id": event.resource_id,
        "question_id": event.question_id,
        "selected_index": selected_index,
        "attempt_number": event.attempt_number,
    }


def load_session(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    session = load_persisted_session(user_id, course_id)
    if session is None:
        return {"status": "not_found", "user_id": user_id, "course_id": course_id}
    return state_response(session)


def restore_or_create_session(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    return state_response(get_session(user_id, course_id))


def create_session(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    return state_response(get_session(user_id, course_id))


def restore_session(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    return create_session(user_id, course_id)


def reset_learning_session(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    session = reset_session(user_id, course_id)
    persist_session(session)
    return {"status": "ok", "user_id": user_id, "course_id": course_id}


def get_learning_state(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    return state_response(get_session(user_id, course_id), include_legacy=True)


def init_path(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    with bind_context(user_id=user_id, course_id=course_id, operation="init_path"):
        session = get_session(user_id, course_id)
        state = session.agent_state
        if not state.active_path:
            topo = session.path_planner.compute_topological_order()
            state.active_path = topo
            if topo:
                state.current_node_id = topo[0]
            session.pipeline_log.append({"agent": "Planner", "event": "initial_path", "path": topo})
            incr_metric("session.replan_total", source="init_path", reason="initial_path")
            log_event("session.path.initialized", path_length=len(topo))
        persist_session(session)
        return {
            "active_path": state.active_path,
            "current_node_id": state.current_node_id,
            "target_node_id": state.target_node_id,
        }


def _legacy_completion_response(
    event_response: Dict[str, Any],
    *,
    interaction_type: str,
    user_id: str,
    course_id: str,
) -> Dict[str, Any]:
    """Expose a transitional advance response without bypassing the event ledger."""
    if event_response.get("status") != "ok":
        return event_response

    state = get_session(user_id, course_id).agent_state
    evaluated_node_id = str(event_response.get("evaluated_node_id") or "")
    knowledge_mastery = event_response.get("knowledge_mastery")
    if not isinstance(knowledge_mastery, dict):
        knowledge_mastery = {
            node_id: round(mastery, 4)
            for node_id, mastery in state.dynamic_profile.knowledge_mastery.items()
        }
    evaluated_mastery = event_response.get("mastery_after")
    if evaluated_mastery is None:
        evaluated_mastery = knowledge_mastery.get(evaluated_node_id, 0.0)

    return {
        **event_response,
        "resource_contract_version": RESOURCE_CONTRACT_VERSION,
        "agent_feedback_version": AGENT_FEEDBACK_VERSION,
        "iteration": state.iteration,
        "interaction_type": interaction_type,
        "current_node_id": event_response.get("current_node_id") or state.current_node_id,
        "evaluated_node_id": evaluated_node_id,
        "evaluated_node_mastery": round(float(evaluated_mastery or 0.0), 4),
        "previous_mastery": event_response.get("mastery_before"),
        "score": event_response.get("effective_correctness"),
        "next_node_title": (
            get_node_title(event_response["next_node_id"], event_response["next_node_id"])
            if event_response.get("next_node_id")
            else None
        ),
        "active_path": state.active_path,
        "pedagogical_strategy": state.pedagogical_strategy,
        "capability_radar": state.dynamic_profile.capability_radar,
        "diagnostic_report": state.dynamic_profile.diagnostic_report_md,
        "knowledge_mastery": knowledge_mastery,
        "generated_cards_count": sum(len(cards) for cards in state.generated_resources.values()),
        "tutor_response": state.tutor_response,
        "re_plan_triggered": state.re_plan_triggered,
        "agent_feedback": [item.model_dump() for item in state.agent_feedback],
        "errors": state.errors[-5:],
        "step_logs": event_response.get("event", {}).get("step_logs", []),
        "all_logs": get_session(user_id, course_id).pipeline_log,
    }


def advance_session(
    user_id: str,
    course_id: str = "data_structures",
    user_input: Optional[str] = None,
    behavior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Advance the official learning flow for one step."""
    with bind_context(user_id=user_id, course_id=course_id, operation="advance_session"):
        started = time.perf_counter()
        input_validation = validate_service_input(
            payload=behavior or {},
            text=user_input,
            field="user_input",
        )
        if not input_validation.passed:
            return validation_blocked_response(input_validation, action="advance_session")
        if user_input is not None:
            user_input = input_validation.sanitized_text or user_input

        # Compatibility callers can still submit server-verifiable quiz
        # answers through /advance, but the result must be recorded as a
        # canonical event. This keeps every mastery change attributable while
        # rejecting score-only payloads in the same way as /events.
        try:
            legacy_event = LearningEventRequest.model_validate(behavior or {})
        except ValidationError:
            legacy_event = None
        if legacy_event is not None and legacy_event.is_terminal:
            event_payload = legacy_event.model_dump(mode="json")
            event_payload["user_id"] = user_id
            event_payload["course_id"] = course_id
            recorded = record_learning_event(user_id, course_id, event_payload)
            return _legacy_completion_response(
                recorded,
                interaction_type=str((behavior or {}).get("interaction_type") or legacy_event.event_type.value),
                user_id=user_id,
                course_id=course_id,
            )

        session = get_session(user_id, course_id)
        result: LearningStepResult = run_official_learning_step(
            session,
            behavior=behavior,
            user_input=user_input,
            runtime=get_runtime(),
        )

        state = result.state
        agent_labels = {
            "Evaluator": "学习评估智能体",
            "Profiler": "画像分析智能体",
            "Planner": "路径规划智能体",
            "Assessment": "综合评估智能体",
            "Validator": "内容校验智能体",
        }
        status_labels = {
            "success": "已完成",
            "warning": "需关注",
            "error": "执行失败",
            "skipped": "已跳过",
            "info": "处理中",
        }
        state.agent_feedback = [
            feedback_item(
                agent=log.get("agent", "Agent"),
                stage="统一学习编排",
                status=log.get("status", "success"),
                headline=f"{agent_labels.get(log.get('agent'), '学习智能体')}已完成本轮处理",
                summary=f"已完成「{get_node_title(result.evaluated_node, result.evaluated_node)}」的学习状态分析与更新。",
                structured_data={
                    "处理节点": get_node_title(result.evaluated_node, result.evaluated_node),
                    "运行状态": status_labels.get(log.get("status", "success"), "已完成"),
                },
            )
            for log in result.logs
        ]
        session.agent_state = state
        persist_session(session)

        replan_applied = any(
            log.get("agent") == "Planner" and bool(log.get("replan"))
            for log in result.logs
        )
        if replan_applied:
            replan_reason = next(
                (
                    log.get("replan_decision")
                    for log in result.logs
                    if log.get("agent") == "Evaluator" and log.get("replan_decision")
                ),
                "manual_or_path_init",
            )
            incr_metric(
                "session.replan_total",
                source="pipeline",
                reason=replan_reason,
            )
            log_event(
                "session.replan",
                reason=replan_reason,
                interaction_type=result.interaction_type,
                node_id=result.evaluated_node,
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        observe_metric(
            "session.advance.duration_ms",
            duration_ms,
            interaction_type=result.interaction_type,
        )
        log_event(
            "session.advance.complete",
            interaction_type=result.interaction_type,
            node_id=result.evaluated_node,
            replan_applied=replan_applied,
            advanced_to_next_node=result.advanced_to_next_node,
            duration_ms=duration_ms,
        )

        return {
            "resource_contract_version": RESOURCE_CONTRACT_VERSION,
            "agent_feedback_version": AGENT_FEEDBACK_VERSION,
            "iteration": state.iteration,
            "interaction_type": result.interaction_type,
            "event_type": result.event_type,
            "current_node_id": result.current_node,
            "evaluated_node_id": result.evaluated_node,
            "evaluated_node_mastery": round(result.evaluated_mastery, 4),
            "previous_mastery": round(result.previous_mastery, 4),
            "score": round(result.correctness, 4),
            "evidence_accepted": result.evidence_accepted,
            "mastery_updated": result.mastery_updated,
            "mastery_update_reason": result.mastery_update_reason,
            "advanced_to_next_node": result.advanced_to_next_node,
            "next_node_id": result.next_node_id,
            "next_node_title": (
                get_node_title(result.next_node_id, result.next_node_id)
                if result.next_node_id
                else None
            ),
            "mastery_threshold": MASTERY_ADVANCE_THRESHOLD,
            "active_path": state.active_path,
            "pedagogical_strategy": state.pedagogical_strategy,
            "capability_radar": state.dynamic_profile.capability_radar,
            "diagnostic_report": state.dynamic_profile.diagnostic_report_md,
            "knowledge_mastery": {
                key: round(value, 4)
                for key, value in state.dynamic_profile.knowledge_mastery.items()
            },
            "generated_cards_count": sum(len(cards) for cards in state.generated_resources.values()),
            "tutor_response": state.tutor_response,
            "re_plan_triggered": state.re_plan_triggered,
            "agent_feedback": [item.model_dump() for item in state.agent_feedback],
            "errors": state.errors[-5:],
            "step_logs": result.logs,
            "all_logs": session.pipeline_log,
        }


def record_learning_event(
    user_id: str,
    course_id: str = "data_structures",
    event_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record one event atomically for a learner/course session."""
    with _learning_event_lock(user_id, course_id):
        return _record_learning_event_unlocked(user_id, course_id, event_payload)


def _record_learning_event_unlocked(
    user_id: str,
    course_id: str = "data_structures",
    event_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist one canonical learner event and, when warranted, assess it.

    The route/session identity is authoritative.  A payload may repeat it for
    observability, but a conflicting identity is rejected before any state can
    change.  All ten event kinds are retained in the ledger.  Only terminal
    lesson/review events with evidence accepted by ``_verify_quiz_completion``
    can reach the evaluator and change mastery.  A `code_submitted` event is
    also eligible only when it names an accepted receipt issued by the isolated
    code-execution service.
    """
    payload = event_payload or {}
    try:
        event = LearningEventRequest.model_validate(payload)
    except ValidationError as exc:
        return {
            "status": "invalid_event",
            "blocked": True,
            "status_code": 422,
            "validation": {"issues": exc.errors()},
        }

    if event.user_id and event.user_id != user_id:
        return {
            "status": "invalid_event",
            "blocked": True,
            "status_code": 422,
            "reason": "user_id_mismatch",
        }
    if event.course_id and event.course_id != course_id:
        return {
            "status": "invalid_event",
            "blocked": True,
            "status_code": 422,
            "reason": "course_id_mismatch",
        }

    with bind_context(
        user_id=user_id,
        course_id=course_id,
        operation="record_learning_event",
    ):
        session = get_session(user_id, course_id)
        state = session.agent_state
        event.user_id = user_id
        event.course_id = course_id
        if not event.node_id:
            event.node_id = state.current_node_id or (
                state.active_path[0] if state.active_path else ""
            )

        # Attribution must identify the same resource the verifier used.  A
        # caller cannot attach a valid answer set for one card to a different
        # visible resource id and make the audit trail misleading.
        if event.is_terminal and event.completion_evidence is not None:
            verified_resource_id = event.completion_evidence.resource_id
            if (
                event.resource_id
                and verified_resource_id
                and event.resource_id != verified_resource_id
            ):
                return {
                    "status": "invalid_event",
                    "blocked": True,
                    "status_code": 422,
                    "reason": "resource_id_mismatch",
                }
            if not event.resource_id:
                event.resource_id = verified_resource_id

        history = _event_history(state)
        if event.event_id:
            existing = next(
                (
                    item
                    for item in reversed(history)
                    if isinstance(item, dict) and item.get("event_id") == event.event_id
                ),
                None,
            )
            if existing is not None:
                return _event_response(
                    existing,
                    attribution=_find_event_attribution(state, event.event_id),
                    idempotent=True,
                )

        event.event_id = event.event_id or uuid4().hex
        event_record = event.model_dump(mode="json")
        event_record["received_at"] = datetime.now(timezone.utc).isoformat()
        event_record["current_node_id"] = state.current_node_id or ""
        event_record["mastery"] = {
            "updated": False,
            "evidence_accepted": False,
            "reason": "event_recorded",
            "before": state.dynamic_profile.knowledge_mastery.get(event.node_id, 0.0),
            "after": state.dynamic_profile.knowledge_mastery.get(event.node_id, 0.0),
        }
        history.append(event_record)

        # Opening a lesson is a real navigation action and persists the
        # position, but it must never be confused with learning evidence.
        if event.event_type == LearningEventType.LESSON_OPENED and event.node_id:
            state.current_node_id = event.node_id
            event_record["current_node_id"] = state.current_node_id

        attribution: Optional[dict[str, Any]] = None
        if event.is_terminal:
            # A terminal event may be retained for audit without carrying
            # server-verifiable evidence (for example, the lesson-completed
            # marker emitted after a separately verified review). Do not let
            # that marker move a session back to its old node.
            current_node_before_evaluation = state.current_node_id
            result = run_official_learning_step(
                session,
                behavior=event.orchestration_payload(),
                runtime=get_runtime(),
            )
            state = result.state
            if not result.evidence_accepted:
                state.current_node_id = current_node_before_evaluation
            event_record["current_node_id"] = state.current_node_id or ""
            event_record["mastery"] = {
                "updated": result.mastery_updated,
                "evidence_accepted": result.evidence_accepted,
                "reason": result.mastery_update_reason,
                "before": result.previous_mastery,
                "after": result.evaluated_mastery,
                "evaluated_node_id": result.evaluated_node,
            }
            event_record["learning_result"] = {
                "advanced_to_next_node": result.advanced_to_next_node,
                "next_node_id": result.next_node_id,
                "mastery_threshold": MASTERY_ADVANCE_THRESHOLD,
                "effective_correctness": result.correctness,
                "knowledge_mastery": {
                    node_id: round(mastery, 4)
                    for node_id, mastery in state.dynamic_profile.knowledge_mastery.items()
                },
            }

            # The existing completion ledger records the server-derived score.
            # Attach the event id so old diagnostic audits and the new unified
            # event stream point at the same underlying evidence.
            verified_evidence = _latest_verified_evidence(state, event)
            if result.evidence_accepted and verified_evidence:
                event_record["verified_evidence"] = verified_evidence
                verified_evidence["event_id"] = event.event_id
                records = state.internal_state.get("verified_completion_events", [])
                if isinstance(records, list) and records and isinstance(records[-1], dict):
                    records[-1]["event_id"] = event.event_id

            if (
                result.evidence_accepted
                and verified_evidence
                and isinstance(verified_evidence.get("question_results"), list)
            ):
                # A review item is an immutable snapshot of server-derived
                # question evidence. Any verified terminal diagnostic, whether
                # submitted as lesson_completed or review_completed, follows
                # this path. Browser-provided scores and explanations never
                # participate in the transition.
                from . import review_service

                event_record["review"] = review_service.record_verified_diagnostic(
                    state,
                    event_id=event.event_id,
                    node_id=result.evaluated_node or event.node_id,
                    resource_id=event.resource_id,
                    evidence=verified_evidence,
                    correctness=result.correctness,
                    mastery_after=result.evaluated_mastery,
                )

            if result.mastery_updated:
                attribution = {
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "user_id": user_id,
                    "course_id": course_id,
                    "node_id": result.evaluated_node,
                    "resource_id": event.resource_id,
                    "question_id": event.question_id,
                    "attempt_number": event.attempt_number,
                    "used_hint": event.used_hint,
                    "duration_ms": event.duration_ms,
                    "mastery_before": result.previous_mastery,
                    "mastery_after": result.evaluated_mastery,
                    "mastery_delta": round(
                        result.evaluated_mastery - result.previous_mastery,
                        6,
                    ),
                    "reason": result.mastery_update_reason,
                    "evidence": verified_evidence,
                    "recorded_at": event_record["received_at"],
                }
                attributions = _mastery_attributions(state)
                attributions.append(attribution)
        elif event.event_type == LearningEventType.ANSWER_SUBMITTED:
            practice_verification = _verify_targeted_practice_answer(state, event)
            event_record["practice_verification"] = practice_verification
            session.pipeline_log.append({
                "agent": "LearningEvent",
                "event": event.event_type.value,
                "event_id": event.event_id,
                "node_id": event.node_id,
                "mastery_updated": False,
                "practice_verified": bool(practice_verification.get("verified")),
                "practice_correct": bool(practice_verification.get("correct")),
            })
        elif event.event_type == LearningEventType.CODE_SUBMITTED:
            mastery, attribution, receipt_verification = _record_verified_code_submission(
                state,
                event,
                user_id=user_id,
                course_id=course_id,
            )
            event_record["mastery"] = mastery
            if receipt_verification.get("receipt_verified"):
                # Non-accepted receipts are useful review evidence but never
                # mastery evidence. An accepted receipt can close only its
                # matching durable code-review item.
                from . import review_service

                receipt_evidence = receipt_verification.get("evidence")
                event_record["review"] = review_service.record_verified_code_submission(
                    state,
                    event_id=event.event_id,
                    node_id=event.node_id,
                    resource_id=event.resource_id,
                    evidence=(
                        receipt_evidence
                        if isinstance(receipt_evidence, dict)
                        else {}
                    ),
                    receipt_accepted=bool(receipt_verification.get("receipt_accepted")),
                )
            event_record["learning_result"] = {
                "advanced_to_next_node": False,
                "next_node_id": None,
                "mastery_threshold": MASTERY_ADVANCE_THRESHOLD,
                "effective_correctness": 1.0 if mastery["evidence_accepted"] else 0.0,
                "knowledge_mastery": {
                    node_id: round(mastery_value, 4)
                    for node_id, mastery_value in state.dynamic_profile.knowledge_mastery.items()
                },
            }
            session.pipeline_log.append({
                "agent": "LearningEvent",
                "event": event.event_type.value,
                "event_id": event.event_id,
                "node_id": event.node_id,
                "mastery_updated": bool(attribution),
                "reason": mastery["reason"],
            })
            if attribution is not None:
                _mastery_attributions(state).append(attribution)
        else:
            session.pipeline_log.append({
                "agent": "LearningEvent",
                "event": event.event_type.value,
                "event_id": event.event_id,
                "node_id": event.node_id,
                "mastery_updated": False,
            })

        # Keep a compact, non-scoring resume record alongside the authoritative
        # event ledger.  Asset synchronization is intentionally best-effort:
        # failure to save UI restoration state must never block a verified
        # learning event or alter its mastery result.
        try:
            from . import learning_assets_service

            learning_assets_service.record_learning_event_asset(state, event_record)
        except Exception as exc:
            state.record_error(f"learning_asset_sync_failed:{type(exc).__name__}")

        session.agent_state = state
        persist_session(session)
        incr_metric("learning_event.recorded_total", event_type=event.event_type.value)
        if event.is_terminal:
            mastery_result = event_record.get("mastery")
            evidence_accepted = bool(
                isinstance(mastery_result, dict)
                and mastery_result.get("evidence_accepted") is True
            )
            incr_metric(
                "learning.node_completion_attempt_total",
                event_type=event.event_type.value,
                outcome="accepted" if evidence_accepted else "rejected",
            )
            if evidence_accepted:
                learning_result = event_record.get("learning_result")
                advanced = bool(
                    isinstance(learning_result, dict)
                    and learning_result.get("advanced_to_next_node") is True
                )
                incr_metric(
                    "learning.node_completion_total",
                    event_type=event.event_type.value,
                    advanced=str(advanced).lower(),
                )
        if attribution is not None:
            incr_metric(
                "learning_event.mastery_update_total",
                event_type=event.event_type.value,
            )
        mastery_result = event_record.get("mastery")
        if isinstance(mastery_result, dict) and mastery_result.get("updated") is True:
            incr_metric(
                "learning_event.mastery_mutation_total",
                outcome="attributed" if attribution is not None else "unattributed",
            )
        log_event(
            "learning_event.recorded",
            event_id=event.event_id,
            event_type=event.event_type.value,
            node_id=event.node_id,
            mastery_updated=bool(attribution),
        )
        return _event_response(event_record, attribution=attribution)


def get_learning_event_history(
    user_id: str,
    course_id: str = "data_structures",
    *,
    node_id: Optional[str] = None,
    event_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Return durable event and mastery provenance records for audit views."""
    session = get_session(user_id, course_id)
    state = session.agent_state
    requested_node_id = str(node_id or "").strip()
    requested_event_id = str(event_id or "").strip()
    try:
        bounded_limit = min(500, max(1, int(limit or 100)))
    except (TypeError, ValueError):
        bounded_limit = 100

    all_events = [dict(event) for event in _event_history(state)]
    opened_nodes = {
        str(event.get("node_id") or "").strip()
        for event in all_events
        if event.get("event_type") == LearningEventType.LESSON_OPENED.value
        and str(event.get("node_id") or "").strip()
    }
    verified_completed_nodes = set()
    for event in all_events:
        if event.get("event_type") not in {
            LearningEventType.LESSON_COMPLETED.value,
            LearningEventType.REVIEW_COMPLETED.value,
        }:
            continue
        mastery = event.get("mastery") if isinstance(event.get("mastery"), dict) else {}
        if mastery.get("evidence_accepted") is not True:
            continue
        node = str(mastery.get("evaluated_node_id") or event.get("node_id") or "").strip()
        if node:
            verified_completed_nodes.add(node)
    completed_opened_nodes = opened_nodes & verified_completed_nodes
    completion_rate = (
        round(len(completed_opened_nodes) / len(opened_nodes), 6)
        if opened_nodes
        else None
    )

    events = [
        event
        for event in all_events
        if (not requested_node_id or event.get("node_id") == requested_node_id)
        and (not requested_event_id or event.get("event_id") == requested_event_id)
    ][-bounded_limit:]
    attributions = [
        dict(attribution)
        for attribution in _mastery_attributions(state)
        if (not requested_node_id or attribution.get("node_id") == requested_node_id)
        and (not requested_event_id or attribution.get("event_id") == requested_event_id)
    ][-bounded_limit:]
    return {
        "status": "ok",
        "user_id": user_id,
        "course_id": course_id,
        "node_id": requested_node_id or None,
        "event_id": requested_event_id or None,
        "events": events,
        "mastery_attributions": attributions,
        "learning_funnel": {
            "opened_nodes": len(opened_nodes),
            "verified_completed_nodes": len(completed_opened_nodes),
            "verified_completed_without_open": len(verified_completed_nodes - opened_nodes),
            "completion_rate": completion_rate,
            "definition": "unique verified completed opened nodes / unique opened nodes",
        },
    }


def request_replan(
    user_id: str,
    course_id: str = "data_structures",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    with bind_context(user_id=user_id, course_id=course_id, operation="request_replan"):
        input_validation = validate_service_input(
            payload=payload or {},
            field="replan",
        )
        if not input_validation.passed:
            return validation_blocked_response(input_validation, action="request_replan")

        incr_metric("session.replan_total", source="request", reason="manual_request")
        log_event(
            "session.replan.requested",
            payload_keys=sorted((payload or {}).keys()),
        )

        session = get_session(user_id, course_id)
        session.agent_state.trigger_replan()
        return advance_session(user_id, course_id, behavior={"interaction_type": "load_node"})
