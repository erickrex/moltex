"""H4 workspace-planning orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from moltex_harness.contracts import ContractStore, ContractVerifier
from moltex_harness.intake.serialization import write_json
from moltex_harness.models import (
    PlanningCompilationReport,
    SourceVisualReceipt,
)

from .compiler import TaskGraphCompiler
from .store import PlanningStore
from .verify import TaskGraphVerifier


@dataclass(frozen=True, slots=True)
class PlanningOutcome:
    report: PlanningCompilationReport
    exit_code: int


class PlanningService:
    def compile_workspace(self, workspace: Path) -> PlanningOutcome:
        original_workspace = workspace
        workspace = workspace.resolve()
        try:
            self._require_safe_targets(original_workspace, workspace)
            contracts, receipt = self._load_boundary(workspace)
            graph, matrix = TaskGraphCompiler().compile(contracts, receipt)
            PlanningStore().write(workspace, graph, matrix, contracts, receipt)
            verification = TaskGraphVerifier().verify(workspace)
            write_json(
                workspace / ".moltex/reports/task-graph-verification-report.json",
                verification,
            )
            if verification.status != "pass":
                raise ValueError(verification.errors[0])
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            report = PlanningCompilationReport(
                status="failed",
                bundle_id=None,
                code="planning_boundary_invalid",
                message=str(error),
            )
            reports = workspace / ".moltex" / "reports"
            if reports.is_dir():
                write_json(reports / "planning-compilation-report.json", report)
            return PlanningOutcome(report, 8)
        families: dict[str, int] = {}
        for task in graph.tasks:
            families[task.family.value] = families.get(task.family.value, 0) + 1
        report = PlanningCompilationReport(
            status="compiled",
            bundle_id=graph.bundle_id,
            code="workspace_planned",
            message="H4 Codex migration workspace compiled successfully",
            counts={"tasks": len(graph.tasks), **families},
            outputs={
                "task_graph": ".moltex/tasks/task-graph.json",
                "parity_matrix": ".moltex/parity-matrix.json",
                "execplan": "EXECPLAN.md",
                "verification_report": ".moltex/reports/task-graph-verification-report.json",
            },
        )
        write_json(
            workspace / ".moltex/reports/planning-compilation-report.json", report
        )
        return PlanningOutcome(report, 0)

    @staticmethod
    def _require_safe_targets(original: Path, workspace: Path) -> None:
        if original.is_symlink():
            raise ValueError("H3 workspace root cannot be a symlink")
        targets = (
            ".moltex",
            ".moltex/tasks",
            "AGENTS.md",
            "EXECPLAN.md",
            "MIGRATION.md",
            "README.md",
        )
        for relative in targets:
            candidate = workspace / relative
            if candidate.is_symlink():
                raise ValueError(f"H4 output target cannot be a symlink: {relative}")

    @staticmethod
    def _load_boundary(workspace: Path):
        if not workspace.is_dir():
            raise ValueError("H3 workspace does not exist")
        baseline_path = workspace / ".moltex/reports/baseline-verification-report.json"
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline.get("status") != "pass" or not all(
            baseline.get("checks", {}).values()
        ):
            raise ValueError("H4 requires a passing H3 baseline verification report")
        contract_dir = workspace / ".moltex/contracts"
        contract_report = ContractVerifier().verify(contract_dir)
        if contract_report.status != "pass":
            raise ValueError(
                f"H4 requires verified H2 contracts: {contract_report.errors[0]}"
            )
        contracts, _ = ContractStore().load(contract_dir)
        receipt = SourceVisualReceipt.model_validate_json(
            (
                workspace
                / ".moltex/evidence/source-visuals/capture-receipt.json"
            ).read_text(encoding="utf-8")
        )
        expectations = json.loads(
            (
                workspace / ".moltex/verification/baseline-expectations.json"
            ).read_text(encoding="utf-8")
        )
        if expectations.get("bundleId") != contracts.source_manifest.bundle_id:
            raise ValueError("H3 expectations do not match the H2 contract bundle")
        if receipt.bundle_id != contracts.source_manifest.bundle_id:
            raise ValueError("Source visual evidence does not match the H2 contract bundle")
        return contracts, receipt
