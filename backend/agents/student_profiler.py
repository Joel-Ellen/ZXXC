"""
Student Profiler Agent - 学生画像构建Agent
通过自然语言对话自动构建动态学习画像
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent


STUDENT_PROFILER_SYSTEM = """你是一位专业的教育测评专家和学生学习顾问。

你的任务是通过自然友好的对话，逐步了解学生的背景信息，并构建其学习画像。

你需要从对话中提取以下维度信息：
1. **专业背景** (major_background): 所学专业、年级、院校
2. **知识基础水平** (knowledge_level): 已掌握的知识点、技能水平
3. **学习能力** (learning_ability): 学习速度、理解能力、自学能力
4. **学习偏好** (learning_preference): 偏好的学习方式（视频/阅读/实践/互动）
5. **认知风格** (cognitive_style): 视觉型/听觉型/动手型/理论型
6. **易错知识点** (weak_points): 容易犯错的知识领域
7. **兴趣方向** (interest_direction): 感兴趣的课程方向和技术领域
8. **职业目标** (career_goal): 职业规划和发展方向

对话策略：
- 不要一次性问所有问题，分2-3轮自然对话
- 根据学生回答动态调整问题
- 使用开放式问题引导深入回答
- 对学生的回答表示理解和共情
- 从回答中推断隐含信息

你必须返回严格的JSON格式结果。"""


class StudentProfilerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="StudentProfiler",
            role="学生画像构建专家",
        )
        self.system_prompt = STUDENT_PROFILER_SYSTEM
        self.conversation_round = 0
        self.collected_info = {}

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute profile building.

        Task params:
        - message: User's natural language input
        - conversation_history: Previous conversation messages
        - mode: "extract" (extract profile from message) or "converse" (generate next question)
        - existing_profile: Previously built profile for updating
        """
        mode = task.get("mode", "extract")
        message = task.get("message", "")
        history = task.get("conversation_history", [])
        existing_profile = task.get("existing_profile", {})

        if mode == "extract":
            return await self._extract_profile(message, history, existing_profile)
        elif mode == "converse":
            return await self._generate_next_question(message, history, existing_profile)
        elif mode == "update":
            return await self._update_profile(message, existing_profile)
        else:
            return await self._extract_profile(message, history, existing_profile)

    async def _extract_profile(
        self,
        message: str,
        history: List[Dict],
        existing: Dict,
    ) -> Dict[str, Any]:
        """Extract profile information from user message"""
        self.state.current_task = "Extracting student profile from conversation"

        prompt = f"""请从以下学生对话中提取学习画像信息。

已有画像信息：
{json.dumps(existing, ensure_ascii=False, indent=2) if existing else "无（首次构建）"}

对话历史：
{json.dumps(history[-6:] if history else [], ensure_ascii=False, indent=2)}

最新学生消息：
"{message}"

请分析并返回更新后的完整画像。对于每个维度，提供：
- score: 0-100的能力/匹配度评分
- label: 简短标签
- description: 详细描述
- evidence: 从对话中得出的证据列表
- confidence: 该维度评估的置信度(0-1)

返回JSON：
{{
    "profile_update": {{
        "major": "专业名称或null",
        "grade": "年级或null",
        "university": "院校或null",
        "learning_goal": "学习目标描述",
        "weekly_study_hours": 每周学习小时数或null,
        "mastered_knowledge": ["已掌握知识点列表"],
        "learning_history": ["学习经历描述"],
        "dimensions": {{
            "major_background": {{"score": 0-100, "label": "", "description": "", "evidence": [], "confidence": 0.0-1.0}},
            "knowledge_level": {{"score": 0-100, "label": "", "description": "", "evidence": [], "confidence": 0.0-1.0}},
            "learning_ability": {{"score": 0-100, "label": "", "description": "", "evidence": [], "confidence": 0.0-1.0}},
            "learning_preference": {{"score": 0-100, "label": "", "description": "", "evidence": [], "confidence": 0.0-1.0}},
            "cognitive_style": {{"score": 0-100, "label": "", "description": "", "evidence": [], "confidence": 0.0-1.0}},
            "weak_points": {{"score": 0-100, "label": "", "description": "", "evidence": [], "confidence": 0.0-1.0}},
            "interest_direction": {{"score": 0-100, "label": "", "description": "", "evidence": [], "confidence": 0.0-1.0}},
            "career_goal": {{"score": 0-100, "label": "", "description": "", "evidence": [], "confidence": 0.0-1.0}}
        }}
    }},
    "profile_version": {existing.get("profile_version", 1) + 1 if existing else 1},
    "confidence_score": 0.0-1.0（整体画像置信度）,
    "missing_info": ["还需要了解的信息"],
    "next_question": "下一步应该问的问题（如果信息充足则为null）",
    "summary": "对学生的简短总结（50字以内）"
}}"""

        result = await self.chat_llm(prompt, json_mode=True)
        data = self.llm.extract_json(result["content"])
        if not data:
            return {"error": "Failed to parse profile", "raw": result["content"]}

        # Update shared memory
        await self.update_shared_memory("student_profile", data.get("profile_update", {}))
        await self.update_shared_memory("student_summary", data.get("summary", ""))

        # Send update to dependent agents
        self.send_message(
            "KnowledgeAnalysis",
            data.get("profile_update", {}),
            "profile_update",
        )

        return data

    async def _generate_next_question(
        self,
        message: str,
        history: List[Dict],
        existing: Dict,
    ) -> Dict[str, Any]:
        """Generate the next conversational question"""
        prompt = f"""你是学生学习顾问。根据已有信息，生成下一个自然对话问题。

已有画像：
{json.dumps(existing, ensure_ascii=False, indent=2) if existing else "无"}

对话历史（最近3轮）：
{json.dumps(history[-6:] if history else [], ensure_ascii=False, indent=2)}

学生最新消息："{message}"

请返回JSON：
{{
    "response_message": "你的回复内容（包含共情+下一个问题，保持自然对话感）",
    "next_question": "核心问题",
    "question_purpose": "这个问题的目的（对应哪个画像维度）",
    "info_collected_so_far": "已收集信息的简要总结"
}}

要求：
- 语气温暖友好
- 问题自然不生硬
- 一次只问1-2个核心问题
- 基于已有信息进行追问（不重复已知道的内容）
"""

        result = await self.chat_llm(prompt, json_mode=True)
        data = self.llm.extract_json(result["content"])
        return data or {"response_message": result["content"]}

    async def _update_profile(
        self,
        message: str,
        existing: Dict,
    ) -> Dict[str, Any]:
        """Incrementally update existing profile"""
        return await self._extract_profile(message, [], existing)
