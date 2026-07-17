from __future__ import annotations

from types import SimpleNamespace

from src.orchestration_core import run_official_learning_step
from src.state.agent_state import ResourceCard
from tests.helpers import FakeRuntime


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


def _runtime_with_evaluator(calls: list[object]) -> FakeRuntime:
    runtime = FakeRuntime()

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
    return runtime


def _session(runtime: FakeRuntime):
    session = runtime.get_session("truthful-user", "course1")
    state = session.agent_state
    state.current_node_id = "N01"
    state.active_path = ["N01", "N02"]
    state.dynamic_profile.knowledge_mastery["N01"] = 0.4
    state.generated_resources["N01"] = _complete_resource_set()
    return session


def test_browse_node_never_evaluates_or_changes_mastery() -> None:
    calls: list[object] = []
    runtime = _runtime_with_evaluator(calls)
    session = _session(runtime)

    result = run_official_learning_step(
        session,
        behavior={
            "interaction_type": "browse_node",
            "current_node_id": "N01",
            "correctness": 1.0,
            "time_spent_ratio": 0.01,
            "code_pass_rate": 1.0,
        },
        runtime=runtime,
    )

    assert calls == []
    assert result.event_type == "browse_node"
    assert result.mastery_updated is False
    assert result.mastery_update_reason == "browse_node"
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 0.4
    assert next(log for log in result.logs if log["agent"] == "Evaluator")["status"] == "skipped"


def test_diagnostic_alias_without_server_evidence_cannot_change_mastery() -> None:
    calls: list[object] = []
    runtime = _runtime_with_evaluator(calls)
    session = _session(runtime)

    result = run_official_learning_step(
        session,
        behavior={
            "interaction_type": "diagnostic",
            "current_node_id": "N01",
            "correctness": 1.0,
            "code_pass_rate": 1.0,
        },
        runtime=runtime,
    )

    assert calls == []
    assert result.interaction_type == "diagnostic"
    assert result.event_type == "complete_learning"
    assert result.mastery_updated is False
    assert result.mastery_update_reason == "missing_completion_evidence"
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 0.4


def test_complete_learning_scores_server_quiz_not_client_correctness() -> None:
    calls: list[object] = []
    runtime = _runtime_with_evaluator(calls)
    session = _session(runtime)

    behavior = {
        "interaction_type": "complete_learning",
        "current_node_id": "N01",
        "resource_id": "N01_diagnostic_quiz_supp",
        "answers": [
            {"question_id": "N01-q1", "selected_option_index": 1},
            {"question_id": "N01-q2", "selected_option_index": 0},
        ],
        # These untrusted fields must have no effect on the evaluated score.
        "correctness": 0.0,
        "time_spent_ratio": 999.0,
        "code_pass_rate": 0.0,
    }
    result = run_official_learning_step(
        session,
        behavior=behavior,
        runtime=runtime,
    )

    assert len(calls) == 1
    assert calls[0].answer_correctness == 1.0
    assert calls[0].verified_quiz_score_only is True
    assert result.mastery_updated is True
    assert result.mastery_update_reason == "verified_diagnostic_quiz"
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 1.0
    assert session.agent_state.internal_state["verified_completion_events"][-1]["correct_count"] == 2

    replay = run_official_learning_step(session, behavior=behavior, runtime=runtime)

    assert len(calls) == 1
    assert replay.mastery_updated is False
    assert replay.mastery_update_reason == "completion_evidence_replayed"


def test_scored_low_quiz_submission_is_consumed_until_refresh() -> None:
    calls: list[object] = []
    runtime = _runtime_with_evaluator(calls)
    session = _session(runtime)
    behavior = {
        "interaction_type": "complete_learning",
        "current_node_id": "N01",
        "resource_id": "N01_diagnostic_quiz_supp",
        "answers": [
            {"question_id": "N01-q1", "selected_option_index": 0},
            {"question_id": "N01-q2", "selected_option_index": 3},
        ],
    }

    first = run_official_learning_step(session, behavior=behavior, runtime=runtime)
    replay = run_official_learning_step(session, behavior=behavior, runtime=runtime)

    assert first.mastery_updated is True
    assert first.correctness == 0.0
    assert replay.mastery_updated is False
    assert replay.mastery_update_reason == "completion_evidence_replayed"
    assert len(calls) == 1


def test_verified_evidence_can_be_accepted_without_claiming_mastery_changed() -> None:
    calls: list[object] = []
    runtime = _runtime_with_evaluator(calls)
    session = _session(runtime)

    def evaluator_without_mastery_change(inp):
        calls.append(inp.raw_behavior)
        return SimpleNamespace(
            agent_state=inp.agent_state,
            cleaned_behavior=SimpleNamespace(
                effective_correctness=inp.raw_behavior.answer_correctness,
                anomaly=SimpleNamespace(anomaly_type=SimpleNamespace(value="normal")),
            ),
            anomaly_detected=False,
            mastery_delta=0.0,
            pid_error=0.0,
            replan_decision=SimpleNamespace(value="maintain"),
            updated_mastery=0.4,
        )

    runtime.evaluator = evaluator_without_mastery_change
    result = run_official_learning_step(
        session,
        behavior={
            "interaction_type": "complete_learning",
            "current_node_id": "N01",
            "resource_id": "N01_diagnostic_quiz_supp",
            "answers": [
                {"question_id": "N01-q1", "selected_option_index": 1},
                {"question_id": "N01-q2", "selected_option_index": 0},
            ],
        },
        runtime=runtime,
    )

    assert len(calls) == 1
    assert result.evidence_accepted is True
    assert result.mastery_updated is False
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 0.4


def test_malformed_server_answer_key_cannot_be_collapsed_into_scored_evidence() -> None:
    calls: list[object] = []
    runtime = _runtime_with_evaluator(calls)
    session = _session(runtime)
    questions = session.agent_state.generated_resources["N01"][0].metadata["structured_payload"]["questions"]
    questions.append({"id": "N01-q1", "answer_index": 1})

    result = run_official_learning_step(
        session,
        behavior={
            "interaction_type": "complete_learning",
            "current_node_id": "N01",
            "resource_id": "N01_diagnostic_quiz_supp",
            "answers": [
                {"question_id": "N01-q1", "selected_option_index": 1},
                {"question_id": "N01-q2", "selected_option_index": 0},
            ],
        },
        runtime=runtime,
    )

    assert calls == []
    assert result.mastery_updated is False
    assert result.mastery_update_reason == "diagnostic_quiz_has_duplicate_question_id"
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 0.4
