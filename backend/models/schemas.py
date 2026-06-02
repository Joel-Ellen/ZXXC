"""
AI Learning Assistant - Pydantic Schemas (Request/Response Models)
多智能体学习系统 - 数据验证模型
"""
from __future__ import annotations
from pydantic import BaseModel, Field, validator, model_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum


# ============================================================
# Auth Schemas
# ============================================================
class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    email: str = Field(..., max_length=100)
    password: str = Field(..., min_length=6, max_length=100)

class UserLogin(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    avatar_url: Optional[str] = None
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ============================================================
# Profile Schemas (Conversational Profile Building)
# ============================================================
class ProfileInitRequest(BaseModel):
    """Initial profile building via conversation"""
    message: str = Field(..., description="User's natural language input")

class ProfileDimension(BaseModel):
    """Single profile dimension"""
    score: float = Field(..., ge=0, le=100)
    label: str
    description: str
    evidence: List[str] = Field(default_factory=list)

class StudentProfileResponse(BaseModel):
    """Complete student profile"""
    id: str
    user_id: str
    major: Optional[str] = None
    grade: Optional[str] = None
    university: Optional[str] = None
    learning_goal: Optional[str] = None
    learning_habits: Optional[Dict] = None
    weekly_study_hours: Optional[int] = None

    # 10 dimensions
    major_background: Optional[ProfileDimension] = None
    knowledge_level: Optional[ProfileDimension] = None
    learning_ability: Optional[ProfileDimension] = None
    learning_preference: Optional[ProfileDimension] = None
    cognitive_style: Optional[ProfileDimension] = None
    weak_points: Optional[ProfileDimension] = None
    interest_direction: Optional[ProfileDimension] = None
    career_goal: Optional[ProfileDimension] = None

    mastered_knowledge: Optional[List[str]] = None
    profile_version: int = 1
    confidence_score: Optional[float] = None
    last_updated: datetime
    created_at: datetime

class ProfileUpdateRequest(BaseModel):
    """Update profile with new information"""
    message: str
    context: Optional[Dict[str, Any]] = None


# ============================================================
# Learning Path Schemas
# ============================================================
class LearningPathRequest(BaseModel):
    """Request to generate learning path"""
    course_name: str = Field(default="人工智能")
    target_level: str = Field(default="advanced")
    weekly_hours: int = Field(default=10, ge=1, le=40)
    duration_weeks: int = Field(default=16, ge=4, le=52)

class StageInfo(BaseModel):
    stage: str
    weeks: str
    topics: List[str]
    resources: List[Dict[str, str]]
    milestones: List[str]

class LearningPathResponse(BaseModel):
    id: str
    course_name: str
    current_stage: str
    total_weeks: int
    completed_weeks: int
    stages: List[StageInfo]
    roadmap_mermaid: Optional[str] = None
    created_at: datetime


# ============================================================
# Resource Generation Schemas
# ============================================================
class ResourceGenerateRequest(BaseModel):
    """Request to generate a learning resource"""
    resource_type: str = Field(..., description="lecture_note/ppt/mindmap/exercise/project/study_note/video_script")
    course_name: str = Field(default="人工智能")
    topic: str = Field(..., description="Knowledge topic to cover")
    difficulty: str = Field(default="basic")
    knowledge_points: List[str] = Field(default_factory=list)
    style_preference: Optional[str] = None  # e.g., "visual", "code-heavy", "theory"

class ResourceResponse(BaseModel):
    id: str
    resource_type: str
    title: str
    course_name: str
    content: Optional[str] = None
    difficulty: str
    knowledge_points: List[str] = []
    metadata: Optional[Dict] = None
    agent_generated: Optional[str] = None
    quality_score: Optional[float] = None
    created_at: datetime


# ============================================================
# Quiz & Exercise Schemas
# ============================================================
class QuizQuestion(BaseModel):
    id: str
    type: str  # choice / true_false / short_answer / coding
    question: str
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    difficulty: str = "basic"
    points: float = 10.0

class QuizGenerateRequest(BaseModel):
    course_name: str = Field(default="人工智能")
    knowledge_point: str
    question_count: int = Field(default=5, ge=1, le=50)
    question_types: List[str] = Field(default=["choice", "true_false", "short_answer"])

class QuizSubmitRequest(BaseModel):
    quiz_id: str
    answers: Dict[str, str]  # question_id -> answer

class QuizResultResponse(BaseModel):
    quiz_id: str
    score: float
    total_score: float
    correct_count: int
    total_count: int
    time_spent: Optional[int] = None
    feedback: List[Dict[str, Any]]  # Per-question feedback
    weak_points: List[str]
    suggestions: List[str]


# ============================================================
# Tutoring Schemas
# ============================================================
class TutoringRequest(BaseModel):
    """Request tutoring help"""
    question: str
    context_type: str = Field(default="general")  # general / code_debug / concept / problem_solving
    course_name: Optional[str] = None
    code_snippet: Optional[str] = None
    error_message: Optional[str] = None

class TutoringResponse(BaseModel):
    answer: str
    explanation: Optional[str] = None
    code_example: Optional[str] = None
    diagram: Optional[str] = None  # Mermaid diagram
    references: List[Dict[str, str]] = []
    related_knowledge: List[str] = []


# ============================================================
# Evaluation Schemas
# ============================================================
class EvaluationRequest(BaseModel):
    course_name: str = Field(default="人工智能")
    period_days: int = Field(default=30, ge=1, le=365)

class EvaluationMetrics(BaseModel):
    study_hours: float
    tasks_completed: int
    total_tasks: int
    quiz_avg_score: float
    error_rate: float
    resources_used: int
    knowledge_coverage: float  # percentage

class EvaluationReportResponse(BaseModel):
    id: str
    course_name: str
    period_start: datetime
    period_end: datetime
    metrics: EvaluationMetrics
    current_level: str
    weak_areas: List[Dict[str, Any]]
    strengths: List[Dict[str, Any]]
    suggestions: List[str]
    next_plan: Dict[str, Any]
    report_content: Optional[str] = None
    created_at: datetime


# ============================================================
# Agent Status Schemas (for UI display)
# ============================================================
class AgentStatus(BaseModel):
    agent_name: str
    status: str  # idle / working / completed / error
    current_task: Optional[str] = None
    progress: float = 0.0  # 0-100
    last_active: Optional[datetime] = None

class MultiAgentStatus(BaseModel):
    agents: List[AgentStatus]
    orchestrator_status: str
    active_agents_count: int
    queue_length: int


# ============================================================
# Chat / Conversation Schemas
# ============================================================
class ChatMessage(BaseModel):
    role: str  # user / assistant / system
    content: str
    message_type: str = "text"  # text / resource / quiz / system

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    session_id: str
    message: ChatMessage
    profile_updates: Optional[Dict[str, Any]] = None
    resources: List[ResourceResponse] = []
    agent_activity: List[AgentStatus] = []


# ============================================================
# Generic API Response
# ============================================================
class APIResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[Any] = None
    error: Optional[str] = None


# ============================================================
# Standardized Output Format Schemas
# 统一输出格式：Markdown（文本型）vs Structured（结构型）
# 前端根据 content_type 字段决定渲染策略：
#   - "markdown"   → 直接用 Markdown 渲染器（marked / markdown-it）
#   - "structured" → 根据 content_subtype 使用专用组件渲染
# ============================================================

class ContentFormat(str, Enum):
    """内容格式分类"""
    MARKDOWN = "markdown"
    STRUCTURED = "structured"


# ----------------------------------------------------------
# Format A: Markdown Content（文本型 — 报告/笔记/讲义/脚本）
# ----------------------------------------------------------
class MarkdownContent(BaseModel):
    """
    标准 Markdown 输出格式。
    适用于：lecture_note, ppt, study_note, video_script,
           tutoring concept_explanation, evaluation report
    """
    content_type: str = Field(default="markdown", description="固定值 'markdown'，前端路由渲染器")
    markdown: str = Field(
        ...,
        description="GitHub-flavored Markdown 字符串，包含严格的 #标题、-列表、```代码块 等标准语法"
    )
    title: Optional[str] = Field(default=None, description="内容标题")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="附属元数据（作者/日期/标签等）")


# ----------------------------------------------------------
# Format B: Structured Content（结构型 — 路径/导图/题库）
# ----------------------------------------------------------

# B1. 思维导图结构化节点
class MindMapNode(BaseModel):
    """思维导图递归节点"""
    id: str = Field(..., description="节点唯一ID")
    label: str = Field(..., description="节点显示文本")
    children: List[MindMapNode] = Field(default_factory=list, description="子节点列表")

class StructuredMindMap(BaseModel):
    """
    结构化思维导图。
    前端可同时使用 mermaid_code（文本渲染）和 root（自定义组件渲染）。
    """
    content_type: str = Field(default="structured")
    content_subtype: str = Field(default="mindmap")
    title: str = Field(..., description="导图标题")
    topic: str = Field(..., description="中心主题")
    mermaid_code: str = Field(..., description="Mermaid mindmap 源码")
    root: Optional[MindMapNode] = Field(default=None, description="递归节点树（前端可用 D3/tree 组件渲染）")
    key_concepts: List[str] = Field(default_factory=list)
    total_nodes: int = Field(default=0)
    max_depth: int = Field(default=3)
    usage_tips: Optional[str] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None)


# B2. 题库结构化模型
class TypedQuestion(BaseModel):
    """单道习题（强类型）"""
    id: str = Field(..., description="题号，如 Q001")
    type: str = Field(..., description="choice | true_false | short_answer | coding")
    difficulty: str = Field(default="basic", description="basic | intermediate | advanced")
    points: float = Field(default=10.0)
    question_text: str = Field(..., description="题目正文")
    options: Optional[List[str]] = Field(default=None, description="选项列表（仅选择题）")
    correct_answer: Optional[str] = Field(default=None, description="正确答案")
    explanation: Optional[str] = Field(default=None, description="题目解析（Markdown）")
    knowledge_tested: List[str] = Field(default_factory=list)
    hints: List[str] = Field(default_factory=list)

class StructuredQuiz(BaseModel):
    """
    结构化题库。
    前端按题目逐一渲染答题卡片，支持作答/批改交互。
    """
    content_type: str = Field(default="structured")
    content_subtype: str = Field(default="quiz")
    title: str = Field(..., description="题库标题")
    course_name: str = Field(default="")
    knowledge_point: str = Field(default="")
    total_questions: int = Field(default=0)
    total_score: float = Field(default=100.0)
    estimated_time_minutes: int = Field(default=30)
    difficulty: str = Field(default="basic")
    questions: List[TypedQuestion] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default=None)


# B3. 学习路径结构化模型
class TypedWeeklyPlan(BaseModel):
    week: int
    focus: str = ""
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    milestone: Optional[str] = None

class TypedStage(BaseModel):
    stage_id: int
    stage_name: str = ""
    weeks: str = ""
    description: str = ""
    goals: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    weekly_plan: List[TypedWeeklyPlan] = Field(default_factory=list)
    assessment: Optional[str] = None

class StructuredLearningPath(BaseModel):
    """
    结构化学习路径。
    前端可按阶段折叠面板 + 周计划甘特图渲染。
    """
    content_type: str = Field(default="structured")
    content_subtype: str = Field(default="learning_path")
    course_name: str = Field(..., description="课程名称")
    total_weeks: int = Field(default=16)
    target_level: str = Field(default="advanced")
    overview_markdown: str = Field(
        default="",
        description="学习路径总览（Markdown格式，供顶部渲染）"
    )
    stages: List[TypedStage] = Field(default_factory=list)
    roadmap_mermaid: Optional[str] = Field(default=None, description="Mermaid 路线图代码")
    personalized_tips: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default=None)


# B4. 辅导回答结构化模型（已有 TutoringResponse，补充Markdown回退）
class TutoringStructuredResponse(BaseModel):
    """
    智能辅导标准输出。
    answer_type 决定前端使用哪种展示模板。
    """
    content_type: str = Field(default="structured")
    content_subtype: str = Field(default="tutoring")
    answer_type: str = Field(
        default="general_tutoring",
        description="concept_explanation | problem_solving_guidance | code_debug | study_advice | exam_preparation | general_tutoring"
    )
    markdown_body: str = Field(
        default="",
        description="所有人可读的 Markdown 正文（每个 answer_type 都生成此字段）"
    )
    # 类型特有字段（仅当 answer_type 匹配时填充）
    diagram: Optional[str] = Field(default=None, description="Mermaid 图代码")
    code_example: Optional[str] = Field(default=None, description="代码示例")
    hints: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)
    extension_questions: List[str] = Field(default_factory=list)
    references: List[Dict[str, str]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default=None)
