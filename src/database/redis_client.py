# -*- coding: utf-8 -*-
"""
Redis 会话与流控客户端
======================
高并发鉴权缓存、令牌黑名单、重放检测。
"""

from __future__ import annotations

import os
import threading
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
_lock = threading.Lock()


def get_redis() -> Optional[redis.Redis]:
    """获取 Redis 客户端（惰性初始化，连接失败则自动降级为 fakeredis）。"""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    with _lock:
        if _redis_client is not None:
            return _redis_client
        # 1. 尝试连接真实 Redis
        try:
            _redis_client = redis.from_url(REDIS_URL, socket_connect_timeout=3)
            _redis_client.ping()
            print(f"[Redis] Connected: {REDIS_URL.split('@')[-1]}")
            return _redis_client
        except Exception:
            pass
        # 2. 降级为 fakeredis（纯 Python，零配置）
        try:
            import fakeredis
            _redis_client = fakeredis.FakeRedis()
            _redis_client.ping()
            print("[Redis] Using fakeredis (in-process, zero-config)")
            return _redis_client
        except Exception:
            pass
        # 3. 完全不可用
        print("[Redis] Unavailable — session features disabled")
        _redis_client = None
        return _redis_client


# ─── 便捷操作 ───


def blacklist_token(jti: str, ttl: int = 900) -> None:
    """将令牌 JTI 加入黑名单（默认 15 分钟 TTL）。"""
    r = get_redis()
    if r:
        try:
            r.setex(f"auth:blacklist:{jti}", ttl, "1")
        except Exception:
            pass


def is_blacklisted(jti: str) -> bool:
    """检查令牌是否已注销。"""
    r = get_redis()
    if r:
        try:
            return bool(r.exists(f"auth:blacklist:{jti}"))
        except Exception:
            pass
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
    """检查令牌是否已被轮转（重放攻击检测）。"""
    r = get_redis()
    if r:
        try:
            return bool(r.exists(f"auth:rotated:{jti}"))
        except Exception:
            pass
    return False


def store_refresh_token(user_id: str, jti: str) -> None:
    """存储用户当前合法的 Refresh Token JTI。"""
    r = get_redis()
    if r:
        try:
            r.set(f"auth:refresh_token:{user_id}", jti)
        except Exception:
            pass


def revoke_all_user_sessions(user_id: str) -> None:
    """注销用户所有会话（检测到重放攻击时调用）。"""
    r = get_redis()
    if r:
        try:
            r.delete(f"auth:refresh_token:{user_id}")
        except Exception:
            pass
