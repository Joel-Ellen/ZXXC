# -*- coding: utf-8 -*-
"""Server-owned coding-practice definitions and isolated execution.

Learner source is never evaluated by the application process.  Each test case
starts a fresh Docker container with no network, a read-only filesystem, an
unprivileged user, and explicit CPU/memory/process/time limits.  The host owns
the answer key and invokes the container once per test, so hidden expectations
are not readable from inside the learner container.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from src.state.agent_state import AgentState, ResourceCard


SUPPORTED_LANGUAGE = "python"
DEFAULT_SANDBOX_IMAGE = "python:3.11-alpine"
DEFAULT_TIME_LIMIT_MS = 1_500
DEFAULT_MEMORY_LIMIT_MB = 128
MAX_SOURCE_BYTES = 64 * 1024
MAX_TESTS_PER_EXECUTION = 16
MAX_RECEIPTS_PER_SESSION = 500


@dataclass(frozen=True)
class PracticeTest:
    """One server-only test case.  ``visibility`` controls response redaction."""

    id: str
    args: tuple[Any, ...]
    expected: Any
    visibility: str = "public"
    kwargs: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class PracticeProblem:
    """A versioned problem, including the answer key retained on the server."""

    id: str
    version: int
    title: str
    prompt: str
    constraints: str
    function_name: str
    starter_code: str
    reference_solution: str
    public_tests: tuple[PracticeTest, ...]
    hidden_tests: tuple[PracticeTest, ...]
    language: str = SUPPORTED_LANGUAGE
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB


def _tests(*items: PracticeTest) -> tuple[PracticeTest, ...]:
    return tuple(items)


# These are deliberately ordinary Python functions with JSON-compatible input
# and output.  That keeps the container protocol narrow and makes every test
# independently executable without exposing hidden expected values.
_PROBLEMS: Dict[str, PracticeProblem] = {
    "ds-list-sum": PracticeProblem(
        id="ds-list-sum",
        version=1,
        title="序列求和",
        prompt="请实现 `sum_values(numbers)`，返回列表中所有整数之和。",
        constraints="返回整数；输入为空时必须返回 0。",
        function_name="sum_values",
        starter_code="def sum_values(numbers: list[int]) -> int:\n    # Return the sum of all values.\n    pass\n",
        reference_solution="def sum_values(numbers):\n    return sum(numbers)\n",
        public_tests=_tests(
            PracticeTest("public-1", ([1, 2, 3],), 6),
            PracticeTest("public-2", ([],), 0),
        ),
        hidden_tests=_tests(
            PracticeTest("hidden-1", ([-4, 9, 0, 5],), 10, "hidden"),
            PracticeTest("hidden-2", ([100000, -1, -99999],), 0, "hidden"),
        ),
    ),
    "ds-balanced-brackets": PracticeProblem(
        id="ds-balanced-brackets",
        version=1,
        title="平衡括号",
        prompt="请实现 `is_balanced(text)`，判断 ()、[] 和 {} 是否正确嵌套。",
        constraints="忽略括号以外的字符，并返回布尔值。",
        function_name="is_balanced",
        starter_code=(
            "def is_balanced(text: str) -> bool:\n"
            "    # Use a stack to match opening and closing brackets.\n"
            "    pass\n"
        ),
        reference_solution=(
            "def is_balanced(text):\n"
            "    pairs = {')': '(', ']': '[', '}': '{'}\n"
            "    stack = []\n"
            "    for char in text:\n"
            "        if char in '([{':\n"
            "            stack.append(char)\n"
            "        elif char in pairs:\n"
            "            if not stack or stack.pop() != pairs[char]:\n"
            "                return False\n"
            "    return not stack\n"
        ),
        public_tests=_tests(
            PracticeTest("public-1", ("([]){}",), True),
            PracticeTest("public-2", ("([)]",), False),
        ),
        hidden_tests=_tests(
            PracticeTest("hidden-1", ("function(a[0] + {b: 1})",), True, "hidden"),
            PracticeTest("hidden-2", ("((",), False, "hidden"),
        ),
    ),
    "ds-tree-height": PracticeProblem(
        id="ds-tree-height",
        version=1,
        title="二叉树的高度",
        prompt=(
            "请实现 `tree_height(values)`，其中二叉树使用层序列表表示，"
            "`None` 表示缺失节点；空树返回 0。"
        ),
        constraints="返回至少包含一个节点的层数。",
        function_name="tree_height",
        starter_code=(
            "def tree_height(values: list[object]) -> int:\n"
            "    # values uses level-order storage; None represents a missing node.\n"
            "    pass\n"
        ),
        reference_solution=(
            "def tree_height(values):\n"
            "    if not values or values[0] is None:\n"
            "        return 0\n"
            "    last = len(values) - 1\n"
            "    while last >= 0 and values[last] is None:\n"
            "        last -= 1\n"
            "    height = 0\n"
            "    while last >= 0:\n"
            "        height += 1\n"
            "        last = (last - 1) // 2\n"
            "    return height\n"
        ),
        public_tests=_tests(
            PracticeTest("public-1", ([1, 2, 3, 4, 5, None, 6],), 3),
            PracticeTest("public-2", ([],), 0),
        ),
        hidden_tests=_tests(
            PracticeTest("hidden-1", ([1],), 1, "hidden"),
            PracticeTest("hidden-2", ([1, 2, None, 3, None, None, None, 4],), 4, "hidden"),
        ),
    ),
    "ds-bfs-distances": PracticeProblem(
        id="ds-bfs-distances",
        version=1,
        title="广度优先搜索距离",
        prompt=(
            "请实现 `bfs_distances(graph, start)`。`graph` 将节点标签映射到相邻节点标签列表；"
            "返回从 `start` 出发可到达的每个节点到起点的最短边数。"
        ),
        constraints="缺失的邻接列表按空列表处理；返回可由 JSON 表示的键和整数值。",
        function_name="bfs_distances",
        starter_code=(
            "def bfs_distances(graph: dict[str, list[str]], start: str) -> dict[str, int]:\n"
            "    # Visit each node at most once.\n"
            "    pass\n"
        ),
        reference_solution=(
            "def bfs_distances(graph, start):\n"
            "    result = {start: 0}\n"
            "    queue = [start]\n"
            "    index = 0\n"
            "    while index < len(queue):\n"
            "        node = queue[index]\n"
            "        index += 1\n"
            "        for neighbor in graph.get(node, []):\n"
            "            if neighbor not in result:\n"
            "                result[neighbor] = result[node] + 1\n"
            "                queue.append(neighbor)\n"
            "    return result\n"
        ),
        public_tests=_tests(
            PracticeTest(
                "public-1",
                ({"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}, "A"),
                {"A": 0, "B": 1, "C": 1, "D": 2},
            ),
            PracticeTest("public-2", ({"A": []}, "A"), {"A": 0}),
        ),
        hidden_tests=_tests(
            PracticeTest(
                "hidden-1",
                ({"A": ["B"], "B": ["C"], "C": ["A", "D"], "D": []}, "A"),
                {"A": 0, "B": 1, "C": 2, "D": 3},
                "hidden",
            ),
        ),
    ),
    "ds-max-non-adjacent": PracticeProblem(
        id="ds-max-non-adjacent",
        version=1,
        title="最大非相邻元素和",
        prompt=(
            "请实现 `max_non_adjacent(values)`，返回不同时选取两个相邻元素时可得到的最大和；"
            "可以不选择任何元素。"
        ),
        constraints="当所有元素均为负数或列表为空时返回 0。",
        function_name="max_non_adjacent",
        starter_code=(
            "def max_non_adjacent(values: list[int]) -> int:\n"
            "    # Use dynamic programming with constant extra space.\n"
            "    pass\n"
        ),
        reference_solution=(
            "def max_non_adjacent(values):\n"
            "    previous_two = 0\n"
            "    previous_one = 0\n"
            "    for value in values:\n"
            "        previous_two, previous_one = previous_one, max(previous_one, previous_two + value)\n"
            "    return previous_one\n"
        ),
        public_tests=_tests(
            PracticeTest("public-1", ([3, 2, 5, 10, 7],), 15),
            PracticeTest("public-2", ([],), 0),
        ),
        hidden_tests=_tests(
            PracticeTest("hidden-1", ([-3, -1, -5],), 0, "hidden"),
            PracticeTest("hidden-2", ([2, 1, 4, 9],), 11, "hidden"),
        ),
    ),
}


_NODE_PROBLEM_IDS = {
    "N01": "ds-list-sum",
    "N02": "ds-list-sum",
    "N03": "ds-balanced-brackets",
    "N04": "ds-balanced-brackets",
    "N05": "ds-balanced-brackets",
    "N06": "ds-tree-height",
    "N07": "ds-tree-height",
    "N08": "ds-tree-height",
    "N09": "ds-bfs-distances",
    "N10": "ds-bfs-distances",
    "N11": "ds-bfs-distances",
    "N12": "ds-bfs-distances",
    "N13": "ds-bfs-distances",
    "N14": "ds-bfs-distances",
    "N15": "ds-list-sum",
    "N16": "ds-list-sum",
    "N17": "ds-list-sum",
    "N18": "ds-max-non-adjacent",
    "N19": "ds-max-non-adjacent",
    "N20": "ds-max-non-adjacent",
}


def problem_binding_for_node(node_id: str) -> Dict[str, Any]:
    """Return only learner-safe binding metadata for a generated resource."""
    problem_id = _NODE_PROBLEM_IDS.get(str(node_id or "").strip(), "ds-list-sum")
    problem = _PROBLEMS[problem_id]
    return {
        "problem_id": problem.id,
        "version": problem.version,
        "language": problem.language,
        "starter_code": problem.starter_code,
    }


def problem_context_for_node(node_id: str) -> Dict[str, Any]:
    """Return generator-safe executable practice context without answer keys.

    Resource prompts need the actual task and starter code to avoid generic
    examples, but reference solutions and hidden tests must remain server-only.
    """
    problem_id = _NODE_PROBLEM_IDS.get(str(node_id or "").strip(), "ds-list-sum")
    problem = _PROBLEMS[problem_id]
    return {
        **problem_binding_for_node(node_id),
        "title": problem.title,
        "prompt": problem.prompt,
        "constraints": problem.constraints,
        "function_name": problem.function_name,
        "public_tests": [_public_test_payload(test) for test in problem.public_tests],
    }


def _as_resource_id(value: object) -> str:
    return str(value or "").strip()


def _card_metadata(card: ResourceCard) -> Dict[str, Any]:
    metadata = getattr(card, "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _practice_binding(card: ResourceCard) -> Dict[str, Any]:
    metadata = _card_metadata(card)
    nested = metadata.get("practice")
    binding = dict(nested) if isinstance(nested, dict) else {}
    if not binding:
        flat_id = metadata.get("practice_problem_id") or metadata.get("problem_id")
        if flat_id:
            binding["problem_id"] = flat_id
        if metadata.get("practice_version") is not None:
            binding["version"] = metadata.get("practice_version")
    return binding


def _ensure_code_card_binding(card: ResourceCard) -> Dict[str, Any]:
    """Backfill a server-owned binding for legacy code cards on first use."""
    binding = _practice_binding(card)
    if binding.get("problem_id"):
        return binding
    if getattr(card, "card_type", "") != "code_snippet":
        return {}
    binding = problem_binding_for_node(getattr(card, "node_id", ""))
    metadata = _card_metadata(card)
    metadata["practice"] = binding
    metadata["practice_problem_id"] = binding["problem_id"]
    metadata["practice_version"] = binding["version"]
    card.metadata = metadata
    return binding


def _find_card(state: AgentState, resource_id: str) -> Optional[ResourceCard]:
    for cards in state.generated_resources.values():
        for card in cards:
            if _as_resource_id(getattr(card, "resource_id", "")) == resource_id:
                return card
    return None


def _find_card_for_problem(state: AgentState, problem_id: str) -> Optional[ResourceCard]:
    for cards in state.generated_resources.values():
        for card in cards:
            binding = _ensure_code_card_binding(card)
            if binding.get("problem_id") == problem_id:
                return card
    return None


def _resolve_problem(
    state: AgentState,
    *,
    resource_id: str = "",
    problem_id: str = "",
) -> tuple[Optional[PracticeProblem], Optional[ResourceCard], Dict[str, Any]]:
    """Resolve only a problem explicitly bound to this session's resource."""
    card: Optional[ResourceCard] = None
    resource_id = _as_resource_id(resource_id)
    problem_id = _as_resource_id(problem_id)
    if resource_id:
        card = _find_card(state, resource_id)
        if card is None:
            return None, None, {"reason": "practice_resource_not_found", "resource_id": resource_id}
    elif problem_id:
        card = _find_card_for_problem(state, problem_id)
        if card is None:
            return None, None, {"reason": "practice_problem_not_bound_to_session", "problem_id": problem_id}
    else:
        return None, None, {"reason": "practice_resource_id_required"}

    binding = _ensure_code_card_binding(card)
    bound_problem_id = _as_resource_id(binding.get("problem_id"))
    if not bound_problem_id:
        return None, card, {
            "reason": "practice_problem_not_configured",
            "resource_id": _as_resource_id(getattr(card, "resource_id", "")),
        }
    if problem_id and problem_id != bound_problem_id:
        return None, card, {
            "reason": "practice_problem_resource_mismatch",
            "resource_id": _as_resource_id(getattr(card, "resource_id", "")),
        }
    problem = _PROBLEMS.get(bound_problem_id)
    if problem is None:
        return None, card, {"reason": "practice_problem_not_found", "problem_id": bound_problem_id}
    requested_version = binding.get("version")
    if requested_version is not None:
        try:
            if int(requested_version) != problem.version:
                return None, card, {
                    "reason": "practice_problem_version_unavailable",
                    "problem_id": bound_problem_id,
                    "version": requested_version,
                }
        except (TypeError, ValueError):
            return None, card, {"reason": "practice_problem_version_invalid", "problem_id": bound_problem_id}
    return problem, card, {}


def _public_test_payload(test: PracticeTest) -> Dict[str, Any]:
    return {
        "id": test.id,
        "input": list(test.args) if len(test.args) != 1 else test.args[0],
        "expected": test.expected,
    }


def public_problem_payload(problem: PracticeProblem) -> Dict[str, Any]:
    """Build the only problem representation allowed to leave the server."""
    return {
        "status": "ok",
        "id": problem.id,
        "problem_id": problem.id,
        "version": problem.version,
        "title": problem.title,
        "prompt": problem.prompt,
        "constraints": problem.constraints,
        "language": problem.language,
        "function_name": problem.function_name,
        "starter_code": problem.starter_code,
        "public_tests": [_public_test_payload(test) for test in problem.public_tests],
        "public_test_count": len(problem.public_tests),
        "hidden_test_count": len(problem.hidden_tests),
        "time_limit_ms": problem.time_limit_ms,
        "memory_limit_mb": problem.memory_limit_mb,
    }


def get_practice_problem(
    state: AgentState,
    problem_or_resource_id: str,
) -> Dict[str, Any]:
    """Return a learner-safe specification for a card in the current session."""
    key = _as_resource_id(problem_or_resource_id)
    problem, card, error = _resolve_problem(state, resource_id=key)
    if problem is None and error.get("reason") == "practice_resource_not_found":
        problem, card, error = _resolve_problem(state, problem_id=key)
    if problem is None:
        return {
            "status": error.get("reason", "practice_problem_not_configured"),
            "message": "该资源尚未配置可执行的编程练习。",
            **error,
        }
    return {
        "status": "ok",
        "resource_id": _as_resource_id(getattr(card, "resource_id", "")),
        "node_id": _as_resource_id(getattr(card, "node_id", "")),
        "problem": public_problem_payload(problem),
    }


_WORKER_SOURCE = r'''import importlib.util
import json
import os
import resource
import sys
import time
import traceback


def json_safe(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def emit(payload):
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), flush=True)


started = time.perf_counter()
try:
    request = json.loads(sys.stdin.read() or "{}")
    function_name = request.get("function_name", "")
    spec = importlib.util.spec_from_file_location("student_solution", "/workspace/solution.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load solution module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, function_name, None)
    if not callable(function):
        raise AttributeError("Required function '%s' was not found" % function_name)
    actual = function(*request.get("args", []), **request.get("kwargs", {}))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    memory_kb = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss or 0)
    emit({"status": "ok", "actual": json_safe(actual), "runtime_ms": elapsed_ms, "memory_kb": memory_kb})
except SyntaxError as error:
    emit({"status": "syntax_error", "message": "%s:%s: %s" % (error.filename or "solution.py", error.lineno or 0, error.msg), "runtime_ms": round((time.perf_counter() - started) * 1000, 3), "memory_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss or 0)})
except BaseException as error:
    emit({"status": "runtime_error", "message": "%s: %s" % (type(error).__name__, str(error)[:500]), "runtime_ms": round((time.perf_counter() - started) * 1000, 3), "memory_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss or 0)})
'''


class DockerSandboxExecutor:
    """Run a single call in a fresh, intentionally constrained Docker container."""

    def __init__(
        self,
        *,
        docker_binary: Optional[str] = None,
        image: Optional[str] = None,
    ) -> None:
        self.docker_binary = docker_binary or os.environ.get("CODE_SANDBOX_DOCKER", "docker")
        self.image = image or os.environ.get("CODE_SANDBOX_IMAGE", DEFAULT_SANDBOX_IMAGE)

    def available(self) -> bool:
        return bool(shutil.which(self.docker_binary))

    def execute(
        self,
        *,
        source_code: str,
        function_name: str,
        args: Iterable[Any],
        kwargs: Optional[Dict[str, Any]],
        time_limit_ms: int,
        memory_limit_mb: int,
    ) -> Dict[str, Any]:
        if not self.available():
            return {
                "status": "sandbox_unavailable",
                "message": "隔离的 Docker 执行环境不可用。",
            }

        timeout_seconds = max(0.2, (float(time_limit_ms) / 1000.0) + 1.0)
        with tempfile.TemporaryDirectory(prefix="eduagent-practice-") as temporary_directory:
            workspace = Path(temporary_directory)
            (workspace / "solution.py").write_text(source_code, encoding="utf-8")
            (workspace / "worker.py").write_text(_WORKER_SOURCE, encoding="utf-8")
            payload = json.dumps(
                {
                    "function_name": function_name,
                    "args": list(args),
                    "kwargs": kwargs or {},
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
            memory_limit = max(32, int(memory_limit_mb))
            cpu_limit = os.environ.get("CODE_SANDBOX_CPUS", "0.5")
            command = [
                self.docker_binary,
                "run",
                "--rm",
                "--interactive",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--pids-limit",
                "64",
                "--memory",
                f"{memory_limit}m",
                "--memory-swap",
                f"{memory_limit}m",
                "--cpus",
                cpu_limit,
                "--ulimit",
                "nofile=64:64",
                "--ulimit",
                "nproc=64:64",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                "--user",
                "65534:65534",
                "--workdir",
                "/workspace",
                "--volume",
                f"{workspace.resolve()}:/workspace:ro",
                "--env",
                "PYTHONDONTWRITEBYTECODE=1",
                self.image,
                "python",
                "-I",
                "-B",
                "/workspace/worker.py",
            ]
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    command,
                    input=payload,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return {
                    "status": "ok",
                    "verdict": "time_limit",
                    "runtime_ms": round((time.perf_counter() - started) * 1000, 3),
                    "memory_kb": None,
                    "message": "代码执行超过时间限制。",
                }
            except OSError as error:
                return {
                    "status": "sandbox_unavailable",
                    "message": f"无法启动隔离执行环境：{type(error).__name__}。",
                }

        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        raw_output = (completed.stdout or "").strip()
        if not raw_output:
            stderr = (completed.stderr or "").strip()
            return {
                "status": "sandbox_unavailable" if completed.returncode == 125 else "ok",
                "verdict": "internal_error",
                "runtime_ms": elapsed_ms,
                "memory_kb": None,
                "message": (
                    "隔离执行环境启动失败。"
                    if completed.returncode == 125
                    else "隔离执行器未返回结构化结果。"
                ),
                "runner_error": stderr[:500] if completed.returncode == 125 else "",
            }
        try:
            # The worker emits exactly one JSON object.  Taking the last line
            # prevents accidental learner stdout from being interpreted as a result.
            worker_result = json.loads(raw_output.splitlines()[-1])
        except (TypeError, ValueError, json.JSONDecodeError):
            return {
                "status": "ok",
                "verdict": "internal_error",
                "runtime_ms": elapsed_ms,
                "memory_kb": None,
                "message": "隔离执行器返回了无效结果。",
            }
        if not isinstance(worker_result, dict):
            return {
                "status": "ok",
                "verdict": "internal_error",
                "runtime_ms": elapsed_ms,
                "memory_kb": None,
                "message": "隔离执行器返回了无效结果。",
            }
        worker_result["runtime_ms"] = worker_result.get("runtime_ms", elapsed_ms)
        return worker_result


def _test_result_payload(
    test: PracticeTest,
    *,
    passed: bool,
    verdict: str,
    worker_result: Dict[str, Any],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": test.id,
        "visibility": test.visibility,
        "passed": bool(passed),
        "verdict": "accepted" if passed else verdict,
    }
    if test.visibility == "public":
        payload["input"] = list(test.args) if len(test.args) != 1 else test.args[0]
        payload["expected"] = test.expected
        if "actual" in worker_result:
            payload["actual"] = worker_result.get("actual")
        if worker_result.get("message"):
            payload["message"] = str(worker_result["message"])[:500]
    elif not passed:
        payload["message"] = "隐藏测试未通过。"
    return payload


def _summary(tests: list[Dict[str, Any]]) -> Dict[str, int]:
    public = [item for item in tests if item.get("visibility") == "public"]
    hidden = [item for item in tests if item.get("visibility") == "hidden"]
    return {
        "public_passed": sum(1 for item in public if item.get("passed")),
        "public_total": len(public),
        "hidden_passed": sum(1 for item in hidden if item.get("passed")),
        "hidden_total": len(hidden),
        "passed": sum(1 for item in tests if item.get("passed")),
        "total": len(tests),
    }


def _record_submission_receipt(
    state: AgentState,
    *,
    user_id: str,
    course_id: str,
    card: ResourceCard,
    problem: PracticeProblem,
    source_code: str,
    result: Dict[str, Any],
) -> str:
    """Persist a server-originated receipt for later event verification."""
    receipt_id = uuid.uuid4().hex
    receipts = state.internal_state.setdefault("practice_submission_receipts", [])
    if not isinstance(receipts, list):
        receipts = []
        state.internal_state["practice_submission_receipts"] = receipts
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    receipts.append(
        {
            "submission_id": receipt_id,
            "user_id": user_id,
            "course_id": course_id,
            "node_id": _as_resource_id(getattr(card, "node_id", "")),
            "resource_id": _as_resource_id(getattr(card, "resource_id", "")),
            "problem_id": problem.id,
            "problem_version": problem.version,
            "verdict": result.get("verdict"),
            "accepted": result.get("verdict") == "accepted",
            "summary": {
                "public_passed": int(summary.get("public_passed", 0) or 0),
                "public_total": int(summary.get("public_total", 0) or 0),
                "hidden_passed": int(summary.get("hidden_passed", 0) or 0),
                "hidden_total": int(summary.get("hidden_total", 0) or 0),
            },
            "runtime_ms": result.get("runtime_ms"),
            "memory_kb": result.get("memory_kb"),
            "source_code": source_code,
            "source_sha256": hashlib.sha256(source_code.encode("utf-8")).hexdigest(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "consumed_by_event_id": "",
        }
    )
    if len(receipts) > MAX_RECEIPTS_PER_SESSION:
        del receipts[:-MAX_RECEIPTS_PER_SESSION]
    return receipt_id


def execute_practice(
    state: AgentState,
    *,
    user_id: str,
    course_id: str,
    resource_id: str,
    problem_id: str,
    language: str,
    source_code: str,
    mode: str,
    executor: Optional[DockerSandboxExecutor] = None,
) -> Dict[str, Any]:
    """Run public tests or submit all tests for a session-bound resource."""
    resource_id = _as_resource_id(resource_id)
    problem_id = _as_resource_id(problem_id)
    language = _as_resource_id(language).lower()
    if mode not in {"run", "submit"}:
        return {"status": "invalid_request", "reason": "practice_mode_invalid"}
    if not resource_id:
        return {"status": "invalid_request", "reason": "practice_resource_id_required"}
    if language != SUPPORTED_LANGUAGE:
        return {"status": "invalid_request", "reason": "practice_language_unsupported"}
    if not isinstance(source_code, str) or not source_code.strip():
        return {"status": "invalid_request", "reason": "practice_code_required"}
    if len(source_code.encode("utf-8")) > MAX_SOURCE_BYTES:
        return {"status": "invalid_request", "reason": "practice_code_too_large"}

    problem, card, error = _resolve_problem(
        state,
        resource_id=resource_id,
        problem_id=problem_id,
    )
    if problem is None or card is None:
        return {"status": error.get("reason", "practice_problem_not_configured"), **error}

    active_executor = executor or DockerSandboxExecutor()
    selected_tests = list(problem.public_tests)
    if mode == "submit":
        selected_tests.extend(problem.hidden_tests)
    selected_tests = selected_tests[:MAX_TESTS_PER_EXECUTION]
    result_tests: list[Dict[str, Any]] = []
    total_runtime_ms = 0.0
    peak_memory_kb: Optional[int] = None
    terminal_verdict = "accepted"
    terminal_message = "所选测试全部通过。"

    for test in selected_tests:
        worker_result = active_executor.execute(
            source_code=source_code,
            function_name=problem.function_name,
            args=test.args,
            kwargs=test.kwargs,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_mb=problem.memory_limit_mb,
        )
        if worker_result.get("status") == "sandbox_unavailable":
            return {
                "status": "sandbox_unavailable",
                "mode": mode,
                "problem_id": problem.id,
                "problem_version": problem.version,
                "message": worker_result.get("message", "隔离执行环境不可用。"),
            }
        runtime_value = worker_result.get("runtime_ms")
        if isinstance(runtime_value, (int, float)):
            total_runtime_ms += max(0.0, float(runtime_value))
        memory_value = worker_result.get("memory_kb")
        if isinstance(memory_value, (int, float)):
            numeric_memory = max(0, int(memory_value))
            peak_memory_kb = max(peak_memory_kb or 0, numeric_memory)

        worker_status = str(worker_result.get("status") or "internal_error")
        worker_verdict = str(worker_result.get("verdict") or worker_status)
        if worker_status == "ok" and worker_verdict != "time_limit":
            passed = worker_result.get("actual") == test.expected
            verdict = "accepted" if passed else "wrong_answer"
        else:
            passed = False
            verdict = worker_verdict if worker_verdict in {
                "syntax_error", "runtime_error", "time_limit", "internal_error"
            } else "internal_error"
        result_tests.append(
            _test_result_payload(test, passed=passed, verdict=verdict, worker_result=worker_result)
        )
        if not passed:
            terminal_verdict = verdict
            terminal_message = (
                worker_result.get("message")
                if test.visibility == "public" and worker_result.get("message")
                else ("公开测试未通过。" if test.visibility == "public" else "隐藏测试未通过。")
            )
            break

    result: Dict[str, Any] = {
        "status": "ok",
        "mode": mode,
        "resource_id": _as_resource_id(getattr(card, "resource_id", "")),
        "node_id": _as_resource_id(getattr(card, "node_id", "")),
        "problem_id": problem.id,
        "problem_version": problem.version,
        "verdict": terminal_verdict,
        "tests": result_tests,
        "summary": _summary(result_tests),
        "runtime_ms": round(total_runtime_ms, 3),
        "memory_kb": peak_memory_kb,
        "message": str(terminal_message)[:500],
    }
    if mode == "submit":
        result["submission_id"] = _record_submission_receipt(
            state,
            user_id=user_id,
            course_id=course_id,
            card=card,
            problem=problem,
            source_code=source_code,
            result=result,
        )
    return result


def verify_submission_receipt(
    state: AgentState,
    *,
    user_id: str,
    course_id: str,
    node_id: str,
    resource_id: str,
    submission_id: str,
    event_id: str,
) -> Dict[str, Any]:
    """Validate a code-submitted event against a server-issued receipt.

    Client-provided verdicts and test summaries are intentionally ignored.  A
    receipt can be consumed only once.  ``accepted`` means the receipt is
    eligible to earn mastery credit; ``receipt_accepted`` preserves the
    server-owned verdict for review workflows even when a resource was already
    credited by an earlier accepted receipt.
    """
    if not _as_resource_id(node_id):
        return {"accepted": False, "reason": "code_submission_node_id_required"}
    if not _as_resource_id(resource_id):
        return {"accepted": False, "reason": "code_submission_resource_id_required"}
    receipts = state.internal_state.get("practice_submission_receipts", [])
    if not isinstance(receipts, list):
        return {"accepted": False, "reason": "code_submission_receipt_not_found"}
    receipt = next(
        (
            item
            for item in reversed(receipts)
            if isinstance(item, dict) and item.get("submission_id") == submission_id
        ),
        None,
    )
    if receipt is None:
        return {"accepted": False, "reason": "code_submission_receipt_not_found"}
    expected = {
        "user_id": user_id,
        "course_id": course_id,
        "node_id": node_id,
        "resource_id": resource_id,
    }
    for key, expected_value in expected.items():
        if expected_value and receipt.get(key) != expected_value:
            return {"accepted": False, "reason": f"code_submission_{key}_mismatch"}
    receipt_accepted = (
        receipt.get("accepted") is True
        and receipt.get("verdict") == "accepted"
    )
    evidence = _receipt_evidence(receipt)
    if receipt.get("consumed_by_event_id"):
        return {
            "accepted": False,
            "receipt_verified": False,
            "receipt_accepted": receipt_accepted,
            "reason": "code_submission_receipt_replayed",
            "evidence": evidence,
        }

    # Failed submissions are real, server-derived learning evidence too.  Mark
    # them consumed before returning so a copied receipt cannot repeatedly
    # inflate a review item's attempt counter.
    receipt["consumed_by_event_id"] = event_id
    if not receipt_accepted:
        return {
            "accepted": False,
            "receipt_verified": True,
            "receipt_accepted": False,
            "reason": "code_submission_not_accepted",
            "evidence": evidence,
        }
    credited = state.internal_state.setdefault("credited_practice_resource_ids", [])
    if not isinstance(credited, list):
        credited = []
        state.internal_state["credited_practice_resource_ids"] = credited
    receipt_resource_id = _as_resource_id(receipt.get("resource_id"))
    if receipt_resource_id in credited:
        return {
            "accepted": False,
            "receipt_verified": True,
            "receipt_accepted": True,
            "reason": "code_submission_resource_already_credited",
            "evidence": evidence,
        }
    credited.append(receipt_resource_id)
    return {
        "accepted": True,
        "receipt_verified": True,
        "receipt_accepted": True,
        "reason": "verified_code_submission",
        "evidence": evidence,
    }


def _receipt_evidence(receipt: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "submission_id": receipt.get("submission_id", ""),
        "resource_id": receipt.get("resource_id", ""),
        "problem_id": receipt.get("problem_id", ""),
        "problem_version": receipt.get("problem_version"),
        "verdict": receipt.get("verdict", ""),
        "summary": dict(receipt.get("summary") or {}),
        "runtime_ms": receipt.get("runtime_ms"),
        "memory_kb": receipt.get("memory_kb"),
        "source_code": receipt.get("source_code", ""),
        "source_sha256": receipt.get("source_sha256", ""),
        "created_at": receipt.get("created_at", ""),
    }
