"""
PPT Generator Agent - PPT课件生成Agent
根据知识点和学习路径生成结构化PPT内容（Markdown格式，可转为PPT）
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent


PPT_GENERATOR_SYSTEM = """你是一位资深的教学课件设计师。

你的任务是为指定知识点生成结构化的PPT课件内容。

要求：
1. 每页PPT有清晰的标题和要点
2. 内容从易到难递进
3. 善用图表、代码示例、对比表格
4. 每页3-5个要点，避免文字过多
5. 包含开场页、目录页、内容页、总结页、Q&A页
6. 适合15-20分钟的讲解

输出Markdown格式，使用：
- ## 标题 表示幻灯片标题
- --- 分隔每页幻灯片
- 使用表格、代码块增强表现力

必须返回严格的JSON格式，包含Markdown内容和结构化slides数组。"""


class PPTGeneratorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="PPTGenerator",
            role="课件生成专家",
        )
        self.system_prompt = PPT_GENERATOR_SYSTEM
        self.plan: Dict = {}

    def update_plan(self, plan: Dict):
        self.plan = plan
        self._log(f"Resource plan received: {plan.get('course_name', '')}")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate PPT content.

        Task params:
        - topic: Lecture topic
        - course_name: Course name
        - difficulty: Difficulty level
        - slide_count: Number of slides (default 15)
        - knowledge_points: Specific knowledge points to cover
        - style: "visual" / "code-heavy" / "theory"
        """
        topic = task.get("topic", "人工智能概述")
        course_name = task.get("course_name", "人工智能")
        difficulty = task.get("difficulty", "basic")
        slide_count = task.get("slide_count", 15)
        style = task.get("style", "visual")

        self.state.current_task = f"Generating PPT: {topic}"

        prompt = f"""请为「{course_name}」课程生成关于「{topic}」的PPT课件。

## 参数
- 难度：{difficulty}
- 幻灯片数：{slide_count}页
- 风格：{style}

## 要求
每页PPT格式（用---分隔）：
## 幻灯片标题
- 要点1
- 要点2
- 要点3
[可包含代码块、表格、图表说明]

幻灯片结构：
1. 封面页（标题+副标题）
2. 目录/大纲页
3-{slide_count-3}. 内容页（知识点讲解）
{slide_count-2}. 本章总结
{slide_count-1}. 思考题
{slide_count}. 参考资料

返回JSON：
{{
    "title": "PPT标题",
    "topic": "{topic}",
    "course_name": "{course_name}",
    "difficulty": "{difficulty}",
    "slide_count": 实际幻灯片数,
    "estimated_duration_minutes": 预计讲解时长,
    "slides": [
        {{
            "slide_number": 1,
            "title": "幻灯片标题",
            "type": "cover|toc|content|summary|questions|references",
            "content_markdown": "幻灯片Markdown内容（包含---格式）",
            "speaker_notes": "讲师备注",
            "visual_suggestion": "建议的图表/图示类型"
        }}
    ],
    "full_markdown": "完整PPT的Markdown文本（所有幻灯片以---分隔）"
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        data = self.llm.extract_json(result["content"])
        return data or {"error": "Failed to generate PPT", "raw": result["content"]}
