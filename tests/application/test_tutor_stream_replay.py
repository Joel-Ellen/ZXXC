import asyncio
import json
from uuid import uuid4

import pytest

from src.agents.prompt_registry import build_user_prompt
from src.application import tutor_service
from src.validation.result import ValidationResult
from tests.helpers import FakeValidationPipeline, disable_persistence, install_fake_runtime


def _install_stream_runtime(monkeypatch, llm):
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        tutor_service,
        "get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )
    monkeypatch.setattr(runtime, "get_llm", lambda: llm)
    return runtime


@pytest.mark.parametrize(
    ("context_type", "next_field"),
    [
        ("concept", "core_definition"),
        ("problem_solving", "hints"),
        ("code_debug", "error_analysis"),
        ("exam_prep", "key_topics"),
        ("general", "diagram"),
    ],
)
def test_tutor_mode_prompt_puts_streamable_explanation_first(context_type, next_field):
    prompt = build_user_prompt(
        "tutor.mode",
        mode=context_type,
        query="请解释二叉树。",
        course_name="数据结构",
        student_context="",
        code_snippet="",
        error_message="",
    )
    schema = prompt[prompt.index("请严格返回 JSON："):]

    assert schema.index('"text_explanation"') < schema.index(f'"{next_field}"')
    if context_type == "general":
        assert '"response"' not in schema


@pytest.mark.asyncio
async def test_stream_yields_displayable_token_before_model_finishes(monkeypatch):
    release_model = asyncio.Event()

    class ControlledLlm:
        finished = False

        async def chat_stream(self, messages, max_tokens=None):
            del messages, max_tokens
            yield "第一段回答"
            await release_model.wait()
            yield "，第二段说明。"
            self.finished = True

    llm = ControlledLlm()
    _install_stream_runtime(monkeypatch, llm)
    stream = tutor_service._stream_tutor_unlimited(
        "stream-user",
        "course1",
        "请解释二叉树。",
        stream_id=f"live-{uuid4().hex}",
    )
    events = []
    first_event_arrived = asyncio.Event()

    async def consume():
        async for event in stream:
            events.append(event)
            first_event_arrived.set()

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(first_event_arrived.wait(), timeout=0.5)
    first = events[0]

    assert first["event"] == "token"
    assert first["id"] == "1"
    assert json.loads(first["data"])["token"] == "第一段回答"
    assert llm.finished is False

    release_model.set()
    await asyncio.wait_for(consumer, timeout=0.5)
    assert [int(event["id"]) for event in events] == list(range(1, len(events) + 1))
    assert events[-1]["event"] == "done"
    assert llm.finished is True


@pytest.mark.asyncio
async def test_structured_stream_yields_text_explanation_before_json_finishes(monkeypatch):
    release_model = asyncio.Event()

    class ControlledLlm:
        finished = False

        async def chat_stream(self, messages, max_tokens=None):
            del max_tokens
            prompt = messages[-1]["content"]
            assert prompt.index('"text_explanation"') < prompt.index('"core_definition"')
            yield '{"text_explanation":"第一段结构化回答'
            await release_model.wait()
            yield '，第二段说明。","core_definition":"这是核心定义。"}'
            self.finished = True

    llm = ControlledLlm()
    _install_stream_runtime(monkeypatch, llm)
    stream = tutor_service._stream_tutor_unlimited(
        "structured-stream-user",
        "course1",
        "请解释二叉树。",
        context_type="concept",
        stream_id=f"structured-live-{uuid4().hex}",
    )
    events = []
    first_event_arrived = asyncio.Event()

    async def consume():
        async for event in stream:
            events.append(event)
            first_event_arrived.set()

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(first_event_arrived.wait(), timeout=0.5)

    assert events[0]["event"] == "token"
    assert json.loads(events[0]["data"])["token"] == "第一段结构化回答"
    assert llm.finished is False

    release_model.set()
    await asyncio.wait_for(consumer, timeout=0.5)
    assert events[-1]["event"] == "done"
    assert llm.finished is True


@pytest.mark.asyncio
async def test_completed_stream_replays_after_last_event_id_without_second_llm_call(monkeypatch):
    class CountingLlm:
        calls = 0

        async def chat_stream(self, messages, max_tokens=None):
            del messages, max_tokens
            self.calls += 1
            yield "第一段回答"
            yield "，第二段说明。"

    llm = CountingLlm()
    _install_stream_runtime(monkeypatch, llm)
    stream_id = f"replay-{uuid4().hex}"

    first = [
        event
        async for event in tutor_service._stream_tutor_unlimited(
            "replay-user",
            "course1",
            "请解释二叉树。",
            stream_id=stream_id,
        )
    ]
    replay = [
        event
        async for event in tutor_service._stream_tutor_unlimited(
            "replay-user",
            "course1",
            "请解释二叉树。",
            stream_id=stream_id,
            last_event_id=first[0]["id"],
        )
    ]

    assert llm.calls == 1
    assert replay == first[1:]
    assert all(int(event["id"]) > int(first[0]["id"]) for event in replay)
    assert replay[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_disconnect_after_persist_replays_without_duplicate_history(monkeypatch):
    class CountingStructuredLlm:
        calls = 0

        async def chat_stream(self, messages, max_tokens=None):
            del messages, max_tokens
            self.calls += 1
            yield json.dumps(
                {"core_definition": "这是已经生成并完成校验的核心定义。"},
                ensure_ascii=False,
            )

    llm = CountingStructuredLlm()
    _install_stream_runtime(monkeypatch, llm)
    history_writes = []
    monkeypatch.setattr(
        "src.application.learning_assets_service.record_tutor_exchange_asset",
        lambda *args, **kwargs: history_writes.append((args, kwargs)),
    )
    stream_id = f"persisted-{uuid4().hex}"
    interrupted = tutor_service._stream_tutor_unlimited(
        "persisted-stream-user",
        "course1",
        "请解释二叉树。",
        context_type="concept",
        stream_id=stream_id,
    )

    first = await anext(interrupted)
    assert first["event"] == "token"
    assert llm.calls == 1
    assert len(history_writes) == 1
    await interrupted.aclose()

    replay = [
        event
        async for event in tutor_service._stream_tutor_unlimited(
            "persisted-stream-user",
            "course1",
            "请解释二叉树。",
            context_type="concept",
            stream_id=stream_id,
            last_event_id=first["id"],
        )
    ]

    assert replay[-1]["event"] == "done"
    assert all(event["event"] != "reset" for event in replay)
    assert llm.calls == 1
    assert len(history_writes) == 1


@pytest.mark.asyncio
async def test_unfinished_stream_restarts_with_reset_above_client_cursor(monkeypatch):
    class CountingLlm:
        calls = 0

        async def chat_stream(self, messages, max_tokens=None):
            del messages, max_tokens
            self.calls += 1
            yield "第一段回答"
            yield "，第二段说明。"

    llm = CountingLlm()
    _install_stream_runtime(monkeypatch, llm)
    stream_id = f"restart-{uuid4().hex}"
    interrupted = tutor_service._stream_tutor_unlimited(
        "restart-user",
        "course1",
        "请解释二叉树。",
        stream_id=stream_id,
    )
    first = await anext(interrupted)
    await interrupted.aclose()

    resumed = [
        event
        async for event in tutor_service._stream_tutor_unlimited(
            "restart-user",
            "course1",
            "请解释二叉树。",
            stream_id=stream_id,
            last_event_id=first["id"],
        )
    ]

    assert resumed[0]["event"] == "reset"
    assert int(resumed[0]["id"]) > int(first["id"])
    assert resumed[-1]["event"] == "done"
    assert llm.calls == 2


def test_superseded_generation_cannot_append_to_new_replay_epoch():
    stream_key = f"epoch-{uuid4().hex}"
    stale_epoch = tutor_service._begin_tutor_stream_replay(stream_key)
    current_epoch = tutor_service._begin_tutor_stream_replay(stream_key)

    stale_appended = tutor_service._append_tutor_stream_event(
        stream_key,
        {"id": "1", "event": "token", "data": "{}"},
        generation_epoch=stale_epoch,
    )
    current_appended = tutor_service._append_tutor_stream_event(
        stream_key,
        {"id": "1", "event": "done", "data": "{}"},
        generation_epoch=current_epoch,
        complete=True,
    )
    events, complete = tutor_service._read_tutor_stream_replay(stream_key, 0)

    assert stale_appended is False
    assert current_appended is True
    assert [(event["id"], event["event"]) for event in events] == [("1", "done")]
    assert complete is True


def test_replay_event_capacity_cannot_drop_requested_model_tokens(monkeypatch):
    monkeypatch.setenv("EDUAGENT_TUTOR_MAX_TOKENS", "7")
    monkeypatch.setenv("EDUAGENT_TUTOR_STREAM_REPLAY_MAX_EVENTS", "1")

    assert tutor_service._tutor_stream_replay_max_events() >= 7 + 64


@pytest.mark.asyncio
async def test_incremental_output_guard_blocks_unsafe_model_text(monkeypatch):
    class UnsafeLlm:
        async def chat_stream(self, messages, max_tokens=None):
            del messages, max_tokens
            yield "这是模型生成但未通过安全校验的原始回答。"

    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(runtime, "get_llm", lambda: UnsafeLlm())
    monkeypatch.setattr(
        tutor_service,
        "get_validation_pipeline",
        lambda: FakeValidationPipeline(pass_tutor=False),
    )

    events = [
        event
        async for event in tutor_service._stream_tutor_unlimited(
            "unsafe-stream-user",
            "course1",
            "请解释二叉树。",
            stream_id=f"unsafe-{uuid4().hex}",
        )
    ]
    visible_text = "".join(
        json.loads(event["data"]).get("token", "")
        for event in events
        if event["event"] == "token"
    )

    assert "模型生成但未通过安全校验" not in visible_text
    assert any(event["event"] == "validation_error" for event in events)
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_input_validation_error_has_terminal_event_id(monkeypatch):
    _install_stream_runtime(monkeypatch, object())

    def reject_input(*, text="", payload=None, field="input"):
        del payload
        result = ValidationResult(sanitized_text=text)
        result.add_issue("forced_input_reject", "forced reject", field=field)
        return result

    monkeypatch.setattr(tutor_service, "validate_service_input", reject_input)
    events = [
        event
        async for event in tutor_service._stream_tutor_unlimited(
            "blocked-user",
            "course1",
            "请解释二叉树。",
            stream_id=f"blocked-{uuid4().hex}",
        )
    ]

    assert [(event["id"], event["event"]) for event in events] == [("1", "error")]


@pytest.mark.asyncio
async def test_capacity_error_does_not_advance_replay_cursor(monkeypatch):
    class FullCapacity:
        def acquire(self, blocking=False):
            del blocking
            return False

    monkeypatch.setattr(tutor_service, "_TUTOR_STREAM_CAPACITY", FullCapacity())

    events = [
        event
        async for event in tutor_service.stream_tutor(
            "busy-user",
            "course1",
            "请解释二叉树。",
            stream_id="busy-stream",
            last_event_id="7",
        )
    ]

    assert [(event.get("id"), event["event"]) for event in events] == [(None, "error")]
    assert json.loads(events[0]["data"])["stream_id"] == "busy-stream"
