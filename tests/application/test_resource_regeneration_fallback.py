from src.application import resource_service
from tests.helpers import FakeValidationPipeline, disable_persistence, install_fake_runtime


def test_resource_regeneration_rejects_invalid_generation(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr("src.application.resource_service.get_validation_pipeline", lambda: FakeValidationPipeline(pass_resource=False))

    result = resource_service.generate_current_node_resources("u5", "course1", "N01", force=True)
    assert result["status"] == "generated"
    assert result["resources"] == []
    assert "cards" not in result
    assert fake.get_session("u5", "course1").agent_state.errors
