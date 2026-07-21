from __future__ import annotations

import pytest

from moltex_harness.models import StaticEligibility
from moltex_harness.normalize import ContractCompiler


@pytest.mark.parametrize(
    ("builder", "content_update", "expected_signal"),
    [
        (
            "elementor",
            {"postmeta": {"_elementor_data": '[{"elType":"section"}]'}},
            "post_meta",
        ),
        (
            "divi",
            {"original_html": "[et_pb_section][et_pb_text]Hello[/et_pb_text]"},
            "shortcode",
        ),
    ],
)
def test_page_builder_evidence_blocks_complete_migration(
    golden_raw_evidence, builder, content_update, expected_signal
) -> None:
    first = golden_raw_evidence.content[0].model_copy(update=content_update)
    raw = golden_raw_evidence.model_copy(
        update={"content": [first, *golden_raw_evidence.content[1:]]}
    )

    contracts = ContractCompiler().compile(raw)

    capability = next(
        item
        for item in contracts.capabilities
        if item.capability_id == f"capability:page-builder:{builder}"
    )
    assert capability.capability_type == "unsupported_page_builder"
    assert expected_signal in capability.source_construct
    assert capability.observed_route_ids
    assert contracts.site_spec.static_eligibility == StaticEligibility.INELIGIBLE
    assert any(
        finding.code == "unsupported_page_builder"
        and finding.severity == "error"
        and finding.subject_id == capability.capability_id
        for finding in contracts.findings
    )
    assert any(
        decision.kind == "unsupported-page-builder"
        and decision.subject_id == capability.capability_id
        for decision in contracts.decisions
    )
