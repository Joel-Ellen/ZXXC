# -*- coding: utf-8 -*-
"""Convenience orchestration API wrappers for service callers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.state.agent_state import AgentState

# ============================================================================
# Official reusable orchestration API
# ============================================================================


def bootstrap_session(agent_state: AgentState) -> AgentState:
    """Prepare a session state through the managed orchestration runtime."""
    from src.orchestration_runtime import get_runtime

    runtime = get_runtime()
    runtime.get_graph()
    runtime.replace_session_state(agent_state.user_id, agent_state.course_id, agent_state)
    return runtime.get_session(agent_state.user_id, agent_state.course_id).agent_state


def advance_session(
    agent_state: AgentState,
    user_input: Optional[str] = None,
    behavior: Optional[Dict[str, Any]] = None,
) -> AgentState:
    """Advance the official learning flow and return the updated AgentState."""
    from src.application.session_service import advance_session as service_advance
    from src.orchestration_runtime import get_runtime

    runtime = get_runtime()
    runtime.replace_session_state(agent_state.user_id, agent_state.course_id, agent_state)
    service_advance(agent_state.user_id, agent_state.course_id, user_input=user_input, behavior=behavior)
    return runtime.get_session(agent_state.user_id, agent_state.course_id).agent_state


def run_tutor(agent_state: AgentState, question: str) -> AgentState:
    """Run tutor answering through the managed runtime."""
    from src.application.tutor_service import run_tutor as service_run_tutor
    from src.orchestration_runtime import get_runtime

    runtime = get_runtime()
    runtime.replace_session_state(agent_state.user_id, agent_state.course_id, agent_state)
    service_run_tutor(agent_state.user_id, agent_state.course_id, question)
    return runtime.get_session(agent_state.user_id, agent_state.course_id).agent_state


def generate_current_node_resources(agent_state: AgentState, force: bool = False) -> AgentState:
    """Generate resources for the state's current node through the official runtime."""
    from src.application.resource_service import generate_current_node_resources as service_generate
    from src.orchestration_runtime import get_runtime

    runtime = get_runtime()
    runtime.replace_session_state(agent_state.user_id, agent_state.course_id, agent_state)
    service_generate(agent_state.user_id, agent_state.course_id, agent_state.current_node_id, force=force)
    return runtime.get_session(agent_state.user_id, agent_state.course_id).agent_state
