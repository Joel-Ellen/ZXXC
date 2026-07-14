from __future__ import annotations

from types import SimpleNamespace

from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from frontend import server
from src.observability import metrics, metrics_snapshot, reset_metrics


def setup_function() -> None:
    reset_metrics()


def teardown_function() -> None:
    reset_metrics()


def test_login_attempts_record_success_and_bounded_failure_reasons(monkeypatch) -> None:
    captcha = SimpleNamespace(verify=lambda *_args: True)
    user = {
        "user_id": "launch-user",
        "email": "launch@example.test",
        "display_name": "Launch User",
        "role": "STUDENT",
        "created_at": "",
        "last_login_at": "",
    }
    store = SimpleNamespace(
        verify_login=lambda user_id, _password: user if user_id == "launch-user" else None,
    )
    monkeypatch.setattr(server, "_get_auth", lambda: (store, captcha))
    monkeypatch.setattr(
        server,
        "_create_authenticated_session",
        lambda *_args: {
            "access_token": "access",
            "refresh_token": "refresh",
            "session_id": "session",
        },
    )
    client = TestClient(server.app)

    failed = client.post(
        "/api/auth/login",
        json={"user_id": "unknown", "password": "Password123!", "captcha_token": "c", "captcha_answer": "1"},
    )
    succeeded = client.post(
        "/api/auth/login",
        json={"user_id": "launch-user", "password": "Password123!", "captcha_token": "c", "captcha_answer": "1"},
    )

    assert failed.status_code == 401
    assert succeeded.status_code == 200
    assert metrics.counter_value("auth.login_total", outcome="failure", reason="invalid_credentials") == 1
    assert metrics.counter_value("auth.login_total", outcome="success", reason="authenticated") == 1
    assert metrics_snapshot()["launch"]["login_failure"]["rate"] == 0.5


def test_client_events_accept_only_fixed_non_pii_dimensions() -> None:
    client = TestClient(server.app)

    exception = client.post(
        "/api/ops/client-events",
        json={
            "event": "frontend_exception",
            "surface": "learn",
            "kind": "vue",
            "user_id": "must-not-be-a-label",
            "message": "must-not-be-recorded",
        },
    )
    recovery = client.post(
        "/api/ops/client-events",
        json={"event": "refresh_recovery", "surface": "learn", "outcome": "success"},
    )
    next_task = client.post(
        "/api/ops/client-events",
        json={"event": "next_task_ready", "surface": "app", "duration_ms": 3200},
    )
    unsupported = client.post("/api/ops/client-events", json={"event": "arbitrary"})

    assert exception.status_code == 202
    assert recovery.status_code == 202
    assert next_task.status_code == 202
    assert unsupported.status_code == 422
    assert metrics.counter_value("frontend.exception_total", surface="learn", kind="vue") == 1
    assert metrics.counter_value("frontend.refresh_recovery_total", surface="learn", outcome="success") == 1
    assert metrics.counter_value("frontend.next_task_ready_total", surface="app", outcome="within_5s") == 1
    assert metrics_snapshot()["launch"]["next_task_ready"]["rate"] == 1.0
    counter_labels = [
        counter["labels"]
        for counter in metrics_snapshot()["counters"]
        if counter["name"].startswith("frontend.")
    ]
    assert all("user_id" not in labels and "message" not in labels for labels in counter_labels)


def test_production_release_metrics_require_authenticated_telemetry(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        server,
        "_access_principal",
        lambda request: (
            ({"sub": "launch-user"}, None)
            if request.headers.get("authorization") == "Bearer valid"
            else (None, JSONResponse({"detail": "invalid"}, status_code=401))
        ),
    )
    client = TestClient(server.app)

    rejected = client.post(
        "/api/ops/client-events",
        json={"event": "next_task_ready", "surface": "app", "duration_ms": 1000},
    )
    public_auth_exception = client.post(
        "/api/ops/client-events",
        json={"event": "frontend_exception", "surface": "auth", "kind": "window"},
    )
    accepted = client.post(
        "/api/ops/client-events",
        json={"event": "next_task_ready", "surface": "app", "duration_ms": 1000},
        headers={"Authorization": "Bearer valid"},
    )

    assert rejected.status_code == 401
    assert public_auth_exception.status_code == 202
    assert accepted.status_code == 202
    assert metrics.counter_value("frontend.next_task_ready_total", surface="app", outcome="within_5s") == 1
    assert metrics.counter_value("frontend.exception_total") == 0
    assert metrics.counter_value(
        "frontend.auth_public_exception_total",
        surface="auth",
        kind="window",
    ) == 1


def test_resource_and_code_execution_outcomes_feed_launch_rates(monkeypatch) -> None:
    monkeypatch.setattr(server, "_event_session_auth_error", lambda *_args: None)

    def generate(_user_id, _course_id, node_id, _force, **_kwargs):
        if node_id == "failed":
            return {"status": "failed", "status_code": 503}
        return {"status": "generated", "resources": []}

    monkeypatch.setattr(server.resource_service, "generate_current_node_resources", generate)
    client = TestClient(server.app)

    assert client.get("/api/sessions/user%3Acourse/resources/N01").status_code == 200
    assert client.get("/api/sessions/user%3Acourse/resources/failed").status_code == 503

    server._practice_response({"status": "ok", "verdict": "accepted", "runtime_ms": 5}, mode="run")
    server._practice_response({"status": "ok", "verdict": "wrong_answer", "runtime_ms": 7}, mode="run")
    server._practice_response({"status": "sandbox_unavailable"}, mode="submit")

    launch = metrics_snapshot()["launch"]
    assert launch["resource_failure"]["rate"] == 0.5
    assert launch["code_execution_failure"]["rate"] == 0.666667
    assert launch["code_execution_failure"]["infrastructure_rate"] == 0.333333


def test_production_hides_internal_surfaces_and_protects_metrics(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EDUAGENT_ENABLE_COMPAT_API", "false")
    monkeypatch.setenv("EDUAGENT_ENABLE_PUBLIC_METRICS", "false")
    monkeypatch.setenv("EDUAGENT_OPS_TOKEN", "operations-secret")
    client = TestClient(server.app)

    assert client.post("/api/reset", json={"user_id": "demo_user"}).status_code == 404
    assert client.get("/api/state").status_code == 404
    assert client.get("/api/ops/metrics").status_code == 404

    authorized = client.get(
        "/api/ops/metrics",
        headers={"X-EduAgent-Ops-Token": "operations-secret"},
    )
    assert authorized.status_code == 200
    assert authorized.headers["cache-control"] == "no-store"


def test_production_hides_legacy_debug_routes_without_ops_token(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EDUAGENT_ENABLE_COMPAT_API", "true")
    monkeypatch.setenv("EDUAGENT_OPS_TOKEN", "operations-secret")
    client = TestClient(server.app)

    requests = (
        ("GET", "/api/profile/me"),
        ("POST", "/api/profile/build"),
        ("POST", "/api/learning/generate-path"),
        ("POST", "/api/resources/generate"),
        ("POST", "/api/resources/generate-all"),
        ("POST", "/api/evaluation/generate-report"),
        ("GET", "/api/agents/status"),
        ("POST", "/api/knowledge/search"),
        ("GET", "/api/knowledge/stats"),
    )
    for method, path in requests:
        assert client.request(method, path, json={}).status_code == 404

    authorized = client.get(
        "/api/agents/status",
        headers={"X-EduAgent-Ops-Token": "operations-secret"},
    )
    assert authorized.status_code == 200


def test_public_health_is_minimal_in_production(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "configured-but-private")
    monkeypatch.setenv("LLM_PROVIDER", "private-provider")
    client = TestClient(server.app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_production_readiness_fails_closed_without_postgres(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://learn.example.test")
    monkeypatch.setenv("EDUAGENT_OPS_TOKEN", "operations-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "production-test-secret-with-at-least-32-characters")
    monkeypatch.setattr(server, "_db_available", False)
    monkeypatch.setattr(server, "_db", None)

    response = TestClient(server.app).get("/api/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "5"


def test_production_readiness_requires_durable_postgres_and_redis(monkeypatch) -> None:
    class Cursor:
        def fetchone(self):
            return {"ready": 1}

    class Database:
        def execute(self, statement):
            assert statement == "SELECT 1 AS ready"
            return Cursor()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://learn.example.test")
    monkeypatch.setenv("EDUAGENT_OPS_TOKEN", "operations-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "production-test-secret-with-at-least-32-characters")
    monkeypatch.setattr(server, "_db_available", True)
    monkeypatch.setattr(server, "_db", Database())
    monkeypatch.setattr(server, "_get_auth", lambda: (object(), object()))
    monkeypatch.setattr(server, "_get_account_repo", lambda: object())
    monkeypatch.setattr(server, "redis_backend_status", lambda: "redis")
    monkeypatch.setattr(server, "durable_redis_available", lambda: True)

    response = TestClient(server.app).get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["cache-control"] == "no-store"


def test_production_login_is_held_back_outside_app_access_cohort(monkeypatch) -> None:
    user = {
        "user_id": "held-back-user",
        "email": "held-back@example.test",
        "display_name": "Held Back",
        "role": "STUDENT",
        "created_at": "",
        "last_login_at": "",
    }
    store = SimpleNamespace(verify_login=lambda *_args: user)
    captcha = SimpleNamespace(verify=lambda *_args: True)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EDUAGENT_APP_ACCESS_ROLLOUT_PERCENT", "0")
    monkeypatch.setattr(server, "_get_auth", lambda: (store, captcha))
    monkeypatch.setattr(
        server,
        "_create_authenticated_session",
        lambda *_args: (_ for _ in ()).throw(AssertionError("held-back login created a session")),
    )

    response = TestClient(server.app).post(
        "/api/auth/login",
        json={
            "user_id": "held-back-user",
            "password": "Password123!",
            "captcha_token": "captcha",
            "captcha_answer": "1",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "RELEASE_NOT_AVAILABLE"
    assert response.headers["x-eduagent-release-cohort"] == "holdback"


def test_app_access_allowlist_overrides_zero_percent(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EDUAGENT_APP_ACCESS_ROLLOUT_PERCENT", "0")
    monkeypatch.setenv("EDUAGENT_APP_ACCESS_ROLLOUT_ALLOWLIST", "internal-user")

    decision, response = server._app_access_rollout("internal-user")

    assert decision.enabled is True
    assert decision.cohort == "allowlist"
    assert response is None


def test_legacy_debug_routes_remain_available_in_test_mode(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("EDUAGENT_ENABLE_COMPAT_API", raising=False)
    client = TestClient(server.app)

    response = client.get("/api/agents/status")

    assert response.status_code == 200
    assert response.json()["orchestrator_status"] == "idle"


def test_code_practice_rollout_can_hold_back_without_identity_metrics(monkeypatch) -> None:
    monkeypatch.setenv("EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT", "0")

    decision, response = server._code_practice_rollout("held-back-user")

    assert decision.enabled is False
    assert response is not None and response.status_code == 404
    rollout_counters = [
        counter
        for counter in metrics_snapshot()["counters"]
        if counter["name"] == "release.rollout_decision_total"
    ]
    assert rollout_counters == [{
        "name": "release.rollout_decision_total",
        "labels": {"cohort": "holdback", "feature": "code_practice"},
        "value": 1,
    }]


def test_production_code_practice_defaults_to_holdback(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT", raising=False)

    decision, response = server._code_practice_rollout("production-user")

    assert decision.enabled is False
    assert response is not None and response.status_code == 404
