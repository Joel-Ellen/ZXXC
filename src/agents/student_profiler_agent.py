# -*- coding: utf-8 -*-
"""
StudentProfilerAgent — 学生画像构建 Agent
==========================================
通过自然语言对话自动构建 8 维动态学习画像。

来源: backend/agents/student_profiler.py (merged)
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent

STUDENT_PROFILER_SYSTEM = """你是一位专业的教育测评专家和学生学习顾问。
通过自然友好的对话，逐步了解学生的背景信息，构建学习画像。
维度：专业背景、知识基础水平、学习能力、学习偏好、认知风格、易错知识点、兴趣方向、职业目标。
必须返回严格的JSON格式结果。"""


class StudentProfilerAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="StudentProfiler", role="学生画像构建专家", llm_client=llm_client)
        self.system_prompt = STUDENT_PROFILER_SYSTEM
        self.conversation_round = 0
        self.collected_info = {}

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        mode = task.get("mode", "extract")
        message = task.get("message", "")
        history = task.get("conversation_history", [])
        existing = task.get("existing_profile", {})

        if mode == "extract":
            return await self._extract_profile(message, history, existing)
        elif mode == "converse":
            return await self._generate_next_question(message, history, existing)
        elif mode == "update":
            return await self._extract_profile(message, [], existing)
        return await self._extract_profile(message, history, existing)

    async def _extract_profile(self, message: str, history: List[Dict], existing: Dict) -> Dict[str, Any]:
        self.state.current_task = "Extracting student profile from conversation"
        prompt = f"""从学生对话中提取学习画像信息。
已有画像：{json.dumps(existing, ensure_ascii=False) if existing else '无'}
对话历史：{json.dumps(history[-6:] if history else [], ensure_ascii=False)}
最新学生消息："{message}"
返回JSON：{{"profile_update": {{dimensions with score/label/description/evidence/confidence}},
"summary": "50字总结", "missing_info": [], "next_question": "..."}}"""
        result = await self.chat_llm(prompt, json_mode=True)
        if self.llm and hasattr(self.llm, 'extract_json'):
            data = self.llm.extract_json(result["content"])
        else:
            try:
                data = json.loads(result["content"])
            except json.JSONDecodeError:
                return {"error": "Failed to parse", "raw": result["content"]}
        if data:
            await self.update_shared_memory("student_profile", data.get("profile_update", {}))
            self.send_message("KnowledgeAnalysis", data.get("profile_update", {}), "profile_update")
        return data or {"error": "Failed to parse", "raw": result["content"]}

    async def _generate_next_question(self, message: str, history: List[Dict], existing: Dict) -> Dict[str, Any]:
        prompt = f"""你是学生学习顾问。生成下一个自然对话问题。
已有画像：{json.dumps(existing, ensure_ascii=False) if existing else '无'}
学生最新消息："{message}"
返回JSON：{{"response_message": "...", "next_question": "...", "question_purpose": "..."}}"""
        result = await self.chat_llm(prompt, json_mode=True)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"response_message": result["content"]}
        return {"response_message": result["content"]}
