from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from src.api_models.learning_event import LearningEventRequest, LearningEventType
from src.application import session_service
from src.observability import metrics, reset_metrics
from src.state.agent_state import ResourceCard
from tests.helpers import FakeRuntime, disable_persistence, install_fake_runtime


def _quiz_card() -> ResourceCard:
    return ResourceCard(
        resource_id="N01_diagnostic_quiz_supp",
        node_id="N01",
        card_type="diagnostic_quiz",
        content="## Diagnostic quiz",
        metadata={
            "structured_payload": {
                "questions": [
                    {"id": "N01-q1", "answer_index": 1},
                    {"id": "N01-q2", "answer_index": 0},
                ]
            }
        },
    )


def _complete_resource_set() -> list[ResourceCard]:
    cards = [_quiz_card()]
    for card_type in ("concept_map", "code_snippet", "interactive_exercise", "video_summary"):
        cards.append(
            ResourceCard(
                resource_id=f"N01_{card_type}_supp",
                node_id="N01",
                card_type=card_type,
                content=f"## {card_type}",
            )
        )
    return cards


def _install_evaluator(runtime: FakeRuntime, calls: list[object]) -> None:
    def evaluator(inp):
        calls.append(inp.raw_behavior)
        state = inp.agent_state
        updated_mastery = inp.raw_behavior.answer_correctness
        state.dynamic_profile.knowledge_mastery[inp.raw_behavior.node_id] = updated_mastery
        return SimpleNamespace(
            agent_state=state,
            cleaned_behavior=SimpleNamespace(
                effective_correctness=updated_mastery,
                anomaly=SimpleNamespace(anomaly_type=SimpleNamespace(value="normal")),
            ),
            anomaly_detected=False,
            mastery_delta=updated_mastery,
            pid_error=0.0,
            replan_decision=SimpleNamespace(value="maintain"),
            updated_mastery=updated_mastery,
        )

    runtime.evaluator = evaluator


def _session(runtime: FakeRuntime):
    session = runtime.get_session("event-user", "course1")
    state = session.agent_state
    state.current_node_id = "N01"
    state.active_path = ["N01", "N02"]
    state.dynamic_profile.knowledge_mastery["N01"] = 0.4
    state.generated_resources["N01"] = _complete_resource_set()
    return session


def _event(event_type: str, **overrides):
    payload = {
        "event_type": event_type,
        "user_id": "event-user",
        "course_id": "course1",
        "node_id": "N01",
        "resource_id": "",
        "question_id": "",
        "duration_ms": 1200,
        "attempt_number": 1,
        "used_hint": False,
        "result": {},
    }
    payload.update(overrides)
    return payload


def test_event_model_exposes_exact_canonical_vocabulary() -> None:
    expected = {
        "lesson_opened",
        "content_viewed",
        "hint_requested",
        "answer_selected",
        "answer_submitted",
        "code_run",
        "code_submitted",
        "lesson_completed",
        "review_completed",
        "tutor_question",
    }

    assert {event.value for event in LearningEventType} == expected
    for event_type in expected:
        event = LearningEventRequest.model_validate(_event(event_type))
        assert event.event_type.value == event_type
        assert event.duration_ms == 1200
        assert event.attempt_number == 1
        assert event.used_hint is False


def test_non_terminal_events_are_durable_but_never_change_mastery(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    _session(runtime)

    response = session_service.record_learning_event(
        "event-user",
        "course1",
        _event(
            "code_submitted",
            resource_id="N01_code_snippet_supp",
            result={
                "test_results": [
                    {"id": "case-1", "passed": True, "actual": "2", "expected": "2"},
                    {"id": "case-2", "passed": False, "actual": "0", "expected": "1"},
                ],
                # A summary score is retained for audit only and is not trusted.
                "score": 1.0,
            },
        ),
    )

    assert response["status"] == "ok"
    assert response["mastery_updated"] is False
    assert response["mastery_attribution"] is None
    assert calls == []

    history = session_service.get_learning_event_history("event-user", "course1")
    assert history["events"][-1]["event_type"] == "code_submitted"
    assert history["events"][-1]["result"]["test_results"][1]["passed"] is False
    assert history["mastery_attributions"] == []


def test_review_completion_uses_server_quiz_key_and_records_attribution(monkeypatch) -> None:
    reset_metrics()
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    session = _session(runtime)

    response = session_service.record_learning_event(
        "event-user",
        "course1",
        _event(
            "review_completed",
            event_id="review-completion-1",
            resource_id="N01_diagnostic_quiz_supp",
            duration_ms=6420,
            attempt_number=2,
            used_hint=True,
            result={
                "answers": [
                    {"question_id": "N01-q1", "selected_option_index": 1},
                    {"question_id": "N01-q2", "selected_option_index": 0},
                ],
                # It intentionally conflicts with the selections.  The server
                # computes 1.0 from its own answer key rather than this field.
                "score": 0.0,
            },
        ),
    )

    assert len(calls) == 1
    assert calls[0].answer_correctness == 1.0
    assert response["evidence_accepted"] is True
    assert response["mastery_updated"] is True
    assert response["effective_correctness"] == 1.0
    assert response["mastery_before"] == 0.4
    assert response["mastery_after"] == 1.0
    assert response["advanced_to_next_node"] is True
    assert metrics.counter_value(
        "learning.node_completion_attempt_total",
        event_type="review_completed",
        outcome="accepted",
    ) == 1
    assert metrics.counter_value(
        "learning.node_completion_total",
        event_type="review_completed",
        advanced="true",
    ) == 1

    attribution = response["mastery_attribution"]
    assert attribution["event_id"] == "review-completion-1"
    assert attribution["event_type"] == "review_completed"
    assert attribution["duration_ms"] == 6420
    assert attribution["attempt_number"] == 2
    assert attribution["used_hint"] is True
    assert attribution["evidence"]["correct_count"] == 2
    assert response["verified_evidence"]["correct_count"] == 2
    assert response["verified_evidence"]["question_results"][0]["correct"] is True
    assert session.agent_state.internal_state["verified_completion_events"][-1]["event_id"] == "review-completion-1"

    replay = session_service.record_learning_event(
        "event-user",
        "course1",
        _event(
            "review_completed",
            event_id="review-completion-1",
            resource_id="N01_diagnostic_quiz_supp",
            result={"answers": []},
        ),
    )
    assert replay["idempotent"] is True
    assert replay["mastery_attribution"]["event_id"] == "review-completion-1"
    assert replay["verified_evidence"]["question_count"] == 2
    assert len(calls) == 1


def test_verified_evidence_is_returned_when_completion_does_not_change_mastery(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    session = _session(runtime)
    session.agent_state.dynamic_profile.knowledge_mastery["N01"] = 1.0

    response = session_service.record_learning_event(
        "event-user",
        "course1",
        _event(
            "lesson_completed",
            resource_id="N01_diagnostic_quiz_supp",
            result={
                "answers": [
                    {"question_id": "N01-q1", "selected_option_index": 1},
                    {"question_id": "N01-q2", "selected_option_index": 0},
                ],
            },
        ),
    )

    assert len(calls) == 1
    assert response["evidence_accepted"] is True
    assert response["mastery_updated"] is False
    assert response["mastery_attribution"] is None
    assert response["verified_evidence"]["correct_count"] == 2
    assert len(response["verified_evidence"]["question_results"]) == 2


def test_same_event_id_is_atomic_during_a_timeout_retry_race(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    _session(runtime)

    original_evaluator = runtime.evaluator

    def delayed_evaluator(inp):
        # Without the per-session lock both callers can pass the duplicate
        # lookup while this first evaluation is still running.
        time.sleep(0.05)
        return original_evaluator(inp)

    runtime.evaluator = delayed_evaluator
    payload = _event(
        "lesson_completed",
        event_id="concurrent-completion-1",
        resource_id="N01_diagnostic_quiz_supp",
        result={
            "answers": [
                {"question_id": "N01-q1", "selected_option_index": 1},
                {"question_id": "N01-q2", "selected_option_index": 0},
            ],
        },
    )
    barrier = threading.Barrier(3)
    responses: list[dict] = []

    def record() -> None:
        barrier.wait()
        responses.append(session_service.record_learning_event("event-user", "course1", dict(payload)))

    first = threading.Thread(target=record)
    second = threading.Thread(target=record)
    first.start()
    second.start()
    barrier.wait()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(calls) == 1
    assert len(responses) == 2
    assert sum(bool(response["idempotent"]) for response in responses) == 1


def test_terminal_event_without_server_verifiable_evidence_cannot_change_mastery(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    session = _session(runtime)

    response = session_service.record_learning_event(
        "event-user",
        "course1",
        _event(
            "lesson_completed",
            resource_id="N01_code_snippet_supp",
            result={
                "test_results": [{"id": "case-1", "passed": True}],
                "score": 1.0,
                "correctness": 1.0,
            },
        ),
    )

    assert calls == []
    assert response["evidence_accepted"] is False
    assert response["mastery_updated"] is False
    assert response["mastery_update_reason"] == "missing_completion_evidence"
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 0.4
    assert session_service.get_learning_event_history("event-user", "course1")["mastery_attributions"] == []


def test_audit_only_terminal_event_does_not_reset_the_advanced_position(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    session = _session(runtime)
    session.agent_state.current_node_id = "N02"

    response = session_service.record_learning_event(
        "event-user",
        "course1",
        _event(
            "lesson_completed",
            node_id="N01",
            resource_id="N01_diagnostic_quiz_supp",
            result={"source_event_id": "review-completion-1"},
        ),
    )

    assert calls == []
    assert response["evidence_accepted"] is False
    assert response["current_node_id"] == "N02"
    assert session.agent_state.current_node_id == "N02"


def test_legacy_advance_records_a_canonical_event_for_mastery_changes(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    _session(runtime)

    response = session_service.advance_session(
        "event-user",
        "course1",
        behavior={
            "interaction_type": "complete_learning",
            "current_node_id": "N01",
            "resource_id": "N01_diagnostic_quiz_supp",
            "answers": [
                {"question_id": "N01-q1", "selected_option_index": 1},
                {"question_id": "N01-q2", "selected_option_index": 0},
            ],
        },
    )

    assert len(calls) == 1
    assert response["event_type"] == "lesson_completed"
    assert response["mastery_updated"] is True
    history = session_service.get_learning_event_history("event-user", "course1")
    assert history["events"][-1]["event_id"] == response["event_id"]
    assert history["mastery_attributions"][-1]["event_id"] == response["event_id"]


def test_event_identity_mismatch_is_rejected_before_it_enters_the_ledger(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    _session(runtime)

    response = session_service.record_learning_event(
        "event-user",
        "course1",
        _event("content_viewed", user_id="another-user"),
    )

    assert response["status"] == "invalid_event"
    assert response["blocked"] is True
    assert response["reason"] == "user_id_mismatch"
    assert session_service.get_learning_event_history("event-user", "course1")["events"] == []


def test_terminal_event_cannot_attribute_verified_evidence_to_another_resource(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    _session(runtime)

    response = session_service.record_learning_event(
        "event-user",
        "course1",
        _event(
            "review_completed",
            resource_id="visible-but-not-verified-card",
            completion_evidence={
                "evidence_type": "diagnostic_quiz",
                "resource_id": "N01_diagnostic_quiz_supp",
                "answers": [
                    {"question_id": "N01-q1", "selected_option_index": 1},
                    {"question_id": "N01-q2", "selected_option_index": 0},
                ],
            },
        ),
    )

    assert response["status"] == "invalid_event"
    assert response["blocked"] is True
    assert response["reason"] == "resource_id_mismatch"
    assert session_service.get_learning_event_history("event-user", "course1")["events"] == []


def test_audit_history_is_append_only_beyond_the_previous_in_memory_limits(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    _session(runtime)

    for index in range(501):
        response = session_service.record_learning_event(
            "event-user",
            "course1",
            _event("content_viewed", event_id=f"view-{index}"),
        )
        assert response["status"] == "ok"

    history = session_service.get_learning_event_history(
        "event-user",
        "course1",
        event_id="view-0",
        limit=1,
    )
    assert len(history["events"]) == 1
    assert history["events"][0]["event_id"] == "view-0"
    assert len(runtime.get_session("event-user", "course1").agent_state.internal_state["learning_events"]) == 501
