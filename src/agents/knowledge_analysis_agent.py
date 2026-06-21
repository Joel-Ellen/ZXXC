# -*- coding: utf-8 -*-
"""
Knowledge analysis agent.
"""

from __future__ import annotations

from typing import Any, Dict

from .base_agent import BaseAgent
from .prompt_registry import build_user_prompt, get_system_prompt


class KnowledgeAnalysisAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(
            name="KnowledgeAnalysis",
            role="知识体系分析专家",
            llm_client=llm_client,
        )
        self.system_prompt = get_system_prompt("knowledge_analysis.full")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        course_name = task.get("course_name", "")
        topic = task.get("topic", "")

        self.state.current_task = f"Analyzing knowledge: {course_name}"
        student_profile = await self.read_shared_memory("student_profile", {})
        prompt = build_user_prompt(
            "knowledge_analysis.full",
            course_name=course_name,
            topic=topic,
            student_profile=student_profile,
        )
        result = await self.chat_llm(
            prompt,
            system_prompt=self.system_prompt,
            json_mode=True,
            temperature=0.5,
        )
        data = self._extract_json(result.get("content", ""))
        if data:
            await self.update_shared_memory("knowledge_structure", data)
            await self.update_shared_memory(f"knowledge_{course_name}", data)
            self.send_message("ResourcePlanner", data, "knowledge_structure")
            return data
        return {"error": "Failed to parse", "raw": result.get("content", "")}

    def _extract_json(self, content: str) -> Dict[str, Any] | None:
        if self.llm and hasattr(self.llm, "extract_json"):
            return self.llm.extract_json(content)
        return None
