# -*- coding: utf-8 -*-
"""EduAgent agent package exports.

Importing a single node module should not construct every agent dependency.
Public names are therefore resolved lazily while keeping ``from src.agents
import ...`` compatible for callers.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "EvaluatorNode": ".evaluator_node",
    "EvaluatorInput": ".evaluator_node",
    "EvaluatorOutput": ".evaluator_node",
    "BehaviorVector": ".evaluator_node",
    "CleanedBehavior": ".evaluator_node",
    "PIDReplanGate": ".evaluator_node",
    "BehaviorAnomaly": ".evaluator_node",
    "GateConfig": ".evaluator_node",
    "ProfilerNode": ".profiler_node",
    "ProfilerInput": ".profiler_node",
    "ProfilerOutput": ".profiler_node",
    "ThompsonSampler": ".profiler_node",
    "EbbinghausForgettingEngine": ".profiler_node",
    "StyleProfileResult": ".profiler_node",
    "ForgettingCurveResult": ".profiler_node",
    "create_profiler_node": ".profiler_node",
    "PlannerNode": ".planner_node",
    "PlannerInput": ".planner_node",
    "PlannerOutput": ".planner_node",
    "DAGDijkstraSolver": ".planner_node",
    "PathEdgeInfo": ".planner_node",
    "create_planner_node": ".planner_node",
    "TutorAgentNode": ".tutor_node",
    "TutorInput": ".tutor_node",
    "TutorOutput": ".tutor_node",
    "TutorResponseCard": ".tutor_node",
    "VideoHydrationCard": ".tutor_node",
    "MermaidSyntaxGuard": ".tutor_node",
    "TutoringMode": ".tutor_node",
    "create_tutor_node": ".tutor_node",
    "ContentMeshNode": ".content_mesh_node",
    "MeshInput": ".content_mesh_node",
    "MeshOutput": ".content_mesh_node",
    "WFQScheduler": ".content_mesh_node",
    "MarkovShadowPregen": ".content_mesh_node",
    "GenerationTask": ".content_mesh_node",
    "CardType": ".content_mesh_node",
    "QueueClass": ".content_mesh_node",
    "GenerationStatus": ".content_mesh_node",
    "create_content_mesh_node": ".content_mesh_node",
    "ValidatorNode": ".validator_node",
    "ValidatorInput": ".validator_node",
    "ValidatorOutput": ".validator_node",
    "Pole1Gate": ".validator_node",
    "Pole2Gate": ".validator_node",
    "EntityExtractor": ".validator_node",
    "SlidingWindowSplitter": ".validator_node",
    "Pole1Result": ".validator_node",
    "Pole2Result": ".validator_node",
    "create_validator_node": ".validator_node",
    "AssessmentReporterNode": ".assessment_node",
    "AssessmentInput": ".assessment_node",
    "AssessmentOutput": ".assessment_node",
    "CapabilityRadar": ".assessment_node",
    "HysteresisStrategyController": ".assessment_node",
    "create_assessment_node": ".assessment_node",
    "PROMPT_REGISTRY": ".prompt_registry",
    "build_user_prompt": ".prompt_registry",
    "get_prompt_definition": ".prompt_registry",
    "get_system_prompt": ".prompt_registry",
    "run_assessment_report_with_llm": ".prompt_adapters",
    "run_tutor_mode_with_llm": ".prompt_adapters",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module 'src.agents' has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
