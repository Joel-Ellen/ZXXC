# -*- coding: utf-8 -*-
"""Canonical resource payload contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResourceIssue(BaseModel):
    """Serializable validation detail with support for legacy issue shapes."""

    model_config = ConfigDict(extra="allow")

    code: str = ""
    message: str = ""
    severity: str = "error"
    field: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_issue(cls, value: Any) -> Dict[str, Any]:
        if isinstance(value, BaseModel):
            value = value.model_dump()
        if isinstance(value, str):
            return {
                "code": "legacy_issue",
                "message": value,
                "details": {"legacy_format": "string"},
            }
        if not isinstance(value, dict):
            return {
                "code": "legacy_issue",
                "message": str(value),
                "details": {"legacy_format": type(value).__name__},
            }

        payload = dict(value)
        raw_code = payload.get("code", payload.get("type", ""))
        raw_message = payload.get("message", payload.get("msg", raw_code))
        payload["code"] = str(raw_code or "")
        payload["message"] = str(raw_message or "")
        payload["severity"] = str(payload.get("severity") or "error")
        if payload.get("field") is not None:
            payload["field"] = str(payload["field"])
        if not isinstance(payload.get("details"), dict):
            raw_details = payload.get("details")
            payload["details"] = {} if raw_details is None else {"value": raw_details}
        return payload


class ResourceValidation(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "pending"
    passed: Optional[bool] = None
    score: Optional[float] = None
    issues: List[ResourceIssue] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResourceSafety(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "unknown"
    issues: List[ResourceIssue] = Field(default_factory=list)


class ResourceContract(BaseModel):
    resource_id: str
    node_id: str
    resource_type: str
    title: str = ""
    body_markdown: str = ""
    structured_payload: Dict[str, Any] = Field(default_factory=dict)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    difficulty: float = 0.5
    difficulty_basis: Dict[str, Any] = Field(default_factory=dict)
    personalization_basis: Dict[str, Any] = Field(default_factory=dict)
    generation: Dict[str, Any] = Field(default_factory=dict)
    content_version: str = ""
    validation: ResourceValidation = Field(default_factory=ResourceValidation)
    safety: ResourceSafety = Field(default_factory=ResourceSafety)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

