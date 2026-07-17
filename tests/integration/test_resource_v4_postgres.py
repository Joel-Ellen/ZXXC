from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any

import psycopg2
import psycopg2.extras
import pytest

from src.database.resource_generation_repo import (
    RESOURCE_GENERATION_TABLES_SQL,
    ResourceAdmissionError,
    ResourceGenerationRepo,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("EDUAGENT_RUN_POSTGRES_INTEGRATION") != "true",
    reason="set EDUAGENT_RUN_POSTGRES_INTEGRATION=true with TEST_DATABASE_URL",
)


class _Cursor:
    def __init__(self, cursor: Any, connection: Any) -> None:
        self.cursor = cursor
        self.connection = connection

    def fetchone(self) -> Any:
        row = self.cursor.fetchone()
        self.cursor.close()
        self.connection.commit()
        return row

    def fetchall(self) -> list[Any]:
        rows = self.cursor.fetchall()
        self.cursor.close()
        self.connection.commit()
        return rows


class _Database:
    def __init__(self, url: str, schema: str) -> None:
        self.conn = psycopg2.connect(
            url,
            options=f"-c search_path={schema}",
        )
        self.conn.autocommit = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Cursor:
        cursor = self.conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        cursor.execute(sql, params)
        return _Cursor(cursor, self.conn)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


@pytest.fixture
def postgres_repositories():
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/eduagent_test",
    )
    schema = f"resource_v4_{uuid.uuid4().hex}"
    admin = psycopg2.connect(url)
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')

    databases: list[_Database] = []

    def create_repo() -> ResourceGenerationRepo:
        database = _Database(url, schema)
        databases.append(database)
        repo = ResourceGenerationRepo(
            database=database,
            allow_memory_fallback=False,
        )
        repo._tables_ready = True  # noqa: SLF001
        return repo

    bootstrap = _Database(url, schema)
    databases.append(bootstrap)
    with bootstrap.conn.cursor() as cursor:
        cursor.execute(RESOURCE_GENERATION_TABLES_SQL)
    bootstrap.conn.commit()
    try:
        yield create_repo
    finally:
        for database in databases:
            database.close()
        with admin.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA "{schema}" CASCADE')
        admin.close()


def test_postgres_admission_is_race_free(postgres_repositories) -> None:
    first = postgres_repositories()
    second = postgres_repositories()
    for index in range(2):
        _job, created = first.create_or_get_active_job(
            "learner",
            "course-a",
            f"N0{index + 1}",
            f"request-{index}",
            card_types=["concept_map"],
            enforce_admission=True,
            concept_lane=True,
        )
        assert created is True

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(repo: ResourceGenerationRepo, node_id: str) -> None:
        barrier.wait(timeout=5)
        try:
            repo.create_or_get_active_job(
                "learner",
                "course-a",
                node_id,
                f"request-{node_id}",
                card_types=["concept_map"],
                enforce_admission=True,
                concept_lane=True,
            )
            outcome = "created"
        except ResourceAdmissionError as exc:
            outcome = exc.code
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=attempt, args=(first, "N03")),
        threading.Thread(target=attempt, args=(second, "N04")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == [
        "resource_user_active_limit",
        "resource_user_active_limit",
    ]
    assert first.active_job_count_for_user("learner") == 2


def test_postgres_skip_locked_and_publication_are_idempotent(
    postgres_repositories,
) -> None:
    first = postgres_repositories()
    second = postgres_repositories()
    jobs = []
    for index in range(2):
        job, _created = first.create_or_get_active_job(
            f"learner-{index}",
            "course-a",
            f"N0{index + 1}",
            f"request-{index}",
            card_types=["concept_map"],
            priority="concept_map",
        )
        jobs.append(job)

    barrier = threading.Barrier(2)
    claimed: list[dict[str, Any]] = []
    lock = threading.Lock()

    def claim(repo: ResourceGenerationRepo, owner: str) -> None:
        barrier.wait(timeout=5)
        job = repo.claim_next_job(owner, lease_seconds=60)
        if job is not None:
            with lock:
                claimed.append(job)

    threads = [
        threading.Thread(target=claim, args=(first, "worker-a")),
        threading.Thread(target=claim, args=(second, "worker-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert {job["job_id"] for job in claimed} == {
        job["job_id"] for job in jobs
    }
    target = claimed[0]
    first.mark_card_ready(
        target["job_id"],
        "concept_map",
        {"resource_id": "first"},
    )
    first.mark_card_ready(
        target["job_id"],
        "concept_map",
        {"resource_id": "replayed"},
    )

    card = first.get_card_record(target["job_id"], "concept_map")
    assert card is not None
    assert card["state_version"] == 1
    assert card["payload"] == {"resource_id": "first"}
    events = [
        event
        for event in first.list_events(target["job_id"])
        if event["event_type"] == "card_ready"
    ]
    assert len(events) == 1
    assert json.loads(json.dumps(events[0]["payload"]))["card"] == {
        "resource_id": "first"
    }


def test_postgres_expired_worker_lease_is_reclaimed(
    postgres_repositories,
) -> None:
    first = postgres_repositories()
    second = postgres_repositories()
    job, _created = first.create_or_get_active_job(
        "learner",
        "course-a",
        "N01",
        "request",
        card_types=["concept_map"],
        priority="concept_map",
        max_retries=1,
    )
    claimed = first.claim_next_job("worker-a", lease_seconds=60)
    assert claimed is not None
    first._fetchone(  # noqa: SLF001
        """UPDATE resource_generation_jobs
           SET lease_expires_at = %s
           WHERE job_id = %s
           RETURNING job_id""",
        ("2000-01-01T00:00:00+00:00", job["job_id"]),
    )

    recovered = second.recover_stale_running_jobs(
        stale_after_seconds=0,
    )

    assert [value["job_id"] for value in recovered] == [job["job_id"]]
    current = second.get_job(job["job_id"])
    assert current is not None
    assert current["status"] == "queued"
    assert current["lease_owner"] is None
    replacement = second.claim_next_job("worker-b", lease_seconds=60)
    assert replacement is not None
    assert replacement["job_id"] == job["job_id"]
    assert replacement["lease_owner"] == "worker-b"

    assert first.mark_card_ready(
        job["job_id"],
        "concept_map",
        {"resource_id": "stale"},
        owner_id="worker-a",
    ) is None
    assert first.mark_completed(
        job["job_id"],
        owner_id="worker-a",
    ) is None
    assert first.get_card_record(job["job_id"], "concept_map") is None

    assert second.mark_card_ready(
        job["job_id"],
        "concept_map",
        {"resource_id": "current"},
        owner_id="worker-b",
    ) is not None
    assert second.mark_completed(
        job["job_id"],
        owner_id="worker-b",
    ) is not None
    card = second.get_card_record(job["job_id"], "concept_map")
    assert card is not None
    assert card["payload"] == {"resource_id": "current"}
    assert len([
        event
        for event in second.list_events(job["job_id"])
        if event["event_type"] == "card_ready"
    ]) == 1
