from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.application import resource_service
from src.database import resource_generation_repo
from src.database.resource_generation_repo import MemoryResourceGenerationRepo, _MemoryGenerationStore


def _claimed_job(
    repo: MemoryResourceGenerationRepo,
    *,
    user_id: str,
    created_at: datetime,
    monkeypatch,
    max_retries: int = 1,
) -> str:
    monkeypatch.setattr(resource_generation_repo, "_now", lambda: created_at.isoformat())
    job, created = repo.create_or_get_active_job(
        user_id,
        "course-recovery",
        "N01",
        f"recovery-{uuid4().hex}",
        card_types=["concept_map"],
        max_retries=max_retries,
    )
    assert created is True
    assert repo.claim_job(job["job_id"])["status"] == "running"
    return str(job["job_id"])


def test_startup_requeues_stale_running_job(monkeypatch) -> None:
    repo = MemoryResourceGenerationRepo(_MemoryGenerationStore())
    job_id = _claimed_job(
        repo,
        user_id=f"stale-worker-{uuid4().hex}",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        monkeypatch=monkeypatch,
    )
    submitted: list[str] = []
    monkeypatch.setattr(
        resource_service,
        "_submit_generation_job",
        lambda candidate, **_kwargs: submitted.append(candidate),
    )

    recovered = resource_service.recover_pending_generation_jobs(
        repo=repo,
        stale_after_seconds=60,
    )

    assert recovered == [job_id]
    assert submitted == [job_id]
    job = repo.get_job(job_id)
    assert job is not None and job["status"] == "queued"
    assert job["retry_count"] == 1
    recovery_event = repo.list_events(job_id)[-1]
    assert recovery_event["event_type"] == "queued"
    assert recovery_event["payload"]["reason"] == "worker_lease_expired"


def test_startup_does_not_reclaim_live_running_job(monkeypatch) -> None:
    repo = MemoryResourceGenerationRepo(_MemoryGenerationStore())
    job_id = _claimed_job(
        repo,
        user_id=f"live-worker-{uuid4().hex}",
        created_at=datetime.now(timezone.utc),
        monkeypatch=monkeypatch,
    )
    submitted: list[str] = []
    monkeypatch.setattr(
        resource_service,
        "_submit_generation_job",
        lambda candidate, **_kwargs: submitted.append(candidate),
    )

    recovered = resource_service.recover_pending_generation_jobs(
        repo=repo,
        stale_after_seconds=60,
    )

    assert recovered == []
    assert submitted == []
    job = repo.get_job(job_id)
    assert job is not None and job["status"] == "running"
    assert [event["event_type"] for event in repo.list_events(job_id)] == ["queued", "running"]


def test_startup_marks_stale_job_failed_after_retry_budget_is_exhausted(monkeypatch) -> None:
    repo = MemoryResourceGenerationRepo(_MemoryGenerationStore())
    job_id = _claimed_job(
        repo,
        user_id=f"exhausted-worker-{uuid4().hex}",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        max_retries=0,
        monkeypatch=monkeypatch,
    )
    submitted: list[str] = []
    monkeypatch.setattr(
        resource_service,
        "_submit_generation_job",
        lambda candidate, **_kwargs: submitted.append(candidate),
    )

    recovered = resource_service.recover_pending_generation_jobs(
        repo=repo,
        stale_after_seconds=60,
    )

    assert recovered == []
    assert submitted == []
    job = repo.get_job(job_id)
    assert job is not None and job["status"] == "failed"
    assert job["error"]["code"] == "worker_lease_expired"
    terminal_event = repo.list_events(job_id)[-1]
    assert terminal_event["event_type"] == "failed"
    assert terminal_event["payload"]["reason"] == "worker_lease_expired"


def test_expire_deadline_jobs_fails_a_running_job_past_its_deadline(monkeypatch) -> None:
    repo = MemoryResourceGenerationRepo(_MemoryGenerationStore())
    job_id = _claimed_job(
        repo,
        user_id=f"deadline-worker-{uuid4().hex}",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        monkeypatch=monkeypatch,
    )
    with repo._store.lock:  # noqa: SLF001 - direct fixture setup
        repo._store.jobs[job_id]["deadline_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=30)
        ).isoformat()

    expired = repo.expire_deadline_jobs()

    assert [job["job_id"] for job in expired] == [job_id]
    job = repo.get_job(job_id)
    assert job is not None and job["status"] == "failed"
    assert job["error"]["code"] == "deadline_exceeded"
    assert job["lease_owner"] is None
    terminal_event = repo.list_events(job_id)[-1]
    assert terminal_event["event_type"] == "failed"
    assert terminal_event["payload"]["reason"] == "deadline_exceeded"


def test_expire_deadline_jobs_keeps_a_running_job_within_its_deadline(monkeypatch) -> None:
    repo = MemoryResourceGenerationRepo(_MemoryGenerationStore())
    job_id = _claimed_job(
        repo,
        user_id=f"healthy-worker-{uuid4().hex}",
        created_at=datetime.now(timezone.utc),
        monkeypatch=monkeypatch,
    )
    with repo._store.lock:  # noqa: SLF001 - direct fixture setup
        repo._store.jobs[job_id]["deadline_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=120)
        ).isoformat()

    assert repo.expire_deadline_jobs() == []
    job = repo.get_job(job_id)
    assert job is not None and job["status"] == "running"


def test_in_process_heartbeat_renews_the_lease_and_stops_after_completion(monkeypatch) -> None:
    repo = MemoryResourceGenerationRepo(_MemoryGenerationStore())
    monkeypatch.setattr(
        resource_generation_repo,
        "_now",
        lambda: datetime.now(timezone.utc).isoformat(),
    )
    job, created = repo.create_or_get_active_job(
        f"heartbeat-worker-{uuid4().hex}",
        "course-recovery",
        "N01",
        f"heartbeat-{uuid4().hex}",
        card_types=["concept_map"],
        max_retries=1,
    )
    assert created is True
    job_id = str(job["job_id"])
    owner = f"compat:test:{uuid4().hex}"
    claimed = repo.claim_job(job_id, owner_id=owner, lease_seconds=1)
    assert claimed is not None and claimed["lease_owner"] == owner
    initial_lease = claimed["lease_expires_at"]

    thread = resource_service._start_job_heartbeat(  # noqa: SLF001
        repo,
        job_id,
        owner,
        interval_seconds=0.05,
    )
    assert thread is not None
    try:
        import time as _time

        _time.sleep(0.3)
        renewed = repo.get_job(job_id)
        assert renewed is not None
        assert renewed["lease_expires_at"] > initial_lease

        # Completion makes heartbeat_job return False and the thread exit.
        repo.transition_job(job_id, "completed", owner_id=owner)
        thread.join(timeout=2.0)
        assert not thread.is_alive()
    finally:
        repo.transition_job(job_id, "completed", owner_id=owner)


def test_sweep_expires_deadline_overruns_before_requeueing_stale_work(monkeypatch) -> None:
    repo = MemoryResourceGenerationRepo(_MemoryGenerationStore())
    overrun_id = _claimed_job(
        repo,
        user_id=f"overrun-worker-{uuid4().hex}",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        monkeypatch=monkeypatch,
    )
    stale_id = _claimed_job(
        repo,
        user_id=f"sweep-stale-worker-{uuid4().hex}",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        monkeypatch=monkeypatch,
    )
    with repo._store.lock:  # noqa: SLF001 - direct fixture setup
        repo._store.jobs[overrun_id]["deadline_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=30)
        ).isoformat()
        repo._store.jobs[stale_id]["deadline_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=120)
        ).isoformat()
    submitted: list[str] = []
    monkeypatch.setattr(
        resource_service,
        "_submit_generation_job",
        lambda candidate, **_kwargs: submitted.append(candidate),
    )

    summary = resource_service.sweep_generation_jobs(repo=repo)

    assert summary == {"expired": 1, "recovered": 1}
    assert submitted == [stale_id]
    overrun = repo.get_job(overrun_id)
    assert overrun is not None and overrun["status"] == "failed"
    assert overrun["error"]["code"] == "deadline_exceeded"
    stale = repo.get_job(stale_id)
    assert stale is not None and stale["status"] == "queued"
    assert stale["retry_count"] == 1
