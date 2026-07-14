from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import psycopg2
import pytest

from src.auth.security import SecurityManager
from src.database import connection
from src.database import user_repo as user_repo_module
from src.database.user_repo import UserRepo


class _FakeCursor:
    def __init__(self, *, row=None, execute_error: Exception | None = None):
        self.row = row
        self.execute_error = execute_error
        self.executed: list[str] = []
        self.closed = False

    def execute(self, sql, _params=()):
        self.executed.append(sql)
        if self.execute_error is not None:
            raise self.execute_error

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor
        self.closed = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _UniqueConflict(psycopg2.IntegrityError):
    def __init__(self, constraint_name: str):
        super().__init__("duplicate key")
        self._constraint_name = constraint_name

    @property
    def pgcode(self):
        return "23505"

    @property
    def diag(self):
        return SimpleNamespace(constraint_name=self._constraint_name)


class _RepoDb:
    def __init__(self, *, fail_statement: str, constraint_name: str):
        self.fail_statement = fail_statement
        self.constraint_name = constraint_name
        self.calls: list[tuple[str, tuple]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        if self.fail_statement in sql:
            raise _UniqueConflict(self.constraint_name)
        return _FakeCursor(row=None)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({"APP_ENV": "production"}, True),
        ({"ENVIRONMENT": " PROD "}, True),
        ({"NODE_ENV": "production"}, True),
        ({"APP_ENV": "test", "NODE_ENV": "production"}, True),
        ({"APP_ENV": "test"}, False),
        ({}, False),
    ],
)
def test_production_environment_detection_is_explicit(environment, expected):
    assert connection.is_production_environment(environment) is expected
    assert connection.legacy_json_migrations_enabled(environment) is (not expected)


def test_schema_requires_unique_normalized_email_for_active_users():
    normalized_sql = " ".join(connection.CREATE_TABLES_SQL.lower().split())
    assert "create unique index if not exists uq_users_active_email_normalized" in normalized_sql
    assert "on users (lower(email)) where is_active = 1" in normalized_sql


def test_production_initialization_skips_legacy_json_migrations(monkeypatch):
    cursor = _FakeCursor()
    fake_connection = _FakeConnection(cursor)
    database = connection.Database()
    migrate_users = Mock()
    migrate_enrollments = Mock()
    monkeypatch.setattr(database, "_get_conn", lambda: fake_connection)
    monkeypatch.setattr(database, "_migrate_users", migrate_users)
    monkeypatch.setattr(database, "_migrate_enrollments", migrate_enrollments)
    monkeypatch.setenv("APP_ENV", "production")

    database._ensure_init()

    assert database._initialized is True
    assert fake_connection.commits == 1
    migrate_users.assert_not_called()
    migrate_enrollments.assert_not_called()


def test_development_initialization_runs_each_legacy_migration_once(monkeypatch):
    cursor = _FakeCursor()
    fake_connection = _FakeConnection(cursor)
    database = connection.Database()
    migrate_users = Mock()
    migrate_enrollments = Mock()
    monkeypatch.setattr(database, "_get_conn", lambda: fake_connection)
    monkeypatch.setattr(database, "_migrate_users", migrate_users)
    monkeypatch.setattr(database, "_migrate_enrollments", migrate_enrollments)
    monkeypatch.setenv("APP_ENV", "test")

    database._ensure_init()

    migrate_users.assert_called_once_with()
    migrate_enrollments.assert_called_once_with()


def test_unique_index_creation_failure_aborts_initialization(monkeypatch):
    unique_conflict = _UniqueConflict("uq_users_active_email_normalized")
    fake_connection = _FakeConnection(_FakeCursor(execute_error=unique_conflict))
    database = connection.Database()
    monkeypatch.setattr(database, "_get_conn", lambda: fake_connection)

    with pytest.raises(psycopg2.IntegrityError):
        database._ensure_init()

    assert database._initialized is False
    assert fake_connection.rollbacks == 1


def test_create_user_maps_concurrent_email_conflict_to_value_error(monkeypatch):
    fake_db = _RepoDb(
        fail_statement="INSERT INTO users",
        constraint_name="uq_users_active_email_normalized",
    )
    repo = UserRepo()
    monkeypatch.setattr(user_repo_module, "db", fake_db)
    monkeypatch.setattr(repo, "get_by_id", lambda _user_id: None)
    monkeypatch.setattr(repo, "get_by_email", lambda _email: None)
    monkeypatch.setattr(SecurityManager, "hash_password", staticmethod(lambda _password: "hash"))

    with pytest.raises(ValueError, match="alice@example.test"):
        repo.create_user("alice", "Alice@Example.Test", "Correct-Pass-123")

    assert fake_db.rollbacks == 1
    assert fake_db.commits == 0


def test_create_user_maps_concurrent_username_conflict_to_value_error(monkeypatch):
    fake_db = _RepoDb(
        fail_statement="INSERT INTO users",
        constraint_name="users_user_id_key",
    )
    repo = UserRepo()
    monkeypatch.setattr(user_repo_module, "db", fake_db)
    monkeypatch.setattr(repo, "get_by_id", lambda _user_id: None)
    monkeypatch.setattr(repo, "get_by_email", lambda _email: None)
    monkeypatch.setattr(SecurityManager, "hash_password", staticmethod(lambda _password: "hash"))

    with pytest.raises(ValueError, match="alice"):
        repo.create_user("alice", "alice@example.test", "Correct-Pass-123")

    assert fake_db.rollbacks == 1
    assert fake_db.commits == 0


def test_profile_email_update_maps_concurrent_conflict_to_value_error(monkeypatch):
    fake_db = _RepoDb(
        fail_statement="UPDATE users SET email",
        constraint_name="uq_users_active_email_normalized",
    )
    repo = UserRepo()
    monkeypatch.setattr(user_repo_module, "db", fake_db)
    monkeypatch.setattr(
        repo,
        "get_by_id",
        lambda _user_id: {
            "user_id": "alice",
            "email": "alice@example.test",
            "display_name": "Alice",
        },
    )

    with pytest.raises(ValueError, match="shared@example.test"):
        repo.update_public_profile("alice", email="Shared@Example.Test")

    assert fake_db.rollbacks == 1
    assert fake_db.commits == 0
