from src.database.session_repo import SessionRepo


class FakeCursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDb:
    def __init__(self):
        self.calls = []
        self.row = None

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "SELECT * FROM learning_sessions" in sql:
            return FakeCursor(self.row)
        return FakeCursor(None)

    def commit(self):
        self.calls.append(("COMMIT", ()))


def test_session_repo_upsert_inserts_when_missing(monkeypatch):
    fake_db = FakeDb()
    fake_db.row = None
    monkeypatch.setattr("src.database.session_repo.db", fake_db)

    repo = SessionRepo()
    repo.upsert("u", "c", current_node_id="N01", snapshot_version=1)
    assert any("INSERT INTO learning_sessions" in sql for sql, _ in fake_db.calls)


def test_session_repo_builds_stable_session_id():
    assert SessionRepo.build_session_id("u", "c") == "u:c"
