from __future__ import annotations

import json
from pathlib import Path

from moltex_harness.models import CapabilityDispositionKind, StaticEligibility


def test_golden_counts_and_contract_coverage(golden_contracts) -> None:
    expected_path = (
        Path(__file__).parents[2] / "fixtures" / "golden_h2_expectations.json"
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    assert len(golden_contracts.content_records) == expected["content"]
    assert len(golden_contracts.routes) == expected["routes"]
    assert len(golden_contracts.assets) == expected["assets"]
    assert len(golden_contracts.seo) == expected["seo"]
    assert len(golden_contracts.capabilities) == expected["capabilities"]
    assert len(golden_contracts.parity_matrix) == expected["parity_rows"]
    assert (
        len(golden_contracts.visual_capture_plan.targets) == expected["visual_targets"]
    )
    assert golden_contracts.site_spec.route_families == tuple(
        expected["route_families"]
    )
    assert golden_contracts.site_spec.static_eligibility == StaticEligibility.ELIGIBLE
    assert golden_contracts.decisions == ()

    public_records = {
        record.record_id
        for record in golden_contracts.content_records
        if record.status == "publish"
    }
    assert {
        route.content_record_id for route in golden_contracts.routes
    } == public_records
    assert {contract.route_contract_id for contract in golden_contracts.seo} == {
        route.contract_id for route in golden_contracts.routes
    }


def test_menu_hierarchy_references_route_contracts(golden_contracts) -> None:
    routes = {route.contract_id for route in golden_contracts.routes}
    navigation = golden_contracts.site_spec.global_navigation
    navigation_ids = {item.navigation_id for item in navigation}

    assert len(navigation) == 8
    assert all(item.route_contract_id in routes for item in navigation)
    assert all(
        item.parent_navigation_id is None or item.parent_navigation_id in navigation_ids
        for item in navigation
    )


def test_media_maps_are_immutable_and_references_reconcile(golden_contracts) -> None:
    assets = {asset.asset_id: asset for asset in golden_contracts.assets}
    assert {entry.asset_contract_id for entry in golden_contracts.media_map} == set(
        assets
    )
    assert all(asset.bundle_path and asset.target_path for asset in assets.values())
    assert all(not asset.needs_decision for asset in assets.values())
    assert any(asset.referencing_content_ids for asset in assets.values())


def test_capabilities_have_explicit_dispositions(golden_contracts) -> None:
    dispositions = {
        capability.disposition for capability in golden_contracts.capabilities
    }
    assert CapabilityDispositionKind.NEEDS_DECISION not in dispositions
    assert CapabilityDispositionKind.EXTERNALIZE in dispositions
    assert CapabilityDispositionKind.REPRODUCE in dispositions
    assert all(
        capability.target_behavior for capability in golden_contracts.capabilities
    )
    assert all(
        capability.verification_method for capability in golden_contracts.capabilities
    )


def test_visual_plan_is_bounded_and_covers_families(golden_contracts) -> None:
    plan = golden_contracts.visual_capture_plan
    routes = {route.contract_id: route for route in golden_contracts.routes}
    assert len(plan.selected_route_ids) <= plan.max_routes
    assert any(
        routes[route_id].target_url == "/" for route_id in plan.selected_route_ids
    )
    assert {
        routes[route_id].page_family for route_id in plan.selected_route_ids
    } == set(golden_contracts.site_spec.route_families)
    for route_id in plan.selected_route_ids:
        targets = [
            target for target in plan.targets if target.route_contract_id == route_id
        ]
        assert {target.viewport.name for target in targets} == {
            "desktop-1440x1200",
            "mobile-500x844",
        }
        assert len({target.evidence_id for target in targets}) == 2
