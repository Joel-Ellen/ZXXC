from __future__ import annotations

import json
import hashlib
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from frontend import server
from src.auth.captcha import CaptchaGenerator
from src.auth.models import UserStore
from src.auth.security import SecurityManager
from src.database.account_repo import JsonAccountRepo
from src.database.user_profile_repo import JsonUserProfileRepo


@pytest.fixture()
def account_app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.setattr(
        SecurityManager,
        "hash_password",
        staticmethod(lambda value: "test$" + hashlib.sha256(value.encode("utf-8")).hexdigest()),
    )
    monkeypatch.setattr(
        SecurityManager,
        "verify_password",
        staticmethod(
            lambda value, hashed: hashed == "test$" + hashlib.sha256(value.encode("utf-8")).hexdigest()
        ),
    )
    users = UserStore(str(tmp_path / "users.json"))
    account = JsonAccountRepo(str(tmp_path / "account.json"))
    profiles = JsonUserProfileRepo(str(tmp_path / "profiles.json"))
    enrollments = server._InMemoryEnrollmentRepo()
    monkeypatch.setattr(server, "_db_available", False)
    monkeypatch.setattr(server, "_user_repo", users)
    monkeypatch.setattr(server, "_auth_captcha", CaptchaGenerator())
    monkeypatch.setattr(server, "_account_repo", account)
    monkeypatch.setattr(server, "_profile_repo", profiles)
    monkeypatch.setattr(server, "_enrollment_repo", enrollments)
    monkeypatch.setattr(server, "_fallback_enrollment_repo", enrollments)
    monkeypatch.setattr(server, "_state_repo", None)
    monkeypatch.setattr(server, "_llm_client", None)
    monkeypatch.setattr(server, "_llm_unavailable", True)
    monkeypatch.setattr(server, "is_blacklisted", lambda _jti: False)
    monkeypatch.setattr(server, "blacklist_token", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "store_refresh_token", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "revoke_user_session", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "revoke_all_user_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "mark_rotated", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "is_rotated", lambda _jti: False)
    monkeypatch.setattr(server, "cache_action_token", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "consume_cached_action_token", lambda *_args, **_kwargs: None)
    return SimpleNamespace(
        client=TestClient(server.app),
        users=users,
        account=account,
        profiles=profiles,
        enrollments=enrollments,
        tmp_path=tmp_path,
    )


def _create_user(env, user_id="alice", password="Correct-Pass-123", email=None):
    return env.users.create_user(user_id, email or f"{user_id}@example.test", password)


def _session(env, user_id="alice", session_id="device-one"):
    user = env.users.get_by_id(user_id)
    pair = SecurityManager.create_token_pair(user_id, user.role, session_id=session_id)
    env.account.create_device_session(
        session_id,
        user_id,
        pair["refresh_jti"],
        device_name=session_id,
        user_agent="pytest",
        ip_address="127.0.0.1",
        expires_at=server.refresh_expiry_iso(),
    )
    return pair, {"Authorization": f"Bearer {pair['access_token']}"}


def test_profile_and_settings_are_persistent_and_email_change_revokes_old_verification(account_app):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)

    requested = env.client.post("/api/auth/email-verification/request", headers=headers)
    assert requested.status_code == 202
    old_token = requested.json()["dev_token"]

    missing_reauthentication = env.client.patch(
        "/api/user/profile",
        headers=headers,
        json={"email": "alice-new@example.test"},
    )
    wrong_reauthentication = env.client.patch(
        "/api/user/profile",
        headers=headers,
        json={"email": "alice-new@example.test", "current_password": "wrong"},
    )
    assert missing_reauthentication.status_code == 422
    assert wrong_reauthentication.status_code == 422
    assert missing_reauthentication.json()["detail"] == "PROFILE_REAUTHENTICATION_REQUIRED"
    assert env.users.get_by_id("alice").email == "alice@example.test"

    profile = env.client.patch(
        "/api/user/profile",
        headers=headers,
        json={
            "display_name": "Alice Zhang",
            "email": "alice-new@example.test",
            "current_password": "Correct-Pass-123",
            "university": "Example University",
            "learning_goal": "Finish the verified course path",
            "weekly_study_hours": 9,
            "preferred_resource_style": "code_first",
        },
    )
    assert profile.status_code == 200
    assert profile.json()["email"] == "alice-new@example.test"
    assert profile.json()["weekly_study_hours"] == 9
    assert profile.json()["email_verified"] is False
    assert env.client.post(
        "/api/auth/email-verification/verify", json={"token": old_token}
    ).status_code == 400

    settings = env.client.patch(
        "/api/user/settings",
        headers=headers,
        json={
            "preferences": {"theme": "dark", "fontSize": 18, "reduceMotion": True},
            "privacy": {"analyticsEnabled": True, "profileVisibility": "teachers"},
        },
    )
    assert settings.status_code == 200
    assert settings.json()["preferences"]["font_size"] == 18
    assert settings.json()["privacy"]["profile_visibility"] == "teachers"

    # A new repository instance reads the same durable files.
    persisted_profile = JsonUserProfileRepo(str(env.tmp_path / "profiles.json")).get_by_user_id("alice")
    persisted_settings = JsonAccountRepo(str(env.tmp_path / "account.json")).get_settings("alice")
    assert persisted_profile["learning_goal"] == "Finish the verified course path"
    assert persisted_settings["preferences"]["theme"] == "dark"


def test_password_reset_is_one_time_non_enumerating_and_revokes_access_session(account_app):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)

    known = env.client.post("/api/auth/password/forgot", json={"email": "alice@example.test"})
    unknown = env.client.post("/api/auth/password/forgot", json={"email": "nobody@example.test"})
    assert known.status_code == unknown.status_code == 202
    assert set(known.json()) == set(unknown.json())
    assert known.json()["message"] == unknown.json()["message"]
    assert len(known.json()["dev_token"]) == len(unknown.json()["dev_token"])

    reset = env.client.post(
        "/api/auth/password/reset",
        json={"token": known.json()["dev_token"], "new_password": "New-Correct-Pass-456"},
    )
    assert reset.status_code == 200
    assert env.users.verify_login("alice", "New-Correct-Pass-456") is not None
    assert env.client.post(
        "/api/auth/password/reset",
        json={"token": known.json()["dev_token"], "new_password": "Another-Pass-789"},
    ).status_code == 400
    assert env.client.get("/api/user/profile", headers=headers).status_code == 401


@pytest.mark.parametrize(
    "failure_layer",
    ["persistent_exception", "persistent_silent_failure", "cached_exception"],
)
def test_password_reset_keeps_token_and_password_when_session_revocation_fails(
    account_app,
    monkeypatch,
    failure_layer,
):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)
    token = env.client.post(
        "/api/auth/password/forgot",
        json={"email": "alice@example.test"},
    ).json()["dev_token"]
    original_persistent_revoke = env.account.revoke_all_device_sessions

    if failure_layer == "persistent_exception":
        def fail_persistent_revoke(_user_id):
            raise OSError("injected persistent-session failure")

        monkeypatch.setattr(env.account, "revoke_all_device_sessions", fail_persistent_revoke)
    elif failure_layer == "persistent_silent_failure":
        monkeypatch.setattr(env.account, "revoke_all_device_sessions", lambda _user_id: 0)
    else:
        def fail_cached_revoke(_user_id):
            raise OSError("injected cached-session failure")

        monkeypatch.setattr(server, "revoke_all_user_sessions", fail_cached_revoke)

    failed = env.client.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": "New-Correct-Pass-456"},
    )

    assert failed.status_code == 503
    assert failed.json()["detail"] == "SESSION_REVOCATION_FAILED"
    binding = env.account.get_action_token_binding(
        server.hash_action_token(token),
        "password_reset",
    )
    assert binding is not None and binding["active"] is True
    assert env.users.verify_login("alice", "Correct-Pass-123") is not None
    assert env.users.verify_login("alice", "New-Correct-Pass-456") is None

    monkeypatch.setattr(env.account, "revoke_all_device_sessions", original_persistent_revoke)
    monkeypatch.setattr(server, "revoke_all_user_sessions", lambda *_args, **_kwargs: None)
    retried = env.client.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": "New-Correct-Pass-456"},
    )
    assert retried.status_code == 200
    assert env.users.verify_login("alice", "New-Correct-Pass-456") is not None
    assert env.client.get("/api/user/profile", headers=headers).status_code == 401


def test_password_forgot_stays_non_enumerating_when_configured_delivery_fails(
    account_app,
    monkeypatch,
):
    env = account_app
    _create_user(env)
    monkeypatch.setattr(server, "email_delivery_configured", lambda: True)
    monkeypatch.setattr(server, "deliver_action_email", lambda *_args, **_kwargs: False)

    known = env.client.post("/api/auth/password/forgot", json={"email": "alice@example.test"})
    unknown = env.client.post("/api/auth/password/forgot", json={"email": "unknown@example.test"})

    assert known.status_code == unknown.status_code == 202
    assert set(known.json()) == set(unknown.json())
    assert known.json()["status"] == unknown.json()["status"] == "accepted"
    assert len(known.json()["dev_token"]) == len(unknown.json()["dev_token"])


def test_email_verification_token_sets_durable_status(account_app):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)
    requested = env.client.post("/api/auth/email-verification/request", headers=headers)
    verified = env.client.post(
        "/api/auth/email-verification/verify",
        json={"token": requested.json()["dev_token"]},
    )
    assert verified.status_code == 200
    assert verified.json()["email_verified"] is True
    assert env.client.get("/api/user/profile", headers=headers).json()["email_verified"] is True
    assert env.client.post(
        "/api/auth/email-verification/verify",
        json={"token": requested.json()["dev_token"]},
    ).status_code == 400


def test_device_session_listing_single_revoke_and_revoke_all(account_app):
    env = account_app
    _create_user(env)
    pair_one, headers_one = _session(env, session_id="device-one")
    pair_two, headers_two = _session(env, session_id="device-two")

    listed = env.client.get("/api/auth/sessions", headers=headers_one)
    assert listed.status_code == 200
    assert {item["session_id"] for item in listed.json()["sessions"]} == {"device-one", "device-two"}
    assert next(item for item in listed.json()["sessions"] if item["session_id"] == "device-one")["current"] is True

    revoked = env.client.delete("/api/auth/sessions/device-two", headers=headers_one)
    assert revoked.status_code == 200
    assert env.client.post(
        "/api/auth/refresh", json={"refresh_token": pair_two["refresh_token"]}
    ).status_code == 401
    assert env.client.get("/api/user/profile", headers=headers_two).status_code == 401

    all_revoked = env.client.delete("/api/auth/sessions", headers=headers_one)
    assert all_revoked.status_code == 200
    assert all_revoked.json()["revoked_count"] == 1
    assert env.client.get("/api/user/profile", headers=headers_one).status_code == 401
    assert pair_one["session_id"] == "device-one"


def test_learning_summary_and_unenroll_are_server_derived_and_preserve_history(account_app, monkeypatch):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)
    env.enrollments.enroll("alice", "data_structures")
    env.enrollments.update_progress("alice", "data_structures", 0.5, 2)
    env.enrollments.enroll("alice", "operating_systems")

    state = {
        "current_node_id": "N02",
        "active_path": ["N01", "N02", "N03", "N04"],
        "dynamic_profile": {"knowledge_mastery": {"N01": 0.8, "N02": 0.7}},
        "internal_state": {
            "learning_events": [
                {
                    "event_id": "server-event-1",
                    "event_type": "lesson_opened",
                    "node_id": "N02",
                    "resource_id": "resource-2",
                    "received_at": "2026-07-13T09:00:00+00:00",
                }
            ],
            "learning_assets": {
                "categories": {
                    "recent_learning": {
                        "server-event-1": {
                            "event_id": "server-event-1",
                            "event_type": "lesson_opened",
                            "node_id": "N02",
                            "resource_id": "resource-2",
                            "occurred_at": "2026-07-13T09:00:00+00:00",
                            "source": "server_event",
                        },
                        "forged": {
                            "event_id": "forged",
                            "event_type": "lesson_completed",
                            "node_id": "N99",
                            "occurred_at": "2099-01-01T00:00:00+00:00",
                            "source": "client_ui",
                        },
                    }
                }
            },
        },
    }

    class StateRows:
        @staticmethod
        def list_user_states(_user_id):
            return [{"course_id": "data_structures", "state_json": state, "updated_at": "2026-07-13T09:00:00+00:00"}]

    monkeypatch.setattr(server, "_state_repo", StateRows())
    summary = env.client.get("/api/user/learning-summary", headers=headers)
    assert summary.status_code == 200
    data_course = next(item for item in summary.json()["courses"] if item["course_id"] == "data_structures")
    assert data_course["progress"] == 0.5
    assert data_course["completed_nodes"] == 2
    assert data_course["total_nodes"] == 4
    assert summary.json()["continue_learning"]["node_id"] == "N02"
    assert all(item["node_id"] != "N99" for item in summary.json()["recent_learning"])

    # Removing a non-active course must preserve the active selection and the
    # durable state row for future re-enrollment/export.
    left = env.client.delete("/api/user/courses/data_structures", headers=headers)
    assert left.status_code == 200
    assert left.json()["active_course"] == "operating_systems"
    assert StateRows.list_user_states("alice")[0]["state_json"] == state


def test_course_mutations_require_bearer_and_ignore_client_user_id(account_app):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)
    assert env.client.get("/api/user/courses?user_id=alice").status_code == 401
    assert env.client.post(
        "/api/user/courses/enroll", json={"user_id": "attacker", "course_id": "data_structures"}
    ).status_code == 401
    enrolled = env.client.post(
        "/api/user/courses/enroll",
        headers=headers,
        json={"user_id": "attacker", "course_id": "data_structures"},
    )
    assert enrolled.status_code == 200
    assert enrolled.json()["user_id"] == "alice"
    assert env.enrollments.get_user_enrollments("attacker")["courses"] == {}


def test_export_omits_credentials_and_account_delete_requires_confirmation_and_password(account_app):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)
    env.enrollments.enroll("alice", "data_structures")
    env.profiles.upsert("alice", {"learning_goal": "Export this"})

    exported = env.client.get("/api/user/export", headers=headers)
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "no-store"
    assert exported.headers["pragma"] == "no-cache"
    payload_text = exported.text
    assert json.loads(payload_text)["profile"]["learning_goal"] == "Export this"
    assert "password_hash" not in payload_text
    assert "refresh_jti" not in payload_text
    assert "Correct-Pass-123" not in payload_text

    assert env.client.request(
        "DELETE", "/api/user/account", headers=headers, json={"confirmation": "DELETE"}
    ).status_code == 422
    assert env.client.request(
        "DELETE", "/api/user/account", headers=headers, json={"password": "Correct-Pass-123"}
    ).status_code == 422
    deleted = env.client.request(
        "DELETE",
        "/api/user/account",
        headers=headers,
        json={"confirmation": "DELETE", "password": "Correct-Pass-123"},
    )
    assert deleted.status_code == 200
    assert env.users.get_by_id("alice") is None
    assert env.enrollments.get_user_enrollments("alice")["courses"] == {}
    assert JsonUserProfileRepo(str(env.tmp_path / "profiles.json")).get_by_user_id("alice") is None
    assert env.client.get("/api/user/profile", headers=headers).status_code == 401


@pytest.mark.parametrize("failure_step", ["enrollments", "profile", "account_data"])
def test_account_delete_cleanup_failure_preserves_identity_and_can_retry(
    account_app,
    monkeypatch,
    failure_step,
):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)
    env.enrollments.enroll("alice", "data_structures")
    env.profiles.upsert("alice", {"learning_goal": "Delete safely"})

    targets = {
        "enrollments": (env.enrollments, "delete_all"),
        "profile": (env.profiles, "delete"),
        "account_data": (env.account, "delete_user_data"),
    }
    target, method_name = targets[failure_step]
    original_cleanup = getattr(target, method_name)

    def fail_cleanup(_user_id):
        raise OSError(f"injected {failure_step} cleanup failure")

    monkeypatch.setattr(target, method_name, fail_cleanup)
    failed = env.client.request(
        "DELETE",
        "/api/user/account",
        headers=headers,
        json={"confirmation": "DELETE", "password": "Correct-Pass-123"},
    )

    assert failed.status_code == 503
    assert failed.json()["detail"] == "ACCOUNT_DATA_CLEANUP_FAILED"
    assert env.users.get_by_id("alice") is not None
    assert env.account.list_device_sessions("alice") == []
    assert env.client.get("/api/user/profile", headers=headers).status_code == 401

    monkeypatch.setattr(target, method_name, original_cleanup)
    _retry_pair, retry_headers = _session(
        env,
        session_id=f"retry-{failure_step}",
    )
    retried = env.client.request(
        "DELETE",
        "/api/user/account",
        headers=retry_headers,
        json={"confirmation": "DELETE", "password": "Correct-Pass-123"},
    )
    assert retried.status_code == 200
    assert env.users.get_by_id("alice") is None
    assert env.account.list_device_sessions("alice") == []


def test_account_delete_identity_failure_is_retryable(account_app, monkeypatch):
    env = account_app
    _create_user(env)
    _pair, headers = _session(env)
    original_delete_user = env.users.delete_user
    monkeypatch.setattr(env.users, "delete_user", lambda _user_id: False)

    failed = env.client.request(
        "DELETE",
        "/api/user/account",
        headers=headers,
        json={"confirmation": "DELETE", "password": "Correct-Pass-123"},
    )

    assert failed.status_code == 503
    assert failed.json()["detail"] == "ACCOUNT_IDENTITY_DELETE_FAILED"
    assert env.users.get_by_id("alice") is not None

    monkeypatch.setattr(env.users, "delete_user", original_delete_user)
    _retry_pair, retry_headers = _session(env, session_id="identity-retry")
    retried = env.client.request(
        "DELETE",
        "/api/user/account",
        headers=retry_headers,
        json={"confirmation": "DELETE", "password": "Correct-Pass-123"},
    )
    assert retried.status_code == 200
    assert env.users.get_by_id("alice") is None
