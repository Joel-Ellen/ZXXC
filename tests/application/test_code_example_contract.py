from __future__ import annotations

from src.agents.content_mesh_node import ContentMeshNode
from src.agents.validator_node import EntityExtractor, Pole1Gate
from src.api_models.tutor_request import TutorRequest
from src.application import resource_service, tutor_service
from src.adapters.state_to_domain import resource_bundle_from_state, resources_from_state
from src.state.agent_state import AgentState
from src.state.agent_state import ResourceCard
from src.validation.c_syntax import validate_c_source


def _code_card(*, language: str, code: str) -> ResourceCard:
    return ResourceCard(
        resource_id=f"example-{language}",
        node_id="N01",
        card_type="code_snippet",
        content=f"## C 代码示例\n\n```{language}\n{code}\n```",
        metadata={
            "structured_payload": {
                "language": language,
                "code": code,
            },
        },
    )


def test_resource_read_boundary_rejects_legacy_python_examples() -> None:
    c_card = _code_card(
        language="c",
        code="int answer(void) { return 42; }",
    )
    python_card = _code_card(
        language="python",
        code="def answer():\n    return 42",
    )

    assert resource_service._resource_card_language_valid(c_card, "zh-CN") is True
    assert resource_service._resource_card_language_valid(python_card, "zh-CN") is False
    assert resource_service._resource_card_language_valid(python_card, "en-US") is False


def test_session_resource_contract_does_not_expose_legacy_python_cards() -> None:
    state = AgentState(
        user_id="u",
        course_id="c",
        generated_resources={"N01": [
            _code_card(
                language="python",
                code="def answer():\n    return 42",
            ),
            _code_card(
                language="c",
                code="int answer(void) { return 42; }",
            ),
        ]},
    )

    resources = resources_from_state(state)["N01"]
    bundle = resource_bundle_from_state(state, "N01")

    assert [resource.structured_payload["language"] for resource in resources] == ["c"]
    assert [resource.resource_type for resource in bundle.resources] == ["code_snippet"]


def test_resource_read_boundary_rejects_other_fenced_languages() -> None:
    javascript_card = _code_card(
        language="c",
        code="int answer(void) { return 42; }",
    ).model_copy(update={
        "content": "## C 代码示例\n\n```javascript\nfunction answer() { return 42; }\n```",
    })

    assert resource_service._resource_card_language_valid(javascript_card, "zh-CN") is False
    assert resource_service._resource_card_language_valid(javascript_card, "en-US") is False


def test_resource_read_boundary_requires_c_on_canonical_payload_for_every_locale() -> None:
    missing_language = _code_card(
        language="c",
        code="int answer(void) { return 42; }",
    )
    del missing_language.metadata["structured_payload"]["language"]

    assert resource_service._resource_card_language_valid(missing_language, "zh-CN") is False
    assert resource_service._resource_card_language_valid(missing_language, "en-US") is False


def test_resource_read_boundary_rejects_python_fences_outside_code_cards() -> None:
    concept_card = ResourceCard(
        resource_id="concept-with-python",
        node_id="N01",
        card_type="concept_map",
        content="## 概念说明\n\n```python\ndef answer():\n    return 42\n```",
        metadata={},
    )

    assert resource_service._resource_card_language_valid(concept_card, "zh-CN") is False
    assert resource_service._resource_card_language_valid(concept_card, "en-US") is False


def test_content_mesh_fallback_contains_a_valid_c_function() -> None:
    content = ContentMeshNode._default_generate("N01", "code_snippet", 0.5)
    blocks = EntityExtractor.extract_code_blocks(content)

    assert len(blocks) == 1
    language, code = blocks[0]
    assert language == "c"
    assert validate_c_source(code) is None


def test_validator_rejects_python_in_unknown_learner_output_types() -> None:
    result = Pole1Gate().validate(
        "```\ndef answer():\n    return 42\n```",
        "future_code_card",
    )

    assert result.passed is False


def test_tutor_fallback_uses_c_but_preserves_submitted_debug_code() -> None:
    generated = tutor_service._fallback_tutor_response(
        TutorRequest(question="请帮我调试", context_type="code_debug")
    )
    assert "```c\n#include <stdio.h>" in generated["text_explanation"]

    submitted = tutor_service._fallback_tutor_response(
        TutorRequest(
            question="请帮我调试",
            context_type="code_debug",
            code_snippet="def legacy():\n    return 1",
        )
    )
    assert "```text\ndef legacy():" in submitted["text_explanation"]
