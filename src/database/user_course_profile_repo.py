# -*- coding: utf-8 -*-
"""
课程级画像与问卷仓库
==================
同步 PostgreSQL 持久化存储。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Optional

from .connection import db


class UserCourseProfileRepo:
    """PostgreSQL 课程级问卷与画像仓库。"""

    def get_by_user_course(self, user_id: str, course_id: str) -> Optional[dict]:
        row = db.execute(
            """SELECT user_id, course_id, survey_version, survey_answers_json, derived_profile_json,
                      created_at, updated_at
               FROM user_course_profiles
               WHERE user_id = %s AND course_id = %s""",
            (user_id, course_id),
        ).fetchone()
        return dict(row) if row else None

    def upsert(
        self,
        user_id: str,
        course_id: str,
        survey_version: int,
        survey_answers: Dict[str, object],
        derived_profile: Dict[str, object],
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            """INSERT INTO user_course_profiles (
                   user_id, course_id, survey_version, survey_answers_json, derived_profile_json, created_at, updated_at
               ) VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
               ON CONFLICT (user_id, course_id) DO UPDATE SET
                   survey_version = EXCLUDED.survey_version,
                   survey_answers_json = EXCLUDED.survey_answers_json,
                   derived_profile_json = EXCLUDED.derived_profile_json,
                   updated_at = EXCLUDED.updated_at""",
            (
                user_id,
                course_id,
                int(survey_version or 1),
                json.dumps(survey_answers or {}, ensure_ascii=False),
                json.dumps(derived_profile or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        db.commit()
        return self.get_by_user_course(user_id, course_id) or {}
