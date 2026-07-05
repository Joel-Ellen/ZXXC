# -*- coding: utf-8 -*-
"""Assessment service entry points."""

from __future__ import annotations

from typing import Any, Dict

from src.agents.assessment_node import AssessmentInput

from ._common import get_session, persist_session


def run_assessment(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    from src.orchestration_runtime import get_runtime

    session = get_session(user_id, course_id)
    output = get_runtime().assessment(AssessmentInput(agent_state=session.agent_state))
    session.agent_state = output.agent_state
    persist_session(session)
    return generate_assessment_summary(user_id, course_id)


def generate_assessment_summary(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    state = get_session(user_id, course_id).agent_state
    return {
        "capability_radar": state.dynamic_profile.capability_radar,
        "diagnostic_report": state.dynamic_profile.diagnostic_report_md,
        "pedagogical_strategy": state.pedagogical_strategy,
    }
