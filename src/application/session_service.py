# -*- coding: utf-8 -*-
"""Session creation, restoration, and official learning advancement."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.orchestration import LearningStepResult, run_official_learning_step
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
    return state_response(get_session(user_id, course_id))


def init_path(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    session = get_session(user_id, course_id)
    state = session.agent_state
    if not state.active_path:
        topo = session.path_planner.compute_topological_order()
        state.active_path = topo
        if topo:
            state.current_node_id = topo[0]
        session.pipeline_log.append({"agent": "Planner", "event": "initial_path", "path": topo})
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
    """Advance the official learning flow for one step.

    Delegates all agent pipeline orchestration to
    :func:`src.orchestration.run_official_learning_step`; this function
    is responsible only for session management and HTTP-response shaping.
    """
    session = get_session(user_id, course_id)

    # ── Delegate to unified orchestration facade ─────────────────────────
    result: LearningStepResult = run_official_learning_step(
        session, behavior=behavior, user_input=user_input,
        runtime=get_runtime(),
    )

    # ── Persist and build response ────────────────────────────────────────
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
            if result.next_node_id else None
        ),
        "mastery_threshold": MASTERY_ADVANCE_THRESHOLD,
        "active_path": state.active_path,
        "pedagogical_strategy": state.pedagogical_strategy,
        "capability_radar": state.dynamic_profile.capability_radar,
        "diagnostic_report": state.dynamic_profile.diagnostic_report_md,
        "knowledge_mastery": {k: round(v, 4) for k, v in state.dynamic_profile.knowledge_mastery.items()},
        "generated_cards_count": sum(len(cards) for cards in state.generated_resources.values()),
        "tutor_response": state.tutor_response,
        "re_plan_triggered": state.re_plan_triggered,
        "agent_feedback": [item.model_dump() for item in state.agent_feedback],
        "errors": state.errors[-5:],
        "step_logs": result.logs,
        "all_logs": session.pipeline_log,
    }
