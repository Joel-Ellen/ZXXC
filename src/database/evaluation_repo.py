# -*- coding: utf-8 -*-
"""
Evaluation Repo — 评估报告异步持久化
=====================================
"""
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_sqlalchemy import EvaluationReport


class EvaluationRepo:
    """评估报告异步仓库。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, report_data: Dict[str, Any]) -> EvaluationReport:
        report = EvaluationReport(**report_data)
        self._session.add(report)
        await self._session.commit()
        await self._session.refresh(report)
        return report

    async def get_by_user(
        self,
        user_id: str,
        course_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[EvaluationReport]:
        stmt = select(EvaluationReport).where(EvaluationReport.user_id == user_id)
        if course_name:
            stmt = stmt.where(EvaluationReport.course_name == course_name)
        stmt = stmt.order_by(EvaluationReport.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_latest(
        self,
        user_id: str,
        course_name: Optional[str] = None,
    ) -> Optional[EvaluationReport]:
        stmt = select(EvaluationReport).where(EvaluationReport.user_id == user_id)
        if course_name:
            stmt = stmt.where(EvaluationReport.course_name == course_name)
        stmt = stmt.order_by(EvaluationReport.created_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
