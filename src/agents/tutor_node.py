# -*- coding: utf-8 -*-
"""
Tutor agent node.

This cleaned version preserves the public API of the legacy module while
delegating mode-specific prompt orchestration to the centralized prompt layer.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.api_models.tutor_request import TutorRequest

from .prompt_adapters import patch_tutor_node_class, run_tutor_mode_with_llm


class TutoringMode(str, Enum):
    CONCEPT = "concept"
    PROBLEM_SOLVING = "problem_solving"
    CODE_DEBUG = "code_debug"
    EXAM_PREP = "exam_prep"
    GENERAL = "general"


class TutorInput(BaseModel):
    agent_state: Any = Field(..., description="Current agent state snapshot")
    milvus_client: Any = Field(default=None, description="Optional Milvus client")
    llm_generator: Any = Field(default=None, description="Optional LLM generator")
    request: Optional[TutorRequest] = Field(
        default=None,
        description="Normalized request context supplied by the application boundary",
    )


class TutorOutput(BaseModel):
    agent_state: Any = Field(..., description="Updated agent state")


class VideoHydrationCard(BaseModel):
    url: str = Field(..., description="Video URL")
    timestamp_range: str = Field(..., description="Recommended timestamp range")
    similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Similarity score")


class TutorResponseCard(BaseModel):
    text_explanation: str = Field(default="", description="Text explanation")
    mermaid_src: str = Field(default="", description="Mermaid diagram source")
    video_hydration: Optional[VideoHydrationCard] = Field(default=None, description="Recommended micro-lesson clip")
    query: str = Field(default="", description="Original user query")

    tutoring_mode: str = Field(default="general", description="Tutoring mode")
    core_definition: Optional[str] = Field(default=None)
    analogy: Optional[str] = Field(default=None)
    detailed_explanation: Optional[str] = Field(default=None)
    code_example: Optional[str] = Field(default=None)
    common_misconceptions: Optional[List[str]] = Field(default=None)
    hints: Optional[List[str]] = Field(default=None)
    solution_approach: Optional[str] = Field(default=None)
    error_analysis: Optional[str] = Field(default=None)
    root_cause: Optional[str] = Field(default=None)
    best_practices: Optional[List[str]] = Field(default=None)
    key_topics: Optional[List[str]] = Field(default=None)
    cheat_sheet: Optional[str] = Field(default=None)
    extension_questions: Optional[List[str]] = Field(default=None)
    follow_up_questions: Optional[List[str]] = Field(default=None)


class MermaidSyntaxGuard:
    @staticmethod
    def validate_and_repair(raw_mermaid_str: str) -> str:
        if not raw_mermaid_str or "graph" not in raw_mermaid_str:
            return "graph TD\n    A[暂无可用图解] --> B[请参考下方文字解释]"

        repaired = raw_mermaid_str.strip()

        open_brackets = len(re.findall(r"\[", repaired))
        close_brackets = len(re.findall(r"\]", repaired))
        if open_brackets > close_brackets:
            repaired += "]" * (open_brackets - close_brackets)

        open_braces = len(re.findall(r"\{", repaired))
        close_braces = len(re.findall(r"\}", repaired))
        if open_braces > close_braces:
            repaired += "}" * (open_braces - close_braces)

        open_parens = len(re.findall(r"\(", repaired))
        close_parens = len(re.findall(r"\)", repaired))
        if open_parens > close_parens:
            repaired += ")" * (open_parens - close_parens)

        repaired = re.sub(r":\->", "-->", repaired)
        repaired = re.sub(r"-->\s*$", "", repaired)

        if "---" not in repaired and "-->" not in repaired and "==" not in repaired:
            repaired += "\n    A[内容概览] --> B[详见文字说明]"

        return repaired


class TutorAgentNode:
    FALLBACK_VIDEO_URL: str = "https://default_course_cdn/fallback.mp4"
    FALLBACK_TIME_RANGE: str = "00:00-01:00"

    def __init__(self, milvus_client: Any = None, llm_generator: Any = None) -> None:
        self._milvus = milvus_client
        self._llm = llm_generator
        self._guard = MermaidSyntaxGuard()

    def __call__(self, inp: TutorInput) -> TutorOutput:
        state = inp.agent_state
        milvus = inp.milvus_client or self._milvus
        llm = inp.llm_generator or self._llm

        request = inp.request
        query = request.question if request is not None else self._extract_query(state)
        current_node = self._extract_current_node(state)
        if not query:
            return TutorOutput(agent_state=state)

        reference_chunks = self._retrieve_parent_context(milvus, query, current_node)
        mode = request.context_type if request is not None else TutoringMode.GENERAL.value
        code_snippet = request.code_snippet if request is not None else ""
        error_message = request.error_message if request is not None else ""
        course_name = getattr(state, "course_id", "") or ""
        student_context = self._student_context(state)
        mode_response = run_tutor_mode_with_llm(
            llm=llm,
            mode=mode,
            query=query,
            course_name=course_name,
            student_context=student_context,
            code_snippet=code_snippet,
            error_message=error_message,
            temperature=self._mode_temperature(mode),
        ) or {}
        text_response = str(mode_response.get("text_explanation") or "")
        if not text_response:
            if mode == TutoringMode.CODE_DEBUG.value and (code_snippet or error_message):
                text_response = self._code_debug_fallback(query, code_snippet, error_message)
            else:
                text_response = self._generate_text_explanation(llm, query, reference_chunks)

        raw_mermaid = self._generate_mermaid(llm, query, text_response)
        clean_mermaid = self._guard.validate_and_repair(raw_mermaid)

        video_metadata = self._search_video_slices(milvus, query)
        video_card = VideoHydrationCard(
            url=video_metadata[0].get("url", self.FALLBACK_VIDEO_URL),
            timestamp_range=video_metadata[0].get("time_range", self.FALLBACK_TIME_RANGE),
            similarity=video_metadata[0].get("similarity", 0.0),
        )

        mode_fields = {
            field_name: value
            for field_name, value in mode_response.items()
            if field_name in TutorResponseCard.model_fields
            and field_name not in {"text_explanation", "mermaid_src", "video_hydration", "query", "tutoring_mode"}
        }
        response_card = TutorResponseCard(
            text_explanation=text_response,
            mermaid_src=clean_mermaid,
            video_hydration=video_card,
            query=query,
            tutoring_mode=mode,
            **mode_fields,
        )
        response_payload = response_card.model_dump()
        try:
            from src.validation.pipeline import get_validation_pipeline

            response_payload, validation = get_validation_pipeline().validate_tutor_response(response_payload)
            if not validation.passed and hasattr(state, "record_error"):
                state.record_error("tutor_node_validation_rejected:" + ";".join(issue.message for issue in validation.issues))
        except Exception as exc:
            response_payload["validation"] = {"status": "failed", "passed": False, "issues": [{"message": str(exc)}]}
        state.tutor_response = response_payload
        return TutorOutput(agent_state=state)

    @staticmethod
    def _extract_query(state: Any) -> Optional[str]:
        lb = getattr(state, "latest_behavior", None)
        if lb is None:
            return None
        return getattr(lb, "tutor_query", None) or ""

    @staticmethod
    def _extract_current_node(state: Any) -> str:
        return getattr(state, "current_node_id", None) or ""

    @staticmethod
    def _student_context(state: Any) -> str:
        current_node = getattr(state, "current_node_id", "") or ""
        style = getattr(state, "recommended_resource_style", "") or ""
        details = [item for item in (f"current_node={current_node}", f"resource_style={style}") if item.split("=", 1)[1]]
        return "; ".join(details)

    @staticmethod
    def _mode_temperature(mode: str) -> float:
        return {
            TutoringMode.CONCEPT.value: 0.7,
            TutoringMode.PROBLEM_SOLVING.value: 0.6,
            TutoringMode.CODE_DEBUG.value: 0.4,
            TutoringMode.EXAM_PREP.value: 0.6,
        }.get(mode, 0.7)

    @staticmethod
    def _code_debug_fallback(query: str, code_snippet: str, error_message: str) -> str:
        code_block = code_snippet or "(No code snippet was provided.)"
        error_block = error_message or "(No runtime error message was provided.)"
        return (
            f"## Debugging: {query}\n\n"
            "### Code under review\n"
            f"```\n{code_block}\n```\n\n"
            "### Reported error\n"
            f"{error_block}\n\n"
            "Start by matching the error location to the values and control flow around it, "
            "then test the smallest input that reproduces the failure."
        )

    @staticmethod
    def _retrieve_parent_context(milvus: Any, query: str, current_node: str) -> List[str]:
        if milvus is None:
            return []
        try:
            if hasattr(milvus, "search_parent_chunks"):
                parents = milvus.search_parent_chunks(query, current_node)
                return [p.content for p in parents]
        except Exception:
            return []
        return []

    def _generate_text_explanation(self, llm: Any, query: str, reference_chunks: List[str]) -> str:
        if llm is not None and hasattr(llm, "generate_academic_explanation"):
            try:
                return llm.generate_academic_explanation(query, reference_chunks)
            except Exception:
                pass

        if reference_chunks:
            context = "\n\n".join(reference_chunks[:3])
            return f"## 关于“{query}”的相关讲解\n\n{context}"

        return f"## 关于“{query}”的解答\n\n离线模式下当前没有足够上下文，请尝试补充问题背景。"

    def _generate_mermaid(self, llm: Any, query: str, text_explanation: str) -> str:
        if llm is not None and hasattr(llm, "generate_mermaid_graph"):
            try:
                return llm.generate_mermaid_graph(query, text_explanation)
            except Exception:
                pass
        return self._template_mermaid(query)

    @staticmethod
    def _template_mermaid(query: str) -> str:
        sanitized = query[:30].replace('"', "'")
        return (
            "graph TD\n"
            f'    Q["[Q] {sanitized}"] --> A["[1] 核心概念"]\n'
            '    A --> B["[2] 原理解析"]\n'
            '    A --> C["[3] 示例"]\n'
            '    B --> D["[4] 常见误区"]\n'
            '    C --> D\n'
            '    D --> E["[5] 巩固问题"]'
        )

    def _search_video_slices(self, milvus: Any, query: str) -> List[Dict[str, Any]]:
        if milvus is not None and hasattr(milvus, "search_video_temporal_slices"):
            try:
                results = milvus.search_video_temporal_slices(query, top_k=1)
                if results:
                    return results
            except Exception:
                pass
        return [{"url": self.FALLBACK_VIDEO_URL, "time_range": self.FALLBACK_TIME_RANGE, "similarity": 0.0}]

    def tutor_with_mode(
        self,
        query: str,
        mode: str = "general",
        course_name: str = "",
        code_snippet: str = "",
        error_message: str = "",
        student_context: str = "",
    ) -> Dict[str, Any]:
        if mode == TutoringMode.CONCEPT:
            return self._tutor_concept(query, course_name, student_context)
        if mode == TutoringMode.PROBLEM_SOLVING:
            return self._tutor_problem_solving(query, course_name, student_context)
        if mode == TutoringMode.CODE_DEBUG:
            return self._tutor_code_debug(query, code_snippet, error_message, student_context)
        if mode == TutoringMode.EXAM_PREP:
            return self._tutor_exam_prep(query, course_name, student_context)
        return self._tutor_general(query, course_name, student_context)


def create_tutor_node(
    milvus_client: Any = None,
    llm_generator: Any = None,
) -> TutorAgentNode:
    return TutorAgentNode(
        milvus_client=milvus_client,
        llm_generator=llm_generator,
    )


patch_tutor_node_class(TutorAgentNode)
