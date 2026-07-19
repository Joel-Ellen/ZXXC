from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from src.llm.client_v2 import LLMClientV2
from src.orchestration_runtime import OrchestrationRuntime


SPARK_ENDPOINT = "https://spark-api-open.xf-yun.com/agent/v1/chat/completions"


def _mock_async_client(monkeypatch, handler):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_spark_x2_flash_uses_apipassword_and_spark_x(monkeypatch):
    password = "test-api-password"
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "Success",
                "model": "spark-x",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "回答"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    monkeypatch.setenv("SPARK_API_PASSWORD", password)
    monkeypatch.delenv("SPARK_API_KEY", raising=False)
    monkeypatch.setenv("SPARK_API_URL", SPARK_ENDPOINT)
    monkeypatch.setenv("SPARK_MODEL", "spark-x")
    _mock_async_client(monkeypatch, handler)

    result = asyncio.run(
        LLMClientV2(provider="spark").chat(
            [{"role": "user", "content": "你好"}],
            temperature=0.4,
            max_tokens=32,
        )
    )

    assert result["content"] == "回答"
    assert captured["url"] == SPARK_ENDPOINT
    assert captured["authorization"] == f"Bearer {password}"
    assert captured["body"]["model"] == "spark-x"
    assert captured["body"]["messages"] == [{"role": "user", "content": "你好"}]
    assert captured["body"]["temperature"] == 0.4
    assert captured["body"]["max_tokens"] == 32


def test_spark_x2_flash_stream_yields_content_but_hides_reasoning(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        payload = "\n".join(
            [
                'data:{"code":0,"choices":[{"delta":{"reasoning_content":"hidden"}}]}',
                'data:{"code":0,"choices":[{"delta":{"content":"第"}}]}',
                'data:{"code":0,"choices":[{"delta":{"content":"一段"}}]}',
                "data:[DONE]",
                "",
            ]
        )
        return httpx.Response(
            200,
            content=payload.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setenv("SPARK_API_PASSWORD", "test-api-password")
    monkeypatch.setenv("SPARK_API_URL", SPARK_ENDPOINT)
    _mock_async_client(monkeypatch, handler)

    async def collect_tokens():
        return [
            token
            async for token in LLMClientV2(provider="spark").chat_stream(
                [{"role": "user", "content": "你好"}],
                max_tokens=32,
            )
        ]

    tokens = asyncio.run(collect_tokens())

    assert tokens == ["第", "一段"]
    assert captured["body"]["model"] == "spark-x"
    assert captured["body"]["stream"] is True


def test_spark_credentials_accept_apipassword_and_legacy_alias(monkeypatch):
    monkeypatch.delenv("SPARK_API_PASSWORD", raising=False)
    monkeypatch.setenv("SPARK_API_KEY", "legacy-api-password")
    assert OrchestrationRuntime._provider_has_credentials("spark") is True

    monkeypatch.setenv("SPARK_API_PASSWORD", "new-api-password")
    monkeypatch.delenv("SPARK_API_KEY", raising=False)
    assert OrchestrationRuntime._provider_has_credentials("spark") is True


def test_spark_api_error_is_not_treated_as_success():
    response = httpx.Response(200, json={"code": 10007, "message": "busy"})
    with pytest.raises(RuntimeError, match=r"Spark API 10007: busy"):
        LLMClientV2._parse_spark_response(response)
