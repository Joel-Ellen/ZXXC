import os
import sys
import types
import uuid

from starlette.testclient import TestClient
from src.auth.security import SecurityManager


def _install_import_stubs() -> None:
    if "loguru" not in sys.modules:
        loguru_module = types.ModuleType("loguru")

        class _Logger:
            def __getattr__(self, _name):
                return lambda *args, **kwargs: None

        loguru_module.logger = _Logger()
        sys.modules["loguru"] = loguru_module

    if "openai" not in sys.modules:
        openai_module = types.ModuleType("openai")

        class _DummyOpenAI:
            def __init__(self, *args, **kwargs):
                pass

        openai_module.OpenAI = _DummyOpenAI
        openai_module.AsyncOpenAI = _DummyOpenAI
        sys.modules["openai"] = openai_module


os.environ["DASHSCOPE_API_KEY"] = ""
_install_import_stubs()

from frontend.server import (  # noqa: E402
    MASTERY_ADVANCE_THRESHOLD,
    RESOURCE_CARD_ORDER,
    RESOURCE_CONTRACT_VERSION,
    app,
    sessions,
)
from src.application._common import get_session  # noqa: E402


def _new_identity() -> tuple[str, str]:
    return f"workspace-contract-{uuid.uuid4().hex}", "data_structures"


def _client() -> TestClient:
    return TestClient(app)


def _init_workspace(client: TestClient, user_id: str, course_id: str) -> str:
    sessions.pop(user_id, None)
    init_response = client.post("/api/init-path", json={"user_id": user_id, "course_id": course_id})
    assert init_response.status_code == 200

    state_response = client.get("/api/state", params={"user_id": user_id, "course_id": course_id})
    assert state_response.status_code == 200
    state = state_response.json()
    return state["current_node_id"] or state["active_path"][0]


def _load_node(client: TestClient, user_id: str, course_id: str, node_id: str) -> dict:
    response = client.post(
        "/api/pipeline/step",
        json={
            "user_id": user_id,
            "course_id": course_id,
            "current_node_id": node_id,
            "interaction_type": "load_node",
        },
    )
    assert response.status_code == 200
    resources_response = client.get(
        f"/api/sessions/{user_id}:{course_id}/resources/{node_id}",
        headers={
            "Authorization": "Bearer " + SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
        },
    )
    assert resources_response.status_code == 200
    return response.json()


def _fetch_state(client: TestClient, user_id: str, course_id: str) -> dict:
    response = client.get("/api/state", params={"user_id": user_id, "course_id": course_id})
    assert response.status_code == 200
    return response.json()


def _cards_for_node(state: dict, node_id: str) -> list[dict]:
    return state["generated_resources"].get(node_id, [])


def _quiz_submission(user_id: str, course_id: str, node_id: str, *, correct: bool) -> dict:
    session = get_session(user_id, course_id)
    quiz_card = next(
        card
        for card in session.agent_state.generated_resources[node_id]
        if card.card_type == "diagnostic_quiz"
    )
    answers = []
    for question in quiz_card.metadata["questions"]:
        answer_index = question["answer_index"]
        selected_option_index = answer_index if correct else (answer_index + 1) % len(question["options"])
        answers.append({
            "question_id": question["id"],
            "selected_option_index": selected_option_index,
        })
    return {"resource_id": quiz_card.resource_id, "answers": answers}


def test_load_node_returns_current_node_resource_contract() -> None:
    client = _client()
    user_id, course_id = _new_identity()
    node_id = _init_workspace(client, user_id, course_id)

    step_payload = _load_node(client, user_id, course_id, node_id)
    state = _fetch_state(client, user_id, course_id)
    cards = _cards_for_node(state, node_id)

    assert step_payload["resource_contract_version"] == RESOURCE_CONTRACT_VERSION
    assert step_payload["interaction_type"] == "load_node"
    assert step_payload["current_node_id"] == node_id
    assert step_payload["advanced_to_next_node"] is False

    assert state["resource_contract_version"] == RESOURCE_CONTRACT_VERSION
    assert [card["card_type"] for card in cards] == RESOURCE_CARD_ORDER
    assert len(cards) == len(RESOURCE_CARD_ORDER)
    assert len({card["card_type"] for card in cards}) == len(RESOURCE_CARD_ORDER)

    for card in cards:
        metadata = card["metadata"]
        assert metadata["render_type"] == card["card_type"]

    metadata_by_type = {card["card_type"]: card["metadata"] for card in cards}
    assert all(metadata_by_type[card_type]["title"] for card_type in RESOURCE_CARD_ORDER)
    assert {"title", "questions", "pass_threshold"} <= metadata_by_type["diagnostic_quiz"].keys()
    assert all(
        "answer_index" not in question
        for question in metadata_by_type["diagnostic_quiz"]["questions"]
    )


def test_repeated_load_node_does_not_duplicate_cards() -> None:
    client = _client()
    user_id, course_id = _new_identity()
    node_id = _init_workspace(client, user_id, course_id)

    _load_node(client, user_id, course_id, node_id)
    _load_node(client, user_id, course_id, node_id)

    state = _fetch_state(client, user_id, course_id)
    cards = _cards_for_node(state, node_id)

    assert len(cards) == len(RESOURCE_CARD_ORDER)
    assert [card["card_type"] for card in cards] == RESOURCE_CARD_ORDER
    assert len({card["card_type"] for card in cards}) == len(RESOURCE_CARD_ORDER)


def test_diagnostic_below_threshold_stays_on_current_node() -> None:
    client = _client()
    user_id, course_id = _new_identity()
    node_id = _init_workspace(client, user_id, course_id)
    _load_node(client, user_id, course_id, node_id)

    response = client.post(
        "/api/pipeline/step",
        json={
            "user_id": user_id,
            "course_id": course_id,
            "current_node_id": node_id,
            "interaction_type": "complete_learning",
            **_quiz_submission(user_id, course_id, node_id, correct=False),
        },
    )
    assert response.status_code == 200
    payload = response.json()

    state = _fetch_state(client, user_id, course_id)

    assert payload["interaction_type"] == "complete_learning"
    assert payload["mastery_updated"] is False
    assert payload["advanced_to_next_node"] is False
    assert payload["current_node_id"] == node_id
    assert payload["evaluated_node_id"] == node_id
    assert payload["evaluated_node_mastery"] == 0.0
    assert state["current_node_id"] == node_id
    assert len(_cards_for_node(state, node_id)) == len(RESOURCE_CARD_ORDER)


def test_diagnostic_at_threshold_advances_to_next_pending_node() -> None:
    client = _client()
    user_id, course_id = _new_identity()
    node_id = _init_workspace(client, user_id, course_id)
    _load_node(client, user_id, course_id, node_id)

    session = get_session(user_id, course_id)
    session.agent_state.dynamic_profile.knowledge_mastery[node_id] = 0.9

    response = client.post(
        "/api/pipeline/step",
        json={
            "user_id": user_id,
            "course_id": course_id,
            "current_node_id": node_id,
            "interaction_type": "complete_learning",
            **_quiz_submission(user_id, course_id, node_id, correct=True),
        },
    )
    assert response.status_code == 200
    payload = response.json()

    state = _fetch_state(client, user_id, course_id)

    assert payload["mastery_updated"] is True
    assert payload["advanced_to_next_node"] is True
    assert payload["evaluated_node_id"] == node_id
    assert payload["evaluated_node_mastery"] >= MASTERY_ADVANCE_THRESHOLD
    assert payload["next_node_id"]
    assert payload["next_node_id"] != node_id
    assert payload["current_node_id"] == payload["next_node_id"]
    assert state["current_node_id"] == payload["next_node_id"]
