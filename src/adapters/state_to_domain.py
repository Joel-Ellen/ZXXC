# -*- coding: utf-8 -*-
"""Adapters from AgentState runtime objects to domain models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.contracts.resource_contract import ResourceContract, ResourceSafety, ResourceValidation
from src.domain.assessment import AssessmentResult, StrategyDecision
from src.domain.path import LearningPath, PathNode
from src.domain.profile import DynamicLearningProfile, StudentProfile
from src.domain.resource import LearningResource, ResourceBundle
from src.domain.session import LearningSession, SessionStatus
from src.state.agent_state import AgentState, ResourceCard


def _node_title(node_id: Optional[str]) -> str:
    if not node_id:
        return ""
    try:
        from src.orchestration_runtime import get_runtime

        return get_runtime().kg.get_node_title(node_id) or node_id
    except Exception:
        return node_id


def profile_from_state(state: AgentState) -> StudentProfile:
    means = state.static_profile.cognitive_style_distribution.compute_means()
    return StudentProfile(
        user_id=state.user_id,
        course_id=state.course_id,
        motivation=state.static_profile.motivation,
        time_budget_hours_per_week=state.static_profile.time_budget_hours_per_week,
        knowledge_base=state.static_profile.knowledge_base,
        cognitive_style_weights=means,
    )


def dynamic_profile_from_state(state: AgentState) -> DynamicLearningProfile:
    return DynamicLearningProfile(
        knowledge_mastery=state.dynamic_profile.knowledge_mastery,
        continuous_fail_counter=state.dynamic_profile.continuous_fail_counter,
        capability_radar=state.dynamic_profile.capability_radar,
        diagnostic_report_md=state.dynamic_profile.diagnostic_report_md,
        error_type_distribution=state.dynamic_profile.error_type_distribution.model_dump(),
    )


def session_from_state(state: AgentState) -> LearningSession:
    status = SessionStatus.COLD_START if state.is_cold_start() else SessionStatus.ACTIVE
    return LearningSession(
        user_id=state.user_id,
        course_id=state.course_id,
        status=status,
        current_node_id=state.current_node_id,
        target_node_id=state.target_node_id,
        iteration=state.iteration,
        c_epoch=state.c_epoch,
        re_plan_triggered=state.re_plan_triggered,
        pedagogical_strategy=state.pedagogical_strategy,
        recommended_resource_style=state.recommended_resource_style,
        errors=state.errors[-10:],
    )


def path_from_state(state: AgentState) -> LearningPath:
    nodes: List[PathNode] = []
    for node_id in state.active_path:
        mastery = state.dynamic_profile.knowledge_mastery.get(node_id, 0.0)
        if node_id == state.current_node_id:
            status = "current"
        elif mastery >= 0.65:
            status = "mastered"
        else:
            status = "pending"
        nodes.append(PathNode(id=node_id, title=_node_title(node_id), mastery=mastery, status=status))
    return LearningPath(nodes=nodes, current_node_id=state.current_node_id, target_node_id=state.target_node_id)


def resource_contract_from_card(card: ResourceCard) -> ResourceContract:
    metadata = dict(card.metadata or {})
    title = metadata.get("title") or _node_title(card.node_id) or card.node_id
    validation_payload = metadata.get("validation") if isinstance(metadata.get("validation"), dict) else {}
    safety_payload = metadata.get("safety") if isinstance(metadata.get("safety"), dict) else {}
    generation_payload = metadata.get("generation") if isinstance(metadata.get("generation"), dict) else {}
    artifacts = _redact_answer_keys(metadata.get("artifacts")) if isinstance(metadata.get("artifacts"), dict) else {}
    source_refs = [
        dict(ref)
        for ref in metadata.get("source_refs", [])
        if isinstance(ref, dict)
    ] if isinstance(metadata.get("source_refs"), list) else []
    created_at = metadata.get("created_at") or metadata.get("generated_at")
    canonical_payload = metadata.get("structured_payload")
    if isinstance(canonical_payload, dict):
        structured_payload = _redact_answer_keys(canonical_payload)
    else:
        # Legacy cards stored renderer fields directly in metadata. Keep this
        # fallback until old persisted sessions have naturally migrated.
        structured_payload = _redact_answer_keys({
            key: value
            for key, value in metadata.items()
            if key not in {
                "generation", "validation", "safety", "artifacts", "source_refs",
                "content_version", "knowledge_index_version", "difficulty_basis", "difficulty_rationale",
                "personalization_basis", "cache_basis", "created_at", "generated_at",
            }
        })
    personalization_basis = {"cognitive_style": card.cognitive_style}
    if isinstance(metadata.get("personalization_basis"), dict):
        personalization_basis.update(metadata["personalization_basis"])
    # GET resource reads must remain non-mutating, including for cards saved
    # before provenance/version fields existed. Normalize those fields only in
    # the response so every visible card retains an auditable contract.
    if not source_refs:
        source_refs = [{
            "id": f"legacy-course-node:{card.node_id}",
            "type": "course_node",
            "node_id": card.node_id,
            "title": str(title),
        }]
    content_version = str(
        metadata.get("content_version") or generation_payload.get("content_version") or "legacy-v1"
    )
    if not generation_payload.get("source"):
        generation_payload = {**generation_payload, "source": "legacy"}
    if content_version and "content_version" not in generation_payload:
        generation_payload = {**generation_payload, "content_version": content_version}
    difficulty_basis = (
        metadata.get("difficulty_basis")
        if isinstance(metadata.get("difficulty_basis"), dict)
        else (metadata.get("difficulty_rationale") if isinstance(metadata.get("difficulty_rationale"), dict) else {})
    )
    if not difficulty_basis:
        difficulty_basis = {
            "source": "legacy_card",
            "difficulty": card.difficulty,
        }
    return ResourceContract(
        resource_id=card.resource_id,
        node_id=card.node_id,
        resource_type=card.card_type,
        title=str(title),
        body_markdown=card.content,
        structured_payload=structured_payload,
        artifacts=artifacts,
        difficulty=card.difficulty,
        difficulty_basis=difficulty_basis,
        personalization_basis=personalization_basis,
        generation=generation_payload,
        content_version=content_version,
        validation=ResourceValidation(**validation_payload),
        safety=ResourceSafety(**safety_payload),
        source_refs=source_refs,
        created_at=created_at or ResourceContract(resource_id=card.resource_id, node_id=card.node_id, resource_type=card.card_type).created_at,
    )


_ANSWER_KEY_FIELDS = {
    "answer_index",
    "answerIndex",
    "correct_answer",
    "correctAnswer",
    "correct_option_index",
    "correctOptionIndex",
    "correct_index",
    "correctIndex",
    "selected_option_index",
    "selectedOptionIndex",
}


def _redact_answer_keys(value: Any) -> Any:
    """Keep grading keys in server state while removing them from API contracts."""
    if isinstance(value, dict):
        return {
            key: _redact_answer_keys(item)
            for key, item in value.items()
            if key not in _ANSWER_KEY_FIELDS
        }
    if isinstance(value, list):
        return [_redact_answer_keys(item) for item in value]
    return value


def learning_resource_from_card(card: ResourceCard) -> LearningResource:
    return LearningResource.model_validate(resource_contract_from_card(card).model_dump())


def resource_bundle_from_state(state: AgentState, node_id: str) -> ResourceBundle:
    return ResourceBundle(
        node_id=node_id,
        resources=[learning_resource_from_card(card) for card in state.generated_resources.get(node_id, [])],
    )


def resources_from_state(state: AgentState) -> Dict[str, List[ResourceContract]]:
    return {
        node_id: [resource_contract_from_card(card) for card in cards]
        for node_id, cards in state.generated_resources.items()
    }


def assessment_from_state(state: AgentState) -> AssessmentResult:
    node_id = state.current_node_id
    return AssessmentResult(
        node_id=node_id,
        mastery=state.dynamic_profile.knowledge_mastery.get(node_id, 0.0) if node_id else None,
        capability_radar=state.dynamic_profile.capability_radar,
        diagnostic_report_md=state.dynamic_profile.diagnostic_report_md,
        strategy_decision=StrategyDecision(strategy=state.pedagogical_strategy),
    )
