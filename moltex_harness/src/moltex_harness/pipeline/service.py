"""Orchestrate one complete site without leaking partial output directories."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from moltex_harness.harness.processes import ProcessSupervisor
from moltex_harness.harness.toolchain import Toolchain
from moltex_harness.intake.serialization import write_json
from moltex_harness.intake.service import IntakeService
from moltex_harness.models import PipelinePhase, SiteIdentity, SitePipelineReport
from moltex_harness.planning import PlanningOutcome, PlanningService
from moltex_harness.scaffold import BaselineService
from moltex_harness.scaffold.service import BaselineOutcome


@dataclass(frozen=True, slots=True)
class WorkspaceBuildResult:
    success: bool
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SitePipelineOutcome:
    report: SitePipelineReport
    exit_code: int
    destination: Path | None = None


class SiteIdentityResolver(Protocol):
    def resolve(self, archive: Path) -> SiteIdentity: ...


class BaselineCompiler(Protocol):
    def compile_archive(
        self, archive: Path, output: Path, source_visuals: Path | None = None
    ) -> BaselineOutcome: ...


class WorkspacePlanner(Protocol):
    def compile_workspace(self, workspace: Path) -> PlanningOutcome: ...


class WorkspaceBuilder(Protocol):
    def build(self, workspace: Path, *, timeout_seconds: float) -> WorkspaceBuildResult: ...


class BundleSiteIdentityResolver:
    """Read identity only after the bundle passes the safe H1 intake boundary."""

    def resolve(self, archive: Path) -> SiteIdentity:
        with tempfile.TemporaryDirectory(prefix="moltex-identity-") as temporary:
            outcome = IntakeService().inspect(archive, Path(temporary) / "intake")
            evidence = outcome.result.evidence
            if outcome.exit_code or evidence is None:
                findings = outcome.result.report.findings
                if findings:
                    finding = findings[0]
                    raise ValueError(f"{finding.code}: {finding.message}")
                raise ValueError("Bundle intake failed without a diagnostic finding")
            identity = evidence.source_manifest.site_identity
            if identity is None:
                raise ValueError("Accepted bundle has no resolvable site identity")
            return identity


class NodeWorkspaceBuilder:
    """Install and build with the exact generated-workspace Node toolchain."""

    def build(
        self, workspace: Path, *, timeout_seconds: float
    ) -> WorkspaceBuildResult:
        try:
            toolchain = Toolchain.resolve()
        except ValueError as error:
            return WorkspaceBuildResult(False, "toolchain_unavailable", str(error))

        reports = workspace / ".moltex" / "reports" / "pipeline"
        supervisor = ProcessSupervisor()
        try:
            install = supervisor.run(
                [str(toolchain.node), str(toolchain.npm_cli), "ci"],
                cwd=workspace,
                artifact_dir=reports,
                name="npm-ci",
                timeout_seconds=timeout_seconds,
                environment=toolchain.environment,
                semantic=False,
                infrastructure_retries=1,
            )
            if install[-1].exit_code != 0:
                return WorkspaceBuildResult(
                    False,
                    "npm_ci_failed",
                    "Locked dependency installation failed; see pipeline logs",
                )
            build = supervisor.run(
                [str(toolchain.node), str(toolchain.npm_cli), "run", "build"],
                cwd=workspace,
                artifact_dir=reports,
                name="npm-build",
                timeout_seconds=timeout_seconds,
                environment=toolchain.environment,
                semantic=True,
            )
            if build[-1].exit_code != 0:
                return WorkspaceBuildResult(
                    False,
                    "npm_build_failed",
                    "Production build or baseline verification failed; see pipeline logs",
                )
        finally:
            supervisor.cleanup()
        return WorkspaceBuildResult(
            True, "workspace_built", "Locked install and production build passed"
        )


class SitePipelineService:
    """Publish exactly one complete site directory for one accepted export."""

    def __init__(
        self,
        *,
        baseline: BaselineCompiler | None = None,
        builder: WorkspaceBuilder | None = None,
        planner: WorkspacePlanner | None = None,
        identity_resolver: SiteIdentityResolver | None = None,
    ) -> None:
        self.baseline = baseline or BaselineService()
        self.builder = builder or NodeWorkspaceBuilder()
        self.planner = planner or PlanningService()
        self.identity_resolver = identity_resolver or BundleSiteIdentityResolver()

    def create(
        self,
        archive: Path,
        output_root: Path,
        *,
        timeout_seconds: float = 900,
    ) -> SitePipelineOutcome:
        try:
            identity = self.identity_resolver.resolve(archive)
        except ValueError as error:
            return self._failure("preflight", "site_identity_invalid", str(error), 3)
        root = output_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        destination = (root / identity.workspace_slug).resolve()
        if destination.parent != root:
            return self._failure(
                "preflight", "site_identity_unsafe", "Site output escapes output root", 3
            )
        if destination.exists():
            return self._failure(
                "preflight",
                "output_exists",
                f"Site output already exists: {identity.workspace_slug}",
                2,
            )

        with tempfile.TemporaryDirectory(prefix="moltex-site-") as temporary:
            workspace = Path(temporary) / "site"
            baseline = self.baseline.compile_archive(archive, workspace)
            if baseline.exit_code:
                return self._failure(
                    "baseline",
                    baseline.report.code,
                    baseline.report.message,
                    baseline.exit_code,
                )

            build = self.builder.build(workspace, timeout_seconds=timeout_seconds)
            if not build.success:
                return self._failure("build", build.code, build.message, 7)

            planning = self.planner.compile_workspace(workspace)
            if planning.exit_code:
                return self._failure(
                    "planning",
                    planning.report.code,
                    planning.report.message,
                    planning.exit_code,
                )

            counts = {
                **baseline.report.counts,
                "tasks": planning.report.counts.get("tasks", 0),
            }
            report = SitePipelineReport(
                status="completed",
                phase="complete",
                code="site_workspace_created",
                message="Complete generated site workspace created successfully",
                output=".",
                site_identity=identity,
                counts=counts,
            )
            write_json(
                workspace / ".moltex" / "reports" / "site-pipeline-report.json",
                report,
            )
            try:
                if destination.exists():
                    return self._failure(
                        "publish",
                        "output_race",
                        "Site output appeared while the pipeline was running",
                        5,
                    )
                shutil.move(str(workspace), str(destination))
            except OSError as error:
                if destination.exists():
                    shutil.rmtree(destination)
                return self._failure(
                    "publish", "publish_failed", f"Could not publish site: {error}", 5
                )
        return SitePipelineOutcome(report, 0, destination)

    @staticmethod
    def _failure(
        phase: PipelinePhase, code: str, message: str, exit_code: int
    ) -> SitePipelineOutcome:
        report = SitePipelineReport(
            status="failed",
            phase=phase,
            code=code,
            message=message,
        )
        return SitePipelineOutcome(report, exit_code)
