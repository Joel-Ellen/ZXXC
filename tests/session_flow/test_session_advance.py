from src.application import session_service
from tests.helpers import disable_persistence, install_fake_runtime


def test_session_advance_load_node_happy_path(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    session_service.init_path("u3", "course1")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("load_node should not invoke heavy resource generation")

    fake.mesh = fail_if_called
    monkeypatch.setattr("src.application.resource_service.generate_current_node_resources", fail_if_called)

    response = session_service.advance_session(
        "u3",
        "course1",
        behavior={"interaction_type": "load_node", "current_node_id": "N01"},
    )
    assert response["interaction_type"] == "load_node"
    assert response["current_node_id"] == "N01"
    assert any(log["agent"] == "Planner" for log in response["step_logs"])
