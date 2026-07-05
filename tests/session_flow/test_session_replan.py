from src.application import session_service
from tests.helpers import disable_persistence, install_fake_runtime


def test_session_replan_recomputes_path(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    session = fake.get_session("u4", "course1")
    session.agent_state.active_path = []
    session.agent_state.trigger_replan()

    response = session_service.advance_session(
        "u4",
        "course1",
        behavior={"interaction_type": "load_node", "current_node_id": "N02"},
    )
    assert response["active_path"][0] == "N02"
    assert response["re_plan_triggered"] is False
