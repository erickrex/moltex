from __future__ import annotations

from moltex_harness.normalize import ContractCompiler


def test_optional_evidence_reduction_preserves_h2_semantics(
    golden_raw_evidence,
) -> None:
    baseline = ContractCompiler().compile(golden_raw_evidence)
    reduced = golden_raw_evidence.model_copy(
        update={
            "html_references": golden_raw_evidence.html_references[:2],
            "inventory": [
                item
                for item in golden_raw_evidence.inventory
                if not item.path.startswith(
                    ("plugins/readmes/", "plugins/templates/")
                )
            ],
        }
    )
    compiled = ContractCompiler().compile(reduced)

    for field in baseline.__class__.model_fields:
        if field != "source_manifest":
            assert getattr(compiled, field) == getattr(baseline, field)


def test_multiple_media_urls_can_share_one_verified_binary(
    golden_raw_evidence,
) -> None:
    first, second, *remaining = golden_raw_evidence.media
    aliased_second = second.model_copy(
        update={
            "artifact": first.artifact,
            "bytes": first.bytes,
            "sha256": first.sha256,
        }
    )
    reduced = golden_raw_evidence.model_copy(
        update={"media": [first, aliased_second, *remaining]}
    )

    contracts = ContractCompiler().compile(reduced)
    assets = {asset.source_url: asset for asset in contracts.assets}

    assert len(assets) == len(golden_raw_evidence.media)
    assert assets[first.source_url].bundle_path == first.artifact
    assert assets[second.source_url].bundle_path == first.artifact
    assert assets[first.source_url].checksum == assets[second.source_url].checksum
    assert {entry.source_url for entry in contracts.media_map} == set(assets)
