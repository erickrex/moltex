"""Immutable prepared state shared by composed pipeline stages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns

from moltex_harness.contracts import CompilationService, ContractStore
from moltex_harness.intake.service import IntakeService
from moltex_harness.models import (
    ContractSet,
    PipelineStageReport,
    RawSourceEvidence,
    SiteIdentity,
)


@dataclass(frozen=True, slots=True)
class PipelineContext:
    archive: Path
    extracted_bundle: Path
    contracts_dir: Path
    evidence: RawSourceEvidence
    contracts: ContractSet
    identity: SiteIdentity
    metrics: tuple[PipelineStageReport, ...]
    export_timestamp: str | None = None


class PipelinePreparationError(ValueError):
    def __init__(self, code: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


class PipelinePreparationService:
    """Perform H1 and H2 exactly once for a composed site run."""

    def __init__(
        self,
        intake: IntakeService | None = None,
        compilation: CompilationService | None = None,
    ) -> None:
        self.intake = intake or IntakeService()
        self.compilation = compilation or CompilationService()

    def prepare(self, archive: Path, root: Path) -> PipelineContext:
        extraction = root / "bundle"
        intake_started = perf_counter_ns()
        intake = self.intake.inspect(
            archive, root / "intake", extraction_dir=extraction
        )
        intake_duration = self._elapsed_ms(intake_started)
        evidence = intake.result.evidence
        if intake.exit_code or evidence is None:
            finding = next(iter(intake.result.report.findings), None)
            raise PipelinePreparationError(
                finding.code if finding else "intake_failed",
                finding.message if finding else "Bundle intake failed",
                intake.exit_code or 5,
            )
        identity = evidence.source_manifest.site_identity
        if identity is None:
            raise PipelinePreparationError(
                "site_identity_invalid",
                "Accepted bundle has no resolvable site identity",
                3,
            )
        intake_metric = PipelineStageReport(
            stage="intake",
            duration_ms=intake_duration,
            artifacts=intake.result.report.inventory.get("files", 0),
            bytes=intake.result.report.inventory.get("expanded_bytes", 0),
        )

        contracts_dir = root / "contracts"
        compilation_started = perf_counter_ns()
        compilation = self.compilation.compile_evidence(
            evidence, archive.name, contracts_dir
        )
        compilation_duration = self._elapsed_ms(compilation_started)
        if compilation.exit_code:
            raise PipelinePreparationError(
                str(compilation.report.get("code", "compilation_failed")),
                str(compilation.report.get("message", "Contract compilation failed")),
                compilation.exit_code,
            )
        contracts, index = ContractStore().load(contracts_dir)
        compilation_metric = PipelineStageReport(
            stage="contracts",
            duration_ms=compilation_duration,
            artifacts=len(index.files),
            bytes=sum(item.bytes for item in index.files),
        )
        return PipelineContext(
            archive=archive.resolve(),
            extracted_bundle=extraction.resolve(),
            contracts_dir=contracts_dir.resolve(),
            evidence=evidence,
            contracts=contracts,
            identity=identity,
            metrics=(intake_metric, compilation_metric),
            export_timestamp=self._export_timestamp(extraction),
        )

    @staticmethod
    def _export_timestamp(extraction: Path) -> str | None:
        """Return the validated bundle creation time as a filesystem-safe suffix."""

        manifest = extraction / "bundle.json"
        if not manifest.is_file():
            return None
        value = json.loads(manifest.read_text(encoding="utf-8")).get("created_at")
        if not isinstance(value, str):
            return None
        try:
            created = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise PipelinePreparationError(
                "invalid_export_timestamp",
                "Bundle created_at is not a valid ISO-8601 timestamp",
                3,
            ) from error
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return created.astimezone(UTC).strftime("%Y-%m-%d_%H-%M-%S")

    @staticmethod
    def _elapsed_ms(started: int) -> int:
        return max(0, (perf_counter_ns() - started) // 1_000_000)
