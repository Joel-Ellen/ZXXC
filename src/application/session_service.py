# -*- coding: utf-8 -*-
"""Session creation, restoration, and official learning advancement."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from src.observability import bind_context, incr_metric, log_event, observe_metric
from src.orchestration_core import LearningStepResult, run_official_learning_step
from src.orchestration_runtime import get_runtime
from src.state.agent_state import AgentState

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

        session = get_session(user_id, course_id)
        result: LearningStepResult = run_official_learning_step(
            session,
            behavior=behavior,
            user_input=user_input,
            runtime=get_runtime(),
        )

        state = result.state
        state.agent_feedback = [
            feedback_item(
                agent=log.get("agent", "Agent"),
                stage="official_orchestration",
                status=log.get("status", "success"),
                headline=f"{log.get('agent', 'Agent')} completed",
                summary=(
                    f"Processed {get_node_title(result.evaluated_node, result.evaluated_node)}"
                    " through the official service layer."
                ),
                structured_data=log,
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
            "current_node_id": result.current_node,
            "evaluated_node_id": result.evaluated_node,
            "evaluated_node_mastery": round(result.evaluated_mastery, 4),
            "previous_mastery": round(result.previous_mastery, 4),
            "score": round(result.correctness, 4),
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
