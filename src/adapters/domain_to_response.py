# -*- coding: utf-8 -*-
"""Adapters from domain models to API response DTOs."""

from __future__ import annotations

from typing import Dict, List

from src.api_models.resource_response import ResourceResponse
from src.api_models.session_response import SessionResponse
from src.api_models.tutor_response import TutorResponse
from src.contracts.resource_contract import ResourceContract
from src.orchestration_runtime import RuntimeSession

from .state_to_domain import (
    assessment_from_state,
    dynamic_profile_from_state,
    path_from_state,
    profile_from_state,
    resources_from_state,
    session_from_state,
)


def session_response_from_runtime(runtime_session: RuntimeSession) -> SessionResponse:
    state = runtime_session.agent_state
    return SessionResponse(
        session=session_from_state(state),
        profile=profile_from_state(state),
        dynamic_profile=dynamic_profile_from_state(state),
        learning_path=path_from_state(state),
        resources=resources_from_state(state),
        assessment=assessment_from_state(state),
        tutor_response=state.tutor_response,
        agent_feedback=[item.model_dump() for item in state.agent_feedback],
        pipeline_log=runtime_session.pipeline_log[-20:],
    )


def resource_response(node_id: str, resources: List[ResourceContract], status: str = "ok") -> ResourceResponse:
    return ResourceResponse(status=status, node_id=node_id, resources=resources)


def tutor_response(tutor_payload: dict, reference_count: int, agent_feedback: list[dict]) -> TutorResponse:
    return TutorResponse(
        tutor_response=tutor_payload,
        reference_count=reference_count,
        agent_feedback=agent_feedback,
    )
