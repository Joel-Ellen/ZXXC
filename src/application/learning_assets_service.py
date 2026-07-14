# -*- coding: utf-8 -*-
"""Durable, scoped learning assets for a learner-course session.

The learning runtime already persists ``AgentState`` as the authoritative
per-user, per-course record.  This module deliberately keeps restoration
assets inside that state instead of adding a second browser-owned source of
truth.  UI assets never participate in mastery calculation; server-derived
learning events and diagnostic metadata are copied as compact audit-friendly
summaries only.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from threading import Lock, RLock
from typing import Any, Iterable, Optional
from uuid import uuid4

from src.state.agent_state import AgentState

from ._common import get_session, persist_session


LEARNING_ASSETS_KEY = "learning_assets"
LEARNING_ASSETS_VERSION = 1

ASSET_CATEGORIES = (
    "tutor_history",
    "drafts",
    "code_drafts",
    "quiz_progress",
    "annotations",
    "bookmarks",
    "recent_learning",
    "scroll_positions",
    "card_state",
    "latest_diagnostic",
)

# Browser-owned restoration state can be updated one key at a time. Timeline
# and diagnostic records are derived from authenticated server work, so a
# browser must never be able to forge, truncate, or replace them.
CLIENT_MUTABLE_ASSET_CATEGORIES = frozenset({
    "drafts",
    "code_drafts",
    "quiz_progress",
    "annotations",
    "bookmarks",
    "scroll_positions",
    "card_state",
})

SERVER_MANAGED_ASSET_CATEGORIES = frozenset(ASSET_CATEGORIES) - CLIENT_MUTABLE_ASSET_CATEGORIES

_CATEGORY_ALIASES = {
    "tutor": "tutor_history",
    "tutor_conversations": "tutor_history",
    "tutor_conversation_history": "tutor_history",
    "unsent_drafts": "drafts",
    "input_drafts": "drafts",
    "code": "code_drafts",
    "quiz": "quiz_progress",
    "notes": "annotations",
    "highlights": "annotations",
    "favorites": "bookmarks",
    "favourites": "bookmarks",
    "recent_learning_records": "recent_learning",
    "recent_records": "recent_learning",
    "scroll": "scroll_positions",
    "card_expansion": "card_state",
    "card_expansion_state": "card_state",
    "latest_diagnostic_metadata": "latest_diagnostic",
}

_MAX_ENTRIES = {
    "tutor_history": 400,
    "drafts": 120,
    "code_drafts": 120,
    "quiz_progress": 240,
    "annotations": 800,
    "bookmarks": 500,
    "recent_learning": 500,
    "scroll_positions": 500,
    "card_state": 1200,
    "latest_diagnostic": 1,
}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/\-]{0,159}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$")
_SECRET_KEY_MARKERS = (
    "password",
    "passphrase",
    "secret",
    "apikey",
    "token",
    "authorization",
    "cookie",
    "credential",
    "privatekey",
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)

_ASSET_LOCKS_GUARD = Lock()
_ASSET_LOCKS: dict[tuple[str, str], RLock] = {}


class AssetValidationError(ValueError):
    """Expected client-facing learning asset validation failure."""


def _asset_lock(user_id: str, course_id: str) -> RLock:
    key = (str(user_id), str(course_id))
    with _ASSET_LOCKS_GUARD:
        lock = _ASSET_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _ASSET_LOCKS[key] = lock
        return lock


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


def _as_text(value: object, *, field: str, max_length: int, allow_empty: bool = False) -> str:
    if isinstance(value, bool) or value is None:
        raise AssetValidationError(f"{field}_must_be_text")
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if not text and not allow_empty:
        raise AssetValidationError(f"{field}_required")
    if len(text) > max_length:
        raise AssetValidationError(f"{field}_too_long")
    return text


def _optional_text(value: object, *, field: str, max_length: int) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        raise AssetValidationError(f"{field}_must_be_text")
    text = str(value).strip()
    if len(text) > max_length:
        raise AssetValidationError(f"{field}_too_long")
    return text


def _identifier(value: object, *, field: str, required: bool = False) -> str:
    if value is None or value == "":
        if required:
            raise AssetValidationError(f"{field}_required")
        return ""
    identifier = _as_text(value, field=field, max_length=160)
    if not _ID_RE.fullmatch(identifier):
        raise AssetValidationError(f"{field}_invalid")
    return identifier


def _asset_key(value: object) -> str:
    """Validate a regular item key or the explicit array-replacement token."""
    if value == "__all__":
        return "__all__"
    return _identifier(value, field="asset_key", required=True)


def _first(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _contains_secret(value: object, *, depth: int = 0) -> bool:
    if depth > 8:
        return True
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower().replace("_", "").replace("-", "")
            if any(marker in normalized_key for marker in _SECRET_KEY_MARKERS):
                return True
            if _contains_secret(item, depth=depth + 1):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item, depth=depth + 1) for item in value)
    if isinstance(value, str):
        return any(pattern.search(value) is not None for pattern in _SECRET_VALUE_PATTERNS)
    return False


def _json_value(value: object, *, field: str, depth: int = 0) -> Any:
    """Keep quiz selections and small metadata JSON-safe and bounded."""
    if depth > 5:
        raise AssetValidationError(f"{field}_too_deep")
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise AssetValidationError(f"{field}_invalid_number")
        return value
    if isinstance(value, str):
        return _as_text(value, field=field, max_length=4_000, allow_empty=True)
    if isinstance(value, list):
        if len(value) > 200:
            raise AssetValidationError(f"{field}_too_many_items")
        return [_json_value(item, field=field, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 200:
            raise AssetValidationError(f"{field}_too_many_fields")
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = _as_text(key, field=f"{field}_key", max_length=80)
            normalized[safe_key] = _json_value(item, field=field, depth=depth + 1)
        return normalized
    raise AssetValidationError(f"{field}_unsupported")


def _number(value: object, *, field: str, minimum: float = 0.0, maximum: float = 100_000_000.0) -> float:
    if isinstance(value, bool):
        raise AssetValidationError(f"{field}_must_be_number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AssetValidationError(f"{field}_must_be_number") from None
    if number != number or number in (float("inf"), float("-inf")) or not minimum <= number <= maximum:
        raise AssetValidationError(f"{field}_out_of_range")
    return number


def _integer(value: object, *, field: str, minimum: int = 0, maximum: int = 10_000) -> int:
    if isinstance(value, bool):
        raise AssetValidationError(f"{field}_must_be_integer")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise AssetValidationError(f"{field}_must_be_integer") from None
    if number < minimum or number > maximum:
        raise AssetValidationError(f"{field}_out_of_range")
    return number


def _boolean(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise AssetValidationError(f"{field}_must_be_boolean")
    return value


def _value_mapping(category: str, value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if category == "drafts" and isinstance(value, str):
        return {"content": value}
    if category == "code_drafts" and isinstance(value, str):
        return {"code": value}
    if category == "scroll_positions" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"top": value}
    if category == "card_state" and isinstance(value, bool):
        return {"expanded": value}
    if category == "latest_diagnostic" and isinstance(value, str):
        return {"event_id": value}
    raise AssetValidationError("asset_value_must_be_object")


def _scope(value: dict[str, Any]) -> dict[str, str]:
    scope: dict[str, str] = {}
    node_id = _identifier(_first(value, "node_id", "nodeId"), field="node_id")
    resource_id = _identifier(_first(value, "resource_id", "resourceId"), field="resource_id")
    question_id = _identifier(_first(value, "question_id", "questionId"), field="question_id")
    card_id = _identifier(_first(value, "card_id", "cardId"), field="card_id")
    if node_id:
        scope["node_id"] = node_id
    if resource_id:
        scope["resource_id"] = resource_id
    if question_id:
        scope["question_id"] = question_id
    if card_id:
        scope["card_id"] = card_id
    return scope


def _require_scoped(scope: dict[str, str], *, category: str) -> None:
    if not any(scope.get(name) for name in ("node_id", "resource_id", "question_id", "card_id")):
        raise AssetValidationError(f"{category}_scope_required")


def _normalize_tutor_history(value: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    role = _as_text(_first(value, "role"), field="role", max_length=16).lower()
    if role not in {"user", "assistant"}:
        raise AssetValidationError("tutor_history_role_invalid")
    content = _as_text(_first(value, "content", "text"), field="content", max_length=24_000)
    context_type = _optional_text(_first(value, "context_type", "contextType"), field="context_type", max_length=80)
    normalized = {**scope, "role": role, "content": content}
    if context_type:
        normalized["context_type"] = context_type
    return normalized


def _normalize_draft(value: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    content = _as_text(_first(value, "content", "text", "draft"), field="content", max_length=32_000, allow_empty=True)
    kind = _optional_text(_first(value, "kind", "draft_type", "draftType"), field="kind", max_length=80)
    normalized = {**scope, "content": content}
    if kind:
        normalized["kind"] = kind
    context_type = _optional_text(
        _first(value, "context_type", "contextType"),
        field="context_type",
        max_length=80,
    )
    code_snippet = _optional_text(
        _first(value, "code_snippet", "codeSnippet"),
        field="code_snippet",
        max_length=120_000,
    )
    error_message = _optional_text(
        _first(value, "error_message", "errorMessage"),
        field="error_message",
        max_length=16_000,
    )
    if context_type:
        normalized["context_type"] = context_type
    if code_snippet:
        normalized["code_snippet"] = code_snippet
    if error_message:
        normalized["error_message"] = error_message
    return normalized


def _normalize_code_draft(value: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    code = _as_text(_first(value, "code", "content"), field="code", max_length=120_000, allow_empty=True)
    language = _optional_text(_first(value, "language"), field="language", max_length=32).lower()
    problem_id = _identifier(_first(value, "problem_id", "problemId"), field="problem_id")
    version = _identifier(
        _first(value, "version", "problem_version", "problemVersion"),
        field="version",
    )
    normalized = {**scope, "code": code}
    if language:
        normalized["language"] = language
    if problem_id:
        normalized["problem_id"] = problem_id
    if version:
        normalized["version"] = version
    for field, aliases in {
        "run_attempts": ("run_attempts", "runAttempts"),
        "submit_attempts": ("submit_attempts", "submitAttempts"),
    }.items():
        raw = _first(value, *aliases)
        if raw is not None:
            normalized[field] = _integer(
                raw,
                field=field,
                minimum=0,
                maximum=1_000_000,
            )
    return normalized


def _normalize_quiz_progress(value: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    _require_scoped(scope, category="quiz_progress")
    forbidden = {
        "score", "correct", "correctness", "correct_answers", "answer_key",
        "mastery", "mastery_delta", "result", "grading_result",
    }
    if any(name in value for name in forbidden):
        raise AssetValidationError("quiz_progress_server_result_forbidden")
    answers_raw = _first(value, "answers", "selections")
    answers = _json_value({} if answers_raw is None else answers_raw, field="answers")
    attempt_number = _integer(
        _first(value, "attempt_number", "attemptNumber") if _first(value, "attempt_number", "attemptNumber") is not None else 1,
        field="attempt_number",
        minimum=1,
    )
    used_hint_raw = _first(value, "used_hint", "usedHint")
    used_hint = _boolean(used_hint_raw, field="used_hint") if used_hint_raw is not None else False
    current_question_id = _identifier(_first(value, "question_id", "questionId", "current_question_id", "currentQuestionId"), field="question_id")
    submitted_raw = _first(value, "submitted_question_ids", "submittedQuestionIds")
    submitted_question_ids: list[str] = []
    if submitted_raw is not None:
        if not isinstance(submitted_raw, list):
            raise AssetValidationError("submitted_question_ids_must_be_list")
        if len(submitted_raw) > 500:
            raise AssetValidationError("submitted_question_ids_too_many")
        for raw_question_id in submitted_raw:
            question_id = _identifier(raw_question_id, field="submitted_question_id", required=True)
            if question_id not in submitted_question_ids:
                submitted_question_ids.append(question_id)
    normalized = {
        **scope,
        "answers": answers,
        "attempt_number": attempt_number,
        "used_hint": used_hint,
    }
    if current_question_id:
        normalized["question_id"] = current_question_id
    if submitted_raw is not None:
        normalized["submitted_question_ids"] = submitted_question_ids
    return normalized


def _normalize_annotation(value: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    _require_scoped(scope, category="annotations")
    kind = _optional_text(_first(value, "kind", "type"), field="kind", max_length=32).lower() or "note"
    if kind not in {"note", "highlight"}:
        raise AssetValidationError("annotation_kind_invalid")
    content = _optional_text(_first(value, "content", "text", "note"), field="content", max_length=32_000)
    selected_text = _optional_text(_first(value, "selected_text", "selectedText", "quote"), field="selected_text", max_length=8_000)
    if kind == "note" and not content:
        raise AssetValidationError("annotation_content_required")
    if kind == "highlight" and not selected_text and not content:
        raise AssetValidationError("highlight_text_required")
    normalized: dict[str, Any] = {**scope, "kind": kind}
    if content:
        normalized["content"] = content
    if selected_text:
        normalized["selected_text"] = selected_text
    start_raw = _first(value, "start_offset", "startOffset", "start")
    end_raw = _first(value, "end_offset", "endOffset", "end")
    if start_raw is not None:
        normalized["start_offset"] = _integer(start_raw, field="start_offset", minimum=0, maximum=10_000_000)
    if end_raw is not None:
        normalized["end_offset"] = _integer(end_raw, field="end_offset", minimum=0, maximum=10_000_000)
    if "start_offset" in normalized and "end_offset" in normalized and normalized["end_offset"] < normalized["start_offset"]:
        raise AssetValidationError("annotation_range_invalid")
    color = _optional_text(_first(value, "color"), field="color", max_length=16)
    if color:
        if not _HEX_COLOR_RE.fullmatch(color):
            raise AssetValidationError("annotation_color_invalid")
        normalized["color"] = color
    return normalized


def _normalize_bookmark(value: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    _require_scoped(scope, category="bookmarks")
    title = _optional_text(_first(value, "title", "label"), field="title", max_length=240)
    note = _optional_text(_first(value, "note", "content"), field="note", max_length=4_000)
    favorite_raw = _first(value, "favorite", "favourite")
    favorite = _boolean(favorite_raw, field="favorite") if favorite_raw is not None else True
    normalized: dict[str, Any] = {**scope, "favorite": favorite}
    if title:
        normalized["title"] = title
    if note:
        normalized["note"] = note
    return normalized


def _internal_state(state: AgentState) -> dict[str, Any]:
    """Return a usable state bag when loading a pre-assets legacy session."""
    raw = getattr(state, "internal_state", None)
    if isinstance(raw, dict):
        return raw

    repaired: dict[str, Any] = {}
    try:
        state.internal_state = repaired
    except Exception:
        # A malformed runtime object should not make a read-only restoration
        # request fail. The empty bag is intentionally not treated as evidence.
        return repaired
    return repaired


def _known_event_ids(state: AgentState) -> set[str]:
    events = _internal_state(state).get("learning_events", [])
    if not isinstance(events, list):
        return set()
    return {
        str(event.get("event_id") or "")
        for event in events
        if isinstance(event, dict) and str(event.get("event_id") or "")
    }


def _normalize_recent_learning(value: dict[str, Any], scope: dict[str, str], state: AgentState) -> dict[str, Any]:
    _require_scoped(scope, category="recent_learning")
    event_id = _identifier(_first(value, "event_id", "eventId"), field="event_id")
    if event_id and event_id not in _known_event_ids(state):
        raise AssetValidationError("recent_learning_event_not_found")
    event_type = _optional_text(_first(value, "event_type", "eventType", "activity"), field="event_type", max_length=64).lower()
    if event_type and event_type not in {
        "lesson_opened", "content_viewed", "hint_requested", "answer_selected",
        "answer_submitted", "code_run", "code_submitted", "lesson_completed",
        "review_completed", "tutor_question",
    }:
        raise AssetValidationError("recent_learning_event_type_invalid")
    duration_raw = _first(value, "duration_ms", "durationMs")
    normalized: dict[str, Any] = {**scope, "source": "client_ui"}
    if event_id:
        normalized["event_id"] = event_id
        normalized["source"] = "server_event_reference"
    if event_type:
        normalized["event_type"] = event_type
    if duration_raw is not None:
        normalized["duration_ms"] = _integer(duration_raw, field="duration_ms", minimum=0, maximum=86_400_000)
    return normalized


def _normalize_scroll_position(value: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    _require_scoped(scope, category="scroll_positions")
    top_raw = _first(value, "top", "scroll_top", "scrollTop", "position")
    if top_raw is None:
        raise AssetValidationError("scroll_top_required")
    normalized: dict[str, Any] = {**scope, "top": _number(top_raw, field="scroll_top")}
    left_raw = _first(value, "left", "scroll_left", "scrollLeft")
    if left_raw is not None:
        normalized["left"] = _number(left_raw, field="scroll_left")
    return normalized


def _normalize_card_state(value: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    _require_scoped(scope, category="card_state")
    expanded_raw = _first(value, "expanded", "is_expanded", "isExpanded")
    if expanded_raw is None:
        raise AssetValidationError("card_expanded_required")
    return {**scope, "expanded": _boolean(expanded_raw, field="expanded")}


def _diagnostic_candidates(state: AgentState) -> Iterable[dict[str, Any]]:
    internal_state = _internal_state(state)
    verified = internal_state.get("verified_completion_events", [])
    if isinstance(verified, list):
        for record in reversed(verified):
            if isinstance(record, dict):
                yield record
    events = internal_state.get("learning_events", [])
    if isinstance(events, list):
        for event in reversed(events):
            if isinstance(event, dict) and isinstance(event.get("verified_evidence"), dict):
                merged = dict(event.get("verified_evidence") or {})
                merged.setdefault("event_id", event.get("event_id", ""))
                merged.setdefault("node_id", event.get("node_id", ""))
                merged.setdefault("resource_id", event.get("resource_id", ""))
                merged.setdefault("received_at", event.get("received_at", ""))
                yield merged


def _diagnostic_metadata(state: AgentState, event_id: str = "") -> Optional[dict[str, Any]]:
    wanted = str(event_id or "").strip()
    for record in _diagnostic_candidates(state):
        candidate_event_id = str(record.get("event_id") or "").strip()
        if wanted and candidate_event_id != wanted:
            continue
        node_id = str(record.get("node_id") or "").strip()
        resource_id = str(record.get("resource_id") or "").strip()
        metadata: dict[str, Any] = {
            "event_id": candidate_event_id,
            "node_id": node_id,
            "resource_id": resource_id,
            "question_count": _safe_nonnegative_int(record.get("question_count")),
            "correct_count": _safe_nonnegative_int(record.get("correct_count")),
            "occurred_at": str(record.get("received_at") or record.get("recorded_at") or "").strip(),
            "has_diagnostic_report": bool(
                getattr(getattr(state, "dynamic_profile", None), "diagnostic_report_md", "")
            ),
            "source": "server_verified_diagnostic",
        }
        correctness = record.get("correctness")
        if isinstance(correctness, (int, float)) and not isinstance(correctness, bool):
            metadata["correctness"] = max(0.0, min(1.0, float(correctness)))
        return {key: value for key, value in metadata.items() if value not in ("", None)}
    return None


def _safe_nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _base_revision(value: object) -> Optional[int]:
    """Validate an optional optimistic-concurrency revision from the client."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise AssetValidationError("asset_base_revision_invalid")
    if isinstance(value, float) and not value.is_integer():
        raise AssetValidationError("asset_base_revision_invalid")
    if isinstance(value, str):
        value = value.strip()
        if not value or not value.isdigit():
            raise AssetValidationError("asset_base_revision_invalid")
    try:
        revision = int(value)
    except (TypeError, ValueError):
        raise AssetValidationError("asset_base_revision_invalid") from None
    if revision < 0:
        raise AssetValidationError("asset_base_revision_invalid")
    return revision


def _normalize_latest_diagnostic(value: dict[str, Any], state: AgentState) -> dict[str, Any]:
    event_id = _identifier(_first(value, "event_id", "eventId", "source_event_id", "sourceEventId"), field="event_id")
    metadata = _diagnostic_metadata(state, event_id)
    if metadata is None:
        raise AssetValidationError("latest_diagnostic_not_found")
    return metadata


def _canonical_category(value: object) -> str:
    category = _as_text(value, field="category", max_length=80).lower().replace("-", "_")
    category = _CATEGORY_ALIASES.get(category, category)
    if category not in ASSET_CATEGORIES:
        raise AssetValidationError("asset_category_invalid")
    return category


def _store(state: AgentState) -> dict[str, Any]:
    internal_state = _internal_state(state)
    raw = internal_state.get(LEARNING_ASSETS_KEY)
    if not isinstance(raw, dict):
        raw = {}
        internal_state[LEARNING_ASSETS_KEY] = raw
    raw["version"] = LEARNING_ASSETS_VERSION
    revision = raw.get("revision", 0)
    raw["revision"] = _safe_nonnegative_int(revision)
    categories = raw.get("categories")
    if not isinstance(categories, dict):
        categories = {}
        raw["categories"] = categories
    for category in ASSET_CATEGORIES:
        if not isinstance(categories.get(category), dict):
            categories[category] = {}
    return raw


def _identity_error(state: AgentState, user_id: str, course_id: str) -> Optional[dict[str, Any]]:
    if state.user_id != user_id or state.course_id != course_id:
        return {
            "status": "session_identity_mismatch",
            "status_code": 409,
        }
    return None


def _normalize_value(category: str, value: object, state: AgentState) -> dict[str, Any]:
    mapping = _value_mapping(category, value)
    if _contains_secret(mapping):
        raise AssetValidationError("asset_sensitive_value_forbidden")
    # These identity fields are deliberately not copied from browser payloads.
    if any(name in mapping for name in ("user_id", "userId", "course_id", "courseId")):
        raise AssetValidationError("asset_identity_fields_forbidden")
    scope = _scope(mapping)
    if category == "tutor_history":
        return _normalize_tutor_history(mapping, scope)
    if category == "drafts":
        return _normalize_draft(mapping, scope)
    if category == "code_drafts":
        return _normalize_code_draft(mapping, scope)
    if category == "quiz_progress":
        return _normalize_quiz_progress(mapping, scope)
    if category == "annotations":
        return _normalize_annotation(mapping, scope)
    if category == "bookmarks":
        return _normalize_bookmark(mapping, scope)
    if category == "recent_learning":
        return _normalize_recent_learning(mapping, scope, state)
    if category == "scroll_positions":
        return _normalize_scroll_position(mapping, scope)
    if category == "card_state":
        return _normalize_card_state(mapping, scope)
    return _normalize_latest_diagnostic(mapping, state)


def _touch(store: dict[str, Any]) -> None:
    store["revision"] = _safe_nonnegative_int(store.get("revision")) + 1
    store["updated_at"] = _now()


def _persist_asset_mutation(
    session: Any,
    previous_store: dict[str, Any],
) -> dict[str, Any] | None:
    """Rollback and report a retryable error when no durable write succeeds."""
    try:
        result = persist_session(session)
    except Exception:
        result = {"durable": False}
    if not isinstance(result, dict) or result.get("durable") is not False:
        return None
    session.agent_state.internal_state[LEARNING_ASSETS_KEY] = previous_store
    return {
        "status": "asset_persistence_failed",
        "status_code": 503,
        "reason": "asset_persistence_failed",
        "retryable": True,
        "revision": _safe_nonnegative_int(previous_store.get("revision")),
    }


def _prune(entries: dict[str, Any], category: str) -> None:
    limit = _MAX_ENTRIES[category]
    if category == "latest_diagnostic":
        entries_keys = [key for key in entries if key != "latest"]
        for key in entries_keys:
            entries.pop(key, None)
        return
    excess = len(entries) - limit
    if excess <= 0:
        return
    ordered = sorted(
        entries,
        key=lambda key: str(entries[key].get("updated_at", "")) if isinstance(entries.get(key), dict) else "",
    )
    for key in ordered[:excess]:
        entries.pop(key, None)


def _matches_scope(entry: object, node_id: str, resource_id: str) -> bool:
    if not isinstance(entry, dict):
        return False
    if node_id and entry.get("node_id") != node_id:
        return False
    if resource_id and entry.get("resource_id") != resource_id:
        return False
    return True


def _assets_response(
    state: AgentState,
    user_id: str,
    course_id: str,
    *,
    node_id: str = "",
    resource_id: str = "",
    categories: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    store = _store(state)
    requested = tuple(categories) if categories is not None else ASSET_CATEGORIES
    output: dict[str, dict[str, Any]] = {}
    raw_categories = store["categories"]
    for category in requested:
        raw_entries = raw_categories.get(category, {})
        if not isinstance(raw_entries, dict):
            raw_entries = {}
        entries: dict[str, Any] = {}
        # Old browser state can contain mixed key types. Filter before sorting
        # so a legacy integer/object key cannot raise while comparing it to a
        # string key, and omit records that cannot be safely copied.
        valid_items = [
            (key, entry)
            for key, entry in raw_entries.items()
            if isinstance(key, str) and _matches_scope(entry, node_id, resource_id)
        ]
        for key, entry in sorted(valid_items, key=lambda item: item[0]):
            try:
                entries[key] = _copy(entry)
            except Exception:
                continue
        # Existing sessions may have verified diagnostics from before the
        # restoration-assets schema was introduced. Surface a read-only,
        # redacted summary on first read without inventing client evidence.
        if (
            category == "latest_diagnostic"
            and not entries
            and not store.get("latest_diagnostic_deleted_at")
        ):
            derived = _diagnostic_metadata(state)
            if derived is not None and _matches_scope(derived, node_id, resource_id):
                entries["latest"] = derived
        output[category] = entries
    # The two timeline categories are naturally rendered as ordered lists.
    # Keep the canonical keyed map above for conflict-free upserts, while
    # exposing a lossless list mirror for store implementations that model
    # histories as arrays.
    asset_lists: dict[str, list[dict[str, Any]]] = {}
    for category in ("tutor_history", "recent_learning"):
        if category not in output:
            continue
        asset_lists[category] = [
            {"key": key, **_copy(entry)}
            for key, entry in sorted(
                output[category].items(),
                key=lambda item: (
                    str(item[1].get("created_at", "")),
                    item[0],
                ),
            )
        ]
    return {
        "status": "ok",
        "user_id": user_id,
        "course_id": course_id,
        "revision": store["revision"],
        "updated_at": store.get("updated_at"),
        "scope": {
            "node_id": node_id or None,
            "resource_id": resource_id or None,
        },
        "assets": output,
        "asset_lists": asset_lists,
    }


def _parse_categories(categories: Optional[Iterable[object]]) -> tuple[str, ...]:
    if categories is None:
        return ASSET_CATEGORIES
    canonical: list[str] = []
    for raw in categories:
        category = _canonical_category(raw)
        if category not in canonical:
            canonical.append(category)
    return tuple(canonical) or ASSET_CATEGORIES


def get_learning_assets(
    user_id: str,
    course_id: str = "data_structures",
    *,
    node_id: object = "",
    resource_id: object = "",
    categories: Optional[Iterable[object]] = None,
) -> dict[str, Any]:
    """Return only assets belonging to one authenticated user-course session."""
    try:
        normalized_node = _identifier(node_id, field="node_id")
        normalized_resource = _identifier(resource_id, field="resource_id")
        normalized_categories = _parse_categories(categories)
    except AssetValidationError as exc:
        return {"status": "invalid_asset_query", "status_code": 422, "reason": str(exc)}

    with _asset_lock(user_id, course_id):
        session = get_session(user_id, course_id)
        identity_error = _identity_error(session.agent_state, user_id, course_id)
        if identity_error is not None:
            return identity_error
        return _assets_response(
            session.agent_state,
            user_id,
            course_id,
            node_id=normalized_node,
            resource_id=normalized_resource,
            categories=normalized_categories,
        )


def patch_learning_asset(
    user_id: str,
    course_id: str,
    *,
    category: object,
    key: object,
    value: object = None,
    delete: object = False,
    base_revision: object = None,
) -> dict[str, Any]:
    """Upsert or delete one scoped UI asset and persist the owning session."""
    try:
        normalized_category = _canonical_category(category)
        normalized_key = _asset_key(key)
        if not isinstance(delete, bool):
            raise AssetValidationError("asset_delete_must_be_boolean")
        if normalized_key == "__all__" and normalized_category not in {"tutor_history", "recent_learning"}:
            raise AssetValidationError("asset_replace_all_not_supported")
        normalized_base_revision = _base_revision(base_revision)
    except AssetValidationError as exc:
        return {"status": "invalid_asset", "status_code": 422, "reason": str(exc)}

    with _asset_lock(user_id, course_id):
        session = get_session(user_id, course_id)
        state = session.agent_state
        identity_error = _identity_error(state, user_id, course_id)
        if identity_error is not None:
            return identity_error
        store = _store(state)
        previous_store = _copy(store)
        if normalized_category in SERVER_MANAGED_ASSET_CATEGORIES:
            return {
                "status": "asset_read_only",
                "status_code": 403,
                "reason": "asset_category_server_managed",
                "category": normalized_category,
            }
        if (
            normalized_base_revision is not None
            and normalized_base_revision != store["revision"]
        ):
            response = _assets_response(state, user_id, course_id)
            response.update({
                "status": "asset_conflict",
                "status_code": 409,
                "reason": "asset_revision_conflict",
                "expected_revision": normalized_base_revision,
            })
            return response
        entries = store["categories"][normalized_category]

        if normalized_category == "latest_diagnostic":
            normalized_key = "latest"

        if delete:
            if normalized_key == "__all__":
                removed = bool(entries)
                entries.clear()
            else:
                removed = entries.pop(normalized_key, None) is not None
            if normalized_category == "latest_diagnostic":
                # Deleting a presentation asset must not erase the verified
                # event ledger; it simply suppresses the cached summary until
                # the next verified diagnostic is recorded.
                store["latest_diagnostic_deleted_at"] = _now()
                removed = True
            if removed:
                _touch(store)
                persistence_error = _persist_asset_mutation(session, previous_store)
                if persistence_error is not None:
                    return persistence_error
            response = _assets_response(state, user_id, course_id)
            response.update({
                "operation": "delete",
                "category": normalized_category,
                "key": normalized_key,
                "deleted": removed,
            })
            return response

        if normalized_key == "__all__":
            if not isinstance(value, list):
                return {
                    "status": "invalid_asset",
                    "status_code": 422,
                    "reason": "asset_replace_all_value_must_be_array",
                }
            if len(value) > _MAX_ENTRIES[normalized_category]:
                return {
                    "status": "invalid_asset",
                    "status_code": 422,
                    "reason": "asset_replace_all_too_many_items",
                }
            replacement: dict[str, dict[str, Any]] = {}
            try:
                for index, raw_item in enumerate(value):
                    if not isinstance(raw_item, dict):
                        raise AssetValidationError("asset_replace_all_item_must_be_object")
                    item = dict(raw_item)
                    supplied_key = item.pop("key", item.pop("id", ""))
                    if supplied_key:
                        item_key = _identifier(supplied_key, field="asset_key", required=True)
                    elif normalized_category == "recent_learning" and item.get("event_id"):
                        item_key = _identifier(item.get("event_id"), field="asset_key", required=True)
                    else:
                        item_key = f"{normalized_category}:{uuid4().hex}:{index}"
                    if item_key in replacement:
                        raise AssetValidationError("asset_replace_all_duplicate_key")
                    normalized_item = _normalize_value(normalized_category, item, state)
                    existing = entries.get(item_key)
                    normalized_item["created_at"] = (
                        existing.get("created_at")
                        if isinstance(existing, dict)
                        else _now()
                    )
                    normalized_item["updated_at"] = _now()
                    replacement[item_key] = normalized_item
            except AssetValidationError as exc:
                return {"status": "invalid_asset", "status_code": 422, "reason": str(exc)}
            entries.clear()
            entries.update(replacement)
            _touch(store)
            persistence_error = _persist_asset_mutation(session, previous_store)
            if persistence_error is not None:
                return persistence_error
            response = _assets_response(state, user_id, course_id)
            response.update({
                "operation": "replace_all",
                "category": normalized_category,
                "key": normalized_key,
                "asset_count": len(replacement),
            })
            return response

        try:
            normalized_value = _normalize_value(normalized_category, value, state)
        except AssetValidationError as exc:
            return {"status": "invalid_asset", "status_code": 422, "reason": str(exc)}

        if normalized_category == "latest_diagnostic":
            entries.clear()
            store.pop("latest_diagnostic_deleted_at", None)
        existing = entries.get(normalized_key)
        created_at = existing.get("created_at") if isinstance(existing, dict) else None
        normalized_value["created_at"] = created_at or _now()
        normalized_value["updated_at"] = _now()
        entries[normalized_key] = normalized_value
        _prune(entries, normalized_category)
        _touch(store)
        persistence_error = _persist_asset_mutation(session, previous_store)
        if persistence_error is not None:
            return persistence_error
        response = _assets_response(state, user_id, course_id)
        response.update({
            "operation": "upsert",
            "category": normalized_category,
            "key": normalized_key,
            "asset": _copy(normalized_value),
        })
        return response


def _append_server_asset(
    state: AgentState,
    category: str,
    key: str,
    value: dict[str, Any],
) -> None:
    """Append trusted server output without exposing this as a browser write path."""
    store = _store(state)
    entries = store["categories"][category]
    existing = entries.get(key)
    entry = _copy(value)
    entry["created_at"] = existing.get("created_at") if isinstance(existing, dict) else _now()
    entry["updated_at"] = _now()
    entries[key] = entry
    if category == "latest_diagnostic":
        store.pop("latest_diagnostic_deleted_at", None)
    _prune(entries, category)
    _touch(store)


def record_learning_event_asset(state: AgentState, event_record: dict[str, Any]) -> None:
    """Mirror a real server-recorded learning event into recent-learning state.

    This is deliberately a compact navigation/resume record.  It does not
    copy answers, client scores, or any mastery values, so it cannot become an
    alternate evidence channel.
    """
    if not isinstance(event_record, dict):
        return
    event_id = str(event_record.get("event_id") or "").strip()
    if not event_id or not _ID_RE.fullmatch(event_id):
        return
    with _asset_lock(state.user_id, state.course_id):
        value: dict[str, Any] = {
            "event_id": event_id,
            "event_type": str(event_record.get("event_type") or "").strip(),
            "source": "server_event",
            "occurred_at": str(event_record.get("received_at") or _now()).strip(),
        }
        for field in ("node_id", "resource_id", "question_id"):
            raw = str(event_record.get(field) or "").strip()
            if raw and _ID_RE.fullmatch(raw):
                value[field] = raw
        duration = event_record.get("duration_ms")
        if isinstance(duration, int) and not isinstance(duration, bool):
            value["duration_ms"] = max(0, min(duration, 86_400_000))
        _append_server_asset(state, "recent_learning", event_id, value)

        # A diagnostic summary is only copied from server-verified evidence.
        if isinstance(event_record.get("verified_evidence"), dict):
            metadata = _diagnostic_metadata(state, event_id)
            if metadata is not None:
                _append_server_asset(state, "latest_diagnostic", "latest", metadata)


def record_tutor_exchange_asset(
    state: AgentState,
    *,
    question: object,
    response: object,
    context_type: object = "",
) -> None:
    """Persist a validated user/assistant exchange after a tutor response.

    System prompts, provider credentials, raw code execution data, and blocked
    responses are intentionally excluded.  A detected secret skips the whole
    exchange rather than persisting or redacting sensitive text silently.
    """
    if not isinstance(response, dict) or response.get("blocked"):
        return
    question_text = str(question or "").strip()
    answer_text = str(response.get("text_explanation") or "").strip()
    if not question_text or not answer_text or _contains_secret(question_text) or _contains_secret(answer_text):
        return
    with _asset_lock(state.user_id, state.course_id):
        context = str(context_type or "").strip()[:80]
        scope: dict[str, Any] = {}
        node_id = str(state.current_node_id or "").strip()
        if node_id and _ID_RE.fullmatch(node_id):
            scope["node_id"] = node_id
        created_at = _now()
        nonce = uuid4().hex
        user_entry = {
            **scope,
            "role": "user",
            "content": question_text[:24_000],
            "source": "server_tutor",
            "exchange_id": nonce,
            "sequence": 0,
            "created_at": created_at,
        }
        assistant_entry = {
            **scope,
            "role": "assistant",
            "content": answer_text[:24_000],
            "source": "server_tutor",
            "exchange_id": nonce,
            "sequence": 1,
            "created_at": created_at,
        }
        if context:
            user_entry["context_type"] = context
            assistant_entry["context_type"] = context
        _append_server_asset(state, "tutor_history", f"tutor:{nonce}:user", user_entry)
        _append_server_asset(state, "tutor_history", f"tutor:{nonce}:assistant", assistant_entry)
