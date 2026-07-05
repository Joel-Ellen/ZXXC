from src.application import session_service
from tests.helpers import disable_persistence, install_fake_runtime


class NoopOutput:
    def __init__(self, agent_state):
        self.agent_state = agent_state
        self.generated_cards = []
        self.valid_cards = []
        self.rejected_cards = []
        self.refined_cards = []
        self.overall_pass_rate = 1.0


def test_session_advance_load_node_happy_path(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    session_service.init_path("u3", "course1")

    monkeypatch.setattr(fake.mesh, "__call__", lambda inp: NoopOutput(inp.agent_state))
    monkeypatch.setattr(fake.validator, "__call__", lambda inp: NoopOutput(inp.agent_state))

    response = session_service.advance_session(
        "u3",
        "course1",
        behavior={"interaction_type": "load_node", "current_node_id": "N01"},
    )
    assert response["interaction_type"] == "load_node"
    assert response["current_node_id"] == "N01"
    assert any(log["agent"] == "Planner" for log in response["step_logs"])
