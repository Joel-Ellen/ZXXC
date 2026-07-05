# -*- coding: utf-8 -*-
"""Profile response DTOs."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from src.domain.profile import StudentProfile


class ProfileResponse(BaseModel):
    phase: str
    profile: Optional[StudentProfile] = None
    probe: Optional[Dict[str, Any]] = None
    collected: Dict[str, Any] = Field(default_factory=dict)
    fusion_triggered: bool = False
