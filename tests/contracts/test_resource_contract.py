from src.contracts.resource_contract import ResourceContract


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
