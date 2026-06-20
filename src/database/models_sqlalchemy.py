# -*- coding: utf-8 -*-
"""
SQLAlchemy Models — 异步数据库模型（合并自 backend/）
====================================================

Tables:
  - User: 用户账号
  - StudentProfile: 学生学习画像
  - LearningPath: 学习路径规划
  - LearningTask: 学习任务
  - GeneratedResource: 生成的资源记录
  - ConversationHistory: 对话历史
  - QuizRecord: 测验记录
  - EvaluationReport: 评估报告
  - KnowledgePoint: 知识点库
  - AgentTaskLog: Agent 任务日志

来源: backend/models/database.py (merged)
"""
import os
import uuid
import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    pass


# ============================================================
# Enums
# ============================================================
class ResourceType(str, enum.Enum):
    LECTURE_NOTE = "lecture_note"
    PPT = "ppt"
    MINDMAP = "mindmap"
    EXERCISE = "exercise"
    PROJECT = "project"
    STUDY_NOTE = "study_note"
    VIDEO_SCRIPT = "video_script"
    ANIMATION_SCRIPT = "animation_script"


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
# User & Profile
# ============================================================
class User(Base):
    __tablename__ = "app_users"  # 与 src/database/connection.py 的 users 表区分

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
    """Dynamic Student Learning Profile"""
    __tablename__ = "student_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id"), unique=True, nullable=False)

    major: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    university: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    learning_goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    learning_habits: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    weekly_study_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 画像维度（8维）
    major_background: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    knowledge_level: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    learning_ability: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    learning_preference: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    cognitive_style: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    weak_points: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    interest_direction: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    career_goal: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)

    mastered_knowledge: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    learning_history: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)

    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="profile")


# ============================================================
# Learning Models
# ============================================================
class LearningPath(Base):
    __tablename__ = "learning_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id"), nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    current_stage: Mapped[str] = mapped_column(String(50), default=LearningStage.STAGE_1_BASICS.value)
    total_weeks: Mapped[int] = mapped_column(Integer, default=16)
    completed_weeks: Mapped[int] = mapped_column(Integer, default=0)
    path_data: Mapped[JSON] = mapped_column(JSON, nullable=False)
    roadmap_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="learning_paths")
    tasks: Mapped[List["LearningTask"]] = relationship(back_populates="learning_path")


class LearningTask(Base):
    __tablename__ = "learning_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tasks: Mapped[JSON] = mapped_column(JSON, nullable=False)
    resources: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    learning_path: Mapped["LearningPath"] = relationship(back_populates="tasks")


# ============================================================
# Resource Models
# ============================================================
class GeneratedResource(Base):
    __tablename__ = "generated_resources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge_points: Mapped[JSON] = mapped_column(JSON, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default=DifficultyLevel.BASIC.value)
    resource_metadata: Mapped[Optional[JSON]] = mapped_column("metadata", JSON, nullable=True)
    agent_generated: Mapped[str] = mapped_column(String(50), nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="resources")


# ============================================================
# Conversation & History
# ============================================================
class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), default="text")
    extra_metadata: Mapped[Optional[JSON]] = mapped_column("metadata", JSON, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="conversations")


class QuizRecord(Base):
    __tablename__ = "quiz_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id"), nullable=False)
    quiz_type: Mapped[str] = mapped_column(String(30), nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge_point: Mapped[str] = mapped_column(String(200), nullable=True)
    questions: Mapped[JSON] = mapped_column(JSON, nullable=False)
    user_answers: Mapped[JSON] = mapped_column(JSON, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_spent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feedback: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="quiz_records")


class EvaluationReport(Base):
    __tablename__ = "evaluation_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id"), nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    metrics: Mapped[JSON] = mapped_column(JSON, nullable=False)
    current_level: Mapped[str] = mapped_column(String(50), nullable=True)
    weak_areas: Mapped[JSON] = mapped_column(JSON, nullable=True)
    strengths: Mapped[JSON] = mapped_column(JSON, nullable=True)
    suggestions: Mapped[JSON] = mapped_column(JSON, nullable=True)
    next_plan: Mapped[JSON] = mapped_column(JSON, nullable=True)
    report_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="evaluation_reports")


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("knowledge_points.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    difficulty: Mapped[str] = mapped_column(String(20), default=DifficultyLevel.BASIC.value)
    prerequisites: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tags: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    resources_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentTaskLog(Base):
    __tablename__ = "agent_task_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("app_users.id"), nullable=True)
    input_params: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    output_summary: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_elapsed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
