# -*- coding: utf-8 -*-
"""Shared response builders and persistence helpers for application services."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from src.database import SessionRepo, SessionSnapshotRepo, StateRepo
except Exception:
    StateRepo = None
    SessionRepo = None
    SessionSnapshotRepo = None

from src.orchestration_runtime import RuntimeSession, get_runtime
from src.state.agent_state import AgentFeedbackItem, ResourceCard

RESOURCE_CONTRACT_VERSION = 1
AGENT_FEEDBACK_VERSION = 1
MASTERY_ADVANCE_THRESHOLD = 0.65
RESOURCE_CARD_ORDER = [
    "concept_map",
    "code_snippet",
    "interactive_exercise",
    "video_summary",
    "diagnostic_quiz",
]


def get_session(user_id: str, course_id: str = "data_structures") -> RuntimeSession:
    return restore_or_create_runtime_session(user_id, course_id)


def reset_session(user_id: str, course_id: str = "data_structures") -> RuntimeSession:
    try:
        if SessionSnapshotRepo is not None:
            SessionSnapshotRepo().delete_for_session(user_id, course_id)
        if SessionRepo is not None:
            SessionRepo().delete(user_id, course_id)
        if StateRepo is not None:
            StateRepo().delete_state(user_id, course_id)
    except Exception:
        pass
    return get_runtime().reset_session(user_id, course_id)


def persist_session(session: RuntimeSession) -> None:
    state = session.agent_state
    state_json = state.model_dump_json()
    cold_json = session.cold_state.model_dump_json() if session.cold_state else None

    try:
        if StateRepo is not None:
            StateRepo().save_state(state.user_id, state.course_id, state_json, cold_json)
    except Exception:
        pass

    try:
        if SessionSnapshotRepo is None:
            return
        from src.adapters.state_to_domain import assessment_from_state, path_from_state, profile_from_state, resources_from_state

        SessionSnapshotRepo().save_snapshot(
            state.user_id,
            state.course_id,
            state_json,
            cold_json,
            path_json=path_from_state(state).model_dump(),
            profile_json=profile_from_state(state).model_dump(),
            resource_bundle_json={
                node_id: [resource.model_dump() for resource in resources]
                for node_id, resources in resources_from_state(state).items()
            },
            assessment_json=assessment_from_state(state).model_dump(),
            pipeline_log_json=session.pipeline_log,
        )
    except Exception as exc:
        state.record_error(f"session_snapshot_save_failed:{exc}")


def load_persisted_session(user_id: str, course_id: str = "data_structures") -> Optional[RuntimeSession]:
    try:
        from src.infrastructure.cold_start import ColdStartState
        from src.state.agent_state import AgentState

        runtime = get_runtime()
        snapshot = SessionSnapshotRepo().get_latest(user_id, course_id) if SessionSnapshotRepo is not None else None
        if snapshot:
            state = AgentState.model_validate(snapshot["state_json"])
            cold_state = ColdStartState.model_validate(snapshot["cold_state_json"]) if snapshot.get("cold_state_json") else None
            session = runtime.replace_session_state(user_id, course_id, state, cold_state=cold_state)
            session.pipeline_log = snapshot.get("pipeline_log_json") or []
            return session

        saved = StateRepo().load_state(user_id, course_id) if StateRepo is not None else None
        if saved:
            state = AgentState.model_validate(saved["state_json"])
            cold_state = ColdStartState.model_validate(saved["cold_state_json"]) if saved.get("cold_state_json") else None
            return runtime.replace_session_state(user_id, course_id, state, cold_state=cold_state)
    except Exception:
        return None
    return None


def restore_or_create_runtime_session(user_id: str, course_id: str = "data_structures") -> RuntimeSession:
    runtime = get_runtime()
    in_memory = runtime.peek_session(user_id, course_id)
    if in_memory is not None:
        return in_memory
    persisted = load_persisted_session(user_id, course_id)
    if persisted is not None:
        return persisted
    session = runtime.get_session(user_id, course_id)
    persist_session(session)
    return session


def get_node_title(node_id: Optional[str], default: Optional[str] = None) -> str:
    if not node_id:
        return default or ""
    kg = get_runtime().kg
    return kg.get_node_title(node_id) or default or node_id


def normalize_resource_card(card: ResourceCard) -> ResourceCard:
    title = get_node_title(card.node_id, card.node_id)
    metadata = dict(card.metadata or {})
    metadata.setdefault("title", title)
    metadata.setdefault("render_type", card.card_type)
    metadata.setdefault("contract_version", RESOURCE_CONTRACT_VERSION)
    metadata.setdefault("resource_type", card.card_type)
    metadata.setdefault("body_markdown", card.content)
    metadata.setdefault("structured_payload", {key: value for key, value in metadata.items() if key not in {"validation", "safety", "artifacts", "source_refs"}})
    metadata.setdefault("artifacts", {})
    metadata.setdefault("validation", {"status": "pending", "issues": []})
    metadata.setdefault("safety", {"status": "unknown", "issues": []})
    metadata.setdefault("source_refs", [])
    card.metadata = metadata
    return card


def normalize_state_resources(agent_state) -> None:
    normalized: Dict[str, List[ResourceCard]] = {}
    for node_id, cards in agent_state.generated_resources.items():
        latest_by_type: Dict[str, ResourceCard] = {}
        extras: List[ResourceCard] = []
        for raw_card in cards:
            card = normalize_resource_card(raw_card)
            if card.card_type in RESOURCE_CARD_ORDER:
                latest_by_type[card.card_type] = card
            else:
                extras.append(card)
        normalized[node_id] = [
            latest_by_type[card_type]
            for card_type in RESOURCE_CARD_ORDER
            if card_type in latest_by_type
        ] + extras
    agent_state.generated_resources = normalized


def upsert_resource_card(agent_state, card: ResourceCard) -> None:
    cards = [
        existing
        for existing in agent_state.generated_resources.get(card.node_id, [])
        if existing.card_type != card.card_type
    ]
    cards.append(normalize_resource_card(card))
    agent_state.generated_resources[card.node_id] = cards
    normalize_state_resources(agent_state)


def state_response(session: RuntimeSession) -> Dict[str, Any]:
    from src.adapters.domain_to_response import session_response_from_runtime

    normalize_state_resources(session.agent_state)
    return session_response_from_runtime(session).to_compatible_dict()


def feedback_item(
    agent: str,
    stage: str,
    status: str,
    headline: str,
    summary: str,
    structured_data: Optional[Dict[str, Any]] = None,
    details_md: str = "",
    artifacts: Optional[Dict[str, Any]] = None,
) -> AgentFeedbackItem:
    return AgentFeedbackItem(
        agent=agent,
        stage=stage,
        status=status,
        headline=headline,
        summary=summary,
        details_md=details_md,
        structured_data=structured_data or {},
        artifacts=artifacts or {},
    )
