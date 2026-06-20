# -*- coding: utf-8 -*-
"""
MindMapGeneratorAgent — 思维导图生成 Agent
===========================================
以 Mermaid mindmap 格式输出知识结构可视化。

来源: backend/agents/mindmap_generator.py (merged)
"""
from typing import Dict, Any
from .base_agent import BaseAgent

MINDMAP_GENERATOR_SYSTEM = """你是一位知识可视化设计师。
以 Mermaid mindmap 格式输出。结构不超过4层，标签简洁，逻辑清晰。
必须返回严格的JSON格式。"""


class MindMapGeneratorAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="MindMapGenerator", role="思维导图生成专家", llm_client=llm_client)
        self.system_prompt = MINDMAP_GENERATOR_SYSTEM

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        topic = task.get("topic", "")
        course_name = task.get("course_name", "")
        knowledge_structure = task.get("knowledge_structure", {})

        self.state.current_task = f"Generating mindmap: {topic}"
        prompt = f"""为「{course_name}」的「{topic}」生成思维导图。
知识结构参考：{knowledge_structure}
返回JSON：{{"title": "", "mermaid_code": "mindmap\\n  root(...)", "root": {{"label": "", "children": []}}, "key_concepts": []}}
只输出 Mermaid mindmap 格式！"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.5)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"mermaid_code": result["content"]}
        return {"mermaid_code": result["content"]}
