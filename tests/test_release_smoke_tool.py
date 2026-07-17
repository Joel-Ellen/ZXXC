from __future__ import annotations

import math

import pytest

from scripts.release_smoke import (
    GateState,
    LoadSample,
    SmokeConfigurationError,
    aggregate_gate_state,
    evaluate_rate_gate,
    evaluate_release_gates,
    is_default_safe_load_host,
    load_target_is_allowed,
    main,
    normalize_base_url,
    parse_exact_host_allowlist,
    percentile,
    summarize_load,
    validate_read_only_path,
)


def _metrics_payload(*, total: int = 200) -> dict:
    return {
        "counters": [
            {
                "name": "auth.login_total",
                "labels": {"outcome": "success", "reason": "authenticated"},
                "value": total,
            },
        ],
        "launch": {
            "login_failure": {"failed": 0, "total": total, "rate": 0.0},
            "resource_failure": {"failed": 0, "total": total, "rate": 0.0},
            "code_execution_failure": {
                "failed": total,
                "infrastructure_failed": 0,
                "total": total,
                "rate": 1.0,
                "infrastructure_rate": 0.0,
            },
            "frontend_exceptions": {"total": 0},
            "next_task_ready": {
                "within_5s": total,
                "total": total,
                "rate": 1.0,
                "target_ms": 5000,
            },
            "refresh_recovery": {
                "successful": total,
                "total": total,
                "rate": 1.0,
            },
            "mastery_attribution_integrity": {
                "attributed": total,
                "unattributed": 0,
                "total": total,
                "rate": 1.0,
            },
        },
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("http://localhost:8800/", "http://localhost:8800"),
        ("http://127.0.0.1:8800", "http://127.0.0.1:8800"),
        ("http://[::1]:8800", "http://[::1]:8800"),
        ("https://STAGING.example.com/", "https://staging.example.com"),
    ),
)
def test_normalize_base_url_accepts_only_safe_origins(value: str, expected: str) -> None:
    assert normalize_base_url(value) == expected


@pytest.mark.parametrize(
    "value",
    (
        "",
        "ftp://staging.example.com",
        "http://staging.example.com",
        "https://user:password@staging.example.com",
        "https://staging.example.com/api",
        "https://staging.example.com?redirect=production",
        "https://staging.example.com#fragment",
        "https://staging.example.com:not-a-port",
        "http://0.0.0.0:8800",
    ),
)
def test_normalize_base_url_rejects_unsafe_targets(value: str) -> None:
    with pytest.raises(SmokeConfigurationError):
        normalize_base_url(value)


@pytest.mark.parametrize(
    "hostname",
    (
        "localhost",
        "api.localhost",
        "127.0.0.1",
        "::1",
        "eduagent.test",
        "eduagent.internal",
        "staging.example.com",
        "api.staging.example.com",
        "eduagent-staging.example.com",
    ),
)
def test_default_load_hosts_are_bounded_to_nonproduction_names(hostname: str) -> None:
    assert is_default_safe_load_host(hostname) is True


@pytest.mark.parametrize(
    "hostname",
    (
        "example.com",
        "production.example.com",
        "evilstaging.example.com",
        "stagingevil.example.com",
        "0.0.0.0",
    ),
)
def test_default_load_hosts_reject_production_and_suffix_traps(hostname: str) -> None:
    assert is_default_safe_load_host(hostname) is False


def test_exact_load_host_override_has_no_wildcard_or_suffix_matching() -> None:
    hosts = parse_exact_host_allowlist("qa.example.com, load.example.net")
    assert load_target_is_allowed("https://qa.example.com", hosts) is True
    assert load_target_is_allowed("https://not-qa.example.com", hosts) is False
    with pytest.raises(SmokeConfigurationError):
        parse_exact_host_allowlist("*.example.com")


@pytest.mark.parametrize(
    "path",
    (
        "https://staging.example.com/api/ready",
        "//staging.example.com/api/ready",
        "/api/ready?force=true",
        "/api/../reset",
        "api/ready",
    ),
)
def test_read_only_path_rejects_remote_query_and_traversal_forms(path: str) -> None:
    with pytest.raises(SmokeConfigurationError):
        validate_read_only_path(path, load=True)


def test_load_path_is_a_fixed_get_allowlist() -> None:
    assert validate_read_only_path("/api/ready", load=True) == "/api/ready"
    assert validate_read_only_path("/api/user/courses", load=True) == "/api/user/courses"
    with pytest.raises(SmokeConfigurationError):
        validate_read_only_path("/api/auth/login", load=True)
    with pytest.raises(SmokeConfigurationError):
        validate_read_only_path("/api/sessions", load=True)


def test_percentile_uses_linear_interpolation() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 0.5) == 25.0
    assert percentile(values, 0.95) == pytest.approx(38.5)
    assert percentile(values, 0.99) == pytest.approx(39.7)


def test_load_summary_reports_latency_throughput_5xx_and_429() -> None:
    summary = summarize_load(
        [
            LoadSample(200, 10),
            LoadSample(200, 20),
            LoadSample(429, 30),
            LoadSample(503, 40),
            LoadSample(None, 50, transport_error=True),
        ],
        wall_seconds=0.5,
    )

    assert summary["throughput_rps"] == 10.0
    assert summary["latency_ms"]["p50"] == 30.0
    assert summary["server_error_rate"] == 0.2
    assert summary["rate_limited_429_rate"] == 0.2
    assert summary["transport_error_rate"] == 0.2
    assert summary["unexpected_status_rate"] == 0.2


def test_rate_gate_has_pass_fail_insufficient_and_invalid_states() -> None:
    passed = evaluate_rate_gate(
        name="refresh",
        rate=0.99,
        total=200,
        threshold=0.99,
        direction="min_inclusive",
        min_samples=200,
    )
    failed = evaluate_rate_gate(
        name="infrastructure",
        rate=0.01,
        total=200,
        threshold=0.01,
        direction="max_exclusive",
        min_samples=200,
    )
    insufficient = evaluate_rate_gate(
        name="refresh",
        rate=None,
        total=0,
        threshold=0.99,
        direction="min_inclusive",
        min_samples=200,
    )
    invalid = evaluate_rate_gate(
        name="refresh",
        rate=math.nan,
        total=200,
        threshold=0.99,
        direction="min_inclusive",
        min_samples=200,
    )

    assert passed.state == GateState.PASS
    assert failed.state == GateState.FAIL
    assert insufficient.state == GateState.INSUFFICIENT
    assert invalid.state == GateState.INVALID


def test_release_gates_pass_and_ignore_student_wrong_answers_for_reliability() -> None:
    gates = evaluate_release_gates(
        _metrics_payload(),
        frontend_sessions=200,
        min_samples=200,
    )

    assert aggregate_gate_state(gates) == GateState.PASS
    code_gate = next(gate for gate in gates if gate.name == "code_infrastructure_failure")
    assert code_gate.state == GateState.PASS
    assert code_gate.observed == 0.0


def test_release_gates_fail_exact_one_percent_infrastructure_and_unattributed_mastery() -> None:
    payload = _metrics_payload()
    payload["launch"]["resource_failure"].update({"failed": 2, "rate": 0.01})
    payload["launch"]["mastery_attribution_integrity"].update(
        {"attributed": 199, "unattributed": 1, "rate": 0.995}
    )

    gates = evaluate_release_gates(payload, frontend_sessions=200, min_samples=200)
    by_name = {gate.name: gate for gate in gates}

    assert by_name["resource_failure"].state == GateState.FAIL
    assert by_name["mastery_attribution_integrity"].state == GateState.FAIL
    assert aggregate_gate_state(gates) == GateState.FAIL


def test_release_gates_never_promote_missing_denominators_or_small_samples() -> None:
    gates = evaluate_release_gates(
        _metrics_payload(total=20),
        frontend_sessions=None,
        min_samples=200,
    )

    assert aggregate_gate_state(gates) == GateState.INSUFFICIENT
    assert all(gate.state == GateState.INSUFFICIENT for gate in gates)


def test_unattributed_mastery_is_a_failure_even_before_minimum_sample() -> None:
    payload = _metrics_payload(total=20)
    payload["launch"]["mastery_attribution_integrity"].update(
        {"attributed": 19, "unattributed": 1, "rate": 0.95}
    )

    gates = evaluate_release_gates(payload, frontend_sessions=20, min_samples=200)
    mastery = next(gate for gate in gates if gate.name == "mastery_attribution_integrity")

    assert mastery.state == GateState.FAIL
    assert aggregate_gate_state(gates) == GateState.FAIL


def test_release_gate_schema_errors_are_invalid() -> None:
    gates = evaluate_release_gates({}, frontend_sessions=200, min_samples=200)
    assert aggregate_gate_state(gates) == GateState.INVALID
    assert gates[0].state == GateState.INVALID


def test_release_gates_reject_a_non_five_second_target_and_mismatched_counters() -> None:
    payload = _metrics_payload()
    payload["launch"]["next_task_ready"]["target_ms"] = 3000
    payload["counters"] = []

    gates = evaluate_release_gates(payload, frontend_sessions=200, min_samples=200)
    by_name = {gate.name: gate for gate in gates}

    assert by_name["next_task_within_5s"].state == GateState.INVALID
    assert by_name["login_infrastructure_failure"].state == GateState.INVALID
    assert aggregate_gate_state(gates) == GateState.INVALID


def test_load_requires_explicit_environment_switch_without_leaking_tokens(capsys) -> None:
    secret = "sensitive-token-that-must-not-be-printed"
    exit_code = main(
        ["load"],
        environment={
            "BASE_URL": "http://localhost:8800",
            "ACCESS_TOKEN": secret,
            "OPS_TOKEN": secret,
        },
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "EDUAGENT_SMOKE_ALLOW_LOAD=true" in captured.err
    assert secret not in captured.out
    assert secret not in captured.err
