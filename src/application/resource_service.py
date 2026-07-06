# -*- coding: utf-8 -*-
"""Resource lookup and regeneration for the current learning node."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from src.adapters.domain_to_response import resource_response
from src.adapters.state_to_domain import resource_contract_from_card
from src.observability import bind_context, incr_metric, log_event, observe_metric
from src.state.agent_state import ResourceCard
from src.validation.pipeline import get_validation_pipeline

from ._common import (
    RESOURCE_CARD_ORDER,
    get_session,
    normalize_state_resources,
    persist_session,
    upsert_resource_card,
)


def generate_current_node_resources(
    user_id: str,
    course_id: str = "data_structures",
    node_id: Optional[str] = None,
    force: bool = False,
    include_legacy: bool = False,
) -> Dict[str, Any]:
    from src.orchestration_runtime import get_runtime

    with bind_context(
        user_id=user_id,
        course_id=course_id,
        node_id=node_id or "",
        operation="generate_current_node_resources",
    ):
        started = time.perf_counter()
        session = get_session(user_id, course_id)
        state = session.agent_state
        target_node = node_id or state.current_node_id or (state.active_path[0] if state.active_path else None)
        if not target_node:
            return {"error": "node_id is required", "status_code": 400}

        existing = state.generated_resources.get(target_node, [])
        existing_types = {card.card_type for card in existing}
        if not force and existing_types.issuperset(set(RESOURCE_CARD_ORDER)):
            normalize_state_resources(state)
            resources = [
                resource_contract_from_card(card)
                for card in state.generated_resources.get(target_node, [])
            ]
            response = resource_response(target_node, resources, status="already_exists")
            return response.to_compatible_dict() if include_legacy else response.to_dto_dict()

        runtime = get_runtime()
        difficulty = max(0.1, 1.0 - state.dynamic_profile.knowledge_mastery.get(target_node, 0.5))
        rejected_cards = 0
        for card_type in RESOURCE_CARD_ORDER:
            if not force and card_type in existing_types:
                continue
            content = runtime.generate_resource_content(target_node, card_type, difficulty)
            raw_card = ResourceCard(
                resource_id=f"{target_node}_{card_type}_supp",
                node_id=target_node,
                card_type=card_type,
                content=content,
                difficulty=difficulty,
                cognitive_style=state.recommended_resource_style or "textual",
            )
            validated_card, validation = get_validation_pipeline().validate_resource_card(raw_card)
            if validated_card is not None:
                upsert_resource_card(state, validated_card)
            else:
                rejected_cards += 1
                issue_codes = [getattr(issue, "code", "") for issue in validation.issues]
                incr_metric(
                    "validation.reject_total",
                    stage="resource_output",
                    card_type=card_type,
                    code=issue_codes[0] if issue_codes else "validation_failed",
                )
                state.record_error(
                    f"resource_validation_rejected:{target_node}:{card_type}:"
                    + ";".join(issue.message for issue in validation.issues)
                )

        normalize_state_resources(state)
        persist_session(session)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        observe_metric("resource.generate.duration_ms", duration_ms)
        log_event(
            "resource.generate.complete",
            node_id=target_node,
            rejected_cards=rejected_cards,
            force=force,
            duration_ms=duration_ms,
        )

        resources = [
            resource_contract_from_card(card)
            for card in state.generated_resources.get(target_node, [])
        ]
        response = resource_response(target_node, resources, status="generated")
        return response.to_compatible_dict() if include_legacy else response.to_dto_dict()
