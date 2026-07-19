from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application import resource_service
from src.application import review_service as service
from src.state.agent_state import AgentState


def _session_with_review_item(
    item: dict[str, object],
    *,
    learning_events: list[dict[str, object]] | None = None,
) -> SimpleNamespace:
    state = AgentState(user_id="review-user", course_id="course1")
    state.internal_state[service.REVIEW_ITEMS_KEY] = [item]
    if learning_events is not None:
        state.internal_state["learning_events"] = learning_events
    return SimpleNamespace(agent_state=state)


def test_delete_review_item_removes_persisted_record(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session_with_review_item({
        "review_item_id": "review-delete-1",
        "review_kind": "diagnostic_quiz",
        "node_id": "N01",
        "status": "due",
    })
    persisted: list[object] = []
    monkeypatch.setattr(service, "get_session", lambda _user_id, _course_id: session)
    monkeypatch.setattr(service, "persist_session", persisted.append)

    result = service.delete_review_item("review-user", "course1", "review-delete-1")

    assert result == {"status": "deleted", "review_item_id": "review-delete-1"}
    assert session.agent_state.internal_state[service.REVIEW_ITEMS_KEY] == []
    assert persisted == [session]


def test_code_review_copy_is_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    state = AgentState(user_id="review-user", course_id="course1")
    monkeypatch.setattr(service, "get_node_title", lambda node_id, _default=None: node_id)

    result = service.record_verified_code_submission(
        state,
        event_id="event-1",
        node_id="N01",
        resource_id="practice-1",
        evidence={
            "submission_id": "submission-1",
            "problem_id": "ds-list-sum",
            "problem_version": 1,
            "verdict": "wrong_answer",
            "summary": {
                "public_passed": 1,
                "public_total": 2,
                "hidden_passed": 0,
                "hidden_total": 2,
            },
        },
        receipt_accepted=False,
    )

    review_item = result["created_or_updated_items"][0]
    assert review_item["question_prompt"] == "代码练习：ds-list-sum"
    assert review_item["original_answer"] == "本次提交的源代码未保存。"
    assert review_item["targeted_practice"]["label"] == "代码练习"
    assert review_item["recommended_materials"][0]["label"] == "代码练习"


@pytest.mark.parametrize(
    ("generation_result", "expected_detail"),
    [
        (
            {"status": "failed", "status_code": 503},
            "暂时无法准备定向练习，请稍后重试。",
        ),
        (
            {"status": "generated"},
            "定向练习资源缺少可验证的题目，请稍后重试。",
        ),
    ],
)
def test_start_review_failure_detail_is_chinese(
    monkeypatch: pytest.MonkeyPatch,
    generation_result: dict[str, object],
    expected_detail: str,
) -> None:
    session = _session_with_review_item({
        "review_item_id": "review-1",
        "review_kind": "diagnostic_quiz",
        "node_id": "N01",
        "status": "due",
        "phase": "material_review",
    })
    monkeypatch.setattr(service, "get_session", lambda _user_id, _course_id: session)
    monkeypatch.setattr(
        resource_service,
        "generate_current_node_resources",
        lambda *_args, **_kwargs: generation_result,
    )

    result = service.start_review_item("review-user", "course1", "review-1")

    assert result["status"] == "targeted_practice_unavailable"
    assert result["detail"] == expected_detail


def test_retest_generation_failure_detail_is_chinese(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_with_review_item(
        {
            "review_item_id": "review-1",
            "review_kind": "diagnostic_quiz",
            "node_id": "N01",
            "status": "in_progress",
            "phase": "material_review",
            "targeted_practice": {"resource_id": "exercise-1"},
            "started_at": "2026-01-01T00:00:00+00:00",
        },
        learning_events=[{
            "event_id": "practice-event-1",
            "event_type": "answer_submitted",
            "node_id": "N01",
            "resource_id": "exercise-1",
            "received_at": "2026-01-01T00:01:00+00:00",
            "practice_verification": {
                "verified": True,
                "correct": True,
                "review_item_id": "review-1",
            },
        }],
    )
    monkeypatch.setattr(service, "get_session", lambda _user_id, _course_id: session)
    monkeypatch.setattr(
        resource_service,
        "generate_current_node_resources",
        lambda *_args, **_kwargs: {"status": "failed", "status_code": 503},
    )

    result = service.prepare_review_retest(
        "review-user",
        "course1",
        "review-1",
        "practice-event-1",
    )

    assert result["status"] == "review_retest_generation_failed"
    assert result["detail"] == "暂时无法准备新的复测，请稍后重试。"
