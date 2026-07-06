import time

from src.orchestration_runtime import OrchestrationRuntime


def test_orchestrator_llm_failure_falls_back(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-valid-looking-key-that-fails")

    def raise_init(*args, **kwargs):
        raise RuntimeError("llm down")

    import src.llm
    monkeypatch.setattr(src.llm, "LLMClientV2", raise_init, raising=False)
    runtime = OrchestrationRuntime()
    assert runtime.get_llm() is None
    content = runtime._generate_resource_content("N01", "concept_map", 0.5)
    assert "N01" in content


def test_resource_generation_timeout_falls_back(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("EDUAGENT_RESOURCE_LLM_TIMEOUT_SEC", "0.1")

    class SlowLLM:
        def generate_content(self, node_id, card_type, difficulty):
            time.sleep(1)
            return "late content"

    runtime = OrchestrationRuntime()
    runtime._llm_client = SlowLLM()
    content = runtime._generate_resource_content("N01", "concept_map", 0.5)
    assert "N01" in content
    assert "late content" not in content
