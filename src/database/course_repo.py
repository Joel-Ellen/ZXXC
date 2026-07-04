# -*- coding: utf-8 -*-
"""
课程目录仓库
===========
同步 PostgreSQL 持久化存储。
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from .connection import db


class CourseRepo:
    """PostgreSQL 课程目录仓库。"""

    def list_courses(self, search: Optional[str] = None, category: Optional[str] = None) -> List[dict]:
        clauses = ["is_active = 1"]
        params: List[object] = []
        if search:
            keyword = f"%{search.lower().strip()}%"
            clauses.append(
                "(LOWER(course_id) LIKE %s OR LOWER(title) LIKE %s OR LOWER(title_cn) LIKE %s OR LOWER(description) LIKE %s OR LOWER(description_cn) LIKE %s)"
            )
            params.extend([keyword, keyword, keyword, keyword, keyword])
        if category:
            clauses.append("category = %s")
            params.append(category.strip())

        where_sql = " AND ".join(clauses)
        rows = db.execute(
            f"""SELECT course_id, title, title_cn, description, description_cn, category,
                       difficulty, estimated_hours, node_count, tags_json, icon, prerequisites_json
                FROM courses
                WHERE {where_sql}
                ORDER BY difficulty ASC, title_cn ASC""",
            tuple(params),
        ).fetchall()
        return [self._hydrate(dict(row)) for row in rows]

    def get_by_id(self, course_id: str) -> Optional[dict]:
        row = db.execute(
            """SELECT course_id, title, title_cn, description, description_cn, category,
                      difficulty, estimated_hours, node_count, tags_json, icon, prerequisites_json
               FROM courses
               WHERE course_id = %s AND is_active = 1""",
            (course_id,),
        ).fetchone()
        return self._hydrate(dict(row)) if row else None

    def upsert_course(self, record: Dict[str, object]) -> dict:
        db.execute(
            """INSERT INTO courses (
                   course_id, title, title_cn, description, description_cn, category,
                   difficulty, estimated_hours, node_count, tags_json, icon, prerequisites_json, is_active
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, 1)
               ON CONFLICT (course_id) DO UPDATE SET
                   title = EXCLUDED.title,
                   title_cn = EXCLUDED.title_cn,
                   description = EXCLUDED.description,
                   description_cn = EXCLUDED.description_cn,
                   category = EXCLUDED.category,
                   difficulty = EXCLUDED.difficulty,
                   estimated_hours = EXCLUDED.estimated_hours,
                   node_count = EXCLUDED.node_count,
                   tags_json = EXCLUDED.tags_json,
                   icon = EXCLUDED.icon,
                   prerequisites_json = EXCLUDED.prerequisites_json,
                   is_active = 1""",
            (
                record.get("course_id", ""),
                record.get("title", ""),
                record.get("title_cn", ""),
                record.get("description", ""),
                record.get("description_cn", ""),
                record.get("category", "computer_science"),
                float(record.get("difficulty", 0.5) or 0.5),
                float(record.get("estimated_hours", 40.0) or 40.0),
                int(record.get("node_count", 0) or 0),
                json.dumps(record.get("tags", []) or [], ensure_ascii=False),
                record.get("icon", ""),
                json.dumps(record.get("prerequisites", []) or [], ensure_ascii=False),
            ),
        )
        db.commit()
        return self.get_by_id(str(record.get("course_id", ""))) or {}

    def count(self) -> int:
        row = db.execute("SELECT COUNT(*) as n FROM courses WHERE is_active = 1").fetchone()
        return int(row["n"]) if row else 0

    @staticmethod
    def _hydrate(row: Dict[str, object]) -> dict:
        row["tags"] = row.pop("tags_json", []) or []
        row["prerequisites"] = row.pop("prerequisites_json", []) or []
        return row
