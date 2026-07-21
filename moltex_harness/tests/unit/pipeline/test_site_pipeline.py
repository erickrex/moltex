from __future__ import annotations

import json
from pathlib import Path

from moltex_harness.models import (
    BaselineCompilationReport,
    PlanningCompilationReport,
    SiteIdentity,
)
from moltex_harness.pipeline import (
    SitePipelineService,
    WorkspaceBuildResult,
)
from moltex_harness.planning import PlanningOutcome
from moltex_harness.scaffold.service import BaselineOutcome


class FakeBaseline:
    def compile_archive(
        self, archive: Path, output: Path, source_visuals: Path | None = None
    ) -> BaselineOutcome:
        assert archive.name == "export.zip"
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


class FakeIdentityResolver:
    def __init__(self, workspace_slug: str = "example-com") -> None:
        self.identity = SiteIdentity(
            site_name="Example Site",
            domain="example.com",
            workspace_slug=workspace_slug,
        )

    def resolve(self, archive: Path) -> SiteIdentity:
        assert archive.name == "export.zip"
        return self.identity


class FakeBuilder:
    def __init__(self, success: bool = True) -> None:
        self.success = success

    def build(
        self, workspace: Path, *, timeout_seconds: float
    ) -> WorkspaceBuildResult:
        assert timeout_seconds == 30
        (workspace / "dist").mkdir()
        (workspace / "dist" / "index.html").write_text("built", encoding="utf-8")
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


def test_pipeline_publishes_one_complete_site_folder(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    destination = output_root / "example-com"
    service = SitePipelineService(
        baseline=FakeBaseline(),
        builder=FakeBuilder(),
        planner=FakePlanner(),
        identity_resolver=FakeIdentityResolver(),
    )

    outcome = service.create(tmp_path / "export.zip", output_root, timeout_seconds=30)

    assert outcome.exit_code == 0
    assert outcome.destination == destination.resolve()
    assert [item.name for item in output_root.iterdir()] == ["example-com"]
    assert (destination / "src" / "site.txt").is_file()
    assert (destination / "dist" / "index.html").is_file()
    assert (destination / ".moltex" / "contracts").is_dir()
    assert (destination / ".moltex" / "tasks").is_dir()
    assert (destination / "AGENTS.md").is_file()
    report = json.loads(
        (
            destination / ".moltex" / "reports" / "site-pipeline-report.json"
        ).read_text(encoding="utf-8")
    )
    assert report["status"] == "completed"
    assert report["output"] == "."
    assert report["site_identity"] == {
        "site_name": "Example Site",
        "domain": "example.com",
        "workspace_slug": "example-com",
    }
    assert report["counts"] == {"routes": 3, "tasks": 4}


def test_pipeline_does_not_publish_partial_site_after_failure(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    destination = output_root / "example-com"
    service = SitePipelineService(
        baseline=FakeBaseline(),
        builder=FakeBuilder(False),
        planner=FakePlanner(),
        identity_resolver=FakeIdentityResolver(),
    )

    outcome = service.create(tmp_path / "export.zip", output_root, timeout_seconds=30)

    assert outcome.exit_code == 7
    assert outcome.report.phase == "build"
    assert not destination.exists()
    assert list(output_root.iterdir()) == []


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
        identity_resolver=FakeIdentityResolver("existing"),
    )

    outcome = service.create(tmp_path / "export.zip", output_root, timeout_seconds=30)

    assert outcome.exit_code == 2
    assert outcome.report.code == "output_exists"
    assert marker.read_text(encoding="utf-8") == "keep"
