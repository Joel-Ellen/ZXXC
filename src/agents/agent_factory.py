# -*- coding: utf-8 -*-
"""
Shared helpers for constructing LLM-enabled agents consistently.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Type, TypeVar

from src.llm import create_llm_client_v2_from_env


T = TypeVar("T")


@lru_cache(maxsize=1)
def get_default_llm() -> Any:
    try:
        return create_llm_client_v2_from_env()
    except Exception:
        return None


def build_agent(agent_cls: Type[T], **kwargs: Any) -> T:
    if "llm_client" not in kwargs or kwargs["llm_client"] is None:
        kwargs["llm_client"] = get_default_llm()
    return agent_cls(**kwargs)
