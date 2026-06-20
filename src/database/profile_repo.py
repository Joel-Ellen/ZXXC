# -*- coding: utf-8 -*-
"""
Profile Repo — 学生画像异步持久化
==================================
"""
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_sqlalchemy import StudentProfile


class ProfileRepo:
    """学生画像异步仓库。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_user_id(self, user_id: str) -> Optional[StudentProfile]:
        result = await self._session.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        user_id: str,
        profile_data: Dict[str, Any],
    ) -> StudentProfile:
        profile = await self.get_by_user_id(user_id)
        if profile:
            for key, value in profile_data.items():
                if hasattr(profile, key) and value is not None:
                    setattr(profile, key, value)
            profile.profile_version = (profile.profile_version or 0) + 1
        else:
            profile = StudentProfile(user_id=user_id, **profile_data)
            self._session.add(profile)

        await self._session.commit()
        await self._session.refresh(profile)
        return profile

    async def update_dimension(
        self,
        user_id: str,
        dimension_name: str,
        dimension_data: Dict[str, Any],
    ) -> Optional[StudentProfile]:
        profile = await self.get_by_user_id(user_id)
        if profile and hasattr(profile, dimension_name):
            setattr(profile, dimension_name, dimension_data)
            profile.profile_version = (profile.profile_version or 0) + 1
            await self._session.commit()
            await self._session.refresh(profile)
        return profile
