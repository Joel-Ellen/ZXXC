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
import secrets
import threading
import time
import uuid
import asyncio
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
configure_logging()


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
from src.graph import get_kg_manager

_kg = get_kg_manager()


def _get_node_title(node_id: str, default: Optional[str] = None) -> str:
    """鑾峰彇鑺傜偣鏍囬銆?"""
    return _kg.get_node_title(node_id) or default or node_id


# Canonical copies live in src/application/_common.py; re-exported here for
# tests and legacy importers.
from src.application._common import (  # noqa: E402
    MASTERY_ADVANCE_THRESHOLD,
    RESOURCE_CARD_ORDER,
    RESOURCE_CONTRACT_VERSION,
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


# ─── API 端点 ────────────────────────────────────────────────


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


# Keep legacy import names on the truthful session-service boundary. The old
# in-module demo handlers were removed; these bridges are the only handlers.
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

# ``new_routes`` is now health + a few read-only debug endpoints. The retired
# synchronous resource-generation paths no longer exist there, but keep the
# filter as a guard so they can never be mounted again: the canonical session
# API owns resource generation now.
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
