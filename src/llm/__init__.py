# -*- coding: utf-8 -*-
"""
EduAgent LLM Layer
==================
大模型接入层 — 统一封装 DashScope (Qwen) 和 iFlyTek Spark (讯飞星火)
两套 API，提供一致的调用接口注入到各 Agent Node。

本包导出:
  - LLMClient: 统一大模型客户端
  - LLMConfig:  连接与模型配置
  - Provider:   后端提供商枚举
"""

from .client import (
    LLMClient,
    LLMConfig,
    Provider,
    create_llm_client,
    create_llm_client_from_env,
)

__all__ = [
    "LLMClient",
    "LLMConfig",
    "Provider",
    "create_llm_client",
    "create_llm_client_from_env",
]
