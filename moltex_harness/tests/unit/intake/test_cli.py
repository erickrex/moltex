from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from moltex_harness.cli import app


def test_inspect_cli_writes_json_report(minimal_legacy_zip, tmp_path: Path) -> None:
    archive = minimal_legacy_zip()
    report_dir = tmp_path / "cli-report"

    result = CliRunner().invoke(
        app,
        ["inspect", str(archive), "--report-dir", str(report_dir), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "accepted"
    assert (report_dir / "intake-report.json").is_file()
    assert (report_dir / "raw-source-evidence.json").is_file()


def test_cli_uses_unsupported_export_exit_code(tmp_path: Path) -> None:
    import zipfile

    archive = tmp_path / "unknown.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("unknown.json", "{}")

    result = CliRunner().invoke(
        app,
        [
            "inspect",
            str(archive),
            "--report-dir",
            str(tmp_path / "unsupported-report"),
            "--json",
        ],
    )
    assert result.exit_code == 4
    assert json.loads(result.stdout)["findings"][0]["code"] == "unsupported_export"


def test_inspect_cli_requires_explicit_diagnostic_output(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    archive = tmp_path / "export.zip"
    archive.write_bytes(b"not-read-without-required-option")

    result = CliRunner().invoke(app, ["inspect", str(archive), "--json"])

    assert result.exit_code == 2
    assert "--report-dir" in result.output
    assert not (tmp_path / "output").exists()
