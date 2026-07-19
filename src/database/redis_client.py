# -*- coding: utf-8 -*-
"""
Redis 会话与流控客户端
======================
高并发鉴权缓存、令牌黑名单、重放检测。
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

import redis

# 加载 .env（如果存在）
try:
    from dotenv import load_dotenv
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _ENV_PATH = os.path.join(_PROJECT_ROOT, "frontend", ".env")
    if os.path.exists(_ENV_PATH):
        load_dotenv(_ENV_PATH)
except ImportError:
    pass

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_client: Optional[redis.Redis] = None
_redis_backend = "uninitialized"
_last_connection_attempt = 0.0
_lock = threading.Lock()


def _is_production_environment() -> bool:
    value = (
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("NODE_ENV")
        or "development"
    )
    return str(value).strip().lower() in {"prod", "production"}


def get_redis() -> Optional[redis.Redis]:
    """获取 Redis 客户端；生产环境禁止降级到进程内 fakeredis。"""
    global _redis_client, _redis_backend, _last_connection_attempt
    if _redis_client is not None:
        if _redis_backend != "fakeredis" or not _is_production_environment():
            return _redis_client
        # 测试/开发进程内后端不能在切换到生产环境后继续被复用。
        _redis_client = None
        _redis_backend = "unavailable"
    with _lock:
        if _redis_client is not None:
            return _redis_client
        now = time.monotonic()
        if _redis_backend == "unavailable" and now - _last_connection_attempt < 5.0:
            return None
        _last_connection_attempt = now
        # 1. 尝试连接真实 Redis
        try:
            _redis_client = redis.from_url(REDIS_URL, socket_connect_timeout=3)
            _redis_client.ping()
            _redis_backend = "redis"
            print(f"[Redis] Connected: {REDIS_URL.split('@')[-1]}")
            return _redis_client
        except Exception:
            _redis_client = None
            _redis_backend = "unavailable"
        if _is_production_environment():
            print("[Redis] Unavailable - production fallback is disabled")
            return None
        # 2. 降级为 fakeredis（纯 Python，零配置）
        try:
            import fakeredis
            _redis_client = fakeredis.FakeRedis()
            _redis_client.ping()
            _redis_backend = "fakeredis"
            print("[Redis] Using fakeredis (in-process, zero-config)")
            return _redis_client
        except Exception:
            _redis_client = None
            _redis_backend = "unavailable"
        # 3. 完全不可用
        print("[Redis] Unavailable - session features disabled")
        return _redis_client


def redis_backend_status() -> str:
    """返回不含连接信息的有限后端状态。"""
    get_redis()
    return _redis_backend


def durable_redis_available() -> bool:
    """确认外部 Redis 可达；fakeredis 永远不满足生产就绪条件。"""
    client = get_redis()
    if client is None or _redis_backend != "redis":
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False


# ─── 便捷操作 ───


def blacklist_token(jti: str, ttl: int = 900) -> None:
    """将令牌 JTI 加入黑名单（默认 15 分钟 TTL）。"""
    r = get_redis()
    if r:
        try:
            r.setex(f"auth:blacklist:{jti}", ttl, "1")
        except Exception:
            try:
                from src.observability import incr_metric
                incr_metric("redis.blacklist_token.error")
            except Exception:
                pass


def is_blacklisted(jti: str) -> bool:
    """检查令牌是否已注销。生产环境下 Redis 不可用时 fail-closed（拒绝请求）。"""
    r = get_redis()
    if r:
        try:
            return bool(r.exists(f"auth:blacklist:{jti}"))
        except Exception:
            try:
                from src.observability import incr_metric
                incr_metric("redis.blacklist_check.error")
            except Exception:
                pass
            if _is_production_environment():
                return True  # fail-closed: treat as blacklisted when Redis fails
    elif _is_production_environment():
        try:
            from src.observability import incr_metric
            incr_metric("redis.blacklist_check.unavailable")
        except Exception:
            pass
        return True  # fail-closed: Redis unavailable in production
    return False


def mark_rotated(jti: str, ttl: int = 10) -> None:
    """标记令牌已轮转（10 秒软存活窗口，防重放）。"""
    r = get_redis()
    if r:
        try:
            r.setex(f"auth:rotated:{jti}", ttl, "1")
        except Exception:
            pass


def is_rotated(jti: str) -> bool:
    """检查令牌是否已被轮转（重放攻击检测）。生产环境下 Redis 不可用时 fail-closed。"""
    r = get_redis()
    if r:
        try:
            return bool(r.exists(f"auth:rotated:{jti}"))
        except Exception:
            try:
                from src.observability import incr_metric
                incr_metric("redis.rotation_check.error")
            except Exception:
                pass
            if _is_production_environment():
                return True  # fail-closed: treat as rotated when Redis fails
    elif _is_production_environment():
        try:
            from src.observability import incr_metric
            incr_metric("redis.rotation_check.unavailable")
        except Exception:
            pass
        return True  # fail-closed: Redis unavailable in production
    return False


def store_refresh_token(user_id: str, jti: str, session_id: str = "", ttl: int = 604800) -> None:
    """存储用户当前合法的 Refresh Token JTI。"""
    r = get_redis()
    if r:
        try:
            bounded_ttl = max(1, int(ttl))
            r.set(f"auth:refresh_token:{user_id}", jti, ex=bounded_ttl)
            if session_id:
                r.set(f"auth:refresh_token:{user_id}:{session_id}", jti, ex=bounded_ttl)
                r.sadd(f"auth:refresh_sessions:{user_id}", session_id)
                r.expire(f"auth:refresh_sessions:{user_id}", bounded_ttl)
        except Exception:
            pass


def is_refresh_token_active(user_id: str, session_id: str, jti: str) -> bool:
    """Check the Redis fast path for a device refresh token.

    ``False`` is authoritative only when Redis is reachable. Callers retain a
    persistent repository as the source of truth when this cache is absent.
    """
    r = get_redis()
    if r and session_id:
        try:
            value = r.get(f"auth:refresh_token:{user_id}:{session_id}")
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return value == jti
        except Exception:
            return False
    return False


def revoke_user_session(user_id: str, session_id: str) -> None:
    r = get_redis()
    if r:
        try:
            r.delete(f"auth:refresh_token:{user_id}:{session_id}")
            r.srem(f"auth:refresh_sessions:{user_id}", session_id)
        except Exception:
            pass


def revoke_all_user_sessions(user_id: str) -> None:
    """注销用户所有会话（检测到重放攻击时调用）。"""
    r = get_redis()
    if r:
        try:
            session_ids = r.smembers(f"auth:refresh_sessions:{user_id}") or set()
            keys = [f"auth:refresh_token:{user_id}", f"auth:refresh_sessions:{user_id}"]
            for session_id in session_ids:
                if isinstance(session_id, bytes):
                    session_id = session_id.decode("utf-8")
                keys.append(f"auth:refresh_token:{user_id}:{session_id}")
            r.delete(*keys)
        except Exception:
            try:
                from src.observability import incr_metric
                incr_metric("redis.revoke_all_sessions.error")
            except Exception:
                pass


def cache_action_token(token_hash: str, user_id: str, purpose: str, ttl: int) -> None:
    """Cache only a one-way action-token digest for fast expiry checks."""
    r = get_redis()
    if r:
        try:
            r.setex(f"auth:action:{purpose}:{token_hash}", ttl, user_id)
        except Exception:
            pass


def consume_cached_action_token(token_hash: str, purpose: str) -> Optional[str]:
    r = get_redis()
    if not r:
        return None
    key = f"auth:action:{purpose}:{token_hash}"
    try:
        pipe = r.pipeline()
        pipe.get(key)
        pipe.delete(key)
        value, _ = pipe.execute()
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return str(value) if value else None
    except Exception:
        return None
