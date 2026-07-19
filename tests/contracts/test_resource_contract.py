from src.adapters.state_to_domain import resource_contract_from_card
from src.api_models.resource_response import ResourceResponse
from src.contracts.resource_contract import ResourceContract, ResourceValidation
from src.state.agent_state import ResourceCard


def test_resource_contract_exposes_legacy_aliases():
    contract = ResourceContract(
        resource_id="r1",
        node_id="N01",
        resource_type="concept_map",
        title="Tree",
        body_markdown="## Tree",
        structured_payload={"summary": "ok"},
    )
    data = contract.with_legacy_aliases()
    assert data["resource_type"] == "concept_map"
    assert data["card_type"] == "concept_map"
    assert data["content"] == "## Tree"
    assert data["metadata"] == {"summary": "ok"}


def test_resource_contract_defaults_validation_and_safety():
    contract = ResourceContract(resource_id="r2", node_id="N02", resource_type="quiz")
    assert contract.validation.status == "pending"
    assert contract.safety.status == "unknown"
    assert contract.created_at


def test_resource_response_keeps_legacy_aliases_out_of_dto_by_default():
    response = ResourceResponse(
        node_id="N01",
        resources=[ResourceContract(resource_id="r1", node_id="N01", resource_type="concept_map")],
    )
    dto = response.to_dto_dict()
    compat = response.to_compatible_dict()

    assert "cards" not in dto
    assert dto["resources"][0]["resource_type"] == "concept_map"
    assert compat["cards"][0]["card_type"] == "concept_map"


def test_resource_validation_parses_poisoned_legacy_issue_shapes():
    # Regression: sessions persisted before commit 4c37822 stored structured
    # issue dicts against an issues: List[str] contract and every read 500ed.
    validation = ResourceValidation(
        status="rejected",
        issues=[
            {"code": "unsafe_content", "message": "拒绝", "severity": "error", "field": "concept_map", "details": {}},
            "legacy plain-string issue",
        ],
    )
    assert validation.issues[0].code == "unsafe_content"
    assert validation.issues[0].field == "concept_map"
    assert validation.issues[1].code == "legacy_issue"
    assert validation.issues[1].message == "legacy plain-string issue"


def test_poisoned_validation_metadata_never_fails_a_resource_read():
    # Worst-case persisted shapes (issues not even a list) must degrade to an
    # unknown validation status instead of failing the whole session read.
    contract = resource_contract_from_card(ResourceCard(
        resource_id="poisoned-concept",
        node_id="N01",
        card_type="concept_map",
        content="## 概念图",
        difficulty=0.5,
        metadata={
            "title": "队列",
            "validation": {"status": "rejected", "issues": {"code": "unsafe_content"}},
            "safety": {"status": "flagged", "issues": "not-a-list"},
        },
    ))

    assert contract.validation.status == "unknown"
    assert contract.validation.metadata.get("parse_error")
    assert contract.safety.status == "unknown"
