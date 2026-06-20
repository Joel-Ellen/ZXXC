# -*- coding: utf-8 -*-
"""
QuestionGeneratorAgent — 题库生成 Agent
=======================================
生成选择题、判断题、简答题、编程题等多种题型。

来源: backend/agents/question_generator.py (merged)
"""
from typing import Dict, Any
from .base_agent import BaseAgent

QUESTION_GENERATOR_SYSTEM = """你是一位专业的出题专家。
生成多种题型：选择题/判断题/简答题/编程题。
强调理解而非记忆，设计干扰项，难度递进，包含详细解析。
必须返回严格的JSON格式。"""


class QuestionGeneratorAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="QuestionGenerator", role="出题专家", llm_client=llm_client)
        self.system_prompt = QUESTION_GENERATOR_SYSTEM

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        topic = task.get("topic", "")
        course_name = task.get("course_name", "")
        question_count = task.get("question_count", 10)
        difficulty = task.get("difficulty", "basic")
        question_types = task.get("question_types", ["choice", "true_false", "short_answer"])

        self.state.current_task = f"Generating {question_count} questions: {topic}"
        prompt = f"""为「{course_name}」的「{topic}」生成{question_count}道题目。
难度：{difficulty}，题型：{question_types}
返回JSON：{{"title": "", "questions": [{{"id": 0, "type": "", "question": "", "options": [], "answer": "", "explanation": "", "difficulty": "", "points": 0}}], "total_score": 0, "estimated_time_minutes": 0}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.6)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"questions": [], "raw": result["content"]}
        return {"questions": [], "raw": result["content"]}
