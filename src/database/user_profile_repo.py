# -*- coding: utf-8 -*-
"""
用户资料仓库
===========
同步 PostgreSQL 持久化存储。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from .connection import db


class UserProfileRepo:
    """PostgreSQL 用户资料仓库。"""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id                         VARCHAR(64) PRIMARY KEY,
        university                      VARCHAR(256) NOT NULL DEFAULT '',
        major                           VARCHAR(256) NOT NULL DEFAULT '',
        grade                           VARCHAR(64) NOT NULL DEFAULT '',
        learning_goal                   TEXT NOT NULL DEFAULT '',
        weekly_study_hours              INTEGER NOT NULL DEFAULT 6,
        preferred_resource_style        VARCHAR(32) NOT NULL DEFAULT 'textual',
        preferred_pace                  VARCHAR(32) NOT NULL DEFAULT 'steady',
        preferred_practice_intensity    VARCHAR(32) NOT NULL DEFAULT 'balanced',
        updated_at                      VARCHAR(64) NOT NULL
    );
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS university VARCHAR(256) NOT NULL DEFAULT '';
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS major VARCHAR(256) NOT NULL DEFAULT '';
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS grade VARCHAR(64) NOT NULL DEFAULT '';
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS learning_goal TEXT NOT NULL DEFAULT '';
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS weekly_study_hours INTEGER NOT NULL DEFAULT 6;
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_resource_style VARCHAR(32) NOT NULL DEFAULT 'textual';
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_pace VARCHAR(32) NOT NULL DEFAULT 'steady';
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_practice_intensity VARCHAR(32) NOT NULL DEFAULT 'balanced';
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS updated_at VARCHAR(64) NOT NULL DEFAULT '';
    CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);
    """

    def ensure_tables(self) -> None:
        db.execute(self.CREATE_TABLE_SQL)
        db.commit()

    def get_by_user_id(self, user_id: str) -> Optional[dict]:
        self.ensure_tables()
        row = db.execute(
            """SELECT user_id, university, major, grade, learning_goal, weekly_study_hours,
                      preferred_resource_style, preferred_pace, preferred_practice_intensity, updated_at
               FROM user_profiles
               WHERE user_id = %s""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def upsert(self, user_id: str, payload: Dict[str, object]) -> dict:
        self.ensure_tables()
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

    def delete(self, user_id: str) -> None:
        self.ensure_tables()
        db.execute("DELETE FROM user_profiles WHERE user_id = %s", (user_id,))
        db.commit()


class JsonUserProfileRepo:
    """Durable local fallback with the same profile repository interface."""

    DEFAULT_PATH = str(Path(__file__).resolve().parents[2] / "frontend" / "_user_profiles.json")

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._path = Path(file_path or os.getenv("USER_PROFILE_STATE_PATH", self.DEFAULT_PATH))
        self._lock = threading.RLock()

    def _load(self) -> Dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return dict(data) if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def _save(self, data: Dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(self._path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._path)

    def get_by_user_id(self, user_id: str) -> Optional[dict]:
        with self._lock:
            row = self._load().get(user_id)
            return dict(row) if row else None

    def upsert(self, user_id: str, payload: Dict[str, object]) -> dict:
        with self._lock:
            data = self._load()
            current = data.get(user_id, {})
            allowed = {
                "university": "",
                "major": "",
                "grade": "",
                "learning_goal": "",
                "weekly_study_hours": 6,
                "preferred_resource_style": "textual",
                "preferred_pace": "steady",
                "preferred_practice_intensity": "balanced",
            }
            row = {key: payload.get(key, current.get(key, default)) for key, default in allowed.items()}
            row["weekly_study_hours"] = int(row.get("weekly_study_hours") or 0)
            row.update({"user_id": user_id, "updated_at": datetime.now(timezone.utc).isoformat()})
            data[user_id] = row
            self._save(data)
            return dict(row)

    def delete(self, user_id: str) -> None:
        with self._lock:
            data = self._load()
            data.pop(user_id, None)
            self._save(data)
