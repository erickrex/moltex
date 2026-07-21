from __future__ import annotations

from unittest.mock import Mock

from moltex_harness.contracts import CompilationService
from moltex_harness.intake import IntakeService
from moltex_harness.pipeline import PipelinePreparationService


def test_pipeline_context_runs_intake_and_compilation_once(
    samples_dir, tmp_path
) -> None:
    intake = Mock(wraps=IntakeService())
    compilation = Mock(wraps=CompilationService())
    service = PipelinePreparationService(intake=intake, compilation=compilation)

    context = service.prepare(samples_dir / "golden-export.zip", tmp_path / "run")

    assert intake.inspect.call_count == 1
    assert compilation.compile_evidence.call_count == 1
    assert compilation.compile_archive.call_count == 0
    assert context.extracted_bundle.is_dir()
    assert context.contracts_dir.is_dir()
    assert context.identity.workspace_slug
    assert [metric.stage for metric in context.metrics] == ["intake", "contracts"]
    assert all(metric.artifacts > 0 for metric in context.metrics)


def test_archive_and_prepared_compilation_are_byte_equivalent(
    samples_dir, tmp_path
) -> None:
    archive = samples_dir / "golden-export.zip"
    direct = tmp_path / "direct"
    outcome = CompilationService().compile_archive(archive, direct)
    assert outcome.exit_code == 0
    context = PipelinePreparationService().prepare(archive, tmp_path / "prepared")

    direct_files = {
        path.relative_to(direct).as_posix(): path.read_bytes()
        for path in direct.rglob("*")
        if path.is_file()
    }
    prepared_files = {
        path.relative_to(context.contracts_dir).as_posix(): path.read_bytes()
        for path in context.contracts_dir.rglob("*")
        if path.is_file()
    }
    assert prepared_files == direct_files
