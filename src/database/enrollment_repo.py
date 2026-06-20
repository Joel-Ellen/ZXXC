# -*- coding: utf-8 -*-
"""
选课数据仓库
===========
PostgreSQL 持久化存储。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .connection import db


class EnrollmentRepo:
    """PostgreSQL 用户选课持久化存储。"""

    def get_user_enrollments(self, user_id: str) -> Dict[str, Any]:
        rows = db.execute(
            "SELECT course_id, enrolled_at, progress, completed_nodes, is_active FROM user_courses WHERE user_id = %s",
            (user_id,),
        ).fetchall()

        courses = {}
        active_course = ""
        for r in rows:
            d = dict(r)
            courses[d["course_id"]] = {
                "enrolled_at": d["enrolled_at"],
                "progress": d["progress"],
                "completed_nodes": d["completed_nodes"],
            }
            if d["is_active"]:
                active_course = d["course_id"]

        return {"active_course": active_course, "courses": courses}

    def enroll(self, user_id: str, course_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing = db.execute(
            "SELECT id FROM user_courses WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        ).fetchone()

        if existing:
            db.execute("UPDATE user_courses SET is_active = 0 WHERE user_id = %s", (user_id,))
            db.execute(
                "UPDATE user_courses SET is_active = 1 WHERE user_id = %s AND course_id = %s",
                (user_id, course_id),
            )
        else:
            db.execute("UPDATE user_courses SET is_active = 0 WHERE user_id = %s", (user_id,))
            db.execute(
                """INSERT INTO user_courses (user_id, course_id, enrolled_at, progress, completed_nodes, is_active)
                   VALUES (%s, %s, %s, 0.0, 0, 1)""",
                (user_id, course_id, now),
            )
        db.commit()
        return {"status": "enrolled", "user_id": user_id, "course_id": course_id}

    def switch_course(self, user_id: str, course_id: str) -> bool:
        existing = db.execute(
            "SELECT id FROM user_courses WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        ).fetchone()
        if not existing:
            return False

        db.execute("UPDATE user_courses SET is_active = 0 WHERE user_id = %s", (user_id,))
        db.execute(
            "UPDATE user_courses SET is_active = 1 WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        )
        db.commit()
        return True

    def update_progress(self, user_id: str, course_id: str, progress: float, completed_nodes: int):
        db.execute(
            "UPDATE user_courses SET progress = %s, completed_nodes = %s WHERE user_id = %s AND course_id = %s",
            (progress, completed_nodes, user_id, course_id),
        )
        db.commit()
