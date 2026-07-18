from __future__ import annotations

from moltex_harness.models import CapabilityDispositionKind
from moltex_harness.normalize import ContractCompiler


def test_geodirectory_fields_and_gallery_are_compiled(golden_raw_evidence) -> None:
    content = list(golden_raw_evidence.content)
    media = golden_raw_evidence.media[0]
    content[0] = content[0].model_copy(
        update={
            "geodirectory": {
                "address": {"city": "Madrid"},
                "geo": {"latitude": 40.42, "longitude": -3.70},
                "custom_fields": {"price_level": 3, "has_dj": True},
                "media": [{"url": media.source_url}],
                "reviews": [{"author": "Public Guest", "rating": 4.5}],
            }
        }
    )

    contracts = ContractCompiler().compile(
        golden_raw_evidence.model_copy(update={"content": content})
    )
    record = next(
        item
        for item in contracts.content_records
        if item.source_id == str(content[0].source_id)
    )
    fields = {field.key: field for field in record.custom_fields}

    assert fields["geodirectory.address.city"].value == "Madrid"
    assert fields["geodirectory.geo.latitude"].value == 40.42
    assert fields["geodirectory.custom_fields.price_level"].value == 3
    assert fields["geodirectory.reviews"].value[0]["rating"] == 4.5
    assert all(
        field.source_owner == "geodirectory"
        for key, field in fields.items()
        if key.startswith("geodirectory.")
    )
    assert any(
        asset.source_url == media.source_url
        and asset.asset_id in record.required_media_ids
        for asset in contracts.assets
    )


def test_geodirectory_behavior_has_explicit_h2_dispositions(
    golden_raw_evidence,
) -> None:
    template = golden_raw_evidence.capabilities[0]
    evidence = template.evidence.model_copy(
        update={"artifact": "geodirectory.json", "pointer": ""}
    )
    geodirectory = template.model_copy(
        update={
            "artifact": "geodirectory.json",
            "data": {
                "schema_version": 1,
                "post_types": {
                    "gd_nightclubs": {
                        "fields": [{"key": "price_level"}],
                        "search_fields": [{"key": "price_level"}],
                        "sort_fields": [{"key": "price_level"}],
                        "tabs": [{"key": "photos"}],
                    }
                },
            },
            "evidence": evidence,
        }
    )
    contracts = ContractCompiler().compile(
        golden_raw_evidence.model_copy(
            update={
                "capabilities": [
                    *golden_raw_evidence.capabilities,
                    geodirectory,
                ]
            }
        )
    )
    listing = next(
        item
        for item in contracts.capabilities
        if item.capability_id == "capability:geodirectory:gd_nightclubs:listing"
    )
    discovery = next(
        item
        for item in contracts.capabilities
        if item.capability_id == "capability:geodirectory:gd_nightclubs:discovery"
    )

    assert listing.disposition == CapabilityDispositionKind.REPRODUCE
    assert discovery.disposition == CapabilityDispositionKind.NEEDS_DECISION
    assert any(
        decision.subject_id == discovery.capability_id
        for decision in contracts.decisions
    )


def test_geodirectory_visual_plan_uses_one_capability_representative(
    golden_raw_evidence,
) -> None:
    source = golden_raw_evidence.content[0]
    content = [
        source.model_copy(
            update={
                "source_id": 1000 + index,
                "content_type": "gd_nightclubs",
                "slug": f"club-{index}",
                "legacy_permalink": f"/nightclubs/club-{index}/",
                "title": f"Club {index}",
            }
        )
        for index in range(20)
    ]
    template = golden_raw_evidence.capabilities[0]
    geodirectory = template.model_copy(
        update={
            "artifact": "geodirectory.json",
            "data": {
                "schema_version": 1,
                "post_types": {
                    "gd_nightclubs": {
                        "fields": [],
                        "search_fields": [],
                        "sort_fields": [],
                        "tabs": [],
                    }
                },
            },
            "evidence": template.evidence.model_copy(
                update={"artifact": "geodirectory.json", "pointer": ""}
            ),
        }
    )

    contracts = ContractCompiler().compile(
        golden_raw_evidence.model_copy(
            update={"content": content, "capabilities": [geodirectory]}
        )
    )

    listing = next(
        item
        for item in contracts.capabilities
        if item.capability_id == "capability:geodirectory:gd_nightclubs:listing"
    )
    capability_targets = {
        target.route_contract_id
        for target in contracts.visual_capture_plan.targets
        if target.selection_reason == f"capability:{listing.capability_id}"
    }
    assert len(listing.observed_route_ids) == 20
    assert len(capability_targets) <= 1
    assert len(contracts.visual_capture_plan.selected_route_ids) <= 12
