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

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        start_http_server,
    )
except ImportError:  # pragma: no cover - optional in minimal local installs
    Counter = Gauge = Histogram = None  # type: ignore[assignment]
    generate_latest = None  # type: ignore[assignment]
    start_http_server = None  # type: ignore[assignment]

try:
    from opentelemetry import trace
except ImportError:  # pragma: no cover
    trace = None  # type: ignore[assignment]


_REQUEST_CONTEXT: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "eduagent_request_context",
    default={},
)

_LOGGER = logging.getLogger("eduagent")
_LOGGING_LOCK = threading.Lock()
_LOGGING_CONFIGURED = False
_PROMETHEUS_LOCK = threading.Lock()
_PROMETHEUS_COLLECTORS: Dict[Tuple[str, str, Tuple[str, ...]], Any] = {}
_PROMETHEUS_SERVER_STARTED = False
_FORBIDDEN_METRIC_LABELS = frozenset({
    "user",
    "user_id",
    "email",
    "job_id",
    "trace_id",
    "request_id",
})
_METRIC_CONTEXT_LABELS = frozenset({
    "release",
    "pipeline_version",
    "cohort",
    "card_type",
    "provider",
    "gate_status",
})
# Prometheus collectors cannot change their label schema after registration.
# A fixed bounded schema keeps canonical metric names stable across call sites
# while retaining the dimensions used by production alerts and rollout gates.
_PROMETHEUS_LABEL_NAMES = (
    "release",
    "pipeline_version",
    "cohort",
    "card_type",
    "provider",
    "gate_status",
    "outcome",
    "operation",
    "fallback",
    "reason",
    "lane",
    "stage",
    "code",
    "source",
    "event_type",
    "advanced",
    "mode",
    "verdict",
    "surface",
    "kind",
    "method",
    "status_family",
    "cache_hit",
    "algorithm",
)


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


def _safe_metric_labels(labels: Dict[str, Any]) -> Dict[str, str]:
    context = get_request_context()
    merged = {
        key: context[key]
        for key in _METRIC_CONTEXT_LABELS
        if context.get(key) is not None and context.get(key) != ""
    }
    if os.environ.get("RELEASE_VERSION") and "release" not in merged:
        merged["release"] = os.environ["RELEASE_VERSION"]
    merged.update(labels)
    return {
        str(key): str(value)
        for key, value in merged.items()
        if key not in _FORBIDDEN_METRIC_LABELS
        and value is not None
        and value != ""
    }


def _prometheus_name(name: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char == "_" else "_"
        for char in str(name)
    )
    return normalized.strip("_") or "eduagent_metric"


def _prometheus_observe(
    kind: str,
    name: str,
    value: float,
    labels: Dict[str, Any],
) -> None:
    collector_type = {
        "counter": Counter,
        "gauge": Gauge,
        "histogram": Histogram,
    }.get(kind)
    if collector_type is None:
        return
    safe_labels = _safe_metric_labels(labels)
    label_names = _PROMETHEUS_LABEL_NAMES
    metric_labels = {
        label_name: safe_labels.get(label_name, "")
        for label_name in label_names
    }
    metric_name = _prometheus_name(name)
    key = (kind, metric_name, label_names)
    with _PROMETHEUS_LOCK:
        collector = _PROMETHEUS_COLLECTORS.get(key)
        if collector is None:
            collector = collector_type(
                metric_name,
                f"EduAgent metric {name}",
                labelnames=label_names,
            )
            _PROMETHEUS_COLLECTORS[key] = collector
    target = collector.labels(**metric_labels)
    if kind == "counter":
        target.inc(value)
    elif kind == "gauge":
        target.set(value)
    else:
        target.observe(value)


class InMemoryMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], int] = {}
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
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
                {"count": 0.0, "sum": 0.0, "max": 0.0, "samples": []},
            )
            bucket["count"] += 1.0
            bucket["sum"] += float(value)
            bucket["max"] = max(bucket["max"], float(value))
            samples = bucket["samples"]
            samples.append(float(value))
            # Keep percentile calculations bounded for the in-process metric
            # backend while retaining a representative rolling sample.
            if len(samples) > 2048:
                del samples[: len(samples) - 2048]

    def set(self, name: str, value: float, **labels: Any) -> None:
        key = _metric_key(name, labels)
        with self._lock:
            self._gauges[key] = float(value)

    @staticmethod
    def _percentile(samples: list[float], percentile: float) -> float:
        if not samples:
            return 0.0
        ordered = sorted(samples)
        index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
        return ordered[index]

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
            gauges = [
                {
                    "name": name,
                    "labels": dict(label_items),
                    "value": value,
                }
                for (name, label_items), value in sorted(self._gauges.items())
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
                        "p50": round(self._percentile(bucket.get("samples", []), 0.50), 3),
                        "p95": round(self._percentile(bucket.get("samples", []), 0.95), 3),
                        "max": round(bucket["max"], 3),
                    }
                )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "request_id": get_request_id(),
            "counters": counters,
            "gauges": gauges,
            "histograms": histograms,
        }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


metrics = InMemoryMetrics()


def incr_metric(name: str, amount: int = 1, **labels: Any) -> None:
    safe_labels = _safe_metric_labels(labels)
    metrics.incr(name, amount=amount, **safe_labels)
    _prometheus_observe("counter", name, float(amount), safe_labels)


def observe_metric(name: str, value: float, **labels: Any) -> None:
    safe_labels = _safe_metric_labels(labels)
    metrics.observe(name, value=value, **safe_labels)
    _prometheus_observe("histogram", name, float(value), safe_labels)


def set_metric(name: str, value: float, **labels: Any) -> None:
    safe_labels = _safe_metric_labels(labels)
    metrics.set(name, value=value, **safe_labels)
    _prometheus_observe("gauge", name, float(value), safe_labels)


def prometheus_metrics_text() -> bytes:
    return generate_latest() if generate_latest is not None else b""


def start_prometheus_metrics_server(
    port: int,
    *,
    address: str = "0.0.0.0",
) -> bool:
    """Start one process-local Prometheus endpoint without changing API routes."""
    global _PROMETHEUS_SERVER_STARTED
    if start_http_server is None:
        return False
    safe_port = max(1, min(65_535, int(port)))
    with _PROMETHEUS_LOCK:
        if _PROMETHEUS_SERVER_STARTED:
            return True
        start_http_server(safe_port, addr=str(address or "0.0.0.0"))
        _PROMETHEUS_SERVER_STARTED = True
    return True


def _start_configured_prometheus_server() -> None:
    raw_port = str(os.environ.get("EDUAGENT_PROMETHEUS_PORT") or "").strip()
    if not raw_port:
        return
    try:
        port = int(raw_port)
    except ValueError:
        return
    start_prometheus_metrics_server(
        port,
        address=str(
            os.environ.get("EDUAGENT_PROMETHEUS_ADDRESS") or "0.0.0.0"
        ),
    )


@contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[Any]:
    if trace is None:
        yield None
        return
    tracer = trace.get_tracer("eduagent.resource-v4")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(str(key), _normalize_value(value))
        yield span


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
    login_infrastructure_failed = sum(
        metrics.counter_sum("auth.login_total", outcome="failure", reason=reason)
        for reason in ("session_persistence_unavailable", "storage_unavailable")
    )

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
    frontend_sessions = metrics.counter_sum("frontend.session_total")
    frontend_exceptions = metrics.counter_sum("frontend.exception_total")

    completion_attempts = metrics.counter_sum("learning.node_completion_attempt_total")
    completion_accepted = metrics.counter_sum("learning.node_completion_total")
    completion_advanced = metrics.counter_sum("learning.node_completion_total", advanced="true")
    mastery_mutations = metrics.counter_sum("learning_event.mastery_mutation_total")
    attributed_mastery_mutations = metrics.counter_sum(
        "learning_event.mastery_mutation_total",
        outcome="attributed",
    )
    unattributed_mastery_mutations = metrics.counter_sum(
        "learning_event.mastery_mutation_total",
        outcome="unattributed",
    )

    return {
        "login_failure": {
            "failed": login_failed,
            "infrastructure_failed": login_infrastructure_failed,
            "total": login_total,
            "rate": _rate(login_failed, login_total),
            "infrastructure_rate": _rate(login_infrastructure_failed, login_total),
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
            "total": frontend_exceptions,
            "sessions": frontend_sessions,
            "rate": _rate(frontend_exceptions, frontend_sessions),
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
            "definition": "accepted terminal event submissions / terminal event submissions",
            "authoritative_completion_rate_source": "session event history learning_funnel",
            "advanced": completion_advanced,
            "advanced_rate": _rate(completion_advanced, completion_accepted),
            "total": completion_accepted,
        },
        "refresh_recovery": {
            "successful": refresh_success,
            "total": refresh_total,
            "rate": _rate(refresh_success, refresh_total),
        },
        "mastery_attribution_integrity": {
            "attributed": attributed_mastery_mutations,
            "unattributed": unattributed_mastery_mutations,
            "total": mastery_mutations,
            "rate": _rate(attributed_mastery_mutations, mastery_mutations),
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


_start_configured_prometheus_server()
