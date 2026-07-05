# -*- coding: utf-8 -*-
"""Session creation, restoration, and official learning advancement."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.agents.assessment_node import AssessmentInput
from src.agents.content_mesh_node import MeshInput
from src.agents.evaluator_node import BehaviorVector, EvaluatorInput
from src.agents.profiler_node import ProfilerInput
from src.agents.tutor_node import TutorInput
from src.agents.validator_node import ValidatorInput
from src.orchestration_runtime import get_runtime
from src.state.agent_state import AgentState, LatestBehavior

from ._common import (
    AGENT_FEEDBACK_VERSION,
    MASTERY_ADVANCE_THRESHOLD,
    RESOURCE_CONTRACT_VERSION,
    feedback_item,
    get_node_title,
    get_session,
    load_persisted_session,
    normalize_state_resources,
    persist_session,
    reset_session,
    state_response,
)
from .resource_service import generate_current_node_resources



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


def _find_next_pending_node(active_path: list[str], mastery_map: Dict[str, float], current_node: str) -> Optional[str]:
    start_index = active_path.index(current_node) + 1 if current_node in active_path else 0
    for node_id in active_path[start_index:]:
        if mastery_map.get(node_id, 0.0) < MASTERY_ADVANCE_THRESHOLD:
            return node_id
    return None


def advance_session(
    user_id: str,
    course_id: str = "data_structures",
    user_input: Optional[str] = None,
    behavior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    runtime = get_runtime()
    session = get_session(user_id, course_id)
    state: AgentState = session.agent_state
    payload = behavior or {}
    interaction_type = payload.get("interaction_type", "practice")
    target_node = payload.get("current_node_id")
    if target_node:
        state.current_node_id = target_node

    current_node = state.current_node_id or (state.active_path[0] if state.active_path else "N01")
    previous_mastery = state.dynamic_profile.knowledge_mastery.get(current_node, 0.0)
    correctness = float(payload.get("correctness", 0.75))
    time_spent_ratio = float(payload.get("time_spent_ratio", 1.0))
    code_pass_rate = float(payload.get("code_pass_rate", 0.70))
    help_count = int(payload.get("help_count", 0))
    tutor_query = payload.get("tutor_query") or user_input
    logs: list[Dict[str, Any]] = []

    if interaction_type == "load_node":
        logs.append({"agent": "Evaluator", "status": "skipped", "reason": "interaction_type=load_node"})
        logs.append({"agent": "Profiler", "status": "skipped", "reason": "interaction_type=load_node"})
    else:
        state.latest_behavior = LatestBehavior(
            node_id=current_node,
            correctness=correctness,
            time_spent_ratio=time_spent_ratio,
            error_types=[],
            resource_feedback={},
            help_request_count=help_count,
            tutor_query=tutor_query,
            accuracy_rate=correctness,
            code_pass_rate=code_pass_rate,
            duration_ratio=time_spent_ratio,
        )
        eval_output = runtime.evaluator(EvaluatorInput(
            agent_state=state,
            raw_behavior=BehaviorVector(
                answer_correctness=correctness,
                code_pass_rate=code_pass_rate,
                time_spent_ratio=time_spent_ratio,
                help_request_count=help_count,
                node_id=current_node,
            ),
        ))
        state = eval_output.agent_state
        logs.append({
            "agent": "Evaluator",
            "effective_correctness": eval_output.cleaned_behavior.effective_correctness,
            "anomaly_type": eval_output.cleaned_behavior.anomaly.anomaly_type.value,
            "anomaly_detected": eval_output.anomaly_detected,
            "mastery_delta": round(eval_output.mastery_delta, 4),
            "pid_error": round(eval_output.pid_error, 4),
            "replan_decision": eval_output.replan_decision.value,
            "updated_mastery": round(eval_output.updated_mastery, 4),
        })

        prof_output = runtime.profiler(ProfilerInput(
            agent_state=state,
            evaluator_mastery_delta=eval_output.mastery_delta,
            evaluator_pid_error=eval_output.pid_error,
            resource_style_delivered=state.recommended_resource_style or "visual",
            node_id=current_node,
        ))
        state = prof_output.agent_state
        logs.append({
            "agent": "Profiler",
            "selected_style": prof_output.style_result.selected_style,
            "sample_values": prof_output.style_result.sample_values,
            "intervention_triggered": prof_output.intervention_active,
            "forgetting_decay": round(prof_output.forgetting_result.decay_factor, 4) if prof_output.forgetting_result else None,
        })

    if not state.active_path or state.re_plan_triggered:
        state.active_path = session.path_planner.compute_topological_order()
        state.re_plan_triggered = False
        logs.append({"agent": "Planner", "replan": True, "new_path": state.active_path})
    else:
        logs.append({"agent": "Planner", "replan": False, "active_path": state.active_path})

    if not state.active_path and current_node:
        state.active_path = [current_node]
    if current_node and current_node in state.active_path:
        state.active_path = [current_node, *[node for node in state.active_path if node != current_node]]

    if tutor_query and interaction_type != "load_node":
        tutor_output = runtime.tutor(TutorInput(agent_state=state))
        state = tutor_output.agent_state
        logs.append({
            "agent": "Tutor",
            "query": tutor_query,
            "has_mermaid": bool(state.tutor_response.get("mermaid_src", "") if state.tutor_response else False),
        })

    mesh_output = runtime.mesh(MeshInput(agent_state=state))
    state = mesh_output.agent_state
    logs.append({
        "agent": "ContentMesh",
        "generated_cards": len(mesh_output.generated_cards),
        "card_types": [card.card_type for card in mesh_output.generated_cards],
    })
    session.agent_state = state
    generate_current_node_resources(user_id, course_id, current_node, force=False)
    state = session.agent_state

    cards_to_validate = list(state.generated_resources.get(current_node, []))
    if cards_to_validate:
        val_output = runtime.validator(ValidatorInput(
            agent_state=state,
            cards_to_validate=cards_to_validate[-5:],
            ground_truth_context="Data structures organize and store data for efficient access and update.",
            enable_pole2=False,
        ))
        state = val_output.agent_state
        logs.append({
            "agent": "Validator",
            "valid_cards": len(val_output.valid_cards),
            "rejected_cards": len(val_output.rejected_cards),
            "refined_cards": len(val_output.refined_cards),
            "overall_pass_rate": round(val_output.overall_pass_rate, 2),
        })
    else:
        logs.append({"agent": "Validator", "status": "no_cards_to_validate"})

    if interaction_type == "load_node":
        logs.append({"agent": "Assessment", "status": "skipped", "reason": "interaction_type=load_node"})
    else:
        assess_output = runtime.assessment(AssessmentInput(agent_state=state))
        state = assess_output.agent_state
        logs.append({
            "agent": "Assessment",
            "capability_radar": state.dynamic_profile.capability_radar,
            "pedagogical_strategy": state.pedagogical_strategy,
            "a_mix": round(sum(state.dynamic_profile.capability_radar) / 5, 4),
        })

    evaluated_mastery = state.dynamic_profile.knowledge_mastery.get(current_node, previous_mastery)
    next_node_id = None
    advanced_to_next_node = False
    if interaction_type == "diagnostic" and evaluated_mastery >= MASTERY_ADVANCE_THRESHOLD:
        next_node_id = _find_next_pending_node(state.active_path, state.dynamic_profile.knowledge_mastery, current_node)
        if next_node_id:
            state.current_node_id = next_node_id
            advanced_to_next_node = True
        else:
            state.current_node_id = current_node
    else:
        state.current_node_id = current_node

    state.agent_feedback = [
        feedback_item(
            agent=log.get("agent", "Agent"),
            stage="official_orchestration",
            status=log.get("status", "success"),
            headline=f"{log.get('agent', 'Agent')} completed",
            summary=f"Processed {get_node_title(current_node, current_node)} through the official service layer.",
            structured_data=log,
        )
        for log in logs
    ]
    normalize_state_resources(state)
    session.agent_state = state
    session.pipeline_log.extend(logs)
    persist_session(session)

    return {
        "resource_contract_version": RESOURCE_CONTRACT_VERSION,
        "agent_feedback_version": AGENT_FEEDBACK_VERSION,
        "iteration": state.iteration,
        "interaction_type": interaction_type,
        "current_node_id": state.current_node_id,
        "evaluated_node_id": current_node,
        "evaluated_node_mastery": round(evaluated_mastery, 4),
        "previous_mastery": round(previous_mastery, 4),
        "score": round(correctness, 4),
        "advanced_to_next_node": advanced_to_next_node,
        "next_node_id": next_node_id,
        "next_node_title": get_node_title(next_node_id, next_node_id) if next_node_id else None,
        "mastery_threshold": MASTERY_ADVANCE_THRESHOLD,
        "active_path": state.active_path,
        "pedagogical_strategy": state.pedagogical_strategy,
        "capability_radar": state.dynamic_profile.capability_radar,
        "diagnostic_report": state.dynamic_profile.diagnostic_report_md,
        "knowledge_mastery": {key: round(value, 4) for key, value in state.dynamic_profile.knowledge_mastery.items()},
        "generated_cards_count": sum(len(cards) for cards in state.generated_resources.values()),
        "tutor_response": state.tutor_response,
        "re_plan_triggered": state.re_plan_triggered,
        "agent_feedback": [item.model_dump() for item in state.agent_feedback],
        "errors": state.errors[-5:],
        "step_logs": logs,
        "all_logs": session.pipeline_log,
    }
