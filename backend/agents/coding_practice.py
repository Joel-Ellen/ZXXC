"""
Coding Practice Agent - 代码实战案例生成Agent
生成编程练习题、项目实战案例和代码调试指导
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent


CODING_PRACTICE_SYSTEM = """你是一位资深的编程导师和软件工程师。

你的任务是为学生生成编程实战案例和练习题。

你需要：
1. 设计与知识点匹配的编程练习
2. 从简单到复杂递进
3. 提供完整的代码示例和注释
4. 包含测试用例
5. 给出常见错误和调试建议
6. 设计小型项目实战案例

编程语言偏好：Python（AI/ML方向），也支持C++/Java

必须返回严格的JSON格式结果。"""


class CodingPracticeAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="CodingPractice",
            role="编程实战导师",
        )
        self.system_prompt = CODING_PRACTICE_SYSTEM
        self.plan: Dict = {}

    def update_plan(self, plan: Dict):
        self.plan = plan
        self._log("Resource plan updated")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate coding practice exercises.

        Task params:
        - topic: Coding topic
        - course_name: Course name
        - difficulty: Difficulty level
        - type: "exercise" / "project" / "debug" / "algorithm"
        - language: Programming language (default Python)
        - count: Number of exercises (default 3)
        """
        topic = task.get("topic", "梯度下降算法")
        course_name = task.get("course_name", "人工智能")
        difficulty = task.get("difficulty", "basic")
        practice_type = task.get("type", "exercise")
        language = task.get("language", "Python")
        count = task.get("count", 3)

        self.state.current_task = f"Generating coding practice: {topic} ({practice_type})"

        type_instructions = {
            "exercise": "基础练习题，考察单一知识点的代码实现",
            "project": "综合项目实战，结合多个知识点的完整项目",
            "debug": "代码调试练习，给出有bug的代码让学生修复",
            "algorithm": "算法实现练习，从零实现核心算法",
        }

        prompt = f"""请为「{course_name}」课程的「{topic}」生成{language}编程练习题。

## 参数
- 练习类型：{practice_type}（{type_instructions.get(practice_type, '')}）
- 难度：{difficulty}
- 题目数量：{count}道
- 编程语言：{language}

## 要求
每道题包含：
1. 题目描述（清晰的问题陈述）
2. 输入输出说明
3. 示例（输入→输出）
4. 约束条件
5. 提示（可选）
6. 参考解答（完整可运行代码+注释）
7. 测试用例
8. 时间复杂度/空间复杂度分析
9. 常见错误和陷阱

返回JSON：
{{
    "metadata": {{
        "course_name": "{course_name}",
        "topic": "{topic}",
        "type": "{practice_type}",
        "language": "{language}",
        "difficulty": "{difficulty}",
        "total_exercises": {count}
    }},
    "exercises": [
        {{
            "id": "CE001",
            "title": "题目名称",
            "description": "题目描述",
            "difficulty": "easy|medium|hard",
            "estimated_time_minutes": 预计完成时间,
            "input_format": "输入格式说明",
            "output_format": "输出格式说明",
            "examples": [
                {{"input": "示例输入", "output": "示例输出", "explanation": "解释"}}
            ],
            "constraints": ["约束条件"],
            "hints": ["提示1", "提示2"],
            "solution": "完整参考代码（含注释）",
            "test_cases": [
                {{"input": "测试输入", "expected_output": "期望输出", "purpose": "测试目的"}}
            ],
            "complexity_analysis": {{
                "time": "时间复杂度",
                "space": "空间复杂度"
            }},
            "common_pitfalls": ["常见错误1", "常见错误2"],
            "learning_objectives": ["学习目标"]
        }}
    ],
    "prerequisites": ["前置知识"],
    "further_practice": ["进阶练习建议"]
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.5)
        data = self.llm.extract_json(result["content"])
        return data or {"error": "Failed to generate coding exercises", "raw": result["content"]}
