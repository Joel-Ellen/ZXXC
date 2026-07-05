# -*- coding: utf-8 -*-
"""Persistent learning session metadata repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .connection import db


CREATE_SESSION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS learning_sessions (
    id              SERIAL PRIMARY KEY,
    session_id      VARCHAR(96) NOT NULL UNIQUE,
    user_id         VARCHAR(64) NOT NULL,
    course_id       VARCHAR(64) NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'active',
    current_node_id VARCHAR(64),
    target_node_id  VARCHAR(64),
    snapshot_version INTEGER NOT NULL DEFAULT 0,
    profile_version INTEGER NOT NULL DEFAULT 0,
    path_version INTEGER NOT NULL DEFAULT 0,
    resource_bundle_version INTEGER NOT NULL DEFAULT 0,
    assessment_version INTEGER NOT NULL DEFAULT 0,
    created_at      VARCHAR(64) NOT NULL,
    updated_at      VARCHAR(64) NOT NULL,
    UNIQUE(user_id, course_id)
);
CREATE INDEX IF NOT EXISTS idx_learning_sessions_user_course ON learning_sessions(user_id, course_id);
"""


class SessionRepo:
    def ensure_tables(self) -> None:
        db.execute(CREATE_SESSION_TABLE_SQL)
        db.commit()

    @staticmethod
    def build_session_id(user_id: str, course_id: str) -> str:
        return f"{user_id}:{course_id}"

    def get_by_user_course(self, user_id: str, course_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_tables()
        row = db.execute(
            "SELECT * FROM learning_sessions WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        ).fetchone()
        return dict(row) if row else None

    def upsert(
        self,
        user_id: str,
        course_id: str,
        status: str = "active",
        current_node_id: Optional[str] = None,
        target_node_id: Optional[str] = None,
        snapshot_version: Optional[int] = None,
        profile_version: Optional[int] = None,
        path_version: Optional[int] = None,
        resource_bundle_version: Optional[int] = None,
        assessment_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        now = datetime.now(timezone.utc).isoformat()
        session_id = self.build_session_id(user_id, course_id)
        existing = self.get_by_user_course(user_id, course_id)
        if existing:
            db.execute(
                """UPDATE learning_sessions SET
                   status = %s,
                   current_node_id = %s,
                   target_node_id = %s,
                   snapshot_version = COALESCE(%s, snapshot_version),
                   profile_version = COALESCE(%s, profile_version),
                   path_version = COALESCE(%s, path_version),
                   resource_bundle_version = COALESCE(%s, resource_bundle_version),
                   assessment_version = COALESCE(%s, assessment_version),
                   updated_at = %s
                   WHERE user_id = %s AND course_id = %s""",
                (
                    status,
                    current_node_id,
                    target_node_id,
                    snapshot_version,
                    profile_version,
                    path_version,
                    resource_bundle_version,
                    assessment_version,
                    now,
                    user_id,
                    course_id,
                ),
            )
        else:
            db.execute(
                """INSERT INTO learning_sessions (
                   session_id, user_id, course_id, status, current_node_id, target_node_id,
                   snapshot_version, profile_version, path_version, resource_bundle_version,
                   assessment_version, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    session_id,
                    user_id,
                    course_id,
                    status,
                    current_node_id,
                    target_node_id,
                    snapshot_version or 0,
                    profile_version or 0,
                    path_version or 0,
                    resource_bundle_version or 0,
                    assessment_version or 0,
                    now,
                    now,
                ),
            )
        db.commit()
        return self.get_by_user_course(user_id, course_id) or {}

    def delete(self, user_id: str, course_id: str) -> None:
        self.ensure_tables()
        db.execute("DELETE FROM learning_sessions WHERE user_id = %s AND course_id = %s", (user_id, course_id))
        db.commit()
