# -*- coding: utf-8 -*-
"""
EduAgent LLM Layer (v2 — merged)
================================
大模型接入层 — 统一封装多厂商 API：

  - DashScope (阿里云灵积 / 通义千问)
  - iFlyTek Spark (讯飞星火)
  - DeepSeek
  - OpenAI

提供一致的调用接口注入到各 Agent Node。

本包导出:
  - LLMClient (v1 遗留，向后兼容)
  - LLMClientV2: 统一异步大模型客户端（推荐）
  - LLMConfig, Provider: 配置与枚举
  - TokenEstimator, InputManager: Token 管理与溢出策略
  - ContentFilter: 内容安全过滤
  - HallucinationChecker: 防幻觉自洽校验
"""

# 向后兼容的 v1 导出
from ._legacy_client import (
    LLMClient,
    LLMConfig,
    Provider,
    create_llm_client,
    create_llm_client_from_env,
)

# v2 导出（推荐）
from .client_v2 import (
    LLMClientV2,
    create_llm_client_v2,
    create_llm_client_v2_from_env,
)

# 工具类
from .token_estimator import TokenEstimator
from .input_manager import InputManager
from .content_filter import ContentFilter
from .hallucination_checker import HallucinationChecker

__all__ = [
    # v1 legacy
    "LLMClient",
    "LLMConfig",
    "Provider",
    "create_llm_client",
    "create_llm_client_from_env",
    # v2
    "LLMClientV2",
    "create_llm_client_v2",
    "create_llm_client_v2_from_env",
    # utilities
    "TokenEstimator",
    "InputManager",
    "ContentFilter",
    "HallucinationChecker",
]
