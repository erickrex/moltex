"""H1 intake orchestration and failure-safe report emission."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from moltex_harness.models import Finding, IntakeReport, IntakeResult

from .adapters import select_adapter
from .archive import ArchiveLimits, SafeArchive
from .errors import HarnessError, IntakeError
from .security import redact
from .serialization import write_json


@dataclass(frozen=True, slots=True)
class InspectionOutcome:
    result: IntakeResult
    exit_code: int


class IntakeService:
    """Inspect one untrusted archive into deterministic H1 artifacts."""

    def __init__(self, limits: ArchiveLimits | None = None) -> None:
        self.limits = limits or ArchiveLimits()

    def inspect(self, archive: Path, report_dir: Path) -> InspectionOutcome:
        archive = archive.expanduser()
        report_dir = report_dir.expanduser()
        report_path = report_dir / "intake-report.json"
        evidence_path = report_dir / "raw-source-evidence.json"
        safe_archive: SafeArchive | None = None
        adapter_name: str | None = None
        bundle_id: str | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="moltex-intake-") as temporary:
                safe_archive = SafeArchive(archive, Path(temporary), self.limits)
                safe_archive.prepare()
                adapter = select_adapter(safe_archive)
                adapter_name = adapter.name
                validation = adapter.validate(safe_archive)
                bundle_id = validation.bundle_id
                evidence = adapter.parse(safe_archive, validation)
                report = IntakeReport(
                    status="accepted",
                    source_archive=archive.name,
                    archive_sha256=safe_archive.archive_sha256,
                    adapter=adapter_name,
                    bundle_id=bundle_id,
                    limits=self.limits.serialized(),
                    inventory={
                        "files": len(safe_archive.inventory),
                        "expanded_bytes": sum(
                            item.bytes for item in safe_archive.inventory
                        ),
                    },
                    findings=evidence.findings,
                    outputs={
                        "intake_report": "intake-report.json",
                        "raw_source_evidence": "raw-source-evidence.json",
                    },
                )
                result = IntakeResult(report=report, evidence=evidence)
                write_json(evidence_path, evidence)
                write_json(report_path, report)
                return InspectionOutcome(result=result, exit_code=0)
        except IntakeError as error:
            report = self._rejection_report(
                archive,
                safe_archive,
                adapter_name,
                bundle_id,
                error,
            )
            evidence_path.unlink(missing_ok=True)
            write_json(report_path, report)
            return InspectionOutcome(
                result=IntakeResult(report=report),
                exit_code=error.exit_code,
            )
        except ValidationError as error:
            failure = IntakeError(
                "invalid_source_model",
                "Accepted source evidence could not satisfy the H1 model",
                context={"errors": len(error.errors())},
            )
            report = self._rejection_report(
                archive,
                safe_archive,
                adapter_name,
                bundle_id,
                failure,
            )
            evidence_path.unlink(missing_ok=True)
            write_json(report_path, report)
            return InspectionOutcome(
                result=IntakeResult(report=report), exit_code=failure.exit_code
            )
        except Exception as error:  # noqa: BLE001 - convert boundary failures without leaking input
            failure = HarnessError(
                "harness_failure",
                "The harness failed while inspecting the archive",
                context={"exception_type": type(error).__name__},
            )
            report = self._rejection_report(
                archive,
                safe_archive,
                adapter_name,
                bundle_id,
                failure,
                status="failed",
            )
            evidence_path.unlink(missing_ok=True)
            write_json(report_path, report)
            return InspectionOutcome(
                result=IntakeResult(report=report), exit_code=failure.exit_code
            )

    def _rejection_report(
        self,
        archive: Path,
        safe_archive: SafeArchive | None,
        adapter_name: str | None,
        bundle_id: str | None,
        error: IntakeError,
        *,
        status: str = "rejected",
    ) -> IntakeReport:
        inventory = safe_archive.inventory if safe_archive else []
        return IntakeReport(
            status=status,  # type: ignore[arg-type]
            source_archive=archive.name,
            archive_sha256=safe_archive.archive_sha256 if safe_archive else None,
            adapter=adapter_name,
            bundle_id=bundle_id,
            limits=self.limits.serialized(),
            inventory={
                "files": len(inventory),
                "expanded_bytes": sum(item.bytes for item in inventory),
            },
            findings=[
                Finding(
                    severity="error",
                    code=error.code,
                    classification=error.classification,  # type: ignore[arg-type]
                    message=error.safe_message,
                    artifact=error.artifact,
                    pointer=error.pointer,
                    context=redact(error.context),
                )
            ],
            outputs={"intake_report": "intake-report.json"},
        )
