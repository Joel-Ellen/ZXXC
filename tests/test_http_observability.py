import os
import re
import sys
import types
import uuid
import io
import json
import logging

from starlette.testclient import TestClient

from src.observability import bind_context, log_event, reset_metrics


def _install_import_stubs() -> None:
    if "loguru" not in sys.modules:
        loguru_module = types.ModuleType("loguru")

        class _Logger:
            def __getattr__(self, _name):
                return lambda *args, **kwargs: None

        loguru_module.logger = _Logger()
        sys.modules["loguru"] = loguru_module

    if "openai" not in sys.modules:
        openai_module = types.ModuleType("openai")

        class _DummyOpenAI:
            def __init__(self, *args, **kwargs):
                pass

        openai_module.OpenAI = _DummyOpenAI
        openai_module.AsyncOpenAI = _DummyOpenAI
        sys.modules["openai"] = openai_module


os.environ["DASHSCOPE_API_KEY"] = ""
_install_import_stubs()

from frontend.server import app  # noqa: E402


def _captcha_answer(svg: str) -> str:
    match = re.search(r"(\d+)\s*([+\-x*])\s*(\d+)", svg)
    assert match is not None
    left = int(match.group(1))
    right = int(match.group(3))
    operator = match.group(2)
    if operator == "+":
        return str(left + right)
    if operator == "-":
        return str(left - right)
    return str(left * right)


def test_request_id_header_round_trip_and_metrics_endpoint(monkeypatch):
    reset_metrics()
    monkeypatch.setattr(
        "frontend.server.session_service.restore_or_create_session",
        lambda user_id, course_id: {"status": "ok"},
    )
    client = TestClient(app)

    response = client.post(
        "/api/sessions",
        json={"user_id": "http-obs", "course_id": "data_structures"},
        headers={"X-Request-ID": "req-observe-123"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-observe-123"

    metrics_response = client.get("/api/ops/metrics")
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert "counters" in payload
    assert any(
        counter["name"] == "http.request_total"
        and counter["labels"].get("method") == "POST"
        and counter["labels"].get("surface") == "session_api"
        and counter["labels"].get("status_family") == "2xx"
        for counter in payload["counters"]
    )


def test_structured_log_event_includes_request_context():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("eduagent")
    logger.addHandler(handler)
    try:
        with bind_context(request_id="req-log-123", user_id="u-log", operation="prelaunch"):
            log_event("prelaunch.structured_log_check", nested={"ok": True})
    finally:
        logger.removeHandler(handler)

    payload = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert payload["event"] == "prelaunch.structured_log_check"
    assert payload["request_id"] == "req-log-123"
    assert payload["user_id"] == "u-log"
    assert payload["operation"] == "prelaunch"
    assert payload["nested"] == {"ok": True}


def test_auth_register_login_and_me_accept_user_records():
    client = TestClient(app)
    user_id = f"http_auth_{uuid.uuid4().hex[:10]}"
    password = "Password123!"

    captcha = client.get("/api/auth/captcha-json").json()
    register_response = client.post(
        "/api/auth/register",
        json={
            "user_id": user_id,
            "email": f"{user_id}@example.com",
            "password": password,
            "captcha_token": captcha["captcha_token"],
            "captcha_answer": _captcha_answer(captcha["svg"]),
        },
    )
    assert register_response.status_code == 200
    assert register_response.json()["user"]["user_id"] == user_id

    login_captcha = client.get("/api/auth/captcha-json").json()
    login_response = client.post(
        "/api/auth/login",
        json={
            "user_id": user_id,
            "password": password,
            "captcha_token": login_captcha["captcha_token"],
            "captcha_answer": _captcha_answer(login_captcha["svg"]),
        },
    )
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]
    me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["user_id"] == user_id
