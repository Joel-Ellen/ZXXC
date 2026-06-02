"""
AI Learning Assistant - Database Models
多智能体学习系统 - 数据库模型

Tables:
- User: 用户账号
- StudentProfile: 学生学习画像（动态更新）
- LearningPath: 学习路径规划
- LearningTask: 学习任务
- GeneratedResource: 生成的资源记录
- ConversationHistory: 对话历史
- QuizRecord: 测验记录
- EvaluationReport: 评估报告
- KnowledgePoint: 知识点库
- AgentTaskLog: Agent任务日志
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, JSON, Enum as SAEnum, create_engine
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, create_async_engine, async_sessionmaker
from config import DATABASE_CONFIG
import enum


class Base(AsyncAttrs, DeclarativeBase):
    pass


# ============================================================
# Enums
# ============================================================
class ResourceType(str, enum.Enum):
    LECTURE_NOTE = "lecture_note"       # 课程讲义
    PPT = "ppt"                          # PPT课件
    MINDMAP = "mindmap"                  # 思维导图
    EXERCISE = "exercise"                # 习题
    PROJECT = "project"                  # 项目实战
    STUDY_NOTE = "study_note"            # 学习笔记
    VIDEO_SCRIPT = "video_script"        # 视频脚本
    ANIMATION_SCRIPT = "animation_script" # 动画脚本


class DifficultyLevel(str, enum.Enum):
    BEGINNER = "beginner"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class LearningStage(str, enum.Enum):
    STAGE_1_BASICS = "基础知识"
    STAGE_2_CORE = "核心知识"
    STAGE_3_INTEGRATED = "综合应用"
    STAGE_4_PROJECT = "项目实践"
    STAGE_5_ADVANCED = "能力提升"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================
# User & Profile Models
# ============================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    profile: Mapped[Optional["StudentProfile"]] = relationship(back_populates="user", uselist=False)
    learning_paths: Mapped[List["LearningPath"]] = relationship(back_populates="user")
    resources: Mapped[List["GeneratedResource"]] = relationship(back_populates="user")
    conversations: Mapped[List["ConversationHistory"]] = relationship(back_populates="user")
    quiz_records: Mapped[List["QuizRecord"]] = relationship(back_populates="user")
    evaluation_reports: Mapped[List["EvaluationReport"]] = relationship(back_populates="user")


class StudentProfile(Base):
    """Dynamic Student Learning Profile - 动态学习画像"""
    __tablename__ = "student_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False)

    # 基础信息
    major: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    university: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 学习目标与习惯
    learning_goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    learning_habits: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    weekly_study_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 画像维度（核心10维）
    major_background: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)        # 专业背景
    knowledge_level: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)         # 知识基础水平
    learning_ability: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)        # 学习能力
    learning_preference: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)     # 学习偏好
    cognitive_style: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)         # 认知风格
    weak_points: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)             # 易错知识点
    interest_direction: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)      # 兴趣方向
    career_goal: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)             # 职业目标

    # 已掌握知识
    mastered_knowledge: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    # 学习历史
    learning_history: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)

    # 动态更新字段
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 画像置信度
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="profile")


# ============================================================
# Learning Models
# ============================================================
class LearningPath(Base):
    """Personalized Learning Path - 个性化学习路径"""
    __tablename__ = "learning_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    current_stage: Mapped[str] = mapped_column(String(50), default=LearningStage.STAGE_1_BASICS.value)
    total_weeks: Mapped[int] = mapped_column(Integer, default=16)
    completed_weeks: Mapped[int] = mapped_column(Integer, default=0)
    path_data: Mapped[JSON] = mapped_column(JSON, nullable=False)  # 完整路径JSON
    roadmap_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Mermaid图URL
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="learning_paths")
    tasks: Mapped[List["LearningTask"]] = relationship(back_populates="learning_path")


class LearningTask(Base):
    """Weekly Learning Tasks - 每周学习任务"""
    __tablename__ = "learning_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tasks: Mapped[JSON] = mapped_column(JSON, nullable=False)  # 具体任务列表
    resources: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)  # 关联资源ID
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    learning_path: Mapped["LearningPath"] = relationship(back_populates="tasks")


# ============================================================
# Resource Models
# ============================================================
class GeneratedResource(Base):
    """AI-Generated Learning Resources - AI生成的学习资源"""
    __tablename__ = "generated_resources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge_points: Mapped[JSON] = mapped_column(JSON, nullable=True)  # 涵盖知识点
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # Markdown内容
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default=DifficultyLevel.BASIC.value)
    resource_metadata: Mapped[Optional[JSON]] = mapped_column("metadata", JSON, nullable=True)
    agent_generated: Mapped[str] = mapped_column(String(50), nullable=True)  # 生成Agent
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="resources")


# ============================================================
# Conversation & History Models
# ============================================================
class ConversationHistory(Base):
    """Dialogue History for Profile Building & Tutoring - 对话历史"""
    __tablename__ = "conversation_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), default="text")  # text / resource / quiz / system
    extra_metadata: Mapped[Optional[JSON]] = mapped_column("metadata", JSON, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="conversations")


class QuizRecord(Base):
    """Quiz & Exercise Records - 测验与练习记录"""
    __tablename__ = "quiz_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    quiz_type: Mapped[str] = mapped_column(String(30), nullable=False)  # choice / true_false / short_answer / coding
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge_point: Mapped[str] = mapped_column(String(200), nullable=True)
    questions: Mapped[JSON] = mapped_column(JSON, nullable=False)
    user_answers: Mapped[JSON] = mapped_column(JSON, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_spent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # seconds
    feedback: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="quiz_records")


class EvaluationReport(Base):
    """Learning Evaluation Reports - 学习评估报告"""
    __tablename__ = "evaluation_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    metrics: Mapped[JSON] = mapped_column(JSON, nullable=False)  # 各项指标
    current_level: Mapped[str] = mapped_column(String(50), nullable=True)
    weak_areas: Mapped[JSON] = mapped_column(JSON, nullable=True)
    strengths: Mapped[JSON] = mapped_column(JSON, nullable=True)
    suggestions: Mapped[JSON] = mapped_column(JSON, nullable=True)
    next_plan: Mapped[JSON] = mapped_column(JSON, nullable=True)
    report_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Markdown报告
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="evaluation_reports")


class KnowledgePoint(Base):
    """Course Knowledge Points - 课程知识点库"""
    __tablename__ = "knowledge_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("knowledge_points.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)  # 1-5
    difficulty: Mapped[str] = mapped_column(String(20), default=DifficultyLevel.BASIC.value)
    prerequisites: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)  # 前置知识点
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tags: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    resources_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentTaskLog(Base):
    """Agent Task Execution Log - Agent任务执行日志"""
    __tablename__ = "agent_task_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    input_params: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    output_summary: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_elapsed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # seconds
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================================
# Database Engine Setup
# ============================================================
_engine = None
_async_session = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_CONFIG["url"],
            echo=DATABASE_CONFIG["echo"],
        )
    return _engine


def get_async_session():
    global _async_session
    if _async_session is None:
        engine = get_engine()
        _async_session = async_sessionmaker(engine, expire_on_commit=False)
    return _async_session


async def init_db():
    """Initialize database tables"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency for FastAPI routes - yields async session"""
    session_maker = get_async_session()
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
