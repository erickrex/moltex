from __future__ import annotations

from moltex_harness.intake.artifacts import (
    CAPABILITY_ARTIFACTS,
    CAPABILITY_CONSUMERS,
    DIAGNOSTIC_ARTIFACTS,
)


def test_capability_handshake_has_exactly_the_compiler_consumers() -> None:
    assert CAPABILITY_ARTIFACTS == (
        "forms_config.json",
        "geodirectory.json",
        "integration_manifest.json",
        "plugins/plugins_fingerprint.json",
        "shortcodes_inventory.json",
        "widgets.json",
    )
    assert set(CAPABILITY_ARTIFACTS) == set(CAPABILITY_CONSUMERS)
    assert not set(CAPABILITY_ARTIFACTS) & DIAGNOSTIC_ARTIFACTS


def test_diagnostic_artifacts_are_not_loaded_as_capabilities(
    golden_raw_evidence,
) -> None:
    loaded = {artifact.artifact for artifact in golden_raw_evidence.capabilities}
    assert loaded <= set(CAPABILITY_ARTIFACTS)
    assert not loaded & DIAGNOSTIC_ARTIFACTS
