from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from src.application import code_practice_service as service
from src.state.agent_state import AgentState, ResourceCard
from src.validation.language import is_chinese_explanatory_text


_PROBLEM_FUNCTIONS = {
    "ds-list-sum": "sum_values",
    "ds-balanced-brackets": "is_balanced",
    "ds-tree-height": "tree_height",
    "ds-bfs-distances": "bfs_distances",
    "ds-max-non-adjacent": "max_non_adjacent",
}

_STARTER_COMMENTS = {
    "ds-list-sum": "# Return the sum of all values.",
    "ds-balanced-brackets": "# Use a stack to match opening and closing brackets.",
    "ds-tree-height": "# values uses level-order storage; None represents a missing node.",
    "ds-bfs-distances": "# Visit each node at most once.",
    "ds-max-non-adjacent": "# Use dynamic programming with constant extra space.",
}


def _state() -> AgentState:
    card = ResourceCard(
        resource_id="practice-r1",
        node_id="N01",
        card_type="code_snippet",
        content="代码练习",
        metadata={"practice": service.problem_binding_for_node("N01")},
    )
    return AgentState(
        user_id="u1",
        course_id="course1",
        current_node_id="N01",
        generated_resources={"N01": [card]},
    )


class _FakeExecutor:
    def __init__(self, *results: dict[str, object]) -> None:
        self.results = list(results)

    def execute(self, **_kwargs: object) -> dict[str, object]:
        return self.results.pop(0)


def _execute(executor: _FakeExecutor, *, mode: str = "run") -> dict[str, object]:
    return service.execute_practice(
        _state(),
        user_id="u1",
        course_id="course1",
        resource_id="practice-r1",
        problem_id="ds-list-sum",
        language="python",
        source_code="def sum_values(numbers):\n    return sum(numbers)\n",
        mode=mode,
        executor=executor,
    )


def _docker_execute(executor: service.DockerSandboxExecutor) -> dict[str, object]:
    return executor.execute(
        source_code="def sum_values(numbers): return sum(numbers)",
        function_name="sum_values",
        args=([1],),
        kwargs={},
        time_limit_ms=100,
        memory_limit_mb=32,
    )


def test_builtin_problem_copy_is_chinese_and_contract_is_stable() -> None:
    assert set(service._PROBLEMS) == set(_PROBLEM_FUNCTIONS)

    for problem_id, function_name in _PROBLEM_FUNCTIONS.items():
        problem = service._PROBLEMS[problem_id]
        payload = service.public_problem_payload(problem)

        assert problem.id == problem_id
        assert problem.version == 1
        assert problem.language == "python"
        assert problem.function_name == function_name
        assert problem.starter_code.startswith(f"def {function_name}(")
        assert _STARTER_COMMENTS[problem_id] in problem.starter_code
        assert all(
            is_chinese_explanatory_text(payload[field])
            for field in ("title", "prompt", "constraints")
        )
        assert "reference_solution" not in payload
        assert "hidden_tests" not in payload


def test_missing_problem_message_is_chinese() -> None:
    result = service.get_practice_problem(
        AgentState(user_id="u1", course_id="course1"),
        "missing-resource",
    )

    assert result["status"] == "practice_problem_not_bound_to_session"
    assert result["reason"] == "practice_problem_not_bound_to_session"
    assert is_chinese_explanatory_text(result["message"])


def test_server_owned_execution_messages_are_chinese() -> None:
    accepted = _execute(
        _FakeExecutor(
            {"status": "ok", "actual": 6},
            {"status": "ok", "actual": 0},
        )
    )
    assert accepted["status"] == "ok"
    assert accepted["verdict"] == "accepted"
    assert accepted["message"] == "所选测试全部通过。"

    wrong_answer = _execute(_FakeExecutor({"status": "ok", "actual": 999}))
    assert wrong_answer["status"] == "ok"
    assert wrong_answer["verdict"] == "wrong_answer"
    assert wrong_answer["message"] == "公开测试未通过。"

    sandbox = _execute(_FakeExecutor({"status": "sandbox_unavailable"}))
    assert sandbox["status"] == "sandbox_unavailable"
    assert sandbox["message"] == "隔离执行环境不可用。"


def test_public_worker_diagnostic_is_returned_verbatim() -> None:
    diagnostic = "solution.py:1: invalid syntax"

    result = _execute(
        _FakeExecutor(
            {
                "status": "syntax_error",
                "message": diagnostic,
                "runtime_ms": 1.0,
                "memory_kb": 128,
            }
        )
    )

    assert result["verdict"] == "syntax_error"
    assert result["message"] == diagnostic
    assert result["tests"][0]["message"] == diagnostic
    assert 'raise RuntimeError("Unable to load solution module")' in service._WORKER_SOURCE
    assert "Required function '%s' was not found" in service._WORKER_SOURCE


def test_hidden_worker_diagnostic_is_redacted_and_message_is_chinese() -> None:
    result = _execute(
        _FakeExecutor(
            {"status": "ok", "actual": 6},
            {"status": "ok", "actual": 0},
            {
                "status": "runtime_error",
                "message": "RuntimeError: hidden secret",
                "runtime_ms": 1.0,
            },
        ),
        mode="submit",
    )

    hidden = result["tests"][-1]
    assert result["verdict"] == "runtime_error"
    assert result["message"] == "隐藏测试未通过。"
    assert hidden["visibility"] == "hidden"
    assert hidden["message"] == "隐藏测试未通过。"
    assert not {"input", "expected", "actual"}.intersection(hidden)
    assert "hidden secret" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"mode": "preview"}, "practice_mode_invalid"),
        ({"resource_id": ""}, "practice_resource_id_required"),
        ({"language": "javascript"}, "practice_language_unsupported"),
        ({"source_code": ""}, "practice_code_required"),
        ({"source_code": "x" * (service.MAX_SOURCE_BYTES + 1)}, "practice_code_too_large"),
    ],
)
def test_invalid_request_codes_remain_stable(
    overrides: dict[str, object],
    reason: str,
) -> None:
    arguments: dict[str, object] = {
        "user_id": "u1",
        "course_id": "course1",
        "resource_id": "practice-r1",
        "problem_id": "ds-list-sum",
        "language": "python",
        "source_code": "def sum_values(numbers): return sum(numbers)",
        "mode": "run",
    }
    arguments.update(overrides)

    result = service.execute_practice(_state(), **arguments)

    assert result == {"status": "invalid_request", "reason": reason}


def test_unavailable_docker_runtime_message_is_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = service.DockerSandboxExecutor(docker_binary="docker")
    monkeypatch.setattr(executor, "available", lambda: False)

    result = _docker_execute(executor)

    assert result["status"] == "sandbox_unavailable"
    assert is_chinese_explanatory_text(result["message"])


@pytest.mark.parametrize(
    ("completed", "expected_message"),
    [
        (
            SimpleNamespace(returncode=125, stdout="", stderr="daemon unavailable"),
            "隔离执行环境启动失败。",
        ),
        (
            SimpleNamespace(returncode=1, stdout="", stderr="runner stopped"),
            "隔离执行器未返回结构化结果。",
        ),
        (
            SimpleNamespace(returncode=0, stdout="not-json", stderr=""),
            "隔离执行器返回了无效结果。",
        ),
        (
            SimpleNamespace(returncode=0, stdout="[]", stderr=""),
            "隔离执行器返回了无效结果。",
        ),
    ],
)
def test_docker_runner_failure_messages_are_chinese(
    monkeypatch: pytest.MonkeyPatch,
    completed: SimpleNamespace,
    expected_message: str,
) -> None:
    executor = service.DockerSandboxExecutor(docker_binary="docker")
    monkeypatch.setattr(executor, "available", lambda: True)
    monkeypatch.setattr(service.subprocess, "run", lambda *_args, **_kwargs: completed)

    result = _docker_execute(executor)

    assert result["message"] == expected_message
    assert is_chinese_explanatory_text(result["message"])


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_verdict"),
    [
        (subprocess.TimeoutExpired(cmd="docker", timeout=1), "ok", "time_limit"),
        (OSError("cannot start"), "sandbox_unavailable", None),
    ],
)
def test_docker_exception_messages_are_chinese(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    expected_status: str,
    expected_verdict: str | None,
) -> None:
    executor = service.DockerSandboxExecutor(docker_binary="docker")
    monkeypatch.setattr(executor, "available", lambda: True)

    def raise_error(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(service.subprocess, "run", raise_error)

    result = _docker_execute(executor)

    assert result["status"] == expected_status
    assert result.get("verdict") == expected_verdict
    assert any("\u4e00" <= char <= "\u9fff" for char in result["message"])
    if isinstance(error, OSError):
        assert type(error).__name__ in result["message"]
