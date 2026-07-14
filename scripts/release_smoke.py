#!/usr/bin/env python3
"""Read-only staging release smoke, bounded GET load, and launch gates.

Credentials are read from environment variables only.  The tool never creates
accounts, submits learning events, follows redirects, or prints response bodies
or request headers.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MIN_SAMPLES = 200
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_LOAD_REQUESTS = 200
MAX_LOAD_CONCURRENCY = 10
SAFE_LOAD_PATHS = frozenset(
    {
        "/api/health",
        "/api/ready",
        "/api/courses",
        "/api/user/courses",
        "/api/user/learning-summary",
    }
)
AUTHENTICATED_LOAD_PATHS = frozenset(
    {
        "/api/user/courses",
        "/api/user/learning-summary",
    }
)
INFRASTRUCTURE_LOGIN_REASONS = frozenset(
    {
        "session_persistence_unavailable",
        "storage_unavailable",
    }
)
_MISSING = object()


class SmokeConfigurationError(ValueError):
    """Raised before network I/O when a smoke configuration is unsafe."""


class SmokeCheckError(RuntimeError):
    """Raised when a remote smoke assertion fails."""


class GateState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT = "INSUFFICIENT"
    INVALID = "INVALID"


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    elapsed_ms: float
    payload: Any = field(default=None, repr=False)


@dataclass(frozen=True)
class LoadSample:
    status_code: Optional[int]
    elapsed_ms: float
    transport_error: bool = False


@dataclass(frozen=True)
class GateResult:
    name: str
    state: GateState
    observed: Optional[float]
    threshold: str
    samples: Optional[int]
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "observed": self.observed,
            "threshold": self.threshold,
            "samples": self.samples,
            "reason": self.reason,
        }


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _first_environment(environment: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = str(environment.get(name) or "").strip()
        if value:
            return value
    return ""


def _is_loopback_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def normalize_base_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise SmokeConfigurationError(
            "BASE_URL is required through EDUAGENT_SMOKE_BASE_URL or BASE_URL"
        )
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        raise SmokeConfigurationError("BASE_URL must use http or https")
    if not parsed.hostname:
        raise SmokeConfigurationError("BASE_URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise SmokeConfigurationError("BASE_URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise SmokeConfigurationError("BASE_URL must not contain a query or fragment")
    if parsed.path not in {"", "/"}:
        raise SmokeConfigurationError("BASE_URL must be an origin without a path prefix")
    if parsed.hostname in {"0.0.0.0", "::"}:
        raise SmokeConfigurationError("BASE_URL must identify a concrete target host")
    if parsed.scheme == "http" and not _is_loopback_hostname(parsed.hostname):
        raise SmokeConfigurationError("remote smoke targets must use https")

    try:
        port = parsed.port
    except ValueError as exc:
        raise SmokeConfigurationError("BASE_URL contains an invalid port") from exc
    hostname = parsed.hostname.lower().rstrip(".")
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), host, "", "", ""))


def is_default_safe_load_host(hostname: str) -> bool:
    host = str(hostname or "").lower().rstrip(".")
    if not host:
        return False
    if _is_loopback_hostname(host):
        return True
    if host.endswith(".test") or host.endswith(".internal"):
        return True
    labels = host.split(".")
    return any(
        label == "staging"
        or label.startswith("staging-")
        or label.endswith("-staging")
        for label in labels
    )


def parse_exact_host_allowlist(value: str) -> frozenset[str]:
    hosts: set[str] = set()
    for item in str(value or "").split(","):
        host = item.strip().lower().rstrip(".")
        if not host:
            continue
        if any(char in host for char in "*/:@[]"):
            raise SmokeConfigurationError(
                "EDUAGENT_SMOKE_LOAD_HOST_ALLOWLIST accepts exact hostnames only"
            )
        hosts.add(host)
    return frozenset(hosts)


def load_target_is_allowed(base_url: str, explicit_hosts: Sequence[str] = ()) -> bool:
    host = (urlsplit(normalize_base_url(base_url)).hostname or "").lower().rstrip(".")
    normalized_explicit = {str(item).lower().rstrip(".") for item in explicit_hosts}
    return is_default_safe_load_host(host) or host in normalized_explicit


def validate_read_only_path(path: str, *, load: bool = False) -> str:
    raw = str(path or "").strip()
    parsed = urlsplit(raw)
    if (
        not raw.startswith("/")
        or raw.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or ".." in parsed.path.split("/")
    ):
        raise SmokeConfigurationError("smoke paths must be absolute, query-free local paths")
    if load and raw not in SAFE_LOAD_PATHS:
        raise SmokeConfigurationError("load target is not in the fixed read-only path allowlist")
    return raw


def parse_bounded_int(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool):
        raise SmokeConfigurationError(f"{name} must be an integer")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SmokeConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise SmokeConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def parse_bounded_float(
    value: object,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool):
        raise SmokeConfigurationError(f"{name} must be numeric")
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SmokeConfigurationError(f"{name} must be numeric") from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise SmokeConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_load(samples: Sequence[LoadSample], wall_seconds: float) -> dict[str, Any]:
    if not samples:
        raise ValueError("load summary requires at least one sample")
    if wall_seconds <= 0:
        raise ValueError("wall_seconds must be positive")
    latencies = [sample.elapsed_ms for sample in samples]
    statuses = Counter(
        str(sample.status_code) if sample.status_code is not None else "transport_error"
        for sample in samples
    )
    total = len(samples)
    server_errors = sum(1 for sample in samples if sample.status_code is not None and 500 <= sample.status_code < 600)
    rate_limited = sum(1 for sample in samples if sample.status_code == 429)
    transport_errors = sum(1 for sample in samples if sample.transport_error)
    unexpected = sum(
        1
        for sample in samples
        if sample.status_code is not None
        and not 200 <= sample.status_code < 300
        and sample.status_code != 429
    )
    return {
        "requests": total,
        "throughput_rps": round(total / wall_seconds, 3),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
        },
        "status_counts": dict(sorted(statuses.items())),
        "server_error_rate": round(server_errors / total, 6),
        "rate_limited_429_rate": round(rate_limited / total, 6),
        "transport_error_rate": round(transport_errors / total, 6),
        "unexpected_status_rate": round(unexpected / total, 6),
    }


def _numeric(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def evaluate_rate_gate(
    *,
    name: str,
    rate: object,
    total: object,
    threshold: float,
    direction: str,
    min_samples: int,
) -> GateResult:
    parsed_total = _numeric(total)
    if parsed_total is None or parsed_total < 0 or not parsed_total.is_integer():
        return GateResult(name, GateState.INVALID, None, _threshold_label(direction, threshold), None, "invalid sample count")
    sample_count = int(parsed_total)
    if rate is None:
        return GateResult(name, GateState.INSUFFICIENT, None, _threshold_label(direction, threshold), sample_count, "rate unavailable")
    parsed_rate = _numeric(rate)
    if parsed_rate is None or not 0.0 <= parsed_rate <= 1.0:
        return GateResult(name, GateState.INVALID, None, _threshold_label(direction, threshold), sample_count, "invalid rate")
    if sample_count < min_samples:
        return GateResult(name, GateState.INSUFFICIENT, parsed_rate, _threshold_label(direction, threshold), sample_count, f"requires at least {min_samples} samples")
    if direction == "min_inclusive":
        passed = parsed_rate >= threshold
    elif direction == "max_exclusive":
        passed = parsed_rate < threshold
    else:
        return GateResult(name, GateState.INVALID, parsed_rate, "unknown", sample_count, "invalid gate direction")
    return GateResult(
        name,
        GateState.PASS if passed else GateState.FAIL,
        round(parsed_rate, 6),
        _threshold_label(direction, threshold),
        sample_count,
    )


def _threshold_label(direction: str, threshold: float) -> str:
    operator = ">=" if direction == "min_inclusive" else "<"
    return f"{operator} {threshold:.2%}"


def _mapping_path(payload: Mapping[str, Any], *path: str) -> object:
    current: object = payload
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return _MISSING
        current = current[key]
    return current


def counter_sum(
    metrics_payload: Mapping[str, Any],
    name: str,
    **expected_labels: str,
) -> Optional[int]:
    counters = metrics_payload.get("counters")
    if not isinstance(counters, list):
        return None
    total = 0
    for counter in counters:
        if not isinstance(counter, Mapping) or counter.get("name") != name:
            continue
        labels = counter.get("labels")
        value = counter.get("value")
        if not isinstance(labels, Mapping) or isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        if all(str(labels.get(key)) == str(expected) for key, expected in expected_labels.items()):
            total += value
    return total


def evaluate_release_gates(
    metrics_payload: Mapping[str, Any],
    *,
    frontend_sessions: Optional[int],
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> list[GateResult]:
    launch = metrics_payload.get("launch")
    if not isinstance(launch, Mapping):
        return [
            GateResult(
                "metrics_schema",
                GateState.INVALID,
                None,
                "launch metrics present",
                None,
                "missing launch metrics",
            )
        ]

    results: list[GateResult] = []

    def section_gate(
        name: str,
        section: str,
        rate_key: str,
        total_key: str,
        threshold: float,
        direction: str,
    ) -> None:
        rate = _mapping_path(launch, section, rate_key)
        total = _mapping_path(launch, section, total_key)
        results.append(
            evaluate_rate_gate(
                name=name,
                rate=None if rate is _MISSING else rate,
                total=-1 if total is _MISSING else total,
                threshold=threshold,
                direction=direction,
                min_samples=min_samples,
            )
        )

    section_gate("refresh_recovery", "refresh_recovery", "rate", "total", 0.99, "min_inclusive")
    section_gate("next_task_within_5s", "next_task_ready", "rate", "total", 0.99, "min_inclusive")
    next_task_target = _numeric(_mapping_path(launch, "next_task_ready", "target_ms"))
    if next_task_target != 5000:
        results[-1] = GateResult(
            "next_task_within_5s",
            GateState.INVALID,
            results[-1].observed,
            ">= 99.00% with target_ms = 5000",
            results[-1].samples,
            "next-task target is not 5000 ms",
        )
    section_gate("resource_failure", "resource_failure", "rate", "total", 0.01, "max_exclusive")
    section_gate(
        "code_infrastructure_failure",
        "code_execution_failure",
        "infrastructure_rate",
        "total",
        0.01,
        "max_exclusive",
    )

    login_total = _mapping_path(launch, "login_failure", "total")
    raw_login_total = counter_sum(metrics_payload, "auth.login_total")
    infra_login_failures: Optional[int] = 0
    for reason in INFRASTRUCTURE_LOGIN_REASONS:
        value = counter_sum(
            metrics_payload,
            "auth.login_total",
            outcome="failure",
            reason=reason,
        )
        if value is None:
            infra_login_failures = None
            break
        infra_login_failures += value
    parsed_login_total = _numeric(login_total)
    login_rate = (
        None
        if infra_login_failures is None or parsed_login_total is None or parsed_login_total <= 0
        else infra_login_failures / parsed_login_total
    )
    login_gate = evaluate_rate_gate(
        name="login_infrastructure_failure",
        rate=login_rate,
        total=-1 if login_total is _MISSING else login_total,
        threshold=0.01,
        direction="max_exclusive",
        min_samples=min_samples,
    )
    if (
        parsed_login_total is None
        or raw_login_total is None
        or raw_login_total != int(parsed_login_total)
    ):
        login_gate = GateResult(
            "login_infrastructure_failure",
            GateState.INVALID,
            None,
            "< 1.00%",
            None if parsed_login_total is None else int(parsed_login_total),
            "raw login counters do not match launch total",
        )
    results.append(login_gate)

    exception_total = _mapping_path(launch, "frontend_exceptions", "total")
    parsed_exceptions = _numeric(exception_total)
    frontend_rate = (
        None
        if frontend_sessions is None or frontend_sessions <= 0 or parsed_exceptions is None
        else parsed_exceptions / frontend_sessions
    )
    results.append(
        evaluate_rate_gate(
            name="frontend_exception_sessions",
            rate=frontend_rate,
            total=0 if frontend_sessions is None else frontend_sessions,
            threshold=0.01,
            direction="max_exclusive",
            min_samples=min_samples,
        )
    )

    section_gate(
        "mastery_attribution_integrity",
        "mastery_attribution_integrity",
        "rate",
        "total",
        1.0,
        "min_inclusive",
    )
    unattributed = _mapping_path(launch, "mastery_attribution_integrity", "unattributed")
    parsed_unattributed = _numeric(unattributed)
    if parsed_unattributed is None or parsed_unattributed < 0 or not parsed_unattributed.is_integer():
        results[-1] = GateResult(
            "mastery_attribution_integrity",
            GateState.INVALID,
            None,
            ">= 100.00% and zero unattributed mutations",
            results[-1].samples,
            "invalid unattributed mutation count",
        )
    elif parsed_unattributed > 0:
        results[-1] = GateResult(
            "mastery_attribution_integrity",
            GateState.FAIL,
            results[-1].observed,
            ">= 100.00% and zero unattributed mutations",
            results[-1].samples,
            "unattributed mastery mutation observed",
        )
    return results


def aggregate_gate_state(results: Sequence[GateResult]) -> GateState:
    states = {result.state for result in results}
    for state in (GateState.INVALID, GateState.FAIL, GateState.INSUFFICIENT):
        if state in states:
            return state
    return GateState.PASS


def _decode_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def get_json(
    base_url: str,
    path: str,
    *,
    timeout_seconds: float,
    authorization_token: str = "",
    ops_token: str = "",
) -> HttpResult:
    safe_base = normalize_base_url(base_url)
    safe_path = validate_read_only_path(path)
    headers = {
        "Accept": "application/json",
        "User-Agent": "EduAgent-Release-Smoke/1.0",
    }
    if authorization_token:
        headers["Authorization"] = f"Bearer {authorization_token}"
    if ops_token:
        headers["X-EduAgent-Ops-Token"] = ops_token
    request = Request(urljoin(f"{safe_base}/", safe_path.lstrip("/")), headers=headers, method="GET")
    opener = build_opener(_NoRedirectHandler())
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SmokeCheckError("response exceeded the smoke size limit")
            return HttpResult(
                status_code=int(response.status),
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                payload=_decode_json(raw),
            )
    except HTTPError as error:
        raw = error.read(MAX_RESPONSE_BYTES + 1)
        return HttpResult(
            status_code=int(error.code),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            payload=_decode_json(raw),
        )
    except (TimeoutError, URLError, OSError) as error:
        raise SmokeCheckError(f"GET {safe_path} failed ({type(error).__name__})") from None


def _assert_response(
    result: HttpResult,
    *,
    path: str,
    expected_status: int,
    expected_payload_status: str = "",
) -> None:
    if result.status_code != expected_status:
        raise SmokeCheckError(
            f"GET {path} returned {result.status_code}; expected {expected_status}"
        )
    if expected_payload_status:
        actual = result.payload.get("status") if isinstance(result.payload, Mapping) else None
        if actual != expected_payload_status:
            raise SmokeCheckError(f"GET {path} returned an invalid status payload")


def run_preflight(
    *,
    base_url: str,
    access_token: str,
    timeout_seconds: float,
    session_id: str = "",
    node_id: str = "",
) -> dict[str, Any]:
    if not access_token:
        raise SmokeConfigurationError(
            "ACCESS_TOKEN is required through EDUAGENT_SMOKE_ACCESS_TOKEN or ACCESS_TOKEN"
        )
    checks: list[dict[str, Any]] = []

    def check(
        path: str,
        expected_status: int,
        *,
        token: str = "",
        payload_status: str = "",
        name: str,
    ) -> None:
        result = get_json(
            base_url,
            path,
            timeout_seconds=timeout_seconds,
            authorization_token=token,
        )
        _assert_response(
            result,
            path=path,
            expected_status=expected_status,
            expected_payload_status=payload_status,
        )
        checks.append(
            {
                "name": name,
                "status_code": result.status_code,
                "elapsed_ms": result.elapsed_ms,
            }
        )

    check("/api/health", 200, payload_status="ok", name="liveness")
    check("/api/ready", 200, payload_status="ready", name="readiness")
    check("/api/state", 404, name="legacy_state_hidden")
    check("/api/agents/status", 404, name="legacy_agents_hidden")
    check("/api/ops/metrics", 404, name="metrics_private_without_ops_token")
    check("/api/user/courses", 401, name="user_api_requires_authentication")
    check("/api/user/courses", 200, token=access_token, name="authenticated_courses")
    check(
        "/api/user/learning-summary",
        200,
        token=access_token,
        name="authenticated_learning_summary",
    )
    check("/api/user/profile", 200, token=access_token, name="authenticated_profile")
    check("/api/user/settings", 200, token=access_token, name="authenticated_settings")

    session_checks = "not_configured"
    if session_id:
        encoded_session = quote(session_id, safe="")
        for suffix, name in (
            ("", "session_restore"),
            ("/events", "learning_event_history"),
            ("/assets", "learning_assets_restore"),
            ("/review", "review_queue_restore"),
        ):
            check(
                f"/api/sessions/{encoded_session}{suffix}",
                200,
                token=access_token,
                name=name,
            )
        if node_id:
            check(
                f"/api/sessions/{encoded_session}/resources/{quote(node_id, safe='')}",
                200,
                token=access_token,
                name="node_resources_restore",
            )
        session_checks = "passed"

    return {
        "command": "preflight",
        "status": "PASS",
        "checks": checks,
        "session_reads": session_checks,
        "notes": [
            "read-only smoke; no account or learning event was created",
            "full P1 state-changing flow must be recorded separately against the real staging backend",
        ],
    }


def run_load(
    *,
    base_url: str,
    path: str,
    access_token: str,
    requests: int,
    concurrency: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    safe_path = validate_read_only_path(path, load=True)
    if safe_path in AUTHENTICATED_LOAD_PATHS and not access_token:
        raise SmokeConfigurationError("the selected load target requires ACCESS_TOKEN")
    token = access_token if safe_path in AUTHENTICATED_LOAD_PATHS else ""

    def one_request() -> LoadSample:
        started = time.perf_counter()
        try:
            result = get_json(
                base_url,
                safe_path,
                timeout_seconds=timeout_seconds,
                authorization_token=token,
            )
            return LoadSample(result.status_code, result.elapsed_ms)
        except SmokeCheckError:
            return LoadSample(
                None,
                round((time.perf_counter() - started) * 1000, 3),
                transport_error=True,
            )

    wall_started = time.perf_counter()
    samples: list[LoadSample] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(one_request) for _ in range(requests)]
        for future in as_completed(futures):
            samples.append(future.result())
    wall_seconds = time.perf_counter() - wall_started
    return {
        "command": "load",
        "target_path": safe_path,
        "summary": summarize_load(samples, wall_seconds),
        "scope": "bounded read-only staging smoke; not a production capacity certification",
    }


def _environment_config(environment: Mapping[str, str]) -> dict[str, Any]:
    base_url = normalize_base_url(
        _first_environment(environment, "EDUAGENT_SMOKE_BASE_URL", "BASE_URL")
    )
    timeout_seconds = parse_bounded_float(
        environment.get("EDUAGENT_SMOKE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        name="EDUAGENT_SMOKE_TIMEOUT_SECONDS",
        minimum=0.5,
        maximum=30.0,
    )
    return {
        "base_url": base_url,
        "timeout_seconds": timeout_seconds,
        "access_token": _first_environment(
            environment,
            "EDUAGENT_SMOKE_ACCESS_TOKEN",
            "ACCESS_TOKEN",
        ),
        "ops_token": _first_environment(
            environment,
            "EDUAGENT_SMOKE_OPS_TOKEN",
            "EDUAGENT_OPS_TOKEN",
            "OPS_TOKEN",
        ),
        "session_id": str(environment.get("EDUAGENT_SMOKE_SESSION_ID") or "").strip(),
        "node_id": str(environment.get("EDUAGENT_SMOKE_NODE_ID") or "").strip(),
    }


def _print_report(report: Mapping[str, Any], *, stream) -> None:  # noqa: ANN001
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), file=stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only EduAgent staging release smoke and launch gates.",
    )
    parser.add_argument(
        "command",
        choices=("preflight", "gates", "load"),
        help="preflight fixed GET checks, evaluate launch gates, or run bounded GET load",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None, environment: Optional[Mapping[str, str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    source = os.environ if environment is None else environment
    try:
        config = _environment_config(source)
        if arguments.command == "preflight":
            report = run_preflight(
                base_url=config["base_url"],
                access_token=config["access_token"],
                timeout_seconds=config["timeout_seconds"],
                session_id=config["session_id"],
                node_id=config["node_id"],
            )
            _print_report(report, stream=sys.stdout)
            return 0

        if arguments.command == "gates":
            if not config["ops_token"]:
                raise SmokeConfigurationError(
                    "OPS_TOKEN is required through EDUAGENT_SMOKE_OPS_TOKEN, EDUAGENT_OPS_TOKEN, or OPS_TOKEN"
                )
            min_samples = parse_bounded_int(
                source.get("EDUAGENT_SMOKE_MIN_SAMPLES", DEFAULT_MIN_SAMPLES),
                name="EDUAGENT_SMOKE_MIN_SAMPLES",
                minimum=1,
                maximum=1_000_000,
            )
            raw_sessions = str(source.get("EDUAGENT_SMOKE_FRONTEND_SESSIONS") or "").strip()
            frontend_sessions = (
                None
                if not raw_sessions
                else parse_bounded_int(
                    raw_sessions,
                    name="EDUAGENT_SMOKE_FRONTEND_SESSIONS",
                    minimum=1,
                    maximum=1_000_000_000,
                )
            )
            response = get_json(
                config["base_url"],
                "/api/ops/metrics",
                timeout_seconds=config["timeout_seconds"],
                ops_token=config["ops_token"],
            )
            _assert_response(response, path="/api/ops/metrics", expected_status=200)
            if not isinstance(response.payload, Mapping):
                raise SmokeCheckError("metrics endpoint returned invalid JSON")
            gates = evaluate_release_gates(
                response.payload,
                frontend_sessions=frontend_sessions,
                min_samples=min_samples,
            )
            state = aggregate_gate_state(gates)
            _print_report(
                {
                    "command": "gates",
                    "status": state.value,
                    "gates": [gate.as_dict() for gate in gates],
                    "scope": "single-instance cumulative snapshot; external windowed evidence is required for canary promotion",
                },
                stream=sys.stdout,
            )
            if state == GateState.PASS:
                return 0
            if state == GateState.INSUFFICIENT:
                return 3
            if state == GateState.INVALID:
                return 2
            return 1

        if str(source.get("EDUAGENT_SMOKE_ALLOW_LOAD") or "").strip().lower() != "true":
            raise SmokeConfigurationError(
                "load requires EDUAGENT_SMOKE_ALLOW_LOAD=true"
            )
        explicit_hosts = parse_exact_host_allowlist(
            str(source.get("EDUAGENT_SMOKE_LOAD_HOST_ALLOWLIST") or "")
        )
        if not load_target_is_allowed(config["base_url"], explicit_hosts):
            raise SmokeConfigurationError(
                "load target is not localhost, .test, .internal, a staging host, or an exact approved host"
            )
        requests = parse_bounded_int(
            source.get("EDUAGENT_SMOKE_LOAD_REQUESTS", 100),
            name="EDUAGENT_SMOKE_LOAD_REQUESTS",
            minimum=1,
            maximum=MAX_LOAD_REQUESTS,
        )
        concurrency = parse_bounded_int(
            source.get("EDUAGENT_SMOKE_LOAD_CONCURRENCY", 5),
            name="EDUAGENT_SMOKE_LOAD_CONCURRENCY",
            minimum=1,
            maximum=MAX_LOAD_CONCURRENCY,
        )
        safe_load_path = validate_read_only_path(
            str(source.get("EDUAGENT_SMOKE_LOAD_PATH") or "/api/ready"),
            load=True,
        )
        if safe_load_path in AUTHENTICATED_LOAD_PATHS and not config["access_token"]:
            raise SmokeConfigurationError("the selected load target requires ACCESS_TOKEN")
        max_p95 = parse_bounded_float(
            source.get("EDUAGENT_SMOKE_LOAD_MAX_P95_MS", 2000),
            name="EDUAGENT_SMOKE_LOAD_MAX_P95_MS",
            minimum=1,
            maximum=120_000,
        )
        max_429_rate = parse_bounded_float(
            source.get("EDUAGENT_SMOKE_LOAD_MAX_429_RATE", 0.05),
            name="EDUAGENT_SMOKE_LOAD_MAX_429_RATE",
            minimum=0,
            maximum=1,
        )
        readiness = get_json(
            config["base_url"],
            "/api/ready",
            timeout_seconds=config["timeout_seconds"],
        )
        _assert_response(
            readiness,
            path="/api/ready",
            expected_status=200,
            expected_payload_status="ready",
        )
        report = run_load(
            base_url=config["base_url"],
            path=safe_load_path,
            access_token=config["access_token"],
            requests=requests,
            concurrency=concurrency,
            timeout_seconds=config["timeout_seconds"],
        )
        summary = report["summary"]
        passed = (
            summary["server_error_rate"] < 0.01
            and summary["transport_error_rate"] == 0
            and summary["unexpected_status_rate"] == 0
            and summary["rate_limited_429_rate"] <= max_429_rate
            and summary["latency_ms"]["p95"] <= max_p95
        )
        report["status"] = "PASS" if passed else "FAIL"
        report["limits"] = {
            "server_error_rate": "< 1%",
            "transport_error_rate": "0%",
            "unexpected_status_rate": "0%",
            "rate_limited_429_rate": f"<= {max_429_rate:.2%}",
            "p95_ms": f"<= {max_p95:g}",
        }
        _print_report(report, stream=sys.stdout)
        return 0 if passed else 1
    except SmokeConfigurationError as error:
        _print_report(
            {"status": "INVALID", "error": str(error)},
            stream=sys.stderr,
        )
        return 2
    except SmokeCheckError as error:
        _print_report(
            {"status": "FAIL", "error": str(error)},
            stream=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
