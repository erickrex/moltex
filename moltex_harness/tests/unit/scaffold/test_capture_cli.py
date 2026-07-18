from __future__ import annotations

from typer.testing import CliRunner

from moltex_harness.cli import app
from moltex_harness.visuals import SourceVisualService


def test_capture_source_classifies_unexpected_backend_failure_without_traceback(
    monkeypatch, tmp_path
) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("browser runtime is unavailable")

    monkeypatch.setattr(SourceVisualService, "capture", fail)

    result = CliRunner().invoke(
        app,
        [
            "capture-source",
            str(tmp_path / "contracts"),
            "--output",
            str(tmp_path / "visuals"),
        ],
    )

    assert result.exit_code == 7
    assert "Source capture failed: browser runtime is unavailable" in result.output
    assert "Traceback" not in result.output
