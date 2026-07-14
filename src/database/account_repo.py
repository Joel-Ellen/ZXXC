# -*- coding: utf-8 -*-
"""Persistent account settings, action tokens, and device sessions.

PostgreSQL is the primary store. ``JsonAccountRepo`` is a durable fallback for
local installations that intentionally run without PostgreSQL; it mirrors the
same small interface and never stores raw password-reset or verification
tokens.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.auth.account_service import action_subject_hash_matches, normalize_action_subject

from .connection import db


CREATE_ACCOUNT_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS user_account_settings (
    user_id             VARCHAR(64) PRIMARY KEY,
    preferences_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    privacy_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    email_verified_at   VARCHAR(64),
    email_verified_for  VARCHAR(256),
    updated_at          VARCHAR(64) NOT NULL
);

ALTER TABLE user_account_settings
    ADD COLUMN IF NOT EXISTS email_verified_for VARCHAR(256);

CREATE TABLE IF NOT EXISTS auth_action_tokens (
    id              SERIAL PRIMARY KEY,
    token_hash      VARCHAR(128) NOT NULL UNIQUE,
    user_id         VARCHAR(64) NOT NULL,
    purpose         VARCHAR(32) NOT NULL,
    subject_hash    VARCHAR(128),
    expires_at      VARCHAR(64) NOT NULL,
    consumed_at     VARCHAR(64),
    created_at      VARCHAR(64) NOT NULL
);

ALTER TABLE auth_action_tokens
    ADD COLUMN IF NOT EXISTS subject_hash VARCHAR(128);

CREATE TABLE IF NOT EXISTS auth_device_sessions (
    session_id          VARCHAR(96) PRIMARY KEY,
    user_id             VARCHAR(64) NOT NULL,
    refresh_jti         VARCHAR(96) NOT NULL,
    device_name         VARCHAR(160) NOT NULL DEFAULT '',
    user_agent          VARCHAR(512) NOT NULL DEFAULT '',
    ip_address          VARCHAR(96) NOT NULL DEFAULT '',
    created_at          VARCHAR(64) NOT NULL,
    last_seen_at        VARCHAR(64) NOT NULL,
    expires_at          VARCHAR(64) NOT NULL,
    revoked_at          VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_auth_action_tokens_user_purpose
    ON auth_action_tokens(user_id, purpose);
CREATE INDEX IF NOT EXISTS idx_auth_device_sessions_user
    ON auth_device_sessions(user_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_future(value: str) -> bool:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def _normalized_email(value: object) -> Optional[str]:
    normalized = normalize_action_subject(value)
    return normalized or None


class AccountRepo:
    """PostgreSQL account metadata repository."""

    def ensure_tables(self) -> None:
        db.execute(CREATE_ACCOUNT_TABLES_SQL)
        db.commit()

    def get_settings(self, user_id: str) -> Dict[str, Any]:
        self.ensure_tables()
        row = db.execute(
            "SELECT * FROM user_account_settings WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        if not row:
            return {
                "user_id": user_id,
                "preferences": {},
                "privacy": {},
                "email_verified_at": None,
                "email_verified_for": None,
                "updated_at": None,
            }
        data = dict(row)
        verified_for = _normalized_email(data.get("email_verified_for"))
        return {
            "user_id": user_id,
            "preferences": dict(data.get("preferences_json") or {}),
            "privacy": dict(data.get("privacy_json") or {}),
            "email_verified_at": data.get("email_verified_at") if verified_for else None,
            "email_verified_for": verified_for,
            "updated_at": data.get("updated_at"),
        }

    def upsert_settings(
        self,
        user_id: str,
        *,
        preferences: Optional[Dict[str, Any]] = None,
        privacy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current = self.get_settings(user_id)
        next_preferences = current["preferences"] if preferences is None else dict(preferences)
        next_privacy = current["privacy"] if privacy is None else dict(privacy)
        now = _now()
        db.execute(
            """INSERT INTO user_account_settings (
                   user_id, preferences_json, privacy_json, email_verified_at,
                   email_verified_for, updated_at
               ) VALUES (%s, %s::jsonb, %s::jsonb, %s, %s, %s)
               ON CONFLICT (user_id) DO UPDATE SET
                   preferences_json = EXCLUDED.preferences_json,
                   privacy_json = EXCLUDED.privacy_json,
                   updated_at = EXCLUDED.updated_at""",
            (
                user_id,
                json.dumps(next_preferences, ensure_ascii=False),
                json.dumps(next_privacy, ensure_ascii=False),
                current.get("email_verified_at"),
                current.get("email_verified_for"),
                now,
            ),
        )
        db.commit()
        return self.get_settings(user_id)

    def mark_email_verified(self, user_id: str, email: Optional[str] = None) -> Dict[str, Any]:
        current = self.get_settings(user_id)
        verified_for = _normalized_email(email)
        now = _now()
        verified_at = now if verified_for else None
        db.execute(
            """INSERT INTO user_account_settings (
                   user_id, preferences_json, privacy_json, email_verified_at,
                   email_verified_for, updated_at
               ) VALUES (%s, %s::jsonb, %s::jsonb, %s, %s, %s)
               ON CONFLICT (user_id) DO UPDATE SET
                   email_verified_at = EXCLUDED.email_verified_at,
                   email_verified_for = EXCLUDED.email_verified_for,
                   updated_at = EXCLUDED.updated_at""",
            (
                user_id,
                json.dumps(current["preferences"], ensure_ascii=False),
                json.dumps(current["privacy"], ensure_ascii=False),
                verified_at,
                verified_for,
                now,
            ),
        )
        db.commit()
        return self.get_settings(user_id)

    def clear_email_verification(self, user_id: str) -> Dict[str, Any]:
        current = self.get_settings(user_id)
        self.ensure_tables()
        now = _now()
        db.execute(
            """INSERT INTO user_account_settings (
                   user_id, preferences_json, privacy_json, email_verified_at,
                   email_verified_for, updated_at
               ) VALUES (%s, %s::jsonb, %s::jsonb, NULL, NULL, %s)
               ON CONFLICT (user_id) DO UPDATE SET
                   email_verified_at = NULL,
                   email_verified_for = NULL,
                   updated_at = EXCLUDED.updated_at""",
            (
                user_id,
                json.dumps(current["preferences"], ensure_ascii=False),
                json.dumps(current["privacy"], ensure_ascii=False),
                now,
            ),
        )
        db.commit()
        return self.get_settings(user_id)

    def create_action_token(
        self,
        user_id: str,
        purpose: str,
        token_hash: str,
        expires_at: str,
        subject_hash: Optional[str] = None,
    ) -> None:
        self.ensure_tables()
        now = _now()
        db.execute(
            "UPDATE auth_action_tokens SET consumed_at = %s WHERE user_id = %s AND purpose = %s AND consumed_at IS NULL",
            (now, user_id, purpose),
        )
        db.execute(
            """INSERT INTO auth_action_tokens
               (token_hash, user_id, purpose, subject_hash, expires_at, consumed_at, created_at)
               VALUES (%s, %s, %s, %s, %s, NULL, %s)""",
            (token_hash, user_id, purpose, subject_hash, expires_at, now),
        )
        db.commit()

    def get_action_token_binding(self, token_hash: str, purpose: str) -> Optional[Dict[str, Any]]:
        self.ensure_tables()
        row = db.execute(
            """SELECT user_id, subject_hash, expires_at, consumed_at
               FROM auth_action_tokens WHERE token_hash = %s AND purpose = %s""",
            (token_hash, purpose),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        return {
            "user_id": str(data.get("user_id") or ""),
            "subject_hash": data.get("subject_hash"),
            "expires_at": data.get("expires_at"),
            "consumed": bool(data.get("consumed_at")),
            "active": not data.get("consumed_at") and _is_future(data.get("expires_at", "")),
        }

    def consume_action_token(
        self,
        token_hash: str,
        purpose: str,
        *,
        subject_hash: Optional[str] = None,
    ) -> Optional[str]:
        self.ensure_tables()
        row = db.execute(
            """SELECT id, user_id, subject_hash, expires_at FROM auth_action_tokens
               WHERE token_hash = %s AND purpose = %s AND consumed_at IS NULL""",
            (token_hash, purpose),
        ).fetchone()
        if (
            not row
            or not _is_future(row["expires_at"])
            or not action_subject_hash_matches(row.get("subject_hash"), subject_hash)
        ):
            return None
        now = _now()
        updated = db.execute(
            """UPDATE auth_action_tokens SET consumed_at = %s
               WHERE id = %s AND consumed_at IS NULL
                 AND subject_hash IS NOT DISTINCT FROM %s
               RETURNING user_id""",
            (now, row["id"], subject_hash),
        ).fetchone()
        db.commit()
        return str(updated["user_id"]) if updated else None

    def revoke_action_tokens(self, user_id: str, purpose: Optional[str] = None) -> None:
        self.ensure_tables()
        now = _now()
        if purpose:
            db.execute(
                "UPDATE auth_action_tokens SET consumed_at = %s WHERE user_id = %s AND purpose = %s AND consumed_at IS NULL",
                (now, user_id, purpose),
            )
        else:
            db.execute(
                "UPDATE auth_action_tokens SET consumed_at = %s WHERE user_id = %s AND consumed_at IS NULL",
                (now, user_id),
            )
        db.commit()

    def create_device_session(
        self,
        session_id: str,
        user_id: str,
        refresh_jti: str,
        *,
        device_name: str,
        user_agent: str,
        ip_address: str,
        expires_at: str,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        now = _now()
        db.execute(
            """INSERT INTO auth_device_sessions (
                   session_id, user_id, refresh_jti, device_name, user_agent,
                   ip_address, created_at, last_seen_at, expires_at, revoked_at
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
               ON CONFLICT (session_id) DO UPDATE SET
                   user_id = EXCLUDED.user_id,
                   refresh_jti = EXCLUDED.refresh_jti,
                   device_name = EXCLUDED.device_name,
                   user_agent = EXCLUDED.user_agent,
                   ip_address = EXCLUDED.ip_address,
                   last_seen_at = EXCLUDED.last_seen_at,
                   expires_at = EXCLUDED.expires_at,
                   revoked_at = NULL""",
            (
                session_id,
                user_id,
                refresh_jti,
                device_name[:160],
                user_agent[:512],
                ip_address[:96],
                now,
                now,
                expires_at,
            ),
        )
        db.commit()
        return self.get_device_session(session_id) or {}

    def get_device_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_tables()
        row = db.execute(
            "SELECT * FROM auth_device_sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def is_device_session_active(
        self,
        session_id: str,
        user_id: str,
        refresh_jti: Optional[str] = None,
    ) -> bool:
        session = self.get_device_session(session_id)
        if not session or session.get("user_id") != user_id or session.get("revoked_at"):
            return False
        if refresh_jti and session.get("refresh_jti") != refresh_jti:
            return False
        return _is_future(str(session.get("expires_at") or ""))

    def rotate_device_session(self, session_id: str, old_jti: str, new_jti: str, expires_at: str) -> bool:
        self.ensure_tables()
        row = db.execute(
            """UPDATE auth_device_sessions
               SET refresh_jti = %s, last_seen_at = %s, expires_at = %s
               WHERE session_id = %s AND refresh_jti = %s AND revoked_at IS NULL
               RETURNING session_id""",
            (new_jti, _now(), expires_at, session_id, old_jti),
        ).fetchone()
        db.commit()
        return bool(row)

    def list_device_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        self.ensure_tables()
        rows = db.execute(
            """SELECT session_id, user_id, device_name, user_agent, ip_address,
                      created_at, last_seen_at, expires_at, revoked_at
               FROM auth_device_sessions WHERE user_id = %s
               ORDER BY last_seen_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows if not row.get("revoked_at") and _is_future(row.get("expires_at", ""))]

    def revoke_device_session(self, user_id: str, session_id: str) -> bool:
        try:
            self.ensure_tables()
            row = db.execute(
                """UPDATE auth_device_sessions SET revoked_at = %s
                   WHERE user_id = %s AND session_id = %s AND revoked_at IS NULL
                   RETURNING session_id""",
                (_now(), user_id, session_id),
            ).fetchone()
            return bool(row)
        except Exception:
            db.rollback()
            raise

    def revoke_all_device_sessions(self, user_id: str) -> int:
        try:
            self.ensure_tables()
            rows = db.execute(
                """UPDATE auth_device_sessions SET revoked_at = %s
                   WHERE user_id = %s AND revoked_at IS NULL
                   RETURNING session_id""",
                (_now(), user_id),
            ).fetchall()
            return len(rows)
        except Exception:
            db.rollback()
            raise

    def delete_user_data(self, user_id: str) -> None:
        try:
            self.ensure_tables()
            db.execute("DELETE FROM auth_action_tokens WHERE user_id = %s", (user_id,))
            db.execute("DELETE FROM auth_device_sessions WHERE user_id = %s", (user_id,))
            db.execute("DELETE FROM user_account_settings WHERE user_id = %s", (user_id,))
            db.commit()
        except Exception:
            db.rollback()
            raise


class JsonAccountRepo:
    """Thread-safe JSON implementation used when PostgreSQL is unavailable."""

    DEFAULT_PATH = str(Path(__file__).resolve().parents[2] / "frontend" / "_account_state.json")

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._path = Path(file_path or os.getenv("ACCOUNT_STATE_PATH", self.DEFAULT_PATH))
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> Dict[str, Any]:
        return {"settings": {}, "action_tokens": {}, "device_sessions": {}}

    def _load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return self._empty()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._empty()
            return {
                "settings": dict(data.get("settings") or {}),
                "action_tokens": dict(data.get("action_tokens") or {}),
                "device_sessions": dict(data.get("device_sessions") or {}),
            }
        except (OSError, json.JSONDecodeError, TypeError):
            return self._empty()

    def _save(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(self._path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._path)

    def get_settings(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            raw = self._load()["settings"].get(user_id, {})
            verified_for = _normalized_email(raw.get("email_verified_for"))
            return {
                "user_id": user_id,
                "preferences": copy.deepcopy(raw.get("preferences") or {}),
                "privacy": copy.deepcopy(raw.get("privacy") or {}),
                "email_verified_at": raw.get("email_verified_at") if verified_for else None,
                "email_verified_for": verified_for,
                "updated_at": raw.get("updated_at"),
            }

    def upsert_settings(self, user_id: str, *, preferences=None, privacy=None) -> Dict[str, Any]:
        with self._lock:
            data = self._load()
            current = data["settings"].get(user_id, {})
            data["settings"][user_id] = {
                "preferences": copy.deepcopy(current.get("preferences") if preferences is None else preferences) or {},
                "privacy": copy.deepcopy(current.get("privacy") if privacy is None else privacy) or {},
                "email_verified_at": current.get("email_verified_at"),
                "email_verified_for": current.get("email_verified_for"),
                "updated_at": _now(),
            }
            self._save(data)
            return self.get_settings(user_id)

    def mark_email_verified(self, user_id: str, email: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            data = self._load()
            current = data["settings"].get(user_id, {})
            now = _now()
            verified_for = _normalized_email(email)
            current.update({
                "email_verified_at": now if verified_for else None,
                "email_verified_for": verified_for,
                "updated_at": now,
            })
            current.setdefault("preferences", {})
            current.setdefault("privacy", {})
            data["settings"][user_id] = current
            self._save(data)
            return self.get_settings(user_id)

    def clear_email_verification(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            data = self._load()
            current = data["settings"].get(user_id, {})
            current.update({
                "email_verified_at": None,
                "email_verified_for": None,
                "updated_at": _now(),
            })
            current.setdefault("preferences", {})
            current.setdefault("privacy", {})
            data["settings"][user_id] = current
            self._save(data)
            return self.get_settings(user_id)

    def create_action_token(
        self,
        user_id: str,
        purpose: str,
        token_hash: str,
        expires_at: str,
        subject_hash: Optional[str] = None,
    ) -> None:
        with self._lock:
            data = self._load()
            now = _now()
            for item in data["action_tokens"].values():
                if item.get("user_id") == user_id and item.get("purpose") == purpose and not item.get("consumed_at"):
                    item["consumed_at"] = now
            data["action_tokens"][token_hash] = {
                "user_id": user_id,
                "purpose": purpose,
                "subject_hash": subject_hash,
                "expires_at": expires_at,
                "consumed_at": None,
                "created_at": now,
            }
            self._save(data)

    def get_action_token_binding(self, token_hash: str, purpose: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._load()["action_tokens"].get(token_hash)
            if not item or item.get("purpose") != purpose:
                return None
            return {
                "user_id": str(item.get("user_id") or ""),
                "subject_hash": item.get("subject_hash"),
                "expires_at": item.get("expires_at"),
                "consumed": bool(item.get("consumed_at")),
                "active": not item.get("consumed_at") and _is_future(item.get("expires_at", "")),
            }

    def consume_action_token(
        self,
        token_hash: str,
        purpose: str,
        *,
        subject_hash: Optional[str] = None,
    ) -> Optional[str]:
        with self._lock:
            data = self._load()
            item = data["action_tokens"].get(token_hash)
            if (
                not item
                or item.get("purpose") != purpose
                or item.get("consumed_at")
                or not _is_future(item.get("expires_at", ""))
                or not action_subject_hash_matches(item.get("subject_hash"), subject_hash)
            ):
                return None
            item["consumed_at"] = _now()
            self._save(data)
            return str(item.get("user_id") or "") or None

    def revoke_action_tokens(self, user_id: str, purpose: Optional[str] = None) -> None:
        with self._lock:
            data = self._load()
            now = _now()
            for item in data["action_tokens"].values():
                if item.get("user_id") == user_id and (not purpose or item.get("purpose") == purpose):
                    item["consumed_at"] = item.get("consumed_at") or now
            self._save(data)

    def create_device_session(
        self,
        session_id: str,
        user_id: str,
        refresh_jti: str,
        *,
        device_name: str,
        user_agent: str,
        ip_address: str,
        expires_at: str,
    ) -> Dict[str, Any]:
        with self._lock:
            data = self._load()
            previous = data["device_sessions"].get(session_id, {})
            now = _now()
            data["device_sessions"][session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "refresh_jti": refresh_jti,
                "device_name": str(device_name)[:160],
                "user_agent": str(user_agent)[:512],
                "ip_address": str(ip_address)[:96],
                "created_at": previous.get("created_at") or now,
                "last_seen_at": now,
                "expires_at": expires_at,
                "revoked_at": None,
            }
            self._save(data)
            return copy.deepcopy(data["device_sessions"][session_id])

    def get_device_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._load()["device_sessions"].get(session_id)
            return copy.deepcopy(item) if item else None

    def is_device_session_active(self, session_id: str, user_id: str, refresh_jti: Optional[str] = None) -> bool:
        item = self.get_device_session(session_id)
        if not item or item.get("user_id") != user_id or item.get("revoked_at"):
            return False
        if refresh_jti and item.get("refresh_jti") != refresh_jti:
            return False
        return _is_future(item.get("expires_at", ""))

    def rotate_device_session(self, session_id: str, old_jti: str, new_jti: str, expires_at: str) -> bool:
        with self._lock:
            data = self._load()
            item = data["device_sessions"].get(session_id)
            if not item or item.get("refresh_jti") != old_jti or item.get("revoked_at"):
                return False
            item.update({"refresh_jti": new_jti, "expires_at": expires_at, "last_seen_at": _now()})
            self._save(data)
            return True

    def list_device_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = [
                copy.deepcopy(item)
                for item in self._load()["device_sessions"].values()
                if item.get("user_id") == user_id
                and not item.get("revoked_at")
                and _is_future(item.get("expires_at", ""))
            ]
            for item in rows:
                item.pop("refresh_jti", None)
            return sorted(rows, key=lambda item: item.get("last_seen_at", ""), reverse=True)

    def revoke_device_session(self, user_id: str, session_id: str) -> bool:
        with self._lock:
            data = self._load()
            item = data["device_sessions"].get(session_id)
            if not item or item.get("user_id") != user_id or item.get("revoked_at"):
                return False
            item["revoked_at"] = _now()
            self._save(data)
            return True

    def revoke_all_device_sessions(self, user_id: str) -> int:
        with self._lock:
            data = self._load()
            count = 0
            now = _now()
            for item in data["device_sessions"].values():
                if item.get("user_id") == user_id and not item.get("revoked_at"):
                    item["revoked_at"] = now
                    count += 1
            self._save(data)
            return count

    def delete_user_data(self, user_id: str) -> None:
        with self._lock:
            data = self._load()
            data["settings"].pop(user_id, None)
            data["action_tokens"] = {
                key: item for key, item in data["action_tokens"].items() if item.get("user_id") != user_id
            }
            data["device_sessions"] = {
                key: item for key, item in data["device_sessions"].items() if item.get("user_id") != user_id
            }
            self._save(data)
