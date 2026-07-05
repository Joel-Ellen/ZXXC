# -*- coding: utf-8 -*-
"""Assessment domain models."""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StrategyDecision(BaseModel):
    strategy: str = "STANDARD_PATH"
    reason: str = ""
    confidence: float = 0.0
    signals: Dict[str, object] = Field(default_factory=dict)


class AssessmentResult(BaseModel):
    node_id: Optional[str] = None
    mastery: Optional[float] = None
    capability_radar: List[float] = Field(default_factory=list)
    diagnostic_report_md: str = ""
    strategy_decision: StrategyDecision = Field(default_factory=StrategyDecision)
