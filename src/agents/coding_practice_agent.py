# -*- coding: utf-8 -*-
"""
CodingPracticeAgent — 编程实战生成 Agent
========================================
生成编程练习、项目实战、调试任务。支持 Python/C++/Java。

来源: backend/agents/coding_practice.py (merged)
"""
from typing import Dict, Any
from .base_agent import BaseAgent

CODING_PRACTICE_SYSTEM = """你是一位编程导师。
生成编程练习题，包含题目描述、示例、约束、解决方案、测试用例、复杂度分析。
支持 Python/C++/Java。必须返回严格的JSON格式。"""


class CodingPracticeAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="CodingPractice", role="编程实战导师", llm_client=llm_client)
        self.system_prompt = CODING_PRACTICE_SYSTEM

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        topic = task.get("topic", "")
        language = task.get("language", "python")
        difficulty = task.get("difficulty", "basic")
        count = task.get("count", 3)

        self.state.current_task = f"Generating {count} coding exercises: {topic}"
        prompt = f"""为「{topic}」生成{count}道{language}编程练习题。难度：{difficulty}
返回JSON：{{"exercises": [{{"id": 0, "title": "", "description": "", "examples": [], "constraints": [], "solution": "", "test_cases": [], "complexity": "", "pitfalls": []}}]}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.4)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"exercises": [], "raw": result["content"]}
        return {"exercises": [], "raw": result["content"]}
