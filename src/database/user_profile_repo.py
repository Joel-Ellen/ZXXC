# -*- coding: utf-8 -*-
"""
用户资料仓库
===========
同步 PostgreSQL 持久化存储。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from .connection import db


class UserProfileRepo:
    """PostgreSQL 用户资料仓库。"""

    def get_by_user_id(self, user_id: str) -> Optional[dict]:
        row = db.execute(
            """SELECT user_id, university, major, grade, learning_goal, weekly_study_hours,
                      preferred_resource_style, preferred_pace, preferred_practice_intensity, updated_at
               FROM user_profiles
               WHERE user_id = %s""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def upsert(self, user_id: str, payload: Dict[str, object]) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            """INSERT INTO user_profiles (
                   user_id, university, major, grade, learning_goal, weekly_study_hours,
                   preferred_resource_style, preferred_pace, preferred_practice_intensity, updated_at
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id) DO UPDATE SET
                   university = EXCLUDED.university,
                   major = EXCLUDED.major,
                   grade = EXCLUDED.grade,
                   learning_goal = EXCLUDED.learning_goal,
                   weekly_study_hours = EXCLUDED.weekly_study_hours,
                   preferred_resource_style = EXCLUDED.preferred_resource_style,
                   preferred_pace = EXCLUDED.preferred_pace,
                   preferred_practice_intensity = EXCLUDED.preferred_practice_intensity,
                   updated_at = EXCLUDED.updated_at""",
            (
                user_id,
                str(payload.get("university", "") or ""),
                str(payload.get("major", "") or ""),
                str(payload.get("grade", "") or ""),
                str(payload.get("learning_goal", "") or ""),
                int(payload.get("weekly_study_hours", 6) or 6),
                str(payload.get("preferred_resource_style", "textual") or "textual"),
                str(payload.get("preferred_pace", "steady") or "steady"),
                str(payload.get("preferred_practice_intensity", "balanced") or "balanced"),
                now,
            ),
        )
        db.commit()
        return self.get_by_user_id(user_id) or {}
