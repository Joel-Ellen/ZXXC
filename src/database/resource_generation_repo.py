# -*- coding: utf-8 -*-
"""Durable coordination storage for incremental resource generation.

The main learning persistence path uses the synchronous PostgreSQL layer in
this package.  This repository deliberately follows that convention instead
of the optional async SQLAlchemy models so callers can use it from resource
generation workers without introducing a second source of truth.

In development and tests a shared in-memory store is used when PostgreSQL is
unavailable.  Production keeps the failure visible because generation jobs and
their event history must be durable for reconnecting SSE clients.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

try:
    import psycopg2
except ImportError:  # Keep the repository importable for memory fallback tests.
    class _PsycopgUnavailable:
        class IntegrityError(Exception):
            pass

    psycopg2 = _PsycopgUnavailable()  # type: ignore[assignment]

from .connection import db, is_production_environment
from src.resource_events import notifier as resource_event_notifier


DEFAULT_LOCALE = "zh-CN"
ACTIVE_JOB_STATUSES = frozenset({
    "queued",
    "running",
    "retrying",
    "retrieving",
    "blueprint",
    "concept",
    "supporting",
    "validating",
    "repairing",
})
TERMINAL_JOB_STATUSES = frozenset({"completed", "partial", "failed", "cancelled"})
PIPELINE_STATES = (
    "queued",
    "retrieving",
    "blueprint",
    "concept",
    "supporting",
    "validating",
    "repairing",
    "completed",
    "partial",
    "failed",
    "cancelled",
)
PRIORITY_VALUES = {
    "concept_map": 100,
    "concept": 100,
    "repair": 80,
    "supporting_bundle": 50,
    "supporting": 50,
    "shadow": 10,
    "normal": 50,
    "interactive": 50,
    "legacy_sync": 50,
}
DEFAULT_LEASE_SECONDS = 60
MAX_ACTIVE_JOBS_PER_USER = 2
QUEUE_SOFT_LIMIT = 4_000
QUEUE_HARD_LIMIT = 5_000

# PostgreSQL advisory locks are scoped to a database session and automatically
# disappear if a worker process loses its connection.  Keeping the namespace
# constant makes the slots shared by every application instance while avoiding
# collisions with unrelated advisory-lock users in the same database.
_RESOURCE_GENERATION_ADVISORY_NAMESPACE = 1_177_184_338
_MAX_GENERATION_CONCURRENCY_SLOTS = 256


class ResourceAdmissionError(RuntimeError):
    """A durable queue admission decision safe to map to an HTTP response."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        retry_after: int,
        queue_depth: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = int(status_code)
        self.retry_after = max(1, int(retry_after))
        self.queue_depth = (
            max(0, int(queue_depth))
            if queue_depth is not None
            else None
        )

    def response_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "error": str(self),
            "error_code": self.code,
            "status_code": self.status_code,
            "retry_after": self.retry_after,
        }
        if self.queue_depth is not None:
            payload["queue_depth"] = self.queue_depth
        return payload


@dataclass(frozen=True)
class ResourceGenerationSlotLease:
    """A non-blocking global generation slot held by the current worker.

    PostgreSQL leases must be released from the same worker thread that
    acquired them because ``Database`` owns a thread-local connection.  The
    in-memory lease additionally carries an owner token so an unrelated test
    worker cannot release another worker's slot.
    """

    slot: int
    backend: str
    owner_id: str


def _slot_candidates(max_concurrency: int, *, concept_priority: bool) -> Tuple[int, ...]:
    """Return eligible global slots while reserving one for concept maps."""
    safe_max = max(1, min(_MAX_GENERATION_CONCURRENCY_SLOTS, int(max_concurrency)))
    if safe_max == 1:
        return (0,)
    # Supporting bundles deliberately cannot take slot zero.  Concept jobs can
    # use every slot, retaining the existing first-visible-resource priority
    # even when several application instances share the same PostgreSQL DB.
    return tuple(range(safe_max)) if concept_priority else tuple(range(1, safe_max))


def _admission_lock_key(value: str) -> int:
    """Return a stable signed int32 key for PostgreSQL two-key advisory locks."""
    raw = int.from_bytes(
        hashlib.sha256(str(value).encode("utf-8")).digest()[:4],
        "big",
        signed=False,
    )
    return raw if raw < 2**31 else raw - 2**32


RESOURCE_GENERATION_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS resource_generation_jobs (
    job_id                  VARCHAR(64) PRIMARY KEY,
    user_id                 VARCHAR(64) NOT NULL,
    course_id               VARCHAR(128) NOT NULL,
    node_id                 VARCHAR(128) NOT NULL,
    idempotency_key         VARCHAR(192) NOT NULL,
    card_types              JSONB NOT NULL DEFAULT '[]'::jsonb,
    force                   BOOLEAN NOT NULL DEFAULT FALSE,
    priority                VARCHAR(32) NOT NULL DEFAULT 'normal',
    status                  VARCHAR(32) NOT NULL DEFAULT 'queued',
    progress                JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_json              JSONB,
    request_params          JSONB NOT NULL DEFAULT '{}'::jsonb,
    retry_count             INTEGER NOT NULL DEFAULT 0,
    max_retries             INTEGER NOT NULL DEFAULT 0,
    content_version         VARCHAR(128) NOT NULL DEFAULT '1',
    knowledge_index_version VARCHAR(128) NOT NULL DEFAULT '',
    locale                  VARCHAR(32) NOT NULL DEFAULT 'zh-CN',
    created_at              VARCHAR(64) NOT NULL,
    updated_at              VARCHAR(64) NOT NULL,
    started_at              VARCHAR(64),
    completed_at            VARCHAR(64),
    failed_at               VARCHAR(64)
);

ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS pipeline_version VARCHAR(64) NOT NULL DEFAULT 'resource-v3';
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(64) NOT NULL DEFAULT 'resource-v3';
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS blueprint_version VARCHAR(64) NOT NULL DEFAULT 'resource-v3';
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS quality_version VARCHAR(64) NOT NULL DEFAULT 'resource-v3';
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS priority_value INTEGER NOT NULL DEFAULT 50;
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS pipeline_state VARCHAR(32) NOT NULL DEFAULT 'queued';
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS deadline_at VARCHAR(64);
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS lease_owner VARCHAR(128);
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS lease_expires_at VARCHAR(64);
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS heartbeat_at VARCHAR(64);
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS token_budget_input INTEGER NOT NULL DEFAULT 45000;
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS token_budget_output INTEGER NOT NULL DEFAULT 12000;
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS cost_budget_microunits BIGINT NOT NULL DEFAULT 0;
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS generation_call_budget INTEGER NOT NULL DEFAULT 8;
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS exposure_mode VARCHAR(32) NOT NULL DEFAULT 'normal';
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS release_version VARCHAR(128) NOT NULL DEFAULT '';
ALTER TABLE resource_generation_jobs ADD COLUMN IF NOT EXISTS cohort VARCHAR(64) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_resource_generation_jobs_user_node
    ON resource_generation_jobs (user_id, course_id, node_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_resource_generation_jobs_status
    ON resource_generation_jobs (status, updated_at);
CREATE INDEX IF NOT EXISTS idx_resource_generation_jobs_queue
    ON resource_generation_jobs (priority_value DESC, created_at ASC)
    WHERE status IN ('queued', 'retrying');
CREATE INDEX IF NOT EXISTS idx_resource_generation_jobs_lease
    ON resource_generation_jobs (lease_expires_at)
    WHERE status NOT IN ('completed', 'partial', 'failed', 'cancelled');
CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_generation_jobs_active_request
    ON resource_generation_jobs (user_id, course_id, node_id, idempotency_key)
    WHERE status NOT IN ('completed', 'partial', 'failed', 'cancelled');

CREATE TABLE IF NOT EXISTS resource_generation_job_events (
    event_id    BIGSERIAL PRIMARY KEY,
    job_id      VARCHAR(64) NOT NULL REFERENCES resource_generation_jobs(job_id) ON DELETE CASCADE,
    event_type  VARCHAR(32) NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resource_generation_job_events_job_event
    ON resource_generation_job_events (job_id, event_id);

CREATE TABLE IF NOT EXISTS resource_generation_cards (
    card_id             BIGSERIAL PRIMARY KEY,
    job_id              VARCHAR(64) NOT NULL REFERENCES resource_generation_jobs(job_id) ON DELETE CASCADE,
    card_type           VARCHAR(64) NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'queued',
    state_version       INTEGER NOT NULL DEFAULT 1,
    payload             JSONB,
    quality_result      JSONB NOT NULL DEFAULT '{}'::jsonb,
    blueprint_snapshot  JSONB NOT NULL DEFAULT '{}'::jsonb,
    publication_version VARCHAR(128) NOT NULL DEFAULT '',
    content_hash        VARCHAR(64) NOT NULL DEFAULT '',
    degraded_reason     VARCHAR(128),
    created_at          VARCHAR(64) NOT NULL,
    updated_at          VARCHAR(64) NOT NULL,
    published_at        VARCHAR(64),
    UNIQUE (job_id, card_type)
);

CREATE INDEX IF NOT EXISTS idx_resource_generation_cards_job_status
    ON resource_generation_cards (job_id, status);

CREATE TABLE IF NOT EXISTS resource_generation_attempts (
    attempt_id       BIGSERIAL PRIMARY KEY,
    job_id           VARCHAR(64) NOT NULL REFERENCES resource_generation_jobs(job_id) ON DELETE CASCADE,
    card_type        VARCHAR(64) NOT NULL,
    operation        VARCHAR(64) NOT NULL,
    provider         VARCHAR(64) NOT NULL DEFAULT '',
    model            VARCHAR(128) NOT NULL DEFAULT '',
    input_tokens     INTEGER NOT NULL DEFAULT 0,
    output_tokens    INTEGER NOT NULL DEFAULT 0,
    elapsed_ms       DOUBLE PRECISION NOT NULL DEFAULT 0,
    issue_code       VARCHAR(128) NOT NULL DEFAULT '',
    artifact_version VARCHAR(128) NOT NULL DEFAULT '',
    content_hash     VARCHAR(64) NOT NULL DEFAULT '',
    created_at       VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resource_generation_attempts_job
    ON resource_generation_attempts (job_id, created_at);

CREATE TABLE IF NOT EXISTS resource_quality_evaluations (
    evaluation_id   BIGSERIAL PRIMARY KEY,
    job_id          VARCHAR(64) NOT NULL REFERENCES resource_generation_jobs(job_id) ON DELETE CASCADE,
    card_type       VARCHAR(64) NOT NULL,
    quality_version VARCHAR(64) NOT NULL,
    gate_status     VARCHAR(32) NOT NULL,
    score           DOUBLE PRECISION NOT NULL DEFAULT 0,
    dimensions      JSONB NOT NULL DEFAULT '{}'::jsonb,
    issue_codes     JSONB NOT NULL DEFAULT '[]'::jsonb,
    artifact_digest VARCHAR(128) NOT NULL DEFAULT '',
    content_hash    VARCHAR(64) NOT NULL DEFAULT '',
    created_at      VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resource_quality_evaluations_job
    ON resource_quality_evaluations (job_id, card_type, created_at DESC);

CREATE TABLE IF NOT EXISTS resource_base_cache (
    course_id               VARCHAR(128) NOT NULL,
    node_id                 VARCHAR(128) NOT NULL,
    resource_type           VARCHAR(64) NOT NULL,
    content_version         VARCHAR(128) NOT NULL,
    locale                  VARCHAR(32) NOT NULL DEFAULT 'zh-CN',
    knowledge_index_version VARCHAR(128) NOT NULL DEFAULT '',
    payload                 JSONB NOT NULL,
    source_refs             JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              VARCHAR(64) NOT NULL,
    updated_at              VARCHAR(64) NOT NULL,
    PRIMARY KEY (
        course_id, node_id, resource_type, content_version, locale, knowledge_index_version
    )
);

CREATE INDEX IF NOT EXISTS idx_resource_base_cache_lookup
    ON resource_base_cache (course_id, node_id, resource_type, updated_at DESC);

CREATE TABLE IF NOT EXISTS resource_personalization_cache (
    user_id                 VARCHAR(64) NOT NULL,
    course_id               VARCHAR(128) NOT NULL,
    node_id                 VARCHAR(128) NOT NULL,
    resource_type           VARCHAR(64) NOT NULL,
    mastery_bucket          VARCHAR(64) NOT NULL,
    error_signature         VARCHAR(256) NOT NULL DEFAULT '',
    cognitive_style         VARCHAR(64) NOT NULL DEFAULT '',
    content_version         VARCHAR(128) NOT NULL,
    locale                  VARCHAR(32) NOT NULL DEFAULT 'zh-CN',
    knowledge_index_version VARCHAR(128) NOT NULL DEFAULT '',
    payload                 JSONB NOT NULL,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              VARCHAR(64) NOT NULL,
    updated_at              VARCHAR(64) NOT NULL,
    PRIMARY KEY (
        user_id, course_id, node_id, resource_type, mastery_bucket,
        error_signature, cognitive_style, content_version, locale, knowledge_index_version
    )
);

CREATE INDEX IF NOT EXISTS idx_resource_personalization_cache_lookup
    ON resource_personalization_cache (
        user_id, course_id, node_id, resource_type, updated_at DESC
    );
"""


_UNSET = object()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_utc_timestamp(value: Any) -> Optional[datetime]:
    """Parse persisted ISO timestamps for the in-memory recovery path."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return copy.deepcopy(default)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return copy.deepcopy(default)
    return copy.deepcopy(value)


def _card_types(value: Optional[Iterable[str]]) -> List[str]:
    if value is None:
        return []
    values = [value] if isinstance(value, str) else value
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _normalise_job(row: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    result = dict(row)
    result["card_types"] = _json_value(result.get("card_types"), [])
    result["progress"] = _json_value(result.get("progress"), {})
    result["request_params"] = _json_value(result.get("request_params"), {})
    result["error"] = _json_value(result.pop("error_json", result.get("error")), None)
    result.setdefault("pipeline_state", result.get("status", "queued"))
    result.setdefault("priority_value", PRIORITY_VALUES.get(str(result.get("priority") or "normal"), 50))
    return result


def _normalise_event(row: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(row)
    result["payload"] = _json_value(result.get("payload"), {})
    result.setdefault("event", result.get("event_type", ""))
    return result


def _normalise_cache(row: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    result = dict(row)
    result["payload"] = _json_value(result.get("payload"), {})
    result["metadata"] = _json_value(result.get("metadata"), {})
    if "source_refs" in result:
        result["source_refs"] = _json_value(result.get("source_refs"), [])
    return result


class _MemoryGenerationStore:
    """A process-local implementation used only when durable storage is absent."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.events: Dict[str, List[Dict[str, Any]]] = {}
        self.cards: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.attempts: List[Dict[str, Any]] = []
        self.quality_evaluations: List[Dict[str, Any]] = []
        self.base_cache: Dict[Tuple[str, str, str, str, str, str], Dict[str, Any]] = {}
        self.personal_cache: Dict[Tuple[str, str, str, str, str, str, str, str, str, str], Dict[str, Any]] = {}
        self.generation_slots: Dict[int, str] = {}
        self.next_event_id = 1

    def try_acquire_generation_slot(
        self,
        max_concurrency: int,
        *,
        concept_priority: bool,
        owner_id: str,
    ) -> Optional[ResourceGenerationSlotLease]:
        """Acquire a process-local slot for development and unit tests."""
        with self.lock:
            for slot in _slot_candidates(max_concurrency, concept_priority=concept_priority):
                if slot not in self.generation_slots:
                    self.generation_slots[slot] = owner_id
                    return ResourceGenerationSlotLease(slot, "memory", owner_id)
        return None

    def release_generation_slot(self, lease: ResourceGenerationSlotLease) -> bool:
        if lease.backend != "memory":
            return False
        with self.lock:
            if self.generation_slots.get(lease.slot) != lease.owner_id:
                return False
            self.generation_slots.pop(lease.slot, None)
            return True

    @staticmethod
    def _active_match(
        job: Mapping[str, Any],
        user_id: str,
        course_id: str,
        node_id: str,
        idempotency_key: str,
    ) -> bool:
        return (
            job.get("user_id") == user_id
            and job.get("course_id") == course_id
            and job.get("node_id") == node_id
            and job.get("idempotency_key") == idempotency_key
            and job.get("status") in ACTIVE_JOB_STATUSES
        )

    def create_or_get_active_job(
        self,
        record: Dict[str, Any],
        *,
        enforce_admission: bool = False,
        concept_lane: bool = False,
    ) -> Tuple[Dict[str, Any], bool]:
        with self.lock:
            for existing in self.jobs.values():
                if self._active_match(
                    existing,
                    record["user_id"],
                    record["course_id"],
                    record["node_id"],
                    record["idempotency_key"],
                ):
                    return copy.deepcopy(existing), False
            if enforce_admission:
                queued = [
                    job
                    for job in self.jobs.values()
                    if job.get("status") in {"queued", "retrying"}
                ]
                queue_depth = len(queued)
                low_priority = (
                    record.get("exposure_mode") == "shadow"
                    or record.get("priority")
                    in {"shadow", "supporting", "supporting_bundle"}
                )
                if queue_depth >= QUEUE_HARD_LIMIT and not concept_lane:
                    raise ResourceAdmissionError(
                        "resource_queue_full",
                        "Resource generation queue is temporarily full.",
                        status_code=503,
                        retry_after=30,
                        queue_depth=queue_depth,
                    )
                if queue_depth >= QUEUE_SOFT_LIMIT and low_priority:
                    raise ResourceAdmissionError(
                        "resource_low_priority_paused",
                        "Low-priority resource generation is temporarily paused.",
                        status_code=503,
                        retry_after=15,
                        queue_depth=queue_depth,
                    )
                active_for_user = sum(
                    job.get("user_id") == record["user_id"]
                    and job.get("status") not in TERMINAL_JOB_STATUSES
                    for job in self.jobs.values()
                )
                if active_for_user >= MAX_ACTIVE_JOBS_PER_USER:
                    raise ResourceAdmissionError(
                        "resource_user_active_limit",
                        "At most two resource generation jobs may be active per learner.",
                        status_code=429,
                        retry_after=5,
                    )
            self.jobs[record["job_id"]] = copy.deepcopy(record)
            self.events.setdefault(record["job_id"], [])
            self._append_event_locked(
                record["job_id"],
                "queued",
                {
                    "status": "queued",
                    "requested_card_types": list(record["card_types"]),
                },
            )
            return copy.deepcopy(record), True

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            job = self.jobs.get(job_id)
            return copy.deepcopy(job) if job is not None else None

    def get_active_job(
        self,
        user_id: str,
        course_id: str,
        node_id: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        with self.lock:
            matches = [
                job for job in self.jobs.values()
                if self._active_match(job, user_id, course_id, node_id, idempotency_key)
            ]
            if not matches:
                return None
            matches.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("job_id", ""))), reverse=True)
            return copy.deepcopy(matches[0])

    def update_job(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[Mapping[str, Any]] = None,
        error: Any = _UNSET,
        retry_count: Optional[int] = None,
        max_retries: Optional[int] = None,
        merge_progress: bool = True,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self.lock:
            record = self.jobs.get(job_id)
            if (
                record is None
                or (
                    owner_id
                    and str(record.get("lease_owner") or "") != owner_id
                )
            ):
                return None
            now = _now()
            if status is not None:
                record["status"] = str(status)
                if status in PIPELINE_STATES:
                    record["pipeline_state"] = status
                if status == "running" and not record.get("started_at"):
                    record["started_at"] = now
                elif status in {"completed", "partial", "cancelled"}:
                    record["completed_at"] = now
                elif status == "failed":
                    record["failed_at"] = now
                if status in TERMINAL_JOB_STATUSES:
                    record["lease_owner"] = None
                    record["lease_expires_at"] = None
            if progress is not None:
                if merge_progress:
                    merged = dict(record.get("progress") or {})
                    merged.update(copy.deepcopy(dict(progress)))
                    record["progress"] = merged
                else:
                    record["progress"] = copy.deepcopy(dict(progress))
            if error is not _UNSET:
                record["error"] = copy.deepcopy(error)
            if retry_count is not None:
                record["retry_count"] = int(retry_count)
            if max_retries is not None:
                record["max_retries"] = int(max_retries)
            record["updated_at"] = now
            return copy.deepcopy(record)

    def claim_job(
        self,
        job_id: str,
        *,
        owner_id: Optional[str] = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> Optional[Dict[str, Any]]:
        with self.lock:
            record = self.jobs.get(job_id)
            if record is None or record.get("status") not in {"queued", "retrying"}:
                return None
            now = _now()
            record["status"] = "running"
            record["pipeline_state"] = "retrieving"
            record["started_at"] = record.get("started_at") or now
            record["updated_at"] = now
            record["lease_owner"] = owner_id
            record["lease_expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=max(1, int(lease_seconds)))
            ).isoformat() if owner_id else None
            record["heartbeat_at"] = now if owner_id else None
            payload = {"status": "running"}
            if owner_id:
                payload["lease_owner"] = owner_id
            self._append_event_locked(job_id, "running", payload)
            return copy.deepcopy(record)

    def claim_next_job(
        self,
        owner_id: str,
        *,
        lease_seconds: int,
        include_shadow: bool,
    ) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        with self.lock:
            candidates = [
                record
                for record in self.jobs.values()
                if record.get("status") in {"queued", "retrying"}
                and (include_shadow or record.get("exposure_mode") != "shadow")
            ]
            candidates.sort(
                key=lambda item: (
                    -int(item.get("priority_value") or 0),
                    str(item.get("created_at") or ""),
                    str(item.get("job_id") or ""),
                )
            )
            if not candidates:
                return None
            record = candidates[0]
            now_text = now.isoformat()
            record.update({
                "status": "running",
                "pipeline_state": "retrieving",
                "lease_owner": owner_id,
                "lease_expires_at": (now + timedelta(seconds=lease_seconds)).isoformat(),
                "heartbeat_at": now_text,
                "started_at": record.get("started_at") or now_text,
                "updated_at": now_text,
            })
            self._append_event_locked(
                str(record["job_id"]),
                "running",
                {"status": "running", "pipeline_state": "retrieving", "lease_owner": owner_id},
            )
            return copy.deepcopy(record)

    def heartbeat_job(self, job_id: str, owner_id: str, *, lease_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        with self.lock:
            record = self.jobs.get(job_id)
            if (
                record is None
                or record.get("status") in TERMINAL_JOB_STATUSES
                or str(record.get("lease_owner") or "") != owner_id
            ):
                return False
            record["heartbeat_at"] = now.isoformat()
            record["lease_expires_at"] = (now + timedelta(seconds=lease_seconds)).isoformat()
            record["updated_at"] = now.isoformat()
            return True

    def _append_event_locked(self, job_id: str, event_type: str, payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        event = {
            "event_id": self.next_event_id,
            "job_id": job_id,
            "event_type": str(event_type),
            "event": str(event_type),
            "payload": copy.deepcopy(dict(payload or {})),
            "created_at": _now(),
        }
        self.next_event_id += 1
        self.events.setdefault(job_id, []).append(event)
        return copy.deepcopy(event)

    def append_event(self, job_id: str, event_type: str, payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(f"Unknown resource generation job '{job_id}'")
            return self._append_event_locked(job_id, event_type, payload)

    def list_events(self, job_id: str, after_event_id: int, limit: int) -> List[Dict[str, Any]]:
        with self.lock:
            events = [
                event for event in self.events.get(job_id, [])
                if int(event["event_id"]) > int(after_event_id)
            ]
            return copy.deepcopy(events[:limit])


_MEMORY_STORE = _MemoryGenerationStore()


class _ResourceGenerationRepositoryMixin:
    """Shared higher-level APIs for durable and in-memory repositories."""

    _store: _MemoryGenerationStore

    @staticmethod
    def _job_record(
        user_id: str,
        course_id: str,
        node_id: str,
        idempotency_key: str,
        *,
        card_types: Optional[Iterable[str]] = None,
        force: bool = False,
        priority: str = "normal",
        request_params: Optional[Mapping[str, Any]] = None,
        content_version: str = "1",
        knowledge_index_version: str = "",
        locale: str = DEFAULT_LOCALE,
        max_retries: int = 0,
        job_id: Optional[str] = None,
        pipeline_version: str = "resource-v3",
        prompt_version: str = "resource-v3",
        blueprint_version: str = "resource-v3",
        quality_version: str = "resource-v3",
        priority_value: Optional[int] = None,
        deadline_at: Optional[str] = None,
        token_budget_input: int = 45_000,
        token_budget_output: int = 12_000,
        generation_call_budget: int = 8,
        cost_budget_microunits: int = 0,
        exposure_mode: str = "normal",
        trace_id: Optional[str] = None,
        release_version: str = "",
        cohort: str = "",
    ) -> Dict[str, Any]:
        now = _now()
        normalized_types = _card_types(card_types)
        return {
            "job_id": str(job_id or uuid.uuid4().hex),
            "user_id": str(user_id),
            "course_id": str(course_id),
            "node_id": str(node_id),
            "idempotency_key": str(idempotency_key),
            "card_types": normalized_types,
            "force": bool(force),
            "priority": str(priority or "normal"),
            "priority_value": int(
                priority_value
                if priority_value is not None
                else PRIORITY_VALUES.get(str(priority or "normal").strip().lower(), 50)
            ),
            "status": "queued",
            "pipeline_state": "queued",
            "progress": {
                "total_cards": len(normalized_types),
                "completed_card_types": [],
                "failed_card_types": [],
            },
            "error": None,
            "request_params": copy.deepcopy(dict(request_params or {})),
            "retry_count": 0,
            "max_retries": max(0, int(max_retries)),
            "content_version": str(content_version or "1"),
            "knowledge_index_version": str(knowledge_index_version or ""),
            "locale": str(locale or DEFAULT_LOCALE),
            "pipeline_version": str(pipeline_version or "resource-v3"),
            "prompt_version": str(prompt_version or "resource-v3"),
            "blueprint_version": str(blueprint_version or "resource-v3"),
            "quality_version": str(quality_version or "resource-v3"),
            "deadline_at": deadline_at,
            "lease_owner": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "token_budget_input": max(0, int(token_budget_input)),
            "token_budget_output": max(0, int(token_budget_output)),
            "generation_call_budget": max(0, int(generation_call_budget)),
            "cost_budget_microunits": max(0, int(cost_budget_microunits)),
            "exposure_mode": str(exposure_mode or "normal"),
            "trace_id": str(trace_id or uuid.uuid4().hex),
            "release_version": str(release_version or ""),
            "cohort": str(cohort or ""),
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
        }

    def _create_or_get_memory(self, *args: Any, **kwargs: Any) -> Tuple[Dict[str, Any], bool]:
        record = self._job_record(*args, **kwargs)
        return self._store.create_or_get_active_job(record)

    def request_generation(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        job, created = self.create_or_get_active_job(*args, **kwargs)
        result = dict(job)
        result["created"] = created
        return result

    def get_job_for_user(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Return a job only when it belongs to the authenticated learner."""
        job = self.get_job(job_id)
        if job is None or str(job.get("user_id")) != str(user_id):
            return None
        return job

    def claim_job(
        self,
        job_id: str,
        *,
        owner_id: Optional[str] = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> Optional[Dict[str, Any]]:
        job = self.get_job(job_id)
        if job is None or job.get("status") not in {"queued", "retrying"}:
            return None
        now = _now()
        updated = self.update_job(
            job_id,
            status="running",
            owner_id=None,
        )
        if updated is not None and owner_id:
            with self._store.lock:
                record = self._store.jobs.get(job_id)
                if record is not None and record.get("status") == "running":
                    record["lease_owner"] = owner_id
                    record["lease_expires_at"] = (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=max(1, int(lease_seconds)))
                    ).isoformat()
                    record["heartbeat_at"] = now
                    updated = copy.deepcopy(record)
        if updated is not None:
            payload = {"status": "running"}
            if owner_id:
                payload["lease_owner"] = owner_id
            self.append_event(job_id, "running", payload)
        return updated

    def claim_next_job(
        self,
        owner_id: str,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        include_shadow: bool = True,
    ) -> Optional[Dict[str, Any]]:
        return self._store.claim_next_job(
            owner_id,
            lease_seconds=max(1, int(lease_seconds)),
            include_shadow=include_shadow,
        )

    def heartbeat_job(
        self,
        job_id: str,
        owner_id: str,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> bool:
        return self._store.heartbeat_job(
            job_id,
            owner_id,
            lease_seconds=max(1, int(lease_seconds)),
        )

    def transition_job(
        self,
        job_id: str,
        status: str,
        *,
        progress: Optional[Mapping[str, Any]] = None,
        error: Any = _UNSET,
        event_payload: Optional[Mapping[str, Any]] = None,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        job = self.update_job(
            job_id,
            status=status,
            progress=progress,
            error=error,
            owner_id=owner_id,
        )
        if job is not None:
            payload = {"status": status}
            if event_payload:
                payload.update(dict(event_payload))
            self.append_event(job_id, status, payload)
        return job

    def mark_card_ready(
        self,
        job_id: str,
        card_type: str,
        card: Mapping[str, Any],
        *,
        progress: Optional[Mapping[str, Any]] = None,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        job = self.get_job(job_id)
        if (
            job is None
            or job.get("status") in TERMINAL_JOB_STATUSES
            or (
                owner_id
                and str(job.get("lease_owner") or "") != owner_id
            )
        ):
            return None
        current = dict(job.get("progress") or {})
        completed = list(current.get("completed_card_types") or [])
        if card_type not in completed:
            completed.append(card_type)
        current["completed_card_types"] = completed
        current["completed_cards"] = len(completed)
        if progress:
            current.update(dict(progress))
        updated = self.update_job(
            job_id,
            progress=current,
            merge_progress=False,
            owner_id=owner_id,
        )
        if updated is not None:
            self.append_event(
                job_id,
                "card_ready",
                {"card_type": card_type, "card": copy.deepcopy(dict(card)), "progress": current},
            )
        return updated

    def mark_card_failed(
        self,
        job_id: str,
        card_type: str,
        error: Any,
        *,
        progress: Optional[Mapping[str, Any]] = None,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        job = self.get_job(job_id)
        if job is None:
            return None
        current = dict(job.get("progress") or {})
        failed = list(current.get("failed_card_types") or [])
        if card_type not in failed:
            failed.append(card_type)
        current["failed_card_types"] = failed
        current["failed_cards"] = len(failed)
        if progress:
            current.update(dict(progress))
        updated = self.update_job(
            job_id,
            progress=current,
            merge_progress=False,
            owner_id=owner_id,
        )
        if updated is not None:
            self.append_event(
                job_id,
                "card_failed",
                {"card_type": card_type, "error": copy.deepcopy(error), "progress": current},
            )
        return updated

    def mark_completed(
        self,
        job_id: str,
        *,
        progress: Optional[Mapping[str, Any]] = None,
        event_payload: Optional[Mapping[str, Any]] = None,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.transition_job(
            job_id,
            "completed",
            progress=progress,
            event_payload=event_payload,
            owner_id=owner_id,
        )

    def mark_partial(
        self,
        job_id: str,
        *,
        progress: Optional[Mapping[str, Any]] = None,
        event_payload: Optional[Mapping[str, Any]] = None,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        job = self.transition_job(
            job_id,
            "partial",
            progress=progress,
            event_payload=event_payload,
            owner_id=owner_id,
        )
        if job is not None:
            # Existing SSE clients terminate only on completed/failed. Keep
            # the durable state truthful while emitting an explicit terminal
            # compatibility envelope whose payload remains status=partial.
            self.append_event(
                job_id,
                "completed",
                {
                    "status": "partial",
                    "partial": True,
                    "compatibility_terminal": True,
                },
            )
        return job

    def mark_failed(
        self,
        job_id: str,
        error: Any,
        *,
        progress: Optional[Mapping[str, Any]] = None,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.transition_job(
            job_id,
            "failed",
            progress=progress,
            error=error,
            event_payload={"error": copy.deepcopy(error)},
            owner_id=owner_id,
        )

    def retry_job(
        self,
        job_id: str,
        *,
        error: Any = _UNSET,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        job = self.get_job(job_id)
        if job is None:
            return None
        retry_count = int(job.get("retry_count") or 0) + 1
        updated = self.update_job(
            job_id,
            status="queued",
            error=error,
            retry_count=retry_count,
            owner_id=owner_id,
        )
        if updated is not None:
            self.append_event(job_id, "queued", {"status": "queued", "retry_count": retry_count})
        return updated

    def get_events(self, job_id: str, after_event_id: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        return self.list_events(job_id, after_event_id=after_event_id, limit=limit)

    def stream_events(self, job_id: str, after_event_id: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        return self.list_events(job_id, after_event_id=after_event_id, limit=limit)

    def get_job_events(self, job_id: str, after_event_id: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        return self.list_events(job_id, after_event_id=after_event_id, limit=limit)


class ResourceGenerationRepo(_ResourceGenerationRepositoryMixin):
    """PostgreSQL-backed generation job and cache repository.

    ``allow_memory_fallback`` defaults to true outside production.  Callers
    that require durability in a local integration test can set it to false.
    """

    def __init__(
        self,
        database: Any = None,
        *,
        allow_memory_fallback: Optional[bool] = None,
        memory_store: Optional[_MemoryGenerationStore] = None,
    ) -> None:
        self._db = database if database is not None else db
        self._store = memory_store or _MEMORY_STORE
        self._allow_memory_fallback = (
            not is_production_environment()
            if allow_memory_fallback is None
            else bool(allow_memory_fallback)
        )
        self._using_memory = False
        self._tables_ready = False

    @property
    def using_memory_fallback(self) -> bool:
        return self._using_memory

    def _failover(self, exc: Exception) -> bool:
        if not self._allow_memory_fallback:
            raise exc
        self._using_memory = True
        return True

    def ensure_tables(self) -> bool:
        """Validate migrated production schema or create local development tables."""
        if self._using_memory:
            return False
        if self._tables_ready:
            return True
        try:
            if is_production_environment():
                # Production schema ownership belongs to Alembic. Application
                # replicas only validate the expand migration and fail closed
                # if rollout ordering is incorrect.
                for sql in (
                    """SELECT job_id, pipeline_version, lease_owner
                       FROM resource_generation_jobs LIMIT 0""",
                    """SELECT job_id, card_type, state_version
                       FROM resource_generation_cards LIMIT 0""",
                ):
                    cursor = self._db.execute(sql)
                    fetchall = getattr(cursor, "fetchall", None)
                    if callable(fetchall):
                        fetchall()
            else:
                self._db.execute(RESOURCE_GENERATION_TABLES_SQL)
            self._db.commit()
            self._tables_ready = True
            return True
        except Exception as exc:
            self._failover(exc)
            return False

    def _database_or_memory(self, database_call: Callable[[], Any], memory_call: Callable[[], Any]) -> Any:
        if not self.ensure_tables():
            return memory_call()
        try:
            return database_call()
        except Exception as exc:
            self._rollback()
            self._failover(exc)
            return memory_call()

    def _read_only_database_or_memory(
        self,
        database_call: Callable[[], Any],
        memory_call: Callable[[], Any],
    ) -> Any:
        """Run a cache lookup without DDL, commits, or job-table initialization.

        A resource GET is allowed to fall back to the process-local cache, but
        it must never turn a cache probe into schema creation.  The normal
        helper deliberately calls ``ensure_tables`` for writers; this variant
        intentionally performs only the supplied SELECT when durable storage
        is already available.
        """
        if self._using_memory:
            return memory_call()
        try:
            return database_call()
        except Exception:
            # A cache probe must not put the repository into memory mode: a
            # later POST is responsible for initializing durable job tables.
            # This also avoids turning a missing cache table into a process
            # wide persistence-mode change.
            return memory_call()

    def _fetchone_read_only(self, sql: str, params: Tuple[Any, ...]) -> Optional[Dict[str, Any]]:
        """Execute one SELECT without Database.execute()'s lazy DDL path."""
        database = self._db
        try:
            connection = getattr(database, "conn")
        except Exception:
            # Test doubles and alternate adapters can expose a plain execute
            # method that has no implicit initialization behavior.
            return self._fetchone(sql, params)

        cursor = None
        try:
            cursor_factory = getattr(getattr(psycopg2, "extras", None), "RealDictCursor", None)
            cursor = (
                connection.cursor(cursor_factory=cursor_factory)
                if cursor_factory is not None
                else connection.cursor()
            )
            cursor.execute(sql, params)
            row = cursor.fetchone()
            # PostgreSQL starts a transaction for a plain SELECT when
            # autocommit is disabled. Roll it back after reading so a cache
            # GET cannot leave an idle transaction open; no data is written.
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            if row is None:
                return None
            if isinstance(row, Mapping):
                return dict(row)
            columns = [column[0] for column in (cursor.description or [])]
            return dict(zip(columns, row))
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            if cursor is not None:
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()

    def _fetchone(self, sql: str, params: Tuple[Any, ...]) -> Optional[Dict[str, Any]]:
        row = self._db.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def _fetchall(self, sql: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        rows = self._db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def _rollback(self) -> None:
        rollback = getattr(self._db, "rollback", None)
        if callable(rollback):
            rollback()

    def _commit(self) -> None:
        commit = getattr(self._db, "commit", None)
        if not callable(commit):
            raise RuntimeError("resource generation storage does not support commit")
        commit()

    @staticmethod
    def _advisory_result(row: Optional[Mapping[str, Any]], key: str) -> bool:
        """Normalise PostgreSQL boolean values returned by lightweight fakes too."""
        if not isinstance(row, Mapping):
            return False
        value = row.get(key)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}

    def try_acquire_generation_slot(
        self,
        max_concurrency: int,
        *,
        concept_priority: bool = False,
        owner_id: Optional[str] = None,
    ) -> Optional[ResourceGenerationSlotLease]:
        """Try to acquire one globally shared generation slot without waiting.

        The PostgreSQL path uses session advisory locks rather than a row lease.
        A dead worker's DB connection releases its slot automatically, and a
        live worker holds the lease through ordinary commits while it writes
        incremental cards.  In-memory fallback is intentionally process-local:
        it preserves unit-test semantics but is not presented as distributed
        coordination.
        """
        token = str(owner_id or uuid.uuid4().hex)
        candidates = _slot_candidates(max_concurrency, concept_priority=concept_priority)
        if self._using_memory or not self.ensure_tables():
            return self._store.try_acquire_generation_slot(
                max_concurrency,
                concept_priority=concept_priority,
                owner_id=token,
            )

        acquired_slot: Optional[int] = None
        try:
            for slot in candidates:
                row = self._fetchone(
                    "SELECT pg_try_advisory_lock(%s, %s) AS acquired",
                    (_RESOURCE_GENERATION_ADVISORY_NAMESPACE, slot),
                )
                if self._advisory_result(row, "acquired"):
                    acquired_slot = slot
                    break
            # A plain SELECT opens a transaction with the sync adapter.  The
            # session-level lock survives commit, while ending that transaction
            # prevents an idle worker from holding a transaction open during an
            # LLM request.
            self._commit()
            if acquired_slot is None:
                return None
            return ResourceGenerationSlotLease(acquired_slot, "postgres", token)
        except Exception as exc:
            self._rollback()
            if acquired_slot is not None:
                # ``pg_advisory_lock`` is not transaction-scoped, so rolling
                # back alone cannot release a lock acquired before a later
                # driver error. Best effort cleanup preserves fallback safety.
                try:
                    self._fetchone(
                        "SELECT pg_advisory_unlock(%s, %s) AS released",
                        (_RESOURCE_GENERATION_ADVISORY_NAMESPACE, acquired_slot),
                    )
                    self._commit()
                except Exception:
                    self._rollback()
            if not self._allow_memory_fallback:
                raise exc
            self._using_memory = True
            return self._store.try_acquire_generation_slot(
                max_concurrency,
                concept_priority=concept_priority,
                owner_id=token,
            )

    def release_generation_slot(self, lease: Optional[ResourceGenerationSlotLease]) -> bool:
        """Release a lease held by the current worker thread, without blocking."""
        if lease is None:
            return False
        if lease.backend == "memory":
            return self._store.release_generation_slot(lease)
        if lease.backend != "postgres":
            return False
        try:
            row = self._fetchone(
                "SELECT pg_advisory_unlock(%s, %s) AS released",
                (_RESOURCE_GENERATION_ADVISORY_NAMESPACE, int(lease.slot)),
            )
            self._commit()
            return self._advisory_result(row, "released")
        except Exception:
            # A broken PostgreSQL session has already dropped all of its
            # advisory locks. Do not let cleanup hide the job's real outcome.
            self._rollback()
            return False

    def _active_job_db(
        self,
        user_id: str,
        course_id: str,
        node_id: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        return _normalise_job(self._fetchone(
            """SELECT * FROM resource_generation_jobs
               WHERE user_id = %s AND course_id = %s AND node_id = %s
                 AND idempotency_key = %s
                 AND status IN ('queued', 'running', 'retrying')
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, course_id, node_id, idempotency_key),
        ))

    def create_or_get_active_job(
        self,
        user_id: str,
        course_id: str,
        node_id: str,
        idempotency_key: str,
        *,
        card_types: Optional[Iterable[str]] = None,
        force: bool = False,
        priority: str = "normal",
        request_params: Optional[Mapping[str, Any]] = None,
        content_version: str = "1",
        knowledge_index_version: str = "",
        locale: str = DEFAULT_LOCALE,
        max_retries: int = 0,
        job_id: Optional[str] = None,
        pipeline_version: str = "resource-v3",
        prompt_version: str = "resource-v3",
        blueprint_version: str = "resource-v3",
        quality_version: str = "resource-v3",
        priority_value: Optional[int] = None,
        deadline_at: Optional[str] = None,
        token_budget_input: int = 45_000,
        token_budget_output: int = 12_000,
        generation_call_budget: int = 8,
        cost_budget_microunits: int = 0,
        exposure_mode: str = "normal",
        trace_id: Optional[str] = None,
        release_version: str = "",
        cohort: str = "",
        enforce_admission: bool = False,
        concept_lane: bool = False,
    ) -> Tuple[Dict[str, Any], bool]:
        record = self._job_record(
            user_id,
            course_id,
            node_id,
            idempotency_key,
            card_types=card_types,
            force=force,
            priority=priority,
            request_params=request_params,
            content_version=content_version,
            knowledge_index_version=knowledge_index_version,
            locale=locale,
            max_retries=max_retries,
            job_id=job_id,
            pipeline_version=pipeline_version,
            prompt_version=prompt_version,
            blueprint_version=blueprint_version,
            quality_version=quality_version,
            priority_value=priority_value,
            deadline_at=deadline_at,
            token_budget_input=token_budget_input,
            token_budget_output=token_budget_output,
            generation_call_budget=generation_call_budget,
            cost_budget_microunits=cost_budget_microunits,
            exposure_mode=exposure_mode,
            trace_id=trace_id,
            release_version=release_version,
            cohort=cohort,
        )

        if not self.ensure_tables():
            return self._store.create_or_get_active_job(
                record,
                enforce_admission=enforce_admission,
                concept_lane=concept_lane,
            )

        try:
            connection = getattr(self._db, "conn", None)
        except Exception:
            connection = None
        if connection is not None:
            cursor_factory = getattr(
                getattr(psycopg2, "extras", None),
                "RealDictCursor",
                None,
            )
            cursor = (
                connection.cursor(cursor_factory=cursor_factory)
                if cursor_factory is not None
                else connection.cursor()
            )

            def row_dict(row: Any) -> Optional[Dict[str, Any]]:
                if row is None:
                    return None
                if isinstance(row, Mapping):
                    return dict(row)
                columns = [
                    column[0]
                    for column in (cursor.description or [])
                ]
                return dict(zip(columns, row))

            try:
                if enforce_admission:
                    # Serialize the short admission transaction so queue caps
                    # cannot be exceeded by concurrent API replicas. The
                    # per-user key documents and preserves the learner-level
                    # fencing boundary if the global policy is later sharded.
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(%s, %s)",
                        (_RESOURCE_GENERATION_ADVISORY_NAMESPACE, 0),
                    )
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(%s, %s)",
                        (
                            _RESOURCE_GENERATION_ADVISORY_NAMESPACE,
                            _admission_lock_key(record["user_id"]),
                        ),
                    )
                cursor.execute(
                    """SELECT * FROM resource_generation_jobs
                       WHERE user_id = %s AND course_id = %s AND node_id = %s
                         AND idempotency_key = %s
                         AND status NOT IN ('completed', 'partial', 'failed', 'cancelled')
                       ORDER BY created_at DESC LIMIT 1""",
                    (user_id, course_id, node_id, idempotency_key),
                )
                existing = _normalise_job(row_dict(cursor.fetchone()))
                if existing is not None:
                    connection.commit()
                    return existing, False

                if enforce_admission:
                    cursor.execute(
                        """SELECT COUNT(*)::integer AS depth
                           FROM resource_generation_jobs
                           WHERE status IN ('queued', 'retrying')""",
                    )
                    queue_row = row_dict(cursor.fetchone()) or {}
                    queue_depth = int(queue_row.get("depth") or 0)
                    low_priority = (
                        record["exposure_mode"] == "shadow"
                        or record["priority"]
                        in {"shadow", "supporting", "supporting_bundle"}
                    )
                    if queue_depth >= QUEUE_HARD_LIMIT and not concept_lane:
                        raise ResourceAdmissionError(
                            "resource_queue_full",
                            "Resource generation queue is temporarily full.",
                            status_code=503,
                            retry_after=30,
                            queue_depth=queue_depth,
                        )
                    if queue_depth >= QUEUE_SOFT_LIMIT and low_priority:
                        raise ResourceAdmissionError(
                            "resource_low_priority_paused",
                            "Low-priority resource generation is temporarily paused.",
                            status_code=503,
                            retry_after=15,
                            queue_depth=queue_depth,
                        )
                    cursor.execute(
                        """SELECT COUNT(*)::integer AS count
                           FROM resource_generation_jobs
                           WHERE user_id = %s
                             AND status NOT IN (
                                 'completed', 'partial', 'failed', 'cancelled'
                             )""",
                        (record["user_id"],),
                    )
                    active_row = row_dict(cursor.fetchone()) or {}
                    if int(active_row.get("count") or 0) >= MAX_ACTIVE_JOBS_PER_USER:
                        raise ResourceAdmissionError(
                            "resource_user_active_limit",
                            "At most two resource generation jobs may be active per learner.",
                            status_code=429,
                            retry_after=5,
                        )

                cursor.execute(
                    """INSERT INTO resource_generation_jobs (
                           job_id, user_id, course_id, node_id, idempotency_key,
                           card_types, force, priority, status, progress, error_json,
                           request_params, retry_count, max_retries, content_version,
                           knowledge_index_version, locale, created_at, updated_at,
                           pipeline_version, prompt_version, blueprint_version, quality_version,
                           priority_value, pipeline_state, deadline_at, token_budget_input,
                           token_budget_output, cost_budget_microunits, generation_call_budget,
                           exposure_mode, trace_id, release_version, cohort
                       ) VALUES (
                           %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb,
                           %s::jsonb, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                       ) RETURNING *""",
                    (
                        record["job_id"], record["user_id"], record["course_id"],
                        record["node_id"], record["idempotency_key"],
                        _json_dump(record["card_types"]), record["force"],
                        record["priority"], record["status"],
                        _json_dump(record["progress"]), _json_dump(record["error"]),
                        _json_dump(record["request_params"]), record["retry_count"],
                        record["max_retries"], record["content_version"],
                        record["knowledge_index_version"], record["locale"],
                        record["created_at"], record["updated_at"],
                        record["pipeline_version"], record["prompt_version"],
                        record["blueprint_version"], record["quality_version"],
                        record["priority_value"], record["pipeline_state"],
                        record["deadline_at"], record["token_budget_input"],
                        record["token_budget_output"],
                        record["cost_budget_microunits"],
                        record["generation_call_budget"], record["exposure_mode"],
                        record["trace_id"], record["release_version"],
                        record["cohort"],
                    ),
                )
                inserted = _normalise_job(row_dict(cursor.fetchone()))
                if inserted is None:
                    raise RuntimeError(
                        "resource generation job insert returned no row"
                    )
                cursor.execute(
                    """INSERT INTO resource_generation_job_events
                       (job_id, event_type, payload, created_at)
                       VALUES (%s, 'queued', %s::jsonb, %s)
                       RETURNING event_id""",
                    (
                        inserted["job_id"],
                        _json_dump({
                            "status": "queued",
                            "requested_card_types": list(inserted["card_types"]),
                        }),
                        record["created_at"],
                    ),
                )
                event_row = row_dict(cursor.fetchone()) or {}
                event_id = int(event_row.get("event_id") or 0)
                connection.commit()
                if event_id:
                    resource_event_notifier.publish(
                        str(inserted["job_id"]),
                        event_id,
                    )
                return inserted, True
            except ResourceAdmissionError:
                connection.rollback()
                raise
            except psycopg2.IntegrityError:
                connection.rollback()
                existing = self._active_job_db(
                    user_id,
                    course_id,
                    node_id,
                    idempotency_key,
                )
                if existing is not None:
                    return existing, False
                raise
            except Exception as exc:
                connection.rollback()
                self._failover(exc)
                return self._store.create_or_get_active_job(
                    record,
                    enforce_admission=enforce_admission,
                    concept_lane=concept_lane,
                )
            finally:
                cursor.close()

        try:
            existing = self._active_job_db(user_id, course_id, node_id, idempotency_key)
            if existing is not None:
                return existing, False
            inserted = self._fetchone(
                """INSERT INTO resource_generation_jobs (
                       job_id, user_id, course_id, node_id, idempotency_key,
                       card_types, force, priority, status, progress, error_json,
                       request_params, retry_count, max_retries, content_version,
                       knowledge_index_version, locale, created_at, updated_at,
                       pipeline_version, prompt_version, blueprint_version, quality_version,
                       priority_value, pipeline_state, deadline_at, token_budget_input,
                       token_budget_output, cost_budget_microunits, generation_call_budget,
                       exposure_mode, trace_id, release_version, cohort
                   ) VALUES (
                       %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb,
                       %s::jsonb, %s, %s, %s, %s, %s, %s, %s
                       , %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                   ) RETURNING *""",
                (
                    record["job_id"], record["user_id"], record["course_id"], record["node_id"],
                    record["idempotency_key"], _json_dump(record["card_types"]), record["force"],
                    record["priority"], record["status"], _json_dump(record["progress"]),
                    _json_dump(record["error"]), _json_dump(record["request_params"]),
                    record["retry_count"], record["max_retries"], record["content_version"],
                    record["knowledge_index_version"], record["locale"], record["created_at"],
                    record["updated_at"],
                    record["pipeline_version"], record["prompt_version"],
                    record["blueprint_version"], record["quality_version"],
                    record["priority_value"], record["pipeline_state"], record["deadline_at"],
                    record["token_budget_input"], record["token_budget_output"],
                    record["cost_budget_microunits"], record["generation_call_budget"],
                    record["exposure_mode"], record["trace_id"], record["release_version"],
                    record["cohort"],
                ),
            )
            result = _normalise_job(inserted)
            if result is None:
                raise RuntimeError("resource generation job insert returned no row")
            self.append_event(
                result["job_id"],
                "queued",
                {"status": "queued", "requested_card_types": list(result["card_types"])},
            )
            return result, True
        except psycopg2.IntegrityError:
            self._rollback()
            existing = self._active_job_db(user_id, course_id, node_id, idempotency_key)
            if existing is not None:
                return existing, False
            raise
        except Exception as exc:
            self._failover(exc)
            return self._store.create_or_get_active_job(
                record,
                enforce_admission=enforce_admission,
                concept_lane=concept_lane,
            )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._database_or_memory(
            lambda: _normalise_job(self._fetchone(
                "SELECT * FROM resource_generation_jobs WHERE job_id = %s", (job_id,)
            )),
            lambda: self._store.get_job(job_id),
        )

    def get_active_job(
        self,
        user_id: str,
        course_id: str,
        node_id: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        return self._database_or_memory(
            lambda: self._active_job_db(user_id, course_id, node_id, idempotency_key),
            lambda: self._store.get_active_job(user_id, course_id, node_id, idempotency_key),
        )

    def list_pending_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recoverable queued jobs for process-start worker recovery."""
        safe_limit = max(1, min(int(limit), 500))

        def list_database() -> List[Dict[str, Any]]:
            return [
                normalized
                for row in self._fetchall(
                    """SELECT * FROM resource_generation_jobs
                       WHERE status IN ('queued', 'retrying')
                       ORDER BY created_at ASC LIMIT %s""",
                    (safe_limit,),
                )
                if (normalized := _normalise_job(row)) is not None
            ]

        def list_memory() -> List[Dict[str, Any]]:
            with self._store.lock:
                records = [
                    copy.deepcopy(job)
                    for job in self._store.jobs.values()
                    if job.get("status") in {"queued", "retrying"}
                ]
            records.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("job_id", ""))))
            return records[:safe_limit]

        return self._database_or_memory(list_database, list_memory)

    def recover_stale_running_jobs(
        self,
        *,
        stale_after_seconds: float,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Atomically recover jobs abandoned by a dead worker.

        A process restart must not permanently strand a job after it has been
        claimed.  ``updated_at`` acts as a lightweight worker lease: normal
        generation touches it when each card is published, while startup
        recovery only takes over jobs whose lease has expired.  The timeout is
        deliberately supplied by the caller so deployments can keep it longer
        than their worst-case model phase.
        """
        safe_limit = max(1, min(int(limit), 500))
        try:
            safe_stale_after = max(0.0, float(stale_after_seconds))
        except (TypeError, ValueError):
            safe_stale_after = 0.0
        recovered_at = datetime.now(timezone.utc)
        cutoff = recovered_at - timedelta(seconds=safe_stale_after)
        updated_at = recovered_at.isoformat()

        recovery_error = {
            "code": "worker_lease_expired",
            "message": "The worker lease expired before the generation job completed.",
        }

        def payload_for(job: Mapping[str, Any]) -> Dict[str, Any]:
            status = str(job.get("status") or "queued")
            payload: Dict[str, Any] = {
                "status": status,
                "reason": "worker_lease_expired",
                "recovered_from": "running",
                "retry_count": int(job.get("retry_count") or 0),
                "stale_after_seconds": safe_stale_after,
            }
            if status == "failed":
                payload["error"] = dict(recovery_error)
            return payload

        def recover_database() -> List[Dict[str, Any]]:
            rows = self._fetchall(
                """WITH stale_jobs AS (
                       SELECT job_id
                       FROM resource_generation_jobs
                       WHERE status = 'running'
                         AND COALESCE(lease_expires_at, updated_at) < %s
                       ORDER BY COALESCE(lease_expires_at, updated_at) ASC
                       LIMIT %s
                       FOR UPDATE SKIP LOCKED
                   )
                   UPDATE resource_generation_jobs AS job
                   SET status = CASE
                                    WHEN job.retry_count < job.max_retries THEN 'queued'
                                    ELSE 'failed'
                                END,
                       pipeline_state = CASE
                                            WHEN job.retry_count < job.max_retries THEN 'queued'
                                            ELSE 'failed'
                                        END,
                       retry_count = CASE
                                         WHEN job.retry_count < job.max_retries THEN job.retry_count + 1
                                         ELSE job.retry_count
                                     END,
                       error_json = CASE
                                        WHEN job.retry_count < job.max_retries THEN NULL
                                        ELSE %s::jsonb
                                    END,
                       updated_at = %s,
                       failed_at = CASE
                                       WHEN job.retry_count < job.max_retries THEN job.failed_at
                                       ELSE %s
                                   END,
                       lease_owner = NULL,
                       lease_expires_at = NULL,
                       heartbeat_at = NULL
                   FROM stale_jobs
                   WHERE job.job_id = stale_jobs.job_id
                   RETURNING job.*""",
                (cutoff.isoformat(), safe_limit, _json_dump(recovery_error), updated_at, updated_at),
            )
            # ``Database`` commits during fetches, but an explicit commit keeps
            # this transition durable for repository implementations that do
            # not wrap their cursors the same way before events are appended.
            self._commit()
            recovered = [
                normalized
                for row in rows
                if (normalized := _normalise_job(row)) is not None
            ]
            for job in recovered:
                event_type = "failed" if job.get("status") == "failed" else "queued"
                self.append_event(str(job["job_id"]), event_type, payload_for(job))
            return recovered

        def recover_memory() -> List[Dict[str, Any]]:
            recovered: List[Dict[str, Any]] = []
            with self._store.lock:
                candidates = sorted(
                    (
                        record
                        for record in self._store.jobs.values()
                        if record.get("status") == "running"
                        and (
                            _as_utc_timestamp(record.get("lease_expires_at"))
                            or _as_utc_timestamp(record.get("updated_at"))
                            or recovered_at
                        ) < cutoff
                    ),
                    key=lambda record: str(record.get("updated_at") or ""),
                )[:safe_limit]
                for record in candidates:
                    retry_count = int(record.get("retry_count") or 0)
                    max_retries = int(record.get("max_retries") or 0)
                    can_retry = retry_count < max_retries
                    record["status"] = "queued" if can_retry else "failed"
                    record["pipeline_state"] = (
                        "queued" if can_retry else "failed"
                    )
                    if can_retry:
                        record["retry_count"] = retry_count + 1
                        record["error"] = None
                    else:
                        record["error"] = copy.deepcopy(recovery_error)
                        record["failed_at"] = updated_at
                    record["lease_owner"] = None
                    record["lease_expires_at"] = None
                    record["heartbeat_at"] = None
                    record["updated_at"] = updated_at
                    self._store._append_event_locked(
                        str(record["job_id"]),
                        "queued" if can_retry else "failed",
                        payload_for(record),
                    )
                    recovered.append(copy.deepcopy(record))
            return recovered

        return self._database_or_memory(recover_database, recover_memory)

    def expire_deadline_jobs(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        """Fail work whose end-to-end deadline elapsed.

        Covers queued/retrying jobs that were never claimed and running jobs
        whose worker died or overran the promised deadline. Expiry clears the
        lease, so a still-alive worker is fenced on its next owned write.
        """
        safe_limit = max(1, min(int(limit), 500))
        now = _now()
        error = {
            "code": "deadline_exceeded",
            "message": "The resource generation deadline elapsed.",
        }

        def expire_database() -> List[Dict[str, Any]]:
            rows = self._fetchall(
                """WITH expired_jobs AS (
                       SELECT job_id
                       FROM resource_generation_jobs
                       WHERE status IN ('queued', 'retrying', 'running')
                         AND deadline_at IS NOT NULL
                         AND deadline_at <= %s
                       ORDER BY deadline_at ASC
                       LIMIT %s
                       FOR UPDATE SKIP LOCKED
                   )
                   UPDATE resource_generation_jobs AS job
                   SET status = 'failed',
                       pipeline_state = 'failed',
                       error_json = %s::jsonb,
                       updated_at = %s,
                       failed_at = %s,
                       lease_owner = NULL,
                       lease_expires_at = NULL,
                       heartbeat_at = NULL
                   FROM expired_jobs
                   WHERE job.job_id = expired_jobs.job_id
                   RETURNING job.*""",
                (now, safe_limit, _json_dump(error), now, now),
            )
            expired = [
                normalized
                for row in rows
                if (normalized := _normalise_job(row)) is not None
            ]
            for job in expired:
                self.append_event(
                    str(job["job_id"]),
                    "failed",
                    {
                        "status": "failed",
                        "reason": "deadline_exceeded",
                        "error": error,
                    },
                )
            return expired

        def expire_memory() -> List[Dict[str, Any]]:
            deadline = datetime.now(timezone.utc)
            expired: List[Dict[str, Any]] = []
            with self._store.lock:
                candidates = sorted(
                    (
                        record
                        for record in self._store.jobs.values()
                        if record.get("status") in {"queued", "retrying", "running"}
                        and (
                            _as_utc_timestamp(record.get("deadline_at"))
                            or datetime.max.replace(tzinfo=timezone.utc)
                        ) <= deadline
                    ),
                    key=lambda record: str(record.get("deadline_at") or ""),
                )[:safe_limit]
                for record in candidates:
                    record.update({
                        "status": "failed",
                        "pipeline_state": "failed",
                        "error": copy.deepcopy(error),
                        "updated_at": now,
                        "failed_at": now,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "heartbeat_at": None,
                    })
                    self._store._append_event_locked(
                        str(record["job_id"]),
                        "failed",
                        {
                            "status": "failed",
                            "reason": "deadline_exceeded",
                            "error": error,
                        },
                    )
                    expired.append(copy.deepcopy(record))
            return expired

        return self._database_or_memory(expire_database, expire_memory)

    def claim_job(
        self,
        job_id: str,
        *,
        owner_id: Optional[str] = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> Optional[Dict[str, Any]]:
        def claim_database() -> Optional[Dict[str, Any]]:
            now = _now()
            safe_lease = max(1, int(lease_seconds))
            lease_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=safe_lease)
            ).isoformat() if owner_id else None
            row = self._fetchone(
                """UPDATE resource_generation_jobs
                   SET status = 'running',
                       pipeline_state = 'retrieving',
                       started_at = COALESCE(started_at, %s),
                       updated_at = %s,
                       lease_owner = %s,
                       lease_expires_at = %s,
                       heartbeat_at = %s
                   WHERE job_id = %s AND status IN ('queued', 'retrying')
                   RETURNING *""",
                (now, now, owner_id, lease_expires_at, now if owner_id else None, job_id),
            )
            result = _normalise_job(row)
            if result is not None:
                payload = {"status": "running"}
                if owner_id:
                    payload["lease_owner"] = owner_id
                self.append_event(job_id, "running", payload)
            return result

        return self._database_or_memory(
            claim_database,
            lambda: self._store.claim_job(
                job_id,
                owner_id=owner_id,
                lease_seconds=lease_seconds,
            ),
        )

    def claim_next_job(
        self,
        owner_id: str,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        include_shadow: bool = True,
    ) -> Optional[Dict[str, Any]]:
        safe_lease = max(1, int(lease_seconds))

        def claim_database() -> Optional[Dict[str, Any]]:
            now = datetime.now(timezone.utc)
            now_text = now.isoformat()
            expires_at = (now + timedelta(seconds=safe_lease)).isoformat()
            shadow_clause = "" if include_shadow else "AND exposure_mode <> 'shadow'"
            row = self._fetchone(
                f"""WITH candidate AS (
                        SELECT job_id
                        FROM resource_generation_jobs
                        WHERE status IN ('queued', 'retrying')
                          {shadow_clause}
                          AND (deadline_at IS NULL OR deadline_at > %s)
                        ORDER BY priority_value DESC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE resource_generation_jobs AS job
                    SET status = 'running',
                        pipeline_state = 'retrieving',
                        lease_owner = %s,
                        lease_expires_at = %s,
                        heartbeat_at = %s,
                        started_at = COALESCE(started_at, %s),
                        updated_at = %s
                    FROM candidate
                    WHERE job.job_id = candidate.job_id
                    RETURNING job.*""",
                (now_text, owner_id, expires_at, now_text, now_text, now_text),
            )
            result = _normalise_job(row)
            if result is not None:
                self.append_event(
                    str(result["job_id"]),
                    "running",
                    {
                        "status": "running",
                        "pipeline_state": "retrieving",
                        "lease_owner": owner_id,
                    },
                )
            return result

        return self._database_or_memory(
            claim_database,
            lambda: self._store.claim_next_job(
                owner_id,
                lease_seconds=safe_lease,
                include_shadow=include_shadow,
            ),
        )

    def heartbeat_job(
        self,
        job_id: str,
        owner_id: str,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> bool:
        safe_lease = max(1, int(lease_seconds))

        def heartbeat_database() -> bool:
            now = datetime.now(timezone.utc)
            row = self._fetchone(
                """UPDATE resource_generation_jobs
                   SET heartbeat_at = %s,
                       lease_expires_at = %s,
                       updated_at = %s
                   WHERE job_id = %s
                     AND lease_owner = %s
                     AND status NOT IN ('completed', 'partial', 'failed', 'cancelled')
                   RETURNING job_id""",
                (
                    now.isoformat(),
                    (now + timedelta(seconds=safe_lease)).isoformat(),
                    now.isoformat(),
                    job_id,
                    owner_id,
                ),
            )
            self._commit()
            return row is not None

        return self._database_or_memory(
            heartbeat_database,
            lambda: self._store.heartbeat_job(
                job_id,
                owner_id,
                lease_seconds=safe_lease,
            ),
        )

    def transition_pipeline_state(
        self,
        job_id: str,
        pipeline_state: str,
        *,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if pipeline_state not in PIPELINE_STATES:
            raise ValueError(f"Unsupported resource pipeline state: {pipeline_state}")

        def transition_database() -> Optional[Dict[str, Any]]:
            params: List[Any] = [pipeline_state, _now(), job_id]
            owner_clause = ""
            if owner_id:
                owner_clause = " AND lease_owner = %s"
                params.append(owner_id)
            row = self._fetchone(
                f"""UPDATE resource_generation_jobs
                    SET pipeline_state = %s, updated_at = %s
                    WHERE job_id = %s{owner_clause}
                    RETURNING *""",
                tuple(params),
            )
            result = _normalise_job(row)
            if result is not None:
                self.append_event(
                    job_id,
                    "phase_changed",
                    {"pipeline_state": pipeline_state},
                )
            return result

        def transition_memory() -> Optional[Dict[str, Any]]:
            with self._store.lock:
                record = self._store.jobs.get(job_id)
                if (
                    record is None
                    or record.get("status") in TERMINAL_JOB_STATUSES
                    or (owner_id and record.get("lease_owner") != owner_id)
                ):
                    return None
                record["pipeline_state"] = pipeline_state
                record["updated_at"] = _now()
                self._store._append_event_locked(
                    job_id,
                    "phase_changed",
                    {"pipeline_state": pipeline_state},
                )
                return copy.deepcopy(record)

        return self._database_or_memory(transition_database, transition_memory)

    def queue_snapshot(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)

        def snapshot_database() -> Dict[str, Any]:
            row = self._fetchone(
                """SELECT COUNT(*)::integer AS depth,
                          MIN(created_at) AS oldest_created_at,
                          COUNT(*) FILTER (WHERE exposure_mode = 'shadow')::integer AS shadow_depth
                   FROM resource_generation_jobs
                   WHERE status IN ('queued', 'retrying')""",
                (),
            ) or {}
            oldest = _as_utc_timestamp(row.get("oldest_created_at"))
            return {
                "depth": int(row.get("depth") or 0),
                "shadow_depth": int(row.get("shadow_depth") or 0),
                "oldest_age_seconds": max(0.0, (now - oldest).total_seconds()) if oldest else 0.0,
            }

        def snapshot_memory() -> Dict[str, Any]:
            with self._store.lock:
                pending = [
                    record
                    for record in self._store.jobs.values()
                    if record.get("status") in {"queued", "retrying"}
                ]
            oldest = min(
                (_as_utc_timestamp(record.get("created_at")) for record in pending),
                default=None,
                key=lambda value: value or now,
            )
            return {
                "depth": len(pending),
                "shadow_depth": sum(record.get("exposure_mode") == "shadow" for record in pending),
                "oldest_age_seconds": max(0.0, (now - oldest).total_seconds()) if oldest else 0.0,
            }

        return self._database_or_memory(snapshot_database, snapshot_memory)

    def active_job_count_for_user(self, user_id: str) -> int:
        return int(self._database_or_memory(
            lambda: (
                self._fetchone(
                    """SELECT COUNT(*)::integer AS count
                       FROM resource_generation_jobs
                       WHERE user_id = %s
                         AND status NOT IN ('completed', 'partial', 'failed', 'cancelled')""",
                    (user_id,),
                ) or {}
            ).get("count", 0),
            lambda: sum(
                1
                for record in self._store.jobs.values()
                if record.get("user_id") == user_id
                and record.get("status") not in TERMINAL_JOB_STATUSES
            ),
        ))

    def get_card_record(self, job_id: str, card_type: str) -> Optional[Dict[str, Any]]:
        def get_database() -> Optional[Dict[str, Any]]:
            row = self._fetchone(
                """SELECT * FROM resource_generation_cards
                   WHERE job_id = %s AND card_type = %s""",
                (job_id, card_type),
            )
            if row is None:
                return None
            result = dict(row)
            result["payload"] = _json_value(result.get("payload"), None)
            result["quality_result"] = _json_value(result.get("quality_result"), {})
            result["blueprint_snapshot"] = _json_value(result.get("blueprint_snapshot"), {})
            return result

        return self._database_or_memory(
            get_database,
            lambda: copy.deepcopy(self._store.cards.get((job_id, card_type))),
        )

    def mark_card_ready(
        self,
        job_id: str,
        card_type: str,
        card: Mapping[str, Any],
        *,
        progress: Optional[Mapping[str, Any]] = None,
        quality_result: Optional[Mapping[str, Any]] = None,
        blueprint_snapshot: Optional[Mapping[str, Any]] = None,
        publication_version: str = "",
        degraded_reason: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = copy.deepcopy(dict(card))
        payload_hash = hashlib.sha256(
            _json_dump(payload).encode("utf-8")
        ).hexdigest()
        now = _now()

        def publish_memory() -> Optional[Dict[str, Any]]:
            with self._store.lock:
                job = self._store.jobs.get(job_id)
                if (
                    job is None
                    or job.get("status") in TERMINAL_JOB_STATUSES
                    or (
                        owner_id
                        and str(job.get("lease_owner") or "") != owner_id
                    )
                ):
                    return None
                key = (job_id, card_type)
                existing = self._store.cards.get(key)
                if (
                    existing is not None
                    and existing.get("status") == "published"
                ):
                    return copy.deepcopy(job)
                version = int((existing or {}).get("state_version") or 0) + 1
                self._store.cards[key] = {
                    "job_id": job_id,
                    "card_type": card_type,
                    "status": "published",
                    "state_version": version,
                    "payload": payload,
                    "quality_result": copy.deepcopy(dict(quality_result or {})),
                    "blueprint_snapshot": copy.deepcopy(dict(blueprint_snapshot or {})),
                    "publication_version": publication_version,
                    "content_hash": payload_hash,
                    "degraded_reason": degraded_reason,
                    "created_at": (existing or {}).get("created_at") or now,
                    "updated_at": now,
                    "published_at": now,
                }
                current = dict(job.get("progress") or {})
                completed = list(current.get("completed_card_types") or [])
                if card_type not in completed:
                    completed.append(card_type)
                current.update(dict(progress or {}))
                current.update({
                    "completed_card_types": completed,
                    "completed_cards": len(completed),
                })
                job["progress"] = current
                job["updated_at"] = now
                self._store._append_event_locked(
                    job_id,
                    "card_ready",
                    {"card_type": card_type, "card": payload, "progress": current},
                )
                return copy.deepcopy(job)

        def publish_database() -> Optional[Dict[str, Any]]:
            connection = getattr(self._db, "conn", None)
            if connection is None:
                return super(ResourceGenerationRepo, self).mark_card_ready(
                    job_id,
                    card_type,
                    payload,
                    progress=progress,
                    owner_id=owner_id,
                )
            cursor_factory = getattr(getattr(psycopg2, "extras", None), "RealDictCursor", None)
            cursor = (
                connection.cursor(cursor_factory=cursor_factory)
                if cursor_factory is not None
                else connection.cursor()
            )
            try:
                cursor.execute(
                    """SELECT progress, lease_owner, status
                       FROM resource_generation_jobs
                       WHERE job_id = %s FOR UPDATE""",
                    (job_id,),
                )
                job_row = cursor.fetchone()
                if job_row is None:
                    connection.rollback()
                    return None
                if isinstance(job_row, Mapping):
                    current_owner = str(job_row.get("lease_owner") or "")
                    current_status = str(job_row.get("status") or "")
                    progress_value = job_row.get("progress")
                else:
                    progress_value = job_row[0]
                    current_owner = str(job_row[1] or "")
                    current_status = str(job_row[2] or "")
                if (
                    current_status in TERMINAL_JOB_STATUSES
                    or (owner_id and current_owner != owner_id)
                ):
                    connection.rollback()
                    return None
                current = _json_value(
                    progress_value,
                    {},
                )
                completed = list(current.get("completed_card_types") or [])
                if card_type not in completed:
                    completed.append(card_type)
                current.update(dict(progress or {}))
                current.update({
                    "completed_card_types": completed,
                    "completed_cards": len(completed),
                })
                cursor.execute(
                    """INSERT INTO resource_generation_cards (
                           job_id, card_type, status, state_version, payload,
                           quality_result, blueprint_snapshot, publication_version,
                           content_hash, degraded_reason, created_at, updated_at, published_at
                       ) VALUES (
                           %s, %s, 'published', 1, %s::jsonb, %s::jsonb, %s::jsonb,
                           %s, %s, %s, %s, %s, %s
                       )
                       ON CONFLICT (job_id, card_type) DO UPDATE
                       SET status = 'published',
                           state_version = resource_generation_cards.state_version + 1,
                           payload = EXCLUDED.payload,
                           quality_result = EXCLUDED.quality_result,
                           blueprint_snapshot = EXCLUDED.blueprint_snapshot,
                           publication_version = EXCLUDED.publication_version,
                           content_hash = EXCLUDED.content_hash,
                           degraded_reason = EXCLUDED.degraded_reason,
                           updated_at = EXCLUDED.updated_at,
                           published_at = EXCLUDED.published_at
                       WHERE resource_generation_cards.status <> 'published'
                       RETURNING state_version""",
                    (
                        job_id,
                        card_type,
                        _json_dump(payload),
                        _json_dump(dict(quality_result or {})),
                        _json_dump(dict(blueprint_snapshot or {})),
                        publication_version,
                        payload_hash,
                        degraded_reason,
                        now,
                        now,
                        now,
                    ),
                )
                changed = cursor.fetchone() is not None
                update_params: List[Any] = [
                    _json_dump(current),
                    now,
                    job_id,
                ]
                owner_clause = ""
                if owner_id:
                    owner_clause = " AND lease_owner = %s"
                    update_params.append(owner_id)
                cursor.execute(
                    f"""UPDATE resource_generation_jobs
                       SET progress = %s::jsonb, updated_at = %s
                       WHERE job_id = %s{owner_clause}
                         AND status NOT IN ('completed', 'partial', 'failed', 'cancelled')
                       RETURNING *""",
                    tuple(update_params),
                )
                updated_row = cursor.fetchone()
                if updated_row is None:
                    connection.rollback()
                    return None
                event_id: Optional[int] = None
                if changed:
                    cursor.execute(
                        """INSERT INTO resource_generation_job_events
                           (job_id, event_type, payload, created_at)
                           VALUES (%s, 'card_ready', %s::jsonb, %s)
                           RETURNING event_id""",
                        (
                            job_id,
                            _json_dump({
                                "card_type": card_type,
                                "card": payload,
                                "progress": current,
                            }),
                            now,
                        ),
                    )
                    event_row = cursor.fetchone()
                    if isinstance(event_row, Mapping):
                        event_id = int(event_row.get("event_id") or 0) or None
                    elif event_row:
                        event_id = int(event_row[0])
                connection.commit()
                if event_id is not None:
                    resource_event_notifier.publish(job_id, event_id)
                return _normalise_job(updated_row)
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

        return self._database_or_memory(publish_database, publish_memory)

    def record_attempt(
        self,
        job_id: str,
        card_type: str,
        operation: str,
        *,
        provider: str = "",
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        elapsed_ms: float = 0.0,
        issue_code: str = "",
        artifact_version: str = "",
        content_hash: str = "",
    ) -> Dict[str, Any]:
        record = {
            "job_id": job_id,
            "card_type": card_type,
            "operation": operation,
            "provider": provider,
            "model": model,
            "input_tokens": max(0, int(input_tokens)),
            "output_tokens": max(0, int(output_tokens)),
            "elapsed_ms": max(0.0, float(elapsed_ms)),
            "issue_code": issue_code,
            "artifact_version": artifact_version,
            "content_hash": content_hash,
            "created_at": _now(),
        }

        def insert_database() -> Dict[str, Any]:
            row = self._fetchone(
                """INSERT INTO resource_generation_attempts (
                       job_id, card_type, operation, provider, model, input_tokens,
                       output_tokens, elapsed_ms, issue_code, artifact_version,
                       content_hash, created_at
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                tuple(record.values()),
            )
            self._commit()
            return dict(row or record)

        def insert_memory() -> Dict[str, Any]:
            with self._store.lock:
                stored = {**record, "attempt_id": len(self._store.attempts) + 1}
                self._store.attempts.append(stored)
                return copy.deepcopy(stored)

        return self._database_or_memory(insert_database, insert_memory)

    def record_quality_evaluation(
        self,
        job_id: str,
        card_type: str,
        *,
        quality_version: str,
        gate_status: str,
        score: float,
        dimensions: Mapping[str, Any],
        issue_codes: Iterable[str] = (),
        artifact_digest: str = "",
        content_hash: str = "",
    ) -> Dict[str, Any]:
        record = {
            "job_id": job_id,
            "card_type": card_type,
            "quality_version": quality_version,
            "gate_status": gate_status,
            "score": float(score),
            "dimensions": dict(dimensions),
            "issue_codes": list(issue_codes),
            "artifact_digest": artifact_digest,
            "content_hash": content_hash,
            "created_at": _now(),
        }

        def insert_database() -> Dict[str, Any]:
            row = self._fetchone(
                """INSERT INTO resource_quality_evaluations (
                       job_id, card_type, quality_version, gate_status, score,
                       dimensions, issue_codes, artifact_digest, content_hash, created_at
                   ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                   RETURNING *""",
                (
                    job_id,
                    card_type,
                    quality_version,
                    gate_status,
                    float(score),
                    _json_dump(dict(dimensions)),
                    _json_dump(list(issue_codes)),
                    artifact_digest,
                    content_hash,
                    record["created_at"],
                ),
            )
            self._commit()
            return dict(row or record)

        def insert_memory() -> Dict[str, Any]:
            with self._store.lock:
                stored = {
                    **record,
                    "evaluation_id": len(self._store.quality_evaluations) + 1,
                }
                self._store.quality_evaluations.append(stored)
                return copy.deepcopy(stored)

        return self._database_or_memory(insert_database, insert_memory)

    def purge_expired_metadata(
        self,
        *,
        evidence_days: int = 30,
        attempt_days: int = 90,
        quality_days: int = 180,
    ) -> Dict[str, int]:
        now = datetime.now(timezone.utc)
        evidence_cutoff = (
            now - timedelta(days=max(1, int(evidence_days)))
        ).isoformat()
        attempt_cutoff = (
            now - timedelta(days=max(1, int(attempt_days)))
        ).isoformat()
        quality_cutoff = (
            now - timedelta(days=max(1, int(quality_days)))
        ).isoformat()

        def purge_database() -> Dict[str, int]:
            attempts = len(self._fetchall(
                """DELETE FROM resource_generation_attempts
                   WHERE created_at < %s RETURNING attempt_id""",
                (attempt_cutoff,),
            ))
            evaluations = len(self._fetchall(
                """DELETE FROM resource_quality_evaluations
                   WHERE created_at < %s RETURNING evaluation_id""",
                (quality_cutoff,),
            ))
            cards = len(self._fetchall(
                """UPDATE resource_generation_cards
                   SET payload = payload - 'source_refs',
                       updated_at = %s
                   WHERE created_at < %s
                     AND payload ? 'source_refs'
                   RETURNING card_id""",
                (now.isoformat(), evidence_cutoff),
            ))
            events = len(self._fetchall(
                """UPDATE resource_generation_job_events
                   SET payload = payload #- '{card,source_refs}'
                   WHERE created_at < %s
                     AND event_type = 'card_ready'
                     AND payload #> '{card,source_refs}' IS NOT NULL
                   RETURNING event_id""",
                (evidence_cutoff,),
            ))
            self._commit()
            return {
                "attempts": attempts,
                "quality_evaluations": evaluations,
                "card_evidence": cards,
                "event_evidence": events,
            }

        def purge_memory() -> Dict[str, int]:
            with self._store.lock:
                original_attempts = len(self._store.attempts)
                self._store.attempts = [
                    value
                    for value in self._store.attempts
                    if str(value.get("created_at") or "") >= attempt_cutoff
                ]
                original_quality = len(self._store.quality_evaluations)
                self._store.quality_evaluations = [
                    value
                    for value in self._store.quality_evaluations
                    if str(value.get("created_at") or "") >= quality_cutoff
                ]
                card_evidence = 0
                for value in self._store.cards.values():
                    if str(value.get("created_at") or "") >= evidence_cutoff:
                        continue
                    payload = value.get("payload")
                    if isinstance(payload, dict) and "source_refs" in payload:
                        payload.pop("source_refs", None)
                        card_evidence += 1
                event_evidence = 0
                for events in self._store.events.values():
                    for event in events:
                        if str(event.get("created_at") or "") >= evidence_cutoff:
                            continue
                        card = event.get("payload", {}).get("card")
                        if isinstance(card, dict) and "source_refs" in card:
                            card.pop("source_refs", None)
                            event_evidence += 1
                return {
                    "attempts": original_attempts - len(self._store.attempts),
                    "quality_evaluations": (
                        original_quality - len(self._store.quality_evaluations)
                    ),
                    "card_evidence": card_evidence,
                    "event_evidence": event_evidence,
                }

        return self._database_or_memory(purge_database, purge_memory)

    def update_job(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[Mapping[str, Any]] = None,
        error: Any = _UNSET,
        retry_count: Optional[int] = None,
        max_retries: Optional[int] = None,
        merge_progress: bool = True,
        owner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        def update_database() -> Optional[Dict[str, Any]]:
            assignments: List[str] = ["updated_at = %s"]
            params: List[Any] = [_now()]
            if status is not None:
                assignments.append("status = %s")
                params.append(str(status))
                if status in PIPELINE_STATES:
                    assignments.append("pipeline_state = %s")
                    params.append(str(status))
                if status == "running":
                    assignments.append("started_at = COALESCE(started_at, %s)")
                    params.append(params[0])
                elif status in {"completed", "partial", "cancelled"}:
                    assignments.append("completed_at = %s")
                    params.append(params[0])
                elif status == "failed":
                    assignments.append("failed_at = %s")
                    params.append(params[0])
                if status in TERMINAL_JOB_STATUSES:
                    assignments.extend([
                        "lease_owner = NULL",
                        "lease_expires_at = NULL",
                    ])
            if progress is not None:
                if merge_progress:
                    assignments.append("progress = COALESCE(progress, '{}'::jsonb) || %s::jsonb")
                else:
                    assignments.append("progress = %s::jsonb")
                params.append(_json_dump(dict(progress)))
            if error is not _UNSET:
                assignments.append("error_json = %s::jsonb")
                params.append(_json_dump(error))
            if retry_count is not None:
                assignments.append("retry_count = %s")
                params.append(int(retry_count))
            if max_retries is not None:
                assignments.append("max_retries = %s")
                params.append(int(max_retries))
            params.append(job_id)
            owner_clause = ""
            if owner_id:
                owner_clause = " AND lease_owner = %s"
                params.append(owner_id)
            row = self._fetchone(
                f"""UPDATE resource_generation_jobs
                    SET {', '.join(assignments)}
                    WHERE job_id = %s{owner_clause}
                    RETURNING *""",
                tuple(params),
            )
            self._commit()
            return _normalise_job(row)

        return self._database_or_memory(
            update_database,
            lambda: self._store.update_job(
                job_id,
                status=status,
                progress=progress,
                error=error,
                retry_count=retry_count,
                max_retries=max_retries,
                merge_progress=merge_progress,
                owner_id=owner_id,
            ),
        )

    def append_event(
        self,
        job_id: str,
        event_type: str,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        def append_database() -> Dict[str, Any]:
            event = _normalise_event(self._fetchone(
                """INSERT INTO resource_generation_job_events (job_id, event_type, payload, created_at)
                   VALUES (%s, %s, %s::jsonb, %s) RETURNING *""",
                (job_id, str(event_type), _json_dump(dict(payload or {})), _now()),
            ) or {})
            self._commit()
            if event.get("event_id"):
                resource_event_notifier.publish(
                    job_id,
                    int(event["event_id"]),
                )
            return event

        return self._database_or_memory(
            append_database,
            lambda: self._store.append_event(job_id, event_type, payload),
        )

    def list_events(
        self,
        job_id: str,
        after_event_id: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        return self._database_or_memory(
            lambda: [
                _normalise_event(row)
                for row in self._fetchall(
                    """SELECT * FROM resource_generation_job_events
                       WHERE job_id = %s AND event_id > %s
                       ORDER BY event_id ASC LIMIT %s""",
                    (job_id, max(0, int(after_event_id)), safe_limit),
                )
            ],
            lambda: self._store.list_events(job_id, after_event_id, safe_limit),
        )

    get_events = list_events
    stream_events = list_events

    def _cache_where(
        self,
        *,
        user_id: Optional[str] = None,
        course_id: Optional[str] = None,
        node_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        content_version: Optional[str] = None,
        locale: Optional[str] = None,
        knowledge_index_version: Optional[str] = None,
        mastery_bucket: Optional[str] = None,
        error_signature: Optional[str] = None,
        cognitive_style: Optional[str] = None,
    ) -> Tuple[List[str], List[Any]]:
        filters = {
            "user_id": user_id,
            "course_id": course_id,
            "node_id": node_id,
            "resource_type": resource_type,
            "content_version": content_version,
            "locale": locale,
            "knowledge_index_version": knowledge_index_version,
            "mastery_bucket": mastery_bucket,
            "error_signature": error_signature,
            "cognitive_style": cognitive_style,
        }
        clauses: List[str] = []
        params: List[Any] = []
        for column, value in filters.items():
            if value is not None:
                clauses.append(f"{column} = %s")
                params.append(str(value))
        return clauses, params

    def get_base_cache(
        self,
        course_id: str,
        node_id: str,
        resource_type: str,
        *,
        content_version: Optional[str] = None,
        locale: Optional[str] = DEFAULT_LOCALE,
        knowledge_index_version: Optional[str] = None,
        read_only: bool = False,
    ) -> Optional[Dict[str, Any]]:
        def get_database() -> Optional[Dict[str, Any]]:
            clauses, params = self._cache_where(
                course_id=course_id,
                node_id=node_id,
                resource_type=resource_type,
                content_version=content_version,
                locale=locale,
                knowledge_index_version=knowledge_index_version,
            )
            fetchone = self._fetchone_read_only if read_only else self._fetchone
            row = fetchone(
                f"SELECT * FROM resource_base_cache WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT 1",
                tuple(params),
            )
            return _normalise_cache(row)

        def get_memory() -> Optional[Dict[str, Any]]:
            with self._store.lock:
                matches = [
                    value for key, value in self._store.base_cache.items()
                    if key[0] == course_id and key[1] == node_id and key[2] == resource_type
                    and (content_version is None or key[3] == content_version)
                    and (locale is None or key[4] == locale)
                    and (knowledge_index_version is None or key[5] == knowledge_index_version)
                ]
                matches.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
                return copy.deepcopy(matches[0]) if matches else None

        lookup = self._read_only_database_or_memory if read_only else self._database_or_memory
        return lookup(get_database, get_memory)

    def read_base_cache(
        self,
        course_id: str,
        node_id: str,
        resource_type: str,
        *,
        content_version: Optional[str] = None,
        locale: Optional[str] = DEFAULT_LOCALE,
        knowledge_index_version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Read a course cache record without creating coordination tables."""
        return self.get_base_cache(
            course_id,
            node_id,
            resource_type,
            content_version=content_version,
            locale=locale,
            knowledge_index_version=knowledge_index_version,
            read_only=True,
        )

    def upsert_base_cache(
        self,
        course_id: str,
        node_id: str,
        resource_type: str,
        payload: Mapping[str, Any],
        *,
        content_version: str = "1",
        locale: str = DEFAULT_LOCALE,
        knowledge_index_version: str = "",
        source_refs: Optional[Iterable[Mapping[str, Any]]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _now()
        record = {
            "course_id": str(course_id),
            "node_id": str(node_id),
            "resource_type": str(resource_type),
            "content_version": str(content_version or "1"),
            "locale": str(locale or DEFAULT_LOCALE),
            "knowledge_index_version": str(knowledge_index_version or ""),
            "payload": copy.deepcopy(dict(payload)),
            "source_refs": copy.deepcopy(list(source_refs or [])),
            "metadata": copy.deepcopy(dict(metadata or {})),
            "created_at": now,
            "updated_at": now,
        }

        def upsert_database() -> Dict[str, Any]:
            row = self._fetchone(
                """INSERT INTO resource_base_cache (
                       course_id, node_id, resource_type, content_version, locale,
                       knowledge_index_version, payload, source_refs, metadata, created_at, updated_at
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
                   ON CONFLICT (
                       course_id, node_id, resource_type, content_version, locale, knowledge_index_version
                   ) DO UPDATE SET
                       payload = EXCLUDED.payload,
                       source_refs = EXCLUDED.source_refs,
                       metadata = EXCLUDED.metadata,
                       updated_at = EXCLUDED.updated_at
                   RETURNING *""",
                (
                    record["course_id"], record["node_id"], record["resource_type"],
                    record["content_version"], record["locale"], record["knowledge_index_version"],
                    _json_dump(record["payload"]), _json_dump(record["source_refs"]),
                    _json_dump(record["metadata"]), record["created_at"], record["updated_at"],
                ),
            )
            self._commit()
            return _normalise_cache(row) or {}

        def upsert_memory() -> Dict[str, Any]:
            key = (
                record["course_id"], record["node_id"], record["resource_type"],
                record["content_version"], record["locale"], record["knowledge_index_version"],
            )
            with self._store.lock:
                existing = self._store.base_cache.get(key)
                if existing is not None:
                    record["created_at"] = existing["created_at"]
                self._store.base_cache[key] = copy.deepcopy(record)
                return copy.deepcopy(record)

        return self._database_or_memory(upsert_database, upsert_memory)

    def delete_base_cache(
        self,
        course_id: str,
        node_id: str,
        *,
        resource_type: Optional[str] = None,
        content_version: Optional[str] = None,
        locale: Optional[str] = None,
        knowledge_index_version: Optional[str] = None,
    ) -> int:
        def delete_database() -> int:
            clauses, params = self._cache_where(
                course_id=course_id,
                node_id=node_id,
                resource_type=resource_type,
                content_version=content_version,
                locale=locale,
                knowledge_index_version=knowledge_index_version,
            )
            deleted = len(self._fetchall(
                f"DELETE FROM resource_base_cache WHERE {' AND '.join(clauses)} RETURNING resource_type",
                tuple(params),
            ))
            self._commit()
            return deleted

        def delete_memory() -> int:
            with self._store.lock:
                keys = [
                    key for key in self._store.base_cache
                    if key[0] == course_id and key[1] == node_id
                    and (resource_type is None or key[2] == resource_type)
                    and (content_version is None or key[3] == content_version)
                    and (locale is None or key[4] == locale)
                    and (knowledge_index_version is None or key[5] == knowledge_index_version)
                ]
                for key in keys:
                    self._store.base_cache.pop(key, None)
                return len(keys)

        return self._database_or_memory(delete_database, delete_memory)

    invalidate_base_cache = delete_base_cache

    def get_personal_cache(
        self,
        user_id: str,
        course_id: str,
        node_id: str,
        resource_type: str,
        *,
        mastery_bucket: Optional[str] = None,
        error_signature: Optional[str] = None,
        cognitive_style: Optional[str] = None,
        content_version: Optional[str] = None,
        locale: Optional[str] = DEFAULT_LOCALE,
        knowledge_index_version: Optional[str] = None,
        read_only: bool = False,
    ) -> Optional[Dict[str, Any]]:
        def get_database() -> Optional[Dict[str, Any]]:
            clauses, params = self._cache_where(
                user_id=user_id,
                course_id=course_id,
                node_id=node_id,
                resource_type=resource_type,
                mastery_bucket=mastery_bucket,
                error_signature=error_signature,
                cognitive_style=cognitive_style,
                content_version=content_version,
                locale=locale,
                knowledge_index_version=knowledge_index_version,
            )
            fetchone = self._fetchone_read_only if read_only else self._fetchone
            row = fetchone(
                f"SELECT * FROM resource_personalization_cache WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT 1",
                tuple(params),
            )
            return _normalise_cache(row)

        def get_memory() -> Optional[Dict[str, Any]]:
            with self._store.lock:
                matches = [
                    value for key, value in self._store.personal_cache.items()
                    if key[0] == user_id and key[1] == course_id and key[2] == node_id and key[3] == resource_type
                    and (mastery_bucket is None or key[4] == mastery_bucket)
                    and (error_signature is None or key[5] == error_signature)
                    and (cognitive_style is None or key[6] == cognitive_style)
                    and (content_version is None or key[7] == content_version)
                    and (locale is None or key[8] == locale)
                    and (knowledge_index_version is None or key[9] == knowledge_index_version)
                ]
                matches.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
                return copy.deepcopy(matches[0]) if matches else None

        lookup = self._read_only_database_or_memory if read_only else self._database_or_memory
        return lookup(get_database, get_memory)

    def read_personal_cache(
        self,
        user_id: str,
        course_id: str,
        node_id: str,
        resource_type: str,
        *,
        mastery_bucket: Optional[str] = None,
        error_signature: Optional[str] = None,
        cognitive_style: Optional[str] = None,
        content_version: Optional[str] = None,
        locale: Optional[str] = DEFAULT_LOCALE,
        knowledge_index_version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Read a learner cache record without creating coordination tables."""
        return self.get_personal_cache(
            user_id,
            course_id,
            node_id,
            resource_type,
            mastery_bucket=mastery_bucket,
            error_signature=error_signature,
            cognitive_style=cognitive_style,
            content_version=content_version,
            locale=locale,
            knowledge_index_version=knowledge_index_version,
            read_only=True,
        )

    def upsert_personal_cache(
        self,
        user_id: str,
        course_id: str,
        node_id: str,
        resource_type: str,
        payload: Mapping[str, Any],
        *,
        mastery_bucket: str,
        error_signature: str = "",
        cognitive_style: str = "",
        content_version: str = "1",
        locale: str = DEFAULT_LOCALE,
        knowledge_index_version: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _now()
        record = {
            "user_id": str(user_id),
            "course_id": str(course_id),
            "node_id": str(node_id),
            "resource_type": str(resource_type),
            "mastery_bucket": str(mastery_bucket),
            "error_signature": str(error_signature or ""),
            "cognitive_style": str(cognitive_style or ""),
            "content_version": str(content_version or "1"),
            "locale": str(locale or DEFAULT_LOCALE),
            "knowledge_index_version": str(knowledge_index_version or ""),
            "payload": copy.deepcopy(dict(payload)),
            "metadata": copy.deepcopy(dict(metadata or {})),
            "created_at": now,
            "updated_at": now,
        }

        def upsert_database() -> Dict[str, Any]:
            row = self._fetchone(
                """INSERT INTO resource_personalization_cache (
                       user_id, course_id, node_id, resource_type, mastery_bucket,
                       error_signature, cognitive_style, content_version, locale,
                       knowledge_index_version, payload, metadata, created_at, updated_at
                   ) VALUES (
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s
                   ) ON CONFLICT (
                       user_id, course_id, node_id, resource_type, mastery_bucket,
                       error_signature, cognitive_style, content_version, locale, knowledge_index_version
                   ) DO UPDATE SET
                       payload = EXCLUDED.payload,
                       metadata = EXCLUDED.metadata,
                       updated_at = EXCLUDED.updated_at
                   RETURNING *""",
                (
                    record["user_id"], record["course_id"], record["node_id"], record["resource_type"],
                    record["mastery_bucket"], record["error_signature"], record["cognitive_style"],
                    record["content_version"], record["locale"], record["knowledge_index_version"],
                    _json_dump(record["payload"]), _json_dump(record["metadata"]),
                    record["created_at"], record["updated_at"],
                ),
            )
            self._commit()
            return _normalise_cache(row) or {}

        def upsert_memory() -> Dict[str, Any]:
            key = (
                record["user_id"], record["course_id"], record["node_id"], record["resource_type"],
                record["mastery_bucket"], record["error_signature"], record["cognitive_style"],
                record["content_version"], record["locale"], record["knowledge_index_version"],
            )
            with self._store.lock:
                existing = self._store.personal_cache.get(key)
                if existing is not None:
                    record["created_at"] = existing["created_at"]
                self._store.personal_cache[key] = copy.deepcopy(record)
                return copy.deepcopy(record)

        return self._database_or_memory(upsert_database, upsert_memory)

    def delete_personal_cache(
        self,
        user_id: str,
        course_id: Optional[str] = None,
        node_id: Optional[str] = None,
        *,
        resource_type: Optional[str] = None,
        content_version: Optional[str] = None,
        locale: Optional[str] = None,
        knowledge_index_version: Optional[str] = None,
    ) -> int:
        def delete_database() -> int:
            clauses, params = self._cache_where(
                user_id=user_id,
                course_id=course_id,
                node_id=node_id,
                resource_type=resource_type,
                content_version=content_version,
                locale=locale,
                knowledge_index_version=knowledge_index_version,
            )
            deleted = len(self._fetchall(
                f"DELETE FROM resource_personalization_cache WHERE {' AND '.join(clauses)} RETURNING resource_type",
                tuple(params),
            ))
            self._commit()
            return deleted

        def delete_memory() -> int:
            with self._store.lock:
                keys = [
                    key for key in self._store.personal_cache
                    if key[0] == user_id
                    and (course_id is None or key[1] == course_id)
                    and (node_id is None or key[2] == node_id)
                    and (resource_type is None or key[3] == resource_type)
                    and (content_version is None or key[7] == content_version)
                    and (locale is None or key[8] == locale)
                    and (knowledge_index_version is None or key[9] == knowledge_index_version)
                ]
                for key in keys:
                    self._store.personal_cache.pop(key, None)
                return len(keys)

        return self._database_or_memory(delete_database, delete_memory)

    invalidate_personal_cache = delete_personal_cache
    get_personalized_cache = get_personal_cache
    upsert_personalized_cache = upsert_personal_cache

    def delete_job(self, job_id: str) -> bool:
        def delete_database() -> bool:
            deleted = bool(self._fetchall(
                "DELETE FROM resource_generation_jobs WHERE job_id = %s RETURNING job_id", (job_id,)
            ))
            self._commit()
            return deleted

        def delete_memory() -> bool:
            with self._store.lock:
                existed = self._store.jobs.pop(job_id, None) is not None
                self._store.events.pop(job_id, None)
                return existed

        return self._database_or_memory(delete_database, delete_memory)

    def delete_for_session(self, user_id: str, course_id: str) -> Dict[str, int]:
        def delete_database() -> Dict[str, int]:
            jobs = len(self._fetchall(
                "DELETE FROM resource_generation_jobs WHERE user_id = %s AND course_id = %s RETURNING job_id",
                (user_id, course_id),
            ))
            personal = len(self._fetchall(
                "DELETE FROM resource_personalization_cache WHERE user_id = %s AND course_id = %s RETURNING resource_type",
                (user_id, course_id),
            ))
            self._commit()
            return {"jobs": jobs, "personal_cache": personal}

        def delete_memory() -> Dict[str, int]:
            with self._store.lock:
                job_ids = [
                    key for key, value in self._store.jobs.items()
                    if value.get("user_id") == user_id and value.get("course_id") == course_id
                ]
                for job_id in job_ids:
                    self._store.jobs.pop(job_id, None)
                    self._store.events.pop(job_id, None)
                cache_keys = [
                    key for key in self._store.personal_cache
                    if key[0] == user_id and key[1] == course_id
                ]
                for key in cache_keys:
                    self._store.personal_cache.pop(key, None)
                return {"jobs": len(job_ids), "personal_cache": len(cache_keys)}

        return self._database_or_memory(delete_database, delete_memory)

    def delete_all(self, user_id: str) -> Dict[str, int]:
        def delete_database() -> Dict[str, int]:
            jobs = len(self._fetchall(
                "DELETE FROM resource_generation_jobs WHERE user_id = %s RETURNING job_id", (user_id,)
            ))
            personal = len(self._fetchall(
                "DELETE FROM resource_personalization_cache WHERE user_id = %s RETURNING resource_type", (user_id,)
            ))
            self._commit()
            return {"jobs": jobs, "personal_cache": personal}

        def delete_memory() -> Dict[str, int]:
            with self._store.lock:
                job_ids = [key for key, value in self._store.jobs.items() if value.get("user_id") == user_id]
                for job_id in job_ids:
                    self._store.jobs.pop(job_id, None)
                    self._store.events.pop(job_id, None)
                cache_keys = [key for key in self._store.personal_cache if key[0] == user_id]
                for key in cache_keys:
                    self._store.personal_cache.pop(key, None)
                return {"jobs": len(job_ids), "personal_cache": len(cache_keys)}

        return self._database_or_memory(delete_database, delete_memory)


class MemoryResourceGenerationRepo(ResourceGenerationRepo):
    """Explicit process-local repository for unit tests and local development."""

    def __init__(self, store: Optional[_MemoryGenerationStore] = None) -> None:
        super().__init__(allow_memory_fallback=True, memory_store=store)
        self._using_memory = True

    def ensure_tables(self) -> bool:
        return False


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "DEFAULT_LOCALE",
    "MemoryResourceGenerationRepo",
    "RESOURCE_GENERATION_TABLES_SQL",
    "ResourceAdmissionError",
    "ResourceGenerationSlotLease",
    "ResourceGenerationRepo",
    "TERMINAL_JOB_STATUSES",
]
