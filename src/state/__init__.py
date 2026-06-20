# -*- coding: utf-8 -*-
"""
EduAgent State Layer
====================
LangGraph 全局上下文状态的强类型定义，基于 Pydantic v2 实现完备的输入输出校验。

本包导出核心状态模型 AgentState 及其所有子结构，供 LangGraph Node 在
运行时进行数据校验与序列化/反序列化。
"""

from .agent_state import (
    AgentState,
    StaticProfile,
    DynamicProfile,
    LatestBehavior,
    KnowledgeMasteryRecord,
    ErrorTypeDistribution,
    PIDErrorRecord,
)

__all__ = [
    "AgentState",
    "StaticProfile",
    "DynamicProfile",
    "LatestBehavior",
    "KnowledgeMasteryRecord",
    "ErrorTypeDistribution",
    "PIDErrorRecord",
]
