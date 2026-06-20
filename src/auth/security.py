# -*- coding: utf-8 -*-
"""
核心密码学与安全配置组件
=========================
- Argon2id 高强度密码哈希 (memory=65536, time=3, parallelism=4)
- JWT 双轨令牌 (Access Token 15min + Refresh Token 7day)
- 等时退避计算 (防止用户名枚举计时攻击)
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import jwt

# Argon2id 配置: memory=65536 (64MB), time=3, parallelism=4
ph = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=4)

# 伪密码哈希密文 — 用于等时退避，防止用户名枚举
FAKE_HASH = ph.hash("stabled_dummy_password_for_constant_time")

# JWT 配置
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "prod_secret_sign_key_997126_edu_agent")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


class SecurityManager:
    """密码哈希与 JWT 令牌管理。"""

    # ------------------------------------------------------------------
    # 密码哈希
    # ------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        """对原始密码执行高强度单向哈希加盐 (Argon2id)。"""
        return ph.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证明文密码与哈希密文是否对齐。"""
        try:
            return ph.verify(hashed_password, plain_password)
        except VerifyMismatchError:
            return False

    @staticmethod
    def execute_constant_time_fallback() -> None:
        """执行等时退避计算，抹平用户名不存在时的响应时差。

        调用方式:
            当用户登录时用户名不存在，调用此方法后再返回 401。
            这样攻击者无法通过计时分析判断用户名是否有效。
        """
        try:
            ph.verify(FAKE_HASH, "invalid_match_trigger")
        except VerifyMismatchError:
            pass  # 预期行为

    # ------------------------------------------------------------------
    # JWT 令牌
    # ------------------------------------------------------------------

    @staticmethod
    def create_token_pair(user_id: str, role: str) -> Dict[str, str]:
        """签发双轨安全令牌对 (Access + Refresh)。

        Access Token:
          - 短寿命 (默认 15min)
          - 包含 role 和 type="access"
          - 唯一 jti 用于黑名单注销

        Refresh Token:
          - 长寿命 (默认 7day)
          - type="refresh"
          - 唯一 jti 用于轮转检测

        Args:
            user_id: 用户唯一 ID。
            role: 用户角色 (如 STUDENT / ADMIN)。

        Returns:
            {"access_token", "refresh_token", "access_jti", "refresh_jti"}
        """
        now = datetime.now(timezone.utc)

        # 1. Access Token
        access_jti = str(uuid.uuid4())
        access_expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_payload = {
            "sub": user_id,
            "role": role,
            "exp": access_expire,
            "jti": access_jti,
            "type": "access",
        }

        # 2. Refresh Token
        refresh_jti = str(uuid.uuid4())
        refresh_expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_payload = {
            "sub": user_id,
            "exp": refresh_expire,
            "jti": refresh_jti,
            "type": "refresh",
        }

        return {
            "access_token": jwt.encode(access_payload, JWT_SECRET_KEY, algorithm=ALGORITHM),
            "refresh_token": jwt.encode(refresh_payload, JWT_SECRET_KEY, algorithm=ALGORITHM),
            "access_jti": access_jti,
            "refresh_jti": refresh_jti,
        }

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """Token 解签与有效期校验。

        Returns:
            Decoded payload dict.

        Raises:
            ValueError("TOKEN_EXPIRED"): 令牌已过期。
            ValueError("TOKEN_INVALID"): 令牌无效（签名不匹配/格式错误）。
        """
        try:
            return jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise ValueError("TOKEN_EXPIRED")
        except jwt.InvalidTokenError:
            raise ValueError("TOKEN_INVALID")
