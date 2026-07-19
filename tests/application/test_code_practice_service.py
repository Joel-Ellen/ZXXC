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
    "ds-list-sum": "/* Return the sum of all values. */",
    "ds-balanced-brackets": "/* Use a stack to match opening and closing brackets. */",
    "ds-tree-height": "/* Level-order storage uses present[i] == 0 for a missing node. */",
    "ds-bfs-distances": "/* Visit every vertex at most once. */",
    "ds-max-non-adjacent": "/* Use dynamic programming with constant extra space. */",
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


class _FakeRunnerClient:
    available = True

    def __init__(self, result: object = None) -> None:
        self.result = result if result is not None else {"status": "ok", "actual": 1}
        self.calls: list[dict[str, object]] = []

    def execute_c_case(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _execute(executor: _FakeExecutor, *, mode: str = "run") -> dict[str, object]:
    return service.execute_practice(
        _state(),
        user_id="u1",
        course_id="course1",
        resource_id="practice-r1",
        problem_id="ds-list-sum",
        language="c",
        source_code=(
            "#include <stddef.h>\n"
            "int sum_values(const int *numbers, size_t count) {\n"
            "    int total = 0;\n"
            "    for (size_t i = 0; i < count; ++i) total += numbers[i];\n"
            "    return total;\n"
            "}\n"
        ),
        mode=mode,
        executor=executor,
    )


def _docker_execute(executor: service.DockerSandboxExecutor) -> dict[str, object]:
    return executor.execute(
        source_code=(
            "#include <stddef.h>\n"
            "int sum_values(const int *numbers, size_t count) { return (int)count; }\n"
        ),
        function_name="sum_values",
        args=([1],),
        kwargs={},
        time_limit_ms=100,
        memory_limit_mb=32,
    )


def _remote_execute(executor: service.RemoteSandboxExecutor) -> dict[str, object]:
    return executor.execute(
        source_code=(
            "#include <stddef.h>\n"
            "int sum_values(const int *numbers, size_t count) { return (int)count; }\n"
        ),
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
        assert problem.version == service.PRACTICE_CONTRACT_VERSION == 2
        assert problem.language == "c"
        assert problem.function_name == function_name
        assert f"int {function_name}(" in problem.starter_code or f"void {function_name}(" in problem.starter_code
        assert _STARTER_COMMENTS[problem_id] in problem.starter_code
        assert all(
            is_chinese_explanatory_text(payload[field])
            for field in ("title", "prompt", "constraints")
        )
        assert "reference_solution" not in payload
        assert "hidden_tests" not in payload

    tree_solution = service._PROBLEMS["ds-tree-height"].reference_solution
    assert "last /= 2" in tree_solution


def test_c_string_literals_use_fixed_width_escapes_for_utf8() -> None:
    literal = service._c_string_literal("中a")

    assert literal == '"\\344\\270\\255a"'
    assert "\\x" not in literal


def test_public_tests_describe_the_c_call_contract() -> None:
    sequence_sum = service.public_problem_payload(service._PROBLEMS["ds-list-sum"])
    bfs = service.public_problem_payload(service._PROBLEMS["ds-bfs-distances"])
    tree = service.public_problem_payload(service._PROBLEMS["ds-tree-height"])

    assert set(sequence_sum["public_tests"][0]["input"]) == {"numbers", "count"}
    bfs_input = bfs["public_tests"][0]["input"]
    assert set(bfs_input) == {"adjacency", "vertex_count", "start", "labels"}
    assert isinstance(bfs_input["start"], int)
    assert isinstance(bfs["public_tests"][0]["expected"], list)

    tree_input = tree["public_tests"][0]["input"]
    assert set(tree_input) == {"values", "present", "count"}
    assert len(tree_input["values"]) == tree_input["count"]


def test_legacy_python_binding_is_migrated_to_the_current_c_contract() -> None:
    state = _state()
    card = state.generated_resources["N01"][0]
    card.metadata = {
        "practice": {
            "problem_id": "ds-list-sum",
            "version": 1,
            "language": "python",
            "starter_code": "def sum_values(numbers):\n    pass\n",
        },
        "practice_problem_id": "ds-list-sum",
        "practice_version": 1,
        "starter_code": "def sum_values(numbers):\n    pass\n",
    }

    response = service.get_practice_problem(state, "practice-r1")

    assert response["status"] == "ok"
    assert response["problem"]["version"] == service.PRACTICE_CONTRACT_VERSION
    assert response["problem"]["language"] == "c"
    assert card.metadata["practice"] == service.problem_binding_for_node("N01")
    assert card.metadata["practice_version"] == service.PRACTICE_CONTRACT_VERSION
    assert card.metadata["starter_code"].startswith("#include <stddef.h>")


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


def test_internal_worker_error_is_not_reported_as_wrong_answer() -> None:
    result = _execute(_FakeExecutor({
        "status": "ok",
        "verdict": "internal_error",
        "message": "隔离执行器内部错误。",
    }))

    assert result["status"] == "ok"
    assert result["verdict"] == "internal_error"
    assert result["tests"][0]["passed"] is False
    assert result["tests"][0]["verdict"] == "internal_error"


def test_public_worker_diagnostic_is_returned_verbatim() -> None:
    diagnostic = "solution.c:1: expected ';'"

    result = _execute(
        _FakeExecutor(
            {
                "status": "syntax_error",
                "message": "代码编译失败，请检查 C11 语法。",
                "compiler_diagnostic": diagnostic,
                "runtime_ms": 1.0,
                "memory_kb": 128,
            }
        )
    )

    assert result["verdict"] == "syntax_error"
    assert result["message"].startswith("代码编译失败，请检查 C11 语法。")
    assert diagnostic in result["message"]
    assert diagnostic in result["tests"][0]["message"]
    assert "C11" in service._WORKER_SOURCE


def test_compiler_diagnostic_is_preserved_when_the_base_message_is_long() -> None:
    diagnostic = "solution.c:9:3: error: expected ';'"

    message = service._worker_message({
        "message": "编译失败。" * 100,
        "compiler_diagnostic": diagnostic,
    })

    assert len(message) <= 500
    assert diagnostic in message


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
        "language": "c",
        "source_code": (
            "#include <stddef.h>\n"
            "int sum_values(const int *numbers, size_t count) { return (int)count; }\n"
        ),
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


def test_remote_runner_receives_a_server_owned_c_harness() -> None:
    client = _FakeRunnerClient()

    result = _remote_execute(service.RemoteSandboxExecutor(client=client))

    assert result == {"status": "ok", "actual": 1}
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["source_code"].startswith("#include <stddef.h>")
    harness = request["harness_source"]
    assert '#include "solution.c"' not in harness
    assert "int sum_values(const int *numbers, size_t count);" in harness
    assert "int main(void)" in harness
    assert request["output_limit_bytes"] == service.MAX_SANDBOX_OUTPUT_BYTES


@pytest.mark.parametrize(
    "worker_result",
    [
        {"status": "ok"},
        {"status": "unexpected", "actual": 1},
        {"status": "ok", "verdict": "unexpected", "actual": 1},
    ],
)
def test_remote_runner_rejects_invalid_result_contract(
    worker_result: dict[str, object],
) -> None:
    result = _remote_execute(service.RemoteSandboxExecutor(
        client=_FakeRunnerClient(worker_result),
    ))

    assert result["status"] == "ok"
    assert result["verdict"] == "internal_error"
    assert "actual" not in result


def test_remote_runner_failure_is_reported_without_local_execution() -> None:
    client = _FakeRunnerClient(service.ServiceUnavailable("offline"))

    result = _remote_execute(service.RemoteSandboxExecutor(client=client))

    assert result["status"] == "sandbox_unavailable"
    assert is_chinese_explanatory_text(result["message"])


def test_configured_remote_runner_is_preferred_over_local_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_RUNNER_URL", "http://sandbox-runner:8080")

    assert isinstance(service._default_sandbox_executor(), service.RemoteSandboxExecutor)


def test_remote_runner_http_contract_is_c11_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = service.SandboxRunnerClient()
    captured: dict[str, object] = {}

    def fake_post(path: str, payload: object, **kwargs: object) -> dict[str, object]:
        captured.update({"path": path, "payload": payload, **kwargs})
        return {"status": "ok", "actual": 1}

    monkeypatch.setattr(client, "post", fake_post)

    result = client.execute_c_case(
        source_code="int answer(void) { return 1; }",
        harness_source="int main(void) { return answer() != 1; }",
        time_limit_ms=1_500,
        memory_limit_mb=128,
        output_limit_bytes=65_536,
    )

    assert result["actual"] == 1
    assert captured["path"] == "/v1/execute"
    payload = captured["payload"]
    assert payload["protocol_version"] == "eduagent-c11-practice-v1"
    assert payload["language"] == "c"
    assert payload["compile_mode"] == "separate_translation_units"
    assert payload["limits"] == {
        "cpu": 1,
        "memory_mb": 128,
        "timeout_ms": 1_500,
        "output_bytes": 65_536,
        "network": "none",
        "root_filesystem": "read_only",
        "run_as_non_root": True,
    }


def test_c_sandbox_keeps_isolation_and_executes_only_bounded_tmpfs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    executor = service.DockerSandboxExecutor(
        docker_binary="docker",
        image="gcc:13",
    )
    monkeypatch.setattr(executor, "available", lambda: True)

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout='{"status":"ok","actual":1}\n',
            stderr="",
        )

    monkeypatch.setattr(service.subprocess, "run", fake_run)

    result = _docker_execute(executor)
    command = captured["command"]

    assert result["actual"] == 1
    assert isinstance(command, list)
    assert ["--network", "none"] == command[
        command.index("--network") : command.index("--network") + 2
    ]
    assert "--read-only" in command
    assert ["--cap-drop", "ALL"] == command[
        command.index("--cap-drop") : command.index("--cap-drop") + 2
    ]
    assert "/tmp:rw,exec,nosuid,size=16m" in command
    assert "--name" in command
    assert "/workspace/solution.c -c -o /tmp/solution.o" in command[-1]
    assert "/workspace/runner.c /tmp/solution.o" in command[-1]
    assert "exit 100" in command[-1]
    assert f"head -c {service.MAX_SANDBOX_OUTPUT_BYTES}" in command[-1]
    assert "/tmp/eduagent-runner >/tmp/program.out" in command[-1]


def test_docker_timeout_forcibly_removes_the_named_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = service.DockerSandboxExecutor(docker_binary="docker")
    monkeypatch.setattr(executor, "available", lambda: True)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[1] == "run":
            raise subprocess.TimeoutExpired(cmd=command, timeout=1)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(service.subprocess, "run", fake_run)

    result = _docker_execute(executor)

    assert result["verdict"] == "time_limit"
    container_name = commands[0][commands[0].index("--name") + 1]
    assert commands[1] == ["docker", "rm", "--force", container_name]


@pytest.mark.parametrize(
    ("completed", "expected_message"),
    [
        (
            SimpleNamespace(returncode=125, stdout="", stderr="daemon unavailable"),
            "隔离执行环境启动失败。",
        ),
        (
            SimpleNamespace(returncode=100, stdout="", stderr="solution.c:1: error"),
            "代码编译失败，请检查 C11 语法。",
        ),
        (
            SimpleNamespace(returncode=139, stdout="", stderr="segmentation fault"),
            "代码运行时异常终止。",
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
