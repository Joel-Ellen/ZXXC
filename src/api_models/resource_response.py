# -*- coding: utf-8 -*-
"""Resource response DTOs."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.contracts.resource_contract import ResourceContract


class ResourceResponse(BaseModel):
    status: str = "ok"
    node_id: str
    resources: List[ResourceContract] = Field(default_factory=list)

    def to_dto_dict(self) -> Dict[str, Any]:
        return self.model_dump()
