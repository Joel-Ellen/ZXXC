# -*- coding: utf-8 -*-
"""Deprecated orchestration compatibility facade.

New code should import formal learning-step orchestration from
``src.orchestration_core`` and service convenience wrappers from
``src.orchestration_api``. This module remains only so older imports keep
working while the official runtime uses the split modules directly.
"""

__all__ = [
    "ColdStartOrchestrator",
    "EduAgentGraph",
    "LearningStepResult",
    "run_official_learning_step",
    "advance_session",
    "bootstrap_session",
    "generate_current_node_resources",
    "run_tutor",
]

_CORE_EXPORTS = {
    "ColdStartOrchestrator",
    "EduAgentGraph",
    "LearningStepResult",
    "run_official_learning_step",
}

_API_EXPORTS = {
    "advance_session",
    "bootstrap_session",
    "generate_current_node_resources",
    "run_tutor",
}


def __getattr__(name: str):
    if name in _CORE_EXPORTS:
        from src import orchestration_core

        return getattr(orchestration_core, name)
    if name in _API_EXPORTS:
        from src import orchestration_api

        return getattr(orchestration_api, name)
    raise AttributeError(f"module 'src.orchestration' has no attribute {name!r}")
