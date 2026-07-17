from __future__ import annotations

from src.agents.evaluator_node import EvaluatorNode
from src.agents.profiler_node import ProfilerNode
from src.orchestration_core import run_official_learning_step
from src.state.agent_state import ResourceCard
from tests.helpers import FakeRuntime


def _session_with_real_scoring_pipeline():
    runtime = FakeRuntime()
    runtime.evaluator = EvaluatorNode()
    runtime.profiler = ProfilerNode(seed=0)
    session = runtime.get_session("evidence-user", "course1")
    state = session.agent_state
    state.current_node_id = "N01"
    state.active_path = ["N01", "N02"]
    state.generated_resources["N01"] = [
        ResourceCard(
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
        ),
        *[
            ResourceCard(
                resource_id=f"N01_{card_type}_supp",
                node_id="N01",
                card_type=card_type,
                content=card_type,
            )
            for card_type in ("concept_map", "code_snippet", "interactive_exercise", "video_summary")
        ],
    ]
    return runtime, session


def _trusted_submission(answers: list[dict[str, int]]) -> dict:
    return {
        "event_type": "review_completed",
        "node_id": "N01",
        "resource_id": "N01_diagnostic_quiz_supp",
        "result": {"answers": answers},
    }


def test_all_wrong_trusted_diagnostic_keeps_uninitialized_mastery_at_zero() -> None:
    runtime, session = _session_with_real_scoring_pipeline()

    result = run_official_learning_step(
        session,
        behavior=_trusted_submission([
            {"question_id": "N01-q1", "answer_index": 0},
            {"question_id": "N01-q2", "answer_index": 1},
        ]),
        runtime=runtime,
    )

    assert result.evidence_accepted is True
    assert result.correctness == 0.0
    assert result.previous_mastery == 0.0
    assert result.evaluated_mastery == 0.0
    assert result.mastery_updated is False
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 0.0


def test_passing_trusted_diagnostic_still_creates_evidence_based_mastery() -> None:
    runtime, session = _session_with_real_scoring_pipeline()

    result = run_official_learning_step(
        session,
        behavior=_trusted_submission([
            {"question_id": "N01-q1", "answer_index": 1},
            {"question_id": "N01-q2", "answer_index": 0},
        ]),
        runtime=runtime,
    )

    assert result.evidence_accepted is True
    assert result.correctness == 1.0
    assert 0.0 < result.evaluated_mastery <= result.correctness
    assert result.mastery_updated is True
