# Agent Prompt 说明书

本文档基于当前实现整理：

- Prompt 注册中心：[src/agents/prompt_registry.py](/C:/Users/17873/Desktop/EduAgent/src/agents/prompt_registry.py)
- Prompt 适配层：[src/agents/prompt_adapters.py](/C:/Users/17873/Desktop/EduAgent/src/agents/prompt_adapters.py)
- 输出归一化：[src/routes/content_normalizer.py](/C:/Users/17873/Desktop/EduAgent/src/routes/content_normalizer.py)

目标是把每个 agent 的：

- Prompt key
- 适用 agent
- 输入字段
- 输出 schema
- 前端消费字段
- 推荐调参

统一列清楚。

**总览**
当前建议的 agent 分层如下：

1. 画像与规划层
2. 资源生成层
3. 交互与评估层

资源生成层已经完成核心合并：

- 核心实现：`ResourceGenerationAgent`
- 兼容类名：
  - `PPTGeneratorAgent`
  - `QuestionGeneratorAgent`
  - `MindMapGeneratorAgent`
  - `CodingPracticeAgent`
  - `VideoScriptAgent`

交互与评估层已经完成 prompt 接管：

- `TutorAgentNode`
- `AssessmentReporterNode`

它们现在通过 `prompt_adapters.py` 使用统一 prompt。

**Prompt Map**
当前 prompt key 列表：

- `student_profiler.extract`
- `student_profiler.converse`
- `knowledge_analysis.full`
- `resource_planner.path`
- `resource_generation.ppt`
- `resource_generation.quiz`
- `resource_generation.mindmap`
- `resource_generation.coding`
- `resource_generation.video`
- `tutor.mode`
- `assessment.report`

**1. StudentProfiler**
适用 agent：

- `StudentProfilerAgent`

Prompt key：

- `student_profiler.extract`
- `student_profiler.converse`

职责：

- 从自然对话中抽取学生画像
- 生成下一轮最自然、最有信息增益的追问

输入字段：

- `message`
- `conversation_history`
- `existing_profile`
- `mode`

`extract` 输出 schema：

```json
{
  "profile_update": {
    "academic_background": {
      "score": 0,
      "label": "",
      "description": "",
      "evidence": "",
      "confidence": 0
    }
  },
  "summary": "",
  "missing_info": [],
  "next_question": ""
}
```

`converse` 输出 schema：

```json
{
  "response_message": "",
  "next_question": "",
  "question_purpose": ""
}
```

前端消费字段：

- `content_type`
- `content_subtype`
- `profile_update`
- `summary_markdown`
- `missing_info`
- `next_question`

推荐调参：

- `json_mode=True`
- 温度建议：`0.3 - 0.5`
- 适合偏低温，避免画像发散

维护建议：

- 如果你后面要增加画像维度，优先改 `prompt_registry.py`
- 同时同步前端 `profile_update` 展示组件

**2. KnowledgeAnalysis**
适用 agent：

- `KnowledgeAnalysisAgent`

Prompt key：

- `knowledge_analysis.full`

职责：

- 输出课程知识树
- 输出难度层级
- 输出前置依赖
- 输出估计学习时长

输入字段：

- `course_name`
- `topic`
- `student_profile`

输出 schema：

```json
{
  "course_name": "",
  "knowledge_tree": {
    "root": {
      "name": "",
      "children": []
    }
  },
  "levels": [
    {
      "level": 1,
      "name": "L1-基础",
      "topics": []
    }
  ],
  "prerequisites": {},
  "estimated_hours": 0
}
```

前端消费情况：

- 当前主要服务于后续路径规划
- 也适合后续扩展知识图谱可视化

推荐调参：

- `json_mode=True`
- 温度建议：`0.4 - 0.5`

**3. ResourcePlanner**
适用 agent：

- `ResourcePlannerAgent`

Prompt key：

- `resource_planner.path`

职责：

- 根据学生画像和知识结构生成个性化学习路径

输入字段：

- `course_name`
- `student_profile`
- `knowledge`

输出 schema：

```json
{
  "course_name": "",
  "stages": [
    {
      "stage": 1,
      "name": "",
      "goals": [],
      "weeks": [
        {
          "week": 1,
          "title": "",
          "tasks": [],
          "resources": []
        }
      ]
    }
  ],
  "total_weeks": 0,
  "weekly_hours": 0,
  "roadmap_mermaid": "",
  "resource_strategy": {
    "primary_modalities": [],
    "practice_ratio": "",
    "review_ratio": ""
  }
}
```

前端消费字段：

- `stages`
- `total_weeks`
- `weekly_hours`
- `roadmap_mermaid`
- `course_name`

推荐调参：

- `json_mode=True`
- 温度建议：`0.4 - 0.5`

**4. ResourceGeneration.ppt**
适用 agent：

- `PPTGeneratorAgent`
- `lecture_note`
- `study_note`

Prompt key：

- `resource_generation.ppt`

输入字段：

- `course_name`
- `topic`
- `difficulty`
- `slide_count`
- `style`

输出 schema：

```json
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
}
```

前端消费字段：

- 经过 normalizer 后主要消费：
  - `markdown`
  - `title`
  - `metadata`

推荐调参：

- 温度建议：`0.6 - 0.7`
- 如果要更稳定，可降到 `0.5`

**5. ResourceGeneration.quiz**
适用 agent：

- `QuestionGeneratorAgent`
- `exercise`

Prompt key：

- `resource_generation.quiz`

输入字段：

- `course_name`
- `topic`
- `difficulty`
- `question_count`
- `question_types`

输出 schema：

```json
{
  "title": "",
  "questions": [
    {
      "id": 1,
      "type": "choice",
      "question": "",
      "options": [],
      "answer": "",
      "explanation": "",
      "difficulty": "",
      "points": 0
    }
  ],
  "total_score": 0,
  "estimated_time_minutes": 0
}
```

前端消费字段：

- `questions`
- `total_score`
- `estimated_time_minutes`
- `title`

推荐调参：

- 温度建议：`0.5 - 0.6`

**6. ResourceGeneration.mindmap**
适用 agent：

- `MindMapGeneratorAgent`

Prompt key：

- `resource_generation.mindmap`

输入字段：

- `course_name`
- `topic`
- `difficulty`
- `knowledge_structure`

输出 schema：

```json
{
  "title": "",
  "mermaid_code": "mindmap\n  root((主题))",
  "root": {
    "id": "root",
    "label": "",
    "children": []
  },
  "key_concepts": []
}
```

前端消费字段：

- `mermaid_code`
- `root`
- `key_concepts`
- `title`

推荐调参：

- 温度建议：`0.4 - 0.5`

**7. ResourceGeneration.coding**
适用 agent：

- `CodingPracticeAgent`
- `project`

Prompt key：

- `resource_generation.coding`

输入字段：

- `topic`
- `difficulty`
- `language`
- `count`
- `course_name`

输出 schema：

```json
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
}
```

前端消费字段：

- 经过 normalizer 后主要消费：
  - `markdown`
  - `title`
  - `metadata.exercises`

推荐调参：

- 温度建议：`0.3 - 0.4`
- 代码题更适合低温

**8. ResourceGeneration.video**
适用 agent：

- `VideoScriptAgent`
- `video_script`
- `animation_script`

Prompt key：

- `resource_generation.video`

输入字段：

- `course_name`
- `topic`
- `difficulty`
- `style`
- `duration_minutes`

输出 schema：

```json
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
}
```

前端消费字段：

- 经过 normalizer 后主要消费：
  - `markdown`
  - `title`
  - `metadata.segments`
  - `metadata.total_duration`

推荐调参：

- 温度建议：`0.6 - 0.7`

**9. Tutor**
适用 agent：

- `TutorAgentNode`

Prompt key：

- `tutor.mode`

职责：

- 概念讲解
- 解题引导
- 代码调试
- 考试冲刺
- 通用答疑

输入字段：

- `mode`
- `query`
- `course_name`
- `student_context`
- `code_snippet`
- `error_message`

按模式输出 schema：

- `concept`

```json
{
  "core_definition": "",
  "analogy": "",
  "detailed_explanation": "",
  "diagram": "",
  "code_example": "",
  "common_misconceptions": [],
  "extension_questions": [],
  "learning_tip": ""
}
```

- `problem_solving`

```json
{
  "hints": [],
  "solution_approach": "",
  "common_mistakes": [],
  "check_points": []
}
```

- `code_debug`

```json
{
  "error_analysis": "",
  "root_cause": "",
  "fix_guidance": "",
  "best_practices": [],
  "debugging_tips": []
}
```

- `exam_prep`

```json
{
  "key_topics": [],
  "review_strategy": "",
  "practice_questions": [],
  "common_exam_traps": [],
  "cheat_sheet": ""
}
```

- `general`

```json
{
  "response": "",
  "diagram": "",
  "code_example": "",
  "follow_up_questions": []
}
```

前端消费字段：

- `answer_type`
- `core_definition`
- `analogy`
- `markdown_body`
- `diagram`
- `code_example`
- `hints`
- `common_mistakes`
- `extension_questions`

推荐调参：

- `concept`: `0.7`
- `problem_solving`: `0.6`
- `code_debug`: `0.4`
- `exam_prep`: `0.6`
- `general`: `0.7`

实现说明：

- 现在 `TutorAgentNode` 已经清洗成干净版
- 具体 prompt 接管走 `prompt_adapters.py`

**10. Assessment**
适用 agent：

- `AssessmentReporterNode`

Prompt key：

- `assessment.report`

职责：

- 基于雷达能力和学习表现输出评估报告
- 与算法评估结果结合

输入字段：

- `radar`
- `a_mix`
- `strategy`
- `course_name`
- `study_time`
- `completed_tasks`

输出 schema：

```json
{
  "metrics": {
    "knowledge_mastery": 0,
    "engagement": 0,
    "efficiency": 0
  },
  "current_level": "",
  "weak_areas": [],
  "strengths": [],
  "suggestions": [],
  "radar_data": {
    "labels": ["概念理解力", "代码工程力", "逻辑推理力", "纠错韧性", "时间管理力"],
    "values": [0, 0, 0, 0, 0]
  }
}
```

前端消费字段：

- `metrics`
- `current_level`
- `weak_areas`
- `strengths`
- `suggestions`
- `radar_data`
- `report_markdown`

推荐调参：

- 温度建议：`0.4 - 0.5`
- 评估报告应偏稳，不建议高温

实现说明：

- 算法评估主体保留在 `AssessmentReporterNode`
- LLM 报告统一由 `prompt_adapters.py` 接入

**前端字段总对照**
目前前端最稳定依赖的字段如下：

- Profile
  - `profile_update`
  - `summary_markdown`
  - `missing_info`
  - `next_question`

- Learning Path
  - `stages`
  - `total_weeks`
  - `weekly_hours`
  - `roadmap_mermaid`

- Mindmap
  - `mermaid_code`
  - `root`
  - `key_concepts`

- Quiz
  - `questions`
  - `total_score`
  - `estimated_time_minutes`

- Markdown resources
  - `markdown`
  - `title`
  - `metadata`

- Tutoring
  - `markdown_body`
  - `core_definition`
  - `analogy`
  - `diagram`
  - `code_example`
  - `hints`

- Evaluation
  - `metrics`
  - `weak_areas`
  - `strengths`
  - `suggestions`
  - `radar_data`
  - `report_markdown`

**后续建议**

1. 下一步最值得做的是把 `prompt_registry.py` 里的“输出 schema”抽成常量。
2. 然后让 agent 解析逻辑和前端类型都共用这一份 schema 概念。
3. 如果后续要做 A/B prompt 实验，建议在 `PromptDefinition` 上增加 `version` 和 `tags` 字段。
