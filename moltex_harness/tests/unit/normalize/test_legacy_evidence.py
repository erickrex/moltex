from __future__ import annotations

from moltex_harness.models import LegacyPayloadEvidence, RawLegacyEvidence
from moltex_harness.normalize import ContractCompiler


def _entry(
    raw,
    *,
    suffix: str,
    artifact_type: str,
    plugin_status: str,
    relationship_status: str,
    payload_status: str = "omitted",
    payload_method: str = "none",
    identity: dict[str, str],
) -> RawLegacyEvidence:
    content = raw.content[0]
    references = (
        (f"{content.evidence.artifact}#/raw_html",)
        if relationship_status == "referenced"
        else ()
    )
    return RawLegacyEvidence.model_validate(
        {
            "evidence_id": f"legacy:{artifact_type}:{suffix:0>64}",
            "artifact_type": artifact_type,
            "source_plugin": "fixture-plugin",
            "ownership_confidence": "high",
            "plugin_status": plugin_status,
            "source_identity": identity,
            "relationship_status": relationship_status,
            "public_reference_count": 1 if references else 0,
            "reference_evidence": references,
            "payload": LegacyPayloadEvidence(
                status=payload_status,
                method=payload_method,
                artifact=None,
                row_count=1,
                reason="Fixture observation",
            ).model_dump(mode="json"),
            "source_lineage": ["fixture"],
            "evidence": content.evidence.model_dump(mode="json"),
        }
    )


def test_legacy_relevance_filters_dormant_and_localizes_public_orphans(
    golden_raw_evidence,
) -> None:
    entries = (
        _entry(
            golden_raw_evidence,
            suffix="1",
            artifact_type="shortcode",
            plugin_status="inactive",
            relationship_status="referenced",
            identity={"tag": "legacy_widget"},
        ),
        _entry(
            golden_raw_evidence,
            suffix="2",
            artifact_type="custom_table",
            plugin_status="inactive",
            relationship_status="unreferenced",
            identity={"table_name": "wp_legacy_cache"},
        ),
        _entry(
            golden_raw_evidence,
            suffix="3",
            artifact_type="postmeta_field",
            plugin_status="active",
            relationship_status="referenced",
            identity={"post_type": "post", "field_name": "hero_title"},
        ),
        _entry(
            golden_raw_evidence,
            suffix="4",
            artifact_type="custom_table",
            plugin_status="inactive",
            relationship_status="referenced",
            payload_status="deferred",
            payload_method="targeted-export",
            identity={"table_name": "wp_legacy_public"},
        ),
    )
    raw = golden_raw_evidence.model_copy(update={"legacy_evidence": list(entries)})
    contracts = ContractCompiler().compile(raw)
    by_source = {item.source_evidence_id: item for item in contracts.legacy_evidence}

    orphan = by_source[entries[0].evidence_id]
    dormant = by_source[entries[1].evidence_id]
    required = by_source[entries[2].evidence_id]
    deferred = by_source[entries[3].evidence_id]
    assert (orphan.classification, orphan.disposition) == (
        "referenced_orphan",
        "decide",
    )
    assert orphan.capability_id and orphan.decision_id
    assert (dormant.classification, dormant.disposition) == ("dormant", "audit")
    assert dormant.capability_id is None and dormant.decision_id is None
    assert (required.classification, required.disposition) == (
        "required",
        "convert",
    )
    assert (deferred.classification, deferred.disposition) == (
        "deferred",
        "acquire",
    )
    assert deferred.capability_id and deferred.decision_id is None
    capability_ids = {item.capability_id for item in contracts.capabilities}
    assert orphan.capability_id in capability_ids
    assert deferred.capability_id in capability_ids
