# -*- coding: utf-8 -*-
"""
Resource Repo — 生成资源异步持久化
===================================
"""
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_sqlalchemy import GeneratedResource


class ResourceRepo:
    """生成资源异步仓库。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, resource_data: Dict[str, Any]) -> GeneratedResource:
        resource = GeneratedResource(**resource_data)
        self._session.add(resource)
        await self._session.commit()
        await self._session.refresh(resource)
        return resource

    async def get_by_user(
        self,
        user_id: str,
        resource_type: Optional[str] = None,
        course_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[GeneratedResource]:
        stmt = select(GeneratedResource).where(GeneratedResource.user_id == user_id)
        if resource_type:
            stmt = stmt.where(GeneratedResource.resource_type == resource_type)
        if course_name:
            stmt = stmt.where(GeneratedResource.course_name == course_name)
        stmt = stmt.order_by(GeneratedResource.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, resource_id: str) -> Optional[GeneratedResource]:
        result = await self._session.execute(
            select(GeneratedResource).where(GeneratedResource.id == resource_id)
        )
        return result.scalar_one_or_none()
