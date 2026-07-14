# -*- coding: utf-8 -*-
"""EduAgent auth package exports.

The package exposes the same public names as before, but resolves them lazily so
lightweight imports such as ``src.auth.prompt_defense`` do not require the full
auth dependency stack.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "SecurityManager": ".security",
    "FAKE_HASH": ".security",
    "JWT_SECRET_KEY": ".security",
    "ALGORITHM": ".security",
    "CaptchaGenerator": ".captcha",
    "CaptchaRecord": ".captcha",
    "UserRecord": ".models",
    "UserStore": ".models",
    "PresetAccounts": ".models",
    "LangGraphImmutableContextGuard": ".graph_guard",
    "PromptDefense": ".prompt_defense",
    "get_prompt_defense": ".prompt_defense",
    "RateLimiter": ".rate_limiter",
    "get_rate_limiter": ".rate_limiter",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module 'src.auth' has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
