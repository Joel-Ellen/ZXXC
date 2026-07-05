# -*- coding: utf-8 -*-
"""Cold-start profile completion and persistence."""

from __future__ import annotations

from typing import Any, Dict

from src.infrastructure.cold_start import ColdStartPhase

from ._common import get_session, persist_session


def get_probe(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    session = get_session(user_id, course_id)
    cold_state = session.cold_state
    if cold_state.current_phase in (ColdStartPhase.COMPLETE, ColdStartPhase.FUSION_FALLBACK):
        return {"phase": "complete", "probe": None}

    probe = session.cold_engine.get_next_probe(cold_state)
    if probe is None:
        return {"phase": cold_state.current_phase.value, "probe": None}

    return {
        "phase": cold_state.current_phase.value,
        "epoch": cold_state.epoch_counter,
        "collected": cold_state.collected_dimensions,
        "probe": {
            "question": probe.question,
            "options": probe.options,
            "option_values": probe.option_values,
            "is_multi_select": probe.is_multi_select,
            "dimension": probe.dimension,
        },
    }


def submit_probe_answer(user_id: str, course_id: str, answer: Any) -> Dict[str, Any]:
    session = get_session(user_id, course_id)
    state = session.agent_state
    state.internal_state.setdefault("_cold_start_answers", []).append(answer)

    cold_state = session.cold_engine.process_response(session.cold_state, answer)
    session.cold_state = cold_state

    if cold_state.should_fuse():
        fused = session.cold_engine.execute_fusion(cold_state)
        state = session.cold_engine.apply_to_agent_state(cold_state, state)
        state.c_epoch = cold_state.epoch_counter
        session.agent_state = state
        session.pipeline_log.append({
            "agent": "ColdStart",
            "event": "fusion_triggered",
            "fused_dimensions": list(fused.keys()),
        })
        persist_session(session)
        return {"phase": "complete", "fusion_triggered": True, "fused_dimensions": list(fused.keys())}

    if cold_state.all_dimensions_collected():
        state = session.cold_engine.apply_to_agent_state(cold_state, state)
        state.c_epoch = cold_state.epoch_counter
        session.agent_state = state
        persist_session(session)
        return {"phase": "complete", "collected": cold_state.collected_dimensions}

    next_probe = session.cold_engine.get_next_probe(cold_state)
    result: Dict[str, Any] = {
        "phase": cold_state.current_phase.value,
        "epoch": cold_state.epoch_counter,
        "collected": cold_state.collected_dimensions,
    }
    result["next_probe"] = {
        "question": next_probe.question,
        "options": next_probe.options,
        "is_multi_select": next_probe.is_multi_select,
        "dimension": next_probe.dimension,
    } if next_probe else None
    persist_session(session)
    return result
