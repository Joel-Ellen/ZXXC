"""
Knowledge Analysis Agent - 知识点拆解Agent
分析课程知识体系，拆解知识点，构建知识图谱结构
"""
import json
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent


KNOWLEDGE_ANALYSIS_SYSTEM = """你是一位资深的课程设计专家和知识工程师。

你的任务是将课程知识体系进行系统化拆解，构建层次化的知识点结构。

你需要：
1. 将课程按主题分解为知识模块
2. 每个模块细分为具体知识点
3. 标注知识点间的依赖关系（前置知识）
4. 标注每个知识点的难度等级
5. 标注推荐学习时长
6. 关联相应的学习资源类型

难度分级：
- L1-入门: 概念理解级别
- L2-基础: 能够应用
- L3-进阶: 能够分析
- L4-高级: 能够综合
- L5-专家: 能够创新

必须返回严格的JSON格式结果。"""


class KnowledgeAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="KnowledgeAnalysis",
            role="知识体系分析专家",
        )
        self.system_prompt = KNOWLEDGE_ANALYSIS_SYSTEM
        self.student_context: Dict = {}

    def update_student_context(self, profile: Dict):
        """Receive student profile updates"""
        self.student_context = profile
        self._log("Student context updated")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute knowledge analysis.

        Task params:
        - course_name: Course to analyze (e.g., "人工智能")
        - student_profile: Student profile for personalization
        - mode: "full_analysis" / "topic_deep_dive" / "prerequisite_check"
        - topic: Specific topic for deep dive (optional)
        """
        course_name = task.get("course_name", "人工智能")
        mode = task.get("mode", "full_analysis")
        topic = task.get("topic", "")

        # Use student context from shared memory if available
        student_profile = task.get("student_profile") or self.student_context or \
                         self.read_shared_memory("student_profile", {})

        if mode == "full_analysis":
            return await self._full_analysis(course_name, student_profile)
        elif mode == "topic_deep_dive":
            return await self._topic_deep_dive(course_name, topic, student_profile)
        elif mode == "prerequisite_check":
            return await self._prerequisite_check(course_name, topic, student_profile)
        else:
            return await self._full_analysis(course_name, student_profile)

    async def _full_analysis(
        self, course_name: str, student_profile: Dict
    ) -> Dict[str, Any]:
        """Complete knowledge structure analysis for a course"""
        self.state.current_task = f"Analyzing knowledge structure: {course_name}"

        student_info = json.dumps({
            "knowledge_level": student_profile.get("knowledge_level", {}).get("label", "未知"),
            "interest": student_profile.get("interest_direction", {}).get("label", "未知"),
            "weak_points": student_profile.get("weak_points", {}).get("description", "未知"),
        }, ensure_ascii=False)

        prompt = f"""请对「{course_name}」课程进行完整的知识体系分析。

学生画像：
{student_info}

请生成详细的知识结构，包含：

1. 5个学习阶段，每个阶段包含多个知识模块
2. 每个知识模块包含多个具体知识点
3. 标注知识点依赖关系和难度等级
4. 根据学生画像标注"重点关注"和"可能薄弱"的知识点

返回JSON格式：
{{
    "course_name": "{course_name}",
    "total_knowledge_points": 知识点总数,
    "difficulty_summary": {{
        "L1_count": 入门级知识点数量,
        "L2_count": 基础级知识点数量,
        "L3_count": 进阶数量,
        "L4_count": 高级数量,
        "L5_count": 专家数量
    }},
    "stages": [
        {{
            "stage_id": 1,
            "stage_name": "基础知识",
            "description": "阶段描述",
            "estimated_weeks": 建议学习周数,
            "modules": [
                {{
                    "module_name": "模块名称",
                    "description": "模块描述",
                    "knowledge_points": [
                        {{
                            "id": "KP_001",
                            "name": "知识点名称",
                            "description": "详细描述",
                            "difficulty": "L1-L5",
                            "estimated_hours": 建议学习小时数,
                            "prerequisites": ["前置知识点ID列表"],
                            "resource_types": ["video", "reading", "practice", "project"],
                            "tags": ["标签"],
                            "student_focus": "recommended|challenge|skip（基于学生画像的建议）"
                        }}
                    ]
                }}
            ]
        }}
    ],
    "knowledge_graph": {{
        "nodes": ["知识点节点ID列表"],
        "edges": [{{"from": "前置知识点ID", "to": "后置知识点ID", "relation": "requires"}}]
    }},
    "personalized_recommendations": {{
        "focus_areas": ["学生应该重点学习的知识点"],
        "skip_or_fast": ["可以快速通过的知识点"],
        "challenge_areas": ["有挑战性的知识点"]
    }}
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.5)
        data = self.llm.extract_json(result["content"])
        if not data:
            return {"error": "Failed to parse knowledge analysis", "raw": result["content"]}

        # Store in shared memory
        self.update_shared_memory("knowledge_structure", data)
        self.update_shared_memory(f"knowledge_{course_name}", data)

        # Notify dependent agents
        self.send_message("ResourcePlanner", data, "knowledge_structure")

        return data

    async def _topic_deep_dive(
        self, course_name: str, topic: str, student_profile: Dict
    ) -> Dict[str, Any]:
        """Deep analysis of a specific topic"""
        prompt = f"""对「{course_name}」课程中的「{topic}」进行深度知识点拆解。

请详细列出该主题下的所有子知识点，包括：
- 概念定义
- 核心原理
- 关键算法/方法
- 常见误区
- 实践要点
- 延伸学习方向

返回JSON格式。
"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.3)
        data = self.llm.extract_json(result["content"])
        return data or {"raw": result["content"]}

    async def _prerequisite_check(
        self, course_name: str, topic: str, student_profile: Dict
    ) -> Dict[str, Any]:
        """Check if student has prerequisites for a topic"""
        mastered = student_profile.get("mastered_knowledge", [])
        prompt = f"""学生已掌握：{json.dumps(mastered, ensure_ascii=False)}
目标学习：「{course_name}」-「{topic}」

分析：
1. 该主题需要哪些前置知识
2. 学生已具备哪些前置知识
3. 学生还缺少哪些前置知识
4. 建议的补课路径

返回JSON。"""
        result = await self.chat_llm(prompt, json_mode=True, temperature=0.3)
        data = self.llm.extract_json(result["content"])
        return data or {"raw": result["content"]}
