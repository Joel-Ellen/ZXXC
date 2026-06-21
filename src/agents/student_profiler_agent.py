# -*- coding: utf-8 -*-
"""
Student profiler agent.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .base_agent import BaseAgent
from .prompt_registry import build_user_prompt, get_system_prompt


class StudentProfilerAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(
            name="StudentProfiler",
            role="学生画像构建专家",
            llm_client=llm_client,
        )
        self.system_prompt = get_system_prompt("student_profiler.extract")
        self.conversation_round = 0
        self.collected_info: Dict[str, Any] = {}

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        mode = task.get("mode", "extract")
        message = task.get("message", "")
        history = task.get("conversation_history", [])
        existing = task.get("existing_profile", {})

        if mode == "converse":
            return await self._generate_next_question(message, history, existing)
        return await self._extract_profile(message, history, existing)

    async def _extract_profile(
        self,
        message: str,
        history: List[Dict[str, Any]],
        existing: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.state.current_task = "Extracting student profile from conversation"
        prompt = build_user_prompt(
            "student_profiler.extract",
            message=message,
            history=history,
            existing=existing,
        )
        result = await self.chat_llm(
            prompt,
            system_prompt=self.system_prompt,
            json_mode=True,
        )
        data = self._extract_json(result.get("content", ""))
        if data:
            await self.update_shared_memory("student_profile", data.get("profile_update", {}))
            self.send_message("KnowledgeAnalysis", data.get("profile_update", {}), "profile_update")
            return data
        return {"error": "Failed to parse", "raw": result.get("content", "")}

    async def _generate_next_question(
        self,
        message: str,
        history: List[Dict[str, Any]],
        existing: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.state.current_task = "Generating next profiling question"
        prompt = build_user_prompt(
            "student_profiler.converse",
            message=message,
            existing=existing,
        )
        result = await self.chat_llm(
            prompt,
            system_prompt=get_system_prompt("student_profiler.converse"),
            json_mode=True,
        )
        data = self._extract_json(result.get("content", ""))
        return data or {"response_message": result.get("content", "")}

    def _extract_json(self, content: str) -> Dict[str, Any] | None:
        if self.llm and hasattr(self.llm, "extract_json"):
            return self.llm.extract_json(content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
