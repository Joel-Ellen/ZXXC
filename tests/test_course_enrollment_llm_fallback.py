import os
import uuid

from starlette.testclient import TestClient


os.environ["DASHSCOPE_API_KEY"] = ""

from frontend import server  # noqa: E402
from src.auth.security import SecurityManager  # noqa: E402


def test_course_enrollment_does_not_block_on_session_or_llm_initialization(monkeypatch):
    user_id = f"enroll-fallback-{uuid.uuid4().hex}"
    server.sessions.pop(user_id, None)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-" + "x" * 40)
    monkeypatch.setattr(server, "_llm_client", None)
    monkeypatch.setattr(server, "_llm_unavailable", False)

    import src.llm

    attempts = 0

    def unavailable_client(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise ImportError("optional openai dependency is unavailable")

    monkeypatch.setattr(src.llm, "LLMClientV2", unavailable_client, raising=False)

    token = SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
    response = TestClient(server.app).post(
        "/api/user/courses/enroll",
        json={"user_id": user_id, "course_id": "data_structures"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "enrolled"
    assert user_id not in server.sessions
    assert server._llm_unavailable is False
    assert attempts == 0
