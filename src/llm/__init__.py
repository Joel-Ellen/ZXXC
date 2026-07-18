# -*- coding: utf-8 -*-
"""EduAgent LLM package exports.

The LLM package includes optional provider clients. Resolve exports lazily so
utility imports such as ``src.llm.content_filter`` do not require provider SDKs.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_OPTIONAL_PROVIDER_EXPORTS = {
    "LLMClientV2",
    "create_llm_client_v2",
    "create_llm_client_v2_from_env",
}

_EXPORT_MODULES = {
    "LLMClientV2": ".client_v2",
    "create_llm_client_v2": ".client_v2",
    "create_llm_client_v2_from_env": ".client_v2",
    "TokenEstimator": ".token_estimator",
    "InputManager": ".input_manager",
    "ContentFilter": ".content_filter",
    "HallucinationChecker": ".hallucination_checker",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module 'src.llm' has no attribute {name!r}")
    try:
        value = getattr(import_module(module_name, __name__), name)
    except ModuleNotFoundError as exc:
        if name in _OPTIONAL_PROVIDER_EXPORTS:
            raise AttributeError(
                f"module 'src.llm' cannot load optional provider export {name!r}: {exc}"
            ) from exc
        raise
    globals()[name] = value
    return value
