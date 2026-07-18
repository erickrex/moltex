from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from moltex_harness.contracts import ContractStore, ContractVerifier
from moltex_harness.contracts.store import FILE_LAYOUT, MODEL_ADAPTERS
from moltex_harness.intake.serialization import deterministic_json
from moltex_harness.intake.service import IntakeService
from moltex_harness.normalize import ContractCompiler
from moltex_harness.models import AssetContract


def _contract_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*.json")
        if path.name != "contract-verification-report.json"
    }


def test_contract_models_round_trip(golden_contracts, tmp_path: Path) -> None:
    destination = tmp_path / "contracts"
    ContractStore().write(destination, golden_contracts)
    loaded, index = ContractStore().load(destination)

    assert loaded == golden_contracts
    assert index.bundle_id == golden_contracts.source_manifest.bundle_id
    for relative_path, attribute, _ in FILE_LAYOUT:
        data = json.loads((destination / relative_path).read_text(encoding="utf-8"))
        value = MODEL_ADAPTERS[attribute].validate_python(data)
        assert deterministic_json(value) == (destination / relative_path).read_text(
            encoding="utf-8"
        )


def test_repeated_compilation_is_byte_equivalent(
    golden_raw_evidence, tmp_path: Path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    store = ContractStore()
    store.write(first, ContractCompiler().compile(golden_raw_evidence))
    store.write(second, ContractCompiler().compile(golden_raw_evidence))

    assert _contract_files(first) == _contract_files(second)
    assert (first / "visual-capture-plan.json").read_bytes() == (
        second / "visual-capture-plan.json"
    ).read_bytes()


def test_verifier_passes_golden_contracts(golden_contracts, tmp_path: Path) -> None:
    destination = tmp_path / "contracts"
    ContractStore().write(destination, golden_contracts)
    report = ContractVerifier().verify(destination)
    assert report.status == "pass"
    assert all(report.checks.values())


def test_verifier_localizes_checksum_mutation(golden_contracts, tmp_path: Path) -> None:
    destination = tmp_path / "contracts"
    ContractStore().write(destination, golden_contracts)
    route_path = destination / "contracts" / "routes.json"
    route_path.write_text(
        route_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
    )

    report = ContractVerifier().verify(destination)
    assert report.status == "fail"
    assert any(
        "contract_size_mismatch: contracts/routes.json" in error
        for error in report.errors
    )
    assert any(
        "contract_checksum_mismatch: contracts/routes.json" in error
        for error in report.errors
    )


def test_verifier_rejects_runtime_media_hotlink(
    golden_contracts, tmp_path: Path
) -> None:
    first = golden_contracts.media_map[0]
    mutated = first.model_copy(update={"target_url": first.source_url})
    contracts = golden_contracts.model_copy(
        update={"media_map": (mutated, *golden_contracts.media_map[1:])}
    )
    destination = tmp_path / "contracts"
    ContractStore().write(destination, contracts)

    report = ContractVerifier().verify(destination)

    assert report.status == "fail"
    assert f"media_local_target: {first.asset_contract_id}" in report.errors


def test_verifier_rejects_unresolved_evidence_pointer(
    golden_contracts, tmp_path: Path
) -> None:
    first = golden_contracts.evidence_resolutions[0]
    contracts = golden_contracts.model_copy(
        update={
            "evidence_resolutions": (
                first.model_copy(update={"pointer": "/does/not/exist"}),
                *golden_contracts.evidence_resolutions[1:],
            )
        }
    )
    destination = tmp_path / "contracts"
    ContractStore().write(destination, contracts)

    report = ContractVerifier().verify(destination)

    assert report.status == "fail"
    assert any("evidence_resolution:" in error for error in report.errors)


def test_asset_model_rejects_contradictory_missing_acquisition(
    golden_contracts,
) -> None:
    value = golden_contracts.assets[0].model_dump(mode="json")
    value.update(
        {
            "acquisition_status": "missing",
            "acquisition_method": "bundle",
            "needs_decision": False,
        }
    )

    with pytest.raises(ValidationError, match="internally inconsistent"):
        AssetContract.model_validate(value)


def test_all_accepted_h1_versions_compile_and_verify(
    samples_dir: Path, tmp_path: Path
) -> None:
    for filename in ("legacy-1-export.zip", "moltex-export-1.zip"):
        raw = (
            IntakeService()
            .inspect(
                samples_dir / filename,
                tmp_path / f"{filename}-intake",
            )
            .result.evidence
        )
        assert raw is not None
        contracts = ContractCompiler().compile(raw)
        destination = tmp_path / f"{filename}-contracts"
        ContractStore().write(destination, contracts)
        assert ContractVerifier().verify(destination).status == "pass"
        assert any(route.target_url == "/" for route in contracts.routes)
        if filename == "legacy-1-export.zip":
            assert len(contracts.redirects) == 7
            assert all(
                redirect.target_route_contract_id for redirect in contracts.redirects
            )
