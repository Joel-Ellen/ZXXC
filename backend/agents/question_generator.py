"""
Question Generator Agent - 题库生成Agent
生成个性化习题：选择题、判断题、简答题、编程题
"""
import json
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent


QUESTION_GENERATOR_SYSTEM = """你是一位资深的教育测评专家和题库设计师。

你的任务是根据知识点和难度要求，生成高质量的习题。

题型包括：
1. 选择题（4个选项，含干扰项设计）
2. 判断题（明确的正误判断+解析）
3. 简答题（开放性问题+评分要点）
4. 编程题（含测试用例和参考解答）

出题原则：
- 考察理解而非记忆
- 干扰项要有迷惑性但有明确错误原因
- 难度递进：基础→应用→分析
- 每道题都要有详细解析
- 适配学生当前水平

必须返回严格的JSON格式结果。"""


class QuestionGeneratorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="QuestionGenerator",
            role="题库生成专家",
        )
        self.system_prompt = QUESTION_GENERATOR_SYSTEM
        self.plan: Dict = {}
        self.student_weak_points: List = []

    def update_plan(self, plan: Dict):
        self.plan = plan
        # Extract weak points from shared memory
        profile = self.read_shared_memory("student_profile", {})
        weak = profile.get("weak_points", {})
        self.student_weak_points = weak.get("description", "").split("，") if weak else []
        self._log(f"Plan received, weak points: {self.student_weak_points}")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate quiz questions.

        Task params:
        - course_name: Course name
        - knowledge_point: Target knowledge point
        - question_count: Number of questions (default 5)
        - question_types: List of types ["choice", "true_false", "short_answer", "coding"]
        - difficulty: Difficulty level
        - focus_weak_points: Whether to emphasize student's weak areas
        """
        course_name = task.get("course_name", "人工智能")
        knowledge_point = task.get("knowledge_point", "机器学习基础")
        question_count = task.get("question_count", 10)
        question_types = task.get("question_types", ["choice", "true_false", "short_answer"])
        difficulty = task.get("difficulty", "basic")
        focus_weak = task.get("focus_weak_points", True)

        self.state.current_task = f"Generating questions: {knowledge_point}"

        weak_focus_str = ""
        if focus_weak and self.student_weak_points:
            weak_focus_str = f"\n## 学生薄弱点（重点出题方向）\n{json.dumps(self.student_weak_points, ensure_ascii=False)}"

        prompt = f"""请为「{course_name}」课程的「{knowledge_point}」知识点生成习题。

## 参数
- 题目总数：{question_count}道
- 题型分布：{json.dumps(question_types, ensure_ascii=False)}
- 难度：{difficulty}
- 每个题型按难度分布：40%基础题 + 40%应用提高 + 20%挑战题
{weak_focus_str}

## 出题要求
1. 选择题：4个选项（A/B/C/D），设计有迷惑性的干扰项
2. 判断题：明确的正误判断，附带详细解析
3. 简答题：考察理解和应用，附带评分要点
4. 编程题：给出题目描述、输入输出示例、测试用例、参考解答

返回JSON：
{{
    "quiz_metadata": {{
        "course_name": "{course_name}",
        "knowledge_point": "{knowledge_point}",
        "total_questions": {question_count},
        "difficulty": "{difficulty}",
        "total_score": 总分,
        "estimated_time_minutes": 预计完成时间（分钟）
    }},
    "questions": [
        {{
            "id": "Q001",
            "type": "choice|true_false|short_answer|coding",
            "difficulty": "basic|intermediate|advanced",
            "points": 分值,
            "question": "题目内容",
            "options": ["A. ...", "B. ...", "C. ...", "D. ..."],  // 仅选择题
            "correct_answer": "正确答案（选择题用A/B/C/D，判断用true/false，简答用要点列表，编程用代码）",
            "explanation": "详细解析",
            "knowledge_tested": ["考察的知识点"],
            "common_mistakes": ["常见错误"],
            "hints": ["提示"]
        }}
    ]
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        data = self.llm.extract_json(result["content"])

        # Store quiz in shared memory for evaluation
        if data:
            self.update_shared_memory(f"quiz_{knowledge_point}", data)

        return data or {"error": "Failed to generate questions", "raw": result["content"]}
