import threading
import time

from src.orchestration_runtime import OrchestrationRuntime


def test_orchestrator_llm_failure_falls_back(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-valid-looking-key-that-fails")

    def raise_init(*args, **kwargs):
        raise RuntimeError("llm down")

    import src.llm.client_v2
    monkeypatch.setattr(src.llm.client_v2, "LLMClientV2", raise_init)
    runtime = OrchestrationRuntime()
    assert runtime.get_llm() is None
    content = runtime.generate_resource_content("N01", "concept_map", 0.5)
    assert "N01" in content


def test_resource_generation_uses_concrete_v2_client_and_keeps_provenance(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-valid-looking-key-that-works")
    monkeypatch.setenv("EDUAGENT_LLM_FALLBACKS", "")

    class FakeLLM:
        def __init__(self, provider):
            self.provider = provider
            self.config = {"model": "fake-learning-model"}

        def compute_nli_entailment(self, *_args):
            return 0.5

        def generate_content(self, node_id, card_type, difficulty, *, timeout_sec=None):
            assert timeout_sec is not None
            return f"## {node_id} {card_type} from the model"

    import src.llm.client_v2
    monkeypatch.setattr(src.llm.client_v2, "LLMClientV2", FakeLLM)

    runtime = OrchestrationRuntime()
    result = runtime.generate_resource_content_result("N01", "concept_map", 0.5)

    assert result.source == "llm"
    assert result.provider == "dashscope"
    assert result.model == "fake-learning-model"
    assert "from the model" in result.content


def test_resource_batch_respects_the_configured_parallelism(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("EDUAGENT_RESOURCE_LLM_TIMEOUT_SEC", "1")
    monkeypatch.setenv("EDUAGENT_RESOURCE_LLM_TOTAL_TIMEOUT_SEC", "1")
    monkeypatch.setenv("EDUAGENT_RESOURCE_LLM_PARALLELISM", "2")

    lock = threading.Lock()
    active = 0
    max_active = 0

    class ProbeLLM:
        provider = "probe"
        config = {"model": "parallelism-probe"}

        def generate_content(self, node_id, card_type, difficulty, *, timeout_sec=None):
            nonlocal active, max_active
            assert timeout_sec is not None
            with lock:
                active += 1
                max_active = max(max_active, active)
            try:
                time.sleep(0.03)
                return f"## {node_id} {card_type}"
            finally:
                with lock:
                    active -= 1

    runtime = OrchestrationRuntime()
    runtime._llm_client = ProbeLLM()
    try:
        results = runtime.generate_resource_contents(
            "N01",
            ["concept_map", "code_snippet", "interactive_exercise", "video_summary"],
            0.5,
        )
    finally:
        runtime._resource_generation_pool.shutdown(wait=True)

    assert set(results) == {"concept_map", "code_snippet", "interactive_exercise", "video_summary"}
    assert all(result.source == "llm" for result in results.values())
    assert max_active == 2


def test_resource_generation_timeout_falls_back(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("EDUAGENT_RESOURCE_LLM_TIMEOUT_SEC", "0.1")

    class SlowLLM:
        def generate_content(self, node_id, card_type, difficulty):
            time.sleep(1)
            return "late content"

    runtime = OrchestrationRuntime()
    runtime._llm_client = SlowLLM()
    content = runtime.generate_resource_content("N01", "concept_map", 0.5)
    assert "N01" in content
    assert "late content" not in content


def test_resource_generation_forwards_canonical_course_and_title(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    captured = {}

    class BoundLLM:
        provider = "bound"
        config = {"model": "binding-probe"}

        def generate_content(
            self,
            node_id,
            card_type,
            difficulty,
            *,
            timeout_sec=None,
            course_id="",
            node_title="",
        ):
            captured.update(
                node_id=node_id,
                card_type=card_type,
                course_id=course_id,
                node_title=node_title,
            )
            return f"## {node_title}\n\nbound content"

    runtime = OrchestrationRuntime()
    runtime._llm_client = BoundLLM()
    runtime._llm_provider_order = []
    try:
        result = runtime.generate_resource_content_result(
            "N01",
            "concept_map",
            0.5,
            course_id="data_structures",
            node_title="算法复杂度分析",
        )
    finally:
        runtime._resource_generation_pool.shutdown(wait=True)

    assert result.source == "llm"
    assert captured == {
        "node_id": "N01",
        "card_type": "concept_map",
        "course_id": "data_structures",
        "node_title": "算法复杂度分析",
    }


def test_v2_resource_prompt_binds_course_node_and_canonical_title():
    from src.llm.client_v2 import LLMClientV2

    captured = {}
    client = object.__new__(LLMClientV2)

    def capture(messages, timeout_sec=None):
        captured["messages"] = messages
        captured["timeout_sec"] = timeout_sec
        return "ok"

    client._sync_chat_wrapper = capture
    result = client.generate_content(
        "N01",
        "concept_map",
        0.5,
        timeout_sec=3.0,
        course_id="data_structures",
        node_title="算法复杂度分析",
    )

    assert result == "ok"
    assert captured["timeout_sec"] == 3.0
    prompt = "\n".join(message["content"] for message in captured["messages"])
    assert "课程 ID: data_structures" in prompt
    assert "知识点 ID: N01" in prompt
    assert "规范知识点标题: 算法复杂度分析" in prompt
    assert "第一个 Markdown 标题必须包含服务端给出的规范标题" in prompt


def test_resource_batch_uses_one_hard_deadline_across_worker_waves(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")

    class SlowLLM:
        provider = "slow"
        config = {"model": "deadline-probe"}

        def generate_content(self, *_args, **_kwargs):
            time.sleep(0.35)
            return "late content"

    runtime = OrchestrationRuntime()
    runtime._llm_client = SlowLLM()
    runtime._llm_provider_order = []
    runtime._resource_generation_parallelism = 1
    runtime._resource_llm_timeout_sec = 0.12
    runtime._resource_llm_total_timeout_sec = 0.12
    started = time.monotonic()
    try:
        results = runtime.generate_resource_contents(
            "N01",
            ["concept_map", "code_snippet", "interactive_exercise", "video_summary"],
            0.5,
            course_id="data_structures",
            node_title="算法复杂度分析",
        )
        elapsed = time.monotonic() - started
    finally:
        runtime._resource_generation_pool.shutdown(wait=True)

    assert elapsed < 0.28
    assert all(result.source == "template" for result in results.values())
    assert sum(result.attempt_count for result in results.values()) == 1
