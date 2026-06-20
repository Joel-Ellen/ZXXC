# -*- coding: utf-8 -*-
"""
VideoScriptAgent — 教学视频脚本 Agent
=====================================
生成带有画面注释的教学视频脚本。

来源: backend/agents/video_script.py (merged)
"""
from typing import Dict, Any
from .base_agent import BaseAgent

VIDEO_SCRIPT_SYSTEM = """你是一位教学视频编导。
生成带有画面注释的脚本。支持风格：lecture/animation/screencast/mixed。
必须返回严格的JSON格式。"""


class VideoScriptAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(name="VideoScript", role="教学视频编导", llm_client=llm_client)
        self.system_prompt = VIDEO_SCRIPT_SYSTEM

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        topic = task.get("topic", "")
        course_name = task.get("course_name", "")
        style = task.get("style", "lecture")
        duration_minutes = task.get("duration_minutes", 15)

        self.state.current_task = f"Generating video script: {topic}"
        prompt = f"""为「{course_name}」的「{topic}」生成教学视频脚本。
风格：{style}，时长：{duration_minutes}分钟
返回JSON：{{"title": "", "segments": [{{"id": 0, "time_range": "", "narration": "", "visual": "", "notes": ""}}], "total_duration": ""}}"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        if self.llm and hasattr(self.llm, 'extract_json'):
            return self.llm.extract_json(result["content"]) or {"segments": [], "raw": result["content"]}
        return {"segments": [], "raw": result["content"]}
