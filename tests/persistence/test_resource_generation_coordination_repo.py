from __future__ import annotations

from uuid import uuid4

from src.database.resource_generation_repo import MemoryResourceGenerationRepo, ResourceGenerationRepo, _MemoryGenerationStore


def _fallback_repo() -> ResourceGenerationRepo:
    # A backend without execute() activates the explicitly permitted dev/test
    # memory store without requiring a local PostgreSQL service.
    return ResourceGenerationRepo(database=object(), allow_memory_fallback=True)


def test_generation_jobs_merge_idempotently_and_replay_events() -> None:
    repo = _fallback_repo()
    suffix = uuid4().hex
    arguments = {
        "card_types": ["concept_map", "code_snippet"],
        "force": False,
        "priority": "interactive",
        "content_version": "resource-v3",
        "knowledge_index_version": "kb-v1",
    }

    first, created = repo.create_or_get_active_job(
        f"user-{suffix}", "course-a", "N01", f"same-request-{suffix}", **arguments
    )
    duplicate, duplicate_created = repo.create_or_get_active_job(
        f"user-{suffix}", "course-a", "N01", f"same-request-{suffix}", **arguments
    )

    assert repo.using_memory_fallback is True
    assert created is True
    assert duplicate_created is False
    assert duplicate["job_id"] == first["job_id"]

    assert repo.claim_job(first["job_id"])["status"] == "running"
    repo.mark_card_ready(first["job_id"], "concept_map", {"resource_id": "concept-card"})
    assert repo.mark_completed(first["job_id"])["status"] == "completed"

    events = repo.list_events(first["job_id"])
    assert [event["event_type"] for event in events] == [
        "queued",
        "running",
        "card_ready",
        "completed",
    ]
    replay = repo.list_events(first["job_id"], after_event_id=events[0]["event_id"])
    assert [event["event_type"] for event in replay] == ["running", "card_ready", "completed"]
    assert replay[1]["payload"]["card"]["resource_id"] == "concept-card"


def test_global_generation_slots_are_shared_and_reserve_capacity_for_concepts() -> None:
    store = _MemoryGenerationStore()
    first_instance = MemoryResourceGenerationRepo(store)
    second_instance = MemoryResourceGenerationRepo(store)

    concept_lease = first_instance.try_acquire_generation_slot(2, concept_priority=True)
    supporting_lease = second_instance.try_acquire_generation_slot(2, concept_priority=False)

    assert concept_lease is not None and concept_lease.slot == 0
    assert supporting_lease is not None and supporting_lease.slot == 1
    assert first_instance.try_acquire_generation_slot(2, concept_priority=False) is None

    assert first_instance.release_generation_slot(concept_lease) is True
    replacement_concept = second_instance.try_acquire_generation_slot(2, concept_priority=True)
    assert replacement_concept is not None and replacement_concept.slot == 0

    assert second_instance.release_generation_slot(supporting_lease) is True
    assert second_instance.release_generation_slot(replacement_concept) is True


def test_durable_generation_slots_use_session_advisory_locks(monkeypatch) -> None:
    class Database:
        def __init__(self) -> None:
            self.commits = 0

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            pass

    database = Database()
    repo = ResourceGenerationRepo(database=database, allow_memory_fallback=False)
    calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(repo, "ensure_tables", lambda: True)

    def fetchone(sql, params):
        calls.append((sql, params))
        if "pg_try_advisory_lock" in sql:
            return {"acquired": True}
        if "pg_advisory_unlock" in sql:
            return {"released": True}
        raise AssertionError(sql)

    monkeypatch.setattr(repo, "_fetchone", fetchone)

    lease = repo.try_acquire_generation_slot(3, concept_priority=True)

    assert lease is not None and lease.backend == "postgres" and lease.slot == 0
    assert repo.release_generation_slot(lease) is True
    assert database.commits == 2
    assert "pg_try_advisory_lock" in calls[0][0]
    assert "pg_advisory_unlock" in calls[1][0]


def test_cache_keys_separate_content_and_knowledge_index_versions() -> None:
    repo = _fallback_repo()
    suffix = uuid4().hex
    course_id = f"course-{suffix}"

    repo.upsert_base_cache(
        course_id, "N01", "concept_map", {"revision": "content-v1-index-v1"},
        content_version="content-v1", knowledge_index_version="index-v1",
    )
    repo.upsert_base_cache(
        course_id, "N01", "concept_map", {"revision": "content-v2-index-v1"},
        content_version="content-v2", knowledge_index_version="index-v1",
    )
    repo.upsert_base_cache(
        course_id, "N01", "concept_map", {"revision": "content-v1-index-v2"},
        content_version="content-v1", knowledge_index_version="index-v2",
    )

    assert repo.get_base_cache(
        course_id, "N01", "concept_map", content_version="content-v1", knowledge_index_version="index-v1"
    )["payload"]["revision"] == "content-v1-index-v1"
    assert repo.get_base_cache(
        course_id, "N01", "concept_map", content_version="content-v2", knowledge_index_version="index-v1"
    )["payload"]["revision"] == "content-v2-index-v1"
    assert repo.get_base_cache(
        course_id, "N01", "concept_map", content_version="content-v1", knowledge_index_version="index-v2"
    )["payload"]["revision"] == "content-v1-index-v2"

    repo.upsert_personal_cache(
        "cache-user", course_id, "N01", "concept_map", {"revision": "personal-v1"},
        mastery_bucket="developing", error_signature="fifo", cognitive_style="visual",
        content_version="content-v1", knowledge_index_version="index-v1",
    )
    repo.upsert_personal_cache(
        "cache-user", course_id, "N01", "concept_map", {"revision": "personal-v2"},
        mastery_bucket="developing", error_signature="fifo", cognitive_style="visual",
        content_version="content-v2", knowledge_index_version="index-v1",
    )
    repo.upsert_personal_cache(
        "cache-user", course_id, "N01", "concept_map", {"revision": "personal-index-v2"},
        mastery_bucket="developing", error_signature="fifo", cognitive_style="visual",
        content_version="content-v1", knowledge_index_version="index-v2",
    )

    assert repo.get_personal_cache(
        "cache-user", course_id, "N01", "concept_map",
        mastery_bucket="developing", error_signature="fifo", cognitive_style="visual",
        content_version="content-v1", knowledge_index_version="index-v1",
    )["payload"]["revision"] == "personal-v1"
    assert repo.get_personal_cache(
        "cache-user", course_id, "N01", "concept_map",
        mastery_bucket="developing", error_signature="fifo", cognitive_style="visual",
        content_version="content-v2", knowledge_index_version="index-v1",
    )["payload"]["revision"] == "personal-v2"
    assert repo.get_personal_cache(
        "cache-user", course_id, "N01", "concept_map",
        mastery_bucket="developing", error_signature="fifo", cognitive_style="visual",
        content_version="content-v1", knowledge_index_version="index-v2",
    )["payload"]["revision"] == "personal-index-v2"


def test_durable_event_write_commits_before_sse_readers_can_replay_it(monkeypatch) -> None:
    class RecordingDatabase:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    database = RecordingDatabase()
    repo = ResourceGenerationRepo(database=database, allow_memory_fallback=False)
    monkeypatch.setattr(repo, "ensure_tables", lambda: True)
    monkeypatch.setattr(
        repo,
        "_fetchone",
        lambda _sql, _params: {
            "event_id": 12,
            "job_id": "job-1",
            "event_type": "card_ready",
            "payload": {"card_type": "concept_map"},
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )

    event = repo.append_event("job-1", "card_ready", {"card_type": "concept_map"})

    assert event["event_id"] == 12
    assert database.commits == 1


def test_stale_recovery_commits_transition_before_emitting_event(monkeypatch) -> None:
    order: list[str] = []

    class RecordingDatabase:
        def commit(self) -> None:
            order.append("commit")

        def rollback(self) -> None:
            pass

    repo = ResourceGenerationRepo(database=RecordingDatabase(), allow_memory_fallback=False)
    monkeypatch.setattr(repo, "ensure_tables", lambda: True)
    monkeypatch.setattr(
        repo,
        "_fetchall",
        lambda _sql, _params: [
            {
                "job_id": "expired-job",
                "user_id": "learner",
                "course_id": "course-a",
                "node_id": "N01",
                "idempotency_key": "same-request",
                "card_types": [],
                "force": False,
                "priority": "normal",
                "status": "queued",
                "progress": {},
                "error_json": None,
                "request_params": {},
                "retry_count": 1,
                "max_retries": 1,
                "content_version": "resource-v3",
                "knowledge_index_version": "kb-v1",
                "locale": "zh-CN",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:05:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        repo,
        "append_event",
        lambda _job_id, _event_type, _payload: order.append("event"),
    )

    recovered = repo.recover_stale_running_jobs(stale_after_seconds=60)

    assert [job["job_id"] for job in recovered] == ["expired-job"]
    assert order == ["commit", "event"]
