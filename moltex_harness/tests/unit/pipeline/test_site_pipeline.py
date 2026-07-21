from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from moltex_harness.models import (
    BaselineCompilationReport,
    ContractSet,
    PlanningCompilationReport,
    RawSourceEvidence,
    SiteIdentity,
)
from moltex_harness.pipeline import (
    PipelineContext,
    SitePipelineService,
    WorkspaceBuildResult,
)
from moltex_harness.planning import PlanningOutcome
from moltex_harness.scaffold.service import BaselineOutcome


class FakeBaseline:
    def compile_archive(
        self,
        archive: Path,
        output: Path,
        source_visuals: Path | None = None,
        *,
        prepared: PipelineContext | None = None,
    ) -> BaselineOutcome:
        assert archive.name == "export.zip"
        assert prepared is not None
        (output / "src").mkdir(parents=True)
        (output / "src" / "site.txt").write_text("complete", encoding="utf-8")
        (output / ".moltex" / "contracts").mkdir(parents=True)
        return BaselineOutcome(
            BaselineCompilationReport(
                status="compiled",
                bundle_id="bundle-1",
                code="baseline_compiled",
                message="compiled",
                counts={"routes": 3},
            ),
            0,
        )


class FakeBlockedBaseline:
    def compile_archive(
        self,
        archive: Path,
        output: Path,
        source_visuals: Path | None = None,
        *,
        prepared: PipelineContext | None = None,
    ) -> BaselineOutcome:
        assert prepared is not None
        output.mkdir(parents=True)
        (output / "baseline-compilation-report.json").write_text(
            '{"status":"failed","classification":"blocked"}', encoding="utf-8"
        )
        return BaselineOutcome(
            BaselineCompilationReport(
                status="failed",
                bundle_id="bundle-1",
                code="static_ineligible",
                message="WooCommerce is outside the static profile",
                classification="blocked",
            ),
            7,
        )


class FakePreparer:
    def __init__(self, workspace_slug: str = "example-com") -> None:
        self.identity = SiteIdentity(
            site_name="Example Site",
            domain="example.com",
            workspace_slug=workspace_slug,
        )
        self.calls = 0

    def prepare(self, archive: Path, root: Path) -> PipelineContext:
        self.calls += 1
        assert archive.name == "export.zip"
        extracted = root / "bundle"
        contracts = root / "contracts"
        extracted.mkdir(parents=True)
        contracts.mkdir()
        return PipelineContext(
            archive=archive,
            extracted_bundle=extracted,
            contracts_dir=contracts,
            evidence=cast(RawSourceEvidence, object()),
            contracts=cast(ContractSet, object()),
            identity=self.identity,
            metrics=(),
        )


class FakeBuilder:
    def __init__(self, success: bool = True) -> None:
        self.success = success

    def build(self, workspace: Path, *, timeout_seconds: float) -> WorkspaceBuildResult:
        assert timeout_seconds == 30
        (workspace / "dist").mkdir()
        (workspace / "dist" / "index.html").write_text("built", encoding="utf-8")
        if not self.success:
            reports = workspace / ".moltex" / "reports" / "pipeline"
            reports.mkdir(parents=True)
            (reports / "npm-build.log").write_text(
                "password=secret-value\napi_key=another-secret\n", encoding="utf-8"
            )
        return WorkspaceBuildResult(
            self.success,
            "workspace_built" if self.success else "npm_build_failed",
            "built" if self.success else "failed",
        )


class FakePlanner:
    def compile_workspace(self, workspace: Path) -> PlanningOutcome:
        (workspace / ".moltex" / "tasks").mkdir(parents=True)
        (workspace / "AGENTS.md").write_text("instructions", encoding="utf-8")
        return PlanningOutcome(
            PlanningCompilationReport(
                status="compiled",
                bundle_id="bundle-1",
                code="workspace_planned",
                message="planned",
                counts={"tasks": 4},
            ),
            0,
        )


def test_pipeline_publishes_one_migration_ready_workspace(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    destination = output_root / "example-com"
    preparer = FakePreparer()
    service = SitePipelineService(
        baseline=FakeBaseline(),
        builder=FakeBuilder(),
        planner=FakePlanner(),
        preparer=preparer,
    )

    outcome = service.create(tmp_path / "export.zip", output_root, timeout_seconds=30)

    assert outcome.exit_code == 0
    assert outcome.destination == destination.resolve()
    assert preparer.calls == 1
    assert [item.name for item in output_root.iterdir()] == ["example-com"]
    assert (destination / "src" / "site.txt").is_file()
    assert (destination / "dist" / "index.html").is_file()
    assert (destination / ".moltex" / "contracts").is_dir()
    assert (destination / ".moltex" / "tasks").is_dir()
    assert (destination / "AGENTS.md").is_file()
    report = json.loads(
        (destination / ".moltex" / "reports" / "site-pipeline-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "migration_planned"
    assert report["phase"] == "planning"
    assert report["code"] == "workspace_planned_with_unfinished_tasks"
    assert report["output"] == "."
    assert report["site_identity"] == {
        "site_name": "Example Site",
        "domain": "example.com",
        "workspace_slug": "example-com",
    }
    assert report["counts"] == {"routes": 3, "tasks": 4, "tasks_pending": 4}
    assert [stage["stage"] for stage in report["stages"]] == [
        "baseline",
        "build",
        "planning",
    ]


def test_pipeline_does_not_publish_partial_site_after_failure(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    destination = output_root / "example-com"
    service = SitePipelineService(
        baseline=FakeBaseline(),
        builder=FakeBuilder(False),
        planner=FakePlanner(),
        preparer=FakePreparer(),
    )

    outcome = service.create(tmp_path / "export.zip", output_root, timeout_seconds=30)

    assert outcome.exit_code == 7
    assert outcome.report.phase == "build"
    assert not destination.exists()
    assert not list(output_root.glob(".moltex-stage-*"))
    diagnostics = output_root / str(outcome.report.diagnostics)
    assert diagnostics.is_dir()
    report = json.loads(
        (diagnostics / "site-pipeline-report.json").read_text(encoding="utf-8")
    )
    assert report["code"] == "npm_build_failed"
    log = (diagnostics / "artifacts/reports/pipeline/npm-build.log").read_text(
        encoding="utf-8"
    )
    assert "secret-value" not in log
    assert "another-secret" not in log
    assert log.count("<redacted>") == 2


def test_pipeline_blocks_ineligible_contracts_before_build(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    destination = output_root / "example-com"
    service = SitePipelineService(
        baseline=FakeBlockedBaseline(),
        builder=FakeBuilder(),
        planner=FakePlanner(),
        preparer=FakePreparer(),
        run_id_factory=lambda: "blocked-run",
    )

    outcome = service.create(tmp_path / "export.zip", output_root, timeout_seconds=30)

    assert outcome.exit_code == 6
    assert outcome.report.status == "blocked"
    assert outcome.report.phase == "eligibility"
    assert outcome.report.code == "static_ineligible"
    assert not destination.exists()
    diagnostics = output_root / ".moltex-failures/example-com/blocked-run"
    assert (diagnostics / "site-pipeline-report.json").is_file()
    assert (diagnostics / "artifacts/baseline-compilation-report.json").is_file()


def test_pipeline_never_merges_into_an_existing_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    destination = output_root / "existing"
    destination.mkdir(parents=True)
    marker = destination / "owned.txt"
    marker.write_text("keep", encoding="utf-8")
    service = SitePipelineService(
        baseline=FakeBaseline(),
        builder=FakeBuilder(),
        planner=FakePlanner(),
        preparer=FakePreparer("existing"),
    )

    outcome = service.create(tmp_path / "export.zip", output_root, timeout_seconds=30)

    assert outcome.exit_code == 2
    assert outcome.report.code == "output_exists"
    assert marker.read_text(encoding="utf-8") == "keep"
