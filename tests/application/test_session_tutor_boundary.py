import json

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from frontend import server


@pytest.fixture(autouse=True)
def _allow_direct_handler_calls(monkeypatch):
    """Keep these routing tests independent from session authentication."""
    monkeypatch.setattr(server, "_event_session_auth_error", lambda *_args, **_kwargs: None)


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


def test_legacy_tutor_surfaces_are_retired():
    assert not hasattr(server, "api_compat_ask_tutor")
    assert not hasattr(server, "api_compat_ask_tutor_stream")
    assert not hasattr(server, "api_session_tutor_stream")
