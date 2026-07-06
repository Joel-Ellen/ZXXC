# -*- coding: utf-8 -*-
"""Deprecated orchestration compatibility facade for core exports.

Application use cases live in ``src.application.*`` services. This module only
keeps legacy access to formal core orchestration symbols.
"""

__all__ = [
    "ColdStartOrchestrator",
    "EduAgentGraph",
    "LearningStepResult",
    "run_official_learning_step",
]

_CORE_EXPORTS = {
    "ColdStartOrchestrator",
    "EduAgentGraph",
    "LearningStepResult",
    "run_official_learning_step",
}

_REMOVED_SERVICE_EXPORTS = {
    "advance_session": "src.application.session_service.advance_session",
    "bootstrap_session": "src.orchestration_runtime.get_runtime",
    "generate_current_node_resources": (
        "src.application.resource_service.generate_current_node_resources"
    ),
    "run_tutor": "src.application.tutor_service.run_tutor",
}


def __getattr__(name: str):
    if name in _CORE_EXPORTS:
        from src import orchestration_core

        return getattr(orchestration_core, name)
    if name in _REMOVED_SERVICE_EXPORTS:
        raise AttributeError(
            f"module 'src.orchestration' no longer exposes {name!r}; "
            f"use {_REMOVED_SERVICE_EXPORTS[name]} instead"
        )
    raise AttributeError(f"module 'src.orchestration' has no attribute {name!r}")
