"""Orchestrate one complete site without leaking partial output directories."""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Protocol

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
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.baseline = baseline or BaselineService()
        self.builder = builder or NodeWorkspaceBuilder()
        self.planner = planner or PlanningService()
        self.identity_resolver = identity_resolver or BundleSiteIdentityResolver()
        self.run_id_factory = run_id_factory or self._new_run_id

    def create(
        self,
        archive: Path,
        output_root: Path,
        *,
        timeout_seconds: float = 900,
    ) -> SitePipelineOutcome:
        root = output_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        run_id = self.run_id_factory()
        try:
            identity = self.identity_resolver.resolve(archive)
        except ValueError as error:
            return self._failure(
                root,
                None,
                None,
                run_id,
                "preflight",
                "site_identity_invalid",
                str(error),
                3,
            )
        destination = (root / identity.workspace_slug).resolve()
        if destination.parent != root:
            return self._failure(
                root,
                identity,
                None,
                run_id,
                "preflight",
                "site_identity_unsafe",
                "Site output escapes output root",
                3,
            )
        if destination.exists():
            return self._failure(
                root,
                identity,
                None,
                run_id,
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
                    root,
                    identity,
                    workspace,
                    run_id,
                    "eligibility"
                    if baseline.report.classification == "blocked"
                    else "baseline",
                    baseline.report.code,
                    baseline.report.message,
                    6 if baseline.report.classification == "blocked" else baseline.exit_code,
                    blocked=baseline.report.classification == "blocked",
                )

            build = self.builder.build(workspace, timeout_seconds=timeout_seconds)
            if not build.success:
                return self._failure(
                    root,
                    identity,
                    workspace,
                    run_id,
                    "build",
                    build.code,
                    build.message,
                    7,
                )

            planning = self.planner.compile_workspace(workspace)
            if planning.exit_code:
                return self._failure(
                    root,
                    identity,
                    workspace,
                    run_id,
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
                status="workspace_ready",
                phase="workspace_ready",
                code="workspace_ready_for_migration",
                message="Generated site workspace is built, baseline-verified, and planned",
                output=".",
                site_identity=identity,
                counts=counts,
            )
            write_json(
                workspace / ".moltex" / "reports" / "site-pipeline-report.json",
                report,
            )
            staging = root / f".moltex-stage-{run_id}"
            try:
                if destination.exists():
                    return self._failure(
                        root,
                        identity,
                        workspace,
                        run_id,
                        "publish",
                        "output_race",
                        "Site output appeared while the pipeline was running",
                        5,
                    )
                if staging.exists():
                    return self._failure(
                        root,
                        identity,
                        workspace,
                        run_id,
                        "publish",
                        "staging_exists",
                        "Pipeline staging path already exists",
                        5,
                    )
                shutil.move(str(workspace), str(staging))
                staging.rename(destination)
            except OSError as error:
                return self._failure(
                    root,
                    identity,
                    staging if staging.exists() else workspace,
                    run_id,
                    "publish",
                    "publish_failed",
                    f"Could not publish site: {error}",
                    5,
                )
        return SitePipelineOutcome(report, 0, destination)

    @classmethod
    def _failure(
        cls,
        root: Path,
        identity: SiteIdentity | None,
        workspace: Path | None,
        run_id: str,
        phase: PipelinePhase,
        code: str,
        message: str,
        exit_code: int,
        *,
        blocked: bool = False,
    ) -> SitePipelineOutcome:
        slug = identity.workspace_slug if identity else "unknown-site"
        failure_dir = root / ".moltex-failures" / slug / run_id
        failure_dir.mkdir(parents=True, exist_ok=False)
        if workspace is not None and workspace.exists():
            cls._copy_diagnostics(workspace, failure_dir)
            if workspace.parent == root and workspace.name.startswith(".moltex-stage-"):
                shutil.rmtree(workspace)
        relative = failure_dir.relative_to(root).as_posix()
        report = SitePipelineReport(
            status="blocked" if blocked else "failed",
            phase=phase,
            code=code,
            message=message,
            output=None,
            diagnostics=relative,
            site_identity=identity,
        )
        write_json(failure_dir / "site-pipeline-report.json", report)
        return SitePipelineOutcome(report, exit_code)

    @staticmethod
    def _new_run_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid.uuid4().hex[:8]}"

    @classmethod
    def _copy_diagnostics(cls, workspace: Path, destination: Path) -> None:
        candidates: list[Path] = []
        report_root = workspace / ".moltex" / "reports"
        if report_root.is_dir():
            candidates.extend(path for path in report_root.rglob("*") if path.is_file())
        baseline_report = workspace / "baseline-compilation-report.json"
        if baseline_report.is_file():
            candidates.append(baseline_report)
        copied_bytes = 0
        for source in sorted(candidates)[:100]:
            if source.suffix.lower() not in {".json", ".log", ".txt"}:
                continue
            data = source.read_bytes()[:262_144]
            if copied_bytes + len(data) > 2_097_152:
                break
            text = data.decode("utf-8", errors="replace")
            text = cls._redact(text)
            relative = (
                source.relative_to(workspace).as_posix().replace(".moltex/", "", 1)
            )
            target = destination / "artifacts" / Path(*Path(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            copied_bytes += len(text.encode("utf-8"))

    @staticmethod
    def _redact(value: str) -> str:
        value = re.sub(
            r"(?i)(password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)"
            r"(\s*[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+",
            r"\1\2<redacted>",
            value,
        )
        return re.sub(
            r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})",
            "<redacted>",
            value,
        )
