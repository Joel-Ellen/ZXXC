from __future__ import annotations

from dataclasses import replace

import pytest

from src.adapters.state_to_domain import resource_contract_from_card
from src.resource_generation import CARD_TYPES, ResourceContext, ResourceGenerator, TEMPLATE_NOTICE, payload_model_for, validate_resource_payload
from src.resource_generation.prompts import _schema_for, build_card_messages, build_supporting_bundle_messages
from src.state.agent_state import ResourceCard
from src.validation.language import is_chinese_learning_content


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
    assert generated.body_markdown.startswith(TEMPLATE_NOTICE)


def test_question_bank_prompt_is_isolated_from_interactive_exercise(
    generation_context: ResourceContext,
) -> None:
    context = replace(
        generation_context,
        question_bank_status="matched",
        question_bank_candidates=[{
            "id": "bank-secret-boundary",
            "text": "队列在空队列边界下如何处理出队？",
        }],
    )

    class CapturingLlm:
        provider = "test"
        model = "capture"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def chat_sync(self, messages, **_kwargs):
            self.prompts.append(messages[1]["content"])
            return {"content": "{}"}

    llm = CapturingLlm()
    generated = ResourceGenerator().generate_bundle(
        llm,
        context,
        ["interactive_exercise", "diagnostic_quiz"],
    )

    assert set(generated) == {"interactive_exercise", "diagnostic_quiz"}
    assert len(llm.prompts) == 2
    assert sum("bank-secret-boundary" in prompt for prompt in llm.prompts) == 1
    exercise_prompt = next(
        prompt for prompt in llm.prompts if "bank-secret-boundary" not in prompt
    )
    assert '"question_bank"' not in exercise_prompt
    with pytest.raises(ValueError, match="diagnostic_quiz_prompt_must_be_isolated"):
        build_supporting_bundle_messages(
            context,
            ["interactive_exercise", "diagnostic_quiz"],
        )


@pytest.mark.parametrize("card_type", CARD_TYPES)
def test_local_templates_localize_an_english_context_title(
    generation_context: ResourceContext,
    card_type: str,
) -> None:
    generated = ResourceGenerator().template(generation_context, card_type)

    assert generated.structured_payload["title"].startswith("当前知识点")
    assert is_chinese_learning_content(generated.body_markdown)


def test_local_template_replaces_an_english_blueprint_snapshot(
    generation_context: ResourceContext,
) -> None:
    snapshot = ResourceGenerator().template(
        generation_context,
        "concept_map",
    ).structured_payload["learning_blueprint"]
    snapshot["objectives"][0]["text"] = (
        "This objective explains the concept entirely in English."
    )
    context = replace(generation_context, blueprint_snapshot=snapshot)

    generated = ResourceGenerator().template(context, "concept_map")

    blueprint = generated.structured_payload["learning_blueprint"]
    assert "entirely in English" not in str(blueprint)
    assert validate_resource_payload(
        "concept_map",
        generated.structured_payload,
        context,
    ).valid


def test_concept_prompt_keeps_nested_schema_defs_and_requires_a_branches_map(
    generation_context: ResourceContext,
) -> None:
    schema = _schema_for("concept_map")
    assert "$defs" in schema
    assert "ConceptSection" in schema["$defs"]

    prompt = build_card_messages(generation_context, "concept_map")[1]["content"]
    assert "8-14 个语义节点" in prompt
    assert "至少 7 条有向边" in prompt
    assert "至少 3 条边从核心概念分出" in prompt


def test_local_concept_template_is_a_labeled_branching_map(
    generation_context: ResourceContext,
) -> None:
    payload = ResourceGenerator().template(
        generation_context,
        "concept_map",
    ).structured_payload
    diagram = payload["mermaid_source"]
    assert diagram.startswith("graph TD")
    assert diagram.count("-->") >= 7
    assert diagram.count("|准备|") == 1
    assert "|不适用于|" in diagram
    assert "|迁移到|" in diagram


def test_local_video_template_drops_an_english_trusted_timeline(
    generation_context: ResourceContext,
) -> None:
    context = replace(
        generation_context,
        knowledge_refs=[{
            "id": "video-queue-english",
            "type": "video",
            "title": "Queue lecture",
            "excerpt": "可信的视频索引记录。",
            "video_url": "https://video.example/queue-english",
            "video_source_id": "queue-video-english",
            "duration_minutes": 12,
            "timeline": [{
                "label": "00:00",
                "summary": "This section introduces the queue invariant.",
            }],
        }],
    )

    generated = ResourceGenerator().template(context, "video_summary")
    payload = generated.structured_payload

    assert payload["media_status"] == "no_trusted_video"
    assert payload["timeline"] == []
    assert payload["video_url"] is None
    assert validate_resource_payload("video_summary", payload, context).valid


def test_resource_contract_redacts_server_owned_answer_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.adapters.state_to_domain._node_title", lambda _node_id: "Queue invariants")
    card = ResourceCard(
        resource_id="quiz-1",
        node_id="N01",
        card_type="diagnostic_quiz",
        content=(
            "## Queue quiz\n\n"
            "```json\n"
            '{"answer_index":0,"distractor_error_tags":{"1":"wrong"},'
            '"explanation":"FIFO removes the earliest item",'
            '"source_answer_label":"A"}\n'
            "```"
        ),
        metadata={
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Which order does a queue preserve?",
                    "options": ["FIFO", "LIFO", "random", "sorted"],
                    "answer_index": 0,
                    "explanation": "FIFO removes the earliest item.",
                    "distractor_error_tags": {
                        "1": "混淆先进先出与后进先出",
                        "2": "误认为访问顺序随机",
                        "3": "误认为队列自动排序",
                    },
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
    assert "distractor_error_tags" not in public_question
    assert "explanation" not in public_question
    assert "correct_answer" not in contract.structured_payload["nested_answer_data"]
    assert "answerIndex" not in contract.structured_payload["nested_answer_data"]
    assert "answer_index" not in contract.body_markdown
    assert "distractor_error_tags" not in contract.body_markdown
    assert "FIFO removes the earliest item" not in contract.body_markdown
    assert "source_answer_label" not in contract.body_markdown


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


@pytest.mark.parametrize(
    ("card_type", "field_path"),
    (
        ("concept_map", ("summary",)),
        ("code_snippet", ("explanation",)),
        ("interactive_exercise", ("prompt",)),
        ("video_summary", ("summary",)),
        ("diagnostic_quiz", ("questions", 0, "explanation")),
    ),
)
def test_english_resource_prose_is_replaced_by_a_chinese_template(
    generation_context: ResourceContext,
    card_type: str,
    field_path: tuple[object, ...],
) -> None:
    payload = ResourceGenerator().template(generation_context, card_type).structured_payload
    target = payload
    for part in field_path[:-1]:
        target = target[part]
    target[field_path[-1]] = "This is a complete English explanation for the learner."

    validation = validate_resource_payload(card_type, payload, generation_context)
    generated = ResourceGenerator()._result_from_payload(  # noqa: SLF001
        card_type,
        payload,
        generation_context,
        source="llm",
    )

    assert validation.valid is False
    assert any(issue.code == "learner_content_not_chinese" for issue in validation.issues)
    assert generated.source == "template"
    assert "complete English explanation" not in generated.body_markdown
    assert "learner_content_not_chinese" in generated.validation_issues


def test_resource_language_gate_allows_names_apis_and_plain_formulas(
    generation_context: ResourceContext,
) -> None:
    payload = ResourceGenerator().template(generation_context, "concept_map").structured_payload
    payload["summary"] = (
        "使用 Dijkstra 算法和 OpenAI API 说明状态转移，并计算 "
        "d[v] = min(d[v], d[u] + w(u,v))。"
    )
    payload["mermaid_source"] = (
        'graph TD\nA["Dijkstra"] --> B["最短路径"]\n'
        'B --> C["O(n log n)"]'
    )

    validation = validate_resource_payload("concept_map", payload, generation_context)

    assert validation.valid, validation.issues


@pytest.mark.parametrize("english_expected", (
    "The function returns an empty list for this input.",
    "Summary: The algorithm runs in linear time.",
))
def test_resource_language_gate_rejects_english_boundary_expectations(
    generation_context: ResourceContext,
    english_expected: str,
) -> None:
    payload = ResourceGenerator().template(generation_context, "code_snippet").structured_payload
    payload["boundary_tests"][0]["expected"] = english_expected

    validation = validate_resource_payload("code_snippet", payload, generation_context)

    assert validation.valid is False
    assert any(
        issue.code == "learner_content_not_chinese"
        and issue.field == "boundary_tests.0.expected"
        for issue in validation.issues
    )


def test_resource_language_gate_rejects_english_boundary_inputs(
    generation_context: ResourceContext,
) -> None:
    payload = ResourceGenerator().template(generation_context, "code_snippet").structured_payload
    payload["boundary_tests"][0]["input"] = (
        "The learner enters an empty list for this test."
    )

    validation = validate_resource_payload("code_snippet", payload, generation_context)

    assert validation.valid is False
    assert any(
        issue.code == "learner_content_not_chinese"
        and issue.field == "boundary_tests.0.input"
        for issue in validation.issues
    )


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
