"""
Video Script Agent - 教学视频脚本生成Agent
生成教学视频文案、动画讲解脚本
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent


VIDEO_SCRIPT_SYSTEM = """你是一位资深的教学视频编导和内容创作者。

你的任务是为知识点生成高质量的教学视频脚本和动画讲解文案。

脚本要求：
1. 开场吸引注意力（问题/故事/现象引入）
2. 内容由浅入深，逻辑清晰
3. 每3-5分钟一个知识小节
4. 配合画面说明（动画/图表/代码演示）
5. 设置互动环节（提问/思考题）
6. 结尾总结要点+预告下集

画面描述格式：
[画面: 描述画面内容]
[动画: 描述动画效果]
[字幕: 重点文字]
[代码演示: 展示代码]

必须返回严格的JSON格式结果。"""


class VideoScriptAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="VideoScript",
            role="教学视频脚本创作专家",
        )
        self.system_prompt = VIDEO_SCRIPT_SYSTEM
        self.plan: Dict = {}

    def update_plan(self, plan: Dict):
        self.plan = plan
        self._log("Resource plan updated")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate video script.

        Task params:
        - topic: Video topic
        - course_name: Course name
        - duration_minutes: Target video duration
        - style: "lecture" / "animation" / "screencast" / "mixed"
        - segments: Number of segments (default 4)
        """
        topic = task.get("topic", "神经网络基础")
        course_name = task.get("course_name", "人工智能")
        duration = task.get("duration_minutes", 20)
        style = task.get("style", "mixed")
        segments = task.get("segments", 4)

        self.state.current_task = f"Generating video script: {topic}"

        style_instructions = {
            "lecture": "教师出镜讲解风格，配合PPT演示",
            "animation": "全动画风格，图形化展示概念，无教师出镜",
            "screencast": "屏幕录制风格，重点展示代码和实操",
            "mixed": "混合风格：教师出镜引入 + 动画讲解概念 + 代码演示实操",
        }

        prompt = f"""请为「{course_name}」课程的「{topic}」生成教学视频脚本。

## 参数
- 视频时长：{duration}分钟
- 风格：{style}（{style_instructions.get(style, '')}）
- 分段数：{segments}个知识小节

## 脚本结构
1. 片头（30秒）：吸引注意力的引入
2. 内容分段（{segments}段，每段3-5分钟）
3. 互动环节（30秒）
4. 片尾总结（1分钟）

## 画面描述要求
使用以下标注：
- `[画面:]` 描述镜头画面
- `[动画:]` 描述动画效果
- `[字幕:]` 关键字幕文字
- `[代码:]` 展示的代码
- `[音效:]` 音效提示
- `[转场:]` 转场效果
- `[互动:]` 互动提问

返回JSON：
{{
    "metadata": {{
        "title": "视频标题",
        "course_name": "{course_name}",
        "topic": "{topic}",
        "duration_minutes": {duration},
        "style": "{style}",
        "target_audience": "目标观众描述",
        "learning_objectives": ["学习目标"]
    }},
    "script": {{
        "opening": {{
            "duration_seconds": 30,
            "narration": "旁白/讲解文字",
            "visual": "画面描述",
            "hook": "吸引注意力的钩子"
        }},
        "segments": [
            {{
                "segment_number": 1,
                "title": "小节标题",
                "duration_minutes": 5,
                "narration": "完整旁白文字",
                "visual_description": "画面和动画描述",
                "key_points": ["关键知识点"],
                "code_demo": "代码演示内容（如适用）",
                "transition": "转到下一节的过渡语"
            }}
        ],
        "interaction": {{
            "duration_seconds": 30,
            "question": "互动问题",
            "pause_hint": "提示暂停思考"
        }},
        "closing": {{
            "duration_seconds": 60,
            "summary": "要点总结",
            "next_preview": "下集预告",
            "homework": "课后练习建议"
        }}
    }},
    "full_script_text": "完整口播文字稿（不含画面描述）",
    "production_notes": "制作注意事项（录制建议、素材需求等）"
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.8)
        data = self.llm.extract_json(result["content"])
        return data or {"error": "Failed to generate video script", "raw": result["content"]}
