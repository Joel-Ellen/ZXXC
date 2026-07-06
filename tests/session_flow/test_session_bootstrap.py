from src.application import session_service
from tests.helpers import disable_persistence, install_fake_runtime


def test_session_bootstrap_restores_or_creates(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    response = session_service.restore_or_create_session("u1", "course1")
    assert response["session"]["user_id"] == "u1"
    assert response["session"]["course_id"] == "course1"
    assert "user_id" not in response
    assert "generated_resources" not in response
    assert fake.peek_session("u1", "course1") is not None


def test_init_path_sets_current_node(monkeypatch):
    install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    response = session_service.init_path("u2", "course1")
    assert response["active_path"] == ["N01", "N02", "N03"]
    assert response["current_node_id"] == "N01"
