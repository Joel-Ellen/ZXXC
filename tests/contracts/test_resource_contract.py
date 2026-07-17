from src.api_models.resource_response import ResourceResponse
from src.adapters.state_to_domain import resource_contract_from_card
from src.contracts.resource_contract import ResourceContract
from src.state.agent_state import ResourceCard
from src.validation.result import ValidationResult


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


def test_resource_adapter_preserves_structured_validation_details():
    validation = ValidationResult()
    validation.add_issue(
        "unsafe_content",
        "Unsafe content detected",
        severity="critical",
        field="concept_map",
        detector="content_filter",
        match={"category": "unsafe", "confidence": 0.98},
    )
    validation.metadata = {
        "guard": "output",
        "pole1": {"passed": False, "code_ast_errors": []},
    }
    validation_payload = validation.to_contract_validation()
    validation_payload["policy_version"] = "2026-07"
    validation_payload["issues"][0]["rule_version"] = "unsafe-content-v2"

    card = ResourceCard(
        resource_id="resource-with-validation",
        node_id="N01",
        card_type="concept_map",
        content="Blocked content",
        metadata={
            "validation": validation_payload,
            "safety": {
                "status": "flagged",
                "issues": validation_payload["issues"],
            },
        },
    )

    payload = resource_contract_from_card(card).model_dump(mode="json")

    assert payload["validation"]["status"] == "rejected"
    assert payload["validation"]["passed"] is False
    assert payload["validation"]["metadata"] == validation.metadata
    assert payload["validation"]["policy_version"] == "2026-07"
    issue = payload["validation"]["issues"][0]
    assert issue == {
        "code": "unsafe_content",
        "message": "Unsafe content detected",
        "severity": "critical",
        "field": "concept_map",
        "details": {
            "detector": "content_filter",
            "match": {"category": "unsafe", "confidence": 0.98},
        },
        "rule_version": "unsafe-content-v2",
    }
    assert payload["safety"]["issues"][0] == issue


def test_resource_validation_normalizes_legacy_string_issues():
    contract = ResourceContract(
        resource_id="legacy-resource",
        node_id="N02",
        resource_type="concept_map",
        validation={"status": "failed", "issues": ["Legacy validator rejected content"]},
    )

    issue = contract.model_dump(mode="json")["validation"]["issues"][0]
    assert issue["code"] == "legacy_issue"
    assert issue["message"] == "Legacy validator rejected content"
    assert issue["details"] == {"legacy_format": "string"}
