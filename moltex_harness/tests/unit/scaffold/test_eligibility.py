from __future__ import annotations

import shutil
from pathlib import Path

import moltex_harness.scaffold.service as scaffold_service
from moltex_harness.contracts import ContractStore
from moltex_harness.contracts.service import CompilationOutcome
from moltex_harness.models import StaticEligibility
from moltex_harness.scaffold import BaselineService


class NeverCapture:
    def capture(self, target):
        raise AssertionError("ineligible contracts must stop before visual capture")


def test_ineligible_contracts_stop_before_baseline_generation(
    golden_contracts, monkeypatch, tmp_path: Path
) -> None:
    ineligible = golden_contracts.model_copy(
        update={
            "site_spec": golden_contracts.site_spec.model_copy(
                update={"static_eligibility": StaticEligibility.INELIGIBLE}
            )
        }
    )
    prepared = tmp_path / "prepared-contracts"
    ContractStore().write(prepared, ineligible)

    class PreparedCompilation:
        def compile_archive(self, archive: Path, output: Path) -> CompilationOutcome:
            shutil.copytree(prepared, output, dirs_exist_ok=True)
            return CompilationOutcome(
                {
                    "bundle_id": ineligible.source_manifest.bundle_id,
                    "message": "prepared",
                },
                0,
            )

    monkeypatch.setattr(
        scaffold_service, "CompilationService", lambda: PreparedCompilation()
    )
    output = tmp_path / "site"

    outcome = BaselineService(capture_backend=NeverCapture()).compile_archive(
        tmp_path / "source.zip", output
    )

    assert outcome.exit_code == 7
    assert outcome.report.code == "static_ineligible"
    assert outcome.report.classification == "blocked"
    assert (output / "baseline-compilation-report.json").is_file()
    assert not (output / "src").exists()
