import json

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from frontend import server


class _Receive:
    def __init__(self, payload):
        self._payload = payload
        self._sent = False

    async def __call__(self):
        if self._sent:
            return {"type": "http.disconnect"}
        self._sent = True
        return {"type": "http.request", "body": json.dumps(self._payload).encode("utf-8"), "more_body": False}


def _request(payload, accept="application/json"):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/sessions/u1:course1/tutor",
        "headers": [(b"accept", accept.encode("utf-8"))],
        "path_params": {"session_id": "u1:course1"},
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }
    return Request(scope, _Receive(payload))


def _compat_request(payload, path="/api/tutor/ask", accept="application/json"):
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(b"accept", accept.encode("utf-8"))],
        "path_params": {},
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }
    return Request(scope, _Receive(payload))


@pytest.mark.asyncio
async def test_session_tutor_json_uses_non_stream_service(monkeypatch):
    called = {}

    def fake_run(user_id, course_id, question):
        called.update({"mode": "json", "user_id": user_id, "course_id": course_id, "question": question})
        return {"tutor_response": {"text_explanation": "ok"}}

    monkeypatch.setattr(server.tutor_service, "run_tutor", fake_run)

    response = await server.api_session_tutor(_request({"question": "What is a heap?"}))

    assert isinstance(response, JSONResponse)
    assert called == {"mode": "json", "user_id": "u1", "course_id": "course1", "question": "What is a heap?"}


@pytest.mark.asyncio
async def test_session_tutor_stream_flag_uses_canonical_endpoint(monkeypatch):
    called = {}

    async def fake_stream(user_id, course_id, question):
        called.update({"mode": "stream", "user_id": user_id, "course_id": course_id, "question": question})
        yield {"event": "done", "data": "{}"}

    monkeypatch.setattr(server.tutor_service, "stream_tutor", fake_stream)

    response = await server.api_session_tutor(_request({"question": "Explain trees", "stream": True}))

    assert response.__class__.__name__ == "EventSourceResponse"
    assert called == {}
    assert response.body_iterator is not None


@pytest.mark.asyncio
async def test_session_tutor_accept_header_uses_canonical_endpoint(monkeypatch):
    called = {}

    async def fake_stream(user_id, course_id, question):
        called.update({"mode": "stream", "user_id": user_id, "course_id": course_id, "question": question})
        yield {"event": "done", "data": "{}"}

    monkeypatch.setattr(server.tutor_service, "stream_tutor", fake_stream)

    response = await server.api_session_tutor(_request({"question": "Explain trees"}, accept="text/event-stream"))

    assert response.__class__.__name__ == "EventSourceResponse"
    assert called == {}
    assert response.body_iterator is not None


@pytest.mark.asyncio
async def test_session_tutor_stream_alias_is_deprecated(monkeypatch):
    async def fake_stream(user_id, course_id, question):
        yield {"event": "done", "data": "{}"}

    monkeypatch.setattr(server.tutor_service, "stream_tutor", fake_stream)

    response = await server.api_session_tutor_stream(_request({"question": "Explain trees"}))

    assert response.__class__.__name__ == "EventSourceResponse"
    assert response.headers["x-eduagent-api-status"] == "deprecated"
    assert response.headers["x-eduagent-canonical-api"] == "/api/sessions/{session_id}/tutor"


@pytest.mark.asyncio
async def test_session_tutor_stream_alias_bridges_to_session_tutor_response(monkeypatch):
    called = {}

    def fake_session_tutor_response(user_id, course_id, body, accept_header="", headers=None):
        called.update({
            "user_id": user_id,
            "course_id": course_id,
            "body": body,
            "headers": headers,
        })
        return JSONResponse({"ok": True}, headers=headers)

    monkeypatch.setattr(server, "_session_tutor_response", fake_session_tutor_response)

    response = await server.api_session_tutor_stream(_request({"question": "Explain trees"}))

    assert isinstance(response, JSONResponse)
    assert called["user_id"] == "u1"
    assert called["course_id"] == "course1"
    assert called["body"]["question"] == "Explain trees"
    assert called["body"]["stream"] is True
    assert called["headers"]["X-EduAgent-Canonical-Api"] == "/api/sessions/{session_id}/tutor"


@pytest.mark.asyncio
async def test_compat_tutor_json_bridges_to_session_tutor_response(monkeypatch):
    called = {}

    def fake_session_tutor_response(user_id, course_id, body, accept_header="", headers=None):
        called.update({
            "user_id": user_id,
            "course_id": course_id,
            "body": body,
            "accept_header": accept_header,
            "headers": headers,
        })
        return JSONResponse({"ok": True}, headers=headers)

    monkeypatch.setattr(server, "_session_tutor_response", fake_session_tutor_response)

    response = await server.api_compat_ask_tutor(_compat_request({
        "user_id": "u2",
        "course_id": "course2",
        "query": "Explain trees",
        "stream": True,
    }))

    assert isinstance(response, JSONResponse)
    assert called["user_id"] == "u2"
    assert called["course_id"] == "course2"
    assert called["body"]["query"] == "Explain trees"
    assert called["body"]["stream"] is False
    assert called["headers"]["X-EduAgent-Canonical-Api"] == "/api/sessions/{session_id}/tutor"


@pytest.mark.asyncio
async def test_compat_tutor_stream_bridges_to_session_tutor_response(monkeypatch):
    called = {}

    def fake_session_tutor_response(user_id, course_id, body, accept_header="", headers=None):
        called.update({
            "user_id": user_id,
            "course_id": course_id,
            "body": body,
            "headers": headers,
        })
        return JSONResponse({"ok": True}, headers=headers)

    monkeypatch.setattr(server, "_session_tutor_response", fake_session_tutor_response)

    response = await server.api_compat_ask_tutor_stream(_compat_request({
        "user_id": "u3",
        "course_id": "course3",
        "question": "Explain heaps",
    }, path="/api/tutor/ask-stream"))

    assert isinstance(response, JSONResponse)
    assert called["user_id"] == "u3"
    assert called["course_id"] == "course3"
    assert called["body"]["question"] == "Explain heaps"
    assert called["body"]["stream"] is True
    assert called["headers"]["X-EduAgent-Canonical-Api"] == "/api/sessions/{session_id}/tutor"


def test_legacy_tutor_handler_names_are_compat_bridges():
    assert server.api_ask_tutor is server.api_compat_ask_tutor
    assert server.api_ask_tutor_stream is server.api_compat_ask_tutor_stream
