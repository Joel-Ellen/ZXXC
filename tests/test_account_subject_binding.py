from __future__ import annotations

import json

from src.auth import account_service
from src.auth.account_service import (
    action_subject_matches,
    consume_action_token,
    hash_action_subject,
    hash_action_token,
    issue_action_token,
)
from src.database.account_repo import CREATE_ACCOUNT_TABLES_SQL, JsonAccountRepo


def test_email_verification_token_is_bound_to_normalized_subject(tmp_path):
    path = tmp_path / "account.json"
    repo = JsonAccountRepo(str(path))
    token = issue_action_token(
        repo,
        "alice",
        "email_verification",
        3600,
        subject=" Alice@Example.Test ",
    )
    binding = repo.get_action_token_binding(hash_action_token(token), "email_verification")

    assert binding is not None
    assert "token_hash" not in binding
    assert binding["subject_hash"] == hash_action_subject("alice@example.test")
    assert "alice@example.test" not in path.read_text(encoding="utf-8").lower()
    assert action_subject_matches(binding["subject_hash"], "ALICE@example.test") is True
    assert consume_action_token(
        repo,
        token,
        "email_verification",
        subject="other@example.test",
    ) is None
    assert repo.get_action_token_binding(hash_action_token(token), "email_verification")["active"] is True

    assert consume_action_token(
        repo,
        token,
        "email_verification",
        subject="alice@example.test",
    ) == "alice"
    assert consume_action_token(
        repo,
        token,
        "email_verification",
        subject="alice@example.test",
    ) is None


def test_subject_validation_uses_constant_time_digest_comparison(monkeypatch):
    calls: list[tuple[str, str]] = []

    def compare(left: str, right: str) -> bool:
        calls.append((left, right))
        return left == right

    monkeypatch.setattr(account_service.hmac, "compare_digest", compare)
    stored = hash_action_subject("alice@example.test")

    assert action_subject_matches(stored, "Alice@Example.Test") is True
    assert len(calls) == 1
    assert calls[0] == (stored, stored)


def test_bound_and_unbound_tokens_cannot_cross_consumption_modes(tmp_path):
    repo = JsonAccountRepo(str(tmp_path / "account.json"))
    bound = issue_action_token(
        repo,
        "alice",
        "email_verification",
        3600,
        subject="alice@example.test",
    )
    assert consume_action_token(repo, bound, "email_verification") is None

    unbound = issue_action_token(repo, "alice", "password_reset", 3600)
    assert consume_action_token(
        repo,
        unbound,
        "password_reset",
        subject="alice@example.test",
    ) is None
    assert consume_action_token(repo, unbound, "password_reset") == "alice"


def test_verified_email_binding_is_normalized_and_persistent(tmp_path):
    path = tmp_path / "account.json"
    repo = JsonAccountRepo(str(path))

    marked = repo.mark_email_verified("alice", " Alice@Example.Test ")
    assert marked["email_verified_at"]
    assert marked["email_verified_for"] == "alice@example.test"

    reloaded = JsonAccountRepo(str(path)).get_settings("alice")
    assert reloaded["email_verified_at"] == marked["email_verified_at"]
    assert reloaded["email_verified_for"] == "alice@example.test"

    cleared = JsonAccountRepo(str(path)).clear_email_verification("alice")
    assert cleared["email_verified_at"] is None
    assert cleared["email_verified_for"] is None


def test_legacy_unbound_verification_record_degrades_to_unverified(tmp_path):
    path = tmp_path / "legacy-account.json"
    path.write_text(
        json.dumps({
            "settings": {
                "alice": {
                    "preferences": {},
                    "privacy": {},
                    "email_verified_at": "2026-07-13T00:00:00+00:00",
                    "updated_at": "2026-07-13T00:00:00+00:00",
                }
            },
            "action_tokens": {},
            "device_sessions": {},
        }),
        encoding="utf-8",
    )

    repo = JsonAccountRepo(str(path))
    legacy = repo.get_settings("alice")
    assert legacy["email_verified_at"] is None
    assert legacy["email_verified_for"] is None

    unbound_mark = repo.mark_email_verified("alice")
    assert unbound_mark["email_verified_at"] is None
    assert unbound_mark["email_verified_for"] is None


def test_postgres_schema_supports_verification_and_token_subject_bindings():
    normalized_sql = " ".join(CREATE_ACCOUNT_TABLES_SQL.lower().split())
    assert "add column if not exists email_verified_for varchar(256)" in normalized_sql
    assert "add column if not exists subject_hash varchar(128)" in normalized_sql
