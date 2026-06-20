# -*- coding: utf-8 -*-
"""
EduAgent Routes Layer
=====================
新增 API 路由模块（合并自 backend/routes/）。
"""

from .content_normalizer import (
    ContentFormat,
    normalize_agent_output,
    build_markdown_response,
    build_mindmap_response,
    build_quiz_response,
    build_learning_path_response,
    build_tutoring_response,
    build_profile_response,
    build_evaluation_response,
)

__all__ = [
    "ContentFormat",
    "normalize_agent_output",
    "build_markdown_response",
    "build_mindmap_response",
    "build_quiz_response",
    "build_learning_path_response",
    "build_tutoring_response",
    "build_profile_response",
    "build_evaluation_response",
]
