# -*- coding: utf-8 -*-
"""Standard validation result models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ValidationDecision(str, Enum):
    PASSED = "passed"
    REFINED = "refined"
    REJECTED = "rejected"
    FAILED = "failed"


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: str = "error"
    field: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    passed: bool = True
    decision: ValidationDecision = ValidationDecision.PASSED
    issues: List[ValidationIssue] = Field(default_factory=list)
    sanitized_text: Optional[str] = None
    refined_text: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_issue(self, code: str, message: str, severity: str = "error", field: Optional[str] = None, **details: Any) -> None:
        self.issues.append(ValidationIssue(code=code, message=message, severity=severity, field=field, details=details))
        if severity in {"error", "critical"}:
            self.passed = False
            self.decision = ValidationDecision.REJECTED

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.issues.extend(other.issues)
        self.metadata.update(other.metadata)
        if other.sanitized_text is not None:
            self.sanitized_text = other.sanitized_text
        if other.refined_text is not None:
            self.refined_text = other.refined_text
        if not other.passed:
            self.passed = False
            self.decision = other.decision
        elif other.decision == ValidationDecision.REFINED and self.decision == ValidationDecision.PASSED:
            self.decision = ValidationDecision.REFINED
        return self

    def to_contract_validation(self) -> Dict[str, Any]:
        return {
            "status": self.decision.value,
            "passed": self.passed,
            "issues": [issue.model_dump() for issue in self.issues],
            "metadata": self.metadata,
        }
