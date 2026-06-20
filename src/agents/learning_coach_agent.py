# -*- coding: utf-8 -*-
"""
LearningCoachAgent — 智能辅导 Agent
====================================
苏格拉底式引导教学：概念讲解、问题引导、代码调试、学习建议、考试准备。

来源: backend/agents/learning_coach.py (merged)
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent

LEARNING_COACH_SYSTEM = """你是一位耐心的AI学习导师。
核心原则：苏格拉底式引导、脚手架式教学、类比解释、多角度讲解、鼓励试错。
禁止直接给出完整答案。必须返回严格的JSON格式。"""


class LearningCoachAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="LearningCoach", role="AI学习导师", llm_client=llm_client)
        self.system_prompt = LEARNING_COACH_SYSTEM
        self.tutoring_history: List[Dict] = []

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        question = task.get("question", "")
        context_type = task.get("context_type", "concept")
        course_name = task.get("course_name", "")
        code_snippet = task.get("code_snippet", "")
        error_message = task.get("error_message", "")

        self.state.current_task = f"Tutoring: {context_type}"
        student_profile = await self.read_shared_memory("student_profile", {})

        student_context = json.dumps(student_profile, ensure_ascii=False)[:500] if student_profile else "未知"

        if context_type == "concept":
            return await self._explain_concept(question, course_name, student_context)
        elif context_type == "problem_solving":
            return await self._guide_problem(question, course_name, student_context)
        elif context_type == "code_debug":
            return await self._debug_code(question, code_snippet, error_message, student_context)
        elif context_type == "exam_prep":
            return await self._exam_prep(question, course_name, student_context)
        else:
            return await self._general_tutoring(question, course_name, student_context)

    async def _explain_concept(self, question: str, course_name: str, ctx: str) -> Dict[str, Any]:
        prompt = f"""讲解概念。学生画像：{ctx}，课程：{course_name}，问题：{question}
返回JSON：{{"answer_type": "concept", "core_definition": "", "analogy": "", "detailed_explanation": "", "diagram": "", "code_example": "", "common_misconceptions": [], "extension_questions": []}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"answer": result["content"]}
        return {"answer": result["content"]}

    async def _guide_problem(self, question: str, course_name: str, ctx: str) -> Dict[str, Any]:
        prompt = f"""引导解决问题（不给答案）。学生画像：{ctx}，课程：{course_name}，问题：{question}
返回JSON：{{"answer_type": "problem_solving", "hints": [], "solution_approach": "", "common_mistakes": []}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.6)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"answer": result["content"]}
        return {"answer": result["content"]}

    async def _debug_code(self, question: str, code: str, error: str, ctx: str) -> Dict[str, Any]:
        prompt = f"""调试代码。学生画像：{ctx}，问题：{question}，代码：```python\n{code}\n```，错误：{error}
返回JSON：{{"answer_type": "code_debug", "error_analysis": "", "root_cause": "", "fix_guidance": "", "best_practices": []}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.4)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"answer": result["content"]}
        return {"answer": result["content"]}

    async def _exam_prep(self, question: str, course_name: str, ctx: str) -> Dict[str, Any]:
        prompt = f"""考试准备。学生画像：{ctx}，课程：{course_name}，问题：{question}
返回JSON：{{"answer_type": "exam_prep", "key_topics": [], "review_strategy": "", "practice_questions": [], "cheat_sheet": ""}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.6)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"answer": result["content"]}
        return {"answer": result["content"]}

    async def _general_tutoring(self, question: str, course_name: str, ctx: str) -> Dict[str, Any]:
        prompt = f"""一般辅导。学生画像：{ctx}，课程：{course_name}，问题：{question}
返回JSON：{{"answer_type": "general", "response": "", "diagram": "", "code_example": "", "follow_up_questions": []}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"answer": result["content"]}
        return {"answer": result["content"]}
