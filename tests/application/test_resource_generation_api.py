from __future__ import annotations

import json

import pytest
from starlette.requests import Request

from src.auth.security import SecurityManager
from src.release_controls import RolloutDecision


def _scope(method: str, path: str, path_params: dict[str, str], token: str) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "path_params": path_params,
        "query_string": b"",
        "headers": [(b"authorization", f"Bearer {token}".encode("ascii"))],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }


@pytest.mark.asyncio
async def test_generation_post_enqueues_card_types_without_waiting_for_worker(monkeypatch) -> None:
    from frontend import server

    received = {}

    def fake_request(user_id, course_id, node_id, *, card_types, force, priority):
        received.update(
            user_id=user_id,
            course_id=course_id,
            node_id=node_id,
            card_types=card_types,
            force=force,
            priority=priority,
        )
        return {
            "job_id": "job-1",
            "status": "queued",
            "existing_resources": [],
            "resources": [],
            "missing_card_types": card_types,
        }

    monkeypatch.setattr(server.resource_service, "request_generation", fake_request)
    body = json.dumps({
        "card_types": ["concept_map"],
        "force": True,
        "priority": "concept_map",
    }).encode("utf-8")
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    token = SecurityManager.create_token_pair("u1", "STUDENT")["access_token"]
    request = Request(
        _scope("POST", "/api/sessions/u1:course1/resources/N01/generation", {"session_id": "u1:course1", "node_id": "N01"}, token),
        receive,
    )
    response = await server.api_session_resource_generation(request)

    assert response.status_code == 200
    assert received == {
        "user_id": "u1",
        "course_id": "course1",
        "node_id": "N01",
        "card_types": ["concept_map"],
        "force": True,
        "priority": "concept_map",
    }
    assert json.loads(response.body)["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_generation_post_rejects_non_boolean_force(monkeypatch) -> None:
    from frontend import server

    called = False

    def fake_request(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(server.resource_service, "request_generation", fake_request)
    body = json.dumps({"card_types": ["concept_map"], "force": "false"}).encode("utf-8")
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    token = SecurityManager.create_token_pair("u1", "STUDENT")["access_token"]
    request = Request(
        _scope("POST", "/api/sessions/u1:course1/resources/N01/generation", {"session_id": "u1:course1", "node_id": "N01"}, token),
        receive,
    )
    response = await server.api_session_resource_generation(request)

    assert response.status_code == 422
    assert json.loads(response.body) == {"detail": "INVALID_FORCE"}
    assert called is False


@pytest.mark.asyncio
async def test_generation_post_returns_cached_contract_for_rollout_holdback(monkeypatch) -> None:
    from frontend import server

    monkeypatch.setattr(
        server,
        "_resource_generation_rollout",
        lambda _user_id: RolloutDecision(
            feature="resource_generation",
            enabled=False,
            cohort="holdback",
            bucket=88.0,
            percent=0.0,
        ),
    )
    monkeypatch.setattr(
        server.resource_service,
        "get_node_resources",
        lambda _user_id, _course_id, node_id, *, card_types: {
            "node_id": node_id,
            "resources": [{"resource_type": "concept_map", "node_id": node_id}],
            "missing_card_types": [card_type for card_type in card_types if card_type != "concept_map"],
        },
    )

    def generation_must_not_run(*_args, **_kwargs):
        raise AssertionError("rollout holdback must not create a generation job")

    monkeypatch.setattr(server.resource_service, "request_generation", generation_must_not_run)
    body = json.dumps({
        "card_types": ["concept_map", "code_snippet"],
        "force": False,
        "priority": "concept_map",
    }).encode("utf-8")
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    token = SecurityManager.create_token_pair("u1", "STUDENT")["access_token"]
    request = Request(
        _scope("POST", "/api/sessions/u1:course1/resources/N01/generation", {"session_id": "u1:course1", "node_id": "N01"}, token),
        receive,
    )
    response = await server.api_session_resource_generation(request)
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert response.headers["x-eduagent-feature-cohort"] == "holdback"
    assert payload == {
        "job_id": None,
        "status": "rollout_holdback",
        "task_status": "rollout_holdback",
        "generation_available": False,
        "feature": "resource_generation",
        "existing_resources": [{"resource_type": "concept_map", "node_id": "N01"}],
        "resources": [{"resource_type": "concept_map", "node_id": "N01"}],
        "missing_card_types": ["code_snippet"],
        "requested_card_types": ["concept_map", "code_snippet"],
        "node_id": "N01",
        "created": False,
    }


@pytest.mark.asyncio
async def test_generation_sse_is_hidden_for_rollout_holdback(monkeypatch) -> None:
    from frontend import server

    monkeypatch.setattr(
        server,
        "_resource_generation_rollout",
        lambda _user_id: RolloutDecision(
            feature="resource_generation",
            enabled=False,
            cohort="holdback",
            bucket=88.0,
            percent=0.0,
        ),
    )

    def job_must_not_be_read(*_args, **_kwargs):
        raise AssertionError("holdback must not expose job events")

    monkeypatch.setattr(server.resource_service, "get_generation_job", job_must_not_be_read)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    token = SecurityManager.create_token_pair("u1", "STUDENT")["access_token"]
    request = Request(
        _scope("GET", "/api/resource-generation-jobs/job-1/events", {"job_id": "job-1"}, token),
        receive,
    )
    response = await server.api_resource_generation_events(request)

    assert response.status_code == 404
    assert response.headers["x-eduagent-feature-cohort"] == "holdback"
    assert json.loads(response.body) == {
        "detail": "RESOURCE_GENERATION_ROLLOUT_HOLDBACK",
        "feature": "resource_generation",
    }


@pytest.mark.asyncio
async def test_generation_events_replay_durable_cards_for_the_job_owner(monkeypatch) -> None:
    from frontend import server

    events = [
        {"event_id": 3, "event_type": "queued", "payload": {"status": "queued"}},
        {
            "event_id": 4,
            "event_type": "card_ready",
            "payload": {"card_type": "concept_map", "card": {"resource_type": "concept_map"}},
        },
        {"event_id": 5, "event_type": "completed", "payload": {"status": "completed"}},
    ]
    monkeypatch.setattr(server.resource_service, "get_generation_job", lambda job_id, user_id=None: {
        "job_id": job_id,
        "user_id": "u1",
        "status": "completed",
    })
    monkeypatch.setattr(
        server.resource_service,
        "list_generation_events",
        lambda job_id, *, after_event_id=0, user_id=None: [
            event for event in events if event["event_id"] > after_event_id
        ],
    )

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    token = SecurityManager.create_token_pair("u1", "STUDENT")["access_token"]
    request = Request(
        _scope("GET", "/api/resource-generation-jobs/job-1/events", {"job_id": "job-1"}, token),
        receive,
    )
    response = await server.api_resource_generation_events(request)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))

    replay = "".join(chunks)
    assert "'event': 'queued'" in replay
    assert "'event': 'card_ready'" in replay
    assert "'event': 'completed'" in replay
    assert "'id': '3'" in replay
    assert "concept_map" in replay
