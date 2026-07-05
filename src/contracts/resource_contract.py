# -*- coding: utf-8 -*-
"""Canonical resource payload contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ResourceValidation(BaseModel):
    status: str = "pending"
    score: Optional[float] = None
    issues: List[str] = Field(default_factory=list)


class ResourceSafety(BaseModel):
    status: str = "unknown"
    issues: List[str] = Field(default_factory=list)


class ResourceContract(BaseModel):
    resource_id: str
    node_id: str
    resource_type: str
    title: str = ""
    body_markdown: str = ""
    structured_payload: Dict[str, Any] = Field(default_factory=dict)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    difficulty: float = 0.5
    personalization_basis: Dict[str, Any] = Field(default_factory=dict)
    validation: ResourceValidation = Field(default_factory=ResourceValidation)
    safety: ResourceSafety = Field(default_factory=ResourceSafety)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def with_legacy_aliases(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["card_type"] = self.resource_type
        data["content"] = self.body_markdown
        data["metadata"] = self.structured_payload
        return data
