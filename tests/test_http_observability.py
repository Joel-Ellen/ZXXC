import os
import sys
import types

from starlette.testclient import TestClient

from src.observability import reset_metrics


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


def test_request_id_header_round_trip_and_metrics_endpoint():
    reset_metrics()
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
