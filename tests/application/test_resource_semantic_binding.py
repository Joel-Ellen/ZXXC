from __future__ import annotations

from types import SimpleNamespace

from src.application import resource_service
from src.orchestration_runtime import ResourceGenerationResult
from src.state.agent_state import ResourceCard
from tests.helpers import disable_persistence, install_fake_runtime


class _DataStructuresCatalog:
    def get_local_graph(self, course_id):
        if course_id != "data_structures":
            return [], []
        return [
            SimpleNamespace(
                course_id="data_structures",
                node_id="N01",
                title="算法复杂度分析",
            )
        ], []

    def get_node_by_id(self, node_id, course_id="data_structures"):
        nodes, _ = self.get_local_graph(course_id)
        return next((node for node in nodes if node.node_id == node_id), None)

    def get_node_title(self, node_id):
        node = self.get_node_by_id(node_id)
        return node.title if node else node_id


def _runtime_with_catalog(monkeypatch):
    runtime = install_fake_runtime(monkeypatch)
    disable_persistence(monkeypatch)
    runtime.kg = _DataStructuresCatalog()
    session = runtime.get_session("semantic-user", "data_structures")
    session.agent_state.current_node_id = "N01"
    return runtime, session


def test_wrong_n01_stack_generation_is_rejected_and_uses_bound_fallback(monkeypatch):
    runtime, session = _runtime_with_catalog(monkeypatch)
    seen = {}

    def wrong_batch(node_id, card_types, difficulty, *, course_id, node_title):
        seen.update(
            node_id=node_id,
            card_types=list(card_types),
            course_id=course_id,
            node_title=node_title,
        )
        return {
            card_type: ResourceGenerationResult(
                content="## 知识点 N01：栈（Stack）\n\n栈遵循后进先出的访问顺序。",
                source="llm",
                provider="test-provider",
            )
            for card_type in card_types
        }

    runtime.generate_resource_contents = wrong_batch

    result = resource_service.generate_current_node_resources(
        "semantic-user",
        "data_structures",
        "N01",
        card_type="concept_map",
    )

    assert seen == {
        "node_id": "N01",
        "card_types": ["concept_map"],
        "course_id": "data_structures",
        "node_title": "算法复杂度分析",
    }
    assert result["generation"]["status"] == "template_fallback"
    assert result["generation"]["resources"]["concept_map"]["fallback_reason"] == (
        "semantic_binding_failed"
    )
    stored = session.agent_state.generated_resources["N01"][0]
    assert "算法复杂度分析" in stored.content
    assert "栈（Stack）" not in stored.content
    assert stored.metadata["generation"]["source"] == "template"
    assert stored.metadata["semantic_binding"] == {
        "version": 1,
        "source": "server_course_catalog",
        "course_id": "data_structures",
        "node_id": "N01",
        "title": "算法复杂度分析",
        "keywords": [
            "算法复杂度",
            "时间复杂度",
            "空间复杂度",
            "渐进复杂度",
            "Big O",
            "大 O",
            "算法复杂度分析",
        ],
    }
    assert any("resource_semantic_mismatch" in error for error in session.agent_state.errors)


def test_cached_wrong_topic_card_is_repaired_without_calling_the_model(monkeypatch):
    runtime, session = _runtime_with_catalog(monkeypatch)
    session.agent_state.generated_resources["N01"] = [
        ResourceCard(
            resource_id="N01_concept_map_supp",
            node_id="N01",
            card_type="concept_map",
            content="## 知识点 N01：栈（Stack）\n\n这是错误缓存。",
            metadata={"generation": {"source": "llm"}},
        )
    ]

    def must_not_generate(*_args, **_kwargs):
        raise AssertionError("A cached semantic mismatch must use the local bound fallback")

    runtime.generate_resource_contents = must_not_generate

    result = resource_service.generate_current_node_resources(
        "semantic-user",
        "data_structures",
        "N01",
        card_type="concept_map",
    )

    assert result["status"] == "repaired_fallback"
    assert result["generation"]["status"] == "template_fallback"
    stored = session.agent_state.generated_resources["N01"][0]
    assert stored.resource_id == "N01_concept_map_supp"
    assert "算法复杂度分析" in stored.content
    assert "错误缓存" not in stored.content
    assert stored.metadata["generation"]["fallback_reason"] == "semantic_binding_failed"


def test_missing_card_generation_does_not_regenerate_the_complete_batch(monkeypatch):
    runtime, session = _runtime_with_catalog(monkeypatch)
    session.agent_state.generated_resources["N01"] = [
        ResourceCard(
            resource_id="existing-concept-map",
            node_id="N01",
            card_type="concept_map",
            content="## 算法复杂度分析\n\n已有的正确材料。",
        )
    ]
    calls = []

    def bound_batch(node_id, card_types, difficulty, *, course_id, node_title):
        calls.append(list(card_types))
        return {
            card_type: ResourceGenerationResult(
                content=f"## {node_title}\n\n{card_type} for {node_id}",
                source="llm",
            )
            for card_type in card_types
        }

    runtime.generate_resource_contents = bound_batch

    result = resource_service.generate_current_node_resources(
        "semantic-user",
        "data_structures",
        "N01",
    )

    assert calls == [[
        "code_snippet",
        "interactive_exercise",
        "video_summary",
        "diagnostic_quiz",
    ]]
    assert len(result["resources"]) == 5
    concept_map = next(
        card
        for card in session.agent_state.generated_resources["N01"]
        if card.card_type == "concept_map"
    )
    assert concept_map.resource_id == "existing-concept-map"


def test_unconsumed_cached_quiz_replaces_legacy_long_options(monkeypatch):
    runtime, session = _runtime_with_catalog(monkeypatch)
    title = runtime.kg.get_node_title("N01")
    session.agent_state.generated_resources["N01"] = [
        ResourceCard(
            resource_id="N01_diagnostic_quiz_supp",
            node_id="N01",
            card_type="diagnostic_quiz",
            content=f"## {title}\n\nA bound diagnostic resource.",
            metadata={
                "questions": [{
                    "id": "legacy-q1",
                    "prompt": "Legacy question",
                    "options": ["Generation status: " + ("long markdown " * 30)],
                    "answer_index": 0,
                }],
                "quiz_revision": 1,
            },
        )
    ]

    result = resource_service.generate_current_node_resources(
        "semantic-user",
        "data_structures",
        "N01",
        card_type="diagnostic_quiz",
    )

    assert result["status"] == "already_exists"
    metadata = session.agent_state.generated_resources["N01"][0].metadata
    questions = metadata["questions"]
    assert len(questions) == 3
    assert all(max(map(len, question["options"])) < 100 for question in questions)
    assert all(
        "Generation status" not in option
        for question in questions
        for option in question["options"]
    )
    assert metadata["structured_payload"]["questions"] == questions
    assert all("Generation status" not in question["explanation"] for question in questions)


def test_consumed_cached_quiz_keeps_its_original_answer_key(monkeypatch):
    runtime, session = _runtime_with_catalog(monkeypatch)
    title = runtime.kg.get_node_title("N01")
    original_questions = [{
        "id": "consumed-q1",
        "prompt": "Original question",
        "options": ["Original answer", "Distractor"],
        "answer_index": 0,
    }]
    session.agent_state.generated_resources["N01"] = [
        ResourceCard(
            resource_id="consumed-diagnostic",
            node_id="N01",
            card_type="diagnostic_quiz",
            content=f"## {title}\n\nA consumed diagnostic resource.",
            metadata={"questions": original_questions, "quiz_revision": 1},
        )
    ]
    session.agent_state.internal_state["consumed_completion_resource_ids"] = [
        "consumed-diagnostic"
    ]

    resource_service.generate_current_node_resources(
        "semantic-user",
        "data_structures",
        "N01",
        card_type="diagnostic_quiz",
    )

    stored_questions = session.agent_state.generated_resources["N01"][0].metadata["questions"]
    assert stored_questions == original_questions
