import asyncio
import json
import time

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


def test_tutor_timeout_returns_validated_fallback(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setenv("EDUAGENT_TUTOR_TIMEOUT_SEC", "0.1")

    def slow_tutor(inp):
        time.sleep(1)
        return TutorOutput(inp.agent_state)

    monkeypatch.setattr(fake, "tutor", slow_tutor)
    result = tutor_service.run_tutor("u-timeout", "course1", "Give me a hint.")
    assert result["tutor_response"]["fallback"] is True
    assert "智能辅导本次响应超时" in result["tutor_response"]["text_explanation"]
    assert "The live tutor" not in result["tutor_response"]["text_explanation"]
    assert result["agent_feedback"][0]["status"] == "success"


def test_stream_timeout_uses_chinese_local_fallback_without_second_llm_call(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        "src.application.tutor_service.get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )
    monkeypatch.setenv("EDUAGENT_TUTOR_TIMEOUT_SEC", "0.1")
    monkeypatch.setenv("EDUAGENT_TUTOR_MAX_TOKENS", "777")
    observed = {}

    class SlowStreamingLlm:
        async def chat_stream(self, messages, max_tokens=None):
            observed["max_tokens"] = max_tokens
            await asyncio.sleep(1)
            yield "不应返回"

    fake.get_llm = lambda: SlowStreamingLlm()
    monkeypatch.setattr(
        tutor_service,
        "run_tutor",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应重复调用模型")),
    )

    async def collect_events():
        return [
            event
            async for event in tutor_service._stream_tutor_unlimited(
                "u-stream-timeout",
                "course1",
                "什么是二叉搜索树？",
            )
        ]

    events = asyncio.run(collect_events())
    text = "".join(
        json.loads(event["data"]).get("token", "")
        for event in events
        if event["event"] == "token"
    )
    assert observed["max_tokens"] == 777
    assert "智能辅导本次响应超时" in text
    assert "The live tutor" not in text
