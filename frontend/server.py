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
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import JSONResponse, Response
from pydantic import ValidationError

# 新增 API 路由 (合并自 backend/)
from src.routes.new_api_routes import new_routes
from starlette.requests import Request

# --- Course System ---
from src.courses import CourseStore
from src.application import (
    code_practice_service,
    learning_assets_service,
    profile_service,
    resource_service,
    review_service,
    session_service,
    tutor_service,
)
from src.application._common import get_session, persist_session
from src.api_models.tutor_request import TutorRequest
from src.auth.account_service import (
    AccountLifecycleError,
    build_learning_summary,
    consume_action_token,
    deliver_action_email,
    email_delivery_configured,
    hash_action_token,
    is_production,
    issue_action_token,
    normalize_preferences,
    normalize_privacy,
    refresh_expiry_iso,
    resolve_action_token,
    revoke_all_sessions_fail_closed,
    run_required_cleanup_steps,
)
from src.observability import (
    bind_context,
    configure_logging,
    incr_metric,
    log_event,
    metrics_snapshot,
    new_request_id,
    observe_metric,
)
from src.release_controls import RolloutDecision, operational_switch, rollout_decision
from src.auth.rate_limiter import KeyedConcurrencyLimiter, RateLimitBackendUnavailable, RateLimiter
from src.auth.captcha import CaptchaBackendUnavailable
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

from src.auth.security import validate_security_configuration

validate_security_configuration()

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import json
import hashlib
import math
import secrets
import threading
import time
import uuid
import asyncio
import traceback
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
configure_logging()

# ─── LLM 客户端（全局单例）─────────────────────────────────
_llm_client = None
_llm_unavailable = False

def _get_llm():
    global _llm_client, _llm_unavailable
    if _llm_client is not None or _llm_unavailable:
        return _llm_client

    if _llm_client is None:
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if api_key and not api_key.startswith("sk-your-") and len(api_key) > 20:
            try:
                from src.llm import LLMClientV2

                _llm_client = LLMClientV2(provider="qwen")
                print(f"[LLM] LLMClientV2 connected (provider={_llm_client.provider}, model={_llm_client.config.get('model','?')})")
            except Exception as exc:
                # LLM dependencies and provider configuration are optional. Session
                # creation must retain its deterministic fallback when unavailable.
                _llm_unavailable = True
                print(f"[LLM] Optional client unavailable ({type(exc).__name__}: {exc}), using fallback mode")
        elif api_key:
            _llm_unavailable = True
            print(f"[LLM] API key appears to be a placeholder ({api_key[:12]}...), using fallback mode")
        else:
            _llm_unavailable = True
            print("[LLM] No API key found, using fallback mode")
    return _llm_client


# --- 数据库层 (全局单例) ------------------------------------------
try:
    from src.database import (
        db as _db, UserRepo, UserProfileRepo, JsonUserProfileRepo,
        AccountRepo, JsonAccountRepo, EnrollmentRepo, StateRepo,
        SessionRepo, SessionSnapshotRepo,
        get_redis, redis_backend_status, durable_redis_available,
        blacklist_token, is_blacklisted, store_refresh_token,
        mark_rotated, is_rotated, is_refresh_token_active,
        revoke_user_session, revoke_all_user_sessions,
        cache_action_token, consume_cached_action_token,
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
    SessionRepo = None
    SessionSnapshotRepo = None
    UserProfileRepo = None
    AccountRepo = None
    from src.database.user_profile_repo import JsonUserProfileRepo
    from src.database.account_repo import JsonAccountRepo
    get_redis = lambda: None
    redis_backend_status = lambda: "unavailable"
    durable_redis_available = lambda: False
    blacklist_token = lambda *a, **kw: None
    is_blacklisted = lambda *a, **kw: False
    store_refresh_token = lambda *a, **kw: None
    mark_rotated = lambda *a, **kw: None
    is_rotated = lambda *a, **kw: False
    is_refresh_token_active = lambda *a, **kw: False
    revoke_user_session = lambda *a, **kw: None
    revoke_all_user_sessions = lambda *a, **kw: None
    cache_action_token = lambda *a, **kw: None
    consume_cached_action_token = lambda *a, **kw: None

_user_repo = None
_enrollment_repo = None
_state_repo = None
_profile_repo = None
_account_repo = None
_auth_captcha = None
_auth_backend_durable = False


class AuthBackendUnavailable(RuntimeError):
    """Production authentication storage cannot be reached safely."""


class _InMemoryEnrollmentRepo:
    """Process-local fallback when the PostgreSQL enrollment repository is unavailable."""

    def __init__(self) -> None:
        self._users: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _enrolled_at() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def get_user_enrollments(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            enrollment = self._users.get(user_id)
            if enrollment is None:
                return {"active_course": "", "courses": {}}
            return {
                "active_course": enrollment["active_course"],
                "courses": {
                    course_id: dict(course_info)
                    for course_id, course_info in enrollment["courses"].items()
                },
            }

    def enroll(self, user_id: str, course_id: str) -> Dict[str, Any]:
        with self._lock:
            enrollment = self._users.setdefault(
                user_id,
                {"active_course": "", "courses": {}},
            )
            enrollment["courses"].setdefault(
                course_id,
                {
                    "enrolled_at": self._enrolled_at(),
                    "progress": 0.0,
                    "completed_nodes": 0,
                },
            )
            enrollment["active_course"] = course_id
        return {"status": "enrolled", "user_id": user_id, "course_id": course_id}

    def switch_course(self, user_id: str, course_id: str) -> bool:
        with self._lock:
            enrollment = self._users.get(user_id)
            if enrollment is None or course_id not in enrollment["courses"]:
                return False
            enrollment["active_course"] = course_id
            return True

    def update_progress(
        self,
        user_id: str,
        course_id: str,
        progress: float,
        completed_nodes: int,
    ) -> None:
        with self._lock:
            enrollment = self._users.get(user_id)
            if enrollment is None:
                return
            course = enrollment["courses"].get(course_id)
            if course is None:
                return
            course["progress"] = min(1.0, max(0.0, float(progress)))
            course["completed_nodes"] = max(0, int(completed_nodes))

    def unenroll(self, user_id: str, course_id: str) -> Dict[str, Any]:
        with self._lock:
            enrollment = self._users.get(user_id)
            if enrollment is None or course_id not in enrollment["courses"]:
                return {"removed": False, "active_course": "", "remaining_courses": []}
            was_active = enrollment.get("active_course") == course_id
            enrollment["courses"].pop(course_id, None)
            remaining = list(enrollment["courses"])
            if was_active:
                enrollment["active_course"] = remaining[-1] if remaining else ""
            return {
                "removed": True,
                "active_course": enrollment.get("active_course", ""),
                "remaining_courses": remaining,
            }

    def delete_all(self, user_id: str) -> None:
        with self._lock:
            self._users.pop(user_id, None)


class _JsonEnrollmentRepo(_InMemoryEnrollmentRepo):
    """Durable fallback used by local deployments without PostgreSQL."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file_path = Path(
            file_path
            or os.getenv("ENROLLMENT_STATE_PATH", str(PROJECT_ROOT / "frontend" / "_enrollments.json"))
        )
        super().__init__()
        self._load()

    def _load(self) -> None:
        try:
            if self._file_path.exists():
                payload = json.loads(self._file_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self._users = payload
        except (OSError, json.JSONDecodeError, TypeError):
            self._users = {}

    def _save(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
        temp.write_text(json.dumps(self._users, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._file_path)

    def enroll(self, user_id: str, course_id: str) -> Dict[str, Any]:
        result = super().enroll(user_id, course_id)
        with self._lock:
            self._save()
        return result

    def switch_course(self, user_id: str, course_id: str) -> bool:
        result = super().switch_course(user_id, course_id)
        if result:
            with self._lock:
                self._save()
        return result

    def update_progress(self, user_id: str, course_id: str, progress: float, completed_nodes: int) -> None:
        super().update_progress(user_id, course_id, progress, completed_nodes)
        with self._lock:
            self._save()

    def unenroll(self, user_id: str, course_id: str) -> Dict[str, Any]:
        result = super().unenroll(user_id, course_id)
        if result["removed"]:
            with self._lock:
                self._save()
        return result

    def delete_all(self, user_id: str) -> None:
        super().delete_all(user_id)
        with self._lock:
            self._save()


_fallback_enrollment_repo = _JsonEnrollmentRepo()

def _get_user_repo():
    global _user_repo
    if _user_repo is None and _db_available:
        _user_repo = UserRepo()
    return _user_repo

def _get_enrollment_repo():
    global _enrollment_repo
    if _enrollment_repo is None and _db_available:
        try:
            candidate = EnrollmentRepo()
            candidate.get_user_enrollments("__repository_healthcheck__")
            _enrollment_repo = candidate
        except Exception:
            _enrollment_repo = _fallback_enrollment_repo
    return _enrollment_repo or _fallback_enrollment_repo

def _get_state_repo():
    global _state_repo
    if _state_repo is None and _db_available:
        _state_repo = StateRepo()
    return _state_repo

def _get_profile_repo():
    global _profile_repo
    if _profile_repo is not None:
        return _profile_repo
    if _db_available and UserProfileRepo is not None:
        try:
            repo = UserProfileRepo()
            repo.ensure_tables()
            _profile_repo = repo
            return repo
        except Exception:
            pass
    _profile_repo = JsonUserProfileRepo()
    return _profile_repo

def _get_account_repo():
    global _account_repo
    if _account_repo is not None:
        if is_production() and isinstance(_account_repo, JsonAccountRepo):
            raise AuthBackendUnavailable("AUTH_STORAGE_UNAVAILABLE")
        return _account_repo
    if _db_available and AccountRepo is not None:
        try:
            repo = AccountRepo()
            repo.ensure_tables()
            _account_repo = repo
            return repo
        except Exception:
            if is_production():
                raise AuthBackendUnavailable("AUTH_STORAGE_UNAVAILABLE")
    if is_production():
        raise AuthBackendUnavailable("AUTH_STORAGE_UNAVAILABLE")
    _account_repo = JsonAccountRepo()
    return _account_repo

def _get_auth():
    global _auth_captcha, _user_repo, _auth_backend_durable
    if _auth_captcha is not None:
        if is_production() and not _auth_backend_durable:
            raise AuthBackendUnavailable("AUTH_STORAGE_UNAVAILABLE")
        if not is_production() or bool(getattr(_auth_captcha, "uses_shared_backend", False)):
            return _user_repo, _auth_captcha
        _auth_captcha = None
    if is_production() and not _auth_backend_durable:
        # Never promote a cached development UserStore to a durable backend
        # merely because the process environment changed.
        _user_repo = None
    if _auth_captcha is None:
        from src.auth.captcha import CaptchaGenerator
        from src.auth.models import PresetAccounts, UserStore

        if _db_available:
            try:
                _user_repo = _get_user_repo()
                # Production skips fixture creation, so an explicit query is
                # required to prove the durable backend is actually reachable.
                _user_repo.count()
                _auth_backend_durable = True
                created = [] if is_production() else PresetAccounts.ensure_presets_db(_user_repo)
            except Exception:
                if is_production():
                    _user_repo = None
                    _auth_backend_durable = False
                    raise AuthBackendUnavailable("AUTH_STORAGE_UNAVAILABLE")
                _user_repo = UserStore()
                _auth_backend_durable = False
                created = [] if is_production() else PresetAccounts.ensure_presets(_user_repo)
        else:
            if is_production():
                raise AuthBackendUnavailable("AUTH_STORAGE_UNAVAILABLE")
            _user_repo = UserStore()
            _auth_backend_durable = False
            created = [] if is_production() else PresetAccounts.ensure_presets(_user_repo)
        print(f"[Auth] {len(created)} preset accounts ready")
        for u in created:
            if isinstance(u, dict):
                user_id = u.get("user_id", "")
                role = u.get("role", "")
                email = u.get("email", "")
            else:
                user_id = getattr(u, "user_id", "")
                role = getattr(u, "role", "")
                email = getattr(u, "email", "")
            print(f"  - {user_id} ({role}): {email}")
        captcha_redis = None
        if is_production():
            captcha_redis = get_redis()
            if captcha_redis is None or redis_backend_status() != "redis":
                raise AuthBackendUnavailable("AUTH_STORAGE_UNAVAILABLE")
        _auth_captcha = CaptchaGenerator(
            redis_client=captcha_redis,
            require_shared=is_production(),
        )
    return _user_repo, _auth_captcha


# --- 导入项目模块 -------------------------------------------------
from src.state.agent_state import (
    AgentState, StaticProfile, DynamicProfile,
    CognitiveStyleDistribution, ErrorTypeDistribution,
    LatestBehavior, ResourceCard, KnowledgeMasteryRecord, AgentFeedbackItem,
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
from src.llm.token_estimator import TokenEstimator

_kg = get_kg_manager()


def _get_node_title(node_id: str, default: Optional[str] = None) -> str:
    """鑾峰彇鑺傜偣鏍囬銆?"""
    return _kg.get_node_title(node_id) or default or node_id


def _apply_kb_premastery(kb_item: str, agent_state: AgentState, course_id: str = "data_structures") -> None:
    node_map = _kg.get_knowledge_mastery_map([kb_item], course_id)
    for nid, mastery in node_map.items():
        if nid not in agent_state.dynamic_profile.knowledge_mastery:
            agent_state.dynamic_profile.knowledge_mastery[nid] = mastery


RESOURCE_CONTRACT_VERSION = 2
AGENT_FEEDBACK_VERSION = 1
MASTERY_ADVANCE_THRESHOLD = 0.65
QWEN_INPUT_BUDGET = 128000
QWEN_COMPLETION_RESERVE = 6000
QWEN_CONTEXT_BUDGET = QWEN_INPUT_BUDGET - QWEN_COMPLETION_RESERVE
RESOURCE_CARD_ORDER = [
    "concept_map",
    "code_snippet",
    "interactive_exercise",
    "video_summary",
    "diagnostic_quiz",
]


def _strip_markdown(source: str) -> str:
    text = str(source or "")
    text = re.sub(r"```mermaid[\s\S]*?```", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"```[^\n]*\n?([\s\S]*?)```", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[[^\]]*\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _extract_mermaid_source(content: str) -> str:
    match = re.search(r"```mermaid\s*([\s\S]*?)```", str(content or ""), re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_code_block(content: str) -> tuple[str, str]:
    match = re.search(r"```([a-zA-Z0-9_+-]*)\s*([\s\S]*?)```", str(content or ""))
    if match:
        language = match.group(1).strip() or "python"
        code = match.group(2).strip()
        return language, code
    return "python", _strip_markdown(content)


def _extract_bullets(content: str, limit: int = 4) -> List[str]:
    bullets = []
    for line in str(content or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "+ ")):
            bullets.append(stripped[2:].strip())
    if bullets:
        return bullets[:limit]

    text = _strip_markdown(content)
    segments = [segment.strip() for segment in re.split(r"[。\n；;]+", text) if segment.strip()]
    return segments[:limit]


def _extract_sentences(content: str, limit: int = 6) -> List[str]:
    text = _strip_markdown(content)
    if not text:
        return []
    parts = re.split(r"[。\n！？!?；;]+", text)
    return [part.strip() for part in parts if part.strip()][:limit]


def _build_mermaid_from_bullets(title: str, bullets: List[str]) -> str:
    safe_title = title.replace('"', "'")
    lines = [f'ROOT["{safe_title}"]']
    if not bullets:
        lines.append('ROOT --> ITEM1["核心概念"]')
    else:
        for index, bullet in enumerate(bullets[:4], start=1):
            safe_bullet = bullet.replace('"', "'")
            lines.append(f'ROOT --> ITEM{index}["{safe_bullet}"]')
    return "graph TD\n    " + "\n    ".join(lines)


def _build_quiz_questions(title: str, content: str) -> List[Dict[str, Any]]:
    seeds = _extract_sentences(content, limit=3)
    if not seeds:
        seeds = [f"{title} 的核心概念需要结合当前资源继续理解。"]

    questions: List[Dict[str, Any]] = []
    for index, seed in enumerate(seeds, start=1):
        prompt = f"根据当前资源，关于“{title}”哪项说法最符合内容？"
        options = [
            seed,
            f"{title} 与当前主题无关",
            f"{title} 只适用于单一特例",
            "以上都不对",
        ]
        questions.append(
            {
                "id": f"q{index}",
                "prompt": prompt,
                "options": options,
                "answer_index": 0,
                "explanation": seed,
            }
        )
    return questions


def _estimate_token_count(text: str) -> int:
    return TokenEstimator.estimate(text or "")


def _clip_text_to_tokens(text: str, max_tokens: int) -> str:
    text = str(text or "").strip()
    if not text or _estimate_token_count(text) <= max_tokens:
        return text

    low = 0
    high = len(text)
    best = ""
    while low <= high:
        mid = (low + high) // 2
        candidate = text[:mid]
        if _estimate_token_count(candidate) <= max_tokens:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best.strip()


def _chunk_text_by_tokens(text: str, chunk_token_budget: int) -> List[str]:
    paragraphs = [p.strip() for p in str(text or "").split("\n\n") if p.strip()]
    if not paragraphs:
        stripped = _strip_markdown(text)
        return [_clip_text_to_tokens(stripped, chunk_token_budget)] if stripped else []

    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0
    for paragraph in paragraphs:
        para_tokens = _estimate_token_count(paragraph)
        if para_tokens > chunk_token_budget:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_tokens = 0
            chunks.append(_clip_text_to_tokens(paragraph, chunk_token_budget))
            continue
        if current and current_tokens + para_tokens > chunk_token_budget:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_tokens = para_tokens
        else:
            current.append(paragraph)
            current_tokens += para_tokens
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _budget_context_chunks(
    node_title: str,
    chunks: List[str],
    base_prompt_tokens: int,
    per_chunk_budget: int = 14000,
) -> Dict[str, Any]:
    remaining_budget = max(3000, QWEN_CONTEXT_BUDGET - base_prompt_tokens)
    normalized = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
    selected: List[str] = []
    used_tokens = 0
    for chunk in normalized:
        clipped = _clip_text_to_tokens(chunk, min(per_chunk_budget, remaining_budget))
        if not clipped:
            continue
        clip_tokens = _estimate_token_count(clipped)
        if selected and used_tokens + clip_tokens > remaining_budget:
            break
        if not selected and clip_tokens > remaining_budget:
            clipped = _clip_text_to_tokens(clipped, remaining_budget)
            clip_tokens = _estimate_token_count(clipped)
        if clipped:
            selected.append(clipped)
            used_tokens += clip_tokens
        if used_tokens >= remaining_budget:
            break

    overflow_applied = "direct"
    batch_count = 1
    if normalized and not selected:
        selected = [_clip_text_to_tokens(normalized[0], remaining_budget)]
        used_tokens = _estimate_token_count(selected[0])
        overflow_applied = "smart_truncate"
    elif len(normalized) > len(selected):
        overflow_applied = "map_reduce"
        batch_count = len(_chunk_text_by_tokens("\n\n".join(normalized), max(4000, remaining_budget // 3)))

    return {
        "selected_chunks": selected,
        "estimated_input_tokens": base_prompt_tokens + used_tokens,
        "overflow_applied": overflow_applied,
        "batch_count": batch_count,
        "truncated_source_count": max(0, len(normalized) - len(selected)),
        "node_title": node_title,
    }


def _build_resource_metadata(card_type: str, node_title: str, content: str) -> Dict[str, Any]:
    summary = _strip_markdown(content)
    summary_text = summary[:220].strip() if summary else f"{node_title} 的学习资源已生成。"
    bullets = _extract_bullets(content)
    mermaid_source = _extract_mermaid_source(content) or _build_mermaid_from_bullets(node_title, bullets)

    if card_type == "concept_map":
        return {
            "render_type": "concept_map",
            "title": node_title,
            "summary": summary_text,
            "learning_objectives": bullets[:3],
            "sections": [{"heading": "内容概览", "body": summary_text}],
            "bullets": bullets,
            "common_misconceptions": [],
            "mermaid_source": mermaid_source,
            "review_prompts": [],
        }

    if card_type == "code_snippet":
        language, code = _extract_code_block(content)
        explanation = summary_text if summary_text != code else ""
        return {
            "render_type": "code_snippet",
            "title": f"{node_title} 代码示例",
            "language": language,
            "scenario": f"围绕 {node_title} 的基础代码示例",
            "prerequisites": [],
            "code": code,
            "walkthrough_steps": _extract_sentences(content, limit=4),
            "explanation": explanation,
            "complexity_notes": [],
            "pitfalls": [],
            "experiments": [],
        }

    if card_type == "interactive_exercise":
        steps = _extract_sentences(content, limit=4)
        checkpoints = bullets[:3] if bullets else steps[:3]
        return {
            "render_type": "interactive_exercise",
            "title": f"{node_title} 互动练习",
            "prompt": summary_text,
            "goal": summary_text,
            "steps": steps,
            "checkpoints": checkpoints,
            "hints": [],
            "expected_outcome": "",
            "solution_outline": "",
        }

    if card_type == "video_summary":
        key_points = bullets[:4] if bullets else _extract_sentences(content, limit=4)
        return {
            "render_type": "video_summary",
            "title": f"{node_title} 视频摘要",
            "summary": summary_text,
            "key_points": key_points,
            "timeline": [],
            "watch_focus": [],
            "review_questions": [],
            "duration_minutes": 10,
            "video_url": None,
        }

    if card_type == "diagnostic_quiz":
        return {
            "render_type": "diagnostic_quiz",
            "title": f"{node_title} 诊断测验",
            "questions": _build_quiz_questions(node_title, content),
            "pass_threshold": MASTERY_ADVANCE_THRESHOLD,
            "after_quiz_guidance": "",
        }

    return {
        "render_type": card_type,
        "title": node_title,
        "summary": summary_text,
    }


def _normalize_resource_card(card: ResourceCard) -> ResourceCard:
    node_title = _get_node_title(card.node_id) or card.node_id
    base_metadata = _build_resource_metadata(card.card_type, node_title, card.content)
    existing_metadata = dict(card.metadata or {})
    card.metadata = {**base_metadata, **existing_metadata}
    return card


def _dedupe_and_sort_cards(cards: List[ResourceCard]) -> List[ResourceCard]:
    latest_by_type: Dict[str, ResourceCard] = {}
    extras: List[ResourceCard] = []

    for raw_card in cards:
        card = _normalize_resource_card(raw_card)
        if card.card_type in RESOURCE_CARD_ORDER:
            latest_by_type[card.card_type] = card
        else:
            extras.append(card)

    ordered = [latest_by_type[card_type] for card_type in RESOURCE_CARD_ORDER if card_type in latest_by_type]
    return ordered + extras


def _normalize_state_resources(agent_state: AgentState) -> None:
    normalized: Dict[str, List[ResourceCard]] = {}
    for node_id, cards in agent_state.generated_resources.items():
        normalized[node_id] = _dedupe_and_sort_cards(cards)
    agent_state.generated_resources = normalized


def _format_feedback_item(
    agent: str,
    stage: str,
    status: str,
    headline: str,
    summary: str,
    structured_data: Optional[Dict[str, Any]] = None,
    details_md: str = "",
    artifacts: Optional[Dict[str, Any]] = None,
) -> AgentFeedbackItem:
    return AgentFeedbackItem(
        agent=agent,
        stage=stage,
        status=status,
        headline=headline,
        summary=summary,
        details_md=details_md,
        structured_data=structured_data or {},
        artifacts=artifacts or {},
    )


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

# 保存后台 asyncio.Task 引用，防止被 GC 提前回收
_background_tasks: set = set()

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


def _search_knowledge_base(query: str, top_k: int = 5, course_id: str = "") -> List[str]:
    """从 ES 知识库检索相关内容。

    当 course_id 非空时，优先检索对应课程下带标签的内容（如课堂 Q&A），
    结果不足再用全局检索补全，最终去重后返回 top_k 条。
    这样既能命中课程专属 Q&A，也不丢失预置知识库的共享内容。
    """
    client = _safe_get_es_kb()
    if client is None:
        return []

    results: List[str] = []
    seen: set = set()

    def _extract(search_result) -> None:
        for h in search_result.get("hits", {}).get("hits", []):
            content = h["_source"].get("content", "")
            if content and content not in seen:
                results.append(content)
                seen.add(content)

    try:
        if course_id:
            # 1) 先检索对应课程的带标签内容（Q&A 等 section=course_id 的 chunk）
            try:
                course_result = client.hybrid_search(
                    query, top_k=top_k,
                    filters={"section": course_id},
                )
                _extract(course_result)
            except Exception:
                pass

        if len(results) < top_k:
            # 2) 不足时补全局检索（预置教材内容）
            try:
                global_result = client.hybrid_search(query, top_k=top_k)
                _extract(global_result)
            except Exception:
                pass

        return results[:top_k]
    except Exception:
        return []


def _schedule_qa_index(question: str, answer: str, course_id: str) -> None:
    """创建后台 Task 将 Q&A 索引入 ES，保留引用防止被 GC 提前回收。"""
    task = asyncio.create_task(_index_qa_to_knowledge_base(question, answer, course_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _index_qa_to_knowledge_base(question: str, answer: str, course_id: str) -> None:
    """将 Q&A 对异步索引到 ES 知识库（fire-and-forget，失败时静默忽略）。"""
    try:
        from src.vector.elasticsearch_knowledge_base import KnowledgeBaseChunk
        client = _safe_get_es_kb()
        if client is None:
            return
        import hashlib, time
        chunk_id = hashlib.md5(f"qa:{course_id}:{question[:80]}:{time.time()}".encode()).hexdigest()
        content  = f"Q: {question}\n\nA: {answer}"
        chunk = KnowledgeBaseChunk(
            chunk_id=chunk_id,
            document_id=f"qa_{course_id}",
            source_path=f"qa/{course_id}/runtime",
            chunk_index=0,
            content=content,
            content_length=len(content),
            chapter="课堂问答",
            section=course_id,
            knowledge_point=question[:60],
            title_path=f"{course_id} > 课堂问答 > {question[:40]}",
            heading_hierarchy=["课堂问答"],
            language_tags=[],
            has_code_block=False,
            has_latex=False,
            code_block_count=0,
            latex_formula_count=0,
            metadata={"course_id": course_id, "type": "qa_pair"},
        )
        # 生成 embedding
        if _es_embedder is not None:
            chunk.embedding = _es_embedder.embed(content)
        await asyncio.to_thread(client.bulk_index_chunks, [chunk])
    except Exception as e:
        print(f"[ES] Q&A index failed (non-critical): {e}")


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
            nc.set_user_mastery(user_id, node_id, round(score, 4), course_id)
    except Exception:
        # Neo4j 写入失败不影响主流程（回退到内存+PostgreSQL）
        pass


def _sync_enrollment_progress(user_id: str, course_id: str, agent_state) -> None:
    """同步选课进度到 PostgreSQL user_courses 表。"""
    enr_repo = _get_enrollment_repo()
    if not enr_repo or not agent_state.active_path:
        return
    try:
        mastery = agent_state.dynamic_profile.knowledge_mastery
        completed = sum(1 for v in mastery.values() if v >= MASTERY_ADVANCE_THRESHOLD)
        total_nodes = len(agent_state.active_path)
        progress = completed / total_nodes if total_nodes > 0 else 0.0
        enr_repo.update_progress(user_id, course_id, progress, completed)
    except Exception as e:
        print(f"[DB] Progress sync failed: {e}")


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
                        content = llm.generate_content(node_id, card_type, difficulty)
                        if content and len(content) > 50:
                            print(f"[LLM] Generated concept_map for {node_id} ({len(content)} chars)")
                            return content
                        print(f"[LLM] Short/empty response for {node_id}, falling back to ES")
                    except Exception as e:
                        print(f"[LLM] generate_content failed for {node_id}: {type(e).__name__}: {e}")
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
    if session.get("agent_state") is not None:
        _normalize_state_resources(session["agent_state"])
        if getattr(session["agent_state"], "agent_feedback", None) is None:
            session["agent_state"].agent_feedback = []
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
    _normalize_state_resources(state)
    return JSONResponse({
        "resource_contract_version": RESOURCE_CONTRACT_VERSION,
        "agent_feedback_version": AGENT_FEEDBACK_VERSION,
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
        "agent_feedback": [item.model_dump() for item in state.agent_feedback],
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
        _persist_state(user_id, course_id, agent_state, cold_state)
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
        _persist_state(user_id, course_id, agent_state, cold_state)
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
    _sync_enrollment_progress(user_id, course_id, agent_state)
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

    # 从 ES 知识库检索参考上下文（优先对应课程内容）
    ref_chunks = _search_knowledge_base(query, top_k=5, course_id=course_id)

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

    budget_info = _budget_context_chunks(query, ref_chunks, _estimate_token_count(query) + 600, per_chunk_budget=12000)
    tutor_feedback = _format_feedback_item(
        agent="Tutor",
        stage="辅导讲解",
        status="success",
        headline="辅导回答已更新",
        summary="当前问答的正文、图示和参考知识片段已经同步到工作台反馈区。",
        details_md=(agent_state.tutor_response or {}).get("text_explanation", ""),
        structured_data={
            "query": query,
            "reference_count": len(ref_chunks),
            "estimated_input_tokens": budget_info.get("estimated_input_tokens", 0),
            "overflow_applied": budget_info.get("overflow_applied", "direct"),
            "batch_count": budget_info.get("batch_count", 1),
        },
        artifacts={
            "mermaid_src": (agent_state.tutor_response or {}).get("mermaid_src", ""),
            "reference_chunks": budget_info.get("selected_chunks", ref_chunks[:3]),
        },
    )
    agent_state.agent_feedback = [tutor_feedback, *[item for item in agent_state.agent_feedback if item.agent != "Tutor"]]
    session["agent_state"] = agent_state
    _persist_state(user_id, course_id, agent_state, session.get("cold_state"))
    return JSONResponse({
        "tutor_response": agent_state.tutor_response,
        "reference_count": len(ref_chunks),
        "agent_feedback_version": AGENT_FEEDBACK_VERSION,
        "agent_feedback": [item.model_dump() for item in agent_state.agent_feedback],
    })


async def api_ask_tutor_stream(request: Request) -> EventSourceResponse:
    """SSE 流式 Tutor 应答 — 逐 token 推送，先查 ES 知识库再调用 LLM chat_stream。"""
    body = await request.json()
    user_id  = body.get("user_id", "demo_user")
    course_id = body.get("course_id", "data_structures")
    question  = body.get("question", body.get("query", ""))

    # 知识库检索（同步，先于流式推送）
    ref_chunks = _search_knowledge_base(question, top_k=5, course_id=course_id)
    context    = "\n\n---\n\n".join(ref_chunks[:5]) if ref_chunks else "无参考上下文"

    system_prompt = (
        "你是一个耐心、专业的计算机科学助教。请根据提供的参考知识库内容，"
        "用清晰易懂的中文解答学生的问题。你的回答应包含：\n"
        "1. 核心概念解释（用通俗语言）\n"
        "2. 关键步骤或原理拆解\n"
        "3. 一个简单的例子或类比帮助理解\n"
        "请使用 Markdown 格式，结构清晰、层次分明。"
    )
    user_prompt = (
        f"学生提问: {question}\n\n"
        f"参考知识库内容:\n{context}\n\n"
        f"请根据以上参考资料，为学生提供详细的学术原理解答。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    async def event_generator():
        llm = _get_llm()
        full_text = []

        if llm is None:
            # LLM 不可用 — 直接把 ES 原文分段推流
            fallback = (
                f"## 关于「{question}」的相关知识点（来自知识库）\n\n"
                f"{context}\n\n"
                "> 提示: LLM 暂不可用，以上为知识库原文。"
            )
            for chunk in [fallback[i:i+80] for i in range(0, len(fallback), 80)]:
                yield {"event": "token", "data": json.dumps({"token": chunk}, ensure_ascii=False)}
                await asyncio.sleep(0.02)
        else:
            try:
                async for token in llm.chat_stream(messages):
                    if token:
                        full_text.append(token)
                        yield {"event": "token", "data": json.dumps({"token": token}, ensure_ascii=False)}
            except Exception as exc:
                # stream 出错：仍尝试将已收集的部分答案入库，再通知前端
                full_answer = "".join(full_text)
                if full_answer:
                    _schedule_qa_index(question, full_answer, course_id)
                yield {"event": "error", "data": json.dumps({"error": str(exc)}, ensure_ascii=False)}
                return

        # 完整回答入库 + 更新 agent_state
        session = get_or_create_session(user_id, course_id)
        agent_state: AgentState = session["agent_state"]
        full_answer = "".join(full_text)
        agent_state.tutor_response = {"text_explanation": full_answer, "mermaid_src": ""}
        _persist_state(user_id, course_id, agent_state, session.get("cold_state"))

        # 将 Q&A 对异步索引到对应课程的知识库（保留 Task 引用防 GC）
        _schedule_qa_index(question, full_answer, course_id)

        yield {"event": "done", "data": json.dumps({"reference_count": len(ref_chunks)}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


async def api_knowledge_graph(request: Request) -> JSONResponse:
    """获取知识图谱数据（用于前端可视化，可按课程筛选）"""
    course_id = request.query_params.get("course_id", "data_structures")
    nodes, edges = _kg.get_local_graph(course_id)
    return JSONResponse({
        "nodes": [
            {
                "id": n.node_id,
                "title": n.title,
                "difficulty": n.difficulty,
                "estimated_hours": n.estimated_hours,
                "category": n.category,
            }
            for n in nodes
        ],
        "edges": [
            {
                "source": e.source_id,
                "target": e.target_id,
                "dependency_type": e.dependency_type,
                "weight": e.weight,
            }
            for e in edges
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
        _sync_enrollment_progress(user_id, course_id, agent_state)
        _persist_state(user_id, course_id, agent_state, session.get("cold_state"))
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
    principal, error = _access_principal(request)
    if error is not None:
        return error
    user_id = str((principal or {}).get("sub") or "")
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
    principal, error = _access_principal(request)
    if error is not None:
        return error
    user_id = str((principal or {}).get("sub") or "")
    course_id = body.get("course_id", "").strip()

    store = _get_course_store()
    course = store.get_by_id(course_id)
    if not course:
        return JSONResponse({"detail": f"课程 '{course_id}' 不存在"}, status_code=404)

    _get_enrollment_repo().enroll(user_id, course_id) if _get_enrollment_repo() else None

    return JSONResponse({
        "status": "enrolled",
        "user_id": user_id,
        "course_id": course_id,
        "course": course.to_api_dict(),
    })


async def api_switch_course(request: Request) -> JSONResponse:
    """POST /api/user/courses/switch — 切换当前活跃课程（body: {user_id, course_id}）。"""
    body = await request.json()
    principal, error = _access_principal(request)
    if error is not None:
        return error
    user_id = str((principal or {}).get("sub") or "")
    course_id = body.get("course_id", "").strip()

    ok = _get_enrollment_repo().switch_course(user_id, course_id) if _get_enrollment_repo() else True
    if not ok:
        return JSONResponse({"detail": f"你尚未注册课程 '{course_id}'"}, status_code=404)

    return JSONResponse({
        "status": "switched",
        "user_id": user_id,
        "course_id": course_id,
        "active_path": [],
        "has_path": False,
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


def _user_value(user: Any, field: str) -> Any:
    if isinstance(user, dict):
        return user.get(field)
    return getattr(user, field, None)


def _user_public_payload(user: Any) -> Dict[str, Any]:
    fields = ("user_id", "email", "role", "display_name", "created_at", "last_login_at")
    payload: Dict[str, Any] = {}
    for field in fields:
        value = _user_value(user, field)
        if value is not None:
            payload[field] = value
    user_id = str(payload.get("user_id") or "")
    if user_id:
        try:
            settings = _get_account_repo().get_settings(user_id)
            email = str(payload.get("email") or "").strip().lower()
            verified_for = str(settings.get("email_verified_for") or "").strip().lower()
            verified = bool(settings.get("email_verified_at") and email and verified_for == email)
            payload["email_verified"] = verified
            payload["email_verified_at"] = settings.get("email_verified_at") if verified else None
        except Exception:
            payload["email_verified"] = False
            payload["email_verified_at"] = None
    return payload


def _trusted_client_host(request: Request) -> str:
    client_host = request.client.host if request.client else "unknown"
    trust_proxy = str(os.environ.get("EDUAGENT_TRUST_PROXY_HEADERS") or "").strip().lower()
    if trust_proxy in {"1", "true", "yes", "on"}:
        forwarded = str(request.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
        return forwarded or client_host
    return client_host


def _device_metadata(request: Request) -> Dict[str, str]:
    user_agent = str(request.headers.get("User-Agent", ""))[:512]
    explicit_name = str(request.headers.get("X-Device-Name", "")).strip()[:160]
    device_name = explicit_name or (user_agent[:120] if user_agent else "Unknown device")
    return {
        "device_name": device_name,
        "user_agent": user_agent,
        "ip_address": _trusted_client_host(request)[:96],
    }


def _create_authenticated_session(user: Any, request: Request) -> Dict[str, str]:
    from src.auth.security import SecurityManager

    user_id = str(_user_value(user, "user_id") or "")
    role = str(_user_value(user, "role") or "STUDENT")
    session_id = uuid.uuid4().hex
    token_pair = SecurityManager.create_token_pair(user_id, role, session_id=session_id)
    _get_account_repo().create_device_session(
        session_id,
        user_id,
        token_pair["refresh_jti"],
        **_device_metadata(request),
        expires_at=refresh_expiry_iso(),
    )
    store_refresh_token(user_id, token_pair["refresh_jti"], session_id)
    return token_pair


def _access_principal(request: Request) -> Tuple[Optional[Dict[str, Any]], Optional[JSONResponse]]:
    """Decode an access token and enforce persistent device revocation."""
    from src.auth.security import SecurityManager

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, JSONResponse(
            {"detail": "缺少认证令牌"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = SecurityManager.decode_token(auth_header[7:])
    except ValueError as exc:
        return None, JSONResponse({"detail": str(exc)}, status_code=401)
    if payload.get("type") != "access" or not payload.get("sub"):
        return None, JSONResponse({"detail": "INVALID_TOKEN_TYPE"}, status_code=401)
    if is_blacklisted(str(payload.get("jti") or "")):
        return None, JSONResponse({"detail": "TOKEN_REVOKED"}, status_code=401)
    session_id = str(payload.get("sid") or "")
    if session_id:
        try:
            active = _get_account_repo().is_device_session_active(session_id, str(payload["sub"]))
        except Exception:
            active = False
        if not active:
            return None, JSONResponse({"detail": "SESSION_REVOKED"}, status_code=401)
        try:
            store, _ = _get_auth()
            user_exists = store.get_by_id(str(payload["sub"])) is not None
        except Exception:
            return None, JSONResponse({"detail": "AUTH_STORAGE_UNAVAILABLE"}, status_code=503)
        if not user_exists:
            return None, JSONResponse({"detail": "USER_NOT_FOUND"}, status_code=401)
    _decision, rollout_error = _app_access_rollout(str(payload.get("sub") or ""), record=False)
    if rollout_error is not None:
        return None, rollout_error
    return payload, None


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

    access_decision, rollout_response = _app_access_rollout(user_id)
    if rollout_response is not None:
        return rollout_response

    try:
        user = store.create_user(user_id, email, password)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=409)

    try:
        token_pair = _create_authenticated_session(user, request)
    except Exception:
        return JSONResponse({"detail": "SESSION_PERSISTENCE_UNAVAILABLE"}, status_code=503)
    return _attach_app_rollout_header(JSONResponse({
        "access_token": token_pair["access_token"],
        "refresh_token": token_pair["refresh_token"],
        "token_type": "bearer",
        "session_id": token_pair["session_id"],
        "user": _user_public_payload(user),
    }), access_decision)


def _auth_login_response(
    payload: Dict[str, Any],
    *,
    status_code: int,
    outcome: str,
    reason: str,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    incr_metric("auth.login_total", outcome=outcome, reason=reason)
    log_event(
        "auth.login.complete",
        level="warning" if outcome == "failure" else "info",
        outcome=outcome,
        reason=reason,
        status_code=status_code,
    )
    return JSONResponse(payload, status_code=status_code, headers=headers)


async def api_auth_login(request: Request) -> JSONResponse:
    """POST /api/auth/login — 用户登录。"""
    try:
        store, captcha = _get_auth()
    except AuthBackendUnavailable:
        incr_metric("auth.login_total", outcome="failure", reason="storage_unavailable")
        raise
    try:
        body = await request.json()
    except Exception:
        return _auth_login_response(
            {"detail": "请求体格式错误"},
            status_code=400,
            outcome="failure",
            reason="invalid_json",
        )

    user_id = body.get("user_id", "").strip()
    password = body.get("password", "")
    captcha_token = body.get("captcha_token", "")
    captcha_answer = body.get("captcha_answer", "")

    if not captcha.verify(captcha_token, captcha_answer):
        return _auth_login_response(
            {"detail": "验证码错误或已过期"},
            status_code=400,
            outcome="failure",
            reason="captcha_rejected",
        )

    if not user_id or not password:
        return _auth_login_response(
            {"detail": "用户名和密码不能为空"},
            status_code=400,
            outcome="failure",
            reason="missing_credentials",
        )

    user = store.verify_login(user_id, password)
    if user is None:
        return _auth_login_response(
            {"detail": "用户名或密码错误"},
            status_code=401,
            outcome="failure",
            reason="invalid_credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_decision, rollout_response = _app_access_rollout(user_id)
    if rollout_response is not None:
        return _auth_login_response(
            {"status": "release_unavailable", "detail": "RELEASE_NOT_AVAILABLE"},
            status_code=403,
            outcome="failure",
            reason="release_holdback",
            headers={"X-EduAgent-Release-Cohort": access_decision.cohort},
        )

    try:
        token_pair = _create_authenticated_session(user, request)
    except Exception:
        return _auth_login_response(
            {"detail": "SESSION_PERSISTENCE_UNAVAILABLE"},
            status_code=503,
            outcome="failure",
            reason="session_persistence_unavailable",
        )

    return _auth_login_response(
        {
            "access_token": token_pair["access_token"],
            "refresh_token": token_pair["refresh_token"],
            "token_type": "bearer",
            "session_id": token_pair["session_id"],
            "user": _user_public_payload(user),
        },
        status_code=200,
        outcome="success",
        reason="authenticated",
        headers={"X-EduAgent-Release-Cohort": access_decision.cohort},
    )


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
    revoked_identity: Tuple[str, str] = ("", "")
    # 将 Access Token 加入黑名单
    if access_token:
        try:
            payload = SecurityManager.decode_token(access_token)
            blacklist_token(payload.get("jti", ""), ttl=900)
            revoked_identity = (str(payload.get("sub") or ""), str(payload.get("sid") or ""))
        except ValueError:
            pass

    # 将 Refresh Token 加入黑名单
    if refresh_token:
        try:
            payload = SecurityManager.decode_token(refresh_token)
            blacklist_token(payload.get("jti", ""), ttl=604800)  # 7天
            revoked_identity = (str(payload.get("sub") or ""), str(payload.get("sid") or ""))
        except ValueError:
            pass

    user_id, session_id = revoked_identity
    if user_id and session_id:
        try:
            _get_account_repo().revoke_device_session(user_id, session_id)
        finally:
            revoke_user_session(user_id, session_id)

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
    session_id = str(payload.get("sid") or "")

    if not user_id or not old_jti or is_blacklisted(old_jti):
        return JSONResponse({"detail": "TOKEN_REVOKED"}, status_code=401)

    access_decision, rollout_response = _app_access_rollout(str(user_id))
    if rollout_response is not None:
        return rollout_response

    # Redis 重放攻击检测
    if is_rotated(old_jti):
        try:
            _get_account_repo().revoke_all_device_sessions(user_id)
        except Exception:
            pass
        revoke_all_user_sessions(user_id)
        return JSONResponse({"detail": "SECURITY_BREACH_REUSE_DETECTED"}, status_code=403)

    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    if user is None:
        return JSONResponse({"detail": "USER_NOT_FOUND"}, status_code=401)
    role = _user_value(user, "role") or "STUDENT"

    account_repo = _get_account_repo()
    if session_id:
        session_record = account_repo.get_device_session(session_id)
        if (
            not session_record
            or session_record.get("user_id") != user_id
            or session_record.get("revoked_at")
        ):
            return JSONResponse({"detail": "SESSION_REVOKED"}, status_code=401)
        if session_record.get("refresh_jti") != old_jti:
            account_repo.revoke_all_device_sessions(user_id)
            revoke_all_user_sessions(user_id)
            return JSONResponse({"detail": "SECURITY_BREACH_REUSE_DETECTED"}, status_code=403)
        if not account_repo.is_device_session_active(session_id, user_id, old_jti):
            return JSONResponse({"detail": "SESSION_REVOKED"}, status_code=401)
    else:
        # Compatibility migration for refresh tokens issued before device
        # sessions were introduced. The next pair is fully managed.
        session_id = uuid.uuid4().hex
        account_repo.create_device_session(
            session_id,
            user_id,
            old_jti,
            **_device_metadata(request),
            expires_at=refresh_expiry_iso(),
        )

    token_pair = SecurityManager.create_token_pair(user_id, role, session_id=session_id)
    rotated = account_repo.rotate_device_session(
        session_id,
        old_jti,
        token_pair["refresh_jti"],
        refresh_expiry_iso(),
    )
    if not rotated:
        account_repo.revoke_all_device_sessions(user_id)
        revoke_all_user_sessions(user_id)
        return JSONResponse({"detail": "SECURITY_BREACH_REUSE_DETECTED"}, status_code=403)

    # The persistent session record is authoritative; Redis is the fast path.
    mark_rotated(old_jti, ttl=604800)
    blacklist_token(old_jti, ttl=604800)
    store_refresh_token(user_id, token_pair["refresh_jti"], session_id)

    user_info = _user_public_payload(user) if user else {}
    return _attach_app_rollout_header(JSONResponse({
        "access_token": token_pair["access_token"],
        "refresh_token": token_pair["refresh_token"],
        "token_type": "bearer",
        "session_id": session_id,
        "user": user_info,
    }), access_decision)


async def api_auth_me(request: Request) -> JSONResponse:
    """GET /api/auth/me — 获取当前用户信息 (需 Bearer Token)。"""
    payload, error = _access_principal(request)
    if error is not None:
        return error

    user_id = payload.get("sub", "") if payload else ""
    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    if user is None:
        return JSONResponse({"detail": "用户不存在"}, status_code=404)

    return JSONResponse(_user_public_payload(user))


def _require_user(request: Request) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[JSONResponse]]:
    payload, error = _access_principal(request)
    if error is not None:
        return None, None, error
    user_id = str((payload or {}).get("sub") or "")
    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    if user is None:
        return None, None, JSONResponse({"detail": "USER_NOT_FOUND"}, status_code=401)
    return user_id, payload, None


def _profile_response(user: Any, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    account = _get_account_repo().get_settings(str(_user_value(user, "user_id") or ""))
    email = str(_user_value(user, "email") or "").strip().lower()
    verified_for = str(account.get("email_verified_for") or "").strip().lower()
    email_verified = bool(account.get("email_verified_at") and email and verified_for == email)
    values = {
        "university": "",
        "major": "",
        "grade": "",
        "learning_goal": "",
        "weekly_study_hours": 6,
        "preferred_resource_style": "textual",
        "preferred_pace": "steady",
        "preferred_practice_intensity": "balanced",
        **(profile or {}),
    }
    return {
        **_user_public_payload(user),
        **values,
        "email_verified": email_verified,
        "email_verified_at": account.get("email_verified_at") if email_verified else None,
        "updated_at": values.get("updated_at") or account.get("updated_at"),
    }


def _normalized_profile_patch(body: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    limits = {
        "university": 256,
        "major": 256,
        "grade": 64,
        "learning_goal": 1000,
    }
    result = dict(current)
    for field, limit in limits.items():
        if field in body:
            value = str(body.get(field) or "").strip()
            if len(value) > limit:
                raise ValueError(f"profile_{field}_too_long")
            result[field] = value
    if "weekly_study_hours" in body:
        value = body.get("weekly_study_hours")
        if isinstance(value, bool):
            raise ValueError("profile_weekly_study_hours_invalid")
        try:
            hours = int(value)
        except (TypeError, ValueError):
            raise ValueError("profile_weekly_study_hours_invalid") from None
        if not 0 <= hours <= 168:
            raise ValueError("profile_weekly_study_hours_invalid")
        result["weekly_study_hours"] = hours
    choices = {
        "preferred_resource_style": {"textual", "code_first", "interactive", "summary_first"},
        "preferred_pace": {"gentle", "steady", "intensive"},
        "preferred_practice_intensity": {"light", "balanced", "intensive"},
    }
    for field, allowed in choices.items():
        if field in body:
            value = str(body.get(field) or "").strip().lower()
            if value not in allowed:
                raise ValueError(f"profile_{field}_invalid")
            result[field] = value
    return result


async def api_user_profile(request: Request) -> JSONResponse:
    user_id, _payload, error = _require_user(request)
    if error is not None:
        return error
    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    profile_repo = _get_profile_repo()
    current = profile_repo.get_by_user_id(user_id) or {}
    if request.method == "GET":
        return JSONResponse(_profile_response(user, current))
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)
    try:
        merged = _normalized_profile_patch(body, current)
        old_email = str(_user_value(user, "email") or "").lower()
        email = str(body.get("email", old_email) or "").strip().lower()
        display_name = str(body.get("display_name", _user_value(user, "display_name") or user_id) or "").strip()
        if len(email) > 256 or "@" not in email:
            raise ValueError("profile_email_invalid")
        if len(display_name) > 128:
            raise ValueError("profile_display_name_too_long")
        email_changed = email != old_email
        if email_changed:
            from src.auth.security import SecurityManager

            current_password = str(body.get("current_password") or "")
            password_hash = str(_user_value(user, "password_hash") or "")
            if (
                not current_password
                or not password_hash
                or not SecurityManager.verify_password(current_password, password_hash)
            ):
                raise ValueError("PROFILE_REAUTHENTICATION_REQUIRED")
            account_repo = _get_account_repo()
            account_repo.clear_email_verification(user_id)
            account_repo.revoke_action_tokens(user_id, "email_verification")
        user = store.update_public_profile(user_id, email=email, display_name=display_name)
        saved = profile_repo.upsert(user_id, merged)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    return JSONResponse(_profile_response(user, saved))


def _settings_response(user_id: str) -> Dict[str, Any]:
    stored = _get_account_repo().get_settings(user_id)
    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    email = str(_user_value(user, "email") or "").strip().lower()
    verified_for = str(stored.get("email_verified_for") or "").strip().lower()
    email_verified = bool(stored.get("email_verified_at") and email and verified_for == email)
    return {
        "preferences": normalize_preferences({}, stored.get("preferences")),
        "privacy": normalize_privacy({}, stored.get("privacy")),
        "email_verified": email_verified,
        "email_verified_at": stored.get("email_verified_at") if email_verified else None,
        "updated_at": stored.get("updated_at"),
    }


async def api_user_settings(request: Request) -> JSONResponse:
    user_id, _payload, error = _require_user(request)
    if error is not None:
        return error
    if request.method == "GET":
        return JSONResponse(_settings_response(user_id))
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)
    current = _settings_response(user_id)
    try:
        preferences = normalize_preferences(body.get("preferences", {}), current["preferences"])
        privacy = normalize_privacy(body.get("privacy", {}), current["privacy"])
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    _get_account_repo().upsert_settings(user_id, preferences=preferences, privacy=privacy)
    return JSONResponse(_settings_response(user_id))


async def api_auth_password_forgot(request: Request) -> JSONResponse:
    """Issue a one-time reset token without exposing whether an email exists."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)
    email = str((body or {}).get("email") or "").strip().lower()
    if "@" not in email or len(email) > 256:
        return JSONResponse({"detail": "邮箱格式无效"}, status_code=400)
    if is_production() and not email_delivery_configured():
        return JSONResponse(
            {"status": "delivery_not_configured", "detail": "delivery_not_configured"},
            status_code=503,
        )

    store, _ = _get_auth()
    user = store.get_by_email(email)
    raw_token = secrets.token_urlsafe(32)
    if user is not None:
        raw_token = issue_action_token(_get_account_repo(), str(_user_value(user, "user_id")), "password_reset", 1800)
        cache_action_token(hash_action_token(raw_token), str(_user_value(user, "user_id")), "password_reset", 1800)
        if email_delivery_configured() and not deliver_action_email(email, "password_reset", raw_token):
            _get_account_repo().revoke_action_tokens(str(_user_value(user, "user_id")), "password_reset")
            log_event(
                "auth.password_reset.delivery_failed",
                level="warning",
                user_id=str(_user_value(user, "user_id")),
            )

    response: Dict[str, Any] = {
        "status": "accepted",
        "message": "如果邮箱已注册，重置说明将发送到该邮箱。",
    }
    if not is_production():
        # Unknown emails receive an indistinguishable but unusable token.
        response["dev_token"] = raw_token
    return JSONResponse(response, status_code=202)


async def api_auth_password_reset(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)
    token = str((body or {}).get("token") or "").strip()
    new_password = str((body or {}).get("new_password") or "")
    if len(new_password) < 8 or len(new_password) > 128:
        return JSONResponse({"detail": "密码需为 8-128 个字符"}, status_code=422)
    account_repo = _get_account_repo()
    user_id = resolve_action_token(account_repo, token, "password_reset")
    if not user_id:
        return JSONResponse({"detail": "RESET_TOKEN_INVALID_OR_EXPIRED"}, status_code=400)
    store, _ = _get_auth()
    if store.get_by_id(user_id) is None:
        return JSONResponse({"detail": "RESET_TOKEN_INVALID_OR_EXPIRED"}, status_code=400)
    try:
        revoke_all_sessions_fail_closed(account_repo, user_id, revoke_all_user_sessions)
    except AccountLifecycleError as exc:
        log_event(
            "auth.password_reset.session_revocation_failed",
            level="error",
            user_id=user_id,
            cleanup_step=exc.step,
        )
        return JSONResponse({"detail": "SESSION_REVOCATION_FAILED"}, status_code=503)

    # Claim the token only after persistent session revocation is verified.
    claimed_user_id = consume_action_token(account_repo, token, "password_reset")
    if claimed_user_id != user_id:
        return JSONResponse({"detail": "RESET_TOKEN_INVALID_OR_EXPIRED"}, status_code=400)
    update_password = getattr(store, "update_password_plaintext", store.update_password)
    try:
        password_updated = bool(update_password(user_id, new_password))
    except Exception:
        log_event("auth.password_reset.update_failed", level="error", user_id=user_id)
        return JSONResponse({"detail": "PASSWORD_RESET_FAILED"}, status_code=503)
    if not password_updated:
        return JSONResponse({"detail": "RESET_TOKEN_INVALID_OR_EXPIRED"}, status_code=400)
    consume_cached_action_token(hash_action_token(token), "password_reset")
    return JSONResponse({"status": "password_reset", "sessions_revoked": True})


async def api_auth_email_verification_request(request: Request) -> JSONResponse:
    user_id, _payload, error = _require_user(request)
    if error is not None:
        return error
    if is_production() and not email_delivery_configured():
        return JSONResponse(
            {"status": "delivery_not_configured", "detail": "delivery_not_configured"},
            status_code=503,
        )
    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    email = str(_user_value(user, "email") or "")
    raw_token = issue_action_token(
        _get_account_repo(),
        user_id,
        "email_verification",
        86400,
        subject=email,
    )
    cache_action_token(hash_action_token(raw_token), user_id, "email_verification", 86400)
    if email_delivery_configured() and not deliver_action_email(email, "email_verification", raw_token):
        _get_account_repo().revoke_action_tokens(user_id, "email_verification")
        return JSONResponse({"status": "delivery_failed", "detail": "delivery_failed"}, status_code=503)
    response: Dict[str, Any] = {"status": "verification_requested"}
    if not is_production():
        response["dev_token"] = raw_token
    return JSONResponse(response, status_code=202)


async def api_auth_email_verify(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "请求体格式错误"}, status_code=400)
    token = str((body or {}).get("token") or "").strip()
    account_repo = _get_account_repo()
    binding = account_repo.get_action_token_binding(
        hash_action_token(token),
        "email_verification",
    )
    store, _ = _get_auth()
    bound_user = store.get_by_id(str((binding or {}).get("user_id") or "")) if binding else None
    bound_email = str(_user_value(bound_user, "email") or "").strip().lower()
    user_id = consume_action_token(
        account_repo,
        token,
        "email_verification",
        subject=bound_email,
    ) if bound_email else None
    if not user_id:
        return JSONResponse({"detail": "VERIFICATION_TOKEN_INVALID_OR_EXPIRED"}, status_code=400)
    consume_cached_action_token(hash_action_token(token), "email_verification")
    state = account_repo.mark_email_verified(user_id, bound_email)
    current_user = store.get_by_id(user_id)
    current_email = str(_user_value(current_user, "email") or "").strip().lower()
    verified = bool(
        state.get("email_verified_at")
        and current_email
        and str(state.get("email_verified_for") or "").strip().lower() == current_email
    )
    return JSONResponse({
        "status": "email_verified" if verified else "email_changed_before_verification",
        "user_id": user_id,
        "email_verified": verified,
        "email_verified_at": state.get("email_verified_at") if verified else None,
    })


async def api_auth_sessions(request: Request) -> JSONResponse:
    user_id, payload, error = _require_user(request)
    if error is not None:
        return error
    current_session_id = str((payload or {}).get("sid") or "")
    repo = _get_account_repo()
    if request.method == "GET":
        sessions_payload = repo.list_device_sessions(user_id)
        for session in sessions_payload:
            session["current"] = bool(current_session_id and session.get("session_id") == current_session_id)
        return JSONResponse({"sessions": sessions_payload, "current_session_id": current_session_id})
    revoked_count = repo.revoke_all_device_sessions(user_id)
    revoke_all_user_sessions(user_id)
    return JSONResponse({"status": "sessions_revoked", "revoked_count": revoked_count})


async def api_auth_session_revoke(request: Request) -> JSONResponse:
    user_id, payload, error = _require_user(request)
    if error is not None:
        return error
    session_id = str(request.path_params.get("session_id") or "").strip()
    if not session_id:
        return JSONResponse({"detail": "SESSION_ID_REQUIRED"}, status_code=400)
    revoked = _get_account_repo().revoke_device_session(user_id, session_id)
    if not revoked:
        return JSONResponse({"detail": "SESSION_NOT_FOUND"}, status_code=404)
    revoke_user_session(user_id, session_id)
    return JSONResponse({
        "status": "session_revoked",
        "session_id": session_id,
        "current_session_revoked": session_id == str((payload or {}).get("sid") or ""),
    })


def _user_state_rows(user_id: str) -> List[Dict[str, Any]]:
    repo = _get_state_repo()
    if repo is not None and hasattr(repo, "list_user_states"):
        try:
            return repo.list_user_states(user_id)
        except Exception:
            pass
    try:
        from src.orchestration_runtime import get_runtime

        runtime = get_runtime()
        user_sessions = getattr(runtime, "_sessions", {}).get(user_id, {})
        return [
            {
                "user_id": user_id,
                "course_id": course_id,
                "state_json": session.agent_state.model_dump(mode="json"),
                "cold_state_json": session.cold_state.model_dump(mode="json") if session.cold_state else None,
                "updated_at": "",
            }
            for course_id, session in user_sessions.items()
        ]
    except Exception:
        return []


def _user_session_rows(user_id: str) -> List[Dict[str, Any]]:
    if _db_available and SessionRepo is not None:
        try:
            return SessionRepo().list_for_user(user_id)
        except Exception:
            pass
    return []


async def api_user_learning_summary(request: Request) -> JSONResponse:
    user_id, _payload, error = _require_user(request)
    if error is not None:
        return error
    summary = build_learning_summary(
        enrollments=_get_enrollment_repo().get_user_enrollments(user_id),
        state_rows=_user_state_rows(user_id),
        session_rows=_user_session_rows(user_id),
        course_store=_get_course_store(),
        node_title=lambda node_id: _get_node_title(node_id, node_id),
    )
    return JSONResponse(summary)


async def api_unenroll_course(request: Request) -> JSONResponse:
    user_id, _payload, error = _require_user(request)
    if error is not None:
        return error
    course_id = str(request.path_params.get("course_id") or "").strip()
    result = _get_enrollment_repo().unenroll(user_id, course_id)
    if not result.get("removed"):
        return JSONResponse({"detail": "ENROLLMENT_NOT_FOUND"}, status_code=404)
    if _db_available and SessionRepo is not None:
        try:
            SessionRepo().set_status(user_id, course_id, "unenrolled")
        except Exception:
            pass
    return JSONResponse({
        "status": "unenrolled",
        "course_id": course_id,
        "active_course": result.get("active_course", ""),
        "remaining_courses": result.get("remaining_courses", []),
    })


def _export_learning_state(row: Dict[str, Any]) -> Dict[str, Any]:
    state = row.get("state_json")
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except json.JSONDecodeError:
            state = {}
    state = state if isinstance(state, dict) else {}
    internal = state.get("internal_state") if isinstance(state.get("internal_state"), dict) else {}
    profile = state.get("dynamic_profile") if isinstance(state.get("dynamic_profile"), dict) else {}
    return {
        "course_id": row.get("course_id"),
        "updated_at": row.get("updated_at"),
        "current_node_id": state.get("current_node_id"),
        "active_path": state.get("active_path") or [],
        "knowledge_mastery": profile.get("knowledge_mastery") or {},
        "learning_events": internal.get("learning_events") or [],
        "mastery_attributions": internal.get("mastery_attributions") or [],
        "learning_assets": internal.get("learning_assets") or {},
    }


async def api_user_export(request: Request) -> Response:
    user_id, _payload, error = _require_user(request)
    if error is not None:
        return error
    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    export_payload = {
        "export_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": _user_public_payload(user),
        "profile": _profile_response(user, _get_profile_repo().get_by_user_id(user_id) or {}),
        "settings": _settings_response(user_id),
        "enrollments": _get_enrollment_repo().get_user_enrollments(user_id),
        "learning": [_export_learning_state(row) for row in _user_state_rows(user_id)],
    }
    content = json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="eduagent-{user_id}-export.json"',
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )


async def api_user_delete_account(request: Request) -> JSONResponse:
    user_id, payload, error = _require_user(request)
    if error is not None:
        return error
    try:
        body = await request.json()
    except Exception:
        body = {}
    confirmation = str((body or {}).get("confirmation") or "").strip()
    password = str((body or {}).get("password") or "")
    store, _ = _get_auth()
    user = store.get_by_id(user_id)
    password_valid = False
    if password and user is not None:
        from src.auth.security import SecurityManager

        password_hash = str(_user_value(user, "password_hash") or "")
        password_valid = bool(password_hash and SecurityManager.verify_password(password, password_hash))
    if confirmation != "DELETE" or not password_valid:
        return JSONResponse({"detail": "ACCOUNT_DELETION_CONFIRMATION_REQUIRED"}, status_code=422)

    account_repo = _get_account_repo()
    try:
        revoke_all_sessions_fail_closed(account_repo, user_id, revoke_all_user_sessions)
        if payload:
            blacklist_token(str(payload.get("jti") or ""), ttl=900)
    except Exception as exc:
        step = exc.step if isinstance(exc, AccountLifecycleError) else "access_session"
        log_event(
            "auth.account_delete.session_revocation_failed",
            level="error",
            user_id=user_id,
            cleanup_step=step,
        )
        return JSONResponse({"detail": "ACCOUNT_DATA_CLEANUP_FAILED"}, status_code=503)

    def _delete_state_data() -> None:
        state_repo = _get_state_repo()
        if state_repo is not None and hasattr(state_repo, "delete_all"):
            state_repo.delete_all(user_id)

    def _delete_resource_generation_data() -> None:
        # Jobs may carry personalized cache entries and event payloads. Course
        # base cache is intentionally shared and remains after account deletion.
        from src.database.resource_generation_repo import ResourceGenerationRepo

        ResourceGenerationRepo().delete_all(user_id)

    cleanup_steps = []
    if _db_available and SessionSnapshotRepo is not None:
        cleanup_steps.append(("session_snapshots", lambda: SessionSnapshotRepo().delete_all(user_id)))
    if _db_available and SessionRepo is not None:
        cleanup_steps.append(("sessions", lambda: SessionRepo().delete_all(user_id)))
    cleanup_steps.extend([
        ("learning_state", _delete_state_data),
        ("resource_generation", _delete_resource_generation_data),
        ("enrollments", lambda: _get_enrollment_repo().delete_all(user_id)),
        ("profile", lambda: _get_profile_repo().delete(user_id)),
    ])
    if hasattr(store, "delete_domain_data"):
        cleanup_steps.append(("legacy_domain_data", lambda: store.delete_domain_data(user_id)))
    cleanup_steps.extend([
        ("account_data", lambda: account_repo.delete_user_data(user_id)),
        ("session_invariant", lambda: not bool(account_repo.list_device_sessions(user_id))),
    ])
    try:
        run_required_cleanup_steps(cleanup_steps)
    except AccountLifecycleError as exc:
        log_event(
            "auth.account_delete.cleanup_failed",
            level="error",
            user_id=user_id,
            cleanup_step=exc.step,
        )
        return JSONResponse({"detail": "ACCOUNT_DATA_CLEANUP_FAILED"}, status_code=503)

    try:
        identity_deleted = bool(store.delete_user(user_id))
    except Exception:
        try:
            identity_deleted = store.get_by_id(user_id) is None
        except Exception:
            identity_deleted = False
    if not identity_deleted:
        try:
            identity_deleted = store.get_by_id(user_id) is None
        except Exception:
            identity_deleted = False
    if not identity_deleted:
        log_event("auth.account_delete.identity_failed", level="error", user_id=user_id)
        return JSONResponse({"detail": "ACCOUNT_IDENTITY_DELETE_FAILED"}, status_code=503)

    sessions.pop(user_id, None)
    try:
        from src.orchestration_runtime import get_runtime

        runtime = get_runtime()
        if hasattr(runtime, "drop_user_sessions"):
            runtime.drop_user_sessions(user_id)
    except Exception:
        pass
    return JSONResponse({"status": "account_deleted", "user_id": user_id})


# Official route handlers: route -> application service -> response.
# Older implementations above are retained as legacy migration references only.
COMPAT_INTERNAL_HEADERS = {
    "X-EduAgent-Api-Surface": "compat/internal",
    "X-EduAgent-Api-Status": "deprecated",
    "X-EduAgent-Canonical-Api": "/api/sessions",
}

TUTOR_CANONICAL_API = "/api/sessions/{session_id}/tutor"

TUTOR_COMPAT_HEADERS = {
    **COMPAT_INTERNAL_HEADERS,
    "X-EduAgent-Canonical-Api": TUTOR_CANONICAL_API,
}

SESSION_TUTOR_ALIAS_HEADERS = {
    "X-EduAgent-Api-Surface": "alias/bridge",
    "X-EduAgent-Api-Status": "deprecated",
    "X-EduAgent-Canonical-Api": TUTOR_CANONICAL_API,
}


def _compat_json_response(payload: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=COMPAT_INTERNAL_HEADERS)


def _compat_sse_response(generator: Any) -> EventSourceResponse:
    return EventSourceResponse(generator, headers=COMPAT_INTERNAL_HEADERS)


_CLIENT_MASTERY_CLAIM_FIELDS = frozenset({
    "correctness",
    "score",
    "answer_correctness",
    "code_pass_rate",
    "time_spent_ratio",
    "accuracy_rate",
    "duration_ratio",
    "mastery",
    "mastery_delta",
    "mastery_before",
    "mastery_after",
    "knowledge_mastery",
    "evaluated_node_mastery",
    "previous_mastery",
    "effective_correctness",
    # Camel-case legacy clients must not bypass the same rule.
    "codePassRate",
    "timeSpentRatio",
    "accuracyRate",
    "durationRatio",
    "masteryDelta",
    "masteryBefore",
    "masteryAfter",
    "knowledgeMastery",
    "evaluatedNodeMastery",
    "previousMastery",
    "effectiveCorrectness",
})

_CANONICAL_EVENT_FIELD_ALIASES = {
    "event_type": ("event_type", "eventType"),
    "user_id": ("user_id", "userId"),
    "course_id": ("course_id", "courseId"),
    "node_id": ("node_id", "nodeId"),
    "resource_id": ("resource_id", "resourceId"),
    "question_id": ("question_id", "questionId"),
    "duration_ms": ("duration_ms", "durationMs"),
    "attempt_number": ("attempt_number", "attemptNumber"),
    "used_hint": ("used_hint", "usedHint"),
    "result": ("result",),
}


def _without_client_mastery_claims(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep observable evidence while refusing client-computed learning scores."""
    clean = {
        key: value
        for key, value in payload.items()
        if key not in _CLIENT_MASTERY_CLAIM_FIELDS
    }
    result = clean.get("result")
    if isinstance(result, dict):
        clean["result"] = {
            key: value
            for key, value in result.items()
            if key not in _CLIENT_MASTERY_CLAIM_FIELDS
        }
    return clean


def _session_tutor_response(
    user_id: str,
    course_id: str,
    body: Dict[str, Any],
    accept_header: str = "",
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse | EventSourceResponse:
    try:
        tutor_request = TutorRequest.model_validate(body)
    except ValidationError as exc:
        return JSONResponse(
            {
                "status": "invalid_request",
                "blocked": True,
                "validation": {"issues": exc.errors()},
            },
            status_code=422,
            headers=headers,
        )

    wants_stream = tutor_request.stream or "text/event-stream" in accept_header.lower()
    if wants_stream:
        stream_headers = {"X-Accel-Buffering": "no", **(headers or {})}
        return EventSourceResponse(
            tutor_service.stream_tutor(
                user_id,
                course_id,
                tutor_request.question,
                tutor_request=tutor_request,
            ),
            headers=stream_headers,
        )
    result = tutor_service.run_tutor(
        user_id,
        course_id,
        tutor_request.question,
        tutor_request=tutor_request,
    )
    if result.get("status") == "capacity_exceeded":
        return JSONResponse(
            result,
            status_code=503,
            headers={"Retry-After": str(result.get("retry_after") or 1), **(headers or {})},
        )
    return JSONResponse(result, headers=headers)


async def api_reset(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse(session_service.reset_learning_session(
        body.get("user_id", "demo_user"),
        body.get("course_id", "data_structures"),
    ))


async def api_compat_get_state(request: Request) -> JSONResponse:
    return _compat_json_response(session_service.get_learning_state(
        request.query_params.get("user_id", "demo_user"),
        request.query_params.get("course_id", "data_structures"),
    ))


async def api_compat_cold_start_probe(request: Request) -> JSONResponse:
    return _compat_json_response(profile_service.get_probe(
        request.query_params.get("user_id", "demo_user"),
        request.query_params.get("course_id", "data_structures"),
    ))


async def api_compat_cold_start_answer(request: Request) -> JSONResponse:
    body = await request.json()
    return _compat_json_response(profile_service.submit_probe_answer(
        body.get("user_id", "demo_user"),
        body.get("course_id", "data_structures"),
        body.get("answer"),
    ))


async def api_compat_init_path(request: Request) -> JSONResponse:
    body = await request.json()
    return _compat_json_response(session_service.init_path(
        body.get("user_id", "demo_user"),
        body.get("course_id", "data_structures"),
    ))


async def api_compat_run_pipeline_step(request: Request) -> JSONResponse:
    body = _without_client_mastery_claims(await request.json())
    return _compat_json_response(session_service.advance_session(
        body.get("user_id", "demo_user"),
        body.get("course_id", "data_structures"),
        user_input=body.get("tutor_query"),
        behavior=body,
    ))


async def api_compat_stream_pipeline(request: Request) -> EventSourceResponse:
    # Compat/internal bridge. Official advancement should use /api/sessions/{session_id}/advance.
    user_id = request.query_params.get("user_id", "demo_user")
    course_id = request.query_params.get("course_id", "data_structures")
    behavior = {
        "interaction_type": request.query_params.get("interaction_type", "browse_node"),
        "current_node_id": request.query_params.get("current_node_id") or None,
        "tutor_query": request.query_params.get("tutor_query", "") or None,
    }

    async def event_generator():
        yield {
            "event": "compat_notice",
            "data": json.dumps({
                "surface": "compat/internal",
                "canonical_api": "/api/sessions/{session_id}/advance",
            }, ensure_ascii=False),
        }
        result = await asyncio.to_thread(
            session_service.advance_session,
            user_id,
            course_id,
            behavior.get("tutor_query"),
            behavior,
        )
        yield {"event": "done", "data": json.dumps(result, ensure_ascii=False)}

    return _compat_sse_response(event_generator())


# Keep legacy import names on the truthful session-service boundary. The older
# in-module demo handlers above are retained only for historical source context.
api_init_path = api_compat_init_path
api_run_pipeline_step = api_compat_run_pipeline_step
api_run_pipeline_step_v2 = api_compat_run_pipeline_step
api_stream_pipeline = api_compat_stream_pipeline


async def api_compat_ask_tutor(request: Request) -> JSONResponse:
    # Compat/internal bridge. Official tutor traffic should use /api/sessions/{session_id}/tutor.
    body = await request.json()
    body = {**body, "stream": False}
    return _session_tutor_response(
        body.get("user_id", "demo_user"),
        body.get("course_id", "data_structures"),
        body,
        headers=TUTOR_COMPAT_HEADERS,
    )


async def api_compat_ask_tutor_stream(request: Request) -> EventSourceResponse:
    # Compat/internal bridge. Official tutor streaming should use /api/sessions/{session_id}/tutor with stream=true.
    body = await request.json()
    body = {**body, "stream": True}
    return _session_tutor_response(
        body.get("user_id", "demo_user"),
        body.get("course_id", "data_structures"),
        body,
        headers=TUTOR_COMPAT_HEADERS,
    )


async def api_compat_generate_node_resources(request: Request) -> JSONResponse:
    body = await request.json()
    result = await asyncio.to_thread(
        resource_service.generate_current_node_resources,
        body.get("user_id", "demo_user"),
        body.get("course_id", "data_structures"),
        body.get("node_id", ""),
        bool(body.get("force", False)),
        include_legacy=True,
        card_type=body.get("card_type", body.get("cardType")),
    )
    status_code = int(result.pop("status_code", 200))
    return _compat_json_response(result, status_code=status_code)


# Legacy import names are bridges too; only routes below define the supported HTTP surface.
# The historical synchronous five-card generator has been removed from this module:
# resource generation now lives exclusively in src.application.resource_service (async
# jobs) — a direct import of the old handler name resolves to the resource-service bridge.
api_generate_node_resources = api_compat_generate_node_resources
api_ask_tutor = api_compat_ask_tutor
api_ask_tutor_stream = api_compat_ask_tutor_stream

def _session_ids(session_id: str) -> tuple[str, str]:
    if ":" in session_id:
        user_id, course_id = session_id.split(":", 1)
        return user_id or "demo_user", course_id or "data_structures"
    return session_id or "demo_user", "data_structures"


def _event_session_auth_error(request: Request, expected_user_id: str) -> Optional[JSONResponse]:
    """Require the authenticated principal to own the event session."""
    token_payload, error = _access_principal(request)
    if error is not None:
        return error
    if not token_payload or token_payload["sub"] != expected_user_id:
        return JSONResponse({"detail": "SESSION_USER_MISMATCH"}, status_code=403)
    return None


async def api_create_session(request: Request) -> JSONResponse:
    principal, auth_error = _access_principal(request)
    if auth_error is not None:
        return auth_error
    body = await request.json()
    user_id = str((principal or {}).get("sub") or "")
    course_id = body.get("course_id", "data_structures")
    data = session_service.restore_or_create_session(user_id, course_id)
    data["session_id"] = f"{user_id}:{course_id}"
    return JSONResponse(data)


async def api_get_session(request: Request) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    data = session_service.restore_or_create_session(user_id, course_id)
    data["session_id"] = f"{user_id}:{course_id}"
    return JSONResponse(data)


async def api_session_profile_probe(request: Request) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    return JSONResponse(profile_service.get_probe(user_id, course_id))


async def api_session_profile_input(request: Request) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    body = await request.json()
    return JSONResponse(profile_service.submit_probe_answer(user_id, course_id, body.get("answer")))


async def api_session_init_path(request: Request) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    return JSONResponse(session_service.init_path(user_id, course_id))


async def api_session_advance(request: Request) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    body = _without_client_mastery_claims(await request.json())
    return JSONResponse(session_service.advance_session(user_id, course_id, user_input=body.get("tutor_query"), behavior=body))


async def api_session_behavior(request: Request) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    body = _without_client_mastery_claims(await request.json())
    body.setdefault("interaction_type", "browse_node")
    return JSONResponse(session_service.advance_session(user_id, course_id, behavior=body))


def _session_event_response(result: Dict[str, Any]) -> JSONResponse:
    """Translate the service's advisory status code into the HTTP response."""
    payload = dict(result)
    status_code = payload.pop("status_code", 200)
    try:
        status_code = int(status_code)
    except (TypeError, ValueError):
        status_code = 200
    return JSONResponse(payload, status_code=status_code)


async def api_session_events(request: Request) -> JSONResponse:
    """Record one canonical learner event on the authoritative session."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            {
                "status": "invalid_event",
                "blocked": True,
                "reason": "invalid_json",
            },
            status_code=422,
        )

    if not isinstance(body, dict):
        return JSONResponse(
            {
                "status": "invalid_event",
                "blocked": True,
                "reason": "event_payload_must_be_an_object",
            },
            status_code=422,
        )

    missing_fields = [
        field
        for field, aliases in _CANONICAL_EVENT_FIELD_ALIASES.items()
        if not any(alias in body for alias in aliases)
    ]
    if missing_fields:
        return JSONResponse(
            {
                "status": "invalid_event",
                "blocked": True,
                "reason": "missing_canonical_event_fields",
                "missing_fields": missing_fields,
            },
            status_code=422,
        )

    result = session_service.record_learning_event(
        user_id,
        course_id,
        _without_client_mastery_claims(body),
    )
    return _session_event_response(result)


async def api_session_event_history(request: Request) -> JSONResponse:
    """Expose the durable event and mastery-attribution audit trail."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    node_id = request.query_params.get("node_id") or request.query_params.get("nodeId")
    event_id = request.query_params.get("event_id") or request.query_params.get("eventId")
    raw_limit = request.query_params.get("limit", "100")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return JSONResponse(
            {
                "status": "invalid_event_query",
                "blocked": True,
                "reason": "limit_must_be_an_integer",
            },
            status_code=422,
        )

    result = session_service.get_learning_event_history(
        user_id,
        course_id,
        node_id=node_id,
        event_id=event_id,
        limit=limit,
    )
    return _session_event_response(result)


def _asset_categories_from_query(request: Request) -> list[str]:
    """Accept repeated or comma-separated asset category query parameters."""
    raw_values = [
        *request.query_params.getlist("category"),
        *request.query_params.getlist("categories"),
    ]
    categories: list[str] = []
    for raw in raw_values:
        categories.extend(part.strip() for part in raw.split(",") if part.strip())
    return categories


async def api_session_assets_get(request: Request) -> JSONResponse:
    """Return durable UI assets for the authenticated owner of a session."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    result = learning_assets_service.get_learning_assets(
        user_id,
        course_id,
        node_id=request.query_params.get("node_id", request.query_params.get("nodeId", "")),
        resource_id=request.query_params.get("resource_id", request.query_params.get("resourceId", "")),
        categories=_asset_categories_from_query(request) or None,
    )
    return _session_event_response(result)


async def api_session_assets_patch(request: Request) -> JSONResponse:
    """Upsert or delete one bounded, durable UI asset for a session owner."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            {"status": "invalid_asset", "reason": "asset_invalid_json"},
            status_code=422,
        )
    if not isinstance(body, dict):
        return JSONResponse(
            {"status": "invalid_asset", "reason": "asset_payload_must_be_object"},
            status_code=422,
        )
    result = learning_assets_service.patch_learning_asset(
        user_id,
        course_id,
        category=body.get("category"),
        key=body.get("key"),
        value=body.get("value"),
        delete=body.get("delete", False),
        base_revision=body.get("base_revision", body.get("baseRevision")),
    )
    return _session_event_response(result)


async def api_session_review_dashboard(request: Request) -> JSONResponse:
    """Return durable, server-derived review work for the authenticated learner."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    return _session_event_response(review_service.get_review_dashboard(user_id, course_id))


async def api_session_review_start(request: Request) -> JSONResponse:
    """Begin directed remediation for a specific evidence-backed review item."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    result = review_service.start_review_item(
        user_id,
        course_id,
        request.path_params.get("review_item_id", ""),
    )
    return _session_event_response(result)


async def api_session_review_prepare_retest(request: Request) -> JSONResponse:
    """Issue a new server-owned diagnostic quiz after directed practice."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        return JSONResponse(
            {"status": "invalid_request", "detail": "Request body must be an object."},
            status_code=422,
        )
    result = review_service.prepare_review_retest(
        user_id,
        course_id,
        request.path_params.get("review_item_id", ""),
        str(body.get("practice_event_id") or body.get("practiceEventId") or ""),
    )
    return _session_event_response(result)


def _concurrency_environment(name: str, default: int) -> int:
    try:
        return max(1, min(64, int(os.environ.get(name, str(default)))))
    except (TypeError, ValueError):
        return default


_CODE_EXECUTION_CAPACITY = threading.BoundedSemaphore(
    _concurrency_environment("EDUAGENT_CODE_MAX_CONCURRENT", 2)
)
_CODE_EXECUTION_USER_CAPACITY = KeyedConcurrencyLimiter(1)
def _capacity_response(surface: str) -> JSONResponse:
    incr_metric("runtime.capacity_reject_total", surface=surface)
    return JSONResponse(
        {"status": "capacity_exceeded", "detail": f"{surface.upper()}_CAPACITY_EXCEEDED"},
        status_code=503,
        headers={"Retry-After": "1", "Cache-Control": "no-store"},
    )


def _app_access_rollout(
    user_id: str,
    *,
    record: bool = True,
) -> tuple[RolloutDecision, Optional[JSONResponse]]:
    default_percent = 0.0 if is_production() else 100.0
    decision = rollout_decision("app_access", user_id, default_percent=default_percent)
    if record:
        incr_metric(
            "release.rollout_decision_total",
            feature="app_access",
            cohort=decision.cohort,
        )
    if decision.enabled:
        return decision, None
    response = JSONResponse(
        {"status": "release_unavailable", "detail": "RELEASE_NOT_AVAILABLE"},
        status_code=403,
    )
    response.headers["X-EduAgent-Release-Cohort"] = decision.cohort
    return decision, response


def _attach_app_rollout_header(response: JSONResponse, decision: RolloutDecision) -> JSONResponse:
    response.headers["X-EduAgent-Release-Cohort"] = decision.cohort
    return response


def _code_practice_rollout(user_id: str) -> tuple[RolloutDecision, Optional[JSONResponse]]:
    default_percent = 0.0 if is_production() else 100.0
    decision = rollout_decision("code_practice", user_id, default_percent=default_percent)
    incr_metric(
        "release.rollout_decision_total",
        feature="code_practice",
        cohort=decision.cohort,
    )
    if decision.enabled:
        return decision, None
    response = JSONResponse(
        {"status": "feature_unavailable", "feature": "code_practice"},
        status_code=404,
    )
    response.headers["X-EduAgent-Feature-Cohort"] = decision.cohort
    return decision, response


def _resource_generation_rollout(user_id: str) -> RolloutDecision:
    """Assign the durable job/SSE surface to a stable learner cohort."""
    default_percent = 0.0 if is_production() else 100.0
    decision = rollout_decision(
        "resource_generation",
        user_id,
        default_percent=default_percent,
    )
    incr_metric(
        "release.rollout_decision_total",
        feature="resource_generation",
        cohort=decision.cohort,
    )
    return decision


def _attach_rollout_header(response: JSONResponse, decision: RolloutDecision) -> JSONResponse:
    response.headers["X-EduAgent-Feature-Cohort"] = decision.cohort
    return response


def _code_execution_outcome(result: Dict[str, Any]) -> tuple[str, str]:
    status = str(result.get("status") or "internal_error")
    verdict = str(result.get("verdict") or status)
    if status == "ok" and verdict == "accepted":
        return "accepted", verdict
    if status == "sandbox_unavailable" or verdict in {"sandbox_unavailable", "internal_error"}:
        return "infrastructure_failure", verdict
    if status == "ok":
        return "test_failed", verdict
    return "invalid_request", verdict


def _practice_response(result: Dict[str, Any], *, mode: str = "") -> JSONResponse:
    """Map practice-service states to intentional public HTTP responses."""
    status = str(result.get("status") or "internal_error")
    status_code = {
        "ok": 200,
        "invalid_request": 422,
        "sandbox_unavailable": 503,
        "practice_resource_not_found": 404,
        "practice_problem_not_configured": 404,
        "practice_problem_not_bound_to_session": 404,
        "practice_problem_not_found": 404,
        "practice_problem_version_unavailable": 409,
        "practice_problem_version_invalid": 422,
        "practice_problem_resource_mismatch": 422,
        "practice_resource_id_required": 422,
        "practice_code_required": 422,
        "practice_code_too_large": 413,
        "practice_language_unsupported": 422,
        "client_test_data_forbidden": 422,
    }.get(status, 500)
    if mode:
        outcome, verdict = _code_execution_outcome(result)
        incr_metric(
            "code.execution_total",
            mode=mode,
            outcome=outcome,
            verdict=verdict,
        )
        runtime_ms = result.get("runtime_ms")
        if isinstance(runtime_ms, (int, float)) and not isinstance(runtime_ms, bool):
            observe_metric("code.execution.duration_ms", max(0.0, float(runtime_ms)), mode=mode)
    return JSONResponse(result, status_code=status_code)


async def api_session_practice_problem(request: Request) -> JSONResponse:
    """Return a redacted, session-bound coding-practice specification."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    decision, rollout_response = _code_practice_rollout(user_id)
    if rollout_response is not None:
        return rollout_response
    problem_or_resource_id = request.path_params.get("problem_or_resource_id", "")
    session = get_session(user_id, course_id)
    result = code_practice_service.get_practice_problem(
        session.agent_state,
        problem_or_resource_id,
    )
    # Resolving a legacy code card can safely add its server-owned binding.
    persist_session(session)
    return _attach_rollout_header(_practice_response(result), decision)


async def _api_session_practice_execute(request: Request, mode: str) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    decision, rollout_response = _code_practice_rollout(user_id)
    if rollout_response is not None:
        return rollout_response
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _attach_rollout_header(
            _practice_response(
                {"status": "invalid_request", "reason": "practice_invalid_json"},
                mode=mode,
            ),
            decision,
        )
    if not isinstance(body, dict):
        return _attach_rollout_header(
            _practice_response(
                {"status": "invalid_request", "reason": "practice_payload_must_be_object"},
                mode=mode,
            ),
            decision,
        )
    if any(key in body for key in ("tests", "test_cases", "testCases", "expected", "answer", "reference_solution")):
        return _attach_rollout_header(
            _practice_response({"status": "client_test_data_forbidden"}, mode=mode),
            decision,
        )

    global_acquired = _CODE_EXECUTION_CAPACITY.acquire(blocking=False)
    user_acquired = global_acquired and _CODE_EXECUTION_USER_CAPACITY.acquire(user_id)
    if not global_acquired or not user_acquired:
        if global_acquired:
            _CODE_EXECUTION_CAPACITY.release()
        incr_metric(
            "code.execution_total",
            mode=mode,
            outcome="infrastructure_failure",
            verdict="capacity_exceeded",
        )
        return _attach_rollout_header(_capacity_response("code_execution"), decision)

    session = get_session(user_id, course_id)
    try:
        try:
            result = await asyncio.to_thread(
                code_practice_service.execute_practice,
                session.agent_state,
                user_id=user_id,
                course_id=course_id,
                resource_id=body.get("resource_id", body.get("resourceId", "")),
                problem_id=body.get("problem_id", body.get("problemId", "")),
                language=body.get("language", "python"),
                source_code=body.get("code", ""),
                mode=mode,
            )
        except Exception as exc:
            incr_metric(
                "code.execution_total",
                mode=mode,
                outcome="infrastructure_failure",
                verdict="exception",
            )
            log_event("code.execution.failed", level="error", mode=mode, error_type=type(exc).__name__)
            raise
    finally:
        _CODE_EXECUTION_USER_CAPACITY.release(user_id)
        _CODE_EXECUTION_CAPACITY.release()
    # Submission receipts and lazy resource bindings are server state, not
    # browser state, and must survive a refresh before the event is reported.
    persist_session(session)
    return _attach_rollout_header(_practice_response(result, mode=mode), decision)


async def api_session_practice_run(request: Request) -> JSONResponse:
    return await _api_session_practice_execute(request, "run")


async def api_session_practice_submit(request: Request) -> JSONResponse:
    return await _api_session_practice_execute(request, "submit")


async def api_session_tutor(request: Request):
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    body = await request.json()
    return _session_tutor_response(user_id, course_id, body, request.headers.get("accept", ""))


async def api_session_tutor_stream(request: Request) -> EventSourceResponse | JSONResponse:
    # Short-term alias only; canonical streaming is /api/sessions/{session_id}/tutor.
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    body = await request.json()
    body = {**body, "stream": True}
    return _session_tutor_response(
        user_id,
        course_id,
        body,
        headers=SESSION_TUTOR_ALIAS_HEADERS,
    )


async def api_session_replan(request: Request) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    body = await request.json()
    return JSONResponse(session_service.request_replan(user_id, course_id, payload=body))


async def api_session_resources(request: Request) -> JSONResponse:
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    node_id = request.path_params.get("node_id", "")
    card_type = request.query_params.get("card_type") or request.query_params.get("cardType")
    started = time.perf_counter()
    try:
        result = await asyncio.to_thread(
            resource_service.get_node_resources,
            user_id,
            course_id,
            node_id,
            card_types=[card_type] if card_type else None,
        )
    except Exception as exc:
        incr_metric("resource.read_total", outcome="failure")
        log_event("resource.read.failed", level="error", error_type=type(exc).__name__)
        raise
    status_code = int(result.pop("status_code", 200))
    observe_metric("resource.read.duration_ms", round((time.perf_counter() - started) * 1000, 3))
    incr_metric("resource.read_total", outcome="failure" if status_code >= 400 else "success")
    return JSONResponse(result, status_code=status_code)


async def api_session_resource_generation(request: Request) -> JSONResponse:
    """Create or join a background generation job; never wait for model work."""
    user_id, course_id = _session_ids(request.path_params.get("session_id", ""))
    auth_error = _event_session_auth_error(request, user_id)
    if auth_error is not None:
        return auth_error
    node_id = request.path_params.get("node_id", "")
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"detail": "INVALID_GENERATION_REQUEST"}, status_code=422)
    if not isinstance(body, dict):
        return JSONResponse({"detail": "INVALID_GENERATION_REQUEST"}, status_code=422)
    raw_types = body.get("card_types", body.get("cardTypes", body.get("card_type", body.get("cardType", []))))
    if isinstance(raw_types, str):
        card_types = [raw_types]
    elif isinstance(raw_types, list):
        card_types = raw_types
    else:
        return JSONResponse({"detail": "INVALID_CARD_TYPES"}, status_code=422)
    force = body.get("force", False)
    if not isinstance(force, bool):
        return JSONResponse({"detail": "INVALID_FORCE"}, status_code=422)

    # The read boundary remains available to every cohort so a holdback user
    # can still render a previously cached concept map.  Do not revive the
    # synchronous compatibility generator here: a disabled cohort is strictly
    # cache-only until it is admitted to the durable-job rollout.
    rollout = _resource_generation_rollout(user_id)
    if not rollout.enabled:
        cached = await asyncio.to_thread(
            resource_service.get_node_resources,
            user_id,
            course_id,
            node_id,
            card_types=card_types,
        )
        cached_status = int(cached.pop("status_code", 200))
        resources = list(cached.get("resources") or [])
        response = JSONResponse(
            {
                "job_id": None,
                "status": "rollout_holdback",
                "task_status": "rollout_holdback",
                "generation_available": False,
                "feature": "resource_generation",
                "existing_resources": resources,
                "resources": resources,
                "missing_card_types": list(cached.get("missing_card_types") or card_types),
                "requested_card_types": card_types,
                "node_id": node_id,
                "created": False,
            },
            status_code=cached_status,
            headers={"Cache-Control": "no-store"},
        )
        incr_metric("resource.generation_rollout_holdback_total", cohort=rollout.cohort)
        return _attach_rollout_header(response, rollout)

    started = time.perf_counter()
    result = await asyncio.to_thread(
        resource_service.request_generation,
        user_id,
        course_id,
        node_id,
        card_types=card_types,
        force=force,
        priority=str(body.get("priority") or "normal"),
    )
    status_code = int(result.pop("status_code", 200))
    observe_metric("resource.generation_request.duration_ms", round((time.perf_counter() - started) * 1000, 3))
    outcome = "failure" if status_code >= 400 else "success"
    incr_metric("resource.generation_request_total", outcome=outcome)
    # Keep the launch aggregate continuous while generation moves off the
    # request thread. This measures whether a generation request was accepted;
    # card-level outcomes remain available through the job event stream.
    incr_metric(
        "resource.generate_total",
        outcome=outcome,
        card_type=card_types[0] if len(card_types) == 1 else "bundle",
    )
    return _attach_rollout_header(JSONResponse(result, status_code=status_code), rollout)


async def api_resource_generation_events(request: Request) -> EventSourceResponse | JSONResponse:
    """Replay durable job events and wait for later cards for reconnecting clients."""
    job_id = str(request.path_params.get("job_id", "")).strip()
    principal, auth_error = _access_principal(request)
    if auth_error is not None:
        return auth_error
    user_id = str((principal or {}).get("sub") or "")
    rollout = _resource_generation_rollout(user_id)
    if not rollout.enabled:
        incr_metric("resource.generation_rollout_holdback_total", cohort=rollout.cohort)
        return _attach_rollout_header(
            JSONResponse(
                {"detail": "RESOURCE_GENERATION_ROLLOUT_HOLDBACK", "feature": "resource_generation"},
                status_code=404,
                headers={"Cache-Control": "no-store"},
            ),
            rollout,
        )
    job = await asyncio.to_thread(resource_service.get_generation_job, job_id)
    if job is None:
        return JSONResponse({"detail": "RESOURCE_GENERATION_JOB_NOT_FOUND"}, status_code=404)
    if str(job.get("user_id") or "") != user_id:
        return JSONResponse({"detail": "RESOURCE_GENERATION_JOB_FORBIDDEN"}, status_code=403)
    try:
        after_event_id = int(request.headers.get("last-event-id") or request.query_params.get("after") or 0)
    except (TypeError, ValueError):
        after_event_id = 0

    async def event_generator():
        cursor = max(0, after_event_id)
        terminal_statuses = {"completed", "failed", "cancelled"}
        final_pass = False
        while True:
            events = await asyncio.to_thread(
                resource_service.list_generation_events,
                job_id,
                after_event_id=cursor,
                user_id=user_id,
            )
            for event in events:
                event_id = int(event.get("event_id") or cursor)
                cursor = max(cursor, event_id)
                event_type = str(event.get("event_type") or event.get("event") or "message")
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                yield {
                    "id": str(event_id),
                    "event": event_type,
                    "data": json.dumps(payload, ensure_ascii=False),
                }
                if event_type in {"completed", "failed"}:
                    return
            if final_pass:
                return
            latest = await asyncio.to_thread(resource_service.get_generation_job, job_id, user_id=user_id)
            if latest is None:
                return
            if str(latest.get("status") or "") in terminal_statuses:
                # The job can reach a terminal status between the event read
                # above and this status read. Returning here would silently
                # drop the card_ready/terminal events appended inside that
                # window, so run exactly one more replay pass before closing.
                final_pass = True
                continue
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.25)

    return EventSourceResponse(
        event_generator(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_CLIENT_TELEMETRY_SURFACES = frozenset({"app", "auth", "learn", "other"})
_CLIENT_EXCEPTION_KINDS = frozenset({"api", "bootstrap", "unhandled_rejection", "vue", "window"})
_CLIENT_RECOVERY_OUTCOMES = frozenset({"failure", "success"})
_CLIENT_RESOURCE_CACHE_READ_OUTCOMES = frozenset({"failure", "success"})
_CLIENT_RESOURCE_CONCEPT_READY_OUTCOMES = frozenset({"success"})


def _ops_token_matches(request: Request) -> bool:
    expected = str(os.environ.get("EDUAGENT_OPS_TOKEN") or "").strip()
    if not expected:
        return False
    authorization = str(request.headers.get("authorization") or "")
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    candidate = str(request.headers.get("x-eduagent-ops-token") or bearer).strip()
    return bool(candidate and secrets.compare_digest(candidate, expected))


def _ops_metrics_allowed(request: Request) -> bool:
    if operational_switch("public_metrics", default=not is_production()):
        return True
    return _ops_token_matches(request)


async def api_ops_client_event(request: Request) -> JSONResponse:
    raw_length = request.headers.get("content-length")
    try:
        content_length = int(raw_length) if raw_length else 0
    except (TypeError, ValueError):
        content_length = 0
    if content_length > 2048:
        return JSONResponse({"status": "invalid_client_event"}, status_code=413)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"status": "invalid_client_event"}, status_code=422)
    if not isinstance(body, dict):
        return JSONResponse({"status": "invalid_client_event"}, status_code=422)

    event = str(body.get("event") or "").strip()
    surface = str(body.get("surface") or "other").strip().lower()
    if surface not in _CLIENT_TELEMETRY_SURFACES:
        surface = "other"
    authenticated = False
    if is_production():
        principal, auth_error = _access_principal(request)
        authenticated = auth_error is None and bool((principal or {}).get("sub"))
        public_auth_exception = event == "frontend_exception" and surface == "auth"
        if not authenticated and not public_auth_exception:
            return JSONResponse(
                {"status": "authentication_required", "detail": "CLIENT_EVENT_AUTH_REQUIRED"},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
    if event == "client_session_started":
        incr_metric("frontend.session_total", surface=surface)
    elif event == "frontend_exception":
        kind = str(body.get("kind") or "window").strip().lower()
        if kind not in _CLIENT_EXCEPTION_KINDS:
            kind = "window"
        metric_name = (
            "frontend.exception_total"
            if authenticated or not is_production()
            else "frontend.auth_public_exception_total"
        )
        incr_metric(metric_name, surface=surface, kind=kind)
    elif event == "refresh_recovery":
        outcome = str(body.get("outcome") or "").strip().lower()
        if outcome not in _CLIENT_RECOVERY_OUTCOMES:
            return JSONResponse({"status": "invalid_client_event"}, status_code=422)
        incr_metric("frontend.refresh_recovery_total", surface=surface, outcome=outcome)
    elif event == "next_task_ready":
        duration_ms = body.get("duration_ms")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, (int, float))
            or not 0 <= float(duration_ms) <= 600_000
        ):
            return JSONResponse({"status": "invalid_client_event"}, status_code=422)
        duration_ms = float(duration_ms)
        outcome = "within_5s" if duration_ms <= 5000 else "over_5s"
        incr_metric("frontend.next_task_ready_total", surface=surface, outcome=outcome)
        observe_metric("frontend.next_task_ready_ms", duration_ms, surface=surface)
    elif event in {"resource_cache_read", "resource_concept_ready"}:
        duration_ms = body.get("duration_ms")
        cache_hit = body.get("cache_hit")
        outcome = str(body.get("outcome") or "").strip().lower()
        allowed_outcomes = (
            _CLIENT_RESOURCE_CACHE_READ_OUTCOMES
            if event == "resource_cache_read"
            else _CLIENT_RESOURCE_CONCEPT_READY_OUTCOMES
        )
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 <= duration_ms <= 600_000
            or not isinstance(cache_hit, bool)
            or outcome not in allowed_outcomes
        ):
            return JSONResponse({"status": "invalid_client_event"}, status_code=422)
        metric_prefix = f"frontend.{event}"
        labels = {
            "surface": surface,
            "cache_hit": "true" if cache_hit else "false",
            "outcome": outcome,
        }
        incr_metric(f"{metric_prefix}_total", **labels)
        observe_metric(f"{metric_prefix}_ms", float(duration_ms), **labels)
    else:
        return JSONResponse({"status": "unsupported_client_event"}, status_code=422)
    return JSONResponse({"status": "accepted"}, status_code=202)


async def api_ops_metrics(request: Request) -> JSONResponse:
    if not _ops_metrics_allowed(request):
        return JSONResponse({"detail": "NOT_FOUND"}, status_code=404)
    return JSONResponse(metrics_snapshot(), headers={"Cache-Control": "no-store"})


def _production_readiness_status() -> tuple[bool, str]:
    if not is_production():
        return True, "development"
    required_environment = ("PUBLIC_APP_URL", "EDUAGENT_OPS_TOKEN")
    if any(not str(os.environ.get(name) or "").strip() for name in required_environment):
        return False, "configuration"
    try:
        validate_security_configuration()
    except Exception:
        return False, "configuration"
    if not _db_available or _db is None:
        return False, "postgres"
    try:
        row = _db.execute("SELECT 1 AS ready").fetchone()
        if not row:
            return False, "postgres"
        _get_auth()
        _get_account_repo()
    except Exception:
        return False, "postgres"
    try:
        if redis_backend_status() != "redis" or not durable_redis_available():
            return False, "redis"
    except Exception:
        return False, "redis"
    return True, "ready"


async def api_readiness(request: Request) -> JSONResponse:
    ready, reason = await asyncio.to_thread(_production_readiness_status)
    incr_metric("runtime.readiness_total", outcome="ready" if ready else "not_ready", reason=reason)
    if ready:
        return JSONResponse({"status": "ready"}, headers={"Cache-Control": "no-store"})
    log_event("runtime.readiness.failed", level="warning", reason=reason)
    return JSONResponse(
        {"status": "not_ready"},
        status_code=503,
        headers={"Cache-Control": "no-store", "Retry-After": "5"},
    )


class SpaStaticFiles(StaticFiles):
    """Serve built assets normally and return the SPA entry for client routes."""

    async def get_response(self, path: str, scope: Any) -> Response:
        try:
            return await super().get_response(path, scope)
        except (HTTPException, OSError) as exc:
            # On Windows, a stale API route with a colon-bearing session id can
            # reach StaticFiles and make os.stat raise WinError 123 instead of
            # Starlette's normal 404. Treat that exactly like a missing path;
            # an API request must never become an SPA/static-files 500.
            status_code = exc.status_code if isinstance(exc, HTTPException) else 404
            request_path = path.replace("\\", "/").lstrip("/")
            is_api_path = request_path.startswith("api/")
            is_asset_request = bool(Path(request_path).suffix)
            is_navigation = scope.get("method") in {"GET", "HEAD"}
            if status_code != 404 or is_api_path or is_asset_request or not is_navigation:
                raise HTTPException(status_code=status_code) from exc
            return await super().get_response("index.html", scope)


async def _auth_backend_unavailable_response(
    request: Request,
    exc: AuthBackendUnavailable,
) -> JSONResponse:
    return JSONResponse(
        {"status": "auth_storage_unavailable", "detail": "AUTH_STORAGE_UNAVAILABLE"},
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


async def _captcha_backend_unavailable_response(
    request: Request,
    exc: CaptchaBackendUnavailable,
) -> JSONResponse:
    return JSONResponse(
        {"status": "auth_storage_unavailable", "detail": "AUTH_STORAGE_UNAVAILABLE"},
        status_code=503,
        headers={"Cache-Control": "no-store", "Retry-After": "5"},
    )


_RETIRED_RESOURCE_GENERATION_PATHS = frozenset({
    "/api/resources/generate",
    "/api/resources/generate-all",
})

# ``new_routes`` still exports the historical synchronous agent-chain routes
# for import compatibility.  Never mount them into the application: the
# canonical session API owns resource generation now.
_MOUNTED_NEW_ROUTES = tuple(
    route
    for route in new_routes
    if getattr(route, "path", "") not in _RETIRED_RESOURCE_GENERATION_PATHS
)


async def api_retired_resource_generation(_request: Request) -> JSONResponse:
    """Tombstone historical synchronous resource-generator HTTP paths."""
    return JSONResponse({"detail": "NOT_FOUND"}, status_code=404, headers={"Cache-Control": "no-store"})


app = Starlette(
    debug=not is_production(),
    exception_handlers={
        AuthBackendUnavailable: _auth_backend_unavailable_response,
        CaptchaBackendUnavailable: _captcha_backend_unavailable_response,
    },
    routes=[
        # Official session API - main frontend flow.
        Route("/api/sessions", api_create_session, methods=["POST"]),
        Route("/api/sessions/{session_id}", api_get_session, methods=["GET"]),
        Route("/api/sessions/{session_id}/profile-probe", api_session_profile_probe, methods=["GET"]),
        Route("/api/sessions/{session_id}/profile-input", api_session_profile_input, methods=["POST"]),
        Route("/api/sessions/{session_id}/path/init", api_session_init_path, methods=["POST"]),
        Route("/api/sessions/{session_id}/advance", api_session_advance, methods=["POST"]),
        Route("/api/sessions/{session_id}/behavior", api_session_behavior, methods=["POST"]),
        Route("/api/sessions/{session_id}/events", api_session_events, methods=["POST"]),
        Route("/api/sessions/{session_id}/events", api_session_event_history, methods=["GET"]),
        Route("/api/sessions/{session_id}/assets", api_session_assets_get, methods=["GET"]),
        Route("/api/sessions/{session_id}/assets", api_session_assets_patch, methods=["PATCH"]),
        Route("/api/sessions/{session_id}/review", api_session_review_dashboard, methods=["GET"]),
        Route("/api/sessions/{session_id}/review/items/{review_item_id}/start", api_session_review_start, methods=["POST"]),
        Route("/api/sessions/{session_id}/review/items/{review_item_id}/prepare-retest", api_session_review_prepare_retest, methods=["POST"]),
        Route("/api/sessions/{session_id}/practice/problems/{problem_or_resource_id}", api_session_practice_problem, methods=["GET"]),
        Route("/api/sessions/{session_id}/practice/run", api_session_practice_run, methods=["POST"]),
        Route("/api/sessions/{session_id}/practice/submit", api_session_practice_submit, methods=["POST"]),
        Route("/api/sessions/{session_id}/tutor", api_session_tutor, methods=["POST"]),
        # Short-term deprecated alias. Main app and new clients must use /tutor with stream=true or Accept: text/event-stream.
        Route("/api/sessions/{session_id}/tutor-stream", api_session_tutor_stream, methods=["POST"]),
        Route("/api/sessions/{session_id}/replan", api_session_replan, methods=["POST"]),
        Route("/api/sessions/{session_id}/resources/{node_id}/generation", api_session_resource_generation, methods=["POST"]),
        Route("/api/sessions/{session_id}/resources/{node_id}", api_session_resources, methods=["GET"]),
        Route("/api/resource-generation-jobs/{job_id}/events", api_resource_generation_events, methods=["GET"]),

        # Course, user, and shared support APIs used by the main app.
        Route("/api/courses", api_list_courses, methods=["GET"]),
        Route("/api/courses/{course_id}", api_get_course, methods=["GET"]),
        Route("/api/user/courses", api_get_user_courses, methods=["GET"]),
        Route("/api/user/courses/enroll", api_enroll_course, methods=["POST"]),
        Route("/api/user/courses/switch", api_switch_course, methods=["POST"]),
        Route("/api/user/courses/{course_id}", api_unenroll_course, methods=["DELETE"]),
        Route("/api/user/learning-summary", api_user_learning_summary, methods=["GET"]),
        Route("/api/user/profile", api_user_profile, methods=["GET", "PATCH"]),
        Route("/api/user/settings", api_user_settings, methods=["GET", "PATCH"]),
        Route("/api/user/export", api_user_export, methods=["GET"]),
        Route("/api/user/account", api_user_delete_account, methods=["DELETE"]),
        Route("/api/knowledge-graph", api_knowledge_graph, methods=["GET"]),
        Route("/api/ops/client-events", api_ops_client_event, methods=["POST"]),
        Route("/api/ops/metrics", api_ops_metrics, methods=["GET"]),
        Route("/api/ready", api_readiness, methods=["GET"]),
        Route("/api/reset", api_reset, methods=["POST"]),

        # These paths previously reached a second synchronous agent chain.
        # Keep deterministic 404 tombstones so stale callers cannot fall
        # through to the SPA or silently revive that generator.
        Route("/api/resources/generate", api_retired_resource_generation, methods=["POST"]),
        Route("/api/resources/generate-all", api_retired_resource_generation, methods=["POST"]),

        # Compat/internal legacy learning endpoints.
        # Frozen bridge paths for old clients and diagnostics only.
        # Main app code must use /api/sessions/*; compat responses carry X-EduAgent-Api-Surface.
        Route("/api/state", api_compat_get_state, methods=["GET"]),
        Route("/api/cold-start/probe", api_compat_cold_start_probe, methods=["GET"]),
        Route("/api/cold-start/answer", api_compat_cold_start_answer, methods=["POST"]),
        Route("/api/init-path", api_compat_init_path, methods=["POST"]),
        Route("/api/pipeline/step", api_compat_run_pipeline_step, methods=["POST"]),
        Route("/api/pipeline/stream", api_compat_stream_pipeline, methods=["GET"]),
        Route("/api/tutor/ask", api_compat_ask_tutor, methods=["POST"]),
        Route("/api/tutor/ask-stream", api_compat_ask_tutor_stream, methods=["POST"]),
        Route("/api/resources/generate-node", api_compat_generate_node_resources, methods=["POST"]),

        # Auth API.
        Route("/api/auth/captcha", api_auth_captcha, methods=["GET"]),
        Route("/api/auth/captcha-json", api_auth_captcha_json, methods=["GET"]),
        Route("/api/auth/register", api_auth_register, methods=["POST"]),
        Route("/api/auth/login", api_auth_login, methods=["POST"]),
        Route("/api/auth/refresh", api_auth_refresh, methods=["POST"]),
        Route("/api/auth/logout", api_auth_logout, methods=["POST"]),
        Route("/api/auth/me", api_auth_me, methods=["GET"]),
        Route("/api/auth/password/forgot", api_auth_password_forgot, methods=["POST"]),
        Route("/api/auth/password/reset", api_auth_password_reset, methods=["POST"]),
        Route("/api/auth/email-verification/request", api_auth_email_verification_request, methods=["POST"]),
        Route("/api/auth/email-verification/verify", api_auth_email_verify, methods=["POST"]),
        Route("/api/auth/sessions", api_auth_sessions, methods=["GET", "DELETE"]),
        Route("/api/auth/sessions/{session_id}", api_auth_session_revoke, methods=["DELETE"]),

        # Additional API routes merged from backend modules.
        *_MOUNTED_NEW_ROUTES,
        Mount("/", app=SpaStaticFiles(directory=str(static_dir), html=True)),
    ],
)


def _request_surface(path: str) -> str:
    if path.startswith("/api/sessions"):
        return "session_api"
    if path.startswith("/api/"):
        return "api"
    return "static"


_COMPAT_INTERNAL_PATHS = frozenset({
    "/api/reset",
    "/api/state",
    "/api/cold-start/probe",
    "/api/cold-start/answer",
    "/api/init-path",
    "/api/pipeline/step",
    "/api/pipeline/stream",
    "/api/tutor/ask",
    "/api/tutor/ask-stream",
    "/api/resources/generate-node",
}) | frozenset(
    route.path
    for route in _MOUNTED_NEW_ROUTES
    if route.path != "/api/health"
)


def _compat_request_allowed(request: Request) -> bool:
    # The old synchronous resource bridge is retained only for deliberate
    # diagnostics/migrations.  Enabling generic compat APIs must not expose
    # it accidentally.
    if request.url.path == "/api/resources/generate-node" and not operational_switch(
        "legacy_resource_generation",
        default=False,
    ):
        return False
    enabled = operational_switch("compat_api", default=not is_production())
    if not enabled:
        return False
    return not is_production() or _ops_token_matches(request)


_CORE_RATE_LIMITERS: dict[tuple[str, int, int, str, int], RateLimiter] = {}
_CORE_RATE_LIMITERS_LOCK = threading.Lock()


def _positive_int_environment(name: str, default: int, *, maximum: int) -> int:
    try:
        return max(1, min(maximum, int(os.environ.get(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _core_rate_limit_policy(request: Request) -> Optional[tuple[str, int, int]]:
    if not is_production():
        enabled = str(os.environ.get("EDUAGENT_ENABLE_RATE_LIMITS") or "").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return None
    path = request.url.path
    method = request.method.upper()
    policy: Optional[tuple[str, int, int]] = None
    if method == "GET" and path in {"/api/auth/captcha", "/api/auth/captcha-json"}:
        policy = ("captcha", 10, 60)
    elif method == "POST" and path == "/api/auth/login":
        policy = ("login", 20, 60)
    elif method == "POST" and path == "/api/auth/register":
        policy = ("register", 3, 3600)
    elif method == "POST" and path == "/api/auth/refresh":
        policy = ("refresh", 30, 60)
    elif method == "POST" and path == "/api/auth/password/forgot":
        policy = ("password_forgot", 10, 3600)
    elif method == "POST" and path == "/api/auth/password/reset":
        policy = ("password_reset", 10, 3600)
    elif method == "POST" and path == "/api/auth/email-verification/request":
        policy = ("email_verification_request", 3, 3600)
    elif method == "POST" and path == "/api/auth/email-verification/verify":
        policy = ("email_verification_verify", 10, 3600)
    elif method == "POST" and path == "/api/ops/client-events":
        policy = ("client_events", 30, 60)
    elif method == "POST" and path.endswith(("/tutor", "/tutor-stream")):
        policy = ("tutor", 6, 60)
    elif method == "GET" and "/resources/" in path and path.startswith("/api/sessions/"):
        force = request.query_params.get("force", "false").lower() in {"1", "true", "yes"}
        policy = ("resource_force", 2, 300) if force else ("resource", 12, 60)
    elif method == "POST" and path.endswith("/practice/run"):
        policy = ("practice_run", 10, 60)
    elif method == "POST" and path.endswith("/practice/submit"):
        policy = ("practice_submit", 5, 60)
    elif method == "POST" and path.endswith("/replan"):
        policy = ("replan", 6, 300)
    elif method == "POST" and path.endswith("/events") and path.startswith("/api/sessions/"):
        policy = ("learning_events", 120, 60)
    elif method == "PATCH" and path.endswith("/assets") and path.startswith("/api/sessions/"):
        policy = ("learning_assets", 30, 60)
    if policy is None:
        return None
    name, default_requests, default_window = policy
    key = name.upper()
    requests = _positive_int_environment(
        f"EDUAGENT_RATE_LIMIT_{key}_REQUESTS",
        default_requests,
        maximum=100_000,
    )
    window = _positive_int_environment(
        f"EDUAGENT_RATE_LIMIT_{key}_WINDOW_SECONDS",
        default_window,
        maximum=86_400,
    )
    return name, requests, window


def _rate_limit_subject(request: Request) -> str:
    authorization = str(request.headers.get("authorization") or "")
    if authorization.lower().startswith("bearer ") and authorization[7:].strip():
        source = f"token:{authorization[7:].strip()}"
    else:
        source = f"ip:{_trusted_client_host(request)}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _policy_rate_limiter(name: str, requests: int, window: int) -> RateLimiter:
    backend = str(os.environ.get("EDUAGENT_RATE_LIMIT_BACKEND") or "memory").strip().lower()
    redis_client = None
    if backend == "redis":
        redis_client = get_redis()
        if redis_client is None or (is_production() and redis_backend_status() != "redis"):
            raise RateLimitBackendUnavailable("shared rate limiter unavailable")
    elif backend != "memory":
        raise RateLimitBackendUnavailable("invalid rate limiter backend")
    cache_key = (name, requests, window, backend, id(redis_client))
    with _CORE_RATE_LIMITERS_LOCK:
        limiter = _CORE_RATE_LIMITERS.get(cache_key)
        if limiter is None:
            limiter = RateLimiter(
                max_requests=requests,
                window_seconds=window,
                redis_client=redis_client,
                namespace=name,
            )
            _CORE_RATE_LIMITERS[cache_key] = limiter
        return limiter


def _reset_core_rate_limiters() -> None:
    with _CORE_RATE_LIMITERS_LOCK:
        _CORE_RATE_LIMITERS.clear()


def _request_body_limit(request: Request) -> Optional[int]:
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    path = request.url.path
    if path == "/api/ops/client-events":
        return 2 * 1024
    if path.startswith("/api/auth/"):
        return 16 * 1024
    if path.startswith("/api/sessions/") and path.endswith("/events"):
        return 32 * 1024
    if path.startswith("/api/sessions/") and path.endswith(("/tutor", "/tutor-stream")):
        return 64 * 1024
    if path.startswith("/api/sessions/") and "/practice/" in path:
        return 96 * 1024
    if path.startswith("/api/sessions/") and path.endswith("/assets"):
        return 128 * 1024
    return 1024 * 1024


async def _enforce_request_body_limit(request: Request) -> Optional[JSONResponse]:
    limit = _request_body_limit(request)
    if limit is None:
        return None
    raw_length = request.headers.get("content-length")
    if raw_length:
        try:
            if int(raw_length) > limit:
                raise ValueError("body too large")
        except ValueError:
            incr_metric("security.request_body_reject_total", surface=_request_surface(request.url.path))
            return JSONResponse(
                {"status": "invalid_request", "detail": "REQUEST_BODY_TOO_LARGE"},
                status_code=413,
                headers={"Cache-Control": "no-store"},
            )
    body = await request.body()
    if len(body) > limit:
        incr_metric("security.request_body_reject_total", surface=_request_surface(request.url.path))
        return JSONResponse(
            {"status": "invalid_request", "detail": "REQUEST_BODY_TOO_LARGE"},
            status_code=413,
            headers={"Cache-Control": "no-store"},
        )
    return None


def _enforce_core_rate_limit(request: Request) -> Optional[JSONResponse]:
    policy = _core_rate_limit_policy(request)
    if policy is None:
        return None
    name, requests, window = policy
    try:
        decision = _policy_rate_limiter(name, requests, window).check(_rate_limit_subject(request))
    except RateLimitBackendUnavailable:
        incr_metric("security.rate_limit_backend_total", policy=name, outcome="unavailable")
        return JSONResponse(
            {"status": "temporarily_unavailable", "detail": "RATE_LIMIT_BACKEND_UNAVAILABLE"},
            status_code=503,
            headers={"Retry-After": "5", "Cache-Control": "no-store"},
        )
    headers = {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
    }
    request.state.rate_limit_headers = headers
    if decision.allowed:
        return None
    incr_metric("security.rate_limit_total", policy=name, outcome="blocked")
    return JSONResponse(
        {"status": "rate_limited", "detail": "RATE_LIMITED", "policy": name},
        status_code=429,
        headers={**headers, "Retry-After": str(decision.retry_after), "Cache-Control": "no-store"},
    )


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or new_request_id()
        path = request.url.path
        surface = _request_surface(path)
        started = time.perf_counter()

        with bind_context(
            request_id=request_id,
            method=request.method,
            path=path,
            surface=surface,
        ):
            request.state.request_id = request_id
            try:
                rate_limit_response = _enforce_core_rate_limit(request)
                if rate_limit_response is not None:
                    response = rate_limit_response
                else:
                    body_limit_response = await _enforce_request_body_limit(request)
                    if body_limit_response is not None:
                        response = body_limit_response
                    elif path in _COMPAT_INTERNAL_PATHS and not _compat_request_allowed(request):
                        incr_metric("release.internal_surface_block_total", surface="compat_api")
                        response = JSONResponse({"detail": "NOT_FOUND"}, status_code=404)
                    else:
                        response = await call_next(request)
            except Exception as exc:
                duration_ms = round((time.perf_counter() - started) * 1000, 3)
                incr_metric(
                    "http.request_total",
                    method=request.method,
                    surface=surface,
                    status_family="5xx",
                )
                observe_metric(
                    "http.request.duration_ms",
                    duration_ms,
                    method=request.method,
                    surface=surface,
                )
                log_event(
                    "http.request.failed",
                    level="error",
                    status_code=500,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                raise

            response.headers["X-Request-ID"] = request_id
            for header, value in getattr(request.state, "rate_limit_headers", {}).items():
                response.headers.setdefault(header, value)
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            incr_metric(
                "http.request_total",
                method=request.method,
                surface=surface,
                status_family=f"{response.status_code // 100}xx",
            )
            observe_metric(
                "http.request.duration_ms",
                duration_ms,
                method=request.method,
                surface=surface,
            )
            log_event(
                "http.request.complete",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response


app.add_middleware(ObservabilityMiddleware)


async def _preload_services() -> None:
    """异步预加载 ES 知识库，避免首次请求时阻塞。"""
    import asyncio

    async def _warm_es_in_background() -> None:
        try:
            await asyncio.to_thread(_safe_get_es_kb)
        except Exception as exc:
            print(f"[Startup] ES warmup skipped: {exc}")

    async def _recover_resource_jobs_in_background() -> None:
        try:
            recovered = await asyncio.to_thread(resource_service.recover_pending_generation_jobs)
            if recovered:
                log_event("resource.generation.recovered", job_count=len(recovered))
        except Exception as exc:
            log_event(
                "resource.generation.recovery_failed",
                level="warning",
                error_type=type(exc).__name__,
            )

    # 不阻塞应用启动；知识库可用时自动增强，不可用时保持降级链路可用。
    asyncio.create_task(_warm_es_in_background())
    asyncio.create_task(_recover_resource_jobs_in_background())


def _register_startup_handler() -> None:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(_app):
        await _preload_services()
        yield

    if hasattr(app.router, "lifespan_context"):
        app.router.lifespan_context = _lifespan
        return

    app.on_event("startup")(_preload_services)


_register_startup_handler()


if __name__ == "__main__":
    print("=" * 60)
    print("  EduAgent 前后端对接服务器")
    print("  访问: http://localhost:8800")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8800, log_level="info")
