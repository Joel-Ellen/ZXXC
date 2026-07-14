# -*- coding: utf-8 -*-
"""Versioned session snapshot repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .connection import db
from .session_repo import SessionRepo


CREATE_SNAPSHOT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_snapshots (
    id              SERIAL PRIMARY KEY,
    session_id      VARCHAR(96) NOT NULL,
    user_id         VARCHAR(64) NOT NULL,
    course_id       VARCHAR(64) NOT NULL,
    version         INTEGER NOT NULL,
    state_json      JSONB NOT NULL,
    cold_state_json JSONB,
    path_json       JSONB,
    profile_json    JSONB,
    resource_bundle_json JSONB,
    assessment_json JSONB,
    pipeline_log_json JSONB,
    created_at      VARCHAR(64) NOT NULL,
    UNIQUE(session_id, version)
);
CREATE INDEX IF NOT EXISTS idx_session_snapshots_user_course ON session_snapshots(user_id, course_id);
CREATE INDEX IF NOT EXISTS idx_session_snapshots_session_version ON session_snapshots(session_id, version DESC);
"""


class SessionSnapshotRepo:
    def ensure_tables(self) -> None:
        SessionRepo().ensure_tables()
        db.execute(CREATE_SNAPSHOT_TABLE_SQL)
        db.commit()

    def get_latest(self, user_id: str, course_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_tables()
        session_id = SessionRepo.build_session_id(user_id, course_id)
        row = db.execute(
            """SELECT * FROM session_snapshots
               WHERE session_id = %s
               ORDER BY version DESC
               LIMIT 1""",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def next_version(self, user_id: str, course_id: str) -> int:
        latest = self.get_latest(user_id, course_id)
        return int(latest["version"] if latest else 0) + 1

    def save_snapshot(
        self,
        user_id: str,
        course_id: str,
        state_json: str,
        cold_state_json: Optional[str] = None,
        path_json: Optional[Dict[str, Any]] = None,
        profile_json: Optional[Dict[str, Any]] = None,
        resource_bundle_json: Optional[Dict[str, Any]] = None,
        assessment_json: Optional[Dict[str, Any]] = None,
        pipeline_log_json: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        version = self.next_version(user_id, course_id)
        session_id = SessionRepo.build_session_id(user_id, course_id)
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            """INSERT INTO session_snapshots (
               session_id, user_id, course_id, version, state_json, cold_state_json,
               path_json, profile_json, resource_bundle_json, assessment_json,
               pipeline_log_json, created_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)""",
            (
                session_id,
                user_id,
                course_id,
                version,
                state_json,
                cold_state_json,
                json.dumps(path_json or {}, ensure_ascii=False),
                json.dumps(profile_json or {}, ensure_ascii=False),
                json.dumps(resource_bundle_json or {}, ensure_ascii=False),
                json.dumps(assessment_json or {}, ensure_ascii=False),
                json.dumps(pipeline_log_json or [], ensure_ascii=False),
                now,
            ),
        )
        db.commit()
        SessionRepo().upsert(
            user_id,
            course_id,
            current_node_id=(json.loads(state_json).get("current_node_id") if state_json else None),
            target_node_id=(json.loads(state_json).get("target_node_id") if state_json else None),
            snapshot_version=version,
            profile_version=version,
            path_version=version,
            resource_bundle_version=version,
            assessment_version=version,
        )
        return self.get_latest(user_id, course_id) or {}

    def delete_for_session(self, user_id: str, course_id: str) -> None:
        self.ensure_tables()
        session_id = SessionRepo.build_session_id(user_id, course_id)
        db.execute("DELETE FROM session_snapshots WHERE session_id = %s", (session_id,))
        db.commit()

    def delete_all(self, user_id: str) -> None:
        self.ensure_tables()
        db.execute("DELETE FROM session_snapshots WHERE user_id = %s", (user_id,))
        db.commit()
