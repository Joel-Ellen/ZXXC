# -*- coding: utf-8 -*-
"""
KnowledgeAnalysisAgent — 知识体系分析 Agent
===========================================
将课程分解为层次化知识点结构，分析前置依赖关系。

来源: backend/agents/knowledge_analysis.py (merged)
"""
from typing import Dict, Any
from .base_agent import BaseAgent

KNOWLEDGE_ANALYSIS_SYSTEM = """你是一位课程设计专家。
将课程分解为层次化知识点结构，分为5个难度等级(L1-L5)。
分析前置依赖关系。必须返回严格的JSON格式。"""


class KnowledgeAnalysisAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="KnowledgeAnalysis", role="知识体系分析专家", llm_client=llm_client)
        self.system_prompt = KNOWLEDGE_ANALYSIS_SYSTEM

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        mode = task.get("mode", "full_analysis")
        course_name = task.get("course_name", "")
        topic = task.get("topic", "")

        self.state.current_task = f"Analyzing knowledge: {course_name}"
        student_profile = await self.read_shared_memory("student_profile", {})

        prompt = f"""分析「{course_name}」的知识体系结构。主题：{topic}
学生画像：{student_profile}
返回JSON：{{"course_name": "", "knowledge_tree": {{"root": {{"name": "", "children": []}}}}, "levels": [{{"level": 1, "name": "L1-基础", "topics": []}}], "prerequisites": {{}}, "estimated_hours": 0}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.5)
        if self.llm and hasattr(self.llm, 'extract_json'):
            data = self.llm.extract_json(result["content"])
        else:
            data = None
        if data:
            await self.update_shared_memory("knowledge_structure", data)
            await self.update_shared_memory(f"knowledge_{course_name}", data)
            self.send_message("ResourcePlanner", data, "knowledge_structure")
        return data or {"error": "Failed to parse", "raw": result["content"]}

    def update_student_context(self, profile: Dict):
        """接收 profile_update 消息时调用。"""
        self._log(f"Student context updated from profile")
