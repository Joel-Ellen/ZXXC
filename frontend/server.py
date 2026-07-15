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


def _safe_heading(text: str, fallback: str) -> str:
    normalized = _strip_markdown(text or fallback)
    return (normalized[:36] or fallback).strip()


def _normalize_text_list(values: List[str], limit: int = 6) -> List[str]:
    items = []
    for value in values:
        cleaned = _strip_markdown(value)
        if cleaned and cleaned not in items:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return items


def _ensure_text(value: Any, fallback: str, max_chars: int = 420) -> str:
    cleaned = _strip_markdown(str(value or ""))
    cleaned = cleaned[:max_chars].strip()
    return cleaned or fallback


def _coerce_text_list(value: Any, limit: int = 8) -> List[str]:
    if isinstance(value, list):
        return _normalize_text_list([str(item) for item in value], limit=limit)
    if isinstance(value, str):
        return _normalize_text_list([value], limit=limit)
    return []


def _ensure_list_floor(items: List[str], defaults: List[str], min_items: int, limit: int = 8) -> List[str]:
    normalized = _normalize_text_list(items, limit=limit)
    for fallback in defaults:
        if len(normalized) >= min_items:
            break
        cleaned = _strip_markdown(fallback)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized[:limit]


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _resource_json_schema(card_type: str) -> Dict[str, Any]:
    common = {
        "render_type": card_type,
        "title": "string",
    }
    if card_type == "concept_map":
        return {
            **common,
            "summary": "string",
            "learning_objectives": ["string"],
            "sections": [{"heading": "string", "body": "string"}],
            "bullets": ["string"],
            "common_misconceptions": ["string"],
            "mermaid_source": "string",
            "review_prompts": ["string"],
        }
    if card_type == "code_snippet":
        return {
            **common,
            "language": "python|javascript|java|cpp|go|sql|text",
            "scenario": "string",
            "prerequisites": ["string"],
            "code": "string",
            "walkthrough_steps": ["string"],
            "explanation": "string",
            "complexity_notes": ["string"],
            "pitfalls": ["string"],
            "experiments": ["string"],
        }
    if card_type == "interactive_exercise":
        return {
            **common,
            "prompt": "string",
            "goal": "string",
            "steps": ["string"],
            "checkpoints": ["string"],
            "hints": ["string"],
            "expected_outcome": "string",
            "solution_outline": "string",
        }
    if card_type == "video_summary":
        return {
            **common,
            "summary": "string",
            "key_points": ["string"],
            "timeline": [{"label": "string", "summary": "string"}],
            "watch_focus": ["string"],
            "review_questions": ["string"],
            "duration_minutes": 12,
            "video_url": None,
        }
    return {
        **common,
        "questions": [{
            "id": "string",
            "prompt": "string",
            "options": ["string", "string", "string", "string"],
            "answer_index": 0,
            "explanation": "string",
            "skill_tag": "string",
            "difficulty": "easy|medium|hard",
        }],
        "pass_threshold": MASTERY_ADVANCE_THRESHOLD,
        "after_quiz_guidance": "string",
    }


def _build_resource_markdown_from_metadata(card_type: str, metadata: Dict[str, Any]) -> str:
    title = metadata.get("title") or card_type
    if card_type == "concept_map":
        return "\n\n".join(
            [
                f"## {title}",
                f"### 总览\n{metadata.get('summary', '')}",
                "### 学习目标\n" + "\n".join(f"- {item}" for item in metadata.get("learning_objectives", [])),
                *[f"### {section.get('heading', '内容')}\n{section.get('body', '')}" for section in metadata.get("sections", [])],
                "### 关键要点\n" + "\n".join(f"- {item}" for item in metadata.get("bullets", [])),
                "### 常见误区\n" + "\n".join(f"- {item}" for item in metadata.get("common_misconceptions", [])),
                "### 复习提示\n" + "\n".join(f"- {item}" for item in metadata.get("review_prompts", [])),
                f"```mermaid\n{metadata.get('mermaid_source', '')}\n```" if metadata.get("mermaid_source") else "",
            ]
        ).strip()
    if card_type == "code_snippet":
        return "\n\n".join(
            [
                f"## {title}",
                f"### 场景\n{metadata.get('scenario', '')}",
                "### 前置知识\n" + "\n".join(f"- {item}" for item in metadata.get("prerequisites", [])),
                f"```{metadata.get('language', 'python')}\n{metadata.get('code', '')}\n```",
                "### 逐步讲解\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(metadata.get("walkthrough_steps", []))),
                f"### 说明\n{metadata.get('explanation', '')}",
                "### 复杂度提示\n" + "\n".join(f"- {item}" for item in metadata.get("complexity_notes", [])),
                "### 常见坑点\n" + "\n".join(f"- {item}" for item in metadata.get("pitfalls", [])),
                "### 延伸实验\n" + "\n".join(f"- {item}" for item in metadata.get("experiments", [])),
            ]
        ).strip()
    if card_type == "interactive_exercise":
        return "\n\n".join(
            [
                f"## {title}",
                f"### 任务目标\n{metadata.get('goal', '')}",
                f"### 任务说明\n{metadata.get('prompt', '')}",
                "### 推荐步骤\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(metadata.get("steps", []))),
                "### 检查点\n" + "\n".join(f"- {item}" for item in metadata.get("checkpoints", [])),
                "### 提示\n" + "\n".join(f"- {item}" for item in metadata.get("hints", [])),
                f"### 预期结果\n{metadata.get('expected_outcome', '')}",
                f"### 参考思路\n{metadata.get('solution_outline', '')}",
            ]
        ).strip()
    if card_type == "video_summary":
        return "\n\n".join(
            [
                f"## {title}",
                f"### 核心总结\n{metadata.get('summary', '')}",
                "### 关键点\n" + "\n".join(f"- {item}" for item in metadata.get("key_points", [])),
                "### 分段提纲\n" + "\n".join(f"- {item.get('label', '片段')}: {item.get('summary', '')}" for item in metadata.get("timeline", [])),
                "### 观看关注点\n" + "\n".join(f"- {item}" for item in metadata.get("watch_focus", [])),
                "### 复习问题\n" + "\n".join(f"- {item}" for item in metadata.get("review_questions", [])),
            ]
        ).strip()
    return "\n\n".join(
        [
            f"## {title}",
            "### 题目列表",
            "\n".join(
                f"{index + 1}. {question.get('prompt', '')}\n"
                + "\n".join(f"   - {option}" for option in question.get("options", []))
                + f"\n   解析: {question.get('explanation', '')}"
                for index, question in enumerate(metadata.get("questions", []))
            ),
            "### 作答建议",
            metadata.get("summary", "先判断考查点，再结合当前节点材料作答。"),
            "### 诊断后建议",
            metadata.get("after_quiz_guidance", ""),
        ]
    ).strip()


def _resource_card_constraints(card_type: str) -> List[str]:
    shared = [
        "内容必须紧扣当前知识点，不要出现与节点无关的泛化解释。",
        "所有字段都要有实际学习价值，不能用空话填充。",
        "输出面向学生，不要解释你自己在做什么。",
    ]
    per_type = {
        "concept_map": [
            "summary 用 3 到 4 句话搭建整体认知框架，必须说明该知识点解决什么问题、核心约束是什么、学习重点在哪里。",
            "sections 至少 4 个，覆盖定义与约束、工作机制、典型应用场景、与前后知识点关系。",
            "每个 section.body 至少 3 句，必须包含具体机制说明或典型例子，不能只写一句定义就结束。",
            "learning_objectives 至少 3 条，每条必须是可验证的行为描述（能做什么，而不是笼统的了解或理解），bullets 至少 5 条。",
            "common_misconceptions 必须是学生真正常犯的错，每条都要说明错在哪里，不是换个说法重复定义。",
            "review_prompts 至少 3 条，且至少 1 条是迁移型问题（把知识点应用到没见过的新场景）。",
            "mermaid_source 必须是可渲染的 graph TD，节点至少 8 个，体现定义→机制→应用→关联的层次。",
        ],
        "code_snippet": [
            "code 必须是真实代码，不能写伪代码、注释占位或省略号。",
            "优先围绕一个真实、可运行、能体现知识点约束的最小实现展开。",
            "walkthrough_steps 逐段解释代码与知识点的映射关系。",
            "walkthrough_steps 至少 4 条，且至少 1 条解释边界处理，至少 1 条解释复杂度来源。",
            "explanation 需要说明为什么这个实现比表面写法更能体现该知识点。",
            "pitfalls 要指出真实实现风险，如边界、复杂度、状态更新顺序。",
            "experiments 至少给出 3 个可以动手修改的方向。",
        ],
        "interactive_exercise": [
            "goal 说明这道练习具体锻炼什么能力。",
            "steps 必须是学生可执行的推进顺序，至少 4 步。",
            "checkpoints 只做自检，不重复 steps。",
            "hints 至少 2 条，并且是逐层提示，不要直接泄露答案。",
            "solution_outline 只给思路骨架，不直接写完整答案。",
            "expected_outcome 要能明确说明学生做完后应该具备什么判断或实现能力。",
        ],
        "video_summary": [
            "summary 要像高质量学习笔记，不要写成宣传文案。",
            "timeline 至少 4 段，要体现讲解节奏，而不是改写 key_points。",
            "key_points 至少 4 条，其中至少 1 条说明该知识点常见易错点。",
            "watch_focus 指出观看时要特别观察的信号。",
            "watch_focus 至少 3 条，review_questions 至少 3 条。",
            "review_questions 必须能用于复述或迁移，不要只问记忆题。",
        ],
        "diagnostic_quiz": [
            "至少生成 3 题，覆盖概念识别、理解判断、应用判断。",
            "每题必须 4 个选项且只有一个正确答案。",
            "至少有 1 题是带情境的小案例判断题，不能全部是定义题。",
            "每题 explanation 必须说明为什么正确，并顺带指出至少一个错误选项错在哪里。",
            "干扰项必须看起来合理，不能出现明显凑数选项。",
            "after_quiz_guidance 要明确低分时先回看哪类资源。",
        ],
    }
    return shared + per_type.get(card_type, [])


def _resource_fewshot_examples(card_type: str) -> List[Dict[str, Any]]:
    samples = {
        "concept_map": [{
            "input": "知识点: 栈及其应用",
            "output": {
                "render_type": "concept_map",
                "title": "栈及其应用",
                "summary": "栈是一种遵循后进先出（LIFO）原则的线性数据结构，核心价值在于天然维护【最近状态优先】这一约束。学习栈的重点不是背 API 列表，而是能识别哪类问题依赖于回退到最近未处理状态，并判断此时用栈比递归或队列更合适。掌握后你应当能从问题描述中直接看出是否需要维护最近未关闭项，而不是靠套模板。",
                "learning_objectives": [
                    "能用自己的话说明 LIFO 约束的含义，并举出至少两个真实场景解释为什么这个顺序是必要的",
                    "能识别一个新问题是否需要维护最近状态，并判断应使用栈而非队列或直接递归",
                    "能在括号匹配、函数调用等场景中手工追踪栈的入栈和出栈过程，验证结果正确性",
                ],
                "sections": [
                    {
                        "heading": "核心定义与约束",
                        "body": "栈是一种只允许在同一端（栈顶）进行插入（push）和删除（pop）操作的线性结构，这个约束意味着后压入的元素总是先被取出，即后进先出（LIFO）。与数组的随机访问不同，栈的访问路径是单一的：只能看到栈顶，无法直接访问底部元素。这种限制看似不便，实际上正是它能天然解决【最近未关闭状态】问题的根本原因——只要逻辑上需要先处理最新的再回到之前的，栈就是最自然的载体。",
                    },
                    {
                        "heading": "工作机制",
                        "body": "操作层面上，push(x) 将元素 x 放到栈顶，时间复杂度 O(1)；pop() 移除并返回栈顶元素，同样是 O(1)；peek() 只读取栈顶而不移除。栈可用数组或链表实现：数组实现需要维护 top 指针，每次 push 后 top 前进，每次 pop 后 top 退后；链表实现则以链表头作为栈顶，push/pop 即链表头插/删。关键要追踪的状态是 top 指针的移动——这个往复运动就是回溯语义的物理载体，理解它比记住 API 名称重要得多。",
                    },
                    {
                        "heading": "典型应用场景",
                        "body": "括号匹配：遇到左括号就 push，遇到右括号时检查栈顶是否匹配对应的左括号，若不匹配或栈空则非法，最终栈空即合法。函数调用栈：每次调用时系统将当前帧（参数、返回地址、局部变量）压栈，被调函数执行完后弹出，保证嵌套调用能正确返回到调用者——递归本质上就是在隐式使用这个栈。逆波兰表达式求值：遇到操作数 push，遇到运算符则 pop 两个操作数计算后把结果 push 回去，最终栈顶即为答案。三种场景的共同模式是：需要记住最近打开但还没有关闭或完成的项。",
                    },
                    {
                        "heading": "与相关知识点的关系",
                        "body": "栈与队列的关键区别在于服务顺序：栈是 LIFO（最近优先），队列是 FIFO（最早优先），选择哪个取决于问题是需要回退还是按到达顺序处理。递归与栈深层等价：任何递归都可用显式栈改写，系统调用栈就是隐式地在做这件事，面试中常要求将递归 DFS 改成迭代版本正是这个原因。在图算法中，DFS 的迭代版直接用栈实现，而 BFS 用队列——这个对比是理解两种遍历顺序差异的最直接入口。",
                    },
                ],
                "bullets": [
                    "LIFO 约束：后压入的先取出——不是限制，是它天然解决回溯问题的来源",
                    "push / pop / peek 均为 O(1)，操作代价极低",
                    "只有栈顶可见，无法随机访问——使用前必须理解这个约束",
                    "适用判断：问题是否需要维护最近未关闭或未处理的状态",
                    "递归与显式栈等价，可互相转换——理解这个等价是进阶的关键",
                ],
                "common_misconceptions": [
                    "认为栈就是受限的数组，忽略了 LIFO 约束正是其解决特定问题的核心机制，而非单纯的功能限制",
                    "括号匹配时只检查相邻括号是否成对，忽视了栈维护的是最近未匹配的开括号，需要 pop 来匹配而不是线性扫描",
                    "把递归程序和显式栈程序视为两种不同思路，实际上递归就是让系统替你维护了一个隐式调用栈",
                ],
                "mermaid_source": "graph TD\nROOT[栈 Stack] --> CONSTRAINT[约束: LIFO 后进先出]\nROOT --> OPS[基本操作]\nROOT --> USE[典型应用]\nROOT --> RELATE[相关概念]\nOPS --> PUSH[push O1]\nOPS --> POP[pop O1]\nOPS --> PEEK[peek O1]\nUSE --> BRACKET[括号匹配]\nUSE --> CALLSTACK[函数调用栈]\nUSE --> EXPR[逆波兰表达式]\nRELATE --> QUEUE[对比队列 FIFO]\nRELATE --> RECURSION[递归等价隐式栈]",
                "review_prompts": [
                    "如果面试官问你如何判断一个字符串的括号是否合法，你的第一反应是什么数据结构？为什么不是队列或直接线性扫描？",
                    "给你一个只有 push/pop/peek/isEmpty 接口的栈，如何用两个栈实现一个队列？",
                    "迁移题：浏览器的前进和后退按钮背后需要维护几个栈？每个栈里存的是什么？当标签页被关闭后这些栈发生了什么？",
                ],
            },
        }],
        "code_snippet": [{
            "input": "知识点: 队列及其应用",
            "output": {
                "render_type": "code_snippet",
                "title": "队列及其应用 代码示例",
                "language": "python",
                "scenario": "用循环数组实现一个队列，突出 FIFO 约束。",
                "prerequisites": ["理解先进先出", "理解数组下标与取模"],
                "code": "class CircularQueue:\n    def __init__(self, capacity: int):\n        self.data = [None] * capacity\n        self.head = 0\n        self.tail = 0\n        self.size = 0\n\n    def enqueue(self, value):\n        if self.size == len(self.data):\n            raise IndexError('full')\n        self.data[self.tail] = value\n        self.tail = (self.tail + 1) % len(self.data)\n        self.size += 1\n\n    def dequeue(self):\n        if self.size == 0:\n            raise IndexError('empty')\n        value = self.data[self.head]\n        self.data[self.head] = None\n        self.head = (self.head + 1) % len(self.data)\n        self.size -= 1\n        return value",
                "walkthrough_steps": ["head 指向当前队首", "tail 指向下一次写入位置", "取模实现循环复用空间"],
                "explanation": "这个实现比直接 list.pop(0) 更能体现队列的真实约束与工程写法。",
                "complexity_notes": ["入队出队均为 O(1)"],
                "pitfalls": ["忘记区分满与空", "没有处理取模边界"],
                "experiments": ["为队列补 peek 方法"],
            },
        }],
        "interactive_exercise": [{
            "input": "知识点: 二叉搜索树",
            "output": {
                "render_type": "interactive_exercise",
                "title": "二叉搜索树 互动练习",
                "prompt": "给定一组插入序列，手动构造 BST 并判断查找路径。",
                "goal": "把 BST 的有序性和查找过程真正关联起来。",
                "steps": ["先逐个插入节点", "画出树结构", "模拟查找路径"],
                "checkpoints": ["是否始终保持左小右大", "是否能解释路径为什么这样走"],
                "hints": ["先从根节点开始比较"],
                "expected_outcome": "能独立根据序列构造 BST 并手推查找。",
                "solution_outline": "抓住比较结果决定向左或向右。",
            },
        }],
        "video_summary": [{
            "input": "知识点: 图的遍历 DFS/BFS",
            "output": {
                "render_type": "video_summary",
                "title": "图的遍历 DFS/BFS 视频摘要",
                "summary": "这段讲解重点区分 DFS 与 BFS 的推进顺序、辅助结构和适用场景。",
                "key_points": ["DFS 更像一路走到底再回退", "BFS 按层推进", "二者的辅助结构不同"],
                "timeline": [
                    {"label": "概念对比", "summary": "先建立两种遍历顺序的整体印象。"},
                    {"label": "结构选择", "summary": "解释为什么 DFS 常配栈，BFS 常配队列。"},
                ],
                "watch_focus": ["关注访问顺序如何变化"],
                "review_questions": ["为什么 BFS 更适合最短层数问题？"],
                "duration_minutes": 10,
                "video_url": None,
            },
        }],
        "diagnostic_quiz": [{
            "input": "知识点: 排序算法基础",
            "output": {
                "render_type": "diagnostic_quiz",
                "title": "排序算法基础 诊断测验",
                "questions": [{
                    "id": "sort-q1",
                    "prompt": "冒泡排序每一轮最稳定保证的结果是什么？",
                    "options": ["一个当前最大元素被放到末尾", "整个序列完全有序", "中位数固定", "最小元素进入首位"],
                    "answer_index": 0,
                    "explanation": "冒泡排序通过相邻交换，把当前最大元素逐轮推到末尾。",
                    "skill_tag": "概念理解",
                    "difficulty": "easy",
                }],
                "pass_threshold": 0.65,
                "after_quiz_guidance": "如果对复杂度和稳定性混淆，先回看排序基础概念图。",
            },
        }],
    }
    return samples.get(card_type, [])


def _infer_code_template(node_id: str, node_title: str) -> Dict[str, Any]:
    normalized = f"{node_id} {node_title}".lower()
    if any(key in normalized for key in ["n02", "线性表", "顺序", "array", "数组"]):
        return {
            "language": "python",
            "scenario": "用顺序表实现插入、删除和按下标访问，突出顺序存储的移动成本。",
            "code": """class SequenceList:\n    def __init__(self):\n        self.data = []\n\n    def insert(self, index: int, value: int) -> None:\n        if index < 0 or index > len(self.data):\n            raise IndexError('index out of range')\n        self.data.append(0)\n        for i in range(len(self.data) - 1, index, -1):\n            self.data[i] = self.data[i - 1]\n        self.data[index] = value\n\n    def delete(self, index: int) -> int:\n        if index < 0 or index >= len(self.data):\n            raise IndexError('index out of range')\n        removed = self.data[index]\n        for i in range(index, len(self.data) - 1):\n            self.data[i] = self.data[i + 1]\n        self.data.pop()\n        return removed\n""",
            "prerequisites": ["理解顺序存储与连续空间", "理解按下标访问"],
            "complexity_notes": ["随机访问 O(1)", "中间插入删除通常需要 O(n) 元素移动"],
            "pitfalls": ["只看到访问快，忽略插入删除成本", "下标边界处理不完整"],
            "experiments": ["补一个查找方法", "比较头插和尾插代价"],
        }
    if any(key in normalized for key in ["n03", "链表", "linked"]):
        return {
            "language": "python",
            "scenario": "实现单链表的头插、尾插和删除，突出节点链接关系。",
            "code": """class ListNode:\n    def __init__(self, value: int, next_node=None):\n        self.value = value\n        self.next = next_node\n\n\nclass SinglyLinkedList:\n    def __init__(self):\n        self.head = None\n\n    def push_front(self, value: int) -> None:\n        self.head = ListNode(value, self.head)\n\n    def append(self, value: int) -> None:\n        new_node = ListNode(value)\n        if self.head is None:\n            self.head = new_node\n            return\n        current = self.head\n        while current.next is not None:\n            current = current.next\n        current.next = new_node\n\n    def remove(self, value: int) -> bool:\n        dummy = ListNode(0, self.head)\n        prev = dummy\n        current = self.head\n        while current is not None:\n            if current.value == value:\n                prev.next = current.next\n                self.head = dummy.next\n                return True\n            prev, current = current, current.next\n        return False\n""",
            "prerequisites": ["理解节点与引用", "理解 head 和 next"],
            "complexity_notes": ["已知前驱时插入删除 O(1)", "按值查找仍需 O(n)"],
            "pitfalls": ["删除头结点时忘记更新 head", "遍历时 next 判空写错"],
            "experiments": ["改成带尾指针链表", "补一个反转链表函数"],
        }
    if any(key in normalized for key in ["n04", "栈", "stack"]):
        return {
            "language": "python",
            "scenario": "用括号匹配示例直接展示栈如何处理最近未闭合状态。",
            "code": """def is_valid_parentheses(text: str) -> bool:\n    pairs = {')': '(', ']': '[', '}': '{'}\n    stack = []\n    for ch in text:\n        if ch in pairs.values():\n            stack.append(ch)\n        elif ch in pairs:\n            if not stack or stack[-1] != pairs[ch]:\n                return False\n            stack.pop()\n    return not stack\n""",
            "prerequisites": ["理解后进先出", "理解字符串遍历和条件判断"],
            "complexity_notes": ["时间复杂度 O(n)", "辅助栈空间最坏 O(n)"],
            "pitfalls": ["忘记处理空栈", "只背代码，不理解为什么匹配最近括号"],
            "experiments": ["输出第一处非法位置", "扩展到多种括号"],
        }
    if any(key in normalized for key in ["n05", "队列", "queue"]):
        return {
            "language": "python",
            "scenario": "用循环数组实现队列，突出 FIFO 约束和空间复用。",
            "code": """class CircularQueue:\n    def __init__(self, capacity: int):\n        self.data = [None] * capacity\n        self.head = 0\n        self.tail = 0\n        self.size = 0\n\n    def enqueue(self, value: int) -> None:\n        if self.size == len(self.data):\n            raise IndexError('queue full')\n        self.data[self.tail] = value\n        self.tail = (self.tail + 1) % len(self.data)\n        self.size += 1\n\n    def dequeue(self) -> int:\n        if self.size == 0:\n            raise IndexError('queue empty')\n        value = self.data[self.head]\n        self.data[self.head] = None\n        self.head = (self.head + 1) % len(self.data)\n        self.size -= 1\n        return value\n""",
            "prerequisites": ["理解先进先出", "理解数组下标和取模"],
            "complexity_notes": ["入队出队均为 O(1)"],
            "pitfalls": ["满与空判断混淆", "head/tail 更新顺序写错"],
            "experiments": ["补 peek 方法", "改成 deque 风格接口"],
        }
    if any(key in normalized for key in ["n06", "树", "二叉树", "binary tree"]):
        return {
            "language": "python",
            "scenario": "用先序遍历帮助理解树结构和左右子树递归分解。",
            "code": """class TreeNode:\n    def __init__(self, value: int, left=None, right=None):\n        self.value = value\n        self.left = left\n        self.right = right\n\n\ndef preorder(root: TreeNode | None) -> list[int]:\n    if root is None:\n        return []\n    return [root.value] + preorder(root.left) + preorder(root.right)\n""",
            "prerequisites": ["理解节点、左右孩子和空子树", "理解递归分解"],
            "complexity_notes": ["遍历每个节点一次，时间复杂度 O(n)"],
            "pitfalls": ["递归出口漏掉", "先序中序后序顺序混淆"],
            "experiments": ["改写中序和后序", "写一个按层遍历版本"],
        }
    if any(key in normalized for key in ["n07", "二叉搜索树", "bst"]):
        return {
            "language": "python",
            "scenario": "实现 BST 查找，突出左小右大如何指导路径选择。",
            "code": """class BSTNode:\n    def __init__(self, value: int, left=None, right=None):\n        self.value = value\n        self.left = left\n        self.right = right\n\n\ndef bst_search(root: BSTNode | None, target: int) -> BSTNode | None:\n    current = root\n    while current is not None:\n        if target == current.value:\n            return current\n        if target < current.value:\n            current = current.left\n        else:\n            current = current.right\n    return None\n""",
            "prerequisites": ["理解二叉树", "理解左小右大有序性"],
            "complexity_notes": ["平均 O(log n)，退化时可到 O(n)"],
            "pitfalls": ["会写比较分支，但解释不清路径原因", "忽略退化树"],
            "experiments": ["补插入操作", "构造退化树看复杂度变化"],
        }
    if any(key in normalized for key in ["n08", "avl", "平衡树"]):
        return {
            "language": "python",
            "scenario": "展示 AVL 的高度更新与平衡因子计算，突出平衡维护基础。",
            "code": """class AVLNode:\n    def __init__(self, value: int, left=None, right=None):\n        self.value = value\n        self.left = left\n        self.right = right\n        self.height = 1\n\n\ndef height(node: AVLNode | None) -> int:\n    return node.height if node else 0\n\n\ndef update_height(node: AVLNode) -> None:\n    node.height = max(height(node.left), height(node.right)) + 1\n\n\ndef balance_factor(node: AVLNode | None) -> int:\n    if node is None:\n        return 0\n    return height(node.left) - height(node.right)\n""",
            "prerequisites": ["理解 BST", "理解树高与平衡因子"],
            "complexity_notes": ["平衡维护目标是把查找保持在 O(log n) 量级"],
            "pitfalls": ["只背 LL/LR/RR/RL 名称", "高度更新顺序错误"],
            "experiments": ["补一个单旋示意函数", "手推一个失衡例子"],
        }
    if any(key in normalized for key in ["n09", "散列", "哈希", "hash"]):
        return {
            "language": "python",
            "scenario": "用链地址法示意哈希表冲突处理，帮助理解桶和冲突。",
            "code": """class ChainedHashTable:\n    def __init__(self, capacity: int = 8):\n        self.buckets = [[] for _ in range(capacity)]\n\n    def _index(self, key: int) -> int:\n        return key % len(self.buckets)\n\n    def put(self, key: int, value: int) -> None:\n        bucket = self.buckets[self._index(key)]\n        for pair in bucket:\n            if pair[0] == key:\n                pair[1] = value\n                return\n        bucket.append([key, value])\n\n    def get(self, key: int):\n        bucket = self.buckets[self._index(key)]\n        for existing_key, value in bucket:\n            if existing_key == key:\n                return value\n        return None\n""",
            "prerequisites": ["理解取模映射", "理解冲突概念"],
            "complexity_notes": ["平均查找接近 O(1)，冲突严重时会退化"],
            "pitfalls": ["把哈希函数和冲突处理混为一谈", "忽略装载因子"],
            "experiments": ["统计桶长度分布", "补删除操作并思考再散列"],
        }
    if any(key in normalized for key in ["n10", "图的基本概念", "图", "存储"]):
        return {
            "language": "python",
            "scenario": "用邻接表表示图，突出顶点、边和邻居关系。",
            "code": """graph = {\n    'A': ['B', 'C'],\n    'B': ['A', 'D'],\n    'C': ['A', 'D'],\n    'D': ['B', 'C']\n}\n\n\ndef neighbors(node: str) -> list[str]:\n    return graph.get(node, [])\n""",
            "prerequisites": ["理解顶点和边", "理解字典与列表"],
            "complexity_notes": ["邻接表更适合稀疏图"],
            "pitfalls": ["无向图忘记双向建边", "不会比较邻接表与邻接矩阵"],
            "experiments": ["把无向图改成有向图", "补邻接矩阵对比"],
        }
    if any(key in normalized for key in ["n11", "dfs", "bfs", "遍历"]):
        return {
            "language": "python",
            "scenario": "用 BFS 实现展示按层推进与队列的关系。",
            "code": """from collections import deque\n\n\ndef bfs(graph: dict[str, list[str]], start: str) -> list[str]:\n    visited = {start}\n    order = []\n    queue = deque([start])\n    while queue:\n        node = queue.popleft()\n        order.append(node)\n        for neighbor in graph.get(node, []):\n            if neighbor not in visited:\n                visited.add(neighbor)\n                queue.append(neighbor)\n    return order\n""",
            "prerequisites": ["理解邻接表", "理解队列和 visited 集合"],
            "complexity_notes": ["使用邻接表时常写为 O(V+E)"],
            "pitfalls": ["忘记 visited", "知道 BFS 用队列但不理解按层推进"],
            "experiments": ["补 DFS 递归版", "记录每个节点层数"],
        }
    if any(key in normalized for key in ["n12", "最小生成树", "mst"]):
        return {
            "language": "python",
            "scenario": "用 Kruskal 核心循环示意最小生成树如何选边。",
            "code": """def kruskal(n: int, edges: list[tuple[int, int, int]]) -> tuple[int, list[tuple[int, int, int]]]:\n    parent = list(range(n))\n\n    def find(x: int) -> int:\n        if parent[x] != x:\n            parent[x] = find(parent[x])\n        return parent[x]\n\n    def union(a: int, b: int) -> bool:\n        ra, rb = find(a), find(b)\n        if ra == rb:\n            return False\n        parent[ra] = rb\n        return True\n\n    total = 0\n    chosen = []\n    for u, v, w in sorted(edges, key=lambda item: item[2]):\n        if union(u, v):\n            total += w\n            chosen.append((u, v, w))\n    return total, chosen\n""",
            "prerequisites": ["理解边权图", "理解并查集思路"],
            "complexity_notes": ["排序是主要开销，常见为 O(E log E)"],
            "pitfalls": ["最小边优先却不检查成环", "并查集作用不清"],
            "experiments": ["手推一组边的选择过程", "比较 Kruskal 和 Prim"],
        }
    if any(key in normalized for key in ["n13", "最短路径", "dijkstra"]):
        return {
            "language": "python",
            "scenario": "用 Dijkstra 展示单源最短路中的贪心扩展与堆优化。",
            "code": """import heapq\n\n\ndef dijkstra(graph: dict[int, list[tuple[int, int]]], start: int) -> dict[int, int]:\n    dist = {start: 0}\n    heap = [(0, start)]\n    while heap:\n        current_dist, node = heapq.heappop(heap)\n        if current_dist > dist.get(node, float('inf')):\n            continue\n        for neighbor, weight in graph.get(node, []):\n            next_dist = current_dist + weight\n            if next_dist < dist.get(neighbor, float('inf')):\n                dist[neighbor] = next_dist\n                heapq.heappush(heap, (next_dist, neighbor))\n    return dist\n""",
            "prerequisites": ["理解邻接表", "理解优先队列和贪心更新"],
            "complexity_notes": ["堆优化常见为 O((V+E) log V)"],
            "pitfalls": ["忘记跳过过期堆项", "在负权边图上误用 Dijkstra"],
            "experiments": ["补路径恢复数组", "对比 Bellman-Ford"],
        }
    if any(key in normalized for key in ["n14", "拓扑", "关键路径"]):
        return {
            "language": "python",
            "scenario": "用 Kahn 算法实现拓扑排序，突出入度和队列。",
            "code": """from collections import deque\n\n\ndef topo_sort(graph: dict[str, list[str]]) -> list[str]:\n    indegree = {node: 0 for node in graph}\n    for node in graph:\n        for neighbor in graph[node]:\n            indegree[neighbor] = indegree.get(neighbor, 0) + 1\n    queue = deque([node for node, deg in indegree.items() if deg == 0])\n    order = []\n    while queue:\n        node = queue.popleft()\n        order.append(node)\n        for neighbor in graph.get(node, []):\n            indegree[neighbor] -= 1\n            if indegree[neighbor] == 0:\n                queue.append(neighbor)\n    return order\n""",
            "prerequisites": ["理解有向无环图", "理解入度统计"],
            "complexity_notes": ["整体常见为 O(V+E)"],
            "pitfalls": ["图有环时结果不完整却没意识到", "忘记初始化所有节点入度"],
            "experiments": ["检测环", "补 earliest 时间数组"],
        }
    if any(key in normalized for key in ["n15", "排序算法基础", "排序"]):
        return {
            "language": "python",
            "scenario": "用插入排序展示局部有序区间如何逐步扩张。",
            "code": """def insertion_sort(nums: list[int]) -> list[int]:\n    arr = nums[:]\n    for i in range(1, len(arr)):\n        key = arr[i]\n        j = i - 1\n        while j >= 0 and arr[j] > key:\n            arr[j + 1] = arr[j]\n            j -= 1\n        arr[j + 1] = key\n    return arr\n""",
            "prerequisites": ["理解数组访问", "理解局部有序区间"],
            "complexity_notes": ["最好 O(n)，最坏 O(n^2)"],
            "pitfalls": ["会背外层循环，不理解内层移动", "稳定性概念含混"],
            "experiments": ["手推每轮有序区间", "比较插入排序和冒泡排序"],
        }
    if any(key in normalized for key in ["n16", "高级排序", "merge", "quick", "heap sort"]):
        return {
            "language": "python",
            "scenario": "用归并排序展示分治、递归拆分和合并过程。",
            "code": """def merge_sort(nums: list[int]) -> list[int]:\n    if len(nums) <= 1:\n        return nums[:]\n    mid = len(nums) // 2\n    left = merge_sort(nums[:mid])\n    right = merge_sort(nums[mid:])\n    merged = []\n    i = j = 0\n    while i < len(left) and j < len(right):\n        if left[i] <= right[j]:\n            merged.append(left[i])\n            i += 1\n        else:\n            merged.append(right[j])\n            j += 1\n    merged.extend(left[i:])\n    merged.extend(right[j:])\n    return merged\n""",
            "prerequisites": ["理解递归", "理解分治和合并"],
            "complexity_notes": ["时间 O(n log n)，空间通常 O(n)"],
            "pitfalls": ["只背复杂度，不理解 merge 线性过程", "递归基和尾段合并易漏"],
            "experiments": ["补快速排序", "追踪一次 merge 的指针变化"],
        }
    if any(key in normalized for key in ["n17", "查找", "索引", "binary search", "二分"]):
        return {
            "language": "python",
            "scenario": "用二分查找展示有序性如何持续缩小搜索区间。",
            "code": """def binary_search(nums: list[int], target: int) -> int:\n    left, right = 0, len(nums) - 1\n    while left <= right:\n        mid = left + (right - left) // 2\n        if nums[mid] == target:\n            return mid\n        if nums[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1\n""",
            "prerequisites": ["理解数组有序性", "理解左右边界区间"],
            "complexity_notes": ["每轮砍半，时间 O(log n)"],
            "pitfalls": ["条件写成 left < right 导致漏判", "忘记前提必须有序"],
            "experiments": ["改写成找左边界", "证明 mid 写法更稳"],
        }
    if any(key in normalized for key in ["n18", "动态规划", "dp"]):
        return {
            "language": "python",
            "scenario": "用爬楼梯问题示意 DP 的状态定义、转移和自底向上求解。",
            "code": """def climb_stairs(n: int) -> int:\n    if n <= 2:\n        return n\n    dp = [0] * (n + 1)\n    dp[1], dp[2] = 1, 2\n    for i in range(3, n + 1):\n        dp[i] = dp[i - 1] + dp[i - 2]\n    return dp[n]\n""",
            "prerequisites": ["理解子问题", "理解数组状态存储"],
            "complexity_notes": ["时间 O(n)，空间 O(n)，还可压缩"],
            "pitfalls": ["只记转移式，不知道状态含义", "把 DP 和暴力递归混淆"],
            "experiments": ["压缩成两个变量", "换成零钱兑换类问题"],
        }
    if any(key in normalized for key in ["n19", "贪心", "回溯"]):
        return {
            "language": "python",
            "scenario": "用子集回溯示例展示选择、递归、撤销选择的基本过程。",
            "code": """def subsets(nums: list[int]) -> list[list[int]]:\n    result = []\n    path = []\n\n    def dfs(index: int) -> None:\n        result.append(path[:])\n        for i in range(index, len(nums)):\n            path.append(nums[i])\n            dfs(i + 1)\n            path.pop()\n\n    dfs(0)\n    return result\n""",
            "prerequisites": ["理解递归栈", "理解路径与状态恢复"],
            "complexity_notes": ["回溯常是指数级搜索，关键在剪枝与状态组织"],
            "pitfalls": ["忘记撤销选择", "把贪心和回溯混为一谈"],
            "experiments": ["给子集问题加去重", "找一个贪心失败而回溯可解的例子"],
        }
    if any(key in normalized for key in ["n20", "综合应用", "project"]):
        return {
            "language": "python",
            "scenario": "用课程依赖图的拓扑排序示意综合应用，把图、队列和入度统计串起来。",
            "code": """from collections import deque\n\n\ndef schedule_courses(graph: dict[str, list[str]]) -> list[str]:\n    indegree = {node: 0 for node in graph}\n    for node in graph:\n        for nxt in graph[node]:\n            indegree[nxt] = indegree.get(nxt, 0) + 1\n    queue = deque([node for node, deg in indegree.items() if deg == 0])\n    order = []\n    while queue:\n        node = queue.popleft()\n        order.append(node)\n        for nxt in graph.get(node, []):\n            indegree[nxt] -= 1\n            if indegree[nxt] == 0:\n                queue.append(nxt)\n    return order\n""",
            "prerequisites": ["理解图、队列、入度统计", "理解综合题约束拆解"],
            "complexity_notes": ["示例整体仍为 O(V+E) 级别"],
            "pitfalls": ["会写局部算法，但不会把多个知识点串起来", "遗漏图中有环这类异常场景"],
            "experiments": ["补一个环检测", "换成任务调度场景"],
        }
    return {
        "language": "python",
        "scenario": f"围绕 {node_title} 给出一个贴近知识点的 Python 示例。",
        "code": f"def explain_{re.sub(r'[^a-zA-Z0-9]', '_', node_id.lower())}(data):\n    return data\n",
        "prerequisites": [f"已理解 {node_title} 的基本定义"],
        "complexity_notes": ["先解释数据流，再补复杂度。"],
        "pitfalls": ["不要只背代码，要能解释为什么这样写。"],
        "experiments": ["尝试加入一个边界 case 并解释结果。"],
    }


def _generate_card_with_qwen(
    node_id: str,
    card_type: str,
    difficulty: float,
    context_chunks: List[str],
    budget_info: Dict[str, Any],
) -> Optional[Tuple[Dict[str, Any], str]]:
    llm = _get_llm()
    if llm is None:
        return None

    node_title = _get_node_title(node_id, node_id)
    schema = _resource_json_schema(card_type)
    constraints = _resource_card_constraints(card_type)
    fewshots = _resource_fewshot_examples(card_type)
    code_template = _infer_code_template(node_id, node_title) if card_type == "code_snippet" else None
    system_prompt = (
        "你是一名资深中文计算机课程设计专家。"
        "请根据给定知识上下文，为单一学习资源卡生成高质量、可直接给前端渲染的 JSON。"
        "必须严格返回一个 JSON object，不要输出解释，不要输出 Markdown 代码围栏。"
        "内容要求详细、教学性强、避免空泛套话，且必须和当前知识点强相关。"
    )
    fewshot_text = ""
    if fewshots:
        fewshot_blocks = []
        for example in fewshots:
            fewshot_blocks.append(
                f"示例输入:\n{example['input']}\n"
                f"示例输出:\n{json.dumps(example['output'], ensure_ascii=False, indent=2)}"
            )
        fewshot_text = "\n\n".join(fewshot_blocks)
    code_template_text = ""
    if code_template:
        code_template_text = (
            "代码模板约束:\n"
            f"{json.dumps(code_template, ensure_ascii=False, indent=2)}\n"
            "要求保留这个模板所体现的核心实现思路，可以改进讲解，但不要偏离该知识点。"
        )
    user_prompt = (
        f"知识点: {node_title}\n"
        f"卡片类型: {card_type}\n"
        f"难度系数: {difficulty:.2f}\n"
        f"输出 JSON 结构示例:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"卡片约束:\n" + "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(constraints)) + "\n\n"
        f"{fewshot_text}\n\n"
        f"{code_template_text}\n\n"
        f"请结合以下知识上下文生成内容。\n"
        f"要求:\n"
        f"1. 只生成这一类卡片，不要混入其他卡片内容。\n"
        f"2. 所有列表项都要具体、可学、可操作。\n"
        f"3. 诊断题必须给出正确答案解释。\n"
        f"4. 如果是 concept_map，务必生成有效 mermaid_source。\n"
        f"5. 如果是 code_snippet，务必输出真实代码，不要用伪代码，并优先遵循给定模板思路。\n\n"
        f"知识上下文:\n{chr(10).join(f'片段{idx + 1}: {chunk}' for idx, chunk in enumerate(context_chunks))}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # concept_map 内容最丰富，给更多 token 空间以避免在 review_prompts 前截断
    max_tokens = 4096 if card_type == "concept_map" else 2600
    result = llm.chat_sync(messages, temperature=0.35, max_tokens=max_tokens, json_mode=True)
    raw_content = result.get("content", "") if isinstance(result, dict) else str(result)
    payload = _extract_json_object(raw_content)
    if not payload:
        return None

    payload["render_type"] = card_type
    payload.setdefault("title", node_title if card_type == "concept_map" else f"{node_title} {card_type}")
    if card_type == "code_snippet" and code_template:
        payload["language"] = payload.get("language") or code_template.get("language", "python")
        if _estimate_token_count(payload.get("code", "")) < 40:
            payload["code"] = code_template["code"]
        payload["scenario"] = payload.get("scenario") or code_template.get("scenario", "")
        payload["prerequisites"] = payload.get("prerequisites") or code_template.get("prerequisites", [])
        payload["complexity_notes"] = payload.get("complexity_notes") or code_template.get("complexity_notes", [])
        payload["pitfalls"] = payload.get("pitfalls") or code_template.get("pitfalls", [])
        payload["experiments"] = payload.get("experiments") or code_template.get("experiments", [])
        if not payload.get("walkthrough_steps"):
            payload["walkthrough_steps"] = [
                "先观察这段代码想体现的核心约束。",
                "再跟踪关键状态如何变化。",
                "最后对照边界条件检查实现是否完整。",
            ]
    payload = _polish_generated_metadata(node_id, card_type, payload, code_template=code_template)
    markdown = _build_resource_markdown_from_metadata(card_type, payload)
    budget_info[f"{card_type}_generation"] = {
        "estimated_input_tokens": _estimate_token_count(system_prompt) + _estimate_token_count(user_prompt),
        "overflow_applied": budget_info.get("overflow_applied", "direct"),
        "batch_count": budget_info.get("batch_count", 1),
        "model": getattr(llm, "provider", "qwen"),
    }
    return payload, markdown


def _polish_generated_metadata(
    node_id: str,
    card_type: str,
    payload: Dict[str, Any],
    code_template: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    node_title = _get_node_title(node_id, node_id)
    polished = dict(payload or {})
    polished["render_type"] = card_type
    polished["title"] = _ensure_text(
        polished.get("title"),
        node_title if card_type == "concept_map" else f"{node_title} {card_type}",
        max_chars=80,
    )

    if card_type == "concept_map":
        polished["summary"] = _ensure_text(
            polished.get("summary"),
            f"{node_title} 的学习重点在于理解它解决的约束、典型机制和应用判断，而不是只记结论。",
        )
        objectives = _ensure_list_floor(
            _coerce_text_list(polished.get("learning_objectives"), limit=5),
            [
                f"说清 {node_title} 的核心定义与约束",
                f"判断 {node_title} 适合解决什么问题",
                f"识别 {node_title} 的常见误区并能纠正",
            ],
            min_items=3,
            limit=5,
        )
        sections = polished.get("sections") if isinstance(polished.get("sections"), list) else []
        normalized_sections = []
        for section in sections[:6]:
            if not isinstance(section, dict):
                continue
            heading = _ensure_text(section.get("heading"), "内容")
            body = _ensure_text(section.get("body"), f"{heading} 需要结合 {node_title} 的核心机制进一步理解。")
            normalized_sections.append({"heading": heading, "body": body})
        default_sections = [
            {"heading": "核心定义", "body": f"{node_title} 首先要从定义、操作边界和问题抽象三个角度理解，避免只记表面术语。"},
            {"heading": "工作机制", "body": f"学习 {node_title} 时，要重点追踪状态如何变化、约束如何生效，以及为什么这种机制能解决特定问题。"},
            {"heading": "典型应用", "body": f"把 {node_title} 放回典型题型或真实场景中，才能判断它究竟何时该用、何时不该用。"},
            {"heading": "前后关联", "body": f"同时对比 {node_title} 与前序知识点的联系和差异，才能形成稳定的知识网络。"},
        ]
        while len(normalized_sections) < 4:
            normalized_sections.append(default_sections[len(normalized_sections)])
        polished["learning_objectives"] = objectives
        polished["sections"] = normalized_sections[:6]
        polished["bullets"] = _ensure_list_floor(
            _coerce_text_list(polished.get("bullets"), limit=6),
            [
                f"{node_title} 不只是记操作，更要理解约束",
                "先抓住状态变化，再看实现细节",
                "把典型题型和底层机制对应起来",
                "用对比方式识别与相邻知识点的差异",
            ],
            min_items=4,
            limit=6,
        )
        polished["common_misconceptions"] = _ensure_list_floor(
            _coerce_text_list(polished.get("common_misconceptions"), limit=5),
            [
                f"只会背 {node_title} 的定义，却不会判断使用场景",
                "把表面现象当成底层原因",
                "能做模板题，但一换问法就不会迁移",
            ],
            min_items=3,
            limit=5,
        )
        polished["review_prompts"] = _ensure_list_floor(
            _coerce_text_list(polished.get("review_prompts"), limit=5),
            [
                f"如果不能使用术语，你会怎样解释 {node_title}？",
                f"{node_title} 最适合解决哪类问题，为什么？",
                f"遇到什么现象时说明你还没有真正掌握 {node_title}？",
            ],
            min_items=3,
            limit=5,
        )
        polished["mermaid_source"] = _ensure_text(
            polished.get("mermaid_source"),
            _build_mermaid_from_bullets(node_title, polished["bullets"]),
            max_chars=1200,
        )
        return polished

    if card_type == "code_snippet":
        if code_template:
            polished["language"] = _ensure_text(polished.get("language"), code_template.get("language", "python"), max_chars=24)
            if _estimate_token_count(polished.get("code", "")) < 40:
                polished["code"] = code_template.get("code", "")
            polished["scenario"] = _ensure_text(polished.get("scenario"), code_template.get("scenario", ""))
            polished["prerequisites"] = _ensure_list_floor(
                _coerce_text_list(polished.get("prerequisites"), limit=5),
                code_template.get("prerequisites", []) or [f"先理解 {node_title} 的基本定义"],
                min_items=2,
                limit=5,
            )
            polished["complexity_notes"] = _ensure_list_floor(
                _coerce_text_list(polished.get("complexity_notes"), limit=5),
                code_template.get("complexity_notes", []) or ["先解释复杂度来自哪一步，而不是只背结论。"],
                min_items=2,
                limit=5,
            )
            polished["pitfalls"] = _ensure_list_floor(
                _coerce_text_list(polished.get("pitfalls"), limit=5),
                code_template.get("pitfalls", []) or ["先检查边界条件和状态更新顺序。"],
                min_items=2,
                limit=5,
            )
            polished["experiments"] = _ensure_list_floor(
                _coerce_text_list(polished.get("experiments"), limit=5),
                code_template.get("experiments", []) or ["在原实现上扩展一个新操作并验证边界情况。"],
                min_items=3,
                limit=5,
            )
        polished["explanation"] = _ensure_text(
            polished.get("explanation"),
            f"这段代码的重点不只是跑通，而是把 {node_title} 的关键约束、状态变化与工程实现方式对齐。",
        )
        polished["walkthrough_steps"] = _ensure_list_floor(
            _coerce_text_list(polished.get("walkthrough_steps"), limit=6),
            [
                "先明确这段实现要体现的核心约束。",
                "再跟踪关键状态如何随操作变化。",
                "检查边界输入时代码是否仍然成立。",
                "最后回到复杂度，解释为什么代价会落在这些步骤上。",
            ],
            min_items=4,
            limit=6,
        )
        return polished

    if card_type == "interactive_exercise":
        polished["prompt"] = _ensure_text(
            polished.get("prompt"),
            f"围绕 {node_title} 设计一个需要你手动推演状态变化的练习。",
        )
        polished["goal"] = _ensure_text(
            polished.get("goal"),
            f"通过动手推演，把 {node_title} 的概念、机制和判断标准真正连起来。",
        )
        polished["steps"] = _ensure_list_floor(
            _coerce_text_list(polished.get("steps"), limit=6),
            [
                "先写出输入、约束和目标输出。",
                "逐步模拟关键状态变化。",
                "在每一步记录你为什么这样判断。",
                "最后总结这道题体现了什么结构或方法约束。",
            ],
            min_items=4,
            limit=6,
        )
        polished["checkpoints"] = _ensure_list_floor(
            _coerce_text_list(polished.get("checkpoints"), limit=5),
            [
                "是否能解释每一步状态变化的原因？",
                "是否能指出最容易出错的边界位置？",
                "是否能把结果和知识点约束对应起来？",
            ],
            min_items=3,
            limit=5,
        )
        polished["hints"] = _ensure_list_floor(
            _coerce_text_list(polished.get("hints"), limit=4),
            [
                "先不要急着写答案，先画出状态变化。",
                "优先找出决定路径选择的关键约束。",
            ],
            min_items=2,
            limit=4,
        )
        polished["expected_outcome"] = _ensure_text(
            polished.get("expected_outcome"),
            f"做完后，你应该能独立判断 {node_title} 在相近题型中的使用方式，并解释每一步状态变化。",
        )
        polished["solution_outline"] = _ensure_text(
            polished.get("solution_outline"),
            "先抓输入与约束，再按状态变化顺序推进，最后回头验证边界与结果，不要直接套模板。",
        )
        return polished

    if card_type == "video_summary":
        polished["summary"] = _ensure_text(
            polished.get("summary"),
            f"把 {node_title} 当作一份学习笔记来理解：先看它解决什么问题，再看核心机制、易错点和典型应用。",
        )
        polished["key_points"] = _ensure_list_floor(
            _coerce_text_list(polished.get("key_points"), limit=6),
            [
                f"{node_title} 的核心不只是定义，更是约束与状态变化",
                "先理解为什么这样设计，再记操作流程",
                "对比相邻知识点能更快建立判断力",
                "易错点通常出现在边界条件或结构选择上",
            ],
            min_items=4,
            limit=6,
        )
        timeline = polished.get("timeline") if isinstance(polished.get("timeline"), list) else []
        normalized_timeline = []
        for item in timeline[:6]:
            if not isinstance(item, dict):
                continue
            normalized_timeline.append({
                "label": _ensure_text(item.get("label"), "片段"),
                "summary": _ensure_text(item.get("summary"), f"这一段围绕 {node_title} 的某个关键面向展开。"),
            })
        default_timeline = [
            {"label": "概念建立", "summary": f"先建立 {node_title} 的问题背景、核心定义和整体直觉。"},
            {"label": "机制拆解", "summary": "再拆开关键状态、操作顺序或结构约束，理解它为什么成立。"},
            {"label": "案例演示", "summary": "随后用一个典型例题或代码片段展示它如何落地。"},
            {"label": "误区纠正", "summary": "最后集中纠正高频误区，并总结迁移判断方法。"},
        ]
        while len(normalized_timeline) < 4:
            normalized_timeline.append(default_timeline[len(normalized_timeline)])
        polished["timeline"] = normalized_timeline[:6]
        polished["watch_focus"] = _ensure_list_floor(
            _coerce_text_list(polished.get("watch_focus"), limit=5),
            [
                "注意讲解中状态是如何一步步变化的。",
                "特别观察哪里在比较不同方案或不同数据结构。",
                "留意老师是如何解释边界条件和易错点的。",
            ],
            min_items=3,
            limit=5,
        )
        polished["review_questions"] = _ensure_list_floor(
            _coerce_text_list(polished.get("review_questions"), limit=5),
            [
                f"如果不用术语，你会怎样复述 {node_title} 的核心机制？",
                f"{node_title} 与相邻知识点最容易混淆的地方是什么？",
                f"换一道相近题，你怎样判断是否该使用 {node_title}？",
            ],
            min_items=3,
            limit=5,
        )
        return polished

    questions = polished.get("questions") if isinstance(polished.get("questions"), list) else []
    normalized_questions = []
    for index, question in enumerate(questions[:5], start=1):
        if not isinstance(question, dict):
            continue
        options = _coerce_text_list(question.get("options"), limit=4)
        if len(options) < 4:
            defaults = [
                f"{node_title} 的结论要结合约束和场景理解",
                f"{node_title} 与当前知识点没有直接关系",
                f"{node_title} 只能在唯一固定模板中使用",
                "只要记住术语就等于掌握了该知识点",
            ]
            options = _ensure_list_floor(options, defaults, min_items=4, limit=4)
        answer_index = question.get("answer_index", 0)
        if not isinstance(answer_index, int) or answer_index < 0 or answer_index > 3:
            answer_index = 0
        normalized_questions.append(
            {
                "id": _ensure_text(question.get("id"), f"{node_id}-q{index}", max_chars=36),
                "prompt": _ensure_text(
                    question.get("prompt"),
                    f"关于 {node_title}，下列哪项判断最符合当前学习材料？",
                ),
                "options": options[:4],
                "answer_index": answer_index,
                "explanation": _ensure_text(
                    question.get("explanation"),
                    f"正确选项之所以成立，是因为它符合 {node_title} 的核心约束；其余选项则忽略了场景、机制或边界条件。",
                ),
                "skill_tag": _ensure_text(question.get("skill_tag"), "概念理解", max_chars=32),
                "difficulty": _ensure_text(question.get("difficulty"), "medium", max_chars=12),
            }
        )
    while len(normalized_questions) < 3:
        q_index = len(normalized_questions) + 1
        fallback_prompt = [
            f"关于 {node_title} 的核心定义，下列哪项最准确？",
            f"如果把 {node_title} 用在不合适的场景中，最容易出现什么问题？",
            f"在一个具体例子里，哪种做法最能体现 {node_title} 的约束？",
        ][len(normalized_questions)]
        normalized_questions.append(
            {
                "id": f"{node_id}-q{q_index}",
                "prompt": fallback_prompt,
                "options": [
                    f"它符合 {node_title} 的约束与使用场景",
                    "它只是在表面上提到了相关术语",
                    "它忽略了边界条件和状态变化",
                    "它与当前知识点没有直接关系",
                ],
                "answer_index": 0,
                "explanation": f"正确项抓住了 {node_title} 的真正判断标准；其余选项要么只停留在表面术语，要么忽略了场景和边界条件。",
                "skill_tag": ["概念识别", "理解判断", "应用判断"][len(normalized_questions) - 1],
                "difficulty": "medium",
            }
        )
    polished["questions"] = normalized_questions[:5]
    polished["pass_threshold"] = float(polished.get("pass_threshold") or MASTERY_ADVANCE_THRESHOLD)
    polished["after_quiz_guidance"] = _ensure_text(
        polished.get("after_quiz_guidance"),
        f"若得分不理想，先回看 {node_title} 的概念图与代码讲解，再通过互动练习补强状态推演，最后重做诊断题。",
    )
    polished["summary"] = _ensure_text(
        polished.get("summary"),
        f"作答时不要只认术语，要回到 {node_title} 的约束、机制和典型场景。",
    )
    return polished


def _build_structured_resource_payload(node_id: str, card_type: str, difficulty: float, context_chunks: List[str]) -> Tuple[Dict[str, Any], str]:
    title = _get_node_title(node_id) or node_id
    context_text = "\n\n".join(context_chunks).strip()
    context_text = context_text or f"{title} 的相关知识材料暂未命中，以下为针对该节点的结构化学习引导。"
    sentences = _extract_sentences(context_text, limit=12)
    bullets = _extract_bullets(context_text, limit=8)
    summary = "；".join(sentences[:3]) if sentences else f"{title} 的学习材料已经装配完成，可按下列结构继续推进。"
    summary = summary[:240]

    if card_type == "concept_map":
        learning_objectives = _normalize_text_list(
            bullets[:3] or [
                f"理解 {title} 的定义、目标与适用场景",
                f"说明 {title} 与相邻知识点之间的关系",
                f"识别 {title} 的常见误区并建立判断标准",
            ],
            limit=4,
        )
        sections = [
            {
                "heading": "核心定义",
                "body": sentences[0] if sentences else f"{title} 是当前学习路径中的核心知识点，先建立定义和问题边界，再进入例题与实现。",
            },
            {
                "heading": "工作机制",
                "body": "；".join(sentences[1:4]) if len(sentences) > 1 else f"可以从输入、约束、状态变化和输出四个角度拆解 {title} 的工作机制。",
            },
            {
                "heading": "与前后知识点的连接",
                "body": "；".join(sentences[4:7]) if len(sentences) > 4 else f"学习 {title} 时要持续和前序节点建立联系，避免把它当成孤立技巧记忆。",
            },
        ]
        misconceptions = _normalize_text_list(
            [
                f"只记住 {title} 的表面定义，而没有抓住它解决的约束问题",
                f"能背结论，却不能解释为什么这种结构或方法更合适",
                f"一遇到新题型就无法把 {title} 与已有知识联动起来",
            ],
            limit=4,
        )
        review_prompts = _normalize_text_list(
            [
                f"如果不用术语，你会怎样向同学解释 {title}？",
                f"{title} 最适合解决哪类问题，为什么？",
                f"哪些现象说明你只是记住了表面，而没有真正掌握 {title}？",
            ],
            limit=4,
        )
        mermaid_source = _build_mermaid_from_bullets(title, learning_objectives + bullets[:2])
        metadata = {
            "render_type": "concept_map",
            "title": title,
            "summary": summary,
            "learning_objectives": learning_objectives,
            "sections": sections,
            "bullets": _normalize_text_list(bullets or sentences, limit=6),
            "common_misconceptions": misconceptions,
            "mermaid_source": mermaid_source,
            "review_prompts": review_prompts,
        }
        markdown = "\n\n".join(
            [
                f"## {title}",
                f"### 学习目标\n" + "\n".join(f"- {item}" for item in learning_objectives),
                *[f"### {section['heading']}\n{section['body']}" for section in sections],
                "### 常见误区\n" + "\n".join(f"- {item}" for item in misconceptions),
                "### 复习提问\n" + "\n".join(f"- {item}" for item in review_prompts),
                f"```mermaid\n{mermaid_source}\n```",
            ]
        )
        return metadata, markdown

    if card_type == "code_snippet":
        language = "python"
        scenario = f"围绕 {title} 构造一个可讲清思路、又能继续扩展的实现示例。"
        code = (
            f"class {re.sub(r'[^a-zA-Z0-9]', '', title.title()) or 'NodeExample'}Example:\n"
            f"    def __init__(self):\n"
            f"        self.notes = []\n\n"
            f"    def explain(self, item):\n"
            f"        self.notes.append(item)\n"
            f"        return f\"{title}: {{item}}\"\n"
        )
        walkthrough_steps = _normalize_text_list(
            [
                f"先明确这个实现要展示 {title} 的哪一个关键动作",
                "再观察输入、状态变化和输出之间的关系",
                "最后检查边界情况，确认代码没有把关键约束偷掉",
            ],
            limit=5,
        )
        metadata = {
            "render_type": "code_snippet",
            "title": f"{title} 代码示例",
            "language": language,
            "scenario": scenario,
            "prerequisites": _normalize_text_list(
                [f"已掌握 {title} 的基本定义", "能读懂函数、条件分支和基础数据结构操作"],
                limit=4,
            ),
            "code": code,
            "walkthrough_steps": walkthrough_steps,
            "explanation": summary,
            "complexity_notes": _normalize_text_list(
                ["先解释操作流程，再补充时间与空间复杂度，不要只背结论。"],
                limit=4,
            ),
            "pitfalls": _normalize_text_list(
                ["只看最终代码，不推演状态变化。", "忽略边界输入和非法输入处理。"],
                limit=4,
            ),
            "experiments": _normalize_text_list(
                ["尝试自己补一个边界 case。", "把实现改成另一种写法，再比较可读性和复杂度。"],
                limit=4,
            ),
        }
        markdown = "\n\n".join(
            [
                f"## {title} 代码示例",
                f"### 场景\n{scenario}",
                "### 前置知识\n" + "\n".join(f"- {item}" for item in metadata["prerequisites"]),
                f"```{language}\n{code}\n```",
                "### 逐步讲解\n" + "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(walkthrough_steps)),
                f"### 说明\n{summary}",
                "### 常见坑点\n" + "\n".join(f"- {item}" for item in metadata["pitfalls"]),
            ]
        )
        return metadata, markdown

    if card_type == "interactive_exercise":
        steps = _normalize_text_list(
            sentences[:5] or [
                f"先用自己的话复述 {title} 要解决的问题",
                "把题目拆成输入、约束、状态、输出四块",
                "完成一次手推，再落到代码或结论",
            ],
            limit=5,
        )
        checkpoints = _normalize_text_list(
            bullets[:4] or [
                "能说清当前方案为什么成立",
                "能指出至少一个边界情况",
                "能解释答案和核心概念之间的对应关系",
            ],
            limit=4,
        )
        hints = _normalize_text_list(
            [
                f"别急着写答案，先判断 {title} 在这题里扮演的角色。",
                "如果卡住，就从最小样例开始手推状态变化。",
                "优先检查边界和不变量，而不是直接背模板。",
            ],
            limit=4,
        )
        metadata = {
            "render_type": "interactive_exercise",
            "title": f"{title} 互动练习",
            "prompt": summary,
            "goal": f"通过一个完整的小练习把 {title} 从‘看懂’推进到‘会用’。",
            "steps": steps,
            "checkpoints": checkpoints,
            "hints": hints,
            "expected_outcome": f"完成后，你应该能把 {title} 的使用条件和解题动作讲完整。",
            "solution_outline": "先口述思路，再手推样例，最后写出实现或结论，并回看是否满足全部约束。",
        }
        markdown = "\n\n".join(
            [
                f"## {title} 互动练习",
                f"### 任务目标\n{metadata['goal']}",
                f"### 任务说明\n{summary}",
                "### 推荐步骤\n" + "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(steps)),
                "### 检查点\n" + "\n".join(f"- {item}" for item in checkpoints),
                "### 提示\n" + "\n".join(f"- {item}" for item in hints),
                f"### 预期结果\n{metadata['expected_outcome']}",
                f"### 参考思路\n{metadata['solution_outline']}",
            ]
        )
        return metadata, markdown

    if card_type == "video_summary":
        key_points = _normalize_text_list(
            bullets[:5] or sentences[:5] or [f"{title} 的核心学习重点已经整理为可回看的提纲。"],
            limit=5,
        )
        timeline = [
            {"label": "开场定位", "summary": key_points[0] if key_points else f"先建立 {title} 的问题背景。"},
            {"label": "机制拆解", "summary": key_points[1] if len(key_points) > 1 else f"再解释 {title} 的核心机制。"},
            {"label": "应用提醒", "summary": key_points[2] if len(key_points) > 2 else f"最后把 {title} 放回题目或场景中验证。"},
        ]
        metadata = {
            "render_type": "video_summary",
            "title": f"{title} 视频摘要",
            "summary": summary,
            "key_points": key_points,
            "timeline": timeline,
            "watch_focus": _normalize_text_list(
                [f"观看时重点记下 {title} 的触发条件。", "关注讲解里如何从约束过渡到解法。"],
                limit=4,
            ),
            "review_questions": _normalize_text_list(
                [f"如果暂停视频，你能独立复述 {title} 的三步主线吗？", "哪些片段最容易看懂但不会做？"],
                limit=4,
            ),
            "duration_minutes": max(6, min(18, int(math.ceil(8 + difficulty * 6)))),
            "video_url": None,
        }
        markdown = "\n\n".join(
            [
                f"## {title} 视频摘要",
                f"### 核心总结\n{summary}",
                "### 关键点\n" + "\n".join(f"- {item}" for item in key_points),
                "### 分段提纲\n" + "\n".join(f"- {item['label']}: {item['summary']}" for item in timeline),
                "### 观看关注点\n" + "\n".join(f"- {item}" for item in metadata["watch_focus"]),
                "### 复习问题\n" + "\n".join(f"- {item}" for item in metadata["review_questions"]),
            ]
        )
        return metadata, markdown

    questions = []
    seeds = _normalize_text_list(sentences[:3] or bullets[:3], limit=3)
    if not seeds:
        seeds = [f"{title} 的核心概念需要继续结合当前资源理解。"]
    for index, seed in enumerate(seeds, start=1):
        questions.append(
            {
                "id": f"{node_id}-q{index}",
                "prompt": f"关于 {title}，下列哪项最符合当前学习材料的要点？",
                "options": [
                    seed,
                    f"{title} 与当前节点没有直接关系",
                    f"{title} 只在极少数题目中成立",
                    "以上都不准确",
                ],
                "answer_index": 0,
                "explanation": f"正确项对应的是当前资源反复强调的主线: {seed}",
                "skill_tag": _safe_heading(title, "概念理解"),
                "difficulty": "medium" if difficulty < 0.75 else "hard",
            }
        )
    metadata = {
        "render_type": "diagnostic_quiz",
        "title": f"{title} 诊断测验",
        "questions": questions,
        "pass_threshold": MASTERY_ADVANCE_THRESHOLD,
        "after_quiz_guidance": f"若得分不理想，先回到 {title} 的概念图和互动练习，再重新作答。",
    }
    markdown = "\n\n".join(
        [
            f"## {title} 诊断测验",
            "### 作答提醒",
            f"- 先判断题目考查的是 {title} 的哪一层能力",
            "- 不要只凭熟悉词汇选项，要回到约束和机制",
            f"### 诊断后建议\n{metadata['after_quiz_guidance']}",
        ]
    )
    return metadata, markdown


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


def _upsert_resource_card(agent_state: AgentState, card: ResourceCard) -> None:
    cards = list(agent_state.generated_resources.get(card.node_id, []))
    cards = [existing for existing in cards if existing.card_type != card.card_type]
    cards.append(_normalize_resource_card(card))
    agent_state.generated_resources[card.node_id] = _dedupe_and_sort_cards(cards)


def _build_card_content_from_kb(node_id: str, card_type: str, difficulty: float) -> str:
    title = _get_node_title(node_id) or node_id
    chunks = _search_knowledge_base(title, top_k=2)
    if not chunks:
        chunks = _search_knowledge_base(node_id, top_k=2)
    metadata, markdown = _build_structured_resource_payload(node_id, card_type, difficulty, chunks)
    return markdown or metadata.get("summary", f"知识点 {title} 的相关内容正在准备中。")


def _assemble_node_resource_set(node_id: str, difficulty: float) -> Tuple[List[ResourceCard], Dict[str, Any]]:
    title = _get_node_title(node_id) or node_id
    raw_chunks = _search_knowledge_base(title, top_k=6)
    if not raw_chunks:
        raw_chunks = _search_knowledge_base(node_id, top_k=6)

    base_prompt_tokens = _estimate_token_count(title) + 800
    budget_info = _budget_context_chunks(title, raw_chunks, base_prompt_tokens)
    selected_chunks = budget_info["selected_chunks"] or raw_chunks[:2]
    cards: List[ResourceCard] = []

    for card_type in RESOURCE_CARD_ORDER:
        generated = _generate_card_with_qwen(node_id, card_type, difficulty, selected_chunks, budget_info)
        if generated:
            metadata, markdown = generated
        else:
            metadata, markdown = _build_structured_resource_payload(node_id, card_type, difficulty, selected_chunks)
        cards.append(
            ResourceCard(
                resource_id=f"{node_id}_{card_type}_supp",
                node_id=node_id,
                card_type=card_type,
                content=markdown,
                difficulty=difficulty,
                cognitive_style="textual",
                metadata=metadata,
            )
        )

    return cards, budget_info


def _ensure_node_resource_set(agent_state: AgentState, node_id: str, force: bool = False) -> None:
    """填充节点资源集合。

    Args:
        agent_state: 当前 Agent 状态。
        node_id: 目标知识节点 ID。
        force: True 时强制重新生成（用于用户主动点击"生成"/"重新生成"），
               False 时若该节点已有完整资源则直接跳过，避免重复调用 LLM。
    """
    if not force:
        # 若已有全部5种卡片类型，无需重新生成
        existing = agent_state.generated_resources.get(node_id, [])
        existing_types = {c.card_type for c in existing}
        if existing_types.issuperset(set(RESOURCE_CARD_ORDER)):
            return

    difficulty = max(0.1, 1.0 - agent_state.dynamic_profile.knowledge_mastery.get(node_id, 0.5))
    cards, budget_info = _assemble_node_resource_set(node_id, difficulty)
    for card in cards:
        card.cognitive_style = agent_state.recommended_resource_style or "textual"
        _upsert_resource_card(agent_state, card)
    agent_state.internal_state["resource_generation_budget"] = {
        **budget_info,
        "node_id": node_id,
        "card_types": list(RESOURCE_CARD_ORDER),
    }


def _find_next_pending_node(active_path: List[str], mastery_map: Dict[str, float], current_node: str) -> Optional[str]:
    if not active_path:
        return None

    start_index = active_path.index(current_node) + 1 if current_node in active_path else 0
    for node_id in active_path[start_index:]:
        if mastery_map.get(node_id, 0.0) < MASTERY_ADVANCE_THRESHOLD:
            return node_id
    return None


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


def _build_agent_feedback(
    agent_state: AgentState,
    current_node: str,
    logs: List[Dict[str, Any]],
    interaction_type: str,
    previous_mastery: float,
    evaluated_mastery: float,
    advanced_to_next_node: bool,
    next_node_id: Optional[str],
) -> List[AgentFeedbackItem]:
    feedback: List[AgentFeedbackItem] = []
    title = _get_node_title(current_node, current_node)
    next_title = _get_node_title(next_node_id, next_node_id) if next_node_id else ""
    budget_info = agent_state.internal_state.get("resource_generation_budget", {})

    for log in logs:
        agent = log.get("agent", "")
        if agent == "Evaluator":
            effective = round((log.get("effective_correctness") or 0) * 100)
            delta = round((log.get("mastery_delta") or 0) * 100, 1)
            skipped = interaction_type == "load_node" or log.get("status") == "skipped"
            feedback.append(_format_feedback_item(
                agent="Evaluator",
                stage="学习评估",
                status="success" if not skipped else "skipped",
                headline=f"{title} {'已完成本轮学习表现评估' if not skipped else '当前为资源装配阶段，未执行答题评估'}",
                summary=(
                    f"有效正确率 {effective}% ，本轮掌握度变化 {delta}% 。"
                    if not skipped
                    else "本次操作用于装配当前节点资源与反馈，不会计算得分或改变 mastery。"
                ),
                structured_data=log,
                details_md=(
                    f"### Evaluator\n"
                    f"- 当前节点：{title}\n"
                    + (
                        f"- 有效正确率：{effective}%\n"
                        f"- mastery 变化：{delta}%\n"
                        f"- 重规划决策：{log.get('replan_decision', 'n/a')}"
                        if not skipped
                        else "- 当前操作类型：load_node\n- 说明：仅刷新资源，不做学习表现评估"
                    )
                ),
            ))
        elif agent == "Profiler":
            skipped = interaction_type == "load_node" or log.get("status") == "skipped"
            feedback.append(_format_feedback_item(
                agent="Profiler",
                stage="学习风格",
                status="success" if not skipped else "skipped",
                headline="已更新当前节点的学习风格建议",
                summary=(
                    f"推荐资源风格为 {log.get('selected_style', 'textual')}，可据此调整阅读与练习顺序。"
                    if not skipped
                    else "当前仅加载节点资源，保留既有学习风格建议，不触发新的画像干预。"
                ),
                structured_data=log,
                details_md=(
                    f"### Profiler\n"
                    + (
                        f"- 推荐风格：{log.get('selected_style', 'textual')}\n"
                        f"- 是否触发干预：{bool(log.get('intervention_triggered'))}\n"
                        f"- 遗忘衰减：{log.get('forgetting_decay', 'n/a')}"
                        if not skipped
                        else "- 当前操作类型：load_node\n- 说明：未触发新的学习风格评估"
                    )
                ),
            ))
        elif agent == "Planner":
            path_preview = " -> ".join((_get_node_title(node, node) for node in (log.get("new_path") or log.get("active_path") or [])[:5]))
            feedback.append(_format_feedback_item(
                agent="Planner",
                stage="路径规划",
                status="info",
                headline="学习路径已同步",
                summary=f"当前主线路径已定位到 {title}，下一待攻克节点为 {next_title or '当前节点'}。",
                structured_data=log,
                details_md=(
                    f"### Planner\n"
                    f"- 当前节点：{title}\n"
                    f"- 是否重规划：{bool(log.get('replan'))}\n"
                    f"- 路径预览：{path_preview or '暂无'}"
                ),
            ))
        elif agent == "Tutor":
            tutor_response = agent_state.tutor_response or {}
            feedback.append(_format_feedback_item(
                agent="Tutor",
                stage="辅导讲解",
                status="success",
                headline="已生成当前节点的辅导反馈",
                summary="本轮辅导输出已整理为讲解正文、图示和可追问内容。",
                structured_data=log,
                details_md=tutor_response.get("text_explanation", ""),
                artifacts={
                    "mermaid_src": tutor_response.get("mermaid_src", ""),
                    "video_hydration": tutor_response.get("video_hydration", {}),
                },
            ))
        elif agent == "ContentMesh":
            generation_modes = [
                f"{card_type}: {'qwen' if isinstance(budget_info.get(f'{card_type}_generation'), dict) else 'fallback'}"
                for card_type in RESOURCE_CARD_ORDER
            ]
            feedback.append(_format_feedback_item(
                agent="ContentMesh",
                stage="资源装配",
                status="success",
                headline=f"{title} 的 5 类主学习资源已装配",
                summary="当前节点资源已按概念、代码、练习、摘要、诊断的顺序整理完成。",
                structured_data={**log, **budget_info},
                details_md=(
                    f"### ContentMesh\n"
                    f"- 卡片类型：{', '.join(log.get('card_types', []))}\n"
                    f"- 生成路径：{'; '.join(generation_modes)}\n"
                    f"- 估算输入 tokens：{budget_info.get('estimated_input_tokens', 0)}\n"
                    f"- 溢出处理：{budget_info.get('overflow_applied', 'direct')}\n"
                    f"- 批次数：{budget_info.get('batch_count', 1)}"
                ),
            ))
        elif agent == "Validator":
            feedback.append(_format_feedback_item(
                agent="Validator",
                stage="质量校验",
                status="success" if log.get("overall_pass_rate", 1) >= 0.6 else "warning",
                headline="资源质量校验已完成",
                summary=f"本轮资源通过率约 {round((log.get('overall_pass_rate') or 0) * 100)}% 。",
                structured_data=log,
                details_md=(
                    f"### Validator\n"
                    f"- 有效卡片：{log.get('valid_cards', 0)}\n"
                    f"- 被拒卡片：{log.get('rejected_cards', 0)}\n"
                    f"- 通过率：{round((log.get('overall_pass_rate') or 0) * 100)}%"
                ),
            ))
        elif agent == "Assessment":
            feedback.append(_format_feedback_item(
                agent="Assessment",
                stage="推进结论",
                status="success" if advanced_to_next_node else ("info" if interaction_type == "load_node" else "warning"),
                headline="当前节点推进结论已更新",
                summary=(
                    (
                        f"当前为资源装配阶段，节点保持在 {title}，不会因查看资源而推进。"
                        if interaction_type == "load_node"
                        else f"掌握度由 {round(previous_mastery * 100)}% 变化到 {round(evaluated_mastery * 100)}% ，"
                        f"{'已推进到下一节点。' if advanced_to_next_node else '暂时停留当前节点继续补强。'}"
                    )
                ),
                structured_data={
                    **log,
                    "previous_mastery": previous_mastery,
                    "evaluated_mastery": evaluated_mastery,
                    "advanced_to_next_node": advanced_to_next_node,
                    "next_node_id": next_node_id,
                },
                details_md=(
                    f"### Assessment\n"
                    f"- 当前节点：{title}\n"
                    + (
                        "- 当前操作类型：load_node\n"
                        "- 说明：仅刷新资源与反馈，不触发推进判断"
                        if interaction_type == "load_node"
                        else f"- mastery：{round(previous_mastery * 100)}% -> {round(evaluated_mastery * 100)}%\n"
                        f"- 达标阈值：{round(MASTERY_ADVANCE_THRESHOLD * 100)}%\n"
                        f"- 推进结果：{'进入 ' + next_title if advanced_to_next_node and next_title else '继续停留当前节点'}"
                    )
                ),
            ))

    if agent_state.dynamic_profile.diagnostic_report_md:
        feedback.append(_format_feedback_item(
            agent="Diagnostic",
            stage="综合诊断",
            status="info",
            headline="综合诊断报告已更新",
            summary="学习画像、能力雷达和当前建议已同步到工作台。",
            details_md=agent_state.dynamic_profile.diagnostic_report_md,
            structured_data={"current_node_id": current_node},
        ))

    return feedback

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


async def api_run_pipeline_step_v2(request: Request) -> JSONResponse:
    """Run one workspace step with metadata-first resources and explicit interaction semantics."""
    body = await request.json()
    user_id = body.get("user_id", "demo_user")
    course_id = body.get("course_id", "data_structures")
    interaction_type = body.get("interaction_type", "practice")
    correctness = body.get("correctness", 0.75)
    time_spent_ratio = body.get("time_spent_ratio", 1.0)
    code_pass_rate = body.get("code_pass_rate", 0.70)
    help_count = body.get("help_count", 0)
    tutor_query = body.get("tutor_query", None)
    target_node = body.get("current_node_id", None)

    session = get_or_create_session(user_id, course_id)
    agent_state: AgentState = session["agent_state"]
    if target_node:
        agent_state.current_node_id = target_node

    evaluator: EvaluatorNode = session["evaluator"]
    profiler: ProfilerNode = session["profiler"]
    tutor: TutorAgentNode = session["tutor"]
    mesh: ContentMeshNode = session["mesh"]
    validator: ValidatorNode = session["validator"]
    assessment: AssessmentReporterNode = session["assessment"]
    path_planner: PathPlanner = session["path_planner"]

    logs: List[Dict[str, Any]] = []
    current_node = agent_state.current_node_id or (agent_state.active_path[0] if agent_state.active_path else "N01")
    previous_mastery = agent_state.dynamic_profile.knowledge_mastery.get(current_node, 0.0)
    eval_output = None

    if interaction_type == "load_node":
        logs.append({"agent": "Evaluator", "status": "skipped", "reason": "interaction_type=load_node"})
        logs.append({"agent": "Profiler", "status": "skipped", "reason": "interaction_type=load_node"})
    else:
        raw_behavior = BehaviorVector(
            answer_correctness=correctness,
            code_pass_rate=code_pass_rate,
            time_spent_ratio=time_spent_ratio,
            help_request_count=help_count,
            node_id=current_node,
        )
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

    if not agent_state.active_path or agent_state.re_plan_triggered:
        topo = path_planner.compute_topological_order()
        agent_state.active_path = topo
        agent_state.re_plan_triggered = False
        logs.append({"agent": "Planner", "replan": True, "new_path": agent_state.active_path})
    else:
        logs.append({"agent": "Planner", "replan": False, "active_path": agent_state.active_path})

    if not agent_state.active_path and current_node:
        agent_state.active_path = [current_node]
    if current_node and current_node in agent_state.active_path:
        agent_state.active_path = [current_node, *[node for node in agent_state.active_path if node != current_node]]

    if tutor_query and interaction_type != "load_node":
        tut_input = TutorInput(agent_state=agent_state)
        tut_output = tutor(tut_input)
        agent_state = tut_output.agent_state
        logs.append({
            "agent": "Tutor",
            "query": tutor_query,
            "has_mermaid": bool(agent_state.tutor_response.get("mermaid_src", "") if agent_state.tutor_response else False),
        })

    mesh_input = MeshInput(agent_state=agent_state)
    mesh_output = mesh(mesh_input)
    agent_state = mesh_output.agent_state
    logs.append({
        "agent": "ContentMesh",
        "generated_cards": len(mesh_output.generated_cards),
        "card_types": [c.card_type for c in mesh_output.generated_cards],
    })

    _normalize_state_resources(agent_state)
    _ensure_node_resource_set(agent_state, current_node)

    cards_to_validate = list(agent_state.generated_resources.get(current_node, []))
    if cards_to_validate:
        val_input = ValidatorInput(
            agent_state=agent_state,
            cards_to_validate=cards_to_validate[-5:],
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

    if interaction_type == "load_node":
        logs.append({"agent": "Assessment", "status": "skipped", "reason": "interaction_type=load_node"})
    else:
        assess_input = AssessmentInput(agent_state=agent_state)
        assess_output = assessment(assess_input)
        agent_state = assess_output.agent_state
        logs.append({
            "agent": "Assessment",
            "capability_radar": agent_state.dynamic_profile.capability_radar,
            "pedagogical_strategy": agent_state.pedagogical_strategy,
            "a_mix": round(sum(agent_state.dynamic_profile.capability_radar) / 5, 4),
        })

    evaluated_mastery = agent_state.dynamic_profile.knowledge_mastery.get(current_node, previous_mastery)
    next_node_id = None
    advanced_to_next_node = False

    if interaction_type == "diagnostic" and evaluated_mastery >= MASTERY_ADVANCE_THRESHOLD:
        next_node_id = _find_next_pending_node(
            agent_state.active_path,
            agent_state.dynamic_profile.knowledge_mastery,
            current_node,
        )
        if next_node_id:
            agent_state.current_node_id = next_node_id
            advanced_to_next_node = True
        else:
            agent_state.current_node_id = current_node
    else:
        agent_state.current_node_id = current_node

    agent_feedback = _build_agent_feedback(
        agent_state=agent_state,
        current_node=current_node,
        logs=logs,
        interaction_type=interaction_type,
        previous_mastery=previous_mastery,
        evaluated_mastery=evaluated_mastery,
        advanced_to_next_node=advanced_to_next_node,
        next_node_id=next_node_id,
    )
    agent_state.agent_feedback = agent_feedback

    _normalize_state_resources(agent_state)
    session["agent_state"] = agent_state
    session["pipeline_log"].extend(logs)

    _sync_enrollment_progress(user_id, course_id, agent_state)
    _persist_state(user_id, course_id, agent_state, session.get("cold_state"))

    return JSONResponse({
        "resource_contract_version": RESOURCE_CONTRACT_VERSION,
        "agent_feedback_version": AGENT_FEEDBACK_VERSION,
        "iteration": agent_state.iteration,
        "interaction_type": interaction_type,
        "current_node_id": agent_state.current_node_id,
        "evaluated_node_id": current_node,
        "evaluated_node_mastery": round(evaluated_mastery, 4),
        "previous_mastery": round(previous_mastery, 4),
        "score": round(correctness, 4),
        "advanced_to_next_node": advanced_to_next_node,
        "next_node_id": next_node_id,
        "next_node_title": _get_node_title(next_node_id, next_node_id) if next_node_id else None,
        "mastery_threshold": MASTERY_ADVANCE_THRESHOLD,
        "active_path": agent_state.active_path,
        "pedagogical_strategy": agent_state.pedagogical_strategy,
        "capability_radar": agent_state.dynamic_profile.capability_radar,
        "diagnostic_report": agent_state.dynamic_profile.diagnostic_report_md,
        "knowledge_mastery": {
            key: round(value, 4) for key, value in agent_state.dynamic_profile.knowledge_mastery.items()
        },
        "generated_cards_count": sum(len(v) for v in agent_state.generated_resources.values()),
        "tutor_response": agent_state.tutor_response,
        "re_plan_triggered": agent_state.re_plan_triggered,
        "agent_feedback": [item.model_dump() for item in agent_feedback],
        "errors": agent_state.errors[-5:],
        "step_logs": logs,
        "all_logs": session["pipeline_log"],
    })


api_run_pipeline_step = api_run_pipeline_step_v2


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


async def api_generate_node_resources(request: Request) -> JSONResponse:
    """显式生成或重新生成某节点的学习资源。

    仅在用户主动点击"生成"或"重新生成"时调用，不在页面加载时自动触发。

    Body:
        user_id   (str)           — 用户 ID
        course_id (str)           — 课程 ID
        node_id   (str)           — 目标知识节点 ID
        force     (bool, default False) — True 时强制重新生成；False 时若已有完整资源则返回现有内容
    """
    body = await request.json()
    user_id   = body.get("user_id", "demo_user")
    course_id = body.get("course_id", "data_structures")
    node_id   = body.get("node_id", "")
    force     = bool(body.get("force", False))

    if not node_id:
        return JSONResponse({"error": "node_id is required"}, status_code=400)

    session = get_or_create_session(user_id, course_id)
    agent_state: AgentState = session["agent_state"]

    # 若未强制且已有完整资源，直接返回（不调用 LLM，满足"重开不重生成"）
    if not force:
        existing = agent_state.generated_resources.get(node_id, [])
        existing_types = {c.card_type for c in existing}
        if existing_types.issuperset(set(RESOURCE_CARD_ORDER)):
            return JSONResponse({
                "status": "already_exists",
                "node_id": node_id,
                "cards": [c.model_dump() for c in existing],
            })

    # 强制生成或首次生成
    _ensure_node_resource_set(agent_state, node_id, force=True)
    _normalize_state_resources(agent_state)
    _persist_state(user_id, course_id, agent_state, session.get("cold_state"))

    cards = agent_state.generated_resources.get(node_id, [])
    return JSONResponse({
        "status": "generated",
        "node_id": node_id,
        "cards": [c.model_dump() for c in cards],
    })


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
# Keep the historical synchronous five-card handler unreachable as well: a direct
# import of its old name must use the resource-service bridge instead of reviving
# the in-module generator retained above for source-history context.
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
            latest = await asyncio.to_thread(resource_service.get_generation_job, job_id, user_id=user_id)
            if latest is None:
                return
            if str(latest.get("status") or "") in terminal_statuses:
                # A completed job may have no new events only if an old client
                # reconnects after its terminal event; it has nothing left to wait for.
                return
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
