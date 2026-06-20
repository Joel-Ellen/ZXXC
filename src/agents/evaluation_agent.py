# -*- coding: utf-8 -*-
"""
EvaluationAgent — 学习评估 Agent
================================
分析学习数据生成评估报告：知识掌握度、投入度、薄弱点、趋势分析。

来源: backend/agents/evaluation.py (merged)
"""
from typing import Dict, Any
from .base_agent import BaseAgent

EVALUATION_SYSTEM = """你是一位教育评估专家。
分析学习数据：知识掌握度、投入度、效率、薄弱点、趋势、习惯。
数据驱动、客观公正。必须返回严格的JSON格式。"""


class EvaluationAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="EvaluationAgent", role="学习评估专家", llm_client=llm_client)
        self.system_prompt = EVALUATION_SYSTEM

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        course_name = task.get("course_name", "")
        quiz_records = task.get("quiz_records", [])
        study_time = task.get("study_time", 0)
        completed_tasks = task.get("completed_tasks", 0)

        self.state.current_task = f"Generating evaluation report for {course_name}"
        student_profile = await self.read_shared_memory("student_profile", {})
        learning_path = await self.read_shared_memory("learning_path_plan", {})

        prompt = f"""生成学习评估报告。
课程：{course_name}，测验记录：{len(quiz_records)}条，学习时长：{study_time}小时，完成任务：{completed_tasks}
学生画像：{student_profile}，学习路径：{learning_path}
返回JSON：{{"report": {{"metrics": {{"knowledge_mastery": 0.0, "engagement": 0.0, "efficiency": 0.0}}, "current_level": "", "weak_areas": [], "strengths": [], "suggestions": [], "radar_data": {{"labels": [], "values": []}}}}, "report_markdown": ""}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.5)
        if self.llm and hasattr(self.llm, 'extract_json'):
            data = self.llm.extract_json(result["content"])
        else:
            data = None
        if data:
            await self.update_shared_memory("latest_evaluation", data.get("report", {}))
            self.send_message("LearningCoach", data.get("report", {}), "evaluation_complete")
        return data or {"report_markdown": result["content"]}
