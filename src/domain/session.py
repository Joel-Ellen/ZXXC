# -*- coding: utf-8 -*-
"""Session domain models."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    COLD_START = "cold_start"
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"


class LearningSession(BaseModel):
    user_id: str
    course_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    current_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    iteration: int = 0
    c_epoch: int = 0
    re_plan_triggered: bool = False
    pedagogical_strategy: str = "STANDARD_PATH"
    recommended_resource_style: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
