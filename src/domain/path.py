# -*- coding: utf-8 -*-
"""Learning path domain models."""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PathNode(BaseModel):
    id: str
    title: str = ""
    mastery: float = 0.0
    status: str = "pending"
    metadata: Dict[str, object] = Field(default_factory=dict)


class LearningPath(BaseModel):
    nodes: List[PathNode] = Field(default_factory=list)
    current_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
