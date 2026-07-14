# -*- coding: utf-8 -*-
"""
学习状态数据仓库
===============
AgentState 的 JSONB 持久化存储。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .connection import db


class StateRepo:
    """AgentState 持久化存储。"""

    def load_state(self, user_id: str, course_id: str) -> Optional[Dict[str, Any]]:
        row = db.execute(
            "SELECT state_json, cold_state_json FROM user_state WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "state_json": row["state_json"],
            "cold_state_json": row["cold_state_json"],
        }

    def save_state(
        self,
        user_id: str,
        course_id: str,
        state_json: str,
        cold_state_json: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            """INSERT INTO user_state (user_id, course_id, state_json, cold_state_json, updated_at)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (user_id, course_id) DO UPDATE SET
               state_json = EXCLUDED.state_json,
               cold_state_json = EXCLUDED.cold_state_json,
               updated_at = EXCLUDED.updated_at""",
            (user_id, course_id, state_json, cold_state_json, now),
        )
        db.commit()

    def delete_state(self, user_id: str, course_id: str) -> None:
        db.execute(
            "DELETE FROM user_state WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        )
        db.commit()

    def list_user_states(self, user_id: str) -> list[Dict[str, Any]]:
        rows = db.execute(
            "SELECT user_id, course_id, state_json, cold_state_json, updated_at FROM user_state WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_all(self, user_id: str) -> None:
        db.execute("DELETE FROM user_state WHERE user_id = %s", (user_id,))
        db.commit()
