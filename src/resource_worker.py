"""Standalone PostgreSQL-leased worker for resource-v4 generation."""

from __future__ import annotations

import concurrent.futures
import os
import signal
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from src.application.resource_service import _run_claimed_generation_job
from src.database.resource_generation_repo import (
    DEFAULT_LEASE_SECONDS,
    ResourceGenerationRepo,
)
from src.observability import (
    bind_context,
    incr_metric,
    log_event,
    observe_metric,
    set_metric,
)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class WorkerConfig:
    stage_slots: int = 8
    poll_interval_seconds: float = 0.25
    heartbeat_seconds: int = 15
    lease_seconds: int = DEFAULT_LEASE_SECONDS
    shutdown_grace_seconds: int = 90
    include_shadow: bool = True
    metrics_interval_seconds: float = 5.0
    recovery_interval_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return cls(
            stage_slots=_env_int(
                "EDUAGENT_RESOURCE_WORKER_STAGE_SLOTS",
                8,
                minimum=1,
                maximum=64,
            ),
            poll_interval_seconds=_env_float(
                "EDUAGENT_RESOURCE_WORKER_POLL_SECONDS",
                0.25,
                minimum=0.05,
                maximum=5.0,
            ),
            heartbeat_seconds=_env_int(
                "EDUAGENT_RESOURCE_WORKER_HEARTBEAT_SECONDS",
                15,
                minimum=5,
                maximum=30,
            ),
            lease_seconds=_env_int(
                "EDUAGENT_RESOURCE_WORKER_LEASE_SECONDS",
                60,
                minimum=30,
                maximum=300,
            ),
            shutdown_grace_seconds=_env_int(
                "EDUAGENT_RESOURCE_WORKER_SHUTDOWN_GRACE_SECONDS",
                90,
                minimum=10,
                maximum=600,
            ),
            include_shadow=str(
                os.environ.get("EDUAGENT_RESOURCE_WORKER_INCLUDE_SHADOW", "true")
            ).strip().lower() in {"1", "true", "yes", "on"},
            metrics_interval_seconds=_env_float(
                "EDUAGENT_RESOURCE_WORKER_METRICS_SECONDS",
                5.0,
                minimum=1.0,
                maximum=60.0,
            ),
            recovery_interval_seconds=_env_float(
                "EDUAGENT_RESOURCE_WORKER_RECOVERY_SECONDS",
                15.0,
                minimum=5.0,
                maximum=60.0,
            ),
        )


class ResourceWorker:
    """Poll, lease and execute resource jobs without relying on API memory."""

    def __init__(
        self,
        *,
        repo: Optional[ResourceGenerationRepo] = None,
        config: Optional[WorkerConfig] = None,
        owner_id: Optional[str] = None,
    ) -> None:
        self.repo = repo or ResourceGenerationRepo(allow_memory_fallback=False)
        self.config = config or WorkerConfig.from_env()
        self.owner_id = owner_id or (
            f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
        )
        self._stop = threading.Event()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.stage_slots,
            thread_name_prefix="resource-v4-stage",
        )
        self._futures: set[concurrent.futures.Future[Any]] = set()
        self._futures_lock = threading.Lock()
        self._next_metrics_at = 0.0
        self._next_recovery_at = 0.0

    def request_stop(self, *_args: Any) -> None:
        self._stop.set()

    def _track(self, future: concurrent.futures.Future[Any]) -> None:
        with self._futures_lock:
            self._futures.add(future)

        def done(completed: concurrent.futures.Future[Any]) -> None:
            with self._futures_lock:
                self._futures.discard(completed)
            try:
                completed.result()
            except Exception as exc:
                incr_metric(
                    "resource_worker.job_exception_total",
                    release=os.environ.get("RELEASE_VERSION", ""),
                )
                log_event(
                    "resource_worker.job_failed",
                    level="error",
                    owner_id=self.owner_id,
                    error_type=type(exc).__name__,
                )

        future.add_done_callback(done)

    def _heartbeat_loop(self, job_id: str, finished: threading.Event) -> None:
        while not finished.wait(self.config.heartbeat_seconds):
            if not self.repo.heartbeat_job(
                job_id,
                self.owner_id,
                lease_seconds=self.config.lease_seconds,
            ):
                log_event(
                    "resource_worker.lease_lost",
                    level="error",
                    job_id=job_id,
                    owner_id=self.owner_id,
                )
                return

    def _execute(self, job: dict[str, Any]) -> None:
        job_id = str(job["job_id"])
        trace_id = str(job.get("trace_id") or uuid.uuid4().hex)
        finished = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(job_id, finished),
            name=f"resource-heartbeat-{job_id[:8]}",
            daemon=True,
        )
        heartbeat.start()
        started = time.perf_counter()
        try:
            with bind_context(
                trace_id=trace_id,
                job_id=job_id,
                pipeline_version=job.get("pipeline_version"),
                release=job.get("release_version"),
                cohort=job.get("cohort"),
                deadline_at=job.get("deadline_at"),
            ):
                _run_claimed_generation_job(
                    job_id,
                    repo=self.repo,
                    claimed_job=job,
                )
        finally:
            finished.set()
            heartbeat.join(timeout=1.0)
            observe_metric(
                "resource_worker.job_duration_ms",
                round((time.perf_counter() - started) * 1000, 3),
                release=job.get("release_version"),
                pipeline_version=job.get("pipeline_version"),
                cohort=job.get("cohort"),
                gate_status=(self.repo.get_job(job_id) or {}).get("status"),
            )

    def _available_slots(self) -> int:
        with self._futures_lock:
            return max(0, self.config.stage_slots - len(self._futures))

    def _observe_runtime_metrics(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now < self._next_metrics_at:
            return
        self._next_metrics_at = now + self.config.metrics_interval_seconds
        snapshot = self.repo.queue_snapshot()
        set_metric(
            "resource_queue_oldest_age_seconds",
            float(snapshot["oldest_age_seconds"]),
        )
        set_metric("resource_queue_depth", float(snapshot["depth"]))
        set_metric(
            "resource_queue_shadow_depth",
            float(snapshot["shadow_depth"]),
        )
        set_metric(
            "resource_worker_active_jobs",
            float(self.config.stage_slots - self._available_slots()),
        )

    def _recover_expired_work(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now < self._next_recovery_at:
            return
        self._next_recovery_at = now + self.config.recovery_interval_seconds
        recovered = self.repo.recover_stale_running_jobs(
            stale_after_seconds=0,
            limit=max(100, self.config.stage_slots * 4),
        )
        expired = self.repo.expire_deadline_jobs(
            limit=max(100, self.config.stage_slots * 4),
        )
        if recovered:
            incr_metric(
                "resource_worker.lease_recovered_total",
                amount=len(recovered),
            )
        if expired:
            incr_metric(
                "resource_worker.deadline_expired_total",
                amount=len(expired),
            )

    def run_forever(self) -> int:
        self.repo.ensure_tables()
        self._recover_expired_work(force=True)
        set_metric("resource_telemetry_schema_valid", 1.0)
        self._observe_runtime_metrics(force=True)
        log_event(
            "resource_worker.started",
            owner_id=self.owner_id,
            stage_slots=self.config.stage_slots,
            lease_seconds=self.config.lease_seconds,
        )
        while not self._stop.is_set():
            self._recover_expired_work()
            available = self._available_slots()
            if available <= 0:
                self._stop.wait(self.config.poll_interval_seconds)
                continue
            claimed = 0
            for _ in range(available):
                job = self.repo.claim_next_job(
                    self.owner_id,
                    lease_seconds=self.config.lease_seconds,
                    include_shadow=self.config.include_shadow,
                )
                if job is None:
                    break
                self._track(self._executor.submit(self._execute, job))
                claimed += 1
            self._observe_runtime_metrics()
            if claimed == 0:
                self._stop.wait(self.config.poll_interval_seconds)

        self._executor.shutdown(wait=False, cancel_futures=False)
        deadline = time.monotonic() + self.config.shutdown_grace_seconds
        while self._available_slots() < self.config.stage_slots:
            if time.monotonic() >= deadline:
                log_event(
                    "resource_worker.shutdown_timeout",
                    level="warning",
                    owner_id=self.owner_id,
                )
                return 1
            time.sleep(0.1)
        log_event("resource_worker.stopped", owner_id=self.owner_id)
        set_metric("resource_worker_active_jobs", 0.0)
        return 0


def main() -> int:
    worker = ResourceWorker()
    signal.signal(signal.SIGTERM, worker.request_stop)
    signal.signal(signal.SIGINT, worker.request_stop)
    return worker.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
