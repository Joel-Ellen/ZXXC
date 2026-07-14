from __future__ import annotations

from types import SimpleNamespace

import jwt
import pytest
from starlette.testclient import TestClient

from frontend import server
from src.auth.security import (
    ALGORITHM,
    DEV_JWT_SECRET_KEY,
    SecurityConfigurationError,
    SecurityManager,
    validate_security_configuration,
)


VALID_PRODUCTION_SECRET = "production-test-secret-with-at-least-32-characters"


@pytest.mark.parametrize(
    "secret",
    [
        None,
        "",
        "short-secret",
        "change-me-in-production",
        "prod_secret_sign_key_997126_edu_agent",
        DEV_JWT_SECRET_KEY,
    ],
)
def test_production_rejects_missing_default_or_short_jwt_secret(monkeypatch, secret):
    monkeypatch.setenv("APP_ENV", "production")
    if secret is None:
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET_KEY", secret)
    with pytest.raises(SecurityConfigurationError, match="JWT_SECRET_KEY"):
        validate_security_configuration()
    with pytest.raises(SecurityConfigurationError):
        SecurityManager.create_token_pair("alice", "STUDENT", session_id="device-one")


def test_production_requires_sid_for_issued_and_decoded_tokens(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_PRODUCTION_SECRET)
    validate_security_configuration()

    with pytest.raises(SecurityConfigurationError, match="session_id"):
        SecurityManager.create_token_pair("alice", "STUDENT")

    sidless = jwt.encode(
        {"sub": "alice", "type": "access", "jti": "legacy", "role": "STUDENT"},
        VALID_PRODUCTION_SECRET,
        algorithm=ALGORITHM,
    )
    with pytest.raises(ValueError, match="SESSION_REQUIRED"):
        SecurityManager.decode_token(sidless)

    pair = SecurityManager.create_token_pair("alice", "STUDENT", session_id="device-one")
    assert SecurityManager.decode_token(pair["access_token"])["sid"] == "device-one"


def test_production_auth_storage_failure_returns_503_without_json_fallback(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_PRODUCTION_SECRET)
    monkeypatch.setattr(server, "_db_available", False)
    monkeypatch.setattr(server, "_user_repo", None)
    monkeypatch.setattr(server, "_auth_captcha", None)
    monkeypatch.setattr(server, "_auth_backend_durable", False)

    response = TestClient(server.app).get("/api/auth/captcha-json")

    assert response.status_code == 503
    assert response.json()["detail"] == "AUTH_STORAGE_UNAVAILABLE"
    assert response.headers["cache-control"] == "no-store"


def test_production_auth_uses_shared_captcha_storage(monkeypatch):
    class UserRepo:
        def count(self):
            return 1

    class SharedRedis:
        def set(self, *_args, **_kwargs):
            return True

        def getdel(self, _key):
            return None

    shared_redis = SharedRedis()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_PRODUCTION_SECRET)
    monkeypatch.setattr(server, "_db_available", True)
    monkeypatch.setattr(server, "_user_repo", None)
    monkeypatch.setattr(server, "_auth_captcha", None)
    monkeypatch.setattr(server, "_auth_backend_durable", False)
    monkeypatch.setattr(server, "_get_user_repo", lambda: UserRepo())
    monkeypatch.setattr(server, "get_redis", lambda: shared_redis)
    monkeypatch.setattr(server, "redis_backend_status", lambda: "redis")

    _store, captcha = server._get_auth()

    assert captcha.uses_shared_backend is True


def test_shared_captcha_failure_returns_retryable_503(monkeypatch):
    from src.auth.captcha import CaptchaGenerator

    class BrokenRedis:
        def set(self, *_args, **_kwargs):
            raise ConnectionError("redis unavailable")

    captcha = CaptchaGenerator(redis_client=BrokenRedis(), require_shared=True)
    monkeypatch.setattr(server, "_get_auth", lambda: (object(), captcha))

    response = TestClient(server.app).get("/api/auth/captcha-json")

    assert response.status_code == 503
    assert response.json()["detail"] == "AUTH_STORAGE_UNAVAILABLE"
    assert response.headers["retry-after"] == "5"


def _headers(user_id: str) -> dict[str, str]:
    token = SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
    return {"Authorization": f"Bearer {token}"}


SESSION_OWNER_ROUTES = [
    ("GET", "/api/sessions/alice%3Acourse-a", None),
    ("GET", "/api/sessions/alice%3Acourse-a/profile-probe", None),
    ("POST", "/api/sessions/alice%3Acourse-a/profile-input", {"answer": "a"}),
    ("POST", "/api/sessions/alice%3Acourse-a/path/init", {}),
    ("POST", "/api/sessions/alice%3Acourse-a/advance", {}),
    ("POST", "/api/sessions/alice%3Acourse-a/behavior", {}),
    ("POST", "/api/sessions/alice%3Acourse-a/events", {}),
    ("GET", "/api/sessions/alice%3Acourse-a/events", None),
    ("GET", "/api/sessions/alice%3Acourse-a/assets", None),
    ("PATCH", "/api/sessions/alice%3Acourse-a/assets", {}),
    ("GET", "/api/sessions/alice%3Acourse-a/review", None),
    ("POST", "/api/sessions/alice%3Acourse-a/review/items/item-1/start", {}),
    ("POST", "/api/sessions/alice%3Acourse-a/review/items/item-1/prepare-retest", {}),
    ("GET", "/api/sessions/alice%3Acourse-a/practice/problems/problem-1", None),
    ("POST", "/api/sessions/alice%3Acourse-a/practice/run", {}),
    ("POST", "/api/sessions/alice%3Acourse-a/practice/submit", {}),
    ("POST", "/api/sessions/alice%3Acourse-a/tutor", {"question": "help"}),
    ("POST", "/api/sessions/alice%3Acourse-a/tutor-stream", {"question": "help"}),
    ("POST", "/api/sessions/alice%3Acourse-a/replan", {}),
    ("GET", "/api/sessions/alice%3Acourse-a/resources/N01", None),
]


@pytest.mark.parametrize("method,path,body", SESSION_OWNER_ROUTES)
def test_every_official_session_subroute_requires_bearer(method, path, body):
    response = TestClient(server.app).request(method, path, json=body)
    assert response.status_code == 401, (method, path, response.text)


@pytest.mark.parametrize("method,path,body", SESSION_OWNER_ROUTES)
def test_every_official_session_subroute_rejects_cross_user(method, path, body, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    response = TestClient(server.app).request(method, path, json=body, headers=_headers("mallory"))
    assert response.status_code == 403, (method, path, response.text)
    assert response.json()["detail"] == "SESSION_USER_MISMATCH"


def test_create_session_requires_bearer_and_ignores_body_user_id(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    calls = []

    def restore(user_id, course_id):
        calls.append((user_id, course_id))
        return {"user_id": user_id, "course_id": course_id}

    monkeypatch.setattr(server.session_service, "restore_or_create_session", restore)
    client = TestClient(server.app)
    assert client.post(
        "/api/sessions", json={"user_id": "victim", "course_id": "course-a"}
    ).status_code == 401

    created = client.post(
        "/api/sessions",
        json={"user_id": "victim", "course_id": "course-a"},
        headers=_headers("alice"),
    )
    assert created.status_code == 200
    assert created.json()["session_id"] == "alice:course-a"
    assert calls == [("alice", "course-a")]


def test_deleted_identity_cannot_use_a_lingering_persistent_session(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    pair = SecurityManager.create_token_pair("alice", "STUDENT", session_id="device-one")
    monkeypatch.setattr(server, "is_blacklisted", lambda _jti: False)
    monkeypatch.setattr(
        server,
        "_account_repo",
        SimpleNamespace(is_device_session_active=lambda *_args, **_kwargs: True),
    )
    monkeypatch.setattr(server, "_user_repo", SimpleNamespace(get_by_id=lambda _user_id: None))
    monkeypatch.setattr(server, "_auth_captcha", object())

    response = TestClient(server.app).get(
        "/api/sessions/alice%3Acourse-a",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "USER_NOT_FOUND"
