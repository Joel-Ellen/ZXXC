"""
Evaluation Agent - 学习效果评估Agent
分析学习数据，生成评估报告和改进建议
"""
import json
from typing import Dict, Any, List
from datetime import datetime
from .base_agent import BaseAgent


EVALUATION_SYSTEM = """你是一位资深的教育评估专家和学习分析师。

你的任务是基于学生的学习数据，生成全面的学习效果评估报告。

评估维度：
1. 知识掌握度（基于测验成绩）
2. 学习投入度（学习时长、完成任务数）
3. 学习效率（单位时间掌握知识点数）
4. 薄弱领域识别（错题分析）
5. 进步趋势（与历史数据对比）
6. 学习习惯评估

评估报告要求：
- 数据驱动，所有结论有数据支撑
- 既指出问题也肯定进步
- 建议具体可执行
- 关注学生的个性化特点

必须返回严格的JSON格式结果。"""


class EvaluationAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Evaluation",
            role="学习评估分析师",
        )
        self.system_prompt = EVALUATION_SYSTEM
        self.learning_records: List[Dict] = []

    def update_records(self, records: List[Dict]):
        """Receive learning records for analysis"""
        self.learning_records = records
        self._log(f"Received {len(records)} learning records")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate learning evaluation report.

        Task params:
        - course_name: Course name
        - period_days: Evaluation period in days
        - quiz_records: Quiz and exercise records
        - study_logs: Study activity logs
        - learning_path: Student's learning path data
        - student_profile: Student profile
        """
        course_name = task.get("course_name", "人工智能")
        period_days = task.get("period_days", 30)
        quiz_records = task.get("quiz_records", [])
        study_logs = task.get("study_logs", [])

        self.state.current_task = f"Generating evaluation report for {course_name}"

        # Load from shared memory
        student_profile = task.get("student_profile") or \
                         await self.read_shared_memory("student_profile", {})
        learning_path = task.get("learning_path") or \
                       await self.read_shared_memory("learning_path_plan", {})

        return await self._generate_report(
            course_name, period_days, quiz_records, study_logs,
            student_profile, learning_path,
        )

    async def _generate_report(
        self,
        course_name: str,
        period_days: int,
        quiz_records: List[Dict],
        study_logs: List[Dict],
        student_profile: Dict,
        learning_path: Dict,
    ) -> Dict[str, Any]:
        """Generate comprehensive evaluation report"""

        # Calculate basic metrics
        total_study_hours = sum(log.get("duration_hours", 0) for log in study_logs)
        total_quizzes = len(quiz_records)
        avg_score = (
            sum(r.get("score", 0) / max(r.get("total_score", 1), 1) * 100 for r in quiz_records) / total_quizzes
            if total_quizzes > 0 else 0
        )

        # Analyze errors by knowledge point
        error_analysis = {}
        for record in quiz_records:
            if record.get("feedback"):
                for fb in record["feedback"]:
                    kp = fb.get("knowledge_point", "unknown")
                    if kp not in error_analysis:
                        error_analysis[kp] = {"errors": 0, "total": 0}
                    error_analysis[kp]["errors"] += 1 if not fb.get("correct") else 0
                    error_analysis[kp]["total"] += 1

        weak_areas = [
            {"knowledge_point": kp, "error_rate": v["errors"] / max(v["total"], 1)}
            for kp, v in sorted(error_analysis.items(), key=lambda x: x[1]["errors"], reverse=True)
        ]

        prompt = f"""请基于以下学习数据生成学习效果评估报告。

## 学生画像
{json.dumps({
    "knowledge_level": student_profile.get('knowledge_level', {}).get('label', '未知'),
    "learning_preference": student_profile.get('learning_preference', {}).get('label', '未知'),
    "weak_points": student_profile.get('weak_points', {}).get('description', '未知'),
    "career_goal": student_profile.get('career_goal', {}).get('label', '未知'),
}, ensure_ascii=False)}

## 学习数据
- 课程：{course_name}
- 评估周期：最近{period_days}天
- 总学习时长：{total_study_hours:.1f}小时
- 完成测验：{total_quizzes}次
- 平均得分：{avg_score:.1f}分
- 薄弱知识点：{json.dumps(weak_areas[:5], ensure_ascii=False)}

## 学习路径进度
{json.dumps({
    "current_stage": learning_path.get('current_stage', '未知'),
    "completed_weeks": learning_path.get('completed_weeks', 0),
    "total_weeks": learning_path.get('total_weeks', 0),
}, ensure_ascii=False)}

请生成完整评估报告JSON：
{{
    "report_metadata": {{
        "course_name": "{course_name}",
        "evaluation_date": "{datetime.utcnow().isoformat()}",
        "period_days": {period_days},
        "overall_grade": "A/B/C/D/F（综合评级）",
        "overall_score": 综合评分0-100
    }},
    "metrics": {{
        "study_hours": {total_study_hours},
        "tasks_completed": 完成任务数,
        "total_tasks": 总任务数,
        "completion_rate": 完成率0-1,
        "quiz_avg_score": {avg_score:.1f},
        "quiz_count": {total_quizzes},
        "error_rate": 总体错误率0-1,
        "knowledge_coverage": 知识覆盖率0-1
    }},
    "current_level": {{
        "level": "当前水平等级",
        "description": "水平描述",
        "percentile": 在同级学习者中的百分位（估计）
    }},
    "strengths": [
        {{"area": "优势领域", "evidence": "证据", "score": 分数}}
    ],
    "weak_areas": [
        {{"knowledge_point": "薄弱知识点", "error_rate": 错误率, "suggested_focus": "建议关注重点"}}
    ],
    "progress_trend": {{
        "direction": "improving|stable|declining",
        "description": "趋势描述",
        "key_indicators": ["关键指标变化"]
    }},
    "learning_habit_analysis": {{
        "consistency": "学习一致性评价（高/中/低）",
        "peak_study_time": "最佳学习时段",
        "efficiency_score": 学习效率评分0-100,
        "habit_strengths": ["好习惯"],
        "habit_improvements": ["需要改进的习惯"]
    }},
    "suggestions": [
        {{
            "category": "学习方法|时间管理|知识点|资源选择|心态调整",
            "suggestion": "具体建议",
            "priority": "high|medium|low",
            "expected_impact": "预期效果描述"
        }}
    ],
    "next_stage_plan": {{
        "next_focus": "下一阶段重点",
        "recommended_actions": ["推荐行动"],
        "estimated_weeks": 预计需要周数,
        "target_milestones": ["目标里程碑"]
    }},
    "report_content": "完整的Markdown格式评估报告文本（适合展示给学生）",
    "radar_chart_data": {{
        "labels": ["知识掌握", "学习投入", "实践能力", "理论理解", "应用创新", "学习效率"],
        "scores": [各维度0-100分数],
        "average": 平均分
    }}
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.5)
        data = self.llm.extract_json(result["content"])

        # Store evaluation in shared memory
        if data:
            await self.update_shared_memory("latest_evaluation", data)
            # Send to LearningCoach for follow-up
            self.send_message(
                "LearningCoach",
                {"evaluation_summary": data.get("suggestions", []),
                 "weak_areas": data.get("weak_areas", [])},
                "evaluation_complete",
            )

        return data or {"error": "Failed to generate evaluation", "raw": result["content"]}
