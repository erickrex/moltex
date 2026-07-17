from __future__ import annotations

import copy

import pytest

from moltex_harness.models import StaticEligibility
from moltex_harness.normalize import ContractCompilationError, ContractCompiler


def test_route_collision_is_rejected(golden_raw_evidence) -> None:
    content = list(golden_raw_evidence.content)
    content[2] = content[2].model_copy(
        update={"legacy_permalink": content[1].legacy_permalink}
    )
    mutated = golden_raw_evidence.model_copy(update={"content": content})

    with pytest.raises(ContractCompilationError) as failure:
        ContractCompiler().compile(mutated)
    assert failure.value.code == "route_collision"


def test_normalized_contracts_cannot_be_compiled_twice(golden_contracts) -> None:
    with pytest.raises(ContractCompilationError) as failure:
        ContractCompiler().compile(golden_contracts)
    assert failure.value.code == "normalized_input_rejected"


def test_missing_internal_reference_is_preserved_as_decision(
    golden_raw_evidence,
) -> None:
    content = list(golden_raw_evidence.content)
    content[0] = content[0].model_copy(
        update={"internal_links": [*content[0].internal_links, "/missing-target/"]}
    )
    contracts = ContractCompiler().compile(
        golden_raw_evidence.model_copy(update={"content": content})
    )

    record = next(
        item
        for item in contracts.content_records
        if item.source_id == str(content[0].source_id)
    )
    assert "/missing-target/" in record.unresolved_internal_links
    assert any(
        finding.code == "missing_internal_reference" for finding in contracts.findings
    )
    assert any(
        decision.kind == "missing-internal-route" for decision in contracts.decisions
    )
    assert contracts.site_spec.static_eligibility == StaticEligibility.NEEDS_DECISION


def test_conflicting_seo_evidence_needs_decision(golden_raw_evidence) -> None:
    seo_artifact = golden_raw_evidence.seo[0]
    data = copy.deepcopy(seo_artifact.data)
    duplicate = dict(data["pages"][0])
    duplicate["resolved_title"] = "Contradictory title"
    data["pages"].append(duplicate)
    mutated = golden_raw_evidence.model_copy(
        update={"seo": [seo_artifact.model_copy(update={"data": data})]}
    )

    contracts = ContractCompiler().compile(mutated)
    assert any(contract.needs_decision for contract in contracts.seo)
    assert any(decision.kind == "seo-conflict" for decision in contracts.decisions)
    assert any(
        finding.code == "seo_evidence_conflict" for finding in contracts.findings
    )


def test_missing_media_gets_placeholder_contract(golden_raw_evidence) -> None:
    content = list(golden_raw_evidence.content)
    missing_url = "http://localhost:8094/wp-content/uploads/2026/07/missing.png"
    content[0] = content[0].model_copy(
        update={"featured_media": {"id": 9999, "url": missing_url, "alt": "Missing"}}
    )
    contracts = ContractCompiler().compile(
        golden_raw_evidence.model_copy(update={"content": content})
    )

    asset = next(item for item in contracts.assets if item.source_url == missing_url)
    assert asset.needs_decision
    assert asset.bundle_path is None
    assert (
        asset.asset_id
        in next(
            item
            for item in contracts.content_records
            if item.source_id == str(content[0].source_id)
        ).required_media_ids
    )
    assert any(decision.kind == "missing-media" for decision in contracts.decisions)


def test_unresolved_capability_route_is_added_to_visual_plan(
    golden_raw_evidence,
) -> None:
    capabilities = list(golden_raw_evidence.capabilities)
    integration_index = next(
        index
        for index, artifact in enumerate(capabilities)
        if artifact.artifact == "integration_manifest.json"
    )
    artifact = capabilities[integration_index]
    data = copy.deepcopy(artifact.data)
    data["integrations"][0]["target"] = "unknown-video-provider"
    data["integrations"][0]["business_critical"] = True
    capabilities[integration_index] = artifact.model_copy(update={"data": data})

    contracts = ContractCompiler().compile(
        golden_raw_evidence.model_copy(update={"capabilities": capabilities})
    )
    capability = next(
        item
        for item in contracts.capabilities
        if item.capability_id.startswith("capability:integration:")
    )
    assert capability.observed_route_ids == ("route:page:203",)
    assert "route:page:203" in contracts.visual_capture_plan.selected_route_ids
    assert any(
        decision.subject_id == capability.capability_id
        for decision in contracts.decisions
    )
