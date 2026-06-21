# -*- coding: utf-8 -*-
"""
Prompt-backed adapters for complex legacy agent modules.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .prompt_registry import build_user_prompt, get_system_prompt


def run_tutor_mode_with_llm(
    llm: Any,
    mode: str,
    query: str,
    course_name: str = "",
    student_context: str = "",
    code_snippet: str = "",
    error_message: str = "",
    temperature: float = 0.7,
) -> Optional[Dict[str, Any]]:
    if llm is None:
        return None

    prompt = build_user_prompt(
        "tutor.mode",
        mode=mode,
        query=query,
        course_name=course_name,
        student_context=student_context,
        code_snippet=code_snippet,
        error_message=error_message,
    )
    messages = [
        {"role": "system", "content": get_system_prompt("tutor.mode")},
        {"role": "user", "content": prompt},
    ]

    content = ""
    try:
        if hasattr(llm, "chat_sync"):
            result = llm.chat_sync(messages, temperature=temperature, json_mode=True)
        elif hasattr(llm, "chat"):
            result = {"content": llm.chat(messages)}
        else:
            return None
        content = result.get("content", "") if isinstance(result, dict) else str(result)
        if hasattr(llm, "extract_json"):
            return llm.extract_json(content)
        return json.loads(content)
    except Exception:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def run_assessment_report_with_llm(
    llm: Any,
    radar: List[float],
    a_mix: float,
    strategy: str,
    course_name: str = "",
    study_time: float = 0,
    completed_tasks: int = 0,
    fallback_markdown: str = "",
) -> Dict[str, Any]:
    dim_names = ["概念理解力", "代码工程力", "逻辑推理力", "纠错韧性", "时间管理力"]

    if llm is None:
        return {
            "metrics": {"knowledge_mastery": a_mix},
            "current_level": strategy,
            "weak_areas": [dim_names[i] for i, v in enumerate(radar) if v < 0.4],
            "strengths": [dim_names[i] for i, v in enumerate(radar) if v >= 0.7],
            "suggestions": [],
            "radar_data": {"labels": dim_names, "values": radar},
            "report_markdown": fallback_markdown,
        }

    prompt = build_user_prompt(
        "assessment.report",
        radar=radar,
        a_mix=a_mix,
        strategy=strategy,
        course_name=course_name,
        study_time=study_time,
        completed_tasks=completed_tasks,
    )

    try:
        if hasattr(llm, "chat_sync"):
            result = llm.chat_sync(
                [
                    {"role": "system", "content": get_system_prompt("assessment.report")},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                json_mode=True,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)
        elif hasattr(llm, "chat"):
            content = llm.chat(
                [
                    {"role": "system", "content": get_system_prompt("assessment.report")},
                    {"role": "user", "content": prompt},
                ]
            )
        else:
            content = "{}"

        data = json.loads(content) if isinstance(content, str) else content
        data["radar_data"] = {"labels": dim_names, "values": radar}
        data["report_markdown"] = fallback_markdown
        return data
    except Exception:
        return {
            "metrics": {"knowledge_mastery": a_mix},
            "current_level": strategy,
            "weak_areas": [dim_names[i] for i, v in enumerate(radar) if v < 0.4],
            "strengths": [dim_names[i] for i, v in enumerate(radar) if v >= 0.7],
            "suggestions": ["继续保持当前学习节奏"],
            "radar_data": {"labels": dim_names, "values": radar},
            "report_markdown": fallback_markdown,
        }


def patch_tutor_node_class(TutorAgentNode) -> None:
    def _build_tutoring_prompt(self, user_prompt: str, temperature: float = 0.7):
        llm = self._llm
        if llm is None:
            return None
        messages = [
            {"role": "system", "content": get_system_prompt("tutor.mode")},
            {"role": "user", "content": user_prompt},
        ]
        content = ""
        try:
            if hasattr(llm, "chat_sync"):
                result = llm.chat_sync(messages, temperature=temperature, json_mode=True)
            elif hasattr(llm, "chat"):
                result = {"content": llm.chat(messages)}
            else:
                return None
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            if hasattr(llm, "extract_json"):
                return llm.extract_json(content)
            return json.loads(content)
        except Exception:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return None
        return None

    def _tutor_concept(self, query: str, course_name: str, ctx: str):
        prompt = build_user_prompt(
            "tutor.mode",
            mode="concept",
            query=query,
            course_name=course_name,
            student_context=ctx,
        )
        data = self._build_tutoring_prompt(prompt)
        return {"mode": "concept", **(data or {"text_explanation": query})}

    def _tutor_problem_solving(self, query: str, course_name: str, ctx: str):
        prompt = build_user_prompt(
            "tutor.mode",
            mode="problem_solving",
            query=query,
            course_name=course_name,
            student_context=ctx,
        )
        data = self._build_tutoring_prompt(prompt, temperature=0.6)
        return {"mode": "problem_solving", **(data or {"text_explanation": query})}

    def _tutor_code_debug(self, query: str, code: str, error: str, ctx: str):
        prompt = build_user_prompt(
            "tutor.mode",
            mode="code_debug",
            query=query,
            course_name="",
            student_context=ctx,
            code_snippet=code,
            error_message=error,
        )
        data = self._build_tutoring_prompt(prompt, temperature=0.4)
        return {"mode": "code_debug", **(data or {"text_explanation": query})}

    def _tutor_exam_prep(self, query: str, course_name: str, ctx: str):
        prompt = build_user_prompt(
            "tutor.mode",
            mode="exam_prep",
            query=query,
            course_name=course_name,
            student_context=ctx,
        )
        data = self._build_tutoring_prompt(prompt, temperature=0.6)
        return {"mode": "exam_prep", **(data or {"text_explanation": query})}

    def _tutor_general(self, query: str, course_name: str, ctx: str):
        prompt = build_user_prompt(
            "tutor.mode",
            mode="general",
            query=query,
            course_name=course_name,
            student_context=ctx,
        )
        data = self._build_tutoring_prompt(prompt)
        return {"mode": "general", **(data or {"text_explanation": query})}

    TutorAgentNode._build_tutoring_prompt = _build_tutoring_prompt
    TutorAgentNode._tutor_concept = _tutor_concept
    TutorAgentNode._tutor_problem_solving = _tutor_problem_solving
    TutorAgentNode._tutor_code_debug = _tutor_code_debug
    TutorAgentNode._tutor_exam_prep = _tutor_exam_prep
    TutorAgentNode._tutor_general = _tutor_general


def patch_assessment_node_class(AssessmentReporterNode) -> None:
    def generate_llm_report(
        self,
        radar: List[float],
        a_mix: float,
        strategy: str,
        course_name: str = "",
        quiz_records: Any = None,
        study_time: float = 0,
        completed_tasks: int = 0,
    ) -> Dict[str, Any]:
        fallback_markdown = self._generate_diagnostic_report(radar, a_mix, strategy, strategy)
        return run_assessment_report_with_llm(
            llm=self._llm,
            radar=radar,
            a_mix=a_mix,
            strategy=strategy,
            course_name=course_name,
            study_time=study_time,
            completed_tasks=completed_tasks,
            fallback_markdown=fallback_markdown,
        )

    AssessmentReporterNode.generate_llm_report = generate_llm_report
