# -*- coding: utf-8 -*-
"""
用户数据仓库
===========
PostgreSQL 持久化存储。
接口与 UserStore 兼容。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import psycopg2

from .connection import db


_ACTIVE_EMAIL_UNIQUE_INDEX = "uq_users_active_email_normalized"
_UNIQUE_VIOLATION = "23505"


def _is_unique_violation(exc: psycopg2.IntegrityError) -> bool:
    return isinstance(exc, psycopg2.errors.UniqueViolation) or getattr(exc, "pgcode", None) == _UNIQUE_VIOLATION


def _rollback_failed_write() -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _create_conflict_message(exc: psycopg2.IntegrityError, user_id: str, email: str) -> str:
    constraint = str(getattr(getattr(exc, "diag", None), "constraint_name", "") or "")
    if constraint == _ACTIVE_EMAIL_UNIQUE_INDEX or "email" in constraint:
        return f"邮箱 '{email}' 已被注册"
    if constraint == "users_user_id_key" or "user_id" in constraint:
        return f"用户名 '{user_id}' 已存在"
    return "用户名或邮箱已被注册"


class UserRepo:
    """PostgreSQL 用户持久化存储。

    线程安全（依赖 psycopg2 连接级线程隔离）。
    公开接口与 src.auth.models.UserStore 完全兼容。
    """

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_by_id(self, user_id: str) -> Optional[dict]:
        row = db.execute(
            "SELECT * FROM users WHERE user_id = %s AND is_active = 1",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_by_email(self, email: str) -> Optional[dict]:
        row = db.execute(
            "SELECT * FROM users WHERE email = %s AND is_active = 1",
            (email.lower().strip(),),
        ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> List[dict]:
        rows = db.execute(
            "SELECT user_id, email, role, display_name, created_at, last_login_at FROM users WHERE is_active = 1"
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        row = db.execute("SELECT COUNT(*) as n FROM users WHERE is_active = 1").fetchone()
        return row["n"] if row else 0

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def create_user(
        self,
        user_id: str,
        email: str,
        password: str,
        role: str = "STUDENT",
        display_name: str = "",
    ) -> dict:
        from src.auth.security import SecurityManager
        existing = self.get_by_id(user_id)
        if existing:
            raise ValueError(f"用户名 '{user_id}' 已存在")
        existing_email = self.get_by_email(email)
        if existing_email:
            raise ValueError(f"邮箱 '{email}' 已被注册")

        password_hash = SecurityManager.hash_password(password)
        now = datetime.now(timezone.utc).isoformat()
        normalized_email = email.lower().strip()
        try:
            db.execute(
                """INSERT INTO users (user_id, email, password_hash, role, display_name, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (user_id, normalized_email, password_hash, role, display_name or user_id, now),
            )
            db.commit()
        except psycopg2.IntegrityError as exc:
            _rollback_failed_write()
            if not _is_unique_violation(exc):
                raise
            raise ValueError(_create_conflict_message(exc, user_id, normalized_email)) from exc
        return self.get_by_id(user_id)

    def verify_login(self, user_id: str, password: str) -> Optional[dict]:
        """验证登录凭证（含密码校验 + 等时退避）。"""
        from src.auth.security import SecurityManager
        row = db.execute(
            "SELECT * FROM users WHERE user_id = %s AND is_active = 1",
            (user_id,),
        ).fetchone()
        if row is None:
            SecurityManager.execute_constant_time_fallback()
            return None
        user = dict(row)
        if not SecurityManager.verify_password(password, user["password_hash"]):
            return None
        self.update_last_login(user_id)
        return user

    def update_last_login(self, user_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        db.execute("UPDATE users SET last_login_at = %s WHERE user_id = %s", (now, user_id))
        db.commit()

    def update_password(self, user_id: str, password_hash: str) -> bool:
        """Update a pre-hashed password (legacy repository contract)."""
        row = db.execute("SELECT id FROM users WHERE user_id = %s", (user_id,)).fetchone()
        if not row:
            return False
        db.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (password_hash, user_id))
        db.commit()
        return True

    def update_password_plaintext(self, user_id: str, new_password: str) -> bool:
        """Explicit plaintext adapter used by password-reset flows."""
        from src.auth.security import SecurityManager

        return self.update_password(user_id, SecurityManager.hash_password(new_password))

    def update_public_profile(
        self,
        user_id: str,
        *,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Optional[dict]:
        current = self.get_by_id(user_id)
        if current is None:
            return None
        next_email = current["email"] if email is None else email.lower().strip()
        if "@" not in next_email:
            raise ValueError("邮箱格式无效")
        conflict = db.execute(
            "SELECT user_id FROM users WHERE email = %s AND user_id <> %s AND is_active = 1",
            (next_email, user_id),
        ).fetchone()
        if conflict:
            raise ValueError(f"邮箱 '{next_email}' 已被注册")
        next_name = current.get("display_name", user_id) if display_name is None else display_name.strip() or user_id
        try:
            db.execute(
                "UPDATE users SET email = %s, display_name = %s WHERE user_id = %s AND is_active = 1",
                (next_email, next_name, user_id),
            )
            db.commit()
        except psycopg2.IntegrityError as exc:
            _rollback_failed_write()
            if not _is_unique_violation(exc):
                raise
            raise ValueError(f"邮箱 '{next_email}' 已被注册") from exc
        return self.get_by_id(user_id)

    def delete_user(self, user_id: str) -> bool:
        """Anonymize and deactivate the base identity record."""
        row = db.execute("SELECT id FROM users WHERE user_id = %s AND is_active = 1", (user_id,)).fetchone()
        if not row:
            return False
        now = datetime.now(timezone.utc).isoformat()
        anonymous_email = f"deleted+{row['id']}@invalid.local"
        anonymous_user_id = f"deleted_{row['id']}"
        db.execute(
            """UPDATE users SET user_id = %s, email = %s, password_hash = '', display_name = 'Deleted user',
                      last_login_at = %s, is_active = 0
               WHERE user_id = %s""",
            (anonymous_user_id, anonymous_email, now, user_id),
        )
        db.commit()
        return True

    def delete_domain_data(self, user_id: str) -> None:
        """Best-effort removal from optional legacy user-owned tables."""
        tables = (
            "user_course_profiles",
            "agent_task_logs",
            "evaluation_reports",
            "quiz_records",
            "conversation_history",
            "generated_resources",
            "student_profiles",
        )
        paths_exist = db.execute("SELECT to_regclass('learning_paths') AS name").fetchone()
        tasks_exist = db.execute("SELECT to_regclass('learning_tasks') AS name").fetchone()
        if paths_exist and paths_exist.get("name") and tasks_exist and tasks_exist.get("name"):
            db.execute(
                "DELETE FROM learning_tasks WHERE path_id IN (SELECT id FROM learning_paths WHERE user_id = %s)",
                (user_id,),
            )
            db.commit()
        for table in tables:
            exists = db.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
            if not exists or not exists.get("name"):
                continue
            has_user_id = db.execute(
                """SELECT 1 FROM information_schema.columns
                   WHERE table_schema = current_schema() AND table_name = %s AND column_name = 'user_id'""",
                (table,),
            ).fetchone()
            if has_user_id:
                db.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))
                db.commit()
        if paths_exist and paths_exist.get("name"):
            db.execute("DELETE FROM learning_paths WHERE user_id = %s", (user_id,))
            db.commit()

    def ensure_presets(self, presets: List[dict], hash_fn=None) -> List[dict]:
        created = []
        for p in presets:
            existing = self.get_by_id(p["user_id"])
            if existing:
                created.append(existing)
            else:
                user = self.create_user(
                    user_id=p["user_id"],
                    email=p["email"],
                    password=p["password"],
                    role=p.get("role", "STUDENT"),
                    display_name=p.get("display_name", p["user_id"]),
                )
                created.append(user)
        return created
