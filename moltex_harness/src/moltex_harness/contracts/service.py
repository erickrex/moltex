"""Archive-to-contract orchestration for the H2 CLI boundary."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moltex_harness.intake.service import IntakeService
from moltex_harness.intake.serialization import write_json
from moltex_harness.models import RawSourceEvidence
from moltex_harness.normalize import ContractCompilationError, ContractCompiler

from .store import ContractStore


@dataclass(frozen=True, slots=True)
class CompilationOutcome:
    report: dict[str, Any]
    exit_code: int


class CompilationService:
    def compile_archive(self, archive: Path, output: Path) -> CompilationOutcome:
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="moltex-h2-") as temporary:
            intake = IntakeService().inspect(archive, Path(temporary) / "intake")
            if intake.exit_code:
                report = {
                    "schema_version": 1,
                    "status": "rejected",
                    "stage": "intake",
                    "source_archive": archive.name,
                    "bundle_id": intake.result.report.bundle_id,
                    "code": intake.result.report.findings[0].code,
                    "message": intake.result.report.findings[0].message,
                    "outputs": {},
                }
                write_json(output / "compilation-report.json", report)
                return CompilationOutcome(report, intake.exit_code)
            raw = intake.result.evidence
            if raw is None:
                report = {
                    "schema_version": 1,
                    "status": "failed",
                    "stage": "intake",
                    "source_archive": archive.name,
                    "bundle_id": None,
                    "code": "missing_raw_evidence",
                    "message": "Accepted intake did not provide raw evidence",
                    "outputs": {},
                }
                write_json(output / "compilation-report.json", report)
                return CompilationOutcome(report, 5)
            return self.compile_evidence(raw, archive.name, output)

    def compile_evidence(
        self, raw: RawSourceEvidence, source_archive: str, output: Path
    ) -> CompilationOutcome:
        """Compile already accepted H1 evidence without repeating archive intake."""
        output.mkdir(parents=True, exist_ok=True)
        try:
            contracts = ContractCompiler().compile(raw)
            index = ContractStore().write(output, contracts)
        except ContractCompilationError as error:
            report = {
                "schema_version": 1,
                "status": "rejected",
                "stage": "normalization",
                "source_archive": source_archive,
                "bundle_id": raw.source_manifest.bundle_id,
                "code": error.code,
                "message": str(error),
                "outputs": {},
            }
            write_json(output / "compilation-report.json", report)
            return CompilationOutcome(report, 6)
        except ValueError as error:
            report = {
                "schema_version": 1,
                "status": "rejected",
                "stage": "normalization",
                "source_archive": source_archive,
                "bundle_id": raw.source_manifest.bundle_id,
                "code": "normalization_value_error",
                "message": "Source evidence cannot satisfy the H2 canonical contract",
                "context": {"exception_type": type(error).__name__},
                "outputs": {},
            }
            write_json(output / "compilation-report.json", report)
            return CompilationOutcome(report, 6)
        report = {
            "schema_version": 1,
            "status": "compiled",
            "stage": "complete",
            "source_archive": source_archive,
            "bundle_id": contracts.source_manifest.bundle_id,
            "code": "contracts_compiled",
            "message": "H2 contracts compiled successfully",
            "counts": {
                "content": len(contracts.content_records),
                "routes": len(contracts.routes),
                "assets": len(contracts.assets),
                "seo": len(contracts.seo),
                "redirects": len(contracts.redirects),
                "capabilities": len(contracts.capabilities),
                "visual_targets": len(contracts.visual_capture_plan.targets),
                "parity_rows": len(contracts.parity_matrix),
                "findings": len(contracts.findings),
                "decisions": len(contracts.decisions),
            },
            "outputs": {
                "contract_index": "contract-index.json",
                "files": len(index.files),
            },
        }
        write_json(output / "compilation-report.json", report)
        return CompilationOutcome(report, 0)
