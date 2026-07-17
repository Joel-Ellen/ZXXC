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
    assert result["agent_feedback"][0]["status"] == "success"


def test_tutor_stream_fallback_can_defer_history_persistence(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)

    def fake_tutor(inp):
        inp.agent_state.tutor_response = {"text_explanation": "safe response"}
        return TutorOutput(inp.agent_state)

    monkeypatch.setattr(fake, "tutor", fake_tutor)
    tutor_service.run_tutor(
        "u-deferred-history",
        "course1",
        "Explain the invariant.",
        persist_history=False,
    )

    state = fake.get_session("u-deferred-history", "course1").agent_state
    categories = state.internal_state.get("learning_assets", {}).get("categories", {})
    assert categories.get("tutor_history", {}) == {}


def test_tutor_validates_every_context_text_field(monkeypatch):
    seen_fields = []

    class TrackingPipeline(FakeValidationPipeline):
        def validate_input(self, text="", payload=None, field="input"):
            seen_fields.append(field)
            result = super().validate_input(text=text, payload=payload, field=field)
            if field == "code_snippet":
                result.add_issue("unsafe_code_context", "forced code-context rejection", field=field)
            return result

    monkeypatch.setattr(
        "src.application._common.get_validation_pipeline",
        lambda: TrackingPipeline(),
    )

    result = tutor_service.run_tutor(
        "u-context",
        "course1",
        "Why does this fail?",
        context_type="code_debug",
        code_snippet="raise RuntimeError()",
        error_message="RuntimeError",
    )

    assert result["tutor_response"]["blocked"] is True
    assert {"question", "code_snippet", "error_message"} <= set(seen_fields)


def test_tutor_stream_renders_structured_output_without_exposing_json_contract(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        "src.application.tutor_service.get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )

    class StructuredStreamLlm:
        async def chat_stream(self, _messages):
            for token in (
                "```",
                'json\n{"core_definition":"A binary tree gives each node at most two children.",',
                '"common_misconceptions":["It is not necessarily balanced."]}\n```',
            ):
                yield token

    fake.get_llm = lambda: StructuredStreamLlm()

    async def collect_events():
        return [
            event
            async for event in tutor_service.stream_tutor(
                "u-structured-stream",
                "course1",
                "What is a binary tree?",
                context_type="concept",
            )
        ]

    events = asyncio.run(collect_events())
    visible_text = "".join(
        json.loads(event["data"])["token"]
        for event in events
        if event["event"] == "token"
    )

    assert "core_definition" not in visible_text
    assert "### 核心定义" in visible_text
    assert "binary tree gives each node" in visible_text
    assert events[-1]["event"] == "done"
    state = fake.get_session("u-structured-stream", "course1").agent_state
    assert state.tutor_response["text_explanation"] == visible_text


def test_tutor_stream_resets_partial_text_before_fallback(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setenv("EDUAGENT_TUTOR_TIMEOUT_SEC", "0.01")
    monkeypatch.setattr(
        "src.application.tutor_service.get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )

    class SlowStreamLlm:
        async def chat_stream(self, _messages):
            yield "Partial answer that must be replaced."
            await asyncio.sleep(1)

    def fake_tutor(inp):
        inp.agent_state.tutor_response = {"text_explanation": "Fallback answer."}
        return TutorOutput(inp.agent_state)

    fake.get_llm = lambda: SlowStreamLlm()
    monkeypatch.setattr(fake, "tutor", fake_tutor)

    async def collect_events():
        return [
            event
            async for event in tutor_service.stream_tutor(
                "u-reset-stream",
                "course1",
                "Explain an invariant.",
            )
        ]

    events = asyncio.run(collect_events())
    event_names = [event["event"] for event in events]
    reset_index = event_names.index("reset")
    visible_after_reset = "".join(
        json.loads(event["data"])["token"]
        for event in events[reset_index + 1:]
        if event["event"] == "token"
    )

    assert event_names[0] == "token"
    assert visible_after_reset == "Fallback answer."
    assert events[-1]["event"] == "done"
