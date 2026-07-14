from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional, Tuple


_REQUEST_CONTEXT: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "eduagent_request_context",
    default={},
)

_LOGGER = logging.getLogger("eduagent")
_LOGGING_LOCK = threading.Lock()
_LOGGING_CONFIGURED = False


def configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    with _LOGGING_LOCK:
        if _LOGGING_CONFIGURED:
            return
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        _LOGGER.handlers.clear()
        _LOGGER.addHandler(handler)
        level_name = os.environ.get("EDUAGENT_LOG_LEVEL", "INFO").upper()
        _LOGGER.setLevel(getattr(logging, level_name, logging.INFO))
        _LOGGER.propagate = False
        _LOGGING_CONFIGURED = True


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_context() -> Dict[str, Any]:
    return dict(_REQUEST_CONTEXT.get({}))


def get_request_id(default: str = "") -> str:
    return str(get_request_context().get("request_id") or default)


@contextmanager
def bind_context(**fields: Any) -> Iterator[Dict[str, Any]]:
    current = get_request_context()
    next_context = dict(current)
    next_context.update(
        {
            key: value
            for key, value in fields.items()
            if value is not None and value != ""
        }
    )
    token = _REQUEST_CONTEXT.set(next_context)
    try:
        yield next_context
    finally:
        _REQUEST_CONTEXT.reset(token)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return str(value)


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    configure_logging()
    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.lower(),
        "event": event,
    }
    payload.update(get_request_context())
    payload.update({key: _normalize_value(value) for key, value in fields.items()})
    log_level = getattr(logging, level.upper(), logging.INFO)
    _LOGGER.log(log_level, json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _metric_key(name: str, labels: Dict[str, Any]) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    normalized = tuple(
        sorted(
            (
                str(key),
                str(value),
            )
            for key, value in labels.items()
            if value is not None and value != ""
        )
    )
    return name, normalized


class InMemoryMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], int] = {}
        self._histograms: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, float]] = {}

    def incr(self, name: str, amount: int = 1, **labels: Any) -> None:
        key = _metric_key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + amount

    def observe(self, name: str, value: float, **labels: Any) -> None:
        key = _metric_key(name, labels)
        with self._lock:
            bucket = self._histograms.setdefault(
                key,
                {"count": 0.0, "sum": 0.0, "max": 0.0},
            )
            bucket["count"] += 1.0
            bucket["sum"] += float(value)
            bucket["max"] = max(bucket["max"], float(value))

    def counter_value(self, name: str, **labels: Any) -> int:
        key = _metric_key(name, labels)
        with self._lock:
            return int(self._counters.get(key, 0))

    def counter_sum(self, name: str, **labels: Any) -> int:
        expected = {
            str(key): str(value)
            for key, value in labels.items()
            if value is not None and value != ""
        }
        with self._lock:
            return int(sum(
                value
                for (metric_name, label_items), value in self._counters.items()
                if metric_name == name
                and all(dict(label_items).get(key) == value for key, value in expected.items())
            ))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            counters = [
                {
                    "name": name,
                    "labels": dict(label_items),
                    "value": value,
                }
                for (name, label_items), value in sorted(self._counters.items())
            ]
            histograms = []
            for (name, label_items), bucket in sorted(self._histograms.items()):
                count = int(bucket["count"])
                avg = bucket["sum"] / bucket["count"] if bucket["count"] else 0.0
                histograms.append(
                    {
                        "name": name,
                        "labels": dict(label_items),
                        "count": count,
                        "avg": round(avg, 3),
                        "max": round(bucket["max"], 3),
                    }
                )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "request_id": get_request_id(),
            "counters": counters,
            "histograms": histograms,
        }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()


metrics = InMemoryMetrics()


def incr_metric(name: str, amount: int = 1, **labels: Any) -> None:
    metrics.incr(name, amount=amount, **labels)


def observe_metric(name: str, value: float, **labels: Any) -> None:
    metrics.observe(name, value=value, **labels)


def metrics_snapshot() -> Dict[str, Any]:
    snapshot = metrics.snapshot()
    snapshot["launch"] = launch_metrics_snapshot()
    return snapshot


def _rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def launch_metrics_snapshot() -> Dict[str, Any]:
    login_failed = metrics.counter_sum("auth.login_total", outcome="failure")
    login_total = metrics.counter_sum("auth.login_total")

    resource_failed = metrics.counter_sum("resource.generate_total", outcome="failure")
    resource_total = metrics.counter_sum("resource.generate_total")

    code_accepted = metrics.counter_sum("code.execution_total", outcome="accepted")
    code_test_failed = metrics.counter_sum("code.execution_total", outcome="test_failed")
    code_infrastructure_failed = metrics.counter_sum(
        "code.execution_total",
        outcome="infrastructure_failure",
    )
    code_total = code_accepted + code_test_failed + code_infrastructure_failed
    code_failed = code_test_failed + code_infrastructure_failed

    refresh_success = metrics.counter_sum("frontend.refresh_recovery_total", outcome="success")
    refresh_failure = metrics.counter_sum("frontend.refresh_recovery_total", outcome="failure")
    refresh_total = refresh_success + refresh_failure

    task_ready_within_target = metrics.counter_sum("frontend.next_task_ready_total", outcome="within_5s")
    task_ready_over_target = metrics.counter_sum("frontend.next_task_ready_total", outcome="over_5s")
    task_ready_total = task_ready_within_target + task_ready_over_target

    completion_attempts = metrics.counter_sum("learning.node_completion_attempt_total")
    completion_accepted = metrics.counter_sum("learning.node_completion_total")
    completion_advanced = metrics.counter_sum("learning.node_completion_total", advanced="true")

    return {
        "login_failure": {
            "failed": login_failed,
            "total": login_total,
            "rate": _rate(login_failed, login_total),
        },
        "resource_failure": {
            "failed": resource_failed,
            "total": resource_total,
            "rate": _rate(resource_failed, resource_total),
        },
        "code_execution_failure": {
            "failed": code_failed,
            "infrastructure_failed": code_infrastructure_failed,
            "total": code_total,
            "rate": _rate(code_failed, code_total),
            "infrastructure_rate": _rate(code_infrastructure_failed, code_total),
        },
        "frontend_exceptions": {
            "total": metrics.counter_sum("frontend.exception_total"),
        },
        "next_task_ready": {
            "within_5s": task_ready_within_target,
            "total": task_ready_total,
            "rate": _rate(task_ready_within_target, task_ready_total),
            "target_ms": 5000,
        },
        "node_completions": {
            "attempted": completion_attempts,
            "accepted": completion_accepted,
            "rate": _rate(completion_accepted, completion_attempts),
            "advanced": completion_advanced,
            "advanced_rate": _rate(completion_advanced, completion_accepted),
            "total": completion_accepted,
        },
        "refresh_recovery": {
            "successful": refresh_success,
            "total": refresh_total,
            "rate": _rate(refresh_success, refresh_total),
        },
    }


def reset_metrics() -> None:
    metrics.reset()


@contextmanager
def timed_operation(
    metric_name: Optional[str] = None,
    *,
    event_name: Optional[str] = None,
    level: str = "info",
    **labels: Any,
) -> Iterator[float]:
    started = time.perf_counter()
    try:
        yield started
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        if metric_name:
            observe_metric(metric_name, duration_ms, **labels)
        if event_name:
            log_event(event_name, level=level, duration_ms=duration_ms, **labels)
