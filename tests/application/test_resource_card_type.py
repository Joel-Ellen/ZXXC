from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from src.application import resource_service
from src.orchestration_core import run_official_learning_step
from src.resource_generation import TEMPLATE_NOTICE
from tests.helpers import FakeValidationPipeline, disable_persistence, install_fake_runtime
from src.infrastructure.path_planner import KnowledgeNode


def test_resource_service_generates_only_requested_card_type(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        "src.application.resource_service.get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )
    session = runtime.get_session("resource-type-user", "course1")
    session.agent_state.current_node_id = "N01"

    selected = resource_service.generate_current_node_resources(
        "resource-type-user",
        "course1",
        "N01",
        card_type="diagnostic_quiz",
    )

    assert [item["resource_type"] for item in selected["resources"]] == ["diagnostic_quiz"]
    quiz_payload = selected["resources"][0]["structured_payload"]
    assert quiz_payload["questions"]
    assert all("answer_index" not in question for question in quiz_payload["questions"])
    stored_quiz = session.agent_state.generated_resources["N01"][0]
    assert all("answer_index" in question for question in stored_quiz.metadata["questions"])
    assert {question["answer_index"] for question in stored_quiz.metadata["questions"]} != {0}

    refreshed = resource_service.generate_current_node_resources(
        "resource-type-user",
        "course1",
        "N01",
        force=True,
        card_type="diagnostic_quiz",
    )
    assert refreshed["resources"][0]["resource_id"] != selected["resources"][0]["resource_id"]
    refreshed_card = session.agent_state.generated_resources["N01"][0]
    assert refreshed_card.metadata["quiz_revision"] == 2

    all_resources = resource_service.generate_current_node_resources(
        "resource-type-user",
        "course1",
        "N01",
    )

    assert {item["resource_type"] for item in all_resources["resources"]} == {
        "concept_map",
        "code_snippet",
        "interactive_exercise",
        "video_summary",
        "diagnostic_quiz",
    }


def test_resource_service_rejects_unknown_card_type(monkeypatch) -> None:
    install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)

    result = resource_service.generate_current_node_resources(
        "resource-type-invalid",
        "course1",
        "N01",
        card_type="not-a-card",
    )

    assert result["status_code"] == 400


def test_resource_service_rejects_node_outside_server_course_catalog(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)

    class Catalog:
        @staticmethod
        def get_local_graph(course_id):
            return ([KnowledgeNode(node_id="N01", course_id=course_id, title="节点一")], [])

        @staticmethod
        def get_node_title(node_id):
            return node_id

    runtime.kg = Catalog()

    result = resource_service.request_generation(
        "invalid-node-user",
        "course1",
        "N99",
        card_types=["diagnostic_quiz"],
        submit=False,
    )

    assert result["status_code"] == 404
    assert result["node_id"] == "N99"


def test_resource_service_rejects_node_resolved_from_another_course(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)

    class CrossCourseCatalog:
        @staticmethod
        def get_node_by_id(node_id, course_id):
            return KnowledgeNode(
                node_id=node_id,
                course_id="course2",
                title="其他课程节点",
            )

        @staticmethod
        def get_node_title(node_id):
            return node_id

    runtime.kg = CrossCourseCatalog()

    result = resource_service.request_generation(
        "cross-course-node-user",
        "course1",
        "N01",
        card_types=["diagnostic_quiz"],
        submit=False,
    )

    assert result["status_code"] == 404
    assert result["node_id"] == "N01"


def test_template_only_resource_response_is_explicitly_labelled(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        "src.application.resource_service.get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )

    from src.orchestration_runtime import ResourceGenerationResult

    def template_batch(node_id, card_types, difficulty):
        return {
            card_type: ResourceGenerationResult(
                content=f"## {node_id} {card_type} deterministic fallback",
                source="template",
                fallback_reason="no_eligible_provider",
            )
            for card_type in card_types
        }

    runtime.generate_resource_contents = template_batch
    runtime.get_session("template-resource-user", "course1").agent_state.current_node_id = "N01"

    result = resource_service.generate_current_node_resources(
        "template-resource-user",
        "course1",
        "N01",
        card_type="concept_map",
    )

    assert result["generation"]["status"] == "template_fallback"
    assert result["generation"]["template_fallback_count"] == 1
    resource = result["resources"][0]
    assert resource["generation"]["source"] == "template"
    assert resource["body_markdown"].startswith(TEMPLATE_NOTICE)


def test_force_refresh_preserves_an_active_review_retest_quiz(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        "src.application.resource_service.get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )
    session = runtime.get_session("active-retest-user", "course1")
    state = session.agent_state
    state.current_node_id = "N01"

    initial = resource_service.generate_current_node_resources(
        "active-retest-user",
        "course1",
        "N01",
        card_type="diagnostic_quiz",
    )
    active_resource_id = initial["resources"][0]["resource_id"]
    state.internal_state["review_items"] = [{
        "review_item_id": "review-active",
        "node_id": "N01",
        "status": "in_progress",
        "phase": "retest",
        "retest_resource_id": active_resource_id,
    }]

    refreshed = resource_service.generate_current_node_resources(
        "active-retest-user",
        "course1",
        "N01",
        force=True,
    )
    active_card = next(
        card for card in state.generated_resources["N01"]
        if card.card_type == "diagnostic_quiz"
    )

    assert refreshed["preserved_retest_resource_id"] == active_resource_id
    assert active_card.resource_id == active_resource_id
    assert "diagnostic_quiz" not in {item["resource_type"] for item in refreshed["resources"]}

    blocked = resource_service.generate_current_node_resources(
        "active-retest-user",
        "course1",
        "N01",
        force=True,
        card_type="diagnostic_quiz",
    )
    assert blocked["status"] == "review_retest_active"
    assert blocked["status_code"] == 409


@pytest.mark.asyncio
async def test_session_resources_is_read_only_and_accepts_camel_case_card_type(monkeypatch) -> None:
    from frontend import server
    from src.auth.security import SecurityManager

    called = {}

    def fake_read(user_id, course_id, node_id, *, card_types=None):
        called.update({
            "user_id": user_id,
            "course_id": course_id,
            "node_id": node_id,
            "card_types": card_types,
        })
        return {"status": "already_exists", "node_id": node_id, "resources": []}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    monkeypatch.setattr(server.resource_service, "get_node_resources", fake_read)
    token = SecurityManager.create_token_pair("u1", "STUDENT")["access_token"]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/sessions/u1:course1/resources/N01",
            "path_params": {"session_id": "u1:course1", "node_id": "N01"},
            "query_string": b"cardType=diagnostic_quiz&force=true",
            "headers": [(b"authorization", f"Bearer {token}".encode("ascii"))],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        },
        receive,
    )

    response = await server.api_session_resources(request)

    assert response.status_code == 200
    assert called == {
        "user_id": "u1",
        "course_id": "course1",
        "node_id": "N01",
        "card_types": ["diagnostic_quiz"],
    }


@pytest.mark.asyncio
async def test_session_resource_generation_does_not_block_the_event_loop(monkeypatch) -> None:
    from frontend import server
    from src.auth.security import SecurityManager

    def slow_read(user_id, course_id, node_id, *, card_types=None):
        time.sleep(0.2)
        return {"status": "already_exists", "node_id": node_id, "resources": []}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    monkeypatch.setattr(server.resource_service, "get_node_resources", slow_read)
    token = SecurityManager.create_token_pair("u1", "STUDENT")["access_token"]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/sessions/u1:course1/resources/N01",
            "path_params": {"session_id": "u1:course1", "node_id": "N01"},
            "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode("ascii"))],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        },
        receive,
    )

    started = time.perf_counter()
    generation = asyncio.create_task(server.api_session_resources(request))
    await asyncio.sleep(0.03)

    assert time.perf_counter() - started < 0.12
    assert generation.done() is False
    response = await generation
    assert response.status_code == 200


def test_forced_quiz_refresh_allows_one_new_scored_completion(monkeypatch) -> None:
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    monkeypatch.setattr(
        "src.application.resource_service.get_validation_pipeline",
        lambda: FakeValidationPipeline(),
    )
    session = runtime.get_session("resource-retry-user", "course1")
    state = session.agent_state
    state.current_node_id = "N01"
    state.active_path = ["N01"]
    evaluator_calls = []

    def evaluator(inp):
        evaluator_calls.append(inp.raw_behavior.node_id)
        inp.agent_state.dynamic_profile.knowledge_mastery[inp.raw_behavior.node_id] = inp.raw_behavior.answer_correctness
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
            updated_mastery=inp.raw_behavior.answer_correctness,
        )

    runtime.evaluator = evaluator

    def completion_payload(card):
        return {
            "interaction_type": "complete_learning",
            "current_node_id": "N01",
            "resource_id": card.resource_id,
            "answers": [
                {"question_id": question["id"], "selected_option_index": question["answer_index"]}
                for question in card.metadata["questions"]
            ],
        }

    resource_service.generate_current_node_resources(
        "resource-retry-user",
        "course1",
        "N01",
        card_type="diagnostic_quiz",
    )
    first_card = state.generated_resources["N01"][0]
    first = run_official_learning_step(session, behavior=completion_payload(first_card), runtime=runtime)
    assert first.mastery_updated is True
    assert resource_service.drain_generation_workers(timeout_seconds=15.0)

    resource_service.generate_current_node_resources(
        "resource-retry-user",
        "course1",
        "N01",
        force=True,
        card_type="diagnostic_quiz",
    )
    refreshed_card = next(card for card in state.generated_resources["N01"] if card.card_type == "diagnostic_quiz")
    second = run_official_learning_step(session, behavior=completion_payload(refreshed_card), runtime=runtime)

    assert refreshed_card.resource_id != first_card.resource_id
    assert second.evidence_accepted is True
    assert second.mastery_updated is False
    assert evaluator_calls == ["N01", "N01"]
