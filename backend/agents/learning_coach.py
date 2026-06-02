"""
Learning Coach Agent - 学习指导Agent (Tutor Agent)
提供智能辅导：问答、错题解析、代码调试、学习建议
"""
import json
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent


LEARNING_COACH_SYSTEM = """你是一位耐心的AI学习导师（Tutor）。

你的核心职责是帮助学生理解和掌握知识，而非直接给出答案。

辅导原则：
1. **苏格拉底式引导**：先让学生表达理解，再针对性补充
2. **脚手架式教学**：提供适当的提示和支持，逐步撤除
3. **类比解释**：用生活化的类比解释抽象概念
4. **多角度讲解**：如果一个角度不理解，换一种方式
5. **鼓励试错**：引导学生从错误中学习

辅导方式：
- 文字讲解（清晰、结构化）
- 图解说明（Mermaid图表）
- 示例代码（可运行的Python代码）
- 纠错分析（指出错误+原因+正确做法）

禁止：
- 直接给出完整作业答案
- 忽视学生的困惑信号
- 使用过于学术化的语言而不解释

必须返回严格的JSON格式结果。"""


class LearningCoachAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="LearningCoach",
            role="AI学习导师",
        )
        self.system_prompt = LEARNING_COACH_SYSTEM
        self.student_profile: Dict = {}
        self.tutoring_history: List[Dict] = []

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Provide tutoring.

        Task params:
        - question: Student's question
        - context_type: "concept" / "problem_solving" / "code_debug" / "study_advice" / "exam_prep"
        - course_name: Course name
        - code_snippet: Code to debug (for code_debug)
        - error_message: Error encountered (for code_debug)
        - conversation_history: Previous tutoring messages
        """
        question = task.get("question", "")
        context_type = task.get("context_type", "concept")
        course_name = task.get("course_name", "人工智能")
        code_snippet = task.get("code_snippet", "")
        error_message = task.get("error_message", "")

        self.state.current_task = f"Tutoring: {context_type}"

        # Load student profile
        self.student_profile = self.read_shared_memory("student_profile", {})

        student_context = f"""## 学生画像
- 知识水平：{self.student_profile.get('knowledge_level', {}).get('label', '未知')}
- 学习偏好：{self.student_profile.get('learning_preference', {}).get('label', '未知')}
- 薄弱点：{self.student_profile.get('weak_points', {}).get('description', '未知')}
- 已掌握：{json.dumps(self.student_profile.get('mastered_knowledge', [])[:5], ensure_ascii=False)}
"""

        if context_type == "concept":
            return await self._explain_concept(question, course_name, student_context)
        elif context_type == "problem_solving":
            return await self._guide_problem_solving(question, course_name, student_context)
        elif context_type == "code_debug":
            return await self._debug_code(question, code_snippet, error_message, student_context)
        elif context_type == "study_advice":
            return await self._study_advice(question, course_name, student_context)
        elif context_type == "exam_prep":
            return await self._exam_preparation(question, course_name, student_context)
        else:
            return await self._general_tutoring(question, course_name, student_context)

    async def _explain_concept(
        self, question: str, course_name: str, student_context: str
    ) -> Dict[str, Any]:
        """Explain a concept in depth"""
        prompt = f"""请为学生讲解以下概念问题。

{student_context}

课程：{course_name}
学生问题：{question}

请提供：
1. 概念的核心定义（用通俗语言）
2. 一个生活化的类比/例子
3. 技术层面的深入解释
4. 图解（Mermaid代码）
5. 相关的代码示例（如适用）
6. 常见的理解误区
7. 2-3个延伸思考问题（引导学生进一步探索）

返回JSON：
{{
    "answer_type": "concept_explanation",
    "core_definition": "核心定义（1-2句话）",
    "analogy": "生活化类比",
    "detailed_explanation": "详细技术解释（Markdown格式）",
    "diagram": "Mermaid图表代码（如适用）",
    "code_example": "相关Python代码示例（如适用）",
    "common_misconceptions": ["常见误区"],
    "extension_questions": ["延伸思考问题"],
    "related_knowledge": ["关联知识点"],
    "learning_tip": "学习这个概念的技巧"
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        data = self.llm.extract_json(result["content"])
        return data or {"answer": result["content"]}

    async def _guide_problem_solving(
        self, question: str, course_name: str, student_context: str
    ) -> Dict[str, Any]:
        """Guide student through problem solving without giving direct answer"""
        prompt = f"""请引导学生解决以下问题。不要直接给出答案！

{student_context}

课程：{course_name}
学生问题：{question}

请分步骤引导：
1. 帮助学生理解问题（确认理解）
2. 提示相关知识点
3. 引导分解问题
4. 给出解题思路（但不给完整答案）
5. 如果学生做错了，分析错误原因

返回JSON：
{{
    "answer_type": "problem_solving_guidance",
    "problem_understanding": "帮助学生理解问题的引导语",
    "relevant_knowledge": ["相关知识点"],
    "hints": ["提示（由模糊到具体）"],
    "solution_approach": "解题思路框架（不给完整答案）",
    "common_mistakes": ["常见错误预警"],
    "check_points": ["自查要点"]
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.6)
        data = self.llm.extract_json(result["content"])
        return data or {"answer": result["content"]}

    async def _debug_code(
        self, question: str, code: str, error: str, student_context: str
    ) -> Dict[str, Any]:
        """Debug student's code"""
        prompt = f"""请帮助学生调试代码。

{student_context}

学生问题：{question}

代码：
```python
{code}
```

错误信息：{error if error else '学生未提供错误信息'}

请提供：
1. 错误原因分析
2. 修复方案（引导式的，不直接给修复后代码）
3. 如果学生代码逻辑有问题，指出逻辑错误
4. 代码改进建议
5. 相关的编程最佳实践

返回JSON：
{{
    "answer_type": "code_debug",
    "error_analysis": "错误分析",
    "root_cause": "根本原因（1句话）",
    "fix_guidance": "修复引导（分步提示）",
    "logic_issues": ["逻辑问题（如有）"],
    "best_practices": ["相关最佳实践"],
    "improved_code_snippet": "改进后的关键代码段（如适用）",
    "debugging_tips": ["调试技巧"],
    "prevention": "如何避免类似错误"
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.4)
        data = self.llm.extract_json(result["content"])
        return data or {"answer": result["content"]}

    async def _study_advice(
        self, question: str, course_name: str, student_context: str
    ) -> Dict[str, Any]:
        """Provide personalized study advice"""
        prompt = f"""请为学生提供个性化学习建议。

{student_context}

课程：{course_name}
学生问题：{question}

返回JSON：
{{
    "answer_type": "study_advice",
    "analysis": "对当前学习情况的分析",
    "advice": ["具体建议列表"],
    "resource_recommendations": ["推荐的学习资源"],
    "study_plan_adjustment": "学习计划调整建议",
    "motivation_tip": "鼓励和动力激发"
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        data = self.llm.extract_json(result["content"])
        return data or {"answer": result["content"]}

    async def _exam_preparation(
        self, question: str, course_name: str, student_context: str
    ) -> Dict[str, Any]:
        """Exam preparation guidance"""
        prompt = f"""请帮学生准备考试/测试。

{student_context}

课程：{course_name}
学生问题：{question}

返回JSON：
{{
    "answer_type": "exam_preparation",
    "key_topics": ["重点复习主题（带优先级）"],
    "review_strategy": "复习策略",
    "practice_questions": ["模拟考题建议"],
    "common_exam_traps": ["考试常见陷阱"],
    "time_management": "时间分配建议",
    "cheat_sheet": "精简的知识要点速记"
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.6)
        data = self.llm.extract_json(result["content"])
        return data or {"answer": result["content"]}

    async def _general_tutoring(
        self, question: str, course_name: str, student_context: str
    ) -> Dict[str, Any]:
        """General tutoring response"""
        prompt = f"""请回答学生的一般学习问题。

{student_context}

课程：{course_name}
学生问题：{question}

返回JSON：
{{
    "answer_type": "general_tutoring",
    "response": "回答内容（Markdown格式）",
    "diagram": "Mermaid图（如适用）",
    "code_example": "代码示例（如适用）",
    "follow_up_questions": ["可以追问的问题"],
    "references": ["参考资料"]
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.7)
        data = self.llm.extract_json(result["content"])
        return data or {"answer": result["content"]}
