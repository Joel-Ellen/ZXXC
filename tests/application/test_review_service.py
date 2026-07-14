from __future__ import annotations

from types import SimpleNamespace

from starlette.testclient import TestClient

from frontend import server
from src.application import review_service, session_service
from src.auth.security import SecurityManager
from src.state.agent_state import ResourceCard
from tests.helpers import FakeRuntime, disable_persistence, install_fake_runtime


def _quiz_card(resource_id: str = "N01_diagnostic_quiz_supp") -> ResourceCard:
    return ResourceCard(
        resource_id=resource_id,
        node_id="N01",
        card_type="diagnostic_quiz",
        content="## Diagnostic quiz",
        metadata={
            "structured_payload": {
                "questions": [
                    {
                        "id": "N01-q1",
                        "prompt": "Which statement captures the core constraint?",
                        "options": ["Ignore conditions", "Respect the constraint"],
                        "answer_index": 1,
                        "explanation": "The constraint determines the valid solution.",
                        "skill_tag": "核心约束",
                    },
                    {
                        "id": "N01-q2",
                        "prompt": "Which situation is applicable?",
                        "options": ["The matching scenario", "An unrelated scenario"],
                        "answer_index": 0,
                        "explanation": "Match the known preconditions first.",
                        "skill_tag": "适用场景",
                    },
                ]
            }
        },
    )


def _resource_set() -> list[ResourceCard]:
    cards = [_quiz_card()]
    for card_type in ("concept_map", "code_snippet", "interactive_exercise", "video_summary"):
        metadata = {}
        if card_type == "interactive_exercise":
            metadata = {
                "questions": [
                    {
                        "id": "N01-targeted-practice-q1-v1",
                        "prompt": "Which practice method checks the constraint?",
                        "options": ["Ignore it", "Apply and check it"],
                        "answer_index": 1,
                    }
                ],
                "structured_payload": {
                    "questions": [
                        {
                            "id": "N01-targeted-practice-q1-v1",
                            "prompt": "Which practice method checks the constraint?",
                            "options": ["Ignore it", "Apply and check it"],
                            "answer_index": 1,
                        }
                    ]
                },
            }
        cards.append(
            ResourceCard(
                resource_id=f"N01_{card_type}_supp",
                node_id="N01",
                card_type=card_type,
                content=f"## {card_type}",
                metadata=metadata,
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
    session = runtime.get_session("review-user", "course1")
    state = session.agent_state
    state.current_node_id = "N01"
    state.active_path = ["N01", "N02"]
    state.dynamic_profile.knowledge_mastery["N01"] = 0.4
    state.generated_resources["N01"] = _resource_set()
    return session


def _event(event_id: str, resource_id: str, answers: list[dict[str, int]]) -> dict:
    return {
        "event_id": event_id,
        "event_type": "review_completed",
        "user_id": "review-user",
        "course_id": "course1",
        "node_id": "N01",
        "resource_id": resource_id,
        "question_id": "",
        "duration_ms": 1800,
        "attempt_number": 1,
        "used_hint": False,
        "result": {"answers": answers},
    }


def _submit_practice(
    review_item_id: str,
    event_id: str,
    *,
    answer_index: int = 1,
) -> dict:
    return session_service.record_learning_event(
        "review-user",
        "course1",
        {
            "event_id": event_id,
            "event_type": "answer_submitted",
            "user_id": "review-user",
            "course_id": "course1",
            "node_id": "N01",
            "resource_id": "N01_interactive_exercise_supp",
            "question_id": "N01-targeted-practice-q1-v1",
            "duration_ms": 900,
            "attempt_number": 1,
            "used_hint": False,
            "result": {
                "review_item_id": review_item_id,
                "answer_index": answer_index,
            },
        },
    )


def _wrong_answers() -> list[dict[str, int]]:
    return [
        {"question_id": "N01-q1", "selected_option_index": 0},
        {"question_id": "N01-q2", "selected_option_index": 0},
    ]


def _all_wrong_answers() -> list[dict[str, int]]:
    return [
        {"question_id": "N01-q1", "selected_option_index": 0},
        {"question_id": "N01-q2", "selected_option_index": 1},
    ]


def _correct_answers() -> list[dict[str, int]]:
    return [
        {"question_id": "N01-q1", "selected_option_index": 1},
        {"question_id": "N01-q2", "selected_option_index": 0},
    ]


def test_failed_diagnostic_creates_complete_review_snapshot_and_due_queue(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    session = _session(runtime)
    session.agent_state.dynamic_profile.diagnostic_report_md = "stale cold-start report"

    response = session_service.record_learning_event(
        "review-user",
        "course1",
        _event("failed-diagnostic", "N01_diagnostic_quiz_supp", _wrong_answers()),
    )

    assert len(calls) == 1
    assert response["evidence_accepted"] is True
    assert response["effective_correctness"] == 0.5
    assert response["review"]["requires_remediation"] is True
    review_item = response["review"]["created_or_updated_items"][0]
    assert review_item["error_type"] == "concept_understanding"
    assert review_item["original_answer"] == "Ignore conditions"
    assert review_item["correct_answer"] == "Respect the constraint"
    assert review_item["explanation"] == "The constraint determines the valid solution."
    assert review_item["related_node"] == "N01"
    assert review_item["next_review_at"]
    assert review_item["status"] == "due"
    assert any(material["resource_type"] == "interactive_exercise" for material in review_item["recommended_materials"])

    dashboard = review_service.get_review_dashboard("review-user", "course1")
    assert dashboard["today_queue"][0]["review_item_id"] == review_item["review_item_id"]
    assert dashboard["weak_nodes"][0]["node_id"] == "N01"
    assert {node["node_id"] for node in dashboard["weak_nodes"]} == {"N01"}
    assert dashboard["diagnostic_report"]["latest"]["question_results"][0]["correct"] is False
    assert "`failed-diagnostic`" in dashboard["diagnostic_report"]["markdown"]
    assert "stale cold-start report" not in dashboard["diagnostic_report"]["markdown"]
    assert session.agent_state.internal_state["review_items"][0]["source_event_id"] == "failed-diagnostic"


def test_unseen_path_nodes_are_not_reported_as_weak(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    _session(runtime)

    dashboard = review_service.get_review_dashboard("review-user", "course1")

    assert dashboard["weak_nodes"] == []


def test_mastery_below_threshold_creates_non_mistake_reinforcement_until_retest(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    session = _session(runtime)
    mastery_values = iter((0.2, 0.8))

    def evaluator(inp):
        updated_mastery = next(mastery_values)
        state = inp.agent_state
        state.dynamic_profile.knowledge_mastery[inp.raw_behavior.node_id] = updated_mastery
        return SimpleNamespace(
            agent_state=state,
            cleaned_behavior=SimpleNamespace(
                effective_correctness=inp.raw_behavior.answer_correctness,
                anomaly=SimpleNamespace(anomaly_type=SimpleNamespace(value="normal")),
            ),
            anomaly_detected=False,
            mastery_delta=updated_mastery,
            pid_error=0.0,
            replan_decision=SimpleNamespace(value="maintain"),
            updated_mastery=updated_mastery,
        )

    runtime.evaluator = evaluator
    first = session_service.record_learning_event(
        "review-user",
        "course1",
        _event("perfect-but-not-mastered", "N01_diagnostic_quiz_supp", _correct_answers()),
    )

    assert first["effective_correctness"] == 1.0
    assert first["advanced_to_next_node"] is False
    assert first["review"]["requires_remediation"] is True
    task = first["review"]["created_or_updated_items"][0]
    assert task["review_kind"] == "mastery_reinforcement"
    assert task["error_type"] == "insufficient_evidence"
    assert "2/2" in task["original_answer"]
    assert "不会计入错题本" in task["explanation"]
    assert [step["kind"] for step in first["review"]["remediation"]["steps"]] == [
        "review_material",
        "targeted_practice",
        "retest",
    ]

    dashboard = review_service.get_review_dashboard("review-user", "course1")
    assert dashboard["mistakes"] == []
    assert dashboard["today_queue"][0]["review_item_id"] == task["review_item_id"]
    assert dashboard["reinforcement_tasks"][0]["review_item_id"] == task["review_item_id"]

    started = review_service.start_review_item("review-user", "course1", task["review_item_id"])
    assert started["status"] == "ok"
    assert started["learning_task"]["review_kind"] == "mastery_reinforcement"

    def issue_fresh_quiz(user_id, course_id, node_id, force=False, include_legacy=False, card_type=None):
        assert (user_id, course_id, node_id, force, card_type) == (
            "review-user",
            "course1",
            "N01",
            True,
            "diagnostic_quiz",
        )
        state = runtime.get_session(user_id, course_id).agent_state
        state.generated_resources[node_id] = [
            card for card in state.generated_resources[node_id] if card.card_type != "diagnostic_quiz"
        ] + [_quiz_card("N01_diagnostic_quiz_supp_r2")]
        return {"status": "generated", "node_id": node_id}

    monkeypatch.setattr("src.application.resource_service.generate_current_node_resources", issue_fresh_quiz)
    practice = _submit_practice(task["review_item_id"], "reinforcement-practice")
    assert practice["practice_verification"]["correct"] is True
    prepared = review_service.prepare_review_retest(
        "review-user",
        "course1",
        task["review_item_id"],
        practice["event_id"],
    )
    assert prepared["status"] == "ok"

    retested = session_service.record_learning_event(
        "review-user",
        "course1",
        _event("mastery-reinforcement-retest", "N01_diagnostic_quiz_supp_r2", _correct_answers()),
    )

    completed = next(
        item
        for item in retested["review"]["retested_items"]
        if item["review_item_id"] == task["review_item_id"]
    )
    assert completed["status"] == "completed"
    assert completed["last_result"]["mastery_after"] == 0.8
    dashboard = review_service.get_review_dashboard("review-user", "course1")
    assert dashboard["today_queue"] == []
    assert dashboard["reinforcement_tasks"][0]["status"] == "completed"
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 0.8


def test_lesson_completed_and_legacy_diagnostic_events_create_review_items(monkeypatch) -> None:
    disable_persistence(monkeypatch)
    for event_id, legacy in (("lesson-completed", False), ("legacy-diagnostic", True)):
        runtime = install_fake_runtime(monkeypatch)
        calls: list[object] = []
        _install_evaluator(runtime, calls)
        _session(runtime)
        payload = _event(event_id, "N01_diagnostic_quiz_supp", _wrong_answers())
        if legacy:
            payload.pop("event_type")
            payload["interaction_type"] = "diagnostic"
        else:
            payload["event_type"] = "lesson_completed"

        response = (
            session_service.advance_session("review-user", "course1", behavior=payload)
            if legacy
            else session_service.record_learning_event("review-user", "course1", payload)
        )

        assert len(calls) == 1
        assert response["event_type"] == "lesson_completed"
        assert response["review"]["requires_remediation"] is True
        assert response["review"]["created_or_updated_items"][0]["source_event_id"] == event_id


def test_fresh_retest_is_required_to_close_review_item_and_uses_verified_evidence(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    session = _session(runtime)
    failed = session_service.record_learning_event(
        "review-user",
        "course1",
        _event("failed-diagnostic", "N01_diagnostic_quiz_supp", _wrong_answers()),
    )
    review_item_id = failed["review"]["created_or_updated_items"][0]["review_item_id"]

    started = review_service.start_review_item("review-user", "course1", review_item_id)
    assert started["status"] == "ok"
    assert started["review_item"]["status"] == "in_progress"
    assert started["learning_task"]["focus_resource_type"] == "interactive_exercise"

    missing_practice = review_service.prepare_review_retest(
        "review-user",
        "course1",
        review_item_id,
    )
    assert missing_practice["status"] == "targeted_practice_evidence_required"
    wrong_practice = _submit_practice(
        review_item_id,
        "wrong-directed-practice",
        answer_index=0,
    )
    assert wrong_practice["practice_verification"] == {
        "verified": True,
        "correct": False,
        "reason": "verified_targeted_practice_incorrect",
        "review_item_id": review_item_id,
        "resource_id": "N01_interactive_exercise_supp",
        "question_id": "N01-targeted-practice-q1-v1",
        "selected_index": 0,
        "attempt_number": 1,
    }
    rejected_practice = review_service.prepare_review_retest(
        "review-user",
        "course1",
        review_item_id,
        wrong_practice["event_id"],
    )
    assert rejected_practice["status"] == "targeted_practice_answer_incorrect"
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 0.5

    generation_calls: list[str] = []

    def issue_fresh_quiz(user_id, course_id, node_id, force=False, include_legacy=False, card_type=None):
        assert (user_id, course_id, node_id, force, card_type) == ("review-user", "course1", "N01", True, "diagnostic_quiz")
        generation_calls.append(node_id)
        state = runtime.get_session(user_id, course_id).agent_state
        state.generated_resources[node_id] = [
            card for card in state.generated_resources[node_id] if card.card_type != "diagnostic_quiz"
        ] + [_quiz_card("N01_diagnostic_quiz_supp_r2")]
        return {"status": "generated", "node_id": node_id}

    monkeypatch.setattr("src.application.resource_service.generate_current_node_resources", issue_fresh_quiz)
    practice = _submit_practice(review_item_id, "directed-practice")
    retest = review_service.prepare_review_retest(
        "review-user",
        "course1",
        review_item_id,
        practice["event_id"],
    )
    assert retest["status"] == "ok"
    assert retest["review_item"]["phase"] == "retest"
    assert retest["learning_task"]["retest_resource_id"] == "N01_diagnostic_quiz_supp_r2"
    repeated = review_service.prepare_review_retest(
        "review-user",
        "course1",
        review_item_id,
        practice["event_id"],
    )
    assert repeated["status"] == "ok"
    assert repeated["idempotent"] is True
    assert generation_calls == ["N01"]
    resumed = review_service.start_review_item("review-user", "course1", review_item_id)
    assert resumed["learning_task"]["phase"] == "retest"
    assert resumed["learning_task"]["retest_resource_id"] == "N01_diagnostic_quiz_supp_r2"

    completed = session_service.record_learning_event(
        "review-user",
        "course1",
        _event("verified-retest", "N01_diagnostic_quiz_supp_r2", _correct_answers()),
    )

    assert len(calls) == 2
    assert completed["mastery_updated"] is True
    assert completed["review"]["retested_items"][0]["review_item_id"] == review_item_id
    assert completed["review"]["retested_items"][0]["status"] == "completed"
    dashboard = review_service.get_review_dashboard("review-user", "course1")
    item = next(item for item in dashboard["mistakes"] if item["review_item_id"] == review_item_id)
    assert item["status"] == "completed"
    assert item["completed_at"]
    assert not dashboard["today_queue"]
    assert session.agent_state.dynamic_profile.knowledge_mastery["N01"] == 1.0


def test_failed_retest_returns_item_to_material_review_with_clear_remediation(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    _session(runtime)
    failed = session_service.record_learning_event(
        "review-user",
        "course1",
        _event("failed-diagnostic", "N01_diagnostic_quiz_supp", _wrong_answers()),
    )
    review_item_id = failed["review"]["created_or_updated_items"][0]["review_item_id"]
    assert review_service.start_review_item("review-user", "course1", review_item_id)["status"] == "ok"

    def issue_fresh_quiz(user_id, course_id, node_id, force=False, include_legacy=False, card_type=None):
        state = runtime.get_session(user_id, course_id).agent_state
        state.generated_resources[node_id] = [
            card for card in state.generated_resources[node_id] if card.card_type != "diagnostic_quiz"
        ] + [_quiz_card("N01_diagnostic_quiz_supp_r2")]
        return {"status": "generated", "node_id": node_id}

    monkeypatch.setattr("src.application.resource_service.generate_current_node_resources", issue_fresh_quiz)
    practice = _submit_practice(review_item_id, "practice-before-failed-retest")
    assert review_service.prepare_review_retest(
        "review-user",
        "course1",
        review_item_id,
        practice["event_id"],
    )["status"] == "ok"

    failed_retest = session_service.record_learning_event(
        "review-user",
        "course1",
        _event("failed-retest", "N01_diagnostic_quiz_supp_r2", _wrong_answers()),
    )

    review = failed_retest["review"]
    item = next(
        candidate
        for candidate in review["retested_items"]
        if candidate["review_item_id"] == review_item_id
    )
    assert item["status"] == "due"
    assert item["phase"] == "material_review"
    assert item["retest_attempt_count"] == 1
    assert review["requires_remediation"] is True
    assert [step["kind"] for step in review["remediation"]["steps"]] == [
        "review_material",
        "targeted_practice",
        "retest",
    ]


def test_second_same_node_retest_is_rejected_while_first_is_active(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    calls: list[object] = []
    _install_evaluator(runtime, calls)
    _session(runtime)
    failed = session_service.record_learning_event(
        "review-user",
        "course1",
        _event("two-failed-diagnostics", "N01_diagnostic_quiz_supp", _all_wrong_answers()),
    )
    review_item_ids = [
        item["review_item_id"]
        for item in failed["review"]["created_or_updated_items"]
    ]
    assert len(review_item_ids) == 2

    skipped_phase = review_service.prepare_review_retest(
        "review-user",
        "course1",
        review_item_ids[0],
    )
    assert skipped_phase["status"] == "review_material_phase_required"
    assert skipped_phase["status_code"] == 409
    assert review_service.start_review_item("review-user", "course1", review_item_ids[0])["status"] == "ok"
    assert review_service.start_review_item("review-user", "course1", review_item_ids[1])["status"] == "ok"

    def issue_fresh_quiz(user_id, course_id, node_id, force=False, include_legacy=False, card_type=None):
        state = runtime.get_session(user_id, course_id).agent_state
        state.generated_resources[node_id] = [
            card for card in state.generated_resources[node_id] if card.card_type != "diagnostic_quiz"
        ] + [_quiz_card("N01_diagnostic_quiz_supp_r2")]
        return {"status": "generated", "node_id": node_id}

    monkeypatch.setattr("src.application.resource_service.generate_current_node_resources", issue_fresh_quiz)
    first_practice = _submit_practice(review_item_ids[0], "first-item-practice")
    second_practice = _submit_practice(review_item_ids[1], "second-item-practice")
    first = review_service.prepare_review_retest(
        "review-user",
        "course1",
        review_item_ids[0],
        first_practice["event_id"],
    )
    assert first["status"] == "ok"
    assert first["review_item"]["phase"] == "retest"

    blocked = review_service.prepare_review_retest(
        "review-user",
        "course1",
        review_item_ids[1],
        second_practice["event_id"],
    )
    assert blocked["status"] == "review_retest_already_in_progress"
    assert blocked["status_code"] == 409
    assert blocked["blocking_review_item_id"] == review_item_ids[0]
    current_quiz = next(
        card
        for card in runtime.get_session("review-user", "course1").agent_state.generated_resources["N01"]
        if card.card_type == "diagnostic_quiz"
    )
    assert current_quiz.resource_id == "N01_diagnostic_quiz_supp_r2"


def _auth_headers(user_id: str = "review-user") -> dict[str, str]:
    token = SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_review_routes_require_session_owner_and_forward_service_results(monkeypatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(
        server.review_service,
        "get_review_dashboard",
        lambda user_id, course_id: calls.append(("dashboard", user_id, course_id)) or {"status": "ok", "today_queue": []},
    )
    monkeypatch.setattr(
        server.review_service,
        "start_review_item",
        lambda user_id, course_id, item_id: calls.append(("start", user_id, course_id, item_id)) or {"status": "ok", "learning_task": {"node_id": "N01"}},
    )
    monkeypatch.setattr(
        server.review_service,
        "prepare_review_retest",
        lambda user_id, course_id, item_id, practice_event_id: calls.append(
            ("retest", user_id, course_id, item_id, practice_event_id)
        ) or {"status": "ok", "learning_task": {"node_id": "N01"}},
    )
    client = TestClient(server.app)
    path = "/api/sessions/review-user%3Acourse1/review"

    unauthenticated = client.get(path)
    other_user = client.get(path, headers=_auth_headers("other-user"))
    dashboard = client.get(path, headers=_auth_headers())
    started = client.post(f"{path}/items/review-1/start", headers=_auth_headers())
    retest = client.post(
        f"{path}/items/review-1/prepare-retest",
        headers=_auth_headers(),
        json={"practice_event_id": "practice-1"},
    )

    assert unauthenticated.status_code == 401
    assert other_user.status_code == 403
    assert dashboard.status_code == 200
    assert started.status_code == 200
    assert retest.status_code == 200
    assert calls == [
        ("dashboard", "review-user", "course1"),
        ("start", "review-user", "course1", "review-1"),
        ("retest", "review-user", "course1", "review-1", "practice-1"),
    ]
