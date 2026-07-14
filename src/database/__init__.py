# -*- coding: utf-8 -*-
"""
EduAgent Database Layer
=======================
PostgreSQL + Neo4j + Redis + SQLAlchemy async 多层持久化存储。
"""

from .connection import db
from .user_repo import UserRepo
from .user_profile_repo import UserProfileRepo, JsonUserProfileRepo
from .account_repo import AccountRepo, JsonAccountRepo
from .enrollment_repo import EnrollmentRepo
from .state_repo import StateRepo
from .session_repo import SessionRepo
from .session_snapshot_repo import SessionSnapshotRepo
from .redis_client import (
    get_redis, blacklist_token, is_blacklisted,
    mark_rotated, is_rotated, store_refresh_token, is_refresh_token_active,
    revoke_user_session, revoke_all_user_sessions, cache_action_token,
    consume_cached_action_token,
)

# 异步 SQLAlchemy 层（合并自 backend/models/）
from .async_session import get_engine, get_async_session, init_db, get_db
from .profile_repo import ProfileRepo
from .resource_repo import ResourceRepo
from .evaluation_repo import EvaluationRepo

__all__ = [
    # sync layer
    "db", "UserRepo", "UserProfileRepo", "JsonUserProfileRepo", "AccountRepo", "JsonAccountRepo",
    "EnrollmentRepo", "StateRepo", "SessionRepo", "SessionSnapshotRepo",
    "get_redis", "blacklist_token", "is_blacklisted",
    "mark_rotated", "is_rotated", "store_refresh_token", "is_refresh_token_active",
    "revoke_user_session", "revoke_all_user_sessions", "cache_action_token",
    "consume_cached_action_token",
    # async layer
    "get_engine", "get_async_session", "init_db", "get_db",
    "ProfileRepo", "ResourceRepo", "EvaluationRepo",
]
