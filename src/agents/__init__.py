# -*- coding: utf-8 -*-
"""
EduAgent Agent Layer (合并版 — 15 agents)
=========================================
LangGraph Agent Node + Backend B 多智能体集合。

原有 7 个 LangGraph Node (Tutor 已合并 LearningCoach，Assessment 已合并 Evaluation):
  - EvaluatorNode, ProfilerNode, PlannerNode
  - TutorAgentNode (含 5 模式苏格拉底辅导)
  - ContentMeshNode, ValidatorNode
  - AssessmentReporterNode (含 LLM 增强报告)

新增 8 个 Agent（合并自 backend/agents/）:
  - BaseAgent (基类), AgentMessage, BaseAgentState
  - StudentProfilerAgent, KnowledgeAnalysisAgent, ResourcePlannerAgent
  - PPTGeneratorAgent, QuestionGeneratorAgent, MindMapGeneratorAgent
  - CodingPracticeAgent, VideoScriptAgent
"""

# ── 原有 7 个 LangGraph Node ──────────────────────────────────────────
from .evaluator_node import (
    EvaluatorNode, EvaluatorInput, EvaluatorOutput,
    BehaviorVector, CleanedBehavior, PIDReplanGate,
    BehaviorAnomaly, GateConfig,
)
from .profiler_node import (
    ProfilerNode, ProfilerInput, ProfilerOutput,
    ThompsonSampler, EbbinghausForgettingEngine,
    StyleProfileResult, ForgettingCurveResult, create_profiler_node,
)
from .planner_node import (
    PlannerNode, PlannerInput, PlannerOutput,
    DAGDijkstraSolver, PathEdgeInfo, create_planner_node,
)
from .tutor_node import (
    TutorAgentNode, TutorInput, TutorOutput,
    TutorResponseCard, VideoHydrationCard,
    MermaidSyntaxGuard, TutoringMode, create_tutor_node,
)
from .content_mesh_node import (
    ContentMeshNode, MeshInput, MeshOutput,
    WFQScheduler, MarkovShadowPregen, GenerationTask,
    CardType, QueueClass, GenerationStatus, create_content_mesh_node,
)
from .validator_node import (
    ValidatorNode, ValidatorInput, ValidatorOutput,
    Pole1Gate, Pole2Gate, EntityExtractor,
    SlidingWindowSplitter, Pole1Result, Pole2Result, create_validator_node,
)
from .assessment_node import (
    AssessmentReporterNode, AssessmentInput, AssessmentOutput,
    CapabilityRadar, HysteresisStrategyController, create_assessment_node,
)

# ── 新增 10 个 Agent（合并自 backend/）────────────────────────────────
from .base_agent import BaseAgent, AgentMessage, BaseAgentState
from .agent_factory import build_agent, get_default_llm
from .prompt_registry import PROMPT_REGISTRY, build_user_prompt, get_prompt_definition, get_system_prompt
from .prompt_adapters import run_assessment_report_with_llm, run_tutor_mode_with_llm
from .student_profiler_agent import StudentProfilerAgent
from .knowledge_analysis_agent import KnowledgeAnalysisAgent
from .resource_planner_agent import ResourcePlannerAgent
from .ppt_generator_agent import PPTGeneratorAgent
from .question_generator_agent import QuestionGeneratorAgent
from .mindmap_generator_agent import MindMapGeneratorAgent
from .coding_practice_agent import CodingPracticeAgent
from .video_script_agent import VideoScriptAgent
from .resource_generation_agent import ResourceGenerationAgent
__all__ = [
    # Existing 7
    "EvaluatorNode", "EvaluatorInput", "EvaluatorOutput",
    "BehaviorVector", "CleanedBehavior", "PIDReplanGate",
    "BehaviorAnomaly", "GateConfig",
    "ProfilerNode", "ProfilerInput", "ProfilerOutput",
    "ThompsonSampler", "EbbinghausForgettingEngine",
    "StyleProfileResult", "ForgettingCurveResult", "create_profiler_node",
    "PlannerNode", "PlannerInput", "PlannerOutput",
    "DAGDijkstraSolver", "PathEdgeInfo", "create_planner_node",
    "TutorAgentNode", "TutorInput", "TutorOutput",
    "TutorResponseCard", "VideoHydrationCard",
    "MermaidSyntaxGuard", "TutoringMode", "create_tutor_node",
    "ContentMeshNode", "MeshInput", "MeshOutput",
    "WFQScheduler", "MarkovShadowPregen", "GenerationTask",
    "CardType", "QueueClass", "GenerationStatus", "create_content_mesh_node",
    "ValidatorNode", "ValidatorInput", "ValidatorOutput",
    "Pole1Gate", "Pole2Gate", "EntityExtractor",
    "SlidingWindowSplitter", "Pole1Result", "Pole2Result", "create_validator_node",
    "AssessmentReporterNode", "AssessmentInput", "AssessmentOutput",
    "CapabilityRadar", "HysteresisStrategyController", "create_assessment_node",
    # New 10 + base
    "BaseAgent", "AgentMessage", "BaseAgentState",
    "build_agent", "get_default_llm",
    "PROMPT_REGISTRY", "build_user_prompt", "get_prompt_definition", "get_system_prompt",
    "run_assessment_report_with_llm", "run_tutor_mode_with_llm",
    "StudentProfilerAgent", "KnowledgeAnalysisAgent", "ResourcePlannerAgent",
    "PPTGeneratorAgent", "QuestionGeneratorAgent", "MindMapGeneratorAgent",
    "CodingPracticeAgent", "VideoScriptAgent",
    "ResourceGenerationAgent",
    # LearningCoachAgent → 已合并到 TutorAgentNode
    # EvaluationAgent → 已合并到 AssessmentReporterNode
]
