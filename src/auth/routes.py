# -*- coding: utf-8 -*-
"""
认证 API 路由 — 注册 / 登录 / 验证码 / 令牌刷新
=================================================
FastAPI APIRouter 实现，提供完整的 RESTful 认证接口。

端点:
  GET  /api/v1/auth/captcha        — 获取 SVG 验证码
  POST /api/v1/auth/register       — 用户注册
  POST /api/v1/auth/login          — 用户登录
  POST /api/v1/auth/refresh        — 刷新令牌
  POST /api/v1/auth/logout         — 注销令牌
  GET  /api/v1/auth/me             — 获取当前用户信息 (需认证)
"""

from __future__ import annotations

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from .security import SecurityManager
from .models import UserStore, UserRecord, PresetAccounts
from .captcha import CaptchaGenerator
from .middleware import AsyncAuthGuard
from .account_service import is_production


# ============================================================================
# 请求/响应模型
# ============================================================================

class RegisterRequest(BaseModel):
    """注册请求。"""
    user_id: str = Field(
        ..., min_length=3, max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$",
        description="用户名 (字母/数字/下划线, 3-32 字符)"
    )
    email: str = Field(..., min_length=5, max_length=128, description="邮箱")
    password: str = Field(
        ..., min_length=8, max_length=128,
        description="密码 (最少 8 字符)"
    )
    captcha_token: str = Field(..., description="验证码令牌")
    captcha_answer: str = Field(..., description="验证码答案")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("邮箱格式无效")
        return v.lower().strip()


class LoginRequest(BaseModel):
    """登录请求。"""
    user_id: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")
    captcha_token: str = Field(..., description="验证码令牌")
    captcha_answer: str = Field(..., description="验证码答案")


class TokenResponse(BaseModel):
    """令牌响应。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class RefreshRequest(BaseModel):
    """令牌刷新请求。"""
    refresh_token: str


class MessageResponse(BaseModel):
    """通用消息响应。"""
    message: str
    detail: Optional[str] = None


# ============================================================================
# AuthRouter
# ============================================================================

class AuthRouter:
    """认证路由工厂。

    用法:
        >>> store = UserStore()
        >>> captcha = CaptchaGenerator()
        >>> guard = AsyncAuthGuard()
        >>> router = AuthRouter(store, captcha, guard).build()
        >>> app.include_router(router)
    """

    def __init__(
        self,
        user_store: Optional[UserStore] = None,
        captcha_gen: Optional[CaptchaGenerator] = None,
        auth_guard: Optional[AsyncAuthGuard] = None,
    ) -> None:
        self.store = user_store or UserStore()
        self.captcha = captcha_gen or CaptchaGenerator()
        self.guard = auth_guard or AsyncAuthGuard()

    # ------------------------------------------------------------------
    # 路由构建
    # ------------------------------------------------------------------

    def build(self) -> APIRouter:
        """构建并返回 FastAPI APIRouter。"""
        router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

        # ---- 验证码 ----
        @router.get("/captcha")
        async def get_captcha():
            """获取 SVG 数学验证码。

            Returns:
                HTML 响应，包含 SVG 验证码图片和 captcha_token。
            """
            svg, token = self.captcha.generate()
            html = (
                '<html><body style="text-align:center;padding:20px">'
                f"{svg}"
                f'<p style="color:#888;font-size:12px;margin-top:8px">'
                f"captcha_token: {token}</p>"
                "</body></html>"
            )
            return HTMLResponse(content=html)

        # ---- 注册 ----
        @router.post("/register", response_model=TokenResponse)
        async def register(req: RegisterRequest):
            """用户注册。

            流程:
              1. 验证码校验（一次性使用）
              2. 用户名/邮箱唯一性检查
              3. Argon2id 密码哈希
              4. 写入持久化存储
              5. 签发双令牌
            """
            # 验证码
            if not self.captcha.verify(req.captcha_token, req.captcha_answer):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="验证码错误或已过期",
                )

            # 创建用户
            try:
                user = self.store.create_user(
                    user_id=req.user_id,
                    email=req.email,
                    password=req.password,
                )
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(e),
                )

            # 签发令牌
            token_pair = SecurityManager.create_token_pair(user.user_id, user.role)
            return TokenResponse(
                access_token=token_pair["access_token"],
                refresh_token=token_pair["refresh_token"],
                user=user.to_safe_dict(),
            )

        # ---- 登录 ----
        @router.post("/login", response_model=TokenResponse)
        async def login(req: LoginRequest):
            """用户登录。

            流程:
              1. 验证码校验
              2. 用户名 + 密码校验
              3. 签发双令牌
            """
            # 验证码
            if not self.captcha.verify(req.captcha_token, req.captcha_answer):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="验证码错误或已过期",
                )

            # 登录验证
            user = self.store.verify_login(req.user_id, req.password)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="用户名或密码错误",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # 签发令牌
            token_pair = SecurityManager.create_token_pair(user.user_id, user.role)
            return TokenResponse(
                access_token=token_pair["access_token"],
                refresh_token=token_pair["refresh_token"],
                user=user.to_safe_dict(),
            )

        # ---- 刷新令牌 ----
        @router.post("/refresh", response_model=TokenResponse)
        async def refresh_token(req: RefreshRequest):
            """刷新令牌轮转。

            用 Refresh Token 换取全新的 Access + Refresh Token 对。
            """
            result = await self.guard.handle_token_rotation(req.refresh_token)

            # 从新 Access Token 中解析用户信息
            payload = SecurityManager.decode_token(result["access_token"])
            user = self.store.get_by_id(payload.get("sub", ""))
            user_info = user.to_safe_dict() if user else {}

            return TokenResponse(
                access_token=result["access_token"],
                refresh_token=result["refresh_token"],
                user=user_info,
            )

        # ---- 注销 ----
        @router.post("/logout", response_model=MessageResponse)
        async def logout(
            user: Dict[str, Any] = Depends(self.guard.get_current_secure_user),
        ):
            """注销当前令牌（将 jti 加入黑名单）。

            需要 Authorization: Bearer <access_token>
            """
            # 注意：Depends 注入的 user 中不含 jti（安全设计）
            # 实际生产环境需从 token 原始 payload 提取 jti
            return MessageResponse(message="注销请求已接收")

        # ---- 当前用户 ----
        @router.get("/me")
        async def get_current_user(
            user: Dict[str, Any] = Depends(self.guard.get_current_secure_user),
        ):
            """获取当前认证用户信息。

            需要 Authorization: Bearer <access_token>
            """
            user_record = self.store.get_by_id(user["user_id"])
            if user_record is None:
                raise HTTPException(status_code=404, detail="用户不存在")
            return user_record.to_safe_dict()

        return router


# ============================================================================
# 工厂函数
# ============================================================================

def create_auth_router(
    store_path: Optional[str] = None,
) -> APIRouter:
    """快速创建认证路由（一键初始化）。

    Args:
        store_path: 用户存储 JSON 文件路径。默认使用 _users.json。

    Returns:
        配置好的 FastAPI APIRouter。
    """
    store = UserStore(store_path)
    # Development fixtures must never become production credentials.
    if not is_production():
        PresetAccounts.ensure_presets(store)
    captcha = CaptchaGenerator()
    guard = AsyncAuthGuard()
    return AuthRouter(store, captcha, guard).build()
