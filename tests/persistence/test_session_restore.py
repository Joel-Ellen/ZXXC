from src.application import _common
from src.infrastructure.cold_start import ColdStartEngine
from src.orchestration_runtime import RuntimeSession
from src.state.agent_state import AgentState
from tests.helpers import FakeRuntime


def test_session_restore_from_snapshot(monkeypatch):
    fake_runtime = FakeRuntime()
    state = AgentState(user_id="u", course_id="c", current_node_id="N02", target_node_id="N03")
    cold = ColdStartEngine().initialize("u")
    snapshot = {
        "state_json": state.model_dump(),
        "cold_state_json": cold.model_dump(),
        "pipeline_log_json": [{"agent": "Test"}],
    }

    class FakeSnapshotRepo:
        def get_latest(self, user_id, course_id):
            return snapshot

    monkeypatch.setattr(_common, "SessionSnapshotRepo", FakeSnapshotRepo)
    monkeypatch.setattr(_common, "StateRepo", None)
    monkeypatch.setattr(_common, "get_runtime", lambda: fake_runtime)

    restored = _common.load_persisted_session("u", "c")
    assert restored.agent_state.current_node_id == "N02"
    assert restored.pipeline_log == [{"agent": "Test"}]


def test_restore_or_create_falls_back_to_runtime(monkeypatch):
    fake_runtime = FakeRuntime()
    monkeypatch.setattr(_common, "load_persisted_session", lambda user_id, course_id="data_structures": None)
    monkeypatch.setattr(_common, "get_runtime", lambda: fake_runtime)
    monkeypatch.setattr(_common, "persist_session", lambda session: None)

    session = _common.restore_or_create_runtime_session("u", "c")
    assert session.agent_state.user_id == "u"
    assert fake_runtime.peek_session("u", "c") is session
