import uuid
from types import SimpleNamespace

from starlette.testclient import TestClient

from frontend import server
from src.auth.security import SecurityManager


def test_memory_enrollment_fallback_persists_selection_and_progress(monkeypatch):
    user_id = f"memory-enrollment-{uuid.uuid4().hex}"
    monkeypatch.setattr(server, "_db_available", False)
    monkeypatch.setattr(server, "_enrollment_repo", None)
    monkeypatch.setattr(server, "_fallback_enrollment_repo", server._InMemoryEnrollmentRepo())

    client = TestClient(server.app)
    token = SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post(
        "/api/user/courses/enroll",
        json={"user_id": user_id, "course_id": "data_structures"},
        headers=headers,
    ).status_code == 200

    # An unregistered course cannot become active merely because the DB is absent.
    assert client.post(
        "/api/user/courses/switch",
        json={"user_id": user_id, "course_id": "operating_systems"},
        headers=headers,
    ).status_code == 404

    assert client.post(
        "/api/user/courses/enroll",
        json={"user_id": user_id, "course_id": "operating_systems"},
        headers=headers,
    ).status_code == 200

    state = SimpleNamespace(
        active_path=["N01", "N02", "N03", "N04"],
        dynamic_profile=SimpleNamespace(
            knowledge_mastery={"N01": 0.75, "N02": 0.70, "N03": 0.30}
        ),
    )
    server._sync_enrollment_progress(user_id, "operating_systems", state)

    courses = client.get("/api/user/courses", params={"user_id": "attacker"}, headers=headers).json()
    by_id = {course["course_id"]: course for course in courses["courses"]}
    assert courses["active_course"] == "operating_systems"
    assert by_id["data_structures"]["progress"] == 0.0
    assert by_id["operating_systems"]["completed_nodes"] == 2
    assert by_id["operating_systems"]["progress"] == 0.5

    assert client.post(
        "/api/user/courses/switch",
        json={"user_id": user_id, "course_id": "data_structures"},
        headers=headers,
    ).status_code == 200
    assert client.get("/api/user/courses", headers=headers).json()["active_course"] == "data_structures"
