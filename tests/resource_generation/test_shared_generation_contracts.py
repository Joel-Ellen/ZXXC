from __future__ import annotations

import pytest

from src.adapters.state_to_domain import resource_contract_from_card
from src.resource_generation import CARD_TYPES, ResourceContext, ResourceGenerator, payload_model_for, validate_resource_payload
from src.state.agent_state import ResourceCard


@pytest.fixture
def generation_context() -> ResourceContext:
    return ResourceContext(
        user_id="schema-user",
        course_id="course-a",
        node_id="N01",
        node_title="Queue invariants",
        capability_target="reason about FIFO constraints",
        knowledge_refs=[
            {
                "id": "kb-queue-1",
                "type": "knowledge_base",
                "title": "Queue invariant",
                "excerpt": "A queue removes the earliest enqueued item.",
            }
        ],
        error_signature="fifo_vs_lifo",
    )


@pytest.mark.parametrize("card_type", CARD_TYPES)
def test_local_templates_validate_against_all_shared_card_schemas(
    generation_context: ResourceContext,
    card_type: str,
) -> None:
    generated = ResourceGenerator().template(generation_context, card_type)

    parsed = payload_model_for(card_type).model_validate(generated.structured_payload)
    validation = validate_resource_payload(card_type, generated.structured_payload, generation_context)

    assert parsed.render_type == card_type
    assert validation.valid, validation.issues
    assert generated.source == "template"
    assert generated.body_markdown.startswith("> Generation status: local fallback template.")


def test_resource_contract_redacts_server_owned_answer_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.adapters.state_to_domain._node_title", lambda _node_id: "Queue invariants")
    card = ResourceCard(
        resource_id="quiz-1",
        node_id="N01",
        card_type="diagnostic_quiz",
        content="## Queue quiz",
        metadata={
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Which order does a queue preserve?",
                    "options": ["FIFO", "LIFO", "random", "sorted"],
                    "answer_index": 0,
                    "explanation": "FIFO removes the earliest item.",
                }
            ],
            "nested_answer_data": {
                "correct_answer": "FIFO",
                "answerIndex": 0,
            },
        },
    )

    contract = resource_contract_from_card(card)
    public_question = contract.structured_payload["questions"][0]

    assert card.metadata["questions"][0]["answer_index"] == 0
    assert "answer_index" not in public_question
    assert "correct_answer" not in contract.structured_payload["nested_answer_data"]
    assert "answerIndex" not in contract.structured_payload["nested_answer_data"]


def test_legacy_resource_read_gets_a_complete_provenance_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.adapters.state_to_domain._node_title", lambda _node_id: "Queue invariants")
    contract = resource_contract_from_card(ResourceCard(
        resource_id="legacy-concept",
        node_id="N01",
        card_type="concept_map",
        content="## Queue invariants",
        difficulty=0.4,
        metadata={},
    ))

    assert contract.generation["source"] == "legacy"
    assert contract.content_version == "legacy-v1"
    assert contract.difficulty_basis == {"source": "legacy_card", "difficulty": 0.4}
    assert contract.source_refs == [{
        "id": "legacy-course-node:N01",
        "type": "course_node",
        "node_id": "N01",
        "title": "Queue invariants",
    }]


def test_video_links_require_a_matching_trusted_video_reference(
    generation_context: ResourceContext,
) -> None:
    trusted_context = ResourceContext(
        **{
            **generation_context.__dict__,
            "knowledge_refs": [
                {
                    "id": "video-queue-1",
                    "type": "video",
                    "title": "Queue walkthrough",
                    "excerpt": "A trusted queue lecture.",
                    "video_url": "https://video.example/queue",
                    "video_source_id": "queue-course-video-1",
                }
            ],
        }
    )
    payload = ResourceGenerator().template(trusted_context, "video_summary").structured_payload
    payload.update({
        "video_url": "https://video.example/queue",
        "video_source_id": "queue-course-video-1",
    })

    assert validate_resource_payload("video_summary", payload, trusted_context).valid

    payload["video_source_id"] = "unrelated-source"
    issues = validate_resource_payload("video_summary", payload, trusted_context).issues
    assert any(issue.code == "video_source_missing" for issue in issues)


def test_payload_requires_a_retrieved_source_when_knowledge_refs_exist(
    generation_context: ResourceContext,
) -> None:
    payload = ResourceGenerator().template(generation_context, "concept_map").structured_payload
    payload["source_ref_ids"] = ["course:course-a:N01"]

    validation = validate_resource_payload("concept_map", payload, generation_context)

    assert validation.valid is False
    assert any(issue.code == "knowledge_source_required" for issue in validation.issues)


def test_generator_rebinds_provider_citations_to_retrieved_evidence(
    generation_context: ResourceContext,
) -> None:
    template = ResourceGenerator().template(generation_context, "concept_map").structured_payload
    template["source_ref_ids"] = ["course:course-a:N01", "invented-source"]

    generated = ResourceGenerator()._result_from_payload(  # noqa: SLF001 - verifies generator-owned binding
        "concept_map",
        template,
        generation_context,
        source="llm",
    )

    assert generated.source == "llm"
    assert generated.structured_payload["source_ref_ids"] == ["kb-queue-1"]


def test_code_snippet_rejects_invalid_python_syntax(
    generation_context: ResourceContext,
) -> None:
    payload = ResourceGenerator().template(generation_context, "code_snippet").structured_payload
    payload["code"] = "def incomplete(:\n    return 1\n"

    validation = validate_resource_payload("code_snippet", payload, generation_context)

    assert validation.valid is False
    assert validation.payload is None
    assert any(issue.code == "code_syntax_invalid" for issue in validation.issues)


def test_code_snippet_syntax_check_does_not_execute_source(
    generation_context: ResourceContext,
) -> None:
    payload = ResourceGenerator().template(generation_context, "code_snippet").structured_payload
    payload["code"] = "raise RuntimeError('validation must not execute source')"

    validation = validate_resource_payload("code_snippet", payload, generation_context)

    assert validation.valid is True


def test_code_snippet_contract_rejects_unvalidated_languages(
    generation_context: ResourceContext,
) -> None:
    payload = ResourceGenerator().template(generation_context, "code_snippet").structured_payload
    payload.update({"language": "javascript", "code": "const value = 1;"})

    validation = validate_resource_payload("code_snippet", payload, generation_context)

    assert validation.valid is False
    assert validation.payload is None
    assert any(issue.code == "schema_invalid" and issue.field == "language" for issue in validation.issues)


def test_code_snippet_rejects_source_beyond_bounded_local_parser_limit(
    generation_context: ResourceContext,
) -> None:
    payload = ResourceGenerator().template(generation_context, "code_snippet").structured_payload
    payload["code"] = "# " + ("\u4e2d" * 6_000)

    validation = validate_resource_payload("code_snippet", payload, generation_context)

    assert validation.valid is False
    assert validation.payload is None
    assert any(issue.code == "code_too_large" for issue in validation.issues)
