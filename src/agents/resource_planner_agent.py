# -*- coding: utf-8 -*-
"""
ResourcePlannerAgent — 学习路径规划 Agent
=========================================
根据学生画像和知识结构，规划5阶段个性化学习路径。

来源: backend/agents/resource_planner.py (merged)
"""
from typing import Dict, Any
from .base_agent import BaseAgent

RESOURCE_PLANNER_SYSTEM = """你是一位学习路径规划师。
根据学生水平、偏好和知识结构，规划5阶段学习路径。
适配资源类型（视觉/代码/理论）和认知风格。
必须返回严格的JSON格式。"""


class ResourcePlannerAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="ResourcePlanner", role="学习路径规划师", llm_client=llm_client)
        self.system_prompt = RESOURCE_PLANNER_SYSTEM

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        course_name = task.get("course_name", "")
        student_profile = await self.read_shared_memory("student_profile", {})
        knowledge = await self.read_shared_memory("knowledge_structure", {})

        self.state.current_task = f"Planning learning path for {course_name}"
        prompt = f"""规划「{course_name}」的个性化学习路径。
学生画像：{student_profile}
知识结构：{knowledge}
返回JSON：{{"course_name": "", "stages": [{{"stage": 1, "name": "基础知识", "weeks": [{{"week": 1, "title": "", "tasks": [], "resources": []}}], "goals": []}}], "total_weeks": 0, "weekly_hours": 0, "roadmap_mermaid": "graph TD\\n  ...", "resource_strategy": {{}}}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.5)
        if self.llm and hasattr(self.llm, 'extract_json'):
            data = self.llm.extract_json(result["content"])
        else:
            data = None
        if data:
            await self.update_shared_memory("learning_path_plan", data)
            self.send_message("PPTGenerator", data, "resource_plan")
            self.send_message("QuestionGenerator", data, "resource_plan")
            self.send_message("MindMapGenerator", data, "resource_plan")
            self.send_message("CodingPractice", data, "resource_plan")
            self.send_message("VideoScript", data, "resource_plan")
        return data or {"error": "Failed to parse", "raw": result["content"]}

    def update_knowledge_structure(self, knowledge: Dict):
        """接收 knowledge_structure 消息时调用。"""
        self._log(f"Knowledge structure updated")
