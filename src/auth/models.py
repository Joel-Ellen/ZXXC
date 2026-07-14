# -*- coding: utf-8 -*-
"""
用户数据模型与持久化存储
========================
- JSON 文件持久化用户存储
- Pydantic v2 用户记录模型
- 预设初始账号
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict, Optional, List
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from .security import SecurityManager


# ============================================================================
# 用户记录模型
# ============================================================================

class UserRecord(BaseModel):
    """单个用户的持久化记录。"""

    user_id: str = Field(..., min_length=1, description="用户唯一 ID (用户名)")
    email: str = Field(..., description="用户邮箱")
    password_hash: str = Field(..., description="Argon2id 密码哈希")
    role: str = Field(default="STUDENT", pattern=r"^(STUDENT|ADMIN|TEACHER)$")
    display_name: str = Field(default="", description="显示名称")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="注册时间 ISO 时间戳",
    )
    last_login_at: Optional[str] = Field(default=None, description="最近登录时间")

    @field_validator("email")
    @classmethod
    def email_must_contain_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("邮箱格式无效")
        return v.lower().strip()

    def to_safe_dict(self) -> Dict[str, object]:
        """返回不含密码哈希的安全字典（用于 API 响应）。"""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
        }


# ============================================================================
# 用户存储 (JSON 文件)
# ============================================================================

class UserStore:
    """JSON 文件持久化用户存储。

    线程安全 (读写锁)，支持按 ID 和邮箱查找。
    """

    DEFAULT_STORE_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "_users.json"
    )

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file_path = file_path or self.DEFAULT_STORE_PATH
        self._lock = threading.RLock()
        self._users: Dict[str, UserRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_user(
        self, user_id: str, email: str, password: str,
        role: str = "STUDENT", display_name: str = ""
    ) -> UserRecord:
        """创建新用户。

        Raises:
            ValueError: 用户名或邮箱已存在。
        """
        with self._lock:
            # 检查用户名唯一性
            if user_id in self._users:
                raise ValueError(f"用户名 '{user_id}' 已存在")

            # 检查邮箱唯一性
            for u in self._users.values():
                if u.email == email.lower().strip():
                    raise ValueError(f"邮箱 '{email}' 已被注册")

            record = UserRecord(
                user_id=user_id,
                email=email,
                password_hash=SecurityManager.hash_password(password),
                role=role,
                display_name=display_name or user_id,
            )
            self._users[user_id] = record
            self._save()
            return record

    def get_by_id(self, user_id: str) -> Optional[UserRecord]:
        """按用户 ID 查找。"""
        with self._lock:
            return self._users.get(user_id)

    def get_by_email(self, email: str) -> Optional[UserRecord]:
        """按邮箱查找。"""
        with self._lock:
            target = email.lower().strip()
            for u in self._users.values():
                if u.email == target:
                    return u
            return None

    def verify_login(self, user_id: str, password: str) -> Optional[UserRecord]:
        """验证登录凭证。

        Returns:
            UserRecord 若验证通过，否则 None。
        """
        user = self.get_by_id(user_id)
        if user is None:
            # 等时退避：即使用户不存在也执行完整 Argon2 验证
            SecurityManager.execute_constant_time_fallback()
            return None

        if SecurityManager.verify_password(password, user.password_hash):
            # 更新最近登录时间
            with self._lock:
                user.last_login_at = datetime.now(timezone.utc).isoformat()
                self._save()
            return user

        return None

    def update_password(self, user_id: str, new_password: str) -> bool:
        """更新用户密码。"""
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                return False
            user.password_hash = SecurityManager.hash_password(new_password)
            self._save()
            return True

    def update_public_profile(
        self,
        user_id: str,
        *,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Optional[UserRecord]:
        """Update the user-owned public identity fields with uniqueness checks."""
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                return None
            if email is not None:
                normalized = email.lower().strip()
                if "@" not in normalized:
                    raise ValueError("邮箱格式无效")
                if any(item.user_id != user_id and item.email == normalized for item in self._users.values()):
                    raise ValueError(f"邮箱 '{normalized}' 已被注册")
                user.email = normalized
            if display_name is not None:
                user.display_name = display_name.strip() or user_id
            self._save()
            return user

    def delete_user(self, user_id: str) -> bool:
        """Delete a JSON-backed user record after related data is cleaned."""
        with self._lock:
            if user_id not in self._users:
                return False
            self._users.pop(user_id, None)
            self._save()
            return True

    def list_users(self) -> List[Dict[str, object]]:
        """列出所有用户（安全信息）。"""
        with self._lock:
            return [u.to_safe_dict() for u in self._users.values()]

    def count(self) -> int:
        with self._lock:
            return len(self._users)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """从 JSON 文件加载用户数据。"""
        if not os.path.exists(self._file_path):
            self._users = {}
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._users = {
                uid: UserRecord(**rec) for uid, rec in data.items()
            }
        except (json.JSONDecodeError, KeyError):
            self._users = {}

    def _save(self) -> None:
        """保存用户数据到 JSON 文件。"""
        data = {uid: rec.model_dump() for uid, rec in self._users.items()}
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================================
# 预设初始账号
# ============================================================================

class PresetAccounts:
    """预设初始账号管理。

    在首次启动时自动创建默认管理员和学生账号。

    预设账号:
      - admin / Admin@2026!  (管理员)
      - student / Learn@2026 (学生)
    """

    PRESET_USERS = [
        {
            "user_id": "admin",
            "email": "admin@eduagent.local",
            "password": "Admin@2026!",
            "role": "ADMIN",
            "display_name": "系统管理员",
        },
        {
            "user_id": "student",
            "email": "student@eduagent.local",
            "password": "Learn@2026",
            "role": "STUDENT",
            "display_name": "测试学生",
        },
    ]

    @classmethod
    def ensure_presets(cls, store: UserStore) -> List[UserRecord]:
        """确保预设账号存在（首次调用时创建）。

        Args:
            store: UserStore 实例。

        Returns:
            创建/已存在的预设用户列表。
        """
        created = []
        for preset in cls.PRESET_USERS:
            existing = store.get_by_id(preset["user_id"])
            if existing is None:
                user = store.create_user(
                    user_id=preset["user_id"],
                    email=preset["email"],
                    password=preset["password"],
                    role=preset["role"],
                    display_name=preset["display_name"],
                )
                created.append(user)
            else:
                created.append(existing)
        return created

    @classmethod
    def ensure_presets_db(cls, repo) -> list:
        """确保预设账号存在（数据库版本）。"""
        return repo.ensure_presets(cls.PRESET_USERS)
