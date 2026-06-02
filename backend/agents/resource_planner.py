"""
Resource Planner Agent - 学习资源规划Agent
根据学生画像和知识结构，规划个性化学习路径和资源
"""
import json
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent


RESOURCE_PLANNER_SYSTEM = """你是一位资深的学习路径规划师和教学设计专家。

你的任务是根据学生的个人画像和课程知识结构，规划个性化的学习路径。

你需要：
1. 根据学生当前水平确定学习起点
2. 规划5个学习阶段的详细路线
3. 为每个阶段分配具体的学习任务
4. 推荐适合的学习资源类型
5. 制定每周学习计划
6. 设置阶段性的学习里程碑

资源类型适配：
- 视觉型学习者：优先推荐视频、思维导图、PPT
- 动手型学习者：优先推荐编程实践、项目实战
- 理论型学习者：优先推荐讲义、论文、深度阅读
- 互动型学习者：优先推荐问答、讨论、习题

必须返回严格的JSON格式结果。"""


class ResourcePlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ResourcePlanner",
            role="学习路径规划专家",
        )
        self.system_prompt = RESOURCE_PLANNER_SYSTEM
        self.knowledge_structure: Dict = {}
        self.student_profile: Dict = {}

    def update_knowledge_structure(self, data: Dict):
        """Receive knowledge structure from KnowledgeAnalysisAgent"""
        self.knowledge_structure = data
        self._log("Knowledge structure updated")

    def update_plan(self, data: Dict):
        """Receive resource plan updates"""
        pass

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute learning path planning.

        Task params:
        - course_name: Target course
        - student_profile: Student profile (auto-loaded from shared memory if not provided)
        - knowledge_structure: Knowledge analysis result
        - weekly_hours: Available study hours per week
        - duration_weeks: Target duration
        - target_level: Target proficiency level
        """
        course_name = task.get("course_name", "人工智能")
        weekly_hours = task.get("weekly_hours", 10)
        duration_weeks = task.get("duration_weeks", 16)
        target_level = task.get("target_level", "advanced")

        # Load from shared memory
        self.student_profile = (
            task.get("student_profile") or
            self.read_shared_memory("student_profile", {})
        )
        self.knowledge_structure = (
            task.get("knowledge_structure") or
            self.knowledge_structure or
            self.read_shared_memory("knowledge_structure", {})
        )

        return await self._plan_learning_path(
            course_name, weekly_hours, duration_weeks, target_level
        )

    async def _plan_learning_path(
        self,
        course_name: str,
        weekly_hours: int,
        duration_weeks: int,
        target_level: str,
    ) -> Dict[str, Any]:
        """Generate comprehensive learning path plan"""
        self.state.current_task = f"Planning learning path for {course_name}"

        # Determine learning preference for resource type weighting
        learning_pref = self.student_profile.get("learning_preference", {})
        cognitive = self.student_profile.get("cognitive_style", {})
        weak_points = self.student_profile.get("weak_points", {})
        interest = self.student_profile.get("interest_direction", {})

        prompt = f"""请为该学生规划「{course_name}」课程的个性化学习路径。

## 学生画像
- 知识水平：{json.dumps(self.student_profile.get('knowledge_level', {}), ensure_ascii=False)}
- 学习偏好：{json.dumps(learning_pref, ensure_ascii=False)}
- 认知风格：{json.dumps(cognitive, ensure_ascii=False)}
- 薄弱点：{json.dumps(weak_points, ensure_ascii=False)}
- 兴趣方向：{json.dumps(interest, ensure_ascii=False)}
- 已掌握知识：{json.dumps(self.student_profile.get('mastered_knowledge', []), ensure_ascii=False)}
- 学习目标：{self.student_profile.get('learning_goal', '未指定')}

## 学习参数
- 每周可用时间：{weekly_hours}小时
- 目标周期：{duration_weeks}周
- 目标水平：{target_level}

## 知识结构参考
{json.dumps(self.knowledge_structure.get('stages', [])[:3], ensure_ascii=False, indent=2) if self.knowledge_structure.get('stages') else '无（请基于课程通用知识结构规划）'}

请生成完整的学习路径规划JSON：

{{
    "course_name": "{course_name}",
    "plan_overview": {{
        "total_weeks": {duration_weeks},
        "weekly_hours": {weekly_hours},
        "target_level": "{target_level}",
        "start_level": "当前水平评估",
        "learning_strategy": "整体学习策略描述"
    }},
    "stages": [
        {{
            "stage_id": 1,
            "stage_name": "基础知识",
            "weeks": "第1-X周",
            "description": "阶段描述",
            "goals": ["阶段目标"],
            "topics": ["核心主题"],
            "weekly_plan": [
                {{
                    "week": 1,
                    "focus": "本周重点",
                    "tasks": [
                        {{
                            "title": "任务名称",
                            "type": "video|reading|practice|quiz|project",
                            "description": "任务描述",
                            "estimated_hours": 小时数,
                            "resource_type": "推荐资源类型",
                            "priority": "high|medium|low"
                        }}
                    ],
                    "milestone": "本周里程碑"
                }}
            ],
            "assessment": "阶段评估方式"
        }},
        ...共5个阶段
    ],
    "resource_recommendation_strategy": {{
        "preferred_types": ["根据学习偏好排序的资源类型"],
        "visual_to_hands_on_ratio": "视觉型vs动手型资源比例",
        "difficulty_progression": "难度递进策略"
    }},
    "personalized_tips": [
        "针对该学生的个性化学习建议"
    ],
    "roadmap_mermaid": "Mermaid格式的学习路线图代码（timeline或graph）"
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.6)
        data = self.llm.extract_json(result["content"])
        if not data:
            return {"error": "Failed to parse learning path", "raw": result["content"]}

        # Store in shared memory
        self.update_shared_memory("learning_path_plan", data)

        # Notify resource generation agents
        resource_plan = {
            "course_name": course_name,
            "stages": data.get("stages", []),
            "preferred_types": data.get("resource_recommendation_strategy", {}).get("preferred_types", []),
            "topics": [],
        }
        # Extract all topics across stages
        for stage in data.get("stages", []):
            for topic in stage.get("topics", []):
                resource_plan["topics"].append(topic)

        self.send_message("PPTGenerator", resource_plan, "resource_plan")
        self.send_message("QuestionGenerator", resource_plan, "resource_plan")
        self.send_message("MindMapGenerator", resource_plan, "resource_plan")
        self.send_message("CodingPractice", resource_plan, "resource_plan")
        self.send_message("VideoScript", resource_plan, "resource_plan")

        return data
