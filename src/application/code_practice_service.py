# -*- coding: utf-8 -*-
"""Server-owned coding-practice definitions and isolated execution.

Learner source is never evaluated by the application process. Production uses
the isolated sandbox-runner service; local development can fall back to a
fresh constrained Docker container. The application owns the answer key and
invokes the runner once per test, so hidden expectations never enter the
learner process.
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

from src.resource_generation.services import SandboxRunnerClient, ServiceUnavailable
from src.state.agent_state import AgentState, ResourceCard


SUPPORTED_LANGUAGE = "c"
DEFAULT_SANDBOX_IMAGE = "gcc:13"
DEFAULT_TIME_LIMIT_MS = 1_500
DEFAULT_MEMORY_LIMIT_MB = 128
MAX_SOURCE_BYTES = 64 * 1024
MAX_TESTS_PER_EXECUTION = 16
MAX_RECEIPTS_PER_SESSION = 500
MAX_SANDBOX_OUTPUT_BYTES = 64 * 1024
PRACTICE_CONTRACT_VERSION = 2

_WORKER_STATUSES = frozenset({
    "ok",
    "syntax_error",
    "runtime_error",
    "time_limit",
    "sandbox_unavailable",
})
_WORKER_VERDICTS = frozenset({
    "accepted",
    "wrong_answer",
    "syntax_error",
    "runtime_error",
    "time_limit",
    "internal_error",
    "sandbox_unavailable",
})


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


# Practice solutions are C functions.  The server-generated harness supplies
# each test input and prints one JSON result; hidden expected values never enter
# the container.  The public API still uses JSON-compatible values so the
# browser contract remains stable.
_PROBLEMS: Dict[str, PracticeProblem] = {
    "ds-list-sum": PracticeProblem(
        id="ds-list-sum",
        version=PRACTICE_CONTRACT_VERSION,
        title="序列求和",
        prompt="请实现 C 函数 `sum_values(numbers, count)`，返回数组中所有整数之和。",
        constraints="使用 `const int` 指针和 `count` 元素个数；`count` 为 0 时必须返回 0。",
        function_name="sum_values",
        starter_code=(
            "#include <stddef.h>\n"
            "\n"
            "int sum_values(const int *numbers, size_t count) {\n"
            "    /* Return the sum of all values. */\n"
            "    (void)numbers;\n"
            "    (void)count;\n"
            "    return 0;\n"
            "}\n"
        ),
        reference_solution=(
            "#include <stddef.h>\n"
            "int sum_values(const int *numbers, size_t count) {\n"
            "    int total = 0;\n"
            "    for (size_t i = 0; i < count; ++i) total += numbers[i];\n"
            "    return total;\n"
            "}\n"
        ),
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
        version=PRACTICE_CONTRACT_VERSION,
        title="平衡括号",
        prompt="请实现 C 函数 `is_balanced(text)`，判断 ()、[] 和 {} 是否正确嵌套。",
        constraints="忽略括号以外的字符；返回 1 表示平衡，返回 0 表示不平衡。",
        function_name="is_balanced",
        starter_code=(
            "#include <stddef.h>\n"
            "\n"
            "int is_balanced(const char *text) {\n"
            "    /* Use a stack to match opening and closing brackets. */\n"
            "    (void)text;\n"
            "    return 0;\n"
            "}\n"
        ),
        reference_solution=(
            "#include <stddef.h>\n"
            "int is_balanced(const char *text) {\n"
            "    char stack[1024];\n"
            "    size_t top = 0;\n"
            "    for (size_t i = 0; text && text[i] != '\\0'; ++i) {\n"
            "        char ch = text[i];\n"
            "        if (ch == '(' || ch == '[' || ch == '{') {\n"
            "            if (top >= sizeof(stack)) return 0;\n"
            "            stack[top++] = ch;\n"
            "        } else if (ch == ')' || ch == ']' || ch == '}') {\n"
            "            if (top == 0) return 0;\n"
            "            char open = stack[--top];\n"
            "            if ((ch == ')' && open != '(') ||\n"
            "                (ch == ']' && open != '[') ||\n"
            "                (ch == '}' && open != '{')) return 0;\n"
            "        }\n"
            "    }\n"
            "    return top == 0;\n"
            "}\n"
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
        version=PRACTICE_CONTRACT_VERSION,
        title="二叉树的高度",
        prompt=(
            "请实现 C 函数 `tree_height(values, present, count)`，其中二叉树使用层序数组表示，"
            "`present[i] == 0` 表示缺失节点；空树返回 0。"
        ),
        constraints="`values` 与 `present` 长度均为 `count`；返回至少包含一个节点的层数。",
        function_name="tree_height",
        starter_code=(
            "#include <stddef.h>\n"
            "\n"
            "int tree_height(const int *values, const int *present, size_t count) {\n"
            "    /* Level-order storage uses present[i] == 0 for a missing node. */\n"
            "    (void)values;\n"
            "    (void)present;\n"
            "    (void)count;\n"
            "    return 0;\n"
            "}\n"
        ),
        reference_solution=(
            "#include <stddef.h>\n"
            "int tree_height(const int *values, const int *present, size_t count) {\n"
            "    (void)values;\n"
            "    if (!present || count == 0 || !present[0]) return 0;\n"
            "    size_t last = count;\n"
            "    while (last > 0 && !present[last - 1]) --last;\n"
            "    int height = 0;\n"
            "    while (last > 0) {\n"
            "        ++height;\n"
            "        last /= 2;\n"
            "    }\n"
            "    return height;\n"
            "}\n"
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
        version=PRACTICE_CONTRACT_VERSION,
        title="广度优先搜索距离",
        prompt=(
            "请实现 C 函数 `bfs_distances(adjacency, vertex_count, start, distances)`。"
            "`adjacency` 是邻接矩阵，函数将从 `start` 出发的最短边数写入 `distances`。"
        ),
        constraints="不可达顶点写入 -1；每个顶点最多入队一次。",
        function_name="bfs_distances",
        starter_code=(
            "#include <stddef.h>\n"
            "\n"
            "void bfs_distances(const int *adjacency, size_t vertex_count,\n"
            "                    int start, int *distances) {\n"
            "    /* Visit every vertex at most once. */\n"
            "    (void)adjacency;\n"
            "    (void)vertex_count;\n"
            "    (void)start;\n"
            "    (void)distances;\n"
            "}\n"
        ),
        reference_solution=(
            "#include <stddef.h>\n"
            "void bfs_distances(const int *adjacency, size_t vertex_count,\n"
            "                    int start, int *distances) {\n"
            "    if (!adjacency || !distances || start < 0 || (size_t)start >= vertex_count) return;\n"
            "    for (size_t i = 0; i < vertex_count; ++i) distances[i] = -1;\n"
            "    int queue[256];\n"
            "    size_t head = 0, tail = 0;\n"
            "    distances[start] = 0;\n"
            "    queue[tail++] = start;\n"
            "    while (head < tail) {\n"
            "        int node = queue[head++];\n"
            "        for (size_t next = 0; next < vertex_count; ++next) {\n"
            "            if (adjacency[(size_t)node * vertex_count + next] && distances[next] < 0) {\n"
            "                distances[next] = distances[node] + 1;\n"
            "                if (tail < sizeof(queue) / sizeof(queue[0])) queue[tail++] = (int)next;\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
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
        version=PRACTICE_CONTRACT_VERSION,
        title="最大非相邻元素和",
        prompt=(
            "请实现 C 函数 `max_non_adjacent(values, count)`，返回不同时选取两个相邻元素时可得到的最大和；"
            "可以不选择任何元素。"
        ),
        constraints="当所有元素均为负数或 `count` 为 0 时返回 0。",
        function_name="max_non_adjacent",
        starter_code=(
            "#include <stddef.h>\n"
            "\n"
            "int max_non_adjacent(const int *values, size_t count) {\n"
            "    /* Use dynamic programming with constant extra space. */\n"
            "    (void)values;\n"
            "    (void)count;\n"
            "    return 0;\n"
            "}\n"
        ),
        reference_solution=(
            "#include <stddef.h>\n"
            "int max_non_adjacent(const int *values, size_t count) {\n"
            "    int previous_two = 0;\n"
            "    int previous_one = 0;\n"
            "    for (size_t i = 0; i < count; ++i) {\n"
            "        int take = previous_two + values[i];\n"
            "        int next = previous_one > take ? previous_one : take;\n"
            "        previous_two = previous_one;\n"
            "        previous_one = next;\n"
            "    }\n"
            "    return previous_one;\n"
            "}\n"
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


def _problem_binding(problem: PracticeProblem) -> Dict[str, Any]:
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
        "public_tests": [_public_test_payload(problem, test) for test in problem.public_tests],
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
    """Backfill or migrate a server-owned binding for a code card."""
    binding = _practice_binding(card)
    if getattr(card, "card_type", "") != "code_snippet":
        return binding
    problem = _PROBLEMS.get(_as_resource_id(binding.get("problem_id")))
    binding = _problem_binding(problem) if problem is not None else problem_binding_for_node(
        getattr(card, "node_id", "")
    )
    metadata = _card_metadata(card)
    metadata["practice"] = binding
    metadata["practice_problem_id"] = binding["problem_id"]
    metadata["practice_version"] = binding["version"]
    metadata["starter_code"] = binding["starter_code"]
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


def _graph_contract(args: tuple[Any, ...]) -> tuple[list[str], list[int], int]:
    """Convert the server fixture graph into the C adjacency-matrix contract."""
    graph = args[0] if args and isinstance(args[0], dict) else {}
    start = str(args[1] if len(args) > 1 else "")
    labels: list[str] = []
    for key, neighbors in graph.items():
        key_text = str(key)
        if key_text not in labels:
            labels.append(key_text)
        for neighbor in neighbors if isinstance(neighbors, (list, tuple)) else []:
            neighbor_text = str(neighbor)
            if neighbor_text not in labels:
                labels.append(neighbor_text)
    if not labels:
        labels = [start]
    label_index = {label: index for index, label in enumerate(labels)}
    matrix = [0] * (len(labels) * len(labels))
    for source, neighbors in graph.items():
        source_index = label_index.get(str(source))
        if source_index is None:
            continue
        for neighbor in neighbors if isinstance(neighbors, (list, tuple)) else []:
            target_index = label_index.get(str(neighbor))
            if target_index is not None:
                matrix[source_index * len(labels) + target_index] = 1
    return labels, matrix, label_index.get(start, 0)


def _public_test_payload(
    problem: PracticeProblem,
    test: PracticeTest,
    *,
    actual: Any = None,
    include_actual: bool = False,
) -> Dict[str, Any]:
    """Expose the C-side call contract rather than Python-shaped fixtures."""
    args = test.args
    if problem.function_name in {"sum_values", "max_non_adjacent"}:
        values = list(args[0]) if args and isinstance(args[0], (list, tuple)) else []
        array_parameter = "numbers" if problem.function_name == "sum_values" else "values"
        input_value: Any = {array_parameter: values, "count": len(values)}
        expected_value = test.expected
    elif problem.function_name == "is_balanced":
        input_value = {"text": str(args[0] if args else "")}
        expected_value = 1 if bool(test.expected) else 0
    elif problem.function_name == "tree_height":
        values = list(args[0]) if args and isinstance(args[0], (list, tuple)) else []
        input_value = {
            "values": [0 if value is None else int(value) for value in values],
            "present": [0 if value is None else 1 for value in values],
            "count": len(values),
        }
        expected_value = test.expected
    elif problem.function_name == "bfs_distances":
        labels, matrix, start_index = _graph_contract(args)
        input_value = {
            "adjacency": matrix,
            "vertex_count": len(labels),
            "start": start_index,
            "labels": labels,
        }
        expected_value = [
            int(test.expected.get(label, -1))
            if isinstance(test.expected, dict)
            else -1
            for label in labels
        ]
        if include_actual and isinstance(actual, dict):
            actual = [int(actual.get(label, -1)) for label in labels]
    else:
        input_value = list(args) if len(args) != 1 else args[0]
        expected_value = test.expected

    payload: Dict[str, Any] = {
        "id": test.id,
        "input": input_value,
        "expected": expected_value,
    }
    if include_actual:
        payload["actual"] = actual
    return payload


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
        "public_tests": [_public_test_payload(problem, test) for test in problem.public_tests],
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


def _c_string_literal(value: object) -> str:
    """Encode a bounded text value as a C string literal."""
    text = str(value or "")
    chunks: list[str] = ['"']
    for char in text:
        if char == "\\":
            chunks.append("\\\\")
        elif char == '"':
            chunks.append('\\"')
        elif char == "\n":
            chunks.append("\\n")
        elif char == "\r":
            chunks.append("\\r")
        elif char == "\t":
            chunks.append("\\t")
        elif ord(char) < 32 or ord(char) > 126:
            # Three-digit octal escapes are unambiguous even when the next
            # source character is a hexadecimal digit. C's ``\x`` escape,
            # by contrast, consumes every following hexadecimal character.
            for byte in char.encode("utf-8"):
                chunks.append(f"\\{byte:03o}")
        else:
            chunks.append(char)
    chunks.append('"')
    return "".join(chunks)


def _c_int_array(values: Iterable[object]) -> tuple[str, int]:
    numbers = [int(value or 0) for value in values]
    # C does not permit an empty initializer on all supported compilers.
    initializer = ", ".join(str(value) for value in numbers) or "0"
    return "{" + initializer + "}", len(numbers)


def _build_c_runner(function_name: str, args: tuple[Any, ...]) -> str:
    """Build a test-specific C harness without including learner source.

    The learner and harness are compiled as separate translation units.  This
    keeps learner preprocessor definitions (for example ``#define main`` or
    ``#define printf``) from rewriting the server-owned test program.
    """
    declarations = {
        "sum_values": "int sum_values(const int *numbers, size_t count);\n",
        "max_non_adjacent": "int max_non_adjacent(const int *values, size_t count);\n",
        "is_balanced": "int is_balanced(const char *text);\n",
        "tree_height": (
            "int tree_height(const int *values, const int *present, size_t count);\n"
        ),
        "bfs_distances": (
            "void bfs_distances(const int *adjacency, size_t vertex_count, "
            "int start, int *distances);\n"
        ),
    }
    try:
        declaration = declarations[function_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported C practice function: {function_name}") from exc
    prefix = (
        "#include <stddef.h>\n"
        "#include <stdio.h>\n"
        "\n"
        + declaration
        + "\n"
    )
    if function_name in {"sum_values", "max_non_adjacent"}:
        values = args[0] if args and isinstance(args[0], (list, tuple)) else []
        array, count = _c_int_array(values)
        return (
            prefix
            + f"int main(void) {{\n    const int values[] = {array};\n"
            + f"    int actual = {function_name}(values, {count}u);\n"
            + '    printf("{\\"status\\":\\"ok\\",\\"actual\\":%d}\\n", actual);\n'
            + "    return 0;\n}\n"
        )
    if function_name == "is_balanced":
        text = args[0] if args else ""
        return (
            prefix
            + "int main(void) {\n"
            + f"    int actual = is_balanced({_c_string_literal(text)});\n"
            + '    printf("{\\"status\\":\\"ok\\",\\"actual\\":%d}\\n", actual ? 1 : 0);\n'
            + "    return 0;\n}\n"
        )
    if function_name == "tree_height":
        values = args[0] if args and isinstance(args[0], (list, tuple)) else []
        raw_values = [0 if value is None else int(value) for value in values]
        present = [0 if value is None else 1 for value in values]
        values_array, count = _c_int_array(raw_values)
        present_array, _ = _c_int_array(present)
        return (
            prefix
            + f"int main(void) {{\n    const int values[] = {values_array};\n"
            + f"    const int present[] = {present_array};\n"
            + f"    int actual = tree_height(values, present, {count}u);\n"
            + '    printf("{\\"status\\":\\"ok\\",\\"actual\\":%d}\\n", actual);\n'
            + "    return 0;\n}\n"
        )
    if function_name == "bfs_distances":
        labels, matrix, start_index = _graph_contract(args)
        vertex_count = len(labels)
        matrix_array, _ = _c_int_array(matrix)
        label_json = ", ".join(_c_string_literal(label) for label in labels)
        output = [
            prefix,
            "int main(void) {\n",
            f"    const int adjacency[] = {matrix_array};\n",
            f"    int distances[{max(1, vertex_count)}];\n",
            f"    bfs_distances(adjacency, {vertex_count}u, {start_index}, distances);\n",
            "    const char *labels[] = {" + label_json + "};\n",
            '    printf("{\\"status\\":\\"ok\\",\\"actual\\":{");\n',
            "    int first = 1;\n",
            f"    for (size_t i = 0; i < {vertex_count}u; ++i) {{\n",
            "        if (distances[i] < 0) continue;\n",
            '        if (!first) putchar(\',\');\n',
            '        printf("\\\"%s\\\":%d", labels[i], distances[i]);\n',
            "        first = 0;\n",
            "    }\n",
            '    puts("}}");\n',
            "    return 0;\n}\n",
        ]
        return "".join(output)
    raise ValueError(f"Unsupported C practice function: {function_name}")


def _internal_worker_result(message: str = "隔离执行器返回了无效结果。") -> Dict[str, Any]:
    return {
        "status": "ok",
        "verdict": "internal_error",
        "message": message,
    }


def _validate_worker_result(result: object) -> Dict[str, Any]:
    """Validate the small result contract shared by local and remote runners."""
    if not isinstance(result, dict):
        return _internal_worker_result()

    normalized = dict(result)
    status = str(normalized.get("status") or "").strip().lower()
    if status not in _WORKER_STATUSES:
        return _internal_worker_result()
    normalized["status"] = status

    raw_verdict = normalized.get("verdict")
    verdict = str(raw_verdict).strip().lower() if raw_verdict is not None else ""
    if verdict and verdict not in _WORKER_VERDICTS:
        return _internal_worker_result()

    if status == "ok":
        # A successful worker response must carry the value produced by the
        # learner function.  Comparing a missing value would look like a
        # learner wrong answer instead of an executor failure.
        if "actual" not in normalized:
            return _internal_worker_result()
        if verdict:
            normalized["verdict"] = verdict
        return normalized

    normalized["verdict"] = verdict or status
    return normalized


# Kept as a small introspection marker for deployments that report the runner
# protocol.  Actual execution uses a compiler-generated C harness above.
_WORKER_SOURCE = "/* EduAgent C11 practice harness: compile solution.c and run one test. */"


class RemoteSandboxExecutor:
    """Execute one C11 test through the separately isolated runner service."""

    def __init__(self, client: Optional[SandboxRunnerClient] = None) -> None:
        self.client = client or SandboxRunnerClient()

    def available(self) -> bool:
        return bool(self.client.available)

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
        try:
            harness_source = _build_c_runner(function_name, tuple(args))
            result = self.client.execute_c_case(
                source_code=source_code,
                harness_source=harness_source,
                time_limit_ms=time_limit_ms,
                memory_limit_mb=memory_limit_mb,
                output_limit_bytes=MAX_SANDBOX_OUTPUT_BYTES,
            )
        except (TypeError, ValueError, OverflowError) as exc:
            return {
                "status": "ok",
                "verdict": "internal_error",
                "message": f"代码测试输入无法构造：{type(exc).__name__}。",
            }
        except ServiceUnavailable:
            return {
                "status": "sandbox_unavailable",
                "message": "隔离执行环境暂时不可用。",
            }
        return _validate_worker_result(result)


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

    def _force_remove(self, container_name: str) -> None:
        try:
            subprocess.run(
                [self.docker_binary, "rm", "--force", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

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
            (workspace / "solution.c").write_text(source_code, encoding="utf-8")
            try:
                runner_source = _build_c_runner(function_name, tuple(args))
            except (TypeError, ValueError, OverflowError) as exc:
                return {
                    "status": "ok",
                    "verdict": "internal_error",
                    "message": f"代码测试输入无法构造：{type(exc).__name__}。",
                }
            (workspace / "runner.c").write_text(runner_source, encoding="utf-8")
            memory_limit = max(32, int(memory_limit_mb))
            cpu_limit = os.environ.get("CODE_SANDBOX_CPUS", "0.5")
            container_name = f"eduagent-practice-{uuid.uuid4().hex[:16]}"
            file_limit_blocks = max(256, (MAX_SANDBOX_OUTPUT_BYTES * 2 + 511) // 512)
            sandbox_command = (
                f"ulimit -f {file_limit_blocks}; "
                "gcc -std=c11 -O2 -pipe -fvisibility=hidden -fno-common "
                "/workspace/solution.c -c -o /tmp/solution.o "
                "2>/tmp/compiler.err; "
                "compile_status=$?; "
                "if [ \"$compile_status\" -eq 0 ]; then "
                "gcc -std=c11 -O2 -pipe /workspace/runner.c /tmp/solution.o "
                "-o /tmp/eduagent-runner 2>>/tmp/compiler.err; "
                "compile_status=$?; "
                "fi; "
                f"head -c {MAX_SANDBOX_OUTPUT_BYTES} /tmp/compiler.err >&2; "
                '[ "$compile_status" -eq 0 ] || exit 100; '
                "/tmp/eduagent-runner >/tmp/program.out 2>/tmp/runtime.err; "
                "run_status=$?; "
                f"head -c {MAX_SANDBOX_OUTPUT_BYTES} /tmp/program.out; "
                f"head -c {MAX_SANDBOX_OUTPUT_BYTES} /tmp/runtime.err >&2; "
                'exit "$run_status"'
            )
            command = [
                self.docker_binary,
                "run",
                "--rm",
                "--name",
                container_name,
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
                # The compiler output must execute inside the sandbox.  The
                # container remains isolated, read-only outside this bounded
                # temporary mount, and drops capabilities/network access.
                "/tmp:rw,exec,nosuid,size=16m",
                "--user",
                "65534:65534",
                "--workdir",
                "/workspace",
                "--volume",
                f"{workspace.resolve()}:/workspace:ro",
                "--env",
                "LC_ALL=C",
                self.image,
                "sh",
                "-c",
                sandbox_command,
            ]
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    command,
                    input="",
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                self._force_remove(container_name)
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
        stderr = (completed.stderr or "").strip()
        if completed.returncode == 125:
            return {
                "status": "sandbox_unavailable",
                "runtime_ms": elapsed_ms,
                "memory_kb": None,
                "message": "隔离执行环境启动失败。",
                "runner_error": stderr[:500],
            }
        if completed.returncode == 100:
            return {
                "status": "syntax_error",
                "verdict": "syntax_error",
                "runtime_ms": elapsed_ms,
                "memory_kb": None,
                "message": "代码编译失败，请检查 C11 语法。",
                "compiler_diagnostic": stderr[:500],
            }
        if completed.returncode != 0:
            return {
                "status": "runtime_error",
                "verdict": "runtime_error",
                "runtime_ms": elapsed_ms,
                "memory_kb": None,
                "message": "代码运行时异常终止。",
                "runtime_diagnostic": stderr[:500],
            }
        if not raw_output:
            return {
                "status": "ok",
                "verdict": "internal_error",
                "runtime_ms": elapsed_ms,
                "memory_kb": None,
                "message": "隔离执行器未返回结构化结果。",
            }
        try:
            # The worker emits exactly one JSON object.  Taking the last line
            # prevents accidental learner stdout from being interpreted as a result.
            worker_result = json.loads(raw_output.splitlines()[-1])
        except (TypeError, ValueError, json.JSONDecodeError):
            invalid = _internal_worker_result()
            invalid.update({"runtime_ms": elapsed_ms, "memory_kb": None})
            return invalid
        worker_result = _validate_worker_result(worker_result)
        worker_result["runtime_ms"] = worker_result.get("runtime_ms", elapsed_ms)
        return worker_result


def _default_sandbox_executor() -> RemoteSandboxExecutor | DockerSandboxExecutor:
    if str(os.environ.get("SANDBOX_RUNNER_URL") or "").strip():
        return RemoteSandboxExecutor()
    return DockerSandboxExecutor()


def _worker_message(worker_result: Dict[str, Any]) -> str:
    """Build a bounded learner-facing message with compiler context."""
    limit = 500
    message = str(worker_result.get("message") or "").strip()
    diagnostic = str(
        worker_result.get("compiler_diagnostic")
        or worker_result.get("runtime_diagnostic")
        or ""
    ).strip()
    if not diagnostic:
        return message[:limit]
    if diagnostic in message:
        return message[:limit]
    diagnostic = diagnostic[:limit]
    if not message or len(diagnostic) >= limit:
        return diagnostic
    prefix = message[: max(0, limit - len(diagnostic) - 1)]
    return f"{prefix}\n{diagnostic}"


def _test_result_payload(
    problem: PracticeProblem,
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
        public_payload = _public_test_payload(
            problem,
            test,
            actual=worker_result.get("actual"),
            include_actual="actual" in worker_result,
        )
        payload.update(public_payload)
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
    executor: Optional[Any] = None,
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

    active_executor = executor or _default_sandbox_executor()
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
        worker_result = _validate_worker_result(active_executor.execute(
            source_code=source_code,
            function_name=problem.function_name,
            args=test.args,
            kwargs=test.kwargs,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_mb=problem.memory_limit_mb,
        ) or {})
        if worker_result.get("compiler_diagnostic") or worker_result.get("runtime_diagnostic"):
            worker_result["message"] = _worker_message(worker_result)
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
        if worker_status == "ok" and worker_verdict not in {
            "time_limit",
            "internal_error",
            "syntax_error",
            "runtime_error",
            "sandbox_unavailable",
        }:
            passed = worker_result.get("actual") == test.expected
            verdict = "accepted" if passed else "wrong_answer"
        else:
            passed = False
            verdict = worker_verdict if worker_verdict in {
                "syntax_error", "runtime_error", "time_limit", "internal_error"
            } else "internal_error"
        result_tests.append(
            _test_result_payload(
                problem,
                test,
                passed=passed,
                verdict=verdict,
                worker_result=worker_result,
            )
        )
        if not passed:
            terminal_verdict = verdict
            terminal_message = (
                _worker_message(worker_result)
                if test.visibility == "public" and _worker_message(worker_result)
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
