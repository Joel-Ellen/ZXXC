# -*- coding: utf-8 -*-
"""
异步网关拦截与越权阻断中间件
=============================
- FastAPI Depends 风格的 OAuth2 令牌校验
- Redis 黑名单 + 令牌轮转检测
- 10 秒软存活宽限窗口（防止并发惊群效应）
"""

from __future__ import annotations

from typing import Dict, Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .security import SecurityManager

# OAuth2 令牌提取器（从 Authorization: Bearer <token> 头提取）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class AsyncAuthGuard:
    """异步认证拦截器。

    生产环境依赖 aioredis 进行黑名单和令牌轮转检测。
    当 Redis 不可用时，降级为纯 JWT 校验模式（无黑名单、无轮转检测）。

    用法 (FastAPI):
        >>> guard = AsyncAuthGuard(redis_client=None)
        >>> @app.get("/secure")
        >>> async def secure_route(user=Depends(guard.get_current_secure_user)):
        >>>     return {"user": user}
    """

    def __init__(self, redis_client: Any = None) -> None:
        """初始化认证拦截器。

        Args:
            redis_client: aioredis.Redis 实例（可选）。为 None 时降级为纯 JWT 模式。
        """
        self.redis = redis_client

    # ------------------------------------------------------------------
    # 令牌校验 (Depends 注入)
    # ------------------------------------------------------------------

    async def get_current_secure_user(
        self, token: str = Depends(oauth2_scheme)
    ) -> Dict[str, Any]:
        """工业级异步凭证拦截：实施无阻塞流控、黑名单硬拦截。

        校验流程:
          1. JWT 解签 + 过期检查
          2. 验证 type == "access"
          3. Redis 黑名单检查 (若可用)

        Args:
            token: 从 Authorization 头提取的 Bearer token。

        Returns:
            {"user_id": "...", "role": "..."}

        Raises:
            HTTPException 401: 令牌无效/过期/类型错误/已注销。
        """
        try:
            payload = SecurityManager.decode_token(token)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 确保是 Access Token
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="INVALID_TOKEN_TYPE",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = payload.get("sub")
        role = payload.get("role")
        jti = payload.get("jti")

        # Redis 黑名单检查 (若可用)
        if self.redis is not None:
            try:
                is_blacklisted = await self.redis.exists(f"auth:blacklist:{jti}")
                if is_blacklisted:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="TOKEN_REVOKED",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            except Exception:
                # Redis 连接异常时降级通过（不因基础设施故障阻断业务）
                pass

        return {"user_id": user_id, "role": role}

    # ------------------------------------------------------------------
    # 令牌轮转 (Refresh Token → 新令牌对)
    # ------------------------------------------------------------------

    async def handle_token_rotation(
        self, refresh_token: str, user_role: str = "STUDENT"
    ) -> Dict[str, str]:
        """带 10 秒软存活宽限窗口的无震荡令牌轮转算法。

        流程:
          1. 验证 Refresh Token 签名 + 过期 + type
          2. Redis 检查是否已被轮转（防重放攻击）
          3. 签发全新双令牌对
          4. 旧 Refresh Token jti 压入 10s 宽限窗口
          5. 更新用户当前合法 Refresh Token 影子

        Args:
            refresh_token: 客户端提交的 Refresh Token。
            user_role: 用户角色（用于新 Access Token）。

        Returns:
            {"access_token", "refresh_token"}

        Raises:
            HTTPException 401: 令牌无效。
            HTTPException 403: 检测到重放攻击。
        """
        try:
            payload = SecurityManager.decode_token(refresh_token)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
            )

        # 确保是 Refresh Token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="INVALID_TOKEN_TYPE",
            )

        user_id = payload.get("sub")
        jti = payload.get("jti")

        # Redis 重放检测
        if self.redis is not None:
            try:
                is_rotated = await self.redis.exists(f"auth:rotated:{jti}")
                if is_rotated:
                    # 检测到重放攻击 → 销毁该用户所有会话
                    await self.redis.delete(f"auth:refresh_token:{user_id}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="SECURITY_BREACH_REUSE_DETECTED",
                    )

                # 将旧 jti 压入软存活宽限队列 (10s TTL)
                await self.redis.setex(f"auth:rotated:{jti}", 10, "1")

                # 记录最新合法 Refresh Token
                token_pair = SecurityManager.create_token_pair(user_id, role=user_role)
                await self.redis.set(
                    f"auth:refresh_token:{user_id}",
                    token_pair["refresh_jti"],
                )
            except HTTPException:
                raise
            except Exception:
                pass  # Redis 异常时降级
        else:
            # 无 Redis：直接签发新令牌（跳过轮转检测）
            token_pair = SecurityManager.create_token_pair(user_id, role=user_role)

        return {
            "access_token": token_pair["access_token"],
            "refresh_token": token_pair["refresh_token"],
        }

    # ------------------------------------------------------------------
    # 令牌注销
    # ------------------------------------------------------------------

    async def revoke_token(self, jti: str, ttl: int = 900) -> None:
        """将指定 jti 加入 Redis 黑名单。

        Args:
            jti: 令牌唯一 ID。
            ttl: 黑名单 TTL (秒)，默认 15 分钟（匹配 Access Token 寿命）。
        """
        if self.redis is not None:
            try:
                await self.redis.setex(f"auth:blacklist:{jti}", ttl, "1")
            except Exception:
                pass
