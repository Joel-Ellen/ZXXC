# -*- coding: utf-8 -*-
"""
PostgreSQL 数据库连接管理
========================
线程安全连接池 + 自动建表 + 存量 JSON 数据迁移。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Mapping, Optional

import psycopg2
import psycopg2.extras

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    _ENV_PATH = os.path.join(_PROJECT_ROOT, "frontend", ".env")
    if os.path.exists(_ENV_PATH):
        load_dotenv(_ENV_PATH)
except ImportError:
    pass

# 数据库连接配置（环境变量优先）
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/eduagent",
)

# 旧 JSON 文件路径（用于迁移）
_OLD_USERS_PATH = os.path.join(_PROJECT_ROOT, "src", "auth", "_users.json")
_OLD_ENROLLMENTS_PATH = os.path.join(_PROJECT_ROOT, "frontend", "_enrollments.json")

_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})


def is_production_environment(environment: Optional[Mapping[str, str]] = None) -> bool:
    """Return whether legacy development data must be kept out of this process."""
    source = os.environ if environment is None else environment
    values = (source.get("APP_ENV"), source.get("ENVIRONMENT"), source.get("NODE_ENV"))
    return any(
        str(value).strip().lower() in _PRODUCTION_ENVIRONMENTS
        for value in values
        if value is not None
    )


def legacy_json_migrations_enabled(environment: Optional[Mapping[str, str]] = None) -> bool:
    """Legacy fixture migration is a development-only compatibility path."""
    return not is_production_environment(environment)


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL UNIQUE,
    email           VARCHAR(256) NOT NULL,
    password_hash   VARCHAR(256) NOT NULL,
    role            VARCHAR(16) NOT NULL DEFAULT 'STUDENT',
    display_name    VARCHAR(128) NOT NULL DEFAULT '',
    created_at      VARCHAR(64) NOT NULL,
    last_login_at   VARCHAR(64),
    is_active       SMALLINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_courses (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    course_id       VARCHAR(64) NOT NULL,
    enrolled_at     VARCHAR(64) NOT NULL,
    progress        DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    completed_nodes INTEGER NOT NULL DEFAULT 0,
    is_active       SMALLINT NOT NULL DEFAULT 0,
    UNIQUE(user_id, course_id)
);

CREATE TABLE IF NOT EXISTS user_state (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    course_id       VARCHAR(64) NOT NULL,
    state_json      JSONB NOT NULL,
    cold_state_json JSONB,
    updated_at      VARCHAR(64) NOT NULL,
    UNIQUE(user_id, course_id)
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id                         VARCHAR(64) PRIMARY KEY,
    university                      VARCHAR(256) NOT NULL DEFAULT '',
    major                           VARCHAR(256) NOT NULL DEFAULT '',
    grade                           VARCHAR(64) NOT NULL DEFAULT '',
    learning_goal                   TEXT NOT NULL DEFAULT '',
    weekly_study_hours              INTEGER NOT NULL DEFAULT 6,
    preferred_resource_style        VARCHAR(32) NOT NULL DEFAULT 'textual',
    preferred_pace                  VARCHAR(32) NOT NULL DEFAULT 'steady',
    preferred_practice_intensity    VARCHAR(32) NOT NULL DEFAULT 'balanced',
    updated_at                      VARCHAR(64) NOT NULL
);

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS university VARCHAR(256) NOT NULL DEFAULT '';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS major VARCHAR(256) NOT NULL DEFAULT '';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS grade VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS learning_goal TEXT NOT NULL DEFAULT '';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS weekly_study_hours INTEGER NOT NULL DEFAULT 6;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_resource_style VARCHAR(32) NOT NULL DEFAULT 'textual';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_pace VARCHAR(32) NOT NULL DEFAULT 'steady';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_practice_intensity VARCHAR(32) NOT NULL DEFAULT 'balanced';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS updated_at VARCHAR(64) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_active_email_normalized
    ON users (LOWER(email)) WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_user_courses_user_id ON user_courses(user_id);
CREATE INDEX IF NOT EXISTS idx_user_state_user_course ON user_state(user_id, course_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);
"""


class Database:
    """线程安全的 PostgreSQL 数据库单例。"""

    def __init__(self):
        self._local = threading.local()
        self._initialized = False

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------

    def _get_conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None or self._local.conn.closed:
            self._local.conn = psycopg2.connect(DATABASE_URL)
            self._local.conn.autocommit = False
        return self._local.conn

    @property
    def conn(self):
        return self._get_conn()

    def execute(self, sql: str, params=()):
        self._ensure_init()
        conn = self._get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return _CursorWrapper(cur, conn)

    def commit(self):
        if self._initialized:
            self._get_conn().commit()

    def rollback(self):
        if hasattr(self._local, "conn") and self._local.conn is not None and not self._local.conn.closed:
            self._local.conn.rollback()

    # ------------------------------------------------------------------
    # 初始化 + 迁移
    # ------------------------------------------------------------------

    def _ensure_init(self):
        """延迟初始化：首次访问数据库时才连接和建表。"""
        if self._initialized:
            return
        conn = None
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(CREATE_TABLES_SQL)
            conn.commit()
            cur.close()
            print(f"[DB] PostgreSQL connected: {DATABASE_URL.split('@')[-1]}")
            self._initialized = True
            if legacy_json_migrations_enabled():
                self._migrate_users()
                self._migrate_enrollments()
            else:
                print("[DB] Legacy JSON migrations disabled in production")
        except Exception as e:
            self._initialized = False
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[DB] PostgreSQL connection failed: {e}")
            print("[DB] Set DATABASE_URL env or ensure PostgreSQL is running")
            raise

    def _migrate_users(self):
        if not os.path.exists(_OLD_USERS_PATH):
            return
        count = self.execute("SELECT COUNT(*) as n FROM users").fetchone()["n"]
        if count > 0:
            return
        try:
            with open(_OLD_USERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            migrated = 0
            for uid, rec in data.items():
                self.execute(
                    """INSERT INTO users (user_id, email, password_hash, role, display_name, created_at, last_login_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        rec.get("user_id", uid),
                        str(rec.get("email", "") or "").lower().strip(),
                        rec.get("password_hash", ""),
                        rec.get("role", "STUDENT"),
                        rec.get("display_name", uid),
                        rec.get("created_at", datetime.now(timezone.utc).isoformat()),
                        rec.get("last_login_at"),
                    ),
                )
                migrated += 1
            self.commit()
            os.rename(_OLD_USERS_PATH, _OLD_USERS_PATH + ".bak")
            print(f"[DB] Migrated {migrated} users from _users.json")
        except psycopg2.IntegrityError:
            self.rollback()
            raise
        except Exception as e:
            self.rollback()
            print(f"[DB] User migration skipped: {e}")

    def _migrate_enrollments(self):
        if not os.path.exists(_OLD_ENROLLMENTS_PATH):
            return
        count = self.execute("SELECT COUNT(*) as n FROM user_courses").fetchone()["n"]
        if count > 0:
            return
        try:
            with open(_OLD_ENROLLMENTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            migrated = 0
            for uid, info in data.items():
                active = info.get("active_course", "")
                for cid, cinfo in info.get("courses", {}).items():
                    self.execute(
                        """INSERT INTO user_courses (user_id, course_id, enrolled_at, progress, completed_nodes, is_active)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (
                            uid, cid,
                            cinfo.get("enrolled_at", datetime.now(timezone.utc).isoformat()),
                            cinfo.get("progress", 0.0),
                            cinfo.get("completed_nodes", 0),
                            1 if cid == active else 0,
                        ),
                    )
                    migrated += 1
            self.commit()
            os.rename(_OLD_ENROLLMENTS_PATH, _OLD_ENROLLMENTS_PATH + ".bak")
            print(f"[DB] Migrated {migrated} enrollments from _enrollments.json")
        except psycopg2.IntegrityError:
            self.rollback()
            raise
        except Exception as e:
            self.rollback()
            print(f"[DB] Enrollment migration skipped: {e}")


class _CursorWrapper:
    """将 psycopg2 cursor 包装为与 sqlite3.Row 兼容的接口。"""

    def __init__(self, cur, conn):
        self._cur = cur
        self._conn = conn

    def fetchone(self):
        row = self._cur.fetchone()
        self._cur.close()
        self._conn.commit()
        return row

    def fetchall(self):
        rows = self._cur.fetchall()
        self._cur.close()
        self._conn.commit()
        return rows


# 全局单例
db = Database()
