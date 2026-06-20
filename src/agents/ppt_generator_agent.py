# -*- coding: utf-8 -*-
"""
PPTGeneratorAgent — PPT 课件生成 Agent
======================================
根据知识点生成结构化 PPT 内容（Markdown 格式）。

来源: backend/agents/ppt_generator.py (merged)
"""
import json
from typing import Dict, Any
from .base_agent import BaseAgent

PPT_GENERATOR_SYSTEM = """你是一位资深的教学课件设计师。
输出Markdown格式PPT：## 标题表示幻灯片标题，--- 分隔每页。
15-20分钟讲解，包含开场/目录/内容/总结/Q&A页。
必须返回严格的JSON格式。"""


class PPTGeneratorAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="PPTGenerator", role="课件生成专家", llm_client=llm_client)
        self.system_prompt = PPT_GENERATOR_SYSTEM

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        topic = task.get("topic", "人工智能概述")
        course_name = task.get("course_name", "")
        difficulty = task.get("difficulty", "basic")
        slide_count = task.get("slide_count", 15)
        style = task.get("style", "visual")

        self.state.current_task = f"Generating PPT: {topic}"
        prompt = f"""为「{course_name}」生成关于「{topic}」的PPT课件。
难度：{difficulty}，幻灯片：{slide_count}页，风格：{style}
返回JSON：{{"title": "", "slides": [{{"slide_number": 1, "title": "", "content_markdown": "", "speaker_notes": ""}}], "full_markdown": "完整PPT Markdown"}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"full_markdown": result["content"]}
        return {"full_markdown": result["content"]}
