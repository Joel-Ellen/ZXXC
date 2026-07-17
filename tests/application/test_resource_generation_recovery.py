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
