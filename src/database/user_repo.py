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

from .connection import db


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
        db.execute(
            """INSERT INTO users (user_id, email, password_hash, role, display_name, created_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, email.lower().strip(), password_hash, role, display_name or user_id, now),
        )
        db.commit()
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
        row = db.execute("SELECT id FROM users WHERE user_id = %s", (user_id,)).fetchone()
        if not row:
            return False
        db.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (password_hash, user_id))
        db.commit()
        return True

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
