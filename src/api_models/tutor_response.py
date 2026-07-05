# -*- coding: utf-8 -*-
"""Tutor response DTOs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TutorResponse(BaseModel):
    tutor_response: Optional[Dict[str, Any]] = None
    reference_count: int = 0
    agent_feedback_version: int = 1
    agent_feedback: List[Dict[str, Any]] = Field(default_factory=list)
