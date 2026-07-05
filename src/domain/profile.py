# -*- coding: utf-8 -*-
"""Profile domain models."""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StudentProfile(BaseModel):
    user_id: str
    course_id: str
    motivation: str = "academic_exam"
    time_budget_hours_per_week: float = 10.0
    knowledge_base: List[str] = Field(default_factory=list)
    cognitive_style_weights: Dict[str, float] = Field(default_factory=dict)


class DynamicLearningProfile(BaseModel):
    knowledge_mastery: Dict[str, float] = Field(default_factory=dict)
    continuous_fail_counter: int = 0
    capability_radar: List[float] = Field(default_factory=list)
    diagnostic_report_md: str = ""
    error_type_distribution: Dict[str, float] = Field(default_factory=dict)
