# -*- coding: utf-8 -*-
"""Resource domain models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SafetyStatus(str, Enum):
    UNKNOWN = "unknown"
    SAFE = "safe"
    FLAGGED = "flagged"


class LearningResource(BaseModel):
    resource_id: str
    node_id: str
    resource_type: str
    title: str = ""
    body_markdown: str = ""
    structured_payload: Dict[str, Any] = Field(default_factory=dict)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    difficulty: float = 0.5
    personalization_basis: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    safety: Dict[str, Any] = Field(default_factory=dict)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None


class ResourceBundle(BaseModel):
    node_id: str
    resources: List[LearningResource] = Field(default_factory=list)
