from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from starlette.requests import Request
from starlette.testclient import TestClient

from frontend import server
from src.auth.security import SecurityManager
from src.api_models.learning_event import LearningEventRequest
from src.application import code_practice_service, review_service, session_service
from src.state.agent_state import AgentState, ResourceCard


def _state() -> AgentState:
    state = AgentState(user_id="practice-user", course_id="practice-course", current_node_id="N01")
    card = ResourceCard(
        resource_id="N01_code_snippet_supp",
        node_id="N01",
        card_type="code_snippet",
        content="```python\ndef sum_values(numbers):\n    pass\n```",
        metadata={"practice": code_practice_service.problem_binding_for_node("N01")},
    )
    state.generated_resources["N01"] = [card]
    state.dynamic_profile.knowledge_mastery["N01"] = 0.3
    return state


def _auth_headers(user_id: str = "practice-user") -> dict[str, str]:
    token = SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
    return {"Authorization": f"Bearer {token}"}


class _PassingExecutor:
    def execute(self, *, args, **_kwargs):
        values = args[0]
        return {
            "status": "ok",
            "actual": sum(values),
            "runtime_ms": 4.5,
            "memory_kb": 1024,
        }


class _HiddenFailureExecutor:
    """Pass public list-sum cases but fail the first server-only case."""

    def execute(self, *, args, **_kwargs):
        values = args[0]
        actual = sum(values)
        if values == [-4, 9, 0, 5]:
            actual += 1
        return {
            "status": "ok",
            "actual": actual,
            "runtime_ms": 4.5,
            "memory_kb": 1024,
        }


class _InternalFailureExecutor:
    def execute(self, **_kwargs):
        return {
            "status": "internal_error",
            "verdict": "internal_error",
            "message": "Runner failed internally.",
            "runtime_ms": 1.0,
            "memory_kb": None,
        }


def _code_submission_event(submission_id: str, *, event_id: str) -> dict:
    return LearningEventRequest(
        event_id=event_id,
        event_type="code_submitted",
        user_id="practice-user",
        course_id="practice-course",
        node_id="N01",
        resource_id="N01_code_snippet_supp",
        duration_ms=1200,
        attempt_number=1,
        # These client fields intentionally contradict the receipt. The
        # service must derive both review state and mastery from its own data.
        result={
            "submission_id": submission_id,
            "verdict": "accepted",
            "summary": {"passed": 999},
            "test_results": [{"passed": True, "expected": "client-claim"}],
        },
    ).model_dump(mode="json")


def test_problem_payload_redacts_hidden_tests_and_reference_solution() -> None:
    state = _state()

    result = code_practice_service.get_practice_problem(state, "N01_code_snippet_supp")

    assert result["status"] == "ok"
    problem = result["problem"]
    assert problem["problem_id"] == "ds-list-sum"
    assert problem["hidden_test_count"] > 0
    assert "hidden_tests" not in problem
    assert "reference_solution" not in problem
    assert all("expected" in case for case in problem["public_tests"])


def test_run_uses_only_public_tests_and_submission_redacts_hidden_cases() -> None:
    state = _state()
    source = "def sum_values(numbers):\n    return sum(numbers)\n"

    run = code_practice_service.execute_practice(
        state,
        user_id="practice-user",
        course_id="practice-course",
        resource_id="N01_code_snippet_supp",
        problem_id="ds-list-sum",
        language="python",
        source_code=source,
        mode="run",
        executor=_PassingExecutor(),
    )

    assert run["status"] == "ok"
    assert run["verdict"] == "accepted"
    assert run["summary"]["hidden_total"] == 0
    assert all(test["visibility"] == "public" for test in run["tests"])

    submitted = code_practice_service.execute_practice(
        state,
        user_id="practice-user",
        course_id="practice-course",
        resource_id="N01_code_snippet_supp",
        problem_id="ds-list-sum",
        language="python",
        source_code=source,
        mode="submit",
        executor=_PassingExecutor(),
    )

    assert submitted["status"] == "ok"
    assert submitted["verdict"] == "accepted"
    assert submitted["submission_id"]
    hidden = next(test for test in submitted["tests"] if test["visibility"] == "hidden")
    assert "input" not in hidden
    assert "expected" not in hidden
    assert "actual" not in hidden


def test_submission_receipt_can_be_consumed_once_and_updates_mastery(monkeypatch) -> None:
    state = _state()
    source = "def sum_values(numbers):\n    return sum(numbers)\n"
    submitted = code_practice_service.execute_practice(
        state,
        user_id="practice-user",
        course_id="practice-course",
        resource_id="N01_code_snippet_supp",
        problem_id="ds-list-sum",
        language="python",
        source_code=source,
        mode="submit",
        executor=_PassingExecutor(),
    )
    assert submitted["verdict"] == "accepted"

    session = SimpleNamespace(agent_state=state, pipeline_log=[])
    monkeypatch.setattr(session_service, "get_session", lambda *_args: session)
    monkeypatch.setattr(session_service, "persist_session", lambda *_args: None)

    payload = LearningEventRequest(
        event_type="code_submitted",
        user_id="practice-user",
        course_id="practice-course",
        node_id="N01",
        resource_id="N01_code_snippet_supp",
        duration_ms=1200,
        attempt_number=1,
        result={"submission_id": submitted["submission_id"], "test_results": [{"passed": True}]},
    ).model_dump(mode="json")
    response = session_service.record_learning_event("practice-user", "practice-course", payload)

    assert response["evidence_accepted"] is True
    assert response["mastery_updated"] is True
    assert response["mastery_update_reason"] == "verified_code_submission"
    assert response["mastery_attribution"]["evidence"]["submission_id"] == submitted["submission_id"]
    assert state.dynamic_profile.knowledge_mastery["N01"] == 0.42

    replay_payload = {**payload, "event_id": "replay-event"}
    replay = session_service.record_learning_event("practice-user", "practice-course", replay_payload)
    assert replay["evidence_accepted"] is False
    assert replay["mastery_update_reason"] == "code_submission_receipt_replayed"


def test_failed_verified_submission_creates_safe_review_and_later_acceptance_closes_it(monkeypatch) -> None:
    state = _state()
    failed_submission = code_practice_service.execute_practice(
        state,
        user_id="practice-user",
        course_id="practice-course",
        resource_id="N01_code_snippet_supp",
        problem_id="ds-list-sum",
        language="python",
        source_code="def sum_values(numbers):\n    return sum(numbers)\n",
        mode="submit",
        executor=_HiddenFailureExecutor(),
    )
    assert failed_submission["verdict"] == "wrong_answer"
    assert failed_submission["summary"] == {
        "public_passed": 2,
        "public_total": 2,
        "hidden_passed": 0,
        "hidden_total": 1,
        "passed": 2,
        "total": 3,
    }

    session = SimpleNamespace(agent_state=state, pipeline_log=[])
    monkeypatch.setattr(session_service, "get_session", lambda *_args: session)
    monkeypatch.setattr(session_service, "persist_session", lambda *_args: None)
    monkeypatch.setattr(review_service, "get_session", lambda *_args: session)
    monkeypatch.setattr(review_service, "persist_session", lambda *_args: None)

    failed = session_service.record_learning_event(
        "practice-user",
        "practice-course",
        _code_submission_event(failed_submission["submission_id"], event_id="failed-code-event"),
    )

    assert failed["evidence_accepted"] is False
    assert failed["mastery_updated"] is False
    assert failed["mastery_update_reason"] == "code_submission_not_accepted"
    review_item = failed["review"]["created_or_updated_items"][0]
    assert review_item["review_kind"] == "code_practice"
    assert review_item["error_type"] == "wrong_answer"
    assert review_item["original_answer"] == "def sum_values(numbers):\n    return sum(numbers)\n"
    assert review_item["correct_answer"] == "\u901a\u8fc7\u5168\u90e8\u670d\u52a1\u7aef\u6d4b\u8bd5"
    assert review_item["node_id"] == "N01"
    assert review_item["source_resource_id"] == "N01_code_snippet_supp"
    assert review_item["status"] == "due"
    assert failed["review"]["requires_remediation"] is True
    assert [step["kind"] for step in failed["review"]["remediation"]["steps"]] == [
        "review_material",
        "targeted_practice",
        "retest",
    ]
    assert review_item["last_result"]["summary"] == {
        "public_passed": 2,
        "public_total": 2,
        "hidden_passed": 0,
        "hidden_total": 1,
    }
    serialized_review = repr(review_item)
    assert "hidden-1" not in serialized_review
    assert "[-4, 9, 0, 5]" not in serialized_review
    assert "reference_solution" not in serialized_review

    started = review_service.start_review_item(
        "practice-user",
        "practice-course",
        review_item["review_item_id"],
    )
    assert started["learning_task"]["focus_resource_type"] == "code_snippet"
    assert started["learning_task"]["review_kind"] == "code_practice"
    assert started["learning_task"]["phase"] == "code_resubmission"
    not_a_quiz_retest = review_service.prepare_review_retest(
        "practice-user",
        "practice-course",
        review_item["review_item_id"],
    )
    assert not_a_quiz_retest["status"] == "code_review_requires_submission"
    assert not_a_quiz_retest["status_code"] == 409

    replay = session_service.record_learning_event(
        "practice-user",
        "practice-course",
        _code_submission_event(failed_submission["submission_id"], event_id="failed-code-replay"),
    )
    assert replay["mastery_update_reason"] == "code_submission_receipt_replayed"
    assert state.internal_state["review_items"][0]["attempt_count"] == 1

    accepted_submission = code_practice_service.execute_practice(
        state,
        user_id="practice-user",
        course_id="practice-course",
        resource_id="N01_code_snippet_supp",
        problem_id="ds-list-sum",
        language="python",
        source_code="def sum_values(numbers):\n    return sum(numbers)\n",
        mode="submit",
        executor=_PassingExecutor(),
    )
    accepted = session_service.record_learning_event(
        "practice-user",
        "practice-course",
        _code_submission_event(accepted_submission["submission_id"], event_id="accepted-code-event"),
    )

    assert accepted["evidence_accepted"] is True
    assert accepted["mastery_updated"] is True
    assert accepted["review"]["retested_items"][0]["review_item_id"] == review_item["review_item_id"]
    assert accepted["review"]["retested_items"][0]["status"] == "completed"
    assert state.internal_state["review_items"][0]["resolution_submission_id"] == accepted_submission["submission_id"]
    assert state.dynamic_profile.knowledge_mastery["N01"] == 0.42


def test_internal_runner_failure_is_retryable_and_does_not_create_a_weakness(monkeypatch) -> None:
    state = _state()
    submitted = code_practice_service.execute_practice(
        state,
        user_id="practice-user",
        course_id="practice-course",
        resource_id="N01_code_snippet_supp",
        problem_id="ds-list-sum",
        language="python",
        source_code="def sum_values(numbers):\n    return sum(numbers)\n",
        mode="submit",
        executor=_InternalFailureExecutor(),
    )
    assert submitted["verdict"] == "internal_error"

    session = SimpleNamespace(agent_state=state, pipeline_log=[])
    monkeypatch.setattr(session_service, "get_session", lambda *_args: session)
    monkeypatch.setattr(session_service, "persist_session", lambda *_args: None)
    monkeypatch.setattr(review_service, "get_session", lambda *_args: session)

    recorded = session_service.record_learning_event(
        "practice-user",
        "practice-course",
        _code_submission_event(submitted["submission_id"], event_id="internal-code-event"),
    )

    assert recorded["mastery_updated"] is False
    assert recorded["review"]["created_or_updated_items"] == []
    assert recorded["review"]["requires_remediation"] is False
    assert recorded["review"]["transient_failure"] == {
        "reason": "code_execution_internal_error",
        "retryable": True,
    }
    assert review_service.get_review_dashboard("practice-user", "practice-course")["weak_nodes"] == []


def test_client_test_data_and_missing_runtime_are_not_executable_evidence() -> None:
    state = _state()
    unavailable = code_practice_service.DockerSandboxExecutor(docker_binary="definitely-not-a-docker-binary")
    result = unavailable.execute(
        source_code="def sum_values(numbers): return sum(numbers)",
        function_name="sum_values",
        args=([1],),
        kwargs={},
        time_limit_ms=100,
        memory_limit_mb=32,
    )

    assert result["status"] == "sandbox_unavailable"
    verification = code_practice_service.verify_submission_receipt(
        state,
        user_id="practice-user",
        course_id="practice-course",
        node_id="N01",
        resource_id="N01_code_snippet_supp",
        submission_id="client-invented",
        event_id="event-1",
    )
    assert verification["accepted"] is False
    assert verification["reason"] == "code_submission_receipt_not_found"


def test_practice_http_boundary_uses_session_problem_and_rejects_client_tests(monkeypatch) -> None:
    session = SimpleNamespace(agent_state=_state(), pipeline_log=[])
    monkeypatch.setattr(server, "get_session", lambda *_args: session)
    monkeypatch.setattr(server, "persist_session", lambda *_args: None)
    client = TestClient(server.app)
    path = "/api/sessions/practice-user%3Apractice-course/practice"

    problem_response = client.get(
        f"{path}/problems/N01_code_snippet_supp",
        headers=_auth_headers(),
    )
    assert problem_response.status_code == 200
    assert problem_response.json()["problem"]["problem_id"] == "ds-list-sum"

    rejected = client.post(
        f"{path}/run",
        headers=_auth_headers(),
        json={
            "resource_id": "N01_code_snippet_supp",
            "language": "python",
            "code": "def sum_values(numbers): return sum(numbers)",
            "tests": [{"expected": 99}],
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["status"] == "client_test_data_forbidden"

    unauthorized = client.get(f"{path}/problems/N01_code_snippet_supp")
    assert unauthorized.status_code == 401


def test_practice_execution_does_not_block_the_event_loop(monkeypatch) -> None:
    session = SimpleNamespace(agent_state=_state(), pipeline_log=[])

    def slow_execute(*_args, **_kwargs):
        time.sleep(0.2)
        return {
            "status": "ok",
            "mode": "run",
            "resource_id": "N01_code_snippet_supp",
            "problem_id": "ds-list-sum",
            "verdict": "accepted",
            "tests": [],
            "summary": {"passed": 0, "total": 0},
        }

    monkeypatch.setattr(server, "get_session", lambda *_args: session)
    monkeypatch.setattr(server, "persist_session", lambda *_args: None)
    monkeypatch.setattr(server.code_practice_service, "execute_practice", slow_execute)

    async def scenario() -> None:
        payload = json.dumps({
            "resource_id": "N01_code_snippet_supp",
            "problem_id": "ds-list-sum",
            "language": "python",
            "code": "def sum_values(numbers): return sum(numbers)",
        }).encode("utf-8")
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}

        token = SecurityManager.create_token_pair("practice-user", "STUDENT")["access_token"]
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/sessions/practice-user:practice-course/practice/run",
                "path_params": {"session_id": "practice-user:practice-course"},
                "query_string": b"",
                "headers": [
                    (b"authorization", f"Bearer {token}".encode("ascii")),
                    (b"content-type", b"application/json"),
                ],
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
                "scheme": "http",
            },
            receive,
        )

        started = time.perf_counter()
        execution = asyncio.create_task(server.api_session_practice_run(request))
        await asyncio.sleep(0.03)

        assert time.perf_counter() - started < 0.12
        assert execution.done() is False
        response = await execution
        assert response.status_code == 200

    asyncio.run(scenario())
