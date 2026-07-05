from src.application import tutor_service
from tests.helpers import FakeValidationPipeline, disable_persistence, install_fake_runtime


class TutorOutput:
    def __init__(self, state):
        self.agent_state = state


def test_tutor_safety_fallback_blocks_unsafe_output(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr("src.application.tutor_service.get_validation_pipeline", lambda: FakeValidationPipeline(pass_tutor=False))

    def fake_tutor(inp):
        inp.agent_state.tutor_response = {"text_explanation": "unsafe raw"}
        return TutorOutput(inp.agent_state)

    monkeypatch.setattr(fake, "tutor", fake_tutor)
    result = tutor_service.run_tutor("u6", "course1", "What is a tree?")
    assert result["tutor_response"]["blocked"] is True
    assert result["agent_feedback"][0]["status"] == "error"
