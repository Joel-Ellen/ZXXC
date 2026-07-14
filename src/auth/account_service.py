# -*- coding: utf-8 -*-
"""Account-domain helpers shared by the Starlette authentication surface."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Callable, Dict, Iterable, Optional


DEFAULT_PREFERENCES: Dict[str, Any] = {
    "theme": "system",
    "high_contrast": False,
    "reduce_motion": False,
    "font_size": 16,
}

DEFAULT_PRIVACY: Dict[str, Any] = {
    "analytics_enabled": False,
    "personalization_enabled": True,
    "profile_visibility": "private",
}


def is_production() -> bool:
    value = (
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("NODE_ENV")
        or "development"
    )
    return str(value).strip().lower() in {"prod", "production"}


def normalize_preferences(payload: object, current: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    raw = dict(payload) if isinstance(payload, dict) else {}
    aliases = {
        "highContrast": "high_contrast",
        "reduceMotion": "reduce_motion",
        "fontSize": "font_size",
    }
    raw = {aliases.get(key, key): value for key, value in raw.items()}
    result = {**DEFAULT_PREFERENCES, **(current or {})}
    if "theme" in raw:
        theme = str(raw["theme"] or "").strip().lower()
        if theme not in {"system", "light", "dark"}:
            raise ValueError("settings_theme_invalid")
        result["theme"] = theme
    for key in ("high_contrast", "reduce_motion"):
        if key in raw:
            if not isinstance(raw[key], bool):
                raise ValueError(f"settings_{key}_invalid")
            result[key] = raw[key]
    if "font_size" in raw:
        if isinstance(raw["font_size"], bool):
            raise ValueError("settings_font_size_invalid")
        try:
            font_size = int(raw["font_size"])
        except (TypeError, ValueError):
            raise ValueError("settings_font_size_invalid") from None
        if not 12 <= font_size <= 24:
            raise ValueError("settings_font_size_invalid")
        result["font_size"] = font_size
    return result


def normalize_privacy(payload: object, current: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    raw = dict(payload) if isinstance(payload, dict) else {}
    aliases = {
        "analyticsEnabled": "analytics_enabled",
        "personalizationEnabled": "personalization_enabled",
        "profileVisibility": "profile_visibility",
    }
    raw = {aliases.get(key, key): value for key, value in raw.items()}
    result = {**DEFAULT_PRIVACY, **(current or {})}
    for key in ("analytics_enabled", "personalization_enabled"):
        if key in raw:
            if not isinstance(raw[key], bool):
                raise ValueError(f"privacy_{key}_invalid")
            result[key] = raw[key]
    if "profile_visibility" in raw:
        visibility = str(raw["profile_visibility"] or "").strip().lower()
        if visibility not in {"private", "teachers", "public"}:
            raise ValueError("privacy_profile_visibility_invalid")
        result["profile_visibility"] = visibility
    return result


_UNBOUND_SUBJECT_DIGEST = "0" * 64


def normalize_action_subject(subject: object) -> str:
    """Normalize an email-like action-token subject before hashing it."""
    return str(subject or "").strip().lower()


def hash_action_subject(subject: object) -> str:
    normalized = normalize_action_subject(subject)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def action_subject_hash_matches(stored_subject_hash: Optional[str], candidate_subject_hash: Optional[str]) -> bool:
    """Compare optional subject digests without data-dependent string equality."""
    stored_bound = stored_subject_hash is not None
    candidate_bound = candidate_subject_hash is not None
    stored_digest = str(stored_subject_hash or _UNBOUND_SUBJECT_DIGEST).lower()
    candidate_digest = str(candidate_subject_hash or _UNBOUND_SUBJECT_DIGEST).lower()
    digest_matches = hmac.compare_digest(stored_digest, candidate_digest)
    return digest_matches and stored_bound == candidate_bound


def action_subject_matches(stored_subject_hash: Optional[str], subject: Optional[object]) -> bool:
    """Constant-time validation for a stored digest and a caller-owned subject."""
    candidate_hash = None if subject is None else hash_action_subject(subject)
    return action_subject_hash_matches(stored_subject_hash, candidate_hash)


def issue_action_token(
    repo: Any,
    user_id: str,
    purpose: str,
    ttl_seconds: int,
    *,
    subject: Optional[object] = None,
) -> str:
    raw_token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    repo.create_action_token(
        user_id,
        purpose,
        hash_action_token(raw_token),
        expires_at,
        subject_hash=None if subject is None else hash_action_subject(subject),
    )
    return raw_token


def consume_action_token(
    repo: Any,
    raw_token: str,
    purpose: str,
    *,
    subject: Optional[object] = None,
) -> Optional[str]:
    user_id = resolve_action_token(repo, raw_token, purpose, subject=subject)
    if not user_id:
        return None
    token_hash = hash_action_token(str(raw_token or "").strip())
    candidate_subject_hash = None if subject is None else hash_action_subject(subject)
    consumed_user_id = repo.consume_action_token(
        token_hash,
        purpose,
        subject_hash=candidate_subject_hash,
    )
    return user_id if consumed_user_id == user_id else None


def resolve_action_token(
    repo: Any,
    raw_token: str,
    purpose: str,
    *,
    subject: Optional[object] = None,
) -> Optional[str]:
    """Validate an action token without consuming it.

    Password reset uses this preflight before revoking sessions. The token is
    claimed separately only after revocation has been durably verified.
    """
    token = str(raw_token or "").strip()
    if len(token) < 24 or len(token) > 256:
        return None
    token_hash = hash_action_token(token)
    binding = repo.get_action_token_binding(token_hash, purpose)
    if not binding or not binding.get("active"):
        return None
    stored_subject_hash = binding.get("subject_hash")
    if not action_subject_matches(stored_subject_hash, subject):
        return None
    return str(binding.get("user_id") or "") or None


class AccountLifecycleError(RuntimeError):
    """A fail-closed account operation did not reach its required invariant."""

    def __init__(self, code: str, step: str) -> None:
        super().__init__(code)
        self.code = code
        self.step = step


def revoke_all_sessions_fail_closed(
    repo: Any,
    user_id: str,
    revoke_cached_sessions: Callable[[str], Any],
) -> int:
    """Revoke persistent sessions, verify the result, then clear the cache."""
    try:
        revoked_count = int(repo.revoke_all_device_sessions(user_id) or 0)
        remaining = repo.list_device_sessions(user_id)
    except Exception as exc:
        raise AccountLifecycleError("SESSION_REVOCATION_FAILED", "persistent_sessions") from exc
    if remaining:
        raise AccountLifecycleError("SESSION_REVOCATION_FAILED", "persistent_sessions")
    try:
        cache_result = revoke_cached_sessions(user_id)
    except Exception as exc:
        raise AccountLifecycleError("SESSION_REVOCATION_FAILED", "cached_sessions") from exc
    if cache_result is False:
        raise AccountLifecycleError("SESSION_REVOCATION_FAILED", "cached_sessions")
    return revoked_count


def run_required_cleanup_steps(
    steps: Iterable[tuple[str, Callable[[], Any]]],
) -> None:
    """Run idempotent pre-deletion steps and stop before identity deletion on failure."""
    for step, cleanup in steps:
        try:
            result = cleanup()
        except Exception as exc:
            raise AccountLifecycleError("ACCOUNT_DATA_CLEANUP_FAILED", step) from exc
        if result is False:
            raise AccountLifecycleError("ACCOUNT_DATA_CLEANUP_FAILED", step)


def hash_action_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_expiry_iso(days: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def email_delivery_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def deliver_action_email(email: str, purpose: str, raw_token: str) -> bool:
    """Deliver an action link through configured SMTP without logging tokens."""
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    if not host or not sender:
        return False
    try:
        port = int(os.getenv("SMTP_PORT", "465"))
    except ValueError:
        return False
    use_ssl = os.getenv("SMTP_SSL", "1").strip().lower() not in {"0", "false", "no"}
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    base_url = os.getenv("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")
    if purpose == "password_reset":
        subject = "Reset your EduAgent password"
        link = f"{base_url}/login?reset_token={raw_token}"
        action = "Reset password"
    else:
        subject = "Verify your EduAgent email"
        link = f"{base_url}/account?verify_token={raw_token}"
        action = "Verify email"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email
    message["Subject"] = subject
    message.set_content(f"{action}: {link}\n\nThis one-time link will expire automatically.")
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=10) as client:
                if username:
                    client.login(username, password)
                client.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=10) as client:
                if os.getenv("SMTP_STARTTLS", "1").strip().lower() not in {"0", "false", "no"}:
                    client.starttls()
                if username:
                    client.login(username, password)
                client.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        return False


def _mapping(value: object) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _course_title(course_store: Any, course_id: str) -> str:
    try:
        course = course_store.get_by_id(course_id)
        return str(getattr(course, "title_cn", None) or getattr(course, "title", None) or course_id)
    except Exception:
        return course_id


def _event_time(event: Dict[str, Any]) -> str:
    return str(event.get("received_at") or event.get("occurred_at") or event.get("recorded_at") or "")


def build_learning_summary(
    *,
    enrollments: Dict[str, Any],
    state_rows: Iterable[Dict[str, Any]],
    session_rows: Iterable[Dict[str, Any]],
    course_store: Any,
    node_title: Callable[[str], str],
) -> Dict[str, Any]:
    """Derive progress and resume data exclusively from server-owned records."""
    states: Dict[str, Dict[str, Any]] = {}
    state_updated: Dict[str, str] = {}
    for row in state_rows:
        course_id = str(row.get("course_id") or "")
        if not course_id:
            continue
        states[course_id] = _mapping(row.get("state_json"))
        state_updated[course_id] = str(row.get("updated_at") or "")
    session_updated = {
        str(row.get("course_id") or ""): str(row.get("updated_at") or "")
        for row in session_rows
        if row.get("course_id")
    }

    all_recent: list[Dict[str, Any]] = []
    courses: list[Dict[str, Any]] = []
    for course_id, enrollment in (enrollments.get("courses") or {}).items():
        state = states.get(course_id, {})
        internal = _mapping(state.get("internal_state"))
        events = [item for item in internal.get("learning_events", []) if isinstance(item, dict)]
        assets = _mapping(internal.get("learning_assets"))
        categories = _mapping(assets.get("categories"))
        recent_assets = _mapping(categories.get("recent_learning"))

        by_event_id: Dict[str, Dict[str, Any]] = {}
        for event in events:
            event_id = str(event.get("event_id") or "")
            if event_id:
                by_event_id[event_id] = {
                    "event_id": event_id,
                    "course_id": course_id,
                    "course_title": _course_title(course_store, course_id),
                    "node_id": str(event.get("node_id") or event.get("current_node_id") or ""),
                    "event_type": str(event.get("event_type") or ""),
                    "occurred_at": _event_time(event),
                    "resource_id": str(event.get("resource_id") or ""),
                }
        for key, asset in recent_assets.items():
            if not isinstance(asset, dict) or asset.get("source") not in {"server_event", "server_event_reference"}:
                continue
            event_id = str(asset.get("event_id") or key or "")
            record = by_event_id.get(event_id)
            if record is None and event_id:
                # A server-managed record remains eligible even if an older
                # compact event ledger was pruned from the state snapshot.
                record = {
                    "event_id": event_id,
                    "course_id": course_id,
                    "course_title": _course_title(course_store, course_id),
                    "node_id": str(asset.get("node_id") or ""),
                    "event_type": str(asset.get("event_type") or ""),
                    "occurred_at": str(asset.get("occurred_at") or asset.get("updated_at") or ""),
                    "resource_id": str(asset.get("resource_id") or ""),
                }
            if record is not None:
                by_event_id[event_id] = record

        recent = sorted(by_event_id.values(), key=lambda item: item.get("occurred_at", ""), reverse=True)
        for item in recent:
            item["node_title"] = node_title(item["node_id"]) if item["node_id"] else ""
        all_recent.extend(recent)

        latest = recent[0] if recent else None
        fallback_node = str(state.get("current_node_id") or "")
        last_node_id = str((latest or {}).get("node_id") or fallback_node)
        activity_candidates = [
            str((latest or {}).get("occurred_at") or ""),
            state_updated.get(course_id, ""),
            session_updated.get(course_id, ""),
        ]
        last_activity_at = max((value for value in activity_candidates if value), default="")
        try:
            total_nodes = len(state.get("active_path") or [])
        except TypeError:
            total_nodes = 0
        if total_nodes <= 0:
            course = course_store.get_by_id(course_id)
            total_nodes = int(getattr(course, "node_count", 0) or 0) if course else 0
        courses.append({
            "course_id": course_id,
            "progress": max(0.0, min(1.0, float(enrollment.get("progress", 0.0) or 0.0))),
            "completed_nodes": max(0, int(enrollment.get("completed_nodes", 0) or 0)),
            "total_nodes": max(0, total_nodes),
            "last_node_id": last_node_id,
            "last_node_title": node_title(last_node_id) if last_node_id else "",
            "last_activity_at": last_activity_at,
            "last_event_type": str((latest or {}).get("event_type") or ""),
        })

    all_recent.sort(key=lambda item: item.get("occurred_at", ""), reverse=True)
    recent_learning = [
        {key: value for key, value in item.items() if key != "event_id"}
        for item in all_recent[:20]
    ]
    latest = all_recent[0] if all_recent else None
    continue_learning = None
    if latest and latest.get("course_id") and latest.get("node_id"):
        continue_learning = {
            "course_id": latest["course_id"],
            "node_id": latest["node_id"],
            "occurred_at": latest.get("occurred_at", ""),
        }
    courses.sort(key=lambda item: item.get("last_activity_at", ""), reverse=True)
    if continue_learning is None:
        fallback = next(
            (item for item in courses if item.get("course_id") and item.get("last_node_id")),
            None,
        )
        if fallback is not None:
            continue_learning = {
                "course_id": fallback["course_id"],
                "node_id": fallback["last_node_id"],
                "occurred_at": fallback.get("last_activity_at", ""),
            }
    return {
        "courses": courses,
        "recent_learning": recent_learning,
        "continue_learning": continue_learning,
    }
