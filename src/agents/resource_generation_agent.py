# -*- coding: utf-8 -*-
"""
Unified resource generation agent.

Five former resource agents shared almost identical control flow. This class
keeps their differences in a small config table while centralizing prompt use,
JSON parsing and output normalization.
"""

from __future__ import annotations

from typing import Any, Dict

from .base_agent import BaseAgent
from .prompt_registry import build_user_prompt, get_system_prompt


RESOURCE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "ppt": {
        "name": "PPTGenerator",
        "role": "课件生成专家",
        "prompt_key": "resource_generation.ppt",
        "temperature": 0.7,
        "fallback": "full_markdown",
        "default_result": {"full_markdown": "", "slides": []},
    },
    "quiz": {
        "name": "QuestionGenerator",
        "role": "出题专家",
        "prompt_key": "resource_generation.quiz",
        "temperature": 0.6,
        "fallback": "raw",
        "default_result": {"questions": [], "total_score": 0, "estimated_time_minutes": 0},
    },
    "mindmap": {
        "name": "MindMapGenerator",
        "role": "思维导图生成专家",
        "prompt_key": "resource_generation.mindmap",
        "temperature": 0.5,
        "fallback": "mermaid_code",
        "default_result": {"mermaid_code": "", "root": {}, "key_concepts": []},
    },
    "coding": {
        "name": "CodingPractice",
        "role": "编程实战导师",
        "prompt_key": "resource_generation.coding",
        "temperature": 0.4,
        "fallback": "overview_markdown",
        "default_result": {"title": "", "exercises": [], "overview_markdown": ""},
    },
    "video": {
        "name": "VideoScript",
        "role": "教学视频编导",
        "prompt_key": "resource_generation.video",
        "temperature": 0.7,
        "fallback": "overview_markdown",
        "default_result": {"title": "", "segments": [], "overview_markdown": ""},
    },
}


class ResourceGenerationAgent(BaseAgent):
    def __init__(self, resource_kind: str, llm_client=None):
        if resource_kind not in RESOURCE_CONFIGS:
            raise ValueError(f"Unsupported resource kind: {resource_kind}")
        self.resource_kind = resource_kind
        self.config = RESOURCE_CONFIGS[resource_kind]
        super().__init__(
            name=self.config["name"],
            role=self.config["role"],
            llm_client=llm_client,
        )
        self.system_prompt = get_system_prompt(self.config["prompt_key"])

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        topic = task.get("topic", "")
        course_name = task.get("course_name", "")
        difficulty = task.get("difficulty", "basic")

        self.state.current_task = f"Generating {self.resource_kind}: {topic}"
        prompt = build_user_prompt(
            self.config["prompt_key"],
            topic=topic,
            course_name=course_name,
            difficulty=difficulty,
            slide_count=task.get("slide_count", 15),
            style=task.get("style", "visual"),
            question_count=task.get("question_count", 10),
            question_types=task.get("question_types", ["choice", "true_false", "short_answer"]),
            knowledge_structure=task.get("knowledge_structure", {}),
            language=task.get("language", "python"),
            count=task.get("count", 3),
            duration_minutes=task.get("duration_minutes", 15),
        )

        result = await self.chat_llm(
            prompt,
            system_prompt=self.system_prompt,
            json_mode=True,
            temperature=self.config["temperature"],
        )
        parsed = self._parse_result(result.get("content", ""))
        if parsed is not None:
            return parsed

        fallback_key = self.config["fallback"]
        fallback_payload = dict(self.config["default_result"])
        fallback_payload[fallback_key] = result.get("content", "")
        fallback_payload["raw"] = result.get("content", "")
        return fallback_payload

    def _parse_result(self, content: str) -> Dict[str, Any] | None:
        if self.llm and hasattr(self.llm, "extract_json"):
            data = self.llm.extract_json(content)
            if data:
                return data
        return None


class PPTGeneratorAgent(ResourceGenerationAgent):
    def __init__(self, llm_client=None):
        super().__init__("ppt", llm_client=llm_client)


class QuestionGeneratorAgent(ResourceGenerationAgent):
    def __init__(self, llm_client=None):
        super().__init__("quiz", llm_client=llm_client)


class MindMapGeneratorAgent(ResourceGenerationAgent):
    def __init__(self, llm_client=None):
        super().__init__("mindmap", llm_client=llm_client)


class CodingPracticeAgent(ResourceGenerationAgent):
    def __init__(self, llm_client=None):
        super().__init__("coding", llm_client=llm_client)


class VideoScriptAgent(ResourceGenerationAgent):
    def __init__(self, llm_client=None):
        super().__init__("video", llm_client=llm_client)
