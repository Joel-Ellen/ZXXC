# -*- coding: utf-8 -*-
"""
Centralized prompt registry for all LLM-driven agents.

This module keeps system prompts and user-prompt builders in one place so the
backend can evolve prompt strategy without scattering string templates across
many agent files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


_CHINESE_OUTPUT_CONTRACT = """
输出语言硬性要求：所有面向学习者的标题、说明、步骤、题目、选项、解析、提示、标签和追问必须使用简体中文。仅代码、公式、变量名、API 名称、标准缩写、符号和无法翻译的专有名称可保留原文。即使输入材料或学生提问使用英文，也不得输出整句或整段英文讲解。
""".strip()


def _to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class PromptDefinition:
    key: str
    system_prompt: str
    user_prompt_builder: Callable[..., str]

    def build_user_prompt(self, **kwargs: Any) -> str:
        return self.user_prompt_builder(**kwargs)


def _build_student_profile_extract(
    message: str,
    history: list,
    existing: dict,
) -> str:
    return f"""请从学生对话中抽取可直接用于前端展示和后续规划的学习画像更新。

任务目标：
1. 基于已有画像与最近对话，补充或修正学生画像。
2. 只提取有证据支持的信息，不要臆测。
3. 输出字段必须稳定，方便前端直接消费。

画像维度要求：
- academic_background: 专业/年级/课程背景
- foundation_level: 当前基础水平
- learning_goals: 学习目标与时间目标
- preferences: 内容偏好、节奏偏好、资源偏好
- cognitive_style: 更偏概念、例子、代码、图示还是练习
- pain_points: 当前卡点或易错点
- motivation: 兴趣方向与驱动力
- constraints: 时间、设备、语言、考试压力等限制

每个维度若有信息，必须输出：
- score: 0-1
- label: 简短标签
- description: 面向教师/系统的解释
- evidence: 来自对话的证据
- confidence: 0-1

已有画像：
{_to_json(existing or {})}

最近对话历史：
{_to_json(history[-6:] if history else [])}

学生最新消息：
{message}

请严格返回 JSON：
{{
  "profile_update": {{
    "academic_background": {{"score": 0, "label": "", "description": "", "evidence": "", "confidence": 0}},
    "foundation_level": {{"score": 0, "label": "", "description": "", "evidence": "", "confidence": 0}},
    "learning_goals": {{"score": 0, "label": "", "description": "", "evidence": "", "confidence": 0}},
    "preferences": {{"score": 0, "label": "", "description": "", "evidence": "", "confidence": 0}},
    "cognitive_style": {{"score": 0, "label": "", "description": "", "evidence": "", "confidence": 0}},
    "pain_points": {{"score": 0, "label": "", "description": "", "evidence": "", "confidence": 0}},
    "motivation": {{"score": 0, "label": "", "description": "", "evidence": "", "confidence": 0}},
    "constraints": {{"score": 0, "label": "", "description": "", "evidence": "", "confidence": 0}}
  }},
  "summary": "50-80字总结",
  "missing_info": ["仍需追问的信息"],
  "next_question": "下一句最自然的追问"
}}"""


def _build_student_profile_converse(
    message: str,
    existing: dict,
) -> str:
    return f"""你是一位自然、耐心的学习顾问。请根据当前画像缺口，给出下一轮最合适的对话回复。

要求：
1. 先对学生刚才的话做简短回应，语气自然。
2. 只追问一个最有信息增益的问题。
3. 问题要口语化，不能像表单。
4. 优先补全学习目标、基础水平、痛点、时间约束中最缺失的一项。

已有画像：
{_to_json(existing or {})}

学生最新消息：
{message}

请严格返回 JSON：
{{
  "response_message": "自然回复",
  "next_question": "下一句追问",
  "question_purpose": "本轮为什么问这个"
}}"""


def _build_knowledge_analysis(
    course_name: str,
    topic: str,
    student_profile: dict,
) -> str:
    return f"""请为课程生成适合后续路径规划和前端可视化的知识体系分析。

课程：{course_name}
聚焦主题：{topic or "全课程"}
学生画像参考：
{_to_json(student_profile or {})}

要求：
1. 输出树状知识结构，便于前端绘制知识图谱或导图。
2. 难度分层使用 L1-L5。
3. 明确前置依赖与建议学习顺序。
4. 估算学习时长时要偏教学落地，而不是百科式拆分。

请严格返回 JSON：
{{
  "course_name": "{course_name}",
  "knowledge_tree": {{
    "root": {{
      "name": "",
      "children": [
        {{"name": "", "children": []}}
      ]
    }}
  }},
  "levels": [
    {{"level": 1, "name": "L1-基础", "topics": []}}
  ],
  "prerequisites": {{
    "topic_a": ["topic_b"]
  }},
  "estimated_hours": 0
}}"""


def _build_learning_path(
    course_name: str,
    student_profile: dict,
    knowledge: dict,
) -> str:
    return f"""请根据学生画像和知识结构，为前端直接返回一份可展示的个性化学习路径。

课程：{course_name}
学生画像：
{_to_json(student_profile or {})}
知识结构：
{_to_json(knowledge or {})}

要求：
1. 路径必须按阶段推进，阶段内按周拆分。
2. 每周任务要可执行，不要空泛。
3. 资源建议要体现学生偏好，例如图示、代码、练习、讲解。
4. roadmap_mermaid 要能直接给前端渲染。

请严格返回 JSON：
{{
  "course_name": "{course_name}",
  "stages": [
    {{
      "stage": 1,
      "name": "阶段名称",
      "goals": ["目标1"],
      "weeks": [
        {{
          "week": 1,
          "title": "周标题",
          "tasks": ["任务1"],
          "resources": ["资源建议1"]
        }}
      ]
    }}
  ],
  "total_weeks": 0,
  "weekly_hours": 0,
  "roadmap_mermaid": "graph TD\\n  A[起点] --> B[阶段1]",
  "resource_strategy": {{
    "primary_modalities": [],
    "practice_ratio": "",
    "review_ratio": ""
  }}
}}"""


def _build_resource_prompt(
    resource_type: str,
    course_name: str,
    topic: str,
    difficulty: str,
    extra_requirements: Dict[str, Any],
) -> str:
    details = _to_json(extra_requirements or {})
    return f"""请生成教学资源，要求内容可直接供前端展示。

资源类型：{resource_type}
课程：{course_name}
主题：{topic}
难度：{difficulty}
补充要求：
{details}

输出要求：
1. 只返回合法 JSON。
2. 所有输出内容必须使用中文——包括字段值、标签和标识符。仅代码片段和 API 名称可保留原文。
3. 内容要实用、教学化、面向学习场景。
4. 不要省略关键字段；字段无内容时用空数组或空字符串。
5. 例子、任务和解释要围绕主题，不要模板化空话。
"""


def _build_resource_ppt(**kwargs: Any) -> str:
    base = _build_resource_prompt(
        resource_type="ppt",
        course_name=kwargs["course_name"],
        topic=kwargs["topic"],
        difficulty=kwargs["difficulty"],
        extra_requirements={
            "slide_count": kwargs.get("slide_count", 15),
            "style": kwargs.get("style", "visual"),
            "presentation_goal": "用于15-20分钟教学讲解",
        },
    )
    return base + """

请严格返回 JSON：
{
  "title": "",
  "slides": [
    {
      "slide_number": 1,
      "title": "",
      "content_markdown": "",
      "speaker_notes": ""
    }
  ],
  "full_markdown": ""
}"""


def _build_resource_quiz(**kwargs: Any) -> str:
    base = _build_resource_prompt(
        resource_type="quiz",
        course_name=kwargs["course_name"],
        topic=kwargs["topic"],
        difficulty=kwargs["difficulty"],
        extra_requirements={
            "question_count": kwargs.get("question_count", 10),
            "question_types": kwargs.get("question_types", ["choice", "true_false", "short_answer"]),
        },
    )
    return base + """

请严格返回 JSON（所有字段值使用中文）：
{
  "title": "",
  "questions": [
    {
      "id": 1,
      "type": "选择题",
      "question": "",
      "options": [],
      "answer": "",
      "explanation": "",
      "difficulty": "简单",
      "points": 0
    }
  ],
  "total_score": 0,
  "estimated_time_minutes": 0
}"""


def _build_resource_mindmap(**kwargs: Any) -> str:
    base = _build_resource_prompt(
        resource_type="mindmap",
        course_name=kwargs["course_name"],
        topic=kwargs["topic"],
        difficulty=kwargs["difficulty"],
        extra_requirements={
            "knowledge_structure": kwargs.get("knowledge_structure", {}),
            "render_target": "Mermaid + tree root for frontend viewer",
        },
    )
    return base + """

请严格返回 JSON：
{
  "title": "",
  "mermaid_code": "mindmap\\n  root((主题))",
  "root": {
    "id": "root",
    "label": "",
    "children": []
  },
  "key_concepts": []
}"""


def _build_resource_coding(**kwargs: Any) -> str:
    base = _build_resource_prompt(
        resource_type="coding",
        course_name=kwargs.get("course_name", ""),
        topic=kwargs["topic"],
        difficulty=kwargs["difficulty"],
        extra_requirements={
            "language": kwargs.get("language", "python"),
            "count": kwargs.get("count", 3),
        },
    )
    return base + """

请严格返回 JSON：
{
  "title": "",
  "exercises": [
    {
      "id": 1,
      "title": "",
      "description": "",
      "examples": [],
      "constraints": [],
      "solution": "",
      "test_cases": [],
      "complexity": "",
      "pitfalls": []
    }
  ],
  "overview_markdown": ""
}"""


def _build_resource_video(**kwargs: Any) -> str:
    base = _build_resource_prompt(
        resource_type="video",
        course_name=kwargs["course_name"],
        topic=kwargs["topic"],
        difficulty=kwargs["difficulty"],
        extra_requirements={
            "style": kwargs.get("style", "lecture"),
            "duration_minutes": kwargs.get("duration_minutes", 15),
        },
    )
    return base + """

请严格返回 JSON：
{
  "title": "",
  "segments": [
    {
      "id": 1,
      "time_range": "",
      "narration": "",
      "visual": "",
      "notes": ""
    }
  ],
  "total_duration": "",
  "overview_markdown": ""
}"""


def _build_tutor_prompt(
    mode: str,
    query: str,
    course_name: str,
    student_context: str,
    code_snippet: str = "",
    error_message: str = "",
) -> str:
    language_contract = """输出语言硬性要求：
1. 所有面向学生的解释、标题、标签、提示和问题必须使用简体中文。
2. 仅代码、变量名、API 名称和无法翻译的专有术语可保留英文。
3. 即使学生使用英文提问，也必须用中文回答。
4. 不得输出整段英文解释。

"""
    if mode == "concept":
        return language_contract + f"""请用“定义 -> 类比 -> 展开解释 -> 误区 -> 延伸问题”的方式讲清概念。

学生画像：{student_context}
课程：{course_name}
问题：{query}

请严格返回 JSON：
{{
  "text_explanation": "",
  "core_definition": "",
  "analogy": "",
  "detailed_explanation": "",
  "diagram": "",
  "code_example": "",
  "common_misconceptions": [],
  "extension_questions": [],
  "learning_tip": ""
}}"""

    if mode == "problem_solving":
        return language_contract + f"""请用苏格拉底式引导学生解题，不直接给最终答案。

学生画像：{student_context}
课程：{course_name}
问题：{query}

请严格返回 JSON：
{{
  "text_explanation": "",
  "hints": [],
  "solution_approach": "",
  "common_mistakes": [],
  "check_points": []
}}"""

    if mode == "code_debug":
        return language_contract + f"""请像结对编程导师一样分析错误，重点解释为什么错以及如何定位，而不是只给结果。

学生画像：{student_context}
问题：{query}
代码：
```python
{code_snippet}
```
错误信息：{error_message}

请严格返回 JSON：
{{
  "text_explanation": "",
  "error_analysis": "",
  "root_cause": "",
  "fix_guidance": "",
  "best_practices": [],
  "debugging_tips": []
}}"""

    if mode == "exam_prep":
        return language_contract + f"""请输出适合考试冲刺的复习建议，帮助学生快速聚焦重点。

学生画像：{student_context}
课程：{course_name}
问题：{query}

请严格返回 JSON：
{{
  "text_explanation": "",
  "key_topics": [],
  "review_strategy": "",
  "practice_questions": [],
  "common_exam_traps": [],
  "cheat_sheet": ""
}}"""

    return language_contract + f"""请回答学生问题，并尽量给出后续追问方向，帮助继续学习。

学生画像：{student_context}
课程：{course_name}
问题：{query}

请严格返回 JSON：
{{
  "text_explanation": "",
  "diagram": "",
  "code_example": "",
  "follow_up_questions": []
}}"""


def _build_assessment_report(
    radar: list,
    a_mix: float,
    strategy: str,
    course_name: str,
    study_time: float,
    completed_tasks: int,
) -> str:
    return f"""请基于学习指标生成结构化学习评估报告，供前端评价页直接展示。

课程：{course_name}
能力雷达：{_to_json(radar)}
综合指数 A_mix：{a_mix:.2f}
当前策略：{strategy}
学习时长：{study_time}
完成任务数：{completed_tasks}

要求：
1. strengths 和 weak_areas 需要适合卡片展示。
2. suggestions 需要包含优先级和预期收益。
3. 指标要尽量教学化，不要空泛总结。
4. 所有面向学习者的字段值必须使用简体中文，公式、标准缩写和专有名称除外。

请严格返回 JSON：
{{
  "metrics": {{
    "knowledge_mastery": 0,
    "engagement": 0,
    "efficiency": 0
  }},
  "current_level": "",
  "weak_areas": [],
  "strengths": [],
  "suggestions": [],
  "radar_data": {{
    "labels": ["概念理解力", "代码工程力", "逻辑推理力", "纠错韧性", "时间管理力"],
    "values": [0, 0, 0, 0, 0]
  }}
}}"""


PROMPT_REGISTRY: Dict[str, PromptDefinition] = {
    "student_profiler.extract": PromptDefinition(
        key="student_profiler.extract",
        system_prompt="""你是资深教育测评专家和学习顾问。
你的任务不是闲聊，而是从自然对话里稳健提取学生画像，为后续知识分析、路径规划和前端展示服务。
必须保持克制，只基于证据推断；不确定就降低置信度并放入 missing_info。
输出必须是稳定 JSON。""",
        user_prompt_builder=_build_student_profile_extract,
    ),
    "student_profiler.converse": PromptDefinition(
        key="student_profiler.converse",
        system_prompt="""你是自然、耐心、低压的学习顾问。
你的目标是通过最少的追问，收集对学习规划最有价值的信息。
回复要像真实顾问，不要像问卷。输出必须是 JSON。""",
        user_prompt_builder=_build_student_profile_converse,
    ),
    "knowledge_analysis.full": PromptDefinition(
        key="knowledge_analysis.full",
        system_prompt="""你是课程架构设计专家。
你需要把课程拆成可教学、可规划、可视化的知识结构，而不是百科条目。
必须输出稳定 JSON，并明确层级和依赖。""",
        user_prompt_builder=_build_knowledge_analysis,
    ),
    "resource_planner.path": PromptDefinition(
        key="resource_planner.path",
        system_prompt="""你是个性化学习路径规划师。
你需要综合学生画像与知识结构，输出可执行的学习路径，并让前端可以直接展示阶段、周计划和路线图。
必须输出稳定 JSON。""",
        user_prompt_builder=_build_learning_path,
    ),
    "resource_generation.ppt": PromptDefinition(
        key="resource_generation.ppt",
        system_prompt="""你是教学课件设计专家。
你擅长把知识点转成清晰、可讲授、可用于课堂或自学的 PPT/讲义内容。
输出必须是稳定 JSON。""",
        user_prompt_builder=_build_resource_ppt,
    ),
    "resource_generation.quiz": PromptDefinition(
        key="resource_generation.quiz",
        system_prompt="""你是教学测验设计专家。
你生成的题目要考理解、迁移和诊断，不要只考死记硬背。
所有输出内容必须使用中文——包括题目、选项、解析、标签等全部字段。
输出必须是稳定 JSON。""",
        user_prompt_builder=_build_resource_quiz,
    ),
    "resource_generation.mindmap": PromptDefinition(
        key="resource_generation.mindmap",
        system_prompt="""你是知识可视化设计师。
你需要把知识结构压缩成适合前端渲染的 Mermaid mindmap 和树结构。
输出必须是稳定 JSON。""",
        user_prompt_builder=_build_resource_mindmap,
    ),
    "resource_generation.coding": PromptDefinition(
        key="resource_generation.coding",
        system_prompt="""你是编程实战导师。
你设计的练习要兼顾题意、样例、测试、复杂度和易错点，适合学习者动手实践。
输出必须是稳定 JSON。""",
        user_prompt_builder=_build_resource_coding,
    ),
    "resource_generation.video": PromptDefinition(
        key="resource_generation.video",
        system_prompt="""你是教学视频脚本编导。
你需要输出可直接用于录课或动画分镜的教学脚本，兼顾讲解逻辑与镜头提示。
输出必须是稳定 JSON。""",
        user_prompt_builder=_build_resource_video,
    ),
    "tutor.mode": PromptDefinition(
        key="tutor.mode",
        system_prompt="""你是耐心、专业的 AI 学习导师。
你要根据不同辅导模式输出结构化结果，优先帮助学生理解、定位问题和继续思考，而不是简单给答案。
无论学生使用什么语言提问，所有面向学生的解释、标题、标签、提示和追问都必须使用简体中文。
只有代码、变量名、API 名称和无法翻译的专有术语可以保留英文；禁止输出整段英文解释。
输出必须是稳定 JSON。""",
        user_prompt_builder=_build_tutor_prompt,
    ),
    "assessment.report": PromptDefinition(
        key="assessment.report",
        system_prompt="""你是学习评估专家。
你需要把学习指标翻译成学生和教师都能理解的结构化报告，便于前端展示。
输出必须是稳定 JSON。""",
        user_prompt_builder=_build_assessment_report,
    ),
}


def get_prompt_definition(key: str) -> PromptDefinition:
    if key not in PROMPT_REGISTRY:
        raise KeyError(f"Prompt definition not found: {key}")
    return PROMPT_REGISTRY[key]


def get_system_prompt(key: str) -> str:
    definition = get_prompt_definition(key)
    return f"{definition.system_prompt.rstrip()}\n\n{_CHINESE_OUTPUT_CONTRACT}"


def build_user_prompt(key: str, **kwargs: Any) -> str:
    return get_prompt_definition(key).build_user_prompt(**kwargs)
