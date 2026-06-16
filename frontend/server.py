# -*- coding: utf-8 -*-
"""
EduAgent 前后端对接服务器
========================
基于 Starlette 的 HTTP + SSE 服务器，将 LangGraph 多智能体系统
与前端展示页面完整对接。

启动方式:
    cd frontend
    pip install starlette uvicorn sse-starlette
    python server.py

然后访问 http://localhost:8800
"""

from __future__ import annotations

import sys
import os
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import JSONResponse, Response
from starlette.requests import Request
from sse_starlette.sse import EventSourceResponse

# ⚠️ 必须在导入 sentence-transformers 之前设置，否则模型下载会直连 HuggingFace 被墙
# 加载 .env 文件
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                if _k.strip() not in os.environ:
                    os.environ[_k.strip()] = _v.strip()

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import json
import time
import uuid
import asyncio
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, List

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── LLM 客户端（全局单例）─────────────────────────────────
_llm_client = None

def _get_llm():
    global _llm_client
    if _llm_client is None:
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if api_key:
            from src.llm.client import LLMClient, LLMConfig, Provider
            config = LLMConfig(
                provider=Provider.DASHSCOPE,
                dashscope_api_key=api_key,
                dashscope_model="qwen-plus",
                max_tokens=512,
                temperature=0.7,
                timeout_seconds=15,
                max_retries=0,
            )
            _llm_client = LLMClient(config)
            print(f"[LLM] DashScope qwen-plus connected")
        else:
            print("[LLM] No API key found, using fallback mode")
    return _llm_client


# ─── 导入项目模块 ───────────────────────────────────────────
from src.state.agent_state import (
    AgentState, StaticProfile, DynamicProfile,
    CognitiveStyleDistribution, ErrorTypeDistribution,
    LatestBehavior, ResourceCard, KnowledgeMasteryRecord,
)
from src.agents.evaluator_node import (
    EvaluatorNode, EvaluatorInput, BehaviorVector, BehaviorCleaner,
    PIDReplanController, GateConfig, AnomalyType,
)
from src.agents.profiler_node import (
    ProfilerNode, ProfilerInput, ThompsonSampler, EbbinghausForgettingEngine,
)
from src.agents.planner_node import PlannerNode, PlannerInput, DAGDijkstraSolver
from src.agents.tutor_node import TutorAgentNode, TutorInput, MermaidSyntaxGuard
from src.agents.content_mesh_node import (
    ContentMeshNode, MeshInput, WFQScheduler, MarkovShadowPregen,
    WfqConfig, ShadowPregenConfig, QueueClass, CardType, GenerationTask,
)
from src.agents.validator_node import (
    ValidatorNode, ValidatorInput, Pole1Gate, Pole2Gate,
)
from src.agents.assessment_node import (
    AssessmentReporterNode, AssessmentInput,
    HysteresisStrategyController, CapabilityRadar,
)
from src.infrastructure.cold_start import (
    ColdStartEngine, ColdStartState, ColdStartPhase,
    SituationProbe, ProbeFactory,
)
from src.infrastructure.path_planner import (
    PathPlanner, KnowledgeNode, KnowledgeEdge, PathPlanStrategy, PlanContext,
)
from src.infrastructure.pid_controller import PIDController, PIDConfig

# ─── 模拟知识图谱 ───────────────────────────────────────────
MOCK_KNOWLEDGE_NODES = [
    KnowledgeNode(node_id="N01", title="算法复杂度分析", difficulty=0.25, estimated_hours=2.0, category="concept"),
    KnowledgeNode(node_id="N02", title="线性表与顺序存储", difficulty=0.30, estimated_hours=2.5, category="concept"),
    KnowledgeNode(node_id="N03", title="链表与链式存储", difficulty=0.30, estimated_hours=2.5, category="concept"),
    KnowledgeNode(node_id="N04", title="栈及其应用", difficulty=0.35, estimated_hours=2.0, category="concept"),
    KnowledgeNode(node_id="N05", title="队列及其应用", difficulty=0.35, estimated_hours=2.0, category="concept"),
    KnowledgeNode(node_id="N06", title="树与二叉树基础", difficulty=0.45, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N07", title="二叉搜索树", difficulty=0.50, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N08", title="AVL 平衡树", difficulty=0.60, estimated_hours=3.5, category="concept"),
    KnowledgeNode(node_id="N09", title="散列表与哈希", difficulty=0.55, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N10", title="图的基本概念与存储", difficulty=0.50, estimated_hours=2.5, category="concept"),
    KnowledgeNode(node_id="N11", title="图的遍历 DFS/BFS", difficulty=0.55, estimated_hours=3.0, category="skill"),
    KnowledgeNode(node_id="N12", title="最小生成树", difficulty=0.65, estimated_hours=3.5, category="skill"),
    KnowledgeNode(node_id="N13", title="最短路径算法", difficulty=0.70, estimated_hours=4.0, category="skill"),
    KnowledgeNode(node_id="N14", title="拓扑排序与关键路径", difficulty=0.70, estimated_hours=3.5, category="skill"),
    KnowledgeNode(node_id="N15", title="排序算法基础", difficulty=0.55, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N16", title="高级排序算法", difficulty=0.65, estimated_hours=4.0, category="skill"),
    KnowledgeNode(node_id="N17", title="查找与索引技术", difficulty=0.60, estimated_hours=3.0, category="concept"),
    KnowledgeNode(node_id="N18", title="动态规划入门", difficulty=0.75, estimated_hours=5.0, category="skill"),
    KnowledgeNode(node_id="N19", title="贪心算法与回溯", difficulty=0.70, estimated_hours=4.5, category="skill"),
    KnowledgeNode(node_id="N20", title="数据结构综合应用", difficulty=0.80, estimated_hours=6.0, category="project"),
]

MOCK_KNOWLEDGE_EDGES = [
    # 算法基础 → 各种数据结构
    KnowledgeEdge(source_id="N01", target_id="N02", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N01", target_id="N03", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N01", target_id="N06", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N01", target_id="N15", dependency_type="strict", weight=1.0),
    # 线性表 → 栈/队列
    KnowledgeEdge(source_id="N02", target_id="N04", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N02", target_id="N05", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N03", target_id="N04", dependency_type="recommended", weight=0.5),
    KnowledgeEdge(source_id="N03", target_id="N05", dependency_type="recommended", weight=0.5),
    # 树进阶
    KnowledgeEdge(source_id="N06", target_id="N07", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N07", target_id="N08", dependency_type="strict", weight=1.2),
    # 散列表
    KnowledgeEdge(source_id="N03", target_id="N09", dependency_type="recommended", weight=0.7),
    KnowledgeEdge(source_id="N06", target_id="N09", dependency_type="recommended", weight=0.5),
    # 图论链
    KnowledgeEdge(source_id="N06", target_id="N10", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N10", target_id="N11", dependency_type="strict", weight=1.0),
    KnowledgeEdge(source_id="N11", target_id="N12", dependency_type="strict", weight=1.2),
    KnowledgeEdge(source_id="N11", target_id="N13", dependency_type="strict", weight=1.2),
    KnowledgeEdge(source_id="N13", target_id="N14", dependency_type="strict", weight=1.0),
    # 排序链
    KnowledgeEdge(source_id="N15", target_id="N16", dependency_type="strict", weight=1.2),
    KnowledgeEdge(source_id="N16", target_id="N17", dependency_type="recommended", weight=0.8),
    # 高级算法
    KnowledgeEdge(source_id="N13", target_id="N18", dependency_type="strict", weight=1.5),
    KnowledgeEdge(source_id="N14", target_id="N18", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N16", target_id="N19", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N18", target_id="N19", dependency_type="recommended", weight=1.0),
    # 综合
    KnowledgeEdge(source_id="N08", target_id="N20", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N09", target_id="N20", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N12", target_id="N20", dependency_type="recommended", weight=1.0),
    KnowledgeEdge(source_id="N19", target_id="N20", dependency_type="strict", weight=1.5),
]

# ─── 知识基础 → 节点掌握度映射 ─────────────────────────
_KNOWLEDGE_TO_NODES = {
    "python_basics": {"N02": 0.75, "N03": 0.70, "N04": 0.65, "N05": 0.65},
    "data_structures": {"N01": 0.70, "N02": 0.80, "N03": 0.75, "N06": 0.60},
    "linear_algebra": {"N18": 0.50},
    "ml_basics": {"N18": 0.45},
    "deep_learning": {"N18": 0.40, "N19": 0.35},
    "databases": {"N09": 0.55, "N17": 0.50},
    "dev_tools": {},
    "none": {},
}

# ─── 节点标题映射（用于 ES 知识库检索）─────────────────────
_NODE_TITLE_MAP = {
    "N01": "算法复杂度分析", "N02": "线性表与顺序存储", "N03": "链表与链式存储",
    "N04": "栈及其应用", "N05": "队列及其应用", "N06": "树与二叉树基础",
    "N07": "二叉搜索树", "N08": "AVL平衡树", "N09": "散列表与哈希",
    "N10": "图的基本概念与存储", "N11": "图的遍历DFS BFS", "N12": "最小生成树",
    "N13": "最短路径算法", "N14": "拓扑排序与关键路径", "N15": "排序算法基础",
    "N16": "高级排序算法", "N17": "查找与索引技术", "N18": "动态规划入门",
    "N19": "贪心算法与回溯", "N20": "数据结构综合应用",
}

def _apply_kb_premastery(kb_item: str, agent_state: AgentState) -> None:
    node_map = _KNOWLEDGE_TO_NODES.get(kb_item, {})
    for nid, mastery in node_map.items():
        if nid not in agent_state.dynamic_profile.knowledge_mastery:
            agent_state.dynamic_profile.knowledge_mastery[nid] = mastery

# ─── 全局会话存储 ───────────────────────────────────────────
sessions: Dict[str, Dict[str, Any]] = {}

# ─── ES 知识库客户端（全局单例）─────────────────────────────
_es_kb_client = None
_es_embedder = None

def _get_es_kb():
    """延迟初始化 ES 知识库客户端"""
    global _es_kb_client, _es_embedder
    if _es_kb_client is None:
        from src.vector.elasticsearch_knowledge_base import (
            ElasticsearchKnowledgeBaseClient,
            ElasticsearchKnowledgeBaseConfig,
            SentenceTransformerEmbedder,
        )
        _es_embedder = SentenceTransformerEmbedder(model_name="BAAI/bge-small-zh-v1.5")
        config = ElasticsearchKnowledgeBaseConfig(
            hosts=["http://127.0.0.1:9200"],
            index_name="eduagent_data_structure_kb",
            vector_dims=_es_embedder.dims,
            request_timeout=30,
            verify_certs=False,
        )
        _es_kb_client = ElasticsearchKnowledgeBaseClient(config)
        _es_kb_client.set_embedding_function(_es_embedder.embed, _es_embedder.embed_batch)
        try:
            _es_kb_client.connect()
            print(f"[ES] Knowledge base connected, dims={_es_embedder.dims}")
        except Exception as e:
            print(f"[ES] Connection failed: {e}, Tutor will use fallback mode")
            _es_kb_client = None
    return _es_kb_client


def _search_knowledge_base(query: str, top_k: int = 5) -> List[str]:
    """从 ES 知识库检索相关内容"""
    client = _get_es_kb()
    if client is None:
        return []
    try:
        result = client.hybrid_search(query, top_k=top_k)
        hits = result.get("hits", {}).get("hits", [])
        return [h["_source"]["content"] for h in hits]
    except Exception:
        return []


def get_or_create_session(user_id: str) -> Dict[str, Any]:
    if user_id not in sessions:
        # 初始化 AgentState
        agent_state = AgentState(
            user_id=user_id,
            course_id="data_structures_101",
            current_node_id=None,
            target_node_id="N20",
            static_profile=StaticProfile(
                cognitive_style_distribution=CognitiveStyleDistribution(),
                motivation="academic_exam",
                time_budget_hours_per_week=15.0,
                knowledge_base=[],
            ),
            dynamic_profile=DynamicProfile(),
            active_path=[],
            generated_resources={},
            latest_behavior=None,
            c_epoch=0,
            re_plan_triggered=False,
            pedagogical_strategy="STANDARD_PATH",
            recommended_resource_style=None,
            tutor_response=None,
            errors=[],
            internal_state={},
            iteration=0,
        )

        # 初始化各 Agent Node
        llm = _get_llm()
        evaluator = EvaluatorNode()
        profiler = ProfilerNode(seed=42)
        planner = PlannerNode()
        tutor = TutorAgentNode(llm_generator=llm)  # LLM 注入 → AI 讲解 + Mermaid 图解
        validator = ValidatorNode(
            nli_fn=llm.compute_nli_entailment if llm else None  # LLM 注入 → 真实 NLI 校验
        )
        assessment = AssessmentReporterNode(alpha=0.2)

        # ContentMesh: LLM 生成核心卡片，其余用 ES 知识库（缓存查询结果）
        _es_cache: Dict[str, str] = {}
        if llm:
            def _hybrid_generate(node_id: str, card_type: str, difficulty: float) -> str:
                if card_type == "concept_map":
                    try:
                        return llm.generate_content(node_id, card_type, difficulty)
                    except Exception:
                        pass
                # ES 知识库回退（同节点只搜一次）
                title = _NODE_TITLE_MAP.get(node_id, node_id)
                cache_key = node_id
                if cache_key not in _es_cache:
                    chunks = _search_knowledge_base(title, top_k=2)
                    if not chunks:
                        chunks = _search_knowledge_base(node_id, top_k=2)
                    _es_cache[cache_key] = "\n\n".join(chunks) if chunks else f"知识点 {title} 的相关内容正在准备中。"
                context = _es_cache[cache_key]
                templates = {
                    "concept_map": f"## {title}\n\n### 概念解析\n\n{context}\n\n---\n*难度: {difficulty:.0%}*",
                    "code_snippet": f"## {title} · 代码示例\n\n```python\n# 相关实现代码\n{context[:800]}\n```\n\n---\n*难度: {difficulty:.0%}*",
                    "interactive_exercise": f"## 互动练习 · {title}\n\n阅读以下内容并回答问题：\n\n{context[:600]}\n\n---\n*难度: {difficulty:.0%}*",
                    "video_summary": f"## 视频摘要 · {title}\n\n{context[:500]}\n\n---\n*难度: {difficulty:.0%}*",
                    "diagnostic_quiz": f"## 诊断测验 · {title}\n\n根据以下知识点完成自测：\n\n{context[:600]}\n\n---\n*难度: {difficulty:.0%}*",
                }
                return templates.get(card_type, context)
            mesh = ContentMeshNode(generate_fn=_hybrid_generate)
            def _kb_generate(node_id: str, card_type: str, difficulty: float) -> str:
                chunks = _search_knowledge_base(node_id, top_k=2)
                if not chunks:
                    chunks = _search_knowledge_base(_NODE_TITLE_MAP.get(node_id, node_id), top_k=2)
                context = "\n\n".join(chunks) if chunks else f"知识点 {node_id} 的相关内容正在准备中。"
                templates = {
                    "concept_map": f"## {_NODE_TITLE_MAP.get(node_id, node_id)}\n\n### 概念解析\n\n{context}\n\n---\n*难度: {difficulty:.0%}*",
                    "code_snippet": f"## {_NODE_TITLE_MAP.get(node_id, node_id)} · 代码示例\n\n```python\n# 相关实现\n{context[:800]}\n```\n\n---\n*难度: {difficulty:.0%}*",
                    "interactive_exercise": f"## 互动练习 · {_NODE_TITLE_MAP.get(node_id, node_id)}\n\n阅读以下内容并回答问题：\n\n{context[:600]}\n\n---\n*难度: {difficulty:.0%}*",
                    "video_summary": f"## 视频摘要 · {_NODE_TITLE_MAP.get(node_id, node_id)}\n\n{context[:500]}\n\n---\n*难度: {difficulty:.0%}*",
                    "diagnostic_quiz": f"## 诊断测验 · {_NODE_TITLE_MAP.get(node_id, node_id)}\n\n根据以下知识点完成自测：\n\n{context[:600]}\n\n---\n*难度: {difficulty:.0%}*",
                }
                return templates.get(card_type, context)
            mesh = ContentMeshNode(generate_fn=_kb_generate)

        # 初始化冷启动引擎
        cold_engine = ColdStartEngine()
        cold_state = cold_engine.initialize(user_id)

        # 初始化路径规划器（使用模拟知识图谱）
        path_planner = PathPlanner(MOCK_KNOWLEDGE_NODES, MOCK_KNOWLEDGE_EDGES)

        sessions[user_id] = {
            "agent_state": agent_state,
            "evaluator": evaluator,
            "profiler": profiler,
            "planner": planner,
            "tutor": tutor,
            "mesh": mesh,
            "validator": validator,
            "assessment": assessment,
            "cold_engine": cold_engine,
            "cold_state": cold_state,
            "path_planner": path_planner,
            "pipeline_log": [],  # 记录每一步的执行日志
        }
    return sessions[user_id]


# ─── API 端点 ────────────────────────────────────────────────

async def api_reset(request: Request) -> JSONResponse:
    """重置会话"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    sessions.pop(user_id, None)
    get_or_create_session(user_id)
    return JSONResponse({"status": "ok", "user_id": user_id})


async def api_get_state(request: Request) -> JSONResponse:
    """获取当前 AgentState"""
    user_id = request.query_params.get("user_id", "demo_user")
    session = get_or_create_session(user_id)
    state: AgentState = session["agent_state"]
    return JSONResponse({
        "user_id": state.user_id,
        "course_id": state.course_id,
        "current_node_id": state.current_node_id,
        "target_node_id": state.target_node_id,
        "iteration": state.iteration,
        "c_epoch": state.c_epoch,
        "re_plan_triggered": state.re_plan_triggered,
        "pedagogical_strategy": state.pedagogical_strategy,
        "recommended_resource_style": state.recommended_resource_style,
        "active_path": state.active_path,
        "static_profile": {
            "motivation": state.static_profile.motivation,
            "time_budget_hours_per_week": state.static_profile.time_budget_hours_per_week,
            "knowledge_base": state.static_profile.knowledge_base,
            "cognitive_style_distribution": state.static_profile.cognitive_style_distribution.to_dict(),
        },
        "dynamic_profile": {
            "knowledge_mastery": state.dynamic_profile.knowledge_mastery,
            "continuous_fail_counter": state.dynamic_profile.continuous_fail_counter,
            "capability_radar": state.dynamic_profile.capability_radar,
            "diagnostic_report_md": state.dynamic_profile.diagnostic_report_md,
            "error_type_distribution": {
                "logic_flaw": state.dynamic_profile.error_type_distribution.logic_flaw,
                "syntax_error": state.dynamic_profile.error_type_distribution.syntax_error,
                "boundary_miss": state.dynamic_profile.error_type_distribution.boundary_miss,
            },
        },
        "generated_resources": {
            k: [r.model_dump() for r in v]
            for k, v in state.generated_resources.items()
        },
        "tutor_response": state.tutor_response,
        "errors": state.errors[-10:],
        "pipeline_log": session["pipeline_log"][-20:],
    })


async def api_cold_start_probe(request: Request) -> JSONResponse:
    """获取冷启动探针"""
    user_id = request.query_params.get("user_id", "demo_user")
    session = get_or_create_session(user_id)
    cold_state: ColdStartState = session["cold_state"]
    engine: ColdStartEngine = session["cold_engine"]

    if cold_state.current_phase in (ColdStartPhase.COMPLETE, ColdStartPhase.FUSION_FALLBACK):
        return JSONResponse({"phase": "complete", "probe": None})

    probe = engine.get_next_probe(cold_state)
    if probe is None:
        return JSONResponse({"phase": cold_state.current_phase.value, "probe": None})

    return JSONResponse({
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
    })


async def api_cold_start_answer(request: Request) -> JSONResponse:
    """处理冷启动回答"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    answer = body.get("answer")
    session = get_or_create_session(user_id)

    cold_state: ColdStartState = session["cold_state"]
    engine: ColdStartEngine = session["cold_engine"]
    agent_state: AgentState = session["agent_state"]

    # 推进状态机（epoch 不在 process_response 中递增，仅在轮次边界递增）
    if "_cold_start_answers" not in agent_state.internal_state:
        agent_state.internal_state["_cold_start_answers"] = []
    agent_state.internal_state["_cold_start_answers"].append(answer)
    cold_state = engine.process_response(cold_state, answer)
    if cold_state.should_fuse():
        fused = engine.execute_fusion(cold_state)
        agent_state = engine.apply_to_agent_state(cold_state, agent_state)
        agent_state.c_epoch = cold_state.epoch_counter
        session["cold_state"] = cold_state
        session["agent_state"] = agent_state
        session["pipeline_log"].append({
            "agent": "ColdStart",
            "event": "fusion_triggered",
            "fused_dimensions": list(fused.keys()),
        })
        return JSONResponse({
            "phase": "complete",
            "fusion_triggered": True,
            "fused_dimensions": list(fused.keys()),
        })

    # 检查是否完成
    if cold_state.all_dimensions_collected():
        agent_state = engine.apply_to_agent_state(cold_state, agent_state)
        agent_state.c_epoch = cold_state.epoch_counter
        session["cold_state"] = cold_state
        session["agent_state"] = agent_state
        return JSONResponse({
            "phase": "complete",
            "collected": cold_state.collected_dimensions,
        })

    # 获取下一个探针
    next_probe = engine.get_next_probe(cold_state)
    session["cold_state"] = cold_state
    session["agent_state"] = agent_state

    result = {
        "phase": cold_state.current_phase.value,
        "epoch": cold_state.epoch_counter,
        "collected": cold_state.collected_dimensions,
    }
    if next_probe:
        result["next_probe"] = {
            "question": next_probe.question,
            "options": next_probe.options,
            "is_multi_select": next_probe.is_multi_select,
            "dimension": next_probe.dimension,
        }
    else:
        result["next_probe"] = None

    return JSONResponse(result)


async def api_init_path(request: Request) -> JSONResponse:
    """冷启动完成后，初始化学习路径"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    session = get_or_create_session(user_id)
    agent_state: AgentState = session["agent_state"]
    path_planner: PathPlanner = session["path_planner"]

    # 根据冷启动答案，标记已掌握节点
    _cs_answers = agent_state.internal_state.get("_cold_start_answers", [])
    for answer in _cs_answers:
        if isinstance(answer, list):
            for item in answer:
                _apply_kb_premastery(item, agent_state)
        elif isinstance(answer, str):
            _apply_kb_premastery(answer, agent_state)
    # 如果没有记录，回退到 knowledge_base
    if not agent_state.dynamic_profile.knowledge_mastery:
        for kb_item in agent_state.static_profile.knowledge_base:
            _apply_kb_premastery(kb_item, agent_state)

    if not agent_state.active_path:
        # 完整课程路径 = 全部知识点按拓扑序排列
        topo = path_planner.compute_topological_order()
        agent_state.active_path = topo
        if topo:
            agent_state.current_node_id = topo[0]

        session["pipeline_log"].append({
            "agent": "Planner",
            "event": "initial_path",
            "path": agent_state.active_path,
        })

    return JSONResponse({
        "active_path": agent_state.active_path,
        "current_node_id": agent_state.current_node_id,
        "target_node_id": agent_state.target_node_id,
    })


async def api_run_pipeline_step(request: Request) -> JSONResponse:
    """执行一轮完整的 Agent 管线（模拟一次学习交互）"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    # 模拟的行为数据
    correctness = body.get("correctness", 0.75)
    time_spent_ratio = body.get("time_spent_ratio", 1.0)
    code_pass_rate = body.get("code_pass_rate", 0.70)
    help_count = body.get("help_count", 0)
    tutor_query = body.get("tutor_query", None)
    # 可选：指定要生成资源的知识点（用于点击路径节点跳转）
    target_node = body.get("current_node_id", None)

    session = get_or_create_session(user_id)
    agent_state: AgentState = session["agent_state"]
    if target_node:
        agent_state.current_node_id = target_node
    evaluator: EvaluatorNode = session["evaluator"]
    profiler: ProfilerNode = session["profiler"]
    planner: PlannerNode = session["planner"]
    tutor: TutorAgentNode = session["tutor"]
    mesh: ContentMeshNode = session["mesh"]
    validator: ValidatorNode = session["validator"]
    assessment: AssessmentReporterNode = session["assessment"]
    path_planner: PathPlanner = session["path_planner"]

    step_log = {"step": agent_state.iteration + 1}
    logs = []

    # ── Step 1: Evaluator ──
    current_node = agent_state.current_node_id or (agent_state.active_path[0] if agent_state.active_path else "N01")

    raw_behavior = BehaviorVector(
        answer_correctness=correctness,
        code_pass_rate=code_pass_rate,
        time_spent_ratio=time_spent_ratio,
        help_request_count=help_count,
        node_id=current_node,
    )

    # 设置 latest_behavior 以便 tutor_query 能被检测到
    agent_state.latest_behavior = LatestBehavior(
        node_id=current_node,
        correctness=correctness,
        time_spent_ratio=time_spent_ratio,
        error_types=[],
        resource_feedback={},
        help_request_count=help_count,
        tutor_query=tutor_query,
        accuracy_rate=correctness,
        code_pass_rate=code_pass_rate,
        duration_ratio=time_spent_ratio,
    )

    eval_input = EvaluatorInput(agent_state=agent_state, raw_behavior=raw_behavior)
    eval_output = evaluator(eval_input)
    agent_state = eval_output.agent_state
    logs.append({
        "agent": "Evaluator",
        "effective_correctness": eval_output.cleaned_behavior.effective_correctness,
        "anomaly_type": eval_output.cleaned_behavior.anomaly.anomaly_type.value,
        "anomaly_detected": eval_output.anomaly_detected,
        "mastery_delta": round(eval_output.mastery_delta, 4),
        "pid_error": round(eval_output.pid_error, 4),
        "replan_decision": eval_output.replan_decision.value,
        "updated_mastery": round(eval_output.updated_mastery, 4),
    })

    # ── Step 2: Profiler ──
    prof_input = ProfilerInput(
        agent_state=agent_state,
        evaluator_mastery_delta=eval_output.mastery_delta,
        evaluator_pid_error=eval_output.pid_error,
        resource_style_delivered=agent_state.recommended_resource_style or "visual",
        node_id=current_node,
    )
    prof_output = profiler(prof_input)
    agent_state = prof_output.agent_state
    logs.append({
        "agent": "Profiler",
        "selected_style": prof_output.style_result.selected_style,
        "sample_values": prof_output.style_result.sample_values,
        "intervention_triggered": prof_output.intervention_active,
        "forgetting_decay": (
            round(prof_output.forgetting_result.decay_factor, 4)
            if prof_output.forgetting_result else None
        ),
    })

    # ── Step 3: Planner ──
    if not agent_state.active_path or agent_state.re_plan_triggered:
        # 保持完整课程路径，不因重规划而缩短
        topo = path_planner.compute_topological_order()
        agent_state.active_path = topo
        agent_state.re_plan_triggered = False
        logs.append({
            "agent": "Planner",
            "replan": True,
            "new_path": agent_state.active_path,
        })
    else:
        logs.append({
            "agent": "Planner",
            "replan": False,
            "active_path": agent_state.active_path,
        })

    # ── Step 4: Tutor (如果有 tutor_query) ──
    if tutor_query:
        tut_input = TutorInput(agent_state=agent_state)
        tut_output = tutor(tut_input)
        agent_state = tut_output.agent_state
        logs.append({
            "agent": "Tutor",
            "query": tutor_query,
            "has_mermaid": bool(agent_state.tutor_response.get("mermaid_src", "") if agent_state.tutor_response else False),
        })

    # ── Step 5: Content Mesh ──
    mesh_input = MeshInput(agent_state=agent_state)
    mesh_output = mesh(mesh_input)
    agent_state = mesh_output.agent_state
    logs.append({
        "agent": "ContentMesh",
        "generated_cards": len(mesh_output.generated_cards),
        "card_types": [c.card_type for c in mesh_output.generated_cards],
    })

    # 补充缺失的卡片类型（确保每个节点有完整的5种卡片）
    all_card_types = ["concept_map", "code_snippet", "interactive_exercise", "video_summary", "diagnostic_quiz"]
    for nid in agent_state.active_path:
        if nid not in agent_state.generated_resources:
            agent_state.generated_resources[nid] = []
        existing = {c.card_type for c in agent_state.generated_resources[nid]}
        for missing_type in all_card_types:
            if missing_type not in existing:
                difficulty = max(0.1, 1.0 - agent_state.dynamic_profile.knowledge_mastery.get(nid, 0.5))
                content = mesh._default_generate(nid, missing_type, difficulty)
                # Try getting real content from ES
                try:
                    title = _NODE_TITLE_MAP.get(nid, nid)
                    chunks = _search_knowledge_base(title, top_k=1)
                    if not chunks:
                        chunks = _search_knowledge_base(nid, top_k=1)
                    if chunks:
                        ctx = chunks[0]
                        if missing_type == "concept_map":
                            content = f"## {title}\n\n### 概念解析\n\n{ctx}\n\n---\n*难度: {difficulty:.0%}*"
                        elif missing_type == "code_snippet":
                            content = f"## {title} · 代码示例\n\n```python\n{ctx[:800]}\n```\n\n---\n*难度: {difficulty:.0%}*"
                        elif missing_type == "interactive_exercise":
                            content = f"## 互动练习 · {title}\n\n阅读以下内容并回答问题：\n\n{ctx[:600]}\n\n---\n*难度: {difficulty:.0%}*"
                        elif missing_type == "video_summary":
                            content = f"## 视频摘要 · {title}\n\n{ctx[:500]}\n\n---\n*难度: {difficulty:.0%}*"
                        elif missing_type == "diagnostic_quiz":
                            content = f"## 诊断测验 · {title}\n\n根据以下知识点完成自测：\n\n{ctx[:600]}\n\n---\n*难度: {difficulty:.0%}*"
                except Exception:
                    pass
                card = ResourceCard(
                    resource_id=f"{nid}_{missing_type}_supp",
                    node_id=nid,
                    card_type=missing_type,
                    content=content,
                    difficulty=difficulty,
                    cognitive_style=agent_state.recommended_resource_style or "textual",
                )
                agent_state.generated_resources[nid].append(card)

    # ── Step 6: Validator ──
    cards_to_validate = []
    for node_id, cards in agent_state.generated_resources.items():
        cards_to_validate.extend(cards)
    if cards_to_validate:
        val_input = ValidatorInput(
            agent_state=agent_state,
            cards_to_validate=cards_to_validate[-5:],  # 取最近5张
            ground_truth_context="数据结构是计算机存储、组织数据的方式。",
            enable_pole2=False,
        )
        val_output = validator(val_input)
        agent_state = val_output.agent_state
        logs.append({
            "agent": "Validator",
            "valid_cards": len(val_output.valid_cards),
            "rejected_cards": len(val_output.rejected_cards),
            "refined_cards": len(val_output.refined_cards),
            "overall_pass_rate": round(val_output.overall_pass_rate, 2),
        })
    else:
        logs.append({"agent": "Validator", "status": "no_cards_to_validate"})

    # ── Step 7: Assessment ──
    assess_input = AssessmentInput(agent_state=agent_state)
    assess_output = assessment(assess_input)
    agent_state = assess_output.agent_state
    logs.append({
        "agent": "Assessment",
        "capability_radar": agent_state.dynamic_profile.capability_radar,
        "pedagogical_strategy": agent_state.pedagogical_strategy,
        "a_mix": round(sum(agent_state.dynamic_profile.capability_radar) / 5, 4),
    })

    # 更新当前节点为路径中的下一个（除非是指定节点跳转）
    if not target_node and agent_state.active_path:
        idx = agent_state.active_path.index(current_node) if current_node in agent_state.active_path else -1
        if idx >= 0 and idx + 1 < len(agent_state.active_path):
            agent_state.current_node_id = agent_state.active_path[idx + 1]

    # 保存
    session["agent_state"] = agent_state
    session["pipeline_log"].extend(logs)

    return JSONResponse({
        "iteration": agent_state.iteration,
        "current_node_id": agent_state.current_node_id,
        "active_path": agent_state.active_path,
        "pedagogical_strategy": agent_state.pedagogical_strategy,
        "capability_radar": agent_state.dynamic_profile.capability_radar,
        "diagnostic_report": agent_state.dynamic_profile.diagnostic_report_md,
        "knowledge_mastery": {
            k: round(v, 4) for k, v in agent_state.dynamic_profile.knowledge_mastery.items()
        },
        "generated_cards_count": sum(len(v) for v in agent_state.generated_resources.values()),
        "tutor_response": agent_state.tutor_response,
        "re_plan_triggered": agent_state.re_plan_triggered,
        "errors": agent_state.errors[-5:],
        "step_logs": logs,
        "all_logs": session["pipeline_log"],
    })


async def api_ask_tutor(request: Request) -> JSONResponse:
    """单独调用 Tutor Agent（LLM + ES 知识库）"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    query = body.get("query", "")
    session = get_or_create_session(user_id)
    agent_state: AgentState = session["agent_state"]
    tutor: TutorAgentNode = session["tutor"]

    # 从 ES 知识库检索参考上下文
    ref_chunks = _search_knowledge_base(query, top_k=5)

    agent_state.latest_behavior = LatestBehavior(
        node_id=agent_state.current_node_id,
        correctness=0.75,
        time_spent_ratio=1.0,
        error_types=[],
        resource_feedback={},
        help_request_count=1,
        tutor_query=query,
    )

    tut_input = TutorInput(agent_state=agent_state)
    tut_output = tutor(tut_input)
    agent_state = tut_output.agent_state

    # 有 LLM 时，Tutor 会自动生成 AI 讲解；无 LLM 时用 ES 原文兜底
    tr = agent_state.tutor_response or {}
    if ref_chunks and ("无法从知识库中检索到" in tr.get("text_explanation", "")
                       or "离线模式" in tr.get("text_explanation", "")):
        context = "\n\n---\n\n".join(ref_chunks[:3])
        tr["text_explanation"] = (
            f"## 关于「{query}」的相关知识点（来自知识库）\n\n"
            f"{context}\n\n"
            f"> 提示: LLM 暂不可用，以上为知识库原文。"
        )
        agent_state.tutor_response = tr

    session["agent_state"] = agent_state
    return JSONResponse({
        "tutor_response": agent_state.tutor_response,
        "reference_count": len(ref_chunks),
    })


async def api_knowledge_graph(request: Request) -> JSONResponse:
    """获取知识图谱数据（用于前端可视化）"""
    return JSONResponse({
        "nodes": [
            {
                "id": n.node_id,
                "title": n.title,
                "difficulty": n.difficulty,
                "estimated_hours": n.estimated_hours,
                "category": n.category,
            }
            for n in MOCK_KNOWLEDGE_NODES
        ],
        "edges": [
            {
                "source": e.source_id,
                "target": e.target_id,
                "dependency_type": e.dependency_type,
                "weight": e.weight,
            }
            for e in MOCK_KNOWLEDGE_EDGES
        ],
    })


async def api_stream_pipeline(request: Request) -> EventSourceResponse:
    """SSE 流式执行完整管线"""
    user_id = request.query_params.get("user_id", "demo_user")
    correctness = float(request.query_params.get("correctness", "0.75"))
    time_spent_ratio = float(request.query_params.get("time_spent_ratio", "1.0"))
    code_pass_rate = float(request.query_params.get("code_pass_rate", "0.70"))
    tutor_query = request.query_params.get("tutor_query", "")

    async def event_generator():
        session = get_or_create_session(user_id)
        agent_state = session["agent_state"]
        evaluator = session["evaluator"]
        profiler = session["profiler"]
        path_planner = session["path_planner"]
        tutor = session["tutor"]
        mesh = session["mesh"]
        validator = session["validator"]
        assessment = session["assessment"]

        current_node = agent_state.current_node_id or (agent_state.active_path[0] if agent_state.active_path else "N01")

        steps = [
            ("Evaluator", "行为清洗 + PID 评估"),
            ("Profiler", "MAB 汤普森采样 + 遗忘曲线"),
            ("Planner", "DAG 拓扑路径规划"),
            ("ContentMesh", "WFQ 调度 + 资源卡片生成"),
            ("Validator", "双极防幻觉校验"),
            ("Assessment", "EMA 能力雷达 + 迟滞环决策"),
        ]

        for i, (agent_name, desc) in enumerate(steps):
            yield {"event": "step_start", "data": json.dumps({"agent": agent_name, "description": desc, "index": i, "total": len(steps)}, ensure_ascii=False)}
            await asyncio.sleep(0.3)

            # 执行对应 Agent
            if agent_name == "Evaluator":
                agent_state.latest_behavior = LatestBehavior(
                    node_id=current_node,
                    correctness=correctness,
                    time_spent_ratio=time_spent_ratio,
                    error_types=[],
                    resource_feedback={},
                    help_request_count=0,
                    tutor_query=tutor_query or None,
                    accuracy_rate=correctness,
                    code_pass_rate=code_pass_rate,
                    duration_ratio=time_spent_ratio,
                )
                raw = BehaviorVector(
                    answer_correctness=correctness,
                    code_pass_rate=code_pass_rate,
                    time_spent_ratio=time_spent_ratio,
                    help_request_count=0,
                    node_id=current_node,
                )
                out = evaluator(EvaluatorInput(agent_state=agent_state, raw_behavior=raw))
                agent_state = out.agent_state
                yield {"event": "agent_result", "data": json.dumps({
                    "agent": "Evaluator",
                    "anomaly_type": out.cleaned_behavior.anomaly.anomaly_type.value,
                    "effective_correctness": round(out.cleaned_behavior.effective_correctness, 4),
                    "mastery_delta": round(out.mastery_delta, 4),
                    "pid_error": round(out.pid_error, 4),
                    "replan_decision": out.replan_decision.value,
                }, ensure_ascii=False)}

            elif agent_name == "Profiler":
                out = profiler(ProfilerInput(
                    agent_state=agent_state,
                    evaluator_mastery_delta=0.05,
                    evaluator_pid_error=0.3,
                    resource_style_delivered=agent_state.recommended_resource_style or "visual",
                    node_id=current_node,
                ))
                agent_state = out.agent_state
                yield {"event": "agent_result", "data": json.dumps({
                    "agent": "Profiler",
                    "selected_style": out.style_result.selected_style,
                    "sample_values": out.style_result.sample_values,
                    "intervention_triggered": out.intervention_active,
                }, ensure_ascii=False)}

            elif agent_name == "Planner":
                if not agent_state.active_path or agent_state.re_plan_triggered:
                    topo = path_planner.compute_topological_order()
                    agent_state.active_path = topo
                    agent_state.re_plan_triggered = False
                    yield {"event": "agent_result", "data": json.dumps({
                        "agent": "Planner",
                        "replan": True,
                        "new_path": agent_state.active_path,
                    }, ensure_ascii=False)}
                else:
                    yield {"event": "agent_result", "data": json.dumps({
                        "agent": "Planner",
                        "replan": False,
                        "active_path": agent_state.active_path,
                    }, ensure_ascii=False)}

            elif agent_name == "ContentMesh":
                out = mesh(MeshInput(agent_state=agent_state))
                agent_state = out.agent_state
                yield {"event": "agent_result", "data": json.dumps({
                    "agent": "ContentMesh",
                    "generated_cards": len(out.generated_cards),
                    "card_types": [c.card_type for c in out.generated_cards],
                }, ensure_ascii=False)}

            elif agent_name == "Validator":
                cards = []
                for nid, clist in agent_state.generated_resources.items():
                    cards.extend(clist)
                if cards:
                    out_v = validator(ValidatorInput(
                        agent_state=agent_state,
                        cards_to_validate=cards[-5:],
                        ground_truth_context="数据结构是计算机存储、组织数据的方式。",
                        enable_pole2=False,
                    ))
                    agent_state = out_v.agent_state
                    yield {"event": "agent_result", "data": json.dumps({
                        "agent": "Validator",
                        "valid_cards": len(out_v.valid_cards),
                        "rejected_cards": len(out_v.rejected_cards),
                        "overall_pass_rate": round(out_v.overall_pass_rate, 2),
                    }, ensure_ascii=False)}
                else:
                    yield {"event": "agent_result", "data": json.dumps({"agent": "Validator", "status": "no_cards"}, ensure_ascii=False)}

            elif agent_name == "Assessment":
                out_a = assessment(AssessmentInput(agent_state=agent_state))
                agent_state = out_a.agent_state
                yield {"event": "agent_result", "data": json.dumps({
                    "agent": "Assessment",
                    "capability_radar": agent_state.dynamic_profile.capability_radar,
                    "pedagogical_strategy": agent_state.pedagogical_strategy,
                }, ensure_ascii=False)}

            yield {"event": "step_complete", "data": json.dumps({"agent": agent_name, "index": i}, ensure_ascii=False)}

        # 推进 current_node
        if agent_state.active_path:
            idx = agent_state.active_path.index(current_node) if current_node in agent_state.active_path else -1
            if idx >= 0 and idx + 1 < len(agent_state.active_path):
                agent_state.current_node_id = agent_state.active_path[idx + 1]

        session["agent_state"] = agent_state
        yield {"event": "done", "data": json.dumps({
            "iteration": agent_state.iteration,
            "capability_radar": agent_state.dynamic_profile.capability_radar,
            "diagnostic_report": agent_state.dynamic_profile.diagnostic_report_md,
            "knowledge_mastery": {k: round(v, 4) for k, v in agent_state.dynamic_profile.knowledge_mastery.items()},
        }, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


# ─── 应用 ────────────────────────────────────────────────────

static_dir = Path(__file__).resolve().parent

app = Starlette(
    debug=True,
    routes=[
        Route("/api/reset", api_reset, methods=["POST"]),
        Route("/api/state", api_get_state, methods=["GET"]),
        Route("/api/cold-start/probe", api_cold_start_probe, methods=["GET"]),
        Route("/api/cold-start/answer", api_cold_start_answer, methods=["POST"]),
        Route("/api/init-path", api_init_path, methods=["POST"]),
        Route("/api/pipeline/step", api_run_pipeline_step, methods=["POST"]),
        Route("/api/pipeline/stream", api_stream_pipeline, methods=["GET"]),
        Route("/api/tutor/ask", api_ask_tutor, methods=["POST"]),
        Route("/api/knowledge-graph", api_knowledge_graph, methods=["GET"]),
        Mount("/", app=StaticFiles(directory=str(static_dir), html=True)),
    ],
)


if __name__ == "__main__":
    print("=" * 60)
    print("  EduAgent 前后端对接服务器")
    print("  访问: http://localhost:8800")
    print("=" * 60)
    # 启动时预加载 ES 知识库（模型加载 + 连接）
    print("[Init] Loading knowledge base...")
    _get_es_kb()
    print("[Init] Ready.")
    uvicorn.run(app, host="0.0.0.0", port=8800, log_level="info")
