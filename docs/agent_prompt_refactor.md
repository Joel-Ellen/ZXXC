# Agent Prompt 与合并建议

本次整理的目标有三件事：

1. 把 prompt 从各个 agent 文件中抽离，统一收口到 `src/agents/prompt_registry.py`
2. 把功能重叠的资源生成 agent 合并为一个核心实现 `ResourceGenerationAgent`
3. 保留原来的 agent 类名，避免现有接口和前端调用被打断

## 当前 agent 结构

建议保留的核心 agent：

- `StudentProfilerAgent`
  - 职责：从对话中提取学生画像
  - 前端需要：`profile_update`、`summary`、`missing_info`、`next_question`
  - Prompt key：
    - `student_profiler.extract`
    - `student_profiler.converse`

- `KnowledgeAnalysisAgent`
  - 职责：课程知识树、难度层级、前置依赖分析
  - 前端需要：知识树、层级、依赖、预计时长
  - Prompt key：
    - `knowledge_analysis.full`

- `ResourcePlannerAgent`
  - 职责：根据画像和知识结构输出学习路径
  - 前端需要：`stages`、`total_weeks`、`weekly_hours`、`roadmap_mermaid`
  - Prompt key：
    - `resource_planner.path`

- `TutorAgentNode`
  - 职责：辅导答疑
  - 已经包含：
    - 概念讲解
    - 解题引导
    - 代码调试
    - 考前复习
    - 通用答疑
  - Prompt key：
    - `tutor.mode`

- `AssessmentReporterNode`
  - 职责：学习评估与报告
  - Prompt key：
    - `assessment.report`

## 重叠情况与合并结果

### 已经存在的合理合并

- `LearningCoachAgent` 已合并进 `TutorAgentNode`
- `EvaluationAgent` 已合并进 `AssessmentReporterNode`

这两个合并方向是正确的，建议继续保持。

### 本次继续合并的部分

以下 5 个 agent 存在明显功能重叠：

- `PPTGeneratorAgent`
- `QuestionGeneratorAgent`
- `MindMapGeneratorAgent`
- `CodingPracticeAgent`
- `VideoScriptAgent`

它们的共同点：

- 都是 “输入主题/课程/难度 -> 调 LLM -> 解析 JSON -> 返回结构化内容”
- 执行骨架一致
- 差异主要只在：
  - system prompt
  - user prompt 模板
  - 温度参数
  - 输出 schema

因此现在统一收敛为：

- 核心实现：`src/agents/resource_generation_agent.py`
- 兼容包装类：
  - `PPTGeneratorAgent`
  - `QuestionGeneratorAgent`
  - `MindMapGeneratorAgent`
  - `CodingPracticeAgent`
  - `VideoScriptAgent`

这样做的好处：

- prompt 统一管理
- 更容易扩展新的资源类型
- 减少 5 份几乎一致的重复代码
- 前端和接口层不需要大改

## Prompt 统一管理方式

统一入口：

- `src/agents/prompt_registry.py`

核心结构：

- `PromptDefinition`
  - `key`
  - `system_prompt`
  - `user_prompt_builder`

统一调用方式：

```python
from .prompt_registry import build_user_prompt, get_system_prompt

prompt = build_user_prompt("resource_generation.quiz", ...)
system_prompt = get_system_prompt("resource_generation.quiz")
```

这样后续如果你要：

- 调整语气
- 增加字段
- 统一 JSON schema
- 给不同资源增加约束

都只需要改一个地方。

## 建议的 agent 分层

建议后续把 agent 按 3 层理解：

### 1. 画像与规划层

- `StudentProfilerAgent`
- `KnowledgeAnalysisAgent`
- `ResourcePlannerAgent`

### 2. 资源生成层

- `ResourceGenerationAgent`
  - `ppt`
  - `quiz`
  - `mindmap`
  - `coding`
  - `video`

### 3. 交互与评估层

- `TutorAgentNode`
- `AssessmentReporterNode`

说明：

- 这两个文件本身历史包袱更重，存在编码噪音和大段合并痕迹。
- 本次没有强行重写主体文件，而是补了统一适配层：
  - `src/agents/prompt_adapters.py`
- 这样 `Tutor` 与 `Assessment` 的 prompt 也已经可以从统一 registry 获取，只是还没有把遗留文件整体清洗掉。

这样职责会比“每种资源一个独立 agent”更清晰。

## 前端返回内容注意点

目前前端最稳定依赖的是这些字段：

- Profile
  - `content_type`
  - `content_subtype`
  - `profile_update`
  - `summary_markdown`
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

- Markdown-like resources
  - `markdown`
  - `title`
  - `metadata`

所以后续新增资源类型时，建议优先走两种范式：

- 结构化渲染型：`mindmap / quiz / learning_path / tutoring / evaluation`
- Markdown 展示型：`ppt / coding / video / notes`

## 这次改动后的直接收益

- prompt 不再散落
- 资源类 agent 不再重复实现
- 路由创建 agent 时会统一注入默认 LLM
- `coding`、`video` 返回现在也有统一出口可走
- `Tutor / Assessment` 已有统一 prompt 适配落点，后续重构不会再无从下手

## 还建议你后续继续做的两步

1. 给 `TutorAgentNode` 和 `AssessmentReporterNode` 做一次彻底的编码清理
   - 这两个文件有历史合并痕迹和编码噪音
   - 逻辑还在，但维护成本偏高
   - 现在可以围绕 `prompt_adapters.py` 逐步替换，而不是一次性重写

2. 给 `prompt_registry.py` 再加一层 schema 常量
   - 现在已经统一了 prompt
   - 下一步可以把 JSON schema 也抽成常量
   - 这样 prompt、解析、前端类型可以完全对齐
