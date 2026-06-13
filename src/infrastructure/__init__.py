# -*- coding: utf-8 -*-
"""
EduAgent Infrastructure Layer
=============================
底层基础设施层 — 提供与 LangGraph 控制流解耦的纯算法服务。

本包包含：
  - PIDController          : 辅助算法一 — 基于控制论的难度/步长自适应调节器
  - PathPlanner            : 辅助算法三 — 基于拓扑排序 + 最短路径的知识图谱寻路引擎
  - DocumentIngestionPipeline : 数据治理 — Layout-Aware 版面感知动态语义切片
  - GraphBuilder           : 数据治理 — 图谱构建 + Tarjan SCC 环检测 + 传递归约
  - ColdStartEngine        : 冷启动交互 — 情境探针 + 贝叶斯融合熔断
"""

from .pid_controller import PIDController, PIDConfig, PIDStepResult
from .path_planner import (
    PathPlanner,
    PathPlanResult,
    KnowledgeNode,
    KnowledgeEdge,
    PlanContext,
    PathPlanStrategy,
    ReplanTrigger,
)
from .document_chunker import (
    DocumentIngestionPipeline,
    SemanticChunker,
    LayoutParser,
    ChunkConfig,
    ChunkResult,
    ChunkStrategy,
    AtomicBlock,
)
from .graph_builder import (
    GraphBuilder,
    GraphBuildConfig,
    GraphBuildResult,
    SCCDetectionResult,
    TransitiveReductionResult,
    TarjanSCC,
    TransitiveReducer,
)
from .cold_start import (
    ColdStartEngine,
    ColdStartState,
    ColdStartPhase,
    SituationProbe,
    ProbeFactory,
    BayesianPriorFusion,
    handle_cold_start_interaction,
)
from ..vector.elasticsearch_knowledge_base import (
    ElasticsearchKnowledgeBaseClient,
    ElasticsearchKnowledgeBaseConfig,
    ElasticsearchKnowledgeBasePipeline,
    HashingTextEmbedder,
    KnowledgeBaseChunk,
    MarkdownKnowledgeBaseChunker,
    SentenceTransformerEmbedder,
)

__all__ = [
    # PID 控制
    "PIDController",
    "PIDConfig",
    "PIDStepResult",
    # 路径规划
    "PathPlanner",
    "PathPlanResult",
    "KnowledgeNode",
    "KnowledgeEdge",
    "PlanContext",
    "PathPlanStrategy",
    "ReplanTrigger",
    # 文档切片
    "DocumentIngestionPipeline",
    "SemanticChunker",
    "LayoutParser",
    "ChunkConfig",
    "ChunkResult",
    "ChunkStrategy",
    "AtomicBlock",
    # 图谱构建
    "GraphBuilder",
    "GraphBuildConfig",
    "GraphBuildResult",
    "SCCDetectionResult",
    "TransitiveReductionResult",
    "TarjanSCC",
    "TransitiveReducer",
    # 冷启动
    "ColdStartEngine",
    "ColdStartState",
    "ColdStartPhase",
    "SituationProbe",
    "ProbeFactory",
    "BayesianPriorFusion",
    "handle_cold_start_interaction",
    "ElasticsearchKnowledgeBaseClient",
    "ElasticsearchKnowledgeBaseConfig",
    "ElasticsearchKnowledgeBasePipeline",
    "HashingTextEmbedder",
    "KnowledgeBaseChunk",
    "MarkdownKnowledgeBaseChunker",
    "SentenceTransformerEmbedder",
]
