# -*- coding: utf-8 -*-
"""
Learning path planner agent.
"""

from __future__ import annotations

from typing import Any, Dict

from .base_agent import BaseAgent
from .prompt_registry import build_user_prompt, get_system_prompt


class ResourcePlannerAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(
            name="ResourcePlanner",
            role="学习路径规划师",
            llm_client=llm_client,
        )
        self.system_prompt = get_system_prompt("resource_planner.path")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        course_name = task.get("course_name", "")
        student_profile = await self.read_shared_memory("student_profile", {})
        knowledge = await self.read_shared_memory("knowledge_structure", {})

        self.state.current_task = f"Planning learning path for {course_name}"
        prompt = build_user_prompt(
            "resource_planner.path",
            course_name=course_name,
            student_profile=student_profile,
            knowledge=knowledge,
        )
        result = await self.chat_llm(
            prompt,
            system_prompt=self.system_prompt,
            json_mode=True,
            temperature=0.5,
        )
        data = self._extract_json(result.get("content", ""))
        if data:
            await self.update_shared_memory("learning_path_plan", data)
            self.send_message("ResourceGeneration", data, "resource_plan")
            return data
        return {"error": "Failed to parse", "raw": result.get("content", "")}

    def _extract_json(self, content: str) -> Dict[str, Any] | None:
        if self.llm and hasattr(self.llm, "extract_json"):
            return self.llm.extract_json(content)
        return None
