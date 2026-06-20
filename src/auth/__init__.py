# -*- coding: utf-8 -*-
"""
EduAgent Auth Layer
===================
工业级安全认证模块 — Argon2id 密码哈希 + JWT 双令牌 + LangGraph 上下文防护。

本包包含：
  - SecurityManager    : 密码哈希 + 令牌签发/校验
  - AsyncAuthGuard     : FastAPI 异步认证中间件 (Redis 黑名单 + 令牌轮转)
  - GraphGuard         : LangGraph 运行时不可变上下文防护
  - CaptchaGenerator   : SVG 数学验证码生成
  - UserStore          : JSON 文件持久化用户存储
  - AuthRouter         : FastAPI 认证路由 (注册/登录/验证码/刷新)
  - PromptDefense      : Prompt 注入攻击检测与清洗
  - RateLimiter        : 内存滑动窗口限流器
"""

from .security import SecurityManager, FAKE_HASH, JWT_SECRET_KEY, ALGORITHM
from .captcha import CaptchaGenerator, CaptchaRecord
from .models import UserRecord, UserStore, PresetAccounts
from .middleware import AsyncAuthGuard, oauth2_scheme
from .graph_guard import LangGraphImmutableContextGuard
from .routes import AuthRouter, create_auth_router
from .prompt_defense import PromptDefense, get_prompt_defense
from .rate_limiter import RateLimiter, get_rate_limiter

__all__ = [
    "SecurityManager",
    "FAKE_HASH",
    "JWT_SECRET_KEY",
    "ALGORITHM",
    "CaptchaGenerator",
    "CaptchaRecord",
    "UserRecord",
    "UserStore",
    "PresetAccounts",
    "AsyncAuthGuard",
    "oauth2_scheme",
    "LangGraphImmutableContextGuard",
    "AuthRouter",
    "create_auth_router",
    "PromptDefense",
    "get_prompt_defense",
    "RateLimiter",
    "get_rate_limiter",
]
