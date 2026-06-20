# -*- coding: utf-8 -*-
"""
课程数据模型
===========
Pydantic v2 课程记录模型。
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class CourseRecord(BaseModel):
    """单门课程的持久化记录。"""

    course_id: str = Field(..., min_length=1, description="课程唯一标识 (slug)")
    title: str = Field(..., description="英文课程名")
    title_cn: str = Field(..., description="中文课程名")
    description: str = Field(default="", description="英文课程描述")
    description_cn: str = Field(default="", description="中文课程描述")
    category: str = Field(default="computer_science", description="学科分类")
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0, description="难度系数 0-1")
    estimated_hours: float = Field(default=40.0, description="预估总学时")
    node_count: int = Field(default=0, description="知识节点数量")
    tags: List[str] = Field(default_factory=list, description="搜索标签")
    icon: str = Field(default="📚", description="课程图标 (emoji)")
    prerequisites: List[str] = Field(default_factory=list, description="推荐前置课程 ID 列表")

    def to_api_dict(self) -> dict:
        """返回 API 响应用的安全字典。"""
        return self.model_dump()
