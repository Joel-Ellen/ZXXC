# -*- coding: utf-8 -*-
"""
Content Normalizer — Agent 输出规范化
======================================

将不同 Agent 的原始输出规范化为统一的前端格式：
  content_type: "markdown" | "structured"
  content_subtype: "mindmap" | "quiz" | "learning_path" | "tutoring" |
                   "profile" | "evaluation_report" | "knowledge_analysis"

来源: backend/routes/api_routes.py (merged)
"""
import re
from enum import Enum
from typing import Dict, Any, Optional


class ContentFormat(str, Enum):
    MARKDOWN = "markdown"
    STRUCTURED = "structured"


def normalize_agent_output(
    raw: Dict[str, Any],
    agent_name: str = "",
) -> Dict[str, Any]:
    """根据 Agent 类型自动选择规范化策略。"""
    name_lower = agent_name.lower()

    if "mindmap" in name_lower:
        return build_mindmap_response(raw)
    elif "question" in name_lower or "quiz" in name_lower:
        return build_quiz_response(raw)
    elif "coding" in name_lower or "practice" in name_lower:
        return build_markdown_response({
            "title": raw.get("title", "编程练习"),
            "content": raw.get("overview_markdown") or raw.get("raw") or str(raw),
            "metadata": {"exercises": raw.get("exercises", [])},
        })
    elif "video" in name_lower:
        return build_markdown_response({
            "title": raw.get("title", "视频脚本"),
            "content": raw.get("overview_markdown") or raw.get("raw") or str(raw),
            "metadata": {"segments": raw.get("segments", []), "total_duration": raw.get("total_duration", "")},
        })
    elif "planner" in name_lower or "resource" in name_lower:
        return build_learning_path_response(raw)
    elif "coach" in name_lower or "tutor" in name_lower:
        return build_tutoring_response(raw)
    elif "profiler" in name_lower:
        return build_profile_response(raw)
    elif "evaluation" in name_lower or "assess" in name_lower:
        return build_evaluation_response(raw)
    else:
        return build_markdown_response(raw)


def build_markdown_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """规范化为 Markdown 类型输出。"""
    md = raw.get("full_markdown") or raw.get("report_markdown") or raw.get("content") or raw.get("answer", "")
    return {
        "content_type": ContentFormat.MARKDOWN.value,
        "markdown": str(md),
        "title": raw.get("title", ""),
        "metadata": raw.get("metadata", {}),
    }


def build_mindmap_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """规范化为思维导图类型。"""
    mermaid_code = raw.get("mermaid_code", "")
    root = raw.get("root", {})
    return {
        "content_type": ContentFormat.STRUCTURED.value,
        "content_subtype": "mindmap",
        "mermaid_code": mermaid_code,
        "root": root,
        "key_concepts": raw.get("key_concepts", []),
        "title": raw.get("title", ""),
    }


def build_quiz_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """规范化为测验类型。"""
    questions = raw.get("questions", [])
    return {
        "content_type": ContentFormat.STRUCTURED.value,
        "content_subtype": "quiz",
        "questions": questions,
        "total_score": raw.get("total_score", 0),
        "estimated_time_minutes": raw.get("estimated_time_minutes", 0),
        "title": raw.get("title", ""),
    }


def build_learning_path_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """规范化为学习路径类型。"""
    return {
        "content_type": ContentFormat.STRUCTURED.value,
        "content_subtype": "learning_path",
        "stages": raw.get("stages", []),
        "total_weeks": raw.get("total_weeks", 0),
        "weekly_hours": raw.get("weekly_hours", 0),
        "roadmap_mermaid": raw.get("roadmap_mermaid", ""),
        "course_name": raw.get("course_name", ""),
    }


def build_tutoring_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """规范化为辅导类型。"""
    return {
        "content_type": ContentFormat.STRUCTURED.value,
        "content_subtype": "tutoring",
        "answer_type": raw.get("answer_type", "general"),
        "core_definition": raw.get("core_definition"),
        "analogy": raw.get("analogy"),
        "markdown_body": raw.get("detailed_explanation") or raw.get("answer") or raw.get("response", ""),
        "diagram": raw.get("diagram"),
        "code_example": raw.get("code_example"),
        "hints": raw.get("hints", []),
        "common_mistakes": raw.get("common_misconceptions") or raw.get("common_mistakes", []),
        "extension_questions": raw.get("extension_questions", []),
    }


def build_profile_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """规范化为画像类型。"""
    return {
        "content_type": ContentFormat.STRUCTURED.value,
        "content_subtype": "profile_update",
        "profile_update": raw.get("profile_update", raw),
        "summary_markdown": raw.get("summary", ""),
        "next_question": raw.get("next_question"),
        "confidence_score": raw.get("confidence_score"),
        "missing_info": raw.get("missing_info", []),
    }


def build_evaluation_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """规范化为评估报告类型。"""
    report = raw.get("report", raw)
    return {
        "content_type": ContentFormat.STRUCTURED.value,
        "content_subtype": "evaluation_report",
        "metrics": report.get("metrics", {}),
        "current_level": report.get("current_level", ""),
        "weak_areas": report.get("weak_areas", []),
        "strengths": report.get("strengths", []),
        "suggestions": report.get("suggestions", []),
        "radar_data": report.get("radar_data", {}),
        "report_markdown": raw.get("report_markdown", ""),
    }


def build_resource_contract_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize an agent resource payload into the canonical resource contract."""
    from src.contracts.resource_contract import ResourceContract

    resource_type = raw.get("resource_type") or raw.get("card_type") or raw.get("type") or "unknown"
    contract = ResourceContract(
        resource_id=raw.get("resource_id", ""),
        node_id=raw.get("node_id", ""),
        resource_type=resource_type,
        title=raw.get("title") or raw.get("metadata", {}).get("title", ""),
        body_markdown=raw.get("body_markdown") or raw.get("content") or raw.get("markdown") or "",
        structured_payload=raw.get("structured_payload") or raw.get("metadata") or {},
        artifacts=raw.get("artifacts") or {},
        difficulty=raw.get("difficulty", 0.5),
        personalization_basis=raw.get("personalization_basis") or {},
        source_refs=raw.get("source_refs") or [],
    )
    return contract.with_legacy_aliases()