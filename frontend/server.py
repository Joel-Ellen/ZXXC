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

# 将项目根目录加入 sys.path，确保 src 包可被导入
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import JSONResponse, Response

# 新增 API 路由 (合并自 backend/)
from src.routes.new_api_routes import new_routes
from starlette.requests import Request

# --- Course System ---
from src.courses import CourseStore
from sse_starlette.sse import EventSourceResponse


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
import threading
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
            from src.llm import LLMClientV2
            _llm_client = LLMClientV2(provider="dashscope")
            print(f"[LLM] LLMClientV2 connected (provider={_llm_client.provider})")
        else:
            print("[LLM] No API key found, using fallback mode")
    return _llm_client


# --- 数据库层 (全局单例) ------------------------------------------
try:
    from src.database import (
        db as _db, UserRepo, EnrollmentRepo, StateRepo,
        get_redis, blacklist_token, is_blacklisted, store_refresh_token,
        mark_rotated, is_rotated, revoke_all_user_sessions,
    )
    _db_available = True
    print("[DB] PostgreSQL backend loaded")
except Exception as e:
    print(f"[DB] PostgreSQL not available ({e}), using JSON fallback")
    _db_available = False
    _db = None
    UserRepo = None
    EnrollmentRepo = None
    StateRepo = None
    get_redis = lambda: None
    blacklist_token = lambda *a, **kw: None
    is_blacklisted = lambda *a, **kw: False
    store_refresh_token = lambda *a, **kw: None
    mark_rotated = lambda *a, **kw: None
    is_rotated = lambda *a, **kw: False
    revoke_all_user_sessions = lambda *a, **kw: None

_user_repo = None
_enrollment_repo = None
_state_repo = None
_auth_captcha = None

def _get_user_repo():
    global _user_repo
    if _user_repo is None and _db_available:
        _user_repo = UserRepo()
    return _user_repo

def _get_enrollment_repo():
    global _enrollment_repo
    if _enrollment_repo is None and _db_available:
        _enrollment_repo = EnrollmentRepo()
    return _enrollment_repo

def _get_state_repo():
    global _state_repo
    if _state_repo is None and _db_available:
        _state_repo = StateRepo()
    return _state_repo

def _get_auth():
    global _auth_captcha, _user_repo
    if _auth_captcha is None:
        from src.auth.captcha import CaptchaGenerator
        from src.auth.models import PresetAccounts, UserStore

        if _db_available:
            _user_repo = _get_user_repo()
            created = PresetAccounts.ensure_presets_db(_user_repo)
        else:
            _user_repo = UserStore()
            created = PresetAccounts.ensure_presets(_user_repo)
        print(f"[Auth] {len(created)} preset accounts ready")
        for u in created:
            print(f"  - {u['user_id']} ({u['role']}): {u['email']}")
        _auth_captcha = CaptchaGenerator()
    return _user_repo, _auth_captcha


# --- 导入项目模块 -------------------------------------------------
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
    PathPlanner, PathPlanStrategy, PlanContext,
)
from src.graph import get_kg_manager
from src.infrastructure.pid_controller import PIDController, PIDConfig

_kg = get_kg_manager()


def _get_node_title(node_id: str) -> str:
    """鑾峰彇鑺傜偣鏍囬銆?"""
    return _kg.get_node_title(node_id)


def _apply_kb_premastery(kb_item: str, agent_state: AgentState, course_id: str = "data_structures") -> None:
    node_map = _kg.get_knowledge_mastery_map([kb_item], course_id)
    for nid, mastery in node_map.items():
        if nid not in agent_state.dynamic_profile.knowledge_mastery:
            agent_state.dynamic_profile.knowledge_mastery[nid] = mastery

# ─── 全局会话存储 (user_id → course_id → session) ──────────
sessions: Dict[str, Dict[str, Dict[str, Any]]] = {}

# ─── 课程存储 (全局单例) ────────────────────────────────────
_course_store = None

def _get_course_store() -> CourseStore:
    global _course_store
    if _course_store is None:
        _course_store = CourseStore()
        print(f"[Courses] {_course_store.count()} courses loaded")
    return _course_store

# ─── 用户选课 (数据库持久化) ─────────────────────────────────
def _get_user_enrollments(user_id: str) -> Dict[str, Any]:
    repo = _get_enrollment_repo()
    if repo is None:
        return {}
    return repo.get_user_enrollments(user_id)

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
        es_hosts = os.getenv("ES_HOSTS", "http://127.0.0.1:9200")
        es_user = os.getenv("ES_USER", "elastic")
        es_password = os.getenv("ES_PASSWORD", "")
        config = ElasticsearchKnowledgeBaseConfig(
            hosts=[es_hosts],
            index_name="eduagent_data_structure_kb",
            vector_dims=_es_embedder.dims,
            request_timeout=30,
            verify_certs=False,
            basic_auth_user=es_user,
            basic_auth_password=es_password,
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


_es_kb_init_attempted = False
_es_kb_init_error: Optional[str] = None


def _safe_get_es_kb():
    """Initialize the knowledge base once and gracefully degrade on failure."""
    global _es_kb_client, _es_embedder, _es_kb_init_attempted, _es_kb_init_error
    if _es_kb_client is not None:
        return _es_kb_client
    if _es_kb_init_attempted:
        return None

    _es_kb_init_attempted = True
    try:
        client = _get_es_kb()
        _es_kb_init_error = None
        return client
    except Exception as exc:
        _es_kb_client = None
        _es_embedder = None
        _es_kb_init_error = f"{type(exc).__name__}: {exc}"
        print(
            "[ES] Knowledge base unavailable, fallback mode enabled: "
            f"{_es_kb_init_error}"
        )
        print(traceback.format_exc(limit=3).rstrip())
        return None


def _search_knowledge_base(query: str, top_k: int = 5) -> List[str]:
    """从 ES 知识库检索相关内容"""
    client = _safe_get_es_kb()
    if client is None:
        return []
    try:
        result = client.hybrid_search(query, top_k=top_k)
        hits = result.get("hits", {}).get("hits", [])
        return [h["_source"]["content"] for h in hits]
    except Exception:
        return []


def _persist_state(user_id: str, course_id: str, agent_state, cold_state=None) -> None:
    """持久化 AgentState 到 PostgreSQL + Neo4j（三层架构）。"""
    # 1. PostgreSQL: 完整状态 JSON blob
    try:
        state_json = agent_state.model_dump_json()
        cold_json = cold_state.model_dump_json() if cold_state else None
        _get_state_repo().save_state(user_id, course_id, state_json, cold_json)
    except Exception as e:
        print(f"[DB] State save PG failed: {e}")

    # 2. Neo4j: 知识点掌握度关系 (User)-[:MASTERED]->(KnowledgePoint)
    _persist_mastery_to_neo4j(user_id, course_id, agent_state)


def _persist_mastery_to_neo4j(user_id: str, course_id: str, agent_state) -> None:
    """将掌握度数据写入 Neo4j 图数据库。

    为每个已掌握的知识点创建或更新：
        (:User {user_id}) - [:MASTERED {mastery, updated_at}] -> (:KnowledgePoint)
    """
    try:
        mastery = agent_state.dynamic_profile.knowledge_mastery
        if not mastery:
            return
        nc = _kg.get_neo4j_client()
        if nc is None:
            return  # Neo4j 不可用，静默跳过
        for node_id, score in mastery.items():
            nc.set_user_mastery(user_id, node_id, round(score, 4))
    except Exception:
        # Neo4j 写入失败不影响主流程（回退到内存+PostgreSQL）
        pass


def get_or_create_session(user_id: str, course_id: str = "data_structures") -> Dict[str, Any]:
    """获取或创建用户在某课程下的会话。

    Args:
        user_id: 用户 ID。
        course_id: 课程 ID（默认 data_structures）。

    Returns:
        包含 agent_state / evaluator / ... 的会话字典。
    """
    # 确保用户层和课程层存在
    if user_id not in sessions:
        sessions[user_id] = {}
    if course_id not in sessions[user_id]:
        # 获取课程信息以设置 target_node
        store = _get_course_store()
        course = store.get_by_id(course_id)
        target_node = "N20" if course_id == "data_structures" else "N01"

        # 初始化 AgentState
        agent_state = AgentState(
            user_id=user_id,
            course_id=course_id,
            current_node_id=None,
            target_node_id=target_node,
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
        tutor = TutorAgentNode(llm_generator=llm)
        validator = ValidatorNode(
            nli_fn=llm.compute_nli_entailment if llm else None
        )
        assessment = AssessmentReporterNode(alpha=0.2)

        # ContentMesh
        _es_cache: Dict[str, str] = {}
        mesh = None
        if llm:
            def _hybrid_generate(node_id: str, card_type: str, difficulty: float) -> str:
                if card_type == "concept_map":
                    try:
                        return llm.generate_content(node_id, card_type, difficulty)
                    except Exception:
                        pass
                title = _get_node_title(node_id, node_id)
                if node_id not in _es_cache:
                    chunks = _search_knowledge_base(title, top_k=2)
                    if not chunks:
                        chunks = _search_knowledge_base(node_id, top_k=2)
                    _es_cache[node_id] = "\n\n".join(chunks) if chunks else f"知识点 {title} 的相关内容正在准备中。"
                context = _es_cache[node_id]
                templates = {
                    "concept_map": f"## {title}\n\n### 概念解析\n\n{context}\n\n---\n*难度: {difficulty:.0%}*",
                    "code_snippet": f"## {title} · 代码示例\n\n```python\n# 相关实现代码\n{context[:800]}\n```\n\n---\n*难度: {difficulty:.0%}*",
                    "interactive_exercise": f"## 互动练习 · {title}\n\n阅读以下内容并回答问题：\n\n{context[:600]}\n\n---\n*难度: {difficulty:.0%}*",
                    "video_summary": f"## 视频摘要 · {title}\n\n{context[:500]}\n\n---\n*难度: {difficulty:.0%}*",
                    "diagnostic_quiz": f"## 诊断测验 · {title}\n\n根据以下知识点完成自测：\n\n{context[:600]}\n\n---\n*难度: {difficulty:.0%}*",
                }
                return templates.get(card_type, context)
            mesh = ContentMeshNode(generate_fn=_hybrid_generate)
        else:
            def _kb_generate(node_id: str, card_type: str, difficulty: float) -> str:
                chunks = _search_knowledge_base(node_id, top_k=2)
                if not chunks:
                    chunks = _search_knowledge_base(_get_node_title(node_id, node_id), top_k=2)
                context = "\n\n".join(chunks) if chunks else f"知识点 {node_id} 的相关内容正在准备中。"
                templates = {
                    "concept_map": f"## {_get_node_title(node_id, node_id)}\n\n### 概念解析\n\n{context}\n\n---\n*难度: {difficulty:.0%}*",
                    "code_snippet": f"## {_get_node_title(node_id, node_id)} · 代码示例\n\n```python\n# 相关实现\n{context[:800]}\n```\n\n---\n*难度: {difficulty:.0%}*",
                    "interactive_exercise": f"## 互动练习 · {_get_node_title(node_id, node_id)}\n\n阅读以下内容并回答问题：\n\n{context[:600]}\n\n---\n*难度: {difficulty:.0%}*",
                    "video_summary": f"## 视频摘要 · {_get_node_title(node_id, node_id)}\n\n{context[:500]}\n\n---\n*难度: {difficulty:.0%}*",
                    "diagnostic_quiz": f"## 诊断测验 · {_get_node_title(node_id, node_id)}\n\n根据以下知识点完成自测：\n\n{context[:600]}\n\n---\n*难度: {difficulty:.0%}*",
                }
                return templates.get(card_type, context)
            mesh = ContentMeshNode(generate_fn=_kb_generate)

        # 初始化冷启动引擎
        cold_engine = ColdStartEngine()
        cold_state = cold_engine.initialize(user_id)

        # 初始化路径规划器（按课程加载图谱数据）
        path_planner = _kg.create_path_planner(course_id)
        # 如果是非 DSA 课程且 Neo4j 中数据为空，先播种
        _kg.seed_course(course_id)

        sessions[user_id][course_id] = {
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
            "pipeline_log": [],
        }

        # 持久化到 SQLite
        _persist_state(user_id, course_id, agent_state, cold_state)

    # 尝试从 DB 恢复（如果内存中没有 agent_state）
    session = sessions[user_id][course_id]
    if session["agent_state"] is None:
        saved = _get_state_repo().load_state(user_id, course_id) if _get_state_repo() else None
        if saved:
            try:
                session["agent_state"] = AgentState.model_validate_json(saved["state_json"])
                if saved.get("cold_state_json"):
                    session["cold_state"] = ColdStartState.model_validate_json(saved["cold_state_json"])
            except Exception:
                pass  # 反序列化失败则使用新创建的
    return session


# ─── API 端点 ────────────────────────────────────────────────

async def api_reset(request: Request) -> JSONResponse:
    """重置会话"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    course_id = body.get("course_id", "data_structures")
    if user_id in sessions:
        sessions[user_id].pop(course_id, None)
    get_or_create_session(user_id, course_id)
    return JSONResponse({"status": "ok", "user_id": user_id, "course_id": course_id})


async def api_get_state(request: Request) -> JSONResponse:
    """获取当前 AgentState"""
    user_id = request.query_params.get("user_id", "demo_user")
    course_id = request.query_params.get("course_id", "data_structures")
    session = get_or_create_session(user_id, course_id)
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
    course_id = request.query_params.get("course_id", "data_structures")
    session = get_or_create_session(user_id, course_id)
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
    course_id = body.get("course_id", "data_structures")
    answer = body.get("answer")
    session = get_or_create_session(user_id, course_id)

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

    # 持久化冷启动状态
    _persist_state(user_id, course_id, agent_state, cold_state)
    return JSONResponse(result)

async def api_init_path(request: Request) -> JSONResponse:
    """冷启动完成后，初始化学习路径"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    course_id = body.get("course_id", "data_structures")
    session = get_or_create_session(user_id, course_id)
    agent_state: AgentState = session["agent_state"]
    path_planner: PathPlanner = session["path_planner"]

    # 根据冷启动答案，标记已掌握节点
    _cs_answers = agent_state.internal_state.get("_cold_start_answers", [])
    for answer in _cs_answers:
        if isinstance(answer, list):
            for item in answer:
                _apply_kb_premastery(item, agent_state, course_id)
        elif isinstance(answer, str):
            _apply_kb_premastery(answer, agent_state, course_id)
    # 如果没有记录，回退到 knowledge_base
    if not agent_state.dynamic_profile.knowledge_mastery:
        for kb_item in agent_state.static_profile.knowledge_base:
            _apply_kb_premastery(kb_item, agent_state, course_id)

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

    _persist_state(user_id, course_id, agent_state, session.get("cold_state"))
    return JSONResponse({
        "active_path": agent_state.active_path,
        "current_node_id": agent_state.current_node_id,
        "target_node_id": agent_state.target_node_id,
    })


async def api_run_pipeline_step(request: Request) -> JSONResponse:
    """执行一轮完整的 Agent 管线（模拟一次学习交互）"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    course_id = body.get("course_id", "data_structures")
    # 模拟的行为数据
    correctness = body.get("correctness", 0.75)
    time_spent_ratio = body.get("time_spent_ratio", 1.0)
    code_pass_rate = body.get("code_pass_rate", 0.70)
    help_count = body.get("help_count", 0)
    tutor_query = body.get("tutor_query", None)
    # 可选：指定要生成资源的知识点（用于点击路径节点跳转）
    target_node = body.get("current_node_id", None)

    session = get_or_create_session(user_id, course_id)
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
                    title = _get_node_title(nid, nid)
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

    # 持久化学习状态到 SQLite
    _persist_state(user_id, course_id, agent_state, session.get("cold_state"))

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
    course_id = body.get("course_id", "data_structures")
    query = body.get("query", "")
    session = get_or_create_session(user_id, course_id)
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
    """获取知识图谱数据（用于前端可视化，可按课程筛选）"""
    course_id = request.query_params.get("course_id", "data_structures")
    return JSONResponse({
        "nodes": [
            {
                "id": n.node_id,
                "title": n.title,
                "difficulty": n.difficulty,
                "estimated_hours": n.estimated_hours,
                "category": n.category,
            }
            for n in _kg.get_all_nodes(course_id)
        ],
        "edges": [
            {
                "source": e.source_id,
                "target": e.target_id,
                "dependency_type": e.dependency_type,
                "weight": e.weight,
            }
            for e in _kg.get_all_edges(course_id)
        ],
    })


async def api_stream_pipeline(request: Request) -> EventSourceResponse:
    """SSE 流式执行完整管线"""
    user_id = request.query_params.get("user_id", "demo_user")
    course_id = request.query_params.get("course_id", "data_structures")
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

_frontend_root = Path(__file__).resolve().parent
_frontend_dist = _frontend_root / "dist"
static_dir = _frontend_dist if _frontend_dist.is_dir() else _frontend_root

# --- Course API Handlers -----------------------------------------------

async def api_list_courses(request: Request) -> JSONResponse:
    """GET /api/courses — 列出所有课程（支持 ?search= 搜索）。"""
    search = request.query_params.get("search", "").strip() or None
    store = _get_course_store()
    courses = store.list_courses(search=search)
    return JSONResponse([c.to_api_dict() for c in courses])


async def api_get_course(request: Request) -> JSONResponse:
    """GET /api/courses/{course_id} — 获取单个课程详情。"""
    course_id = request.path_params.get("course_id", "")
    store = _get_course_store()
    course = store.get_by_id(course_id)
    if course is None:
        return JSONResponse({"detail": "课程不存在"}, status_code=404)
    return JSONResponse(course.to_api_dict())


async def api_get_user_courses(request: Request) -> JSONResponse:
    """GET /api/user/courses — 获取当前用户的选课记录和进度。"""
    user_id = request.query_params.get("user_id", "demo_user")
    enrollments = _get_user_enrollments(user_id)
    store = _get_course_store()

    courses_detail = []
    for cid, info in enrollments.get("courses", {}).items():
        course = store.get_by_id(cid)
        if course:
            d = course.to_api_dict()
            d["enrolled_at"] = info.get("enrolled_at", "")
            d["progress"] = info.get("progress", 0.0)
            d["completed_nodes"] = info.get("completed_nodes", 0)
            courses_detail.append(d)

    return JSONResponse({
        "user_id": user_id,
        "active_course": enrollments.get("active_course", ""),
        "courses": courses_detail,
    })


async def api_enroll_course(request: Request) -> JSONResponse:
    """POST /api/user/courses/enroll — 注册课程（body: {user_id, course_id}）。"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    course_id = body.get("course_id", "").strip()

    store = _get_course_store()
    course = store.get_by_id(course_id)
    if not course:
        return JSONResponse({"detail": f"课程 '{course_id}' 不存在"}, status_code=404)

    _get_enrollment_repo().enroll(user_id, course_id) if _get_enrollment_repo() else None

    # 预热会话
    get_or_create_session(user_id, course_id)

    return JSONResponse({
        "status": "enrolled",
        "user_id": user_id,
        "course_id": course_id,
        "course": course.to_api_dict(),
    })


async def api_switch_course(request: Request) -> JSONResponse:
    """POST /api/user/courses/switch — 切换当前活跃课程（body: {user_id, course_id}）。"""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    course_id = body.get("course_id", "").strip()

    ok = _get_enrollment_repo().switch_course(user_id, course_id) if _get_enrollment_repo() else True
    if not ok:
        return JSONResponse({"detail": f"你尚未注册课程 '{course_id}'"}, status_code=404)

    # 确保会话存在
    session = get_or_create_session(user_id, course_id)
    agent_state: AgentState = session["agent_state"]

    return JSONResponse({
        "status": "switched",
        "user_id": user_id,
        "course_id": course_id,
        "active_path": agent_state.active_path,
        "has_path": len(agent_state.active_path) > 0,
    })


# --- Auth API Handlers ------------------------------------------------

async def api_auth_captcha(request: Request) -> Response:
    """GET /api/auth/captcha — 获取 SVG 数学验证码。"""
    store, captcha = _get_auth()
    svg, token = captcha.generate()
    html = (
        '<html><head><meta charset="utf-8"></head>'
        '<body style="display:flex;flex-direction:column;align-items:center;'
        'justify-content:center;min-height:100vh;font-family:Arial,sans-serif;'
        'background:#f0f2f5">'
        f'<div style="background:#fff;padding:30px 40px;border-radius:12px;'
        f'box-shadow:0 2px 12px rgba(0,0,0,0.08);text-align:center">'
        f'<h3 style="color:#333;margin-bottom:16px">EduAgent 验证码</h3>'
        f'<div style="border:1px solid #e0e0e0;border-radius:6px;padding:8px;'
        f'background:#fafafa">{svg}</div>'
        f'<p style="margin-top:12px;color:#666;font-size:13px">'
        f'请输入上方数学表达式的计算结果</p>'
        f'<p style="color:#999;font-size:11px;word-break:break-all">'
        f'Captcha Token: <code style="background:#f5f5f5;padding:2px 6px;'
        f'border-radius:3px">{token}</code></p>'
        f'</div></body></html>'
    )
    return Response(html, media_type="text/html; charset=utf-8")


async def api_auth_captcha_json(request: Request) -> JSONResponse:
    """GET /api/auth/captcha-json — 获取验证码 (JSON 响应，供前端调用)。"""
    store, captcha = _get_auth()
    svg, token = captcha.generate()
    return JSONResponse({"svg": svg, "captcha_token": token})


async def api_auth_register(request: Request) -> JSONResponse:
    """POST /api/auth/register — 用户注册。"""
    store, captcha = _get_auth()
    from src.auth.security import SecurityManager
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)

    user_id = body.get("user_id", "").strip()
    email = body.get("email", "").strip()
    password = body.get("password", "")
    captcha_token = body.get("captcha_token", "")
    captcha_answer = body.get("captcha_answer", "")

    # 校验验证码
    if not captcha.verify(captcha_token, captcha_answer):
        return JSONResponse({"detail": "验证码错误或已过期"}, status_code=400)

    # 基本校验
    if len(user_id) < 3 or not user_id.replace("_", "").isalnum():
        return JSONResponse(
            {"detail": "用户名需 3-32 字符，仅允许字母/数字/下划线"},
            status_code=400,
        )
    if "@" not in email:
        return JSONResponse({"detail": "邮箱格式无效"}, status_code=400)
    if len(password) < 8:
        return JSONResponse({"detail": "密码至少 8 个字符"}, status_code=400)

    try:
        user = store.create_user(user_id, email, password)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=409)

    token_pair = SecurityManager.create_token_pair(user["user_id"], user["role"])
    return JSONResponse({
        "access_token": token_pair["access_token"],
        "refresh_token": token_pair["refresh_token"],
        "token_type": "bearer",
        "user": {k: user[k] for k in ("user_id", "email", "role", "display_name", "created_at", "last_login_at") if k in user},
    })


async def api_auth_login(request: Request) -> JSONResponse:
    """POST /api/auth/login — 用户登录。"""
    store, captcha = _get_auth()
    from src.auth.security import SecurityManager
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)

    user_id = body.get("user_id", "").strip()
    password = body.get("password", "")
    captcha_token = body.get("captcha_token", "")
    captcha_answer = body.get("captcha_answer", "")

    if not captcha.verify(captcha_token, captcha_answer):
        return JSONResponse({"detail": "验证码错误或已过期"}, status_code=400)

    if not user_id or not password:
        return JSONResponse({"detail": "用户名和密码不能为空"}, status_code=400)

    user = store.verify_login(user_id, password)
    if user is None:
        return JSONResponse(
            {"detail": "用户名或密码错误"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_pair = SecurityManager.create_token_pair(user["user_id"], user["role"])

    # Redis: 存储 Refresh Token JTI（高并发鉴权缓存）
    store_refresh_token(user["user_id"], token_pair["refresh_jti"])

    return JSONResponse({
        "access_token": token_pair["access_token"],
        "refresh_token": token_pair["refresh_token"],
        "token_type": "bearer",
        "user": {k: user[k] for k in ("user_id", "email", "role", "display_name", "created_at", "last_login_at") if k in user},
    })


async def api_auth_logout(request: Request) -> JSONResponse:
    """POST /api/auth/logout — 注销登录（Redis 黑名单）。"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    access_token = body.get("access_token", "")
    refresh_token = body.get("refresh_token", "")

    # 从 Authorization header 回退提取
    if not access_token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            access_token = auth[7:]

    from src.auth.security import SecurityManager
    # 将 Access Token 加入黑名单
    if access_token:
        try:
            payload = SecurityManager.decode_token(access_token)
            blacklist_token(payload.get("jti", ""), ttl=900)
        except ValueError:
            pass

    # 将 Refresh Token 加入黑名单
    if refresh_token:
        try:
            payload = SecurityManager.decode_token(refresh_token)
            blacklist_token(payload.get("jti", ""), ttl=604800)  # 7天
        except ValueError:
            pass

    return JSONResponse({"status": "logged_out"})


async def api_auth_refresh(request: Request) -> JSONResponse:
    """POST /api/auth/refresh — 令牌刷新轮转（Redis 重放检测）。"""
    from src.auth.security import SecurityManager
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)

    refresh_token = body.get("refresh_token", "")
    if not refresh_token:
        return JSONResponse({"detail": "refresh_token 不能为空"}, status_code=400)

    try:
        payload = SecurityManager.decode_token(refresh_token)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=401)

    if payload.get("type") != "refresh":
        return JSONResponse({"detail": "INVALID_TOKEN_TYPE"}, status_code=401)

    user_id = payload.get("sub", "")
    old_jti = payload.get("jti", "")

    # Redis 重放攻击检测
    if is_rotated(old_jti):
        revoke_all_user_sessions(user_id)
        return JSONResponse({"detail": "SECURITY_BREACH_REUSE_DETECTED"}, status_code=403)

    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    role = user["role"] if user else "STUDENT"

    token_pair = SecurityManager.create_token_pair(user_id, role)

    # Redis: 旧令牌标记为已轮转（10s 宽限窗口），存储新令牌
    mark_rotated(old_jti, ttl=10)
    store_refresh_token(user_id, token_pair["refresh_jti"])

    user_info = {k: user[k] for k in ("user_id", "email", "role", "display_name", "created_at", "last_login_at") if k in user} if user else {}
    return JSONResponse({
        "access_token": token_pair["access_token"],
        "refresh_token": token_pair["refresh_token"],
        "token_type": "bearer",
        "user": user_info,
    })


async def api_auth_me(request: Request) -> JSONResponse:
    """GET /api/auth/me — 获取当前用户信息 (需 Bearer Token)。"""
    from src.auth.security import SecurityManager
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "缺少认证令牌"}, status_code=401)

    token = auth_header[7:]
    try:
        payload = SecurityManager.decode_token(token)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=401)

    if payload.get("type") != "access":
        return JSONResponse({"detail": "INVALID_TOKEN_TYPE"}, status_code=401)

    user_id = payload.get("sub", "")
    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    if user is None:
        return JSONResponse({"detail": "用户不存在"}, status_code=404)

    return JSONResponse({k: user[k] for k in ("user_id", "email", "role", "display_name", "created_at", "last_login_at") if k in user})


app = Starlette(
    debug=True,
    routes=[
        Route("/api/courses", api_list_courses, methods=["GET"]),
        Route("/api/courses/{course_id}", api_get_course, methods=["GET"]),
        Route("/api/user/courses", api_get_user_courses, methods=["GET"]),
        Route("/api/user/courses/enroll", api_enroll_course, methods=["POST"]),
        Route("/api/user/courses/switch", api_switch_course, methods=["POST"]),
        Route("/api/reset", api_reset, methods=["POST"]),
        Route("/api/state", api_get_state, methods=["GET"]),
        Route("/api/cold-start/probe", api_cold_start_probe, methods=["GET"]),
        Route("/api/cold-start/answer", api_cold_start_answer, methods=["POST"]),
        Route("/api/init-path", api_init_path, methods=["POST"]),
        Route("/api/pipeline/step", api_run_pipeline_step, methods=["POST"]),
        Route("/api/pipeline/stream", api_stream_pipeline, methods=["GET"]),
        Route("/api/tutor/ask", api_ask_tutor, methods=["POST"]),
        Route("/api/knowledge-graph", api_knowledge_graph, methods=["GET"]),
        # ── 认证 API ──
        Route("/api/auth/captcha", api_auth_captcha, methods=["GET"]),
        Route("/api/auth/captcha-json", api_auth_captcha_json, methods=["GET"]),
        Route("/api/auth/register", api_auth_register, methods=["POST"]),
        Route("/api/auth/login", api_auth_login, methods=["POST"]),
        Route("/api/auth/refresh", api_auth_refresh, methods=["POST"]),
        Route("/api/auth/logout", api_auth_logout, methods=["POST"]),
        Route("/api/auth/me", api_auth_me, methods=["GET"]),
        # ── 新增 API (合并自 backend/) ──
        *new_routes,
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
    _safe_get_es_kb()
    print("[Init] Ready.")
    uvicorn.run(app, host="0.0.0.0", port=8800, log_level="info")
