from __future__ import annotations

import math
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from frontend import server
from src.application import session_service
from src.auth.captcha import CaptchaGenerator
from src.auth.rate_limiter import RateLimiter
from src.state.agent_state import AgentState


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class SharedRedisWindow:
    """Small atomic eval stand-in shared by multiple limiter instances."""

    def __init__(self) -> None:
        self._entries: dict[str, list[int]] = {}
        self._lock = threading.Lock()

    def eval(self, _script, _key_count, key, now, window, limit, _member):
        now = int(now)
        window = int(window)
        limit = int(limit)
        with self._lock:
            entries = [value for value in self._entries.get(key, []) if value > now - window]
            if len(entries) >= limit:
                self._entries[key] = entries
                return [0, len(entries), entries[0]]
            entries.append(now)
            self._entries[key] = entries
            return [1, len(entries), 0]

    def delete(self, key):
        with self._lock:
            self._entries.pop(key, None)


def setup_function() -> None:
    server._reset_core_rate_limiters()


def teardown_function() -> None:
    server._reset_core_rate_limiters()


def test_memory_limiter_blocks_exactly_after_limit_and_recovers() -> None:
    clock = Clock()
    limiter = RateLimiter(2, 10, clock=clock)

    first = limiter.check("subject")
    second = limiter.check("subject")
    blocked = limiter.check("subject")

    assert (first.allowed, first.remaining) == (True, 1)
    assert (second.allowed, second.remaining) == (True, 0)
    assert blocked.allowed is False
    assert blocked.retry_after == 10

    clock.value += 10.01
    recovered = limiter.check("subject")
    assert recovered.allowed is True
    assert recovered.remaining == 1


def test_memory_limiter_is_thread_safe() -> None:
    limiter = RateLimiter(5, 60)
    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(executor.map(lambda _index: limiter.check("shared"), range(20)))

    assert sum(decision.allowed for decision in decisions) == 5


def test_redis_limiter_shares_an_atomic_window_across_instances() -> None:
    clock = Clock()
    redis_backend = SharedRedisWindow()
    first = RateLimiter(2, 10, redis_client=redis_backend, namespace="login", clock=clock)
    second = RateLimiter(2, 10, redis_client=redis_backend, namespace="login", clock=clock)

    assert first.check("subject").allowed is True
    assert second.check("subject").allowed is True
    blocked = first.check("subject")

    assert blocked.allowed is False
    assert blocked.retry_after == math.ceil(10)


def test_login_rate_limit_returns_retryable_429(monkeypatch) -> None:
    monkeypatch.setenv("EDUAGENT_ENABLE_RATE_LIMITS", "true")
    monkeypatch.setenv("EDUAGENT_RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("EDUAGENT_RATE_LIMIT_LOGIN_REQUESTS", "2")
    monkeypatch.setenv("EDUAGENT_RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    monkeypatch.setattr(
        server,
        "_get_auth",
        lambda: (SimpleNamespace(), SimpleNamespace(verify=lambda *_args: False)),
    )
    client = TestClient(server.app)
    payload = {
        "user_id": "learner",
        "password": "Password123!",
        "captcha_token": "invalid",
        "captcha_answer": "0",
    }

    first = client.post("/api/auth/login", json=payload)
    second = client.post("/api/auth/login", json=payload)
    blocked = client.post("/api/auth/login", json=payload)

    assert first.status_code == 400
    assert second.status_code == 400
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert second.headers["x-ratelimit-remaining"] == "0"
    assert blocked.status_code == 429
    assert blocked.json() == {
        "status": "rate_limited",
        "detail": "RATE_LIMITED",
        "policy": "login",
    }
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["cache-control"] == "no-store"


def test_canonical_tutor_endpoint_uses_tutor_policy(monkeypatch) -> None:
    monkeypatch.setenv("EDUAGENT_ENABLE_RATE_LIMITS", "true")
    monkeypatch.setenv("EDUAGENT_RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("EDUAGENT_RATE_LIMIT_TUTOR_REQUESTS", "1")
    monkeypatch.setattr(server, "_event_session_auth_error", lambda *_args: None)
    monkeypatch.setattr(
        server,
        "_session_tutor_response",
        lambda *_args, **_kwargs: JSONResponse({"status": "ok"}),
    )
    client = TestClient(server.app)

    first = client.post("/api/sessions/user%3Acourse/tutor", json={"question": "help"})
    blocked = client.post("/api/sessions/user%3Acourse/tutor", json={"question": "help"})

    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit"] == "1"
    assert blocked.status_code == 429
    assert blocked.json()["policy"] == "tutor"


def test_configured_shared_backend_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("EDUAGENT_ENABLE_RATE_LIMITS", "true")
    monkeypatch.setenv("EDUAGENT_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(server, "get_redis", lambda: None)
    client = TestClient(server.app)

    response = client.post("/api/auth/login", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == "RATE_LIMIT_BACKEND_UNAVAILABLE"
    assert response.headers["retry-after"] == "5"


def test_client_telemetry_body_limit_checks_actual_payload() -> None:
    client = TestClient(server.app)

    response = client.post(
        "/api/ops/client-events",
        content=b"{" + (b"x" * 4096) + b"}",
        headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "REQUEST_BODY_TOO_LARGE"


def test_captcha_store_evicts_oldest_record_at_capacity(monkeypatch) -> None:
    captcha = CaptchaGenerator()
    monkeypatch.setattr(captcha, "MAX_RECORDS", 2)

    _first_svg, first_token = captcha.generate()
    captcha.generate()
    captcha.generate()

    assert len(captcha._records) == 2
    assert first_token not in captcha._records


def test_learning_event_history_has_a_hard_maximum(monkeypatch) -> None:
    state = AgentState(user_id="history-user", course_id="course")
    state.internal_state["learning_events"] = [
        {"event_id": f"event-{index}", "event_type": "content_viewed", "node_id": "N01"}
        for index in range(700)
    ]
    monkeypatch.setattr(
        session_service,
        "get_session",
        lambda *_args, **_kwargs: SimpleNamespace(agent_state=state),
    )

    result = session_service.get_learning_event_history("history-user", "course", limit=10_000)

    assert len(result["events"]) == 500
    assert result["events"][0]["event_id"] == "event-200"


def test_learning_funnel_counts_only_verified_completions_after_open(monkeypatch) -> None:
    state = AgentState(user_id="funnel-user", course_id="course")
    state.internal_state["learning_events"] = [
        {"event_id": "open-1", "event_type": "lesson_opened", "node_id": "N01"},
        {"event_id": "open-2", "event_type": "lesson_opened", "node_id": "N02"},
        {
            "event_id": "complete-1",
            "event_type": "lesson_completed",
            "node_id": "N01",
            "mastery": {"evidence_accepted": True, "evaluated_node_id": "N01"},
        },
        {
            "event_id": "unverified",
            "event_type": "lesson_completed",
            "node_id": "N02",
            "mastery": {"evidence_accepted": False, "evaluated_node_id": "N02"},
        },
        {
            "event_id": "orphan",
            "event_type": "review_completed",
            "node_id": "N03",
            "mastery": {"evidence_accepted": True, "evaluated_node_id": "N03"},
        },
    ]
    monkeypatch.setattr(
        session_service,
        "get_session",
        lambda *_args, **_kwargs: SimpleNamespace(agent_state=state),
    )

    result = session_service.get_learning_event_history("funnel-user", "course")

    assert result["learning_funnel"] == {
        "opened_nodes": 2,
        "verified_completed_nodes": 1,
        "verified_completed_without_open": 1,
        "completion_rate": 0.5,
        "definition": "unique verified completed opened nodes / unique opened nodes",
    }
