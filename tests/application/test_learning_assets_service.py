from __future__ import annotations

from starlette.testclient import TestClient

from frontend import server
from src.application import learning_assets_service
from src.auth.security import SecurityManager
from tests.helpers import install_fake_runtime


def _auth_headers(user_id: str = "asset-user") -> dict[str, str]:
    token = SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _runtime(monkeypatch):
    runtime = install_fake_runtime(monkeypatch)
    monkeypatch.setattr(learning_assets_service, "persist_session", lambda session: None)
    return runtime


def _verified_diagnostic(state) -> None:
    state.internal_state["verified_completion_events"] = [{
        "event_id": "diagnostic-verified-1",
        "node_id": "N01",
        "resource_id": "quiz-1",
        "question_count": 2,
        "correct_count": 1,
        "correctness": 0.5,
        "question_results": [{"question_id": "q1", "answer": "never expose this"}],
        "received_at": "2026-07-12T08:00:00+00:00",
    }]


def test_upserts_all_restore_categories_with_bounded_normalized_values(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    state = runtime.get_session("asset-user", "course-a").agent_state
    _verified_diagnostic(state)
    state.current_node_id = "N01"
    learning_assets_service.record_tutor_exchange_asset(
        state,
        question="Why does this work?",
        response={"text_explanation": "The invariant remains true after each operation."},
    )
    learning_assets_service.record_learning_event_asset(state, {
        "event_id": "diagnostic-verified-1",
        "event_type": "lesson_completed",
        "node_id": "N01",
        "resource_id": "quiz-1",
        "received_at": "2026-07-12T08:00:00+00:00",
        "verified_evidence": {"question_results": [{"question_id": "q1"}]},
    })

    payloads = {
        "drafts": ("draft-1", {
            "node_id": "N01",
            "content": "unfinished tutor input",
            "kind": "tutor_input",
            "context_type": "code_debug",
            "code_snippet": "def pop(items):\n    return items.pop()",
            "error_message": "IndexError: pop from empty list",
        }),
        "code_drafts": ("code-1", {
            "node_id": "N01",
            "resource_id": "exercise-1",
            "problem_id": "exercise-1",
            "version": "v2",
            "language": "python",
            "code": "print('ok')",
            "run_attempts": 3,
            "submit_attempts": 1,
        }),
        "quiz_progress": ("quiz-1", {
            "node_id": "N01",
            "resource_id": "quiz-1",
            "answers": {"q1": 2},
            "attempt_number": 2,
            "used_hint": True,
            "submitted_question_ids": ["q1"],
        }),
        "annotations": ("note-1", {"node_id": "N01", "resource_id": "concept-1", "kind": "note", "content": "Remember the invariant."}),
        "bookmarks": ("favorite-1", {"node_id": "N01", "resource_id": "concept-1", "title": "Useful explanation", "favorite": True}),
        "scroll_positions": ("scroll-1", {"node_id": "N01", "resource_id": "concept-1", "top": 138.5}),
        "card_state": ("card-1", {"node_id": "N01", "resource_id": "concept-1", "card_id": "concept-1", "expanded": True}),
    }

    revision = 0
    for category, (key, value) in payloads.items():
        response = learning_assets_service.patch_learning_asset(
            "asset-user",
            "course-a",
            category=category,
            key=key,
            value=value,
        )
        assert response["status"] == "ok"
        assert response["operation"] == "upsert"
        assert response["revision"] > revision
        revision = response["revision"]

    assets = learning_assets_service.get_learning_assets("asset-user", "course-a")
    assert set(assets["assets"]) == set(learning_assets_service.ASSET_CATEGORIES)
    for category in learning_assets_service.ASSET_CATEGORIES:
        assert assets["assets"][category]
    latest = assets["assets"]["latest_diagnostic"]["latest"]
    assert latest["event_id"] == "diagnostic-verified-1"
    assert latest["correctness"] == 0.5
    assert "question_results" not in latest
    assert "answer" not in latest
    assert assets["assets"]["annotations"]["note-1"]["kind"] == "note"
    assert assets["assets"]["scroll_positions"]["scroll-1"]["top"] == 138.5
    restored_draft = assets["assets"]["drafts"]["draft-1"]
    assert restored_draft["context_type"] == "code_debug"
    assert restored_draft["code_snippet"].startswith("def pop")
    assert restored_draft["error_message"].startswith("IndexError")
    restored_code_draft = assets["assets"]["code_drafts"]["code-1"]
    assert restored_code_draft["version"] == "v2"
    assert restored_code_draft["run_attempts"] == 3
    assert restored_code_draft["submit_attempts"] == 1
    assert assets["assets"]["quiz_progress"]["quiz-1"]["submitted_question_ids"] == ["q1"]


def test_assets_are_isolated_by_user_course_scope_and_support_scoped_get_delete(monkeypatch) -> None:
    _runtime(monkeypatch)
    saved = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="notes",  # Alias is normalized to annotations.
        key="note-n01",
        value={"node_id": "N01", "content": "N01 note"},
    )
    assert saved["category"] == "annotations"
    learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="annotations",
        key="note-n02",
        value={"node_id": "N02", "content": "N02 note"},
    )

    same_scope = learning_assets_service.get_learning_assets(
        "asset-user", "course-a", node_id="N01", categories=["annotations"]
    )
    assert set(same_scope["assets"]["annotations"]) == {"note-n01"}

    other_course = learning_assets_service.get_learning_assets("asset-user", "course-b")
    other_user = learning_assets_service.get_learning_assets("another-user", "course-a")
    assert other_course["assets"]["annotations"] == {}
    assert other_user["assets"]["annotations"] == {}

    deleted = learning_assets_service.patch_learning_asset(
        "asset-user", "course-a", category="annotations", key="note-n01", delete=True
    )
    assert deleted["deleted"] is True
    assert "note-n01" not in deleted["assets"]["annotations"]


def test_asset_patch_uses_base_revision_to_rebase_without_losing_unrelated_assets(monkeypatch) -> None:
    _runtime(monkeypatch)
    first = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="drafts",
        key="draft-1",
        value={"node_id": "N01", "content": "first device"},
        base_revision=0,
    )
    stale = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="bookmarks",
        key="bookmark-1",
        value={"node_id": "N01", "resource_id": "concept-1", "favorite": True},
        base_revision=0,
    )

    assert first["revision"] == 1
    assert stale["status"] == "asset_conflict"
    assert stale["status_code"] == 409
    assert stale["reason"] == "asset_revision_conflict"
    assert stale["assets"]["drafts"]["draft-1"]["content"] == "first device"
    assert stale["assets"]["bookmarks"] == {}

    rebased = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="bookmarks",
        key="bookmark-1",
        value={"node_id": "N01", "resource_id": "concept-1", "favorite": True},
        base_revision=stale["revision"],
    )
    invalid_revision = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="bookmarks",
        key="bookmark-2",
        value={"node_id": "N01", "resource_id": "concept-2", "favorite": True},
        base_revision="1.5",
    )

    assert rebased["revision"] == 2
    assert set(rebased["assets"]["drafts"]) == {"draft-1"}
    assert set(rebased["assets"]["bookmarks"]) == {"bookmark-1"}
    assert invalid_revision["status_code"] == 422
    assert invalid_revision["reason"] == "asset_base_revision_invalid"


def test_asset_patch_rolls_back_when_all_durable_writes_fail(monkeypatch) -> None:
    _runtime(monkeypatch)
    monkeypatch.setattr(
        learning_assets_service,
        "persist_session",
        lambda _session: {
            "durable": False,
            "attempted": ["state", "snapshot"],
            "succeeded": [],
            "failed": ["state", "snapshot"],
        },
    )

    failed = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="drafts",
        key="tutor:N01",
        value={"node_id": "N01", "content": "must not be acknowledged"},
        base_revision=0,
    )
    restored = learning_assets_service.get_learning_assets("asset-user", "course-a")

    assert failed == {
        "status": "asset_persistence_failed",
        "status_code": 503,
        "reason": "asset_persistence_failed",
        "retryable": True,
        "revision": 0,
    }
    assert restored["revision"] == 0
    assert restored["assets"]["drafts"] == {}


def test_server_derived_categories_cannot_be_forged_or_replaced_by_the_browser(monkeypatch) -> None:
    _runtime(monkeypatch)
    tutor = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="tutor_history",
        key="__all__",
        value=[
            {"id": "turn-1", "node_id": "N01", "role": "user", "content": "Question"},
            {"id": "turn-2", "node_id": "N01", "role": "assistant", "content": "Answer"},
        ],
    )

    recent = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="recent_learning",
        key="__all__",
        value=[
            {"id": "recent-1", "node_id": "N01", "event_type": "lesson_opened"},
            {"id": "recent-2", "node_id": "N02", "event_type": "content_viewed", "duration_ms": 700},
        ],
    )

    diagnostic = learning_assets_service.patch_learning_asset(
        "asset-user", "course-a", category="latest_diagnostic", key="latest", delete=True
    )

    for result in (tutor, recent, diagnostic):
        assert result["status_code"] == 403
        assert result["reason"] == "asset_category_server_managed"


def test_sensitive_and_unverified_client_values_are_rejected_without_state_mutation(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    state = runtime.get_session("asset-user", "course-a").agent_state

    secret = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="drafts",
        key="draft-1",
        value={"node_id": "N01", "content": "sk-secretvalue123456789"},
    )
    forged_quiz = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="quiz_progress",
        key="quiz-1",
        value={"node_id": "N01", "answers": {"q1": 1}, "score": 1.0},
    )
    invalid_diagnostic = learning_assets_service.patch_learning_asset(
        "asset-user",
        "course-a",
        category="latest_diagnostic",
        key="latest",
        value={"event_id": "not-a-server-event"},
    )

    assert secret["status_code"] == 422
    assert secret["reason"] == "asset_sensitive_value_forbidden"
    assert forged_quiz["reason"] == "quiz_progress_server_result_forbidden"
    assert invalid_diagnostic["status_code"] == 403
    assert invalid_diagnostic["reason"] == "asset_category_server_managed"
    assert state.internal_state.get(learning_assets_service.LEARNING_ASSETS_KEY, {}).get("categories", {}).get("drafts", {}) == {}


def test_existing_verified_diagnostic_is_derived_on_read_and_remains_server_managed(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    state = runtime.get_session("asset-user", "course-a").agent_state
    _verified_diagnostic(state)

    derived = learning_assets_service.get_learning_assets(
        "asset-user", "course-a", categories=["latest_diagnostic"]
    )
    assert derived["assets"]["latest_diagnostic"]["latest"]["event_id"] == "diagnostic-verified-1"

    deleted = learning_assets_service.patch_learning_asset(
        "asset-user", "course-a", category="latest_diagnostic", key="latest", delete=True
    )
    assert deleted["status_code"] == 403
    assert deleted["reason"] == "asset_category_server_managed"

    restored = learning_assets_service.get_learning_assets(
        "asset-user", "course-a", categories=["latest_diagnostic"]
    )
    assert restored["assets"]["latest_diagnostic"]["latest"]["event_id"] == "diagnostic-verified-1"


def test_server_recorded_events_and_tutor_exchanges_have_non_scoring_assets(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    state = runtime.get_session("asset-user", "course-a").agent_state
    state.current_node_id = "N01"
    _verified_diagnostic(state)
    event_record = {
        "event_id": "diagnostic-verified-1",
        "event_type": "lesson_completed",
        "node_id": "N01",
        "resource_id": "quiz-1",
        "duration_ms": 1_200,
        "received_at": "2026-07-12T08:00:00+00:00",
        "verified_evidence": {"question_results": [{"question_id": "q1"}]},
        "mastery": {"updated": True, "after": 0.9},
    }
    learning_assets_service.record_learning_event_asset(state, event_record)
    learning_assets_service.record_tutor_exchange_asset(
        state,
        question="Can you explain the invariant?",
        response={"text_explanation": "Keep it true before and after every operation."},
        context_type="concept",
    )

    assets = learning_assets_service.get_learning_assets("asset-user", "course-a")
    recent = assets["assets"]["recent_learning"]["diagnostic-verified-1"]
    assert recent["source"] == "server_event"
    assert "mastery" not in recent
    assert assets["assets"]["latest_diagnostic"]["latest"]["source"] == "server_verified_diagnostic"
    assert len(assets["asset_lists"]["tutor_history"]) == 2


def test_asset_http_routes_require_owner_and_return_normalized_assets(monkeypatch) -> None:
    _runtime(monkeypatch)
    client = TestClient(server.app)
    path = "/api/sessions/asset-user%3Acourse-a/assets"

    unauthenticated = client.get(path)
    other_user = client.get(path, headers=_auth_headers("other-user"))
    patched = client.patch(
        path,
        headers=_auth_headers(),
        json={
            "category": "card_state",
            "key": "card-n01",
            "value": {"node_id": "N01", "card_id": "card-n01", "expanded": True},
            "base_revision": 0,
        },
    )
    stale = client.patch(
        path,
        headers=_auth_headers(),
        json={
            "category": "card_state",
            "key": "card-n02",
            "value": {"node_id": "N01", "card_id": "card-n02", "expanded": True},
            "baseRevision": 0,
        },
    )
    restored = client.get(f"{path}?node_id=N01&category=card_state", headers=_auth_headers())

    assert unauthenticated.status_code == 401
    assert other_user.status_code == 403
    assert patched.status_code == 200
    assert patched.json()["revision"] == 1
    assert stale.status_code == 409
    assert stale.json()["reason"] == "asset_revision_conflict"
    assert restored.status_code == 200
    assert restored.json()["assets"]["card_state"]["card-n01"]["expanded"] is True


def test_asset_read_repairs_legacy_state_and_skips_mixed_or_malformed_entries(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    state = runtime.get_session("asset-user", "course-a").agent_state
    state.internal_state = {
        learning_assets_service.LEARNING_ASSETS_KEY: {
            "revision": "legacy",
            "categories": {
                "annotations": {
                    7: {"node_id": "N01", "content": "integer key"},
                    "note-valid": {"node_id": "N01", "content": "durable note"},
                    "broken": ["not", "an", "asset"],
                },
            },
        },
    }

    response = learning_assets_service.get_learning_assets("asset-user", "course-a")

    assert response["status"] == "ok"
    assert response["revision"] == 0
    assert response["assets"]["annotations"] == {
        "note-valid": {"node_id": "N01", "content": "durable note"},
    }

    # A severely malformed old state is also repaired into an empty asset bag.
    state.internal_state = []
    repaired = learning_assets_service.get_learning_assets("asset-user", "course-a")
    assert repaired["status"] == "ok"
    assert isinstance(state.internal_state, dict)
    assert repaired["assets"]["drafts"] == {}


def test_colon_bearing_unmatched_api_path_returns_404_not_static_files_500(monkeypatch) -> None:
    _runtime(monkeypatch)
    client = TestClient(server.app)

    response = client.get("/api/missing%3Alegacy/assets", headers=_auth_headers())

    assert response.status_code == 404
