"""
AI Learning Assistant - Pydantic Schemas (Request/Response Models)
多智能体学习系统 - 数据验证模型
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
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
