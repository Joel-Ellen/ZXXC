# -*- coding: utf-8 -*-
"""Session response DTOs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.contracts.resource_contract import ResourceContract
from src.domain.assessment import AssessmentResult
from src.domain.path import LearningPath
from src.domain.profile import DynamicLearningProfile, StudentProfile
from src.domain.session import LearningSession


class SessionResponse(BaseModel):
    resource_contract_version: int = 2
    agent_feedback_version: int = 1
    session: LearningSession
    profile: StudentProfile
    dynamic_profile: DynamicLearningProfile
    learning_path: LearningPath
    resources: Dict[str, List[ResourceContract]] = Field(default_factory=dict)
    assessment: AssessmentResult = Field(default_factory=AssessmentResult)
    tutor_response: Optional[Dict[str, Any]] = None
    agent_feedback: List[Dict[str, Any]] = Field(default_factory=list)
    pipeline_log: List[Dict[str, Any]] = Field(default_factory=list)

    def to_dto_dict(self) -> Dict[str, Any]:
        return self.model_dump()
