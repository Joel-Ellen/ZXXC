import json

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from frontend import server
from src.auth.security import SecurityManager


class _Receive:
    def __init__(self, payload):
        self._payload = payload
        self._sent = False

    async def __call__(self):
        if self._sent:
            return {"type": "http.disconnect"}
        self._sent = True
        return {
            "type": "http.request",
            "body": json.dumps(self._payload).encode("utf-8"),
            "more_body": False,
        }


def _auth_headers(user_id="u1"):
    token = SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _request(payload, *, method="POST", query_string=b"", token_user_id="u1"):
    token = SecurityManager.create_token_pair(token_user_id, "STUDENT")["access_token"]
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/sessions/u1:course1/events",
            "headers": [
                (b"content-type", b"application/json"),
                (b"authorization", f"Bearer {token}".encode("ascii")),
            ],
            "path_params": {"session_id": "u1:course1"},
            "query_string": query_string,
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        },
        _Receive(payload),
    )


def test_session_event_routes_are_reachable_over_http(monkeypatch):
    calls = []

    def fake_record(user_id, course_id, event_payload):
        calls.append(("record", user_id, course_id, event_payload))
        return {
            "status": "ok",
            "event_id": "event-http",
            "mastery_attribution": None,
            "current_node_id": "N01",
        }

    def fake_history(user_id, course_id, *, node_id=None, event_id=None, limit=100):
        calls.append(("history", user_id, course_id, node_id, event_id, limit))
        return {"status": "ok", "events": [], "mastery_attributions": []}

    monkeypatch.setattr(server.session_service, "record_learning_event", fake_record)
    monkeypatch.setattr(server.session_service, "get_learning_event_history", fake_history)
    payload = {
        "event_type": "lesson_opened",
        "user_id": "u1",
        "course_id": "course1",
        "node_id": "N01",
        "resource_id": "",
        "question_id": "",
        "duration_ms": 0,
        "attempt_number": 1,
        "used_hint": False,
        "result": {},
    }

    client = TestClient(server.app)
    post_response = client.post("/api/sessions/u1%3Acourse1/events", json=payload, headers=_auth_headers())
    get_response = client.get("/api/sessions/u1%3Acourse1/events?node_id=N01&limit=2", headers=_auth_headers())

    assert post_response.status_code == 200
    assert post_response.json()["event_id"] == "event-http"
    assert get_response.status_code == 200
    assert calls == [
        ("record", "u1", "course1", payload),
        ("history", "u1", "course1", "N01", None, 2),
    ]


@pytest.mark.asyncio
async def test_session_events_posts_the_canonical_payload_and_keeps_attribution(monkeypatch):
    called = {}
    payload = {
        "event_type": "review_completed",
        "user_id": "u1",
        "course_id": "course1",
        "node_id": "N01",
        "resource_id": "quiz-1",
        "question_id": "",
        "duration_ms": 12_500,
        "attempt_number": 2,
        "used_hint": True,
        "score": 1.0,
        "result": {
            "answers": [{"question_id": "q1", "answer_index": 1}],
            "score": 1.0,
        },
    }

    def fake_record(user_id, course_id, event_payload):
        called.update({
            "user_id": user_id,
            "course_id": course_id,
            "event_payload": event_payload,
        })
        return {
            "status": "ok",
            "event_id": "event-1",
            "event_type": "review_completed",
            "current_node_id": "N02",
            "mastery_attribution": {
                "event_id": "event-1",
                "mastery_before": 0.4,
                "mastery_after": 0.6,
                "reason": "verified_diagnostic_quiz",
            },
            "advanced_to_next_node": True,
            "next_node_id": "N02",
            "knowledge_mastery": {"N01": 0.6},
        }

    monkeypatch.setattr(server.session_service, "record_learning_event", fake_record)
    response = await server.api_session_events(_request(payload))

    assert response.status_code == 200
    assert called["user_id"] == "u1"
    assert called["course_id"] == "course1"
    assert called["event_payload"]["event_type"] == "review_completed"
    assert called["event_payload"]["result"] == {
        "answers": [{"question_id": "q1", "answer_index": 1}],
    }
    assert "score" not in called["event_payload"]
    body = json.loads(response.body)
    assert body["event_id"] == "event-1"
    assert body["mastery_attribution"]["mastery_after"] == 0.6
    assert body["advanced_to_next_node"] is True
    assert body["knowledge_mastery"] == {"N01": 0.6}


@pytest.mark.asyncio
async def test_session_event_history_forwards_filters_and_bounds(monkeypatch):
    called = {}

    def fake_history(user_id, course_id, *, node_id=None, event_id=None, limit=100):
        called.update({
            "user_id": user_id,
            "course_id": course_id,
            "node_id": node_id,
            "event_id": event_id,
            "limit": limit,
        })
        return {"status": "ok", "events": [], "mastery_attributions": []}

    monkeypatch.setattr(server.session_service, "get_learning_event_history", fake_history)
    response = await server.api_session_event_history(
        _request({}, method="GET", query_string=b"nodeId=N01&limit=3"),
    )

    assert response.status_code == 200
    assert called == {
        "user_id": "u1",
        "course_id": "course1",
        "node_id": "N01",
        "event_id": None,
        "limit": 3,
    }


@pytest.mark.asyncio
async def test_session_events_uses_service_validation_status(monkeypatch):
    monkeypatch.setattr(
        server.session_service,
        "record_learning_event",
        lambda *_args: {
            "status": "invalid_event",
            "blocked": True,
            "reason": "user_id_mismatch",
            "status_code": 422,
        },
    )

    response = await server.api_session_events(_request({
        "event_type": "lesson_opened",
        "user_id": "u1",
        "course_id": "course1",
        "node_id": "N01",
        "resource_id": "",
        "question_id": "",
        "duration_ms": 0,
        "attempt_number": 1,
        "used_hint": False,
        "result": {},
    }))

    assert response.status_code == 422
    body = json.loads(response.body)
    assert body["reason"] == "user_id_mismatch"
    assert "status_code" not in body


def test_session_event_routes_require_the_authenticated_session_owner():
    client = TestClient(server.app)
    payload = {
        "event_type": "lesson_opened",
        "user_id": "u1",
        "course_id": "course1",
        "node_id": "N01",
        "resource_id": "",
        "question_id": "",
        "duration_ms": 0,
        "attempt_number": 1,
        "used_hint": False,
        "result": {},
    }

    unauthenticated = client.post("/api/sessions/u1%3Acourse1/events", json=payload)
    other_user = client.post(
        "/api/sessions/u1%3Acourse1/events",
        json=payload,
        headers=_auth_headers("u2"),
    )

    assert unauthenticated.status_code == 401
    assert other_user.status_code == 403


@pytest.mark.asyncio
async def test_session_events_requires_the_canonical_envelope(monkeypatch):
    called = False

    def fake_record(*_args):
        nonlocal called
        called = True
        return {"status": "ok"}

    monkeypatch.setattr(server.session_service, "record_learning_event", fake_record)
    response = await server.api_session_events(_request({"event_type": "lesson_opened"}))

    assert response.status_code == 422
    body = json.loads(response.body)
    assert body["reason"] == "missing_canonical_event_fields"
    assert "node_id" in body["missing_fields"]
    assert called is False


@pytest.mark.asyncio
async def test_legacy_session_routes_strip_client_mastery_claims(monkeypatch):
    calls = []

    def fake_advance(user_id, course_id, user_input=None, behavior=None):
        calls.append({
            "user_id": user_id,
            "course_id": course_id,
            "user_input": user_input,
            "behavior": behavior,
        })
        return {"status": "ok", "mastery_updated": False}

    payload = {
        "interaction_type": "complete_learning",
        "current_node_id": "N01",
        "answers": [{"question_id": "q1", "selected_option_index": 1}],
        "correctness": 1.0,
        "score": 1.0,
        "code_pass_rate": 1.0,
        "time_spent_ratio": 0.01,
        "mastery_after": 1.0,
        "result": {
            "answers": [{"question_id": "q1", "answer_index": 1}],
            "correctness": 1.0,
            "knowledge_mastery": {"N01": 1.0},
            "test_results": [{"name": "real browser test", "passed": True}],
        },
    }
    monkeypatch.setattr(server.session_service, "advance_session", fake_advance)

    await server.api_session_advance(_request(payload))
    await server.api_session_behavior(_request(payload))

    assert len(calls) == 2
    for call in calls:
        behavior = call["behavior"]
        assert behavior["answers"] == payload["answers"]
        assert "correctness" not in behavior
        assert "score" not in behavior
        assert "code_pass_rate" not in behavior
        assert "time_spent_ratio" not in behavior
        assert "mastery_after" not in behavior
        assert behavior["result"] == {
            "answers": [{"question_id": "q1", "answer_index": 1}],
            "test_results": [{"name": "real browser test", "passed": True}],
        }
