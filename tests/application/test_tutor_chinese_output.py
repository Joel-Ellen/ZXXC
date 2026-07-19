import json
import asyncio

from src.agents.tutor_node import TutorAgentNode
from src.application import learning_assets_service, tutor_service
from src.validation.language import is_chinese_explanatory_text, is_chinese_mermaid_text
from tests.helpers import FakeValidationPipeline, disable_persistence, install_fake_runtime


class _TutorOutput:
    def __init__(self, state):
        self.agent_state = state


class _EnglishStreamingLlm:
    def __init__(self):
        self.max_tokens = None

    async def chat_stream(self, messages, max_tokens=None):
        self.max_tokens = max_tokens
        assert "必须使用简体中文" in messages[0]["content"]
        yield "This answer is entirely in English and must never be shown to the student."


def test_chinese_language_check_allows_code_but_rejects_english_prose():
    assert is_chinese_explanatory_text(
        "请先检查边界条件，再运行下面的代码：\n```python\nprint('hello')\n```"
    )
    assert not is_chinese_explanatory_text(
        "This answer explains the concept entirely in English."
    )
    assert not is_chinese_explanatory_text(
        "## Binary Tree\n\n二叉树是一种常见的数据结构，每个节点最多有两个子节点。"
    )
    assert is_chinese_explanatory_text(
        "请通过 HTTP API 获取数据，再检查返回值是否符合预期。"
    )
    assert is_chinese_mermaid_text(
        'graph TD\n    A["核心概念"] --> B["API"]\n    B --> C["调用流程"]'
    )
    assert not is_chinese_mermaid_text(
        'graph TD\n    A["Question"] --> B["Key concept"]'
    )


def test_offline_tutor_fallback_preserves_chinese_query():
    query = "二叉搜索树的插入操作如何实现？"

    response = TutorAgentNode()._generate_text_explanation(None, query, [])

    assert query in response
    assert is_chinese_explanatory_text(response)


def test_offline_tutor_fallback_does_not_echo_english_query():
    query = "Explain binary tree insertion."

    response = TutorAgentNode()._generate_text_explanation(None, query, [])

    assert query not in response
    assert is_chinese_explanatory_text(response)


def test_non_stream_tutor_replaces_english_model_output(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        tutor_service,
        "get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )

    def fake_tutor(inp):
        inp.agent_state.tutor_response = {
            "text_explanation": "This answer is entirely in English.",
            "mermaid_src": "",
        }
        return _TutorOutput(inp.agent_state)

    monkeypatch.setattr(fake, "tutor", fake_tutor)

    result = tutor_service.run_tutor("chinese-user", "course1", "Explain trees.")
    response = result["tutor_response"]

    assert response["language_fallback"] is True
    assert is_chinese_explanatory_text(response["text_explanation"])
    assert "entirely in English" not in response["text_explanation"]


def test_non_stream_tutor_replaces_english_mermaid_labels(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        tutor_service,
        "get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )

    def fake_tutor(inp):
        inp.agent_state.tutor_response = {
            "text_explanation": "这是模型返回的中文讲解。",
            "mermaid_src": 'graph TD\n    A["Question"] --> B["Key concept"]',
        }
        return _TutorOutput(inp.agent_state)

    monkeypatch.setattr(fake, "tutor", fake_tutor)

    result = tutor_service.run_tutor("mermaid-user", "course1", "Explain trees.")
    response = result["tutor_response"]

    assert response["text_explanation"] == "这是模型返回的中文讲解。"
    assert response["language_fallback"] is True
    assert is_chinese_mermaid_text(response["mermaid_src"])
    assert "Question" not in response["mermaid_src"]


def test_non_stream_tutor_removes_english_optional_fields(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        tutor_service,
        "get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )

    def fake_tutor(inp):
        inp.agent_state.tutor_response = {
            "text_explanation": "这是模型返回的中文讲解。",
            "analogy": "可以把它理解为按顺序处理任务。",
            "core_definition": "A tree is a hierarchical data structure.",
            "code_example": "THE FUNCTION RETURNS AN EMPTY LIST",
            "hints": ["Start from the root node.", "Then inspect each child node."],
            "follow_up_questions": ["How does traversal order affect the result?"],
            "mermaid_src": "",
        }
        return _TutorOutput(inp.agent_state)

    monkeypatch.setattr(fake, "tutor", fake_tutor)

    result = tutor_service.run_tutor("structured-user", "course1", "请解释树结构。")
    response = result["tutor_response"]

    assert response["text_explanation"] == "这是模型返回的中文讲解。"
    assert response["analogy"] == "可以把它理解为按顺序处理任务。"
    assert response["language_fallback"] is True
    assert "core_definition" not in response
    assert "code_example" not in response
    assert "hints" not in response
    assert "follow_up_questions" not in response


def test_learning_assets_hide_entire_exchange_with_english_assistant(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    state = fake.get_session("history-user", "course1").agent_state
    state.internal_state[learning_assets_service.LEARNING_ASSETS_KEY] = {
        "version": learning_assets_service.LEARNING_ASSETS_VERSION,
        "revision": 1,
        "categories": {
            "tutor_history": {
                "tutor:bad:user": {
                    "role": "user",
                    "content": "请解释二叉树。",
                    "exchange_id": "bad-exchange",
                    "sequence": 0,
                    "created_at": "2026-07-19T00:00:00+00:00",
                },
                "tutor:bad:assistant": {
                    "role": "assistant",
                    "content": "A binary tree stores values in a hierarchy.",
                    "exchange_id": "bad-exchange",
                    "sequence": 1,
                    "created_at": "2026-07-19T00:00:01+00:00",
                },
                "tutor:good:user": {
                    "role": "user",
                    "content": "请解释队列。",
                    "exchange_id": "good-exchange",
                    "sequence": 0,
                    "created_at": "2026-07-19T00:00:02+00:00",
                },
                "tutor:good:assistant": {
                    "role": "assistant",
                    "content": "队列按照先进先出的顺序处理元素。",
                    "exchange_id": "good-exchange",
                    "sequence": 1,
                    "created_at": "2026-07-19T00:00:03+00:00",
                },
            },
        },
    }

    result = learning_assets_service.get_learning_assets(
        "history-user",
        "course1",
        categories=["tutor_history"],
    )
    history = result["assets"]["tutor_history"]
    history_list = result["asset_lists"]["tutor_history"]

    assert set(history) == {"tutor:good:user", "tutor:good:assistant"}
    assert {entry["key"] for entry in history_list} == {
        "tutor:good:user",
        "tutor:good:assistant",
    }
    assert all(entry.get("exchange_id") != "bad-exchange" for entry in history_list)


def test_stream_tutor_never_emits_english_model_output(monkeypatch):
    fake = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        tutor_service,
        "get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )
    llm = _EnglishStreamingLlm()
    monkeypatch.setattr(fake, "get_llm", lambda: llm)

    async def collect_events():
        return [
            event
            async for event in tutor_service._stream_tutor_unlimited(
                "stream-chinese-user",
                "course1",
                "Explain trees.",
            )
        ]

    events = asyncio.run(collect_events())
    tokens = "".join(
        json.loads(event["data"])["token"]
        for event in events
        if event["event"] == "token"
    )

    assert is_chinese_explanatory_text(tokens)
    assert "entirely in English" not in tokens
    assert llm.max_tokens == tutor_service._tutor_max_tokens()
    assert events[-1]["event"] == "done"
