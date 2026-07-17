from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from moltex_harness.cli import app


def test_compile_and_verify_contract_cli(samples_dir: Path, tmp_path: Path) -> None:
    output = tmp_path / "golden-contracts"
    runner = CliRunner()
    compile_result = runner.invoke(
        app,
        [
            "compile-contracts",
            str(samples_dir / "golden-export.zip"),
            "--output",
            str(output),
            "--json",
        ],
    )
    assert compile_result.exit_code == 0, compile_result.output
    assert json.loads(compile_result.stdout)["status"] == "compiled"

    verify_result = runner.invoke(app, ["verify-contracts", str(output), "--json"])
    assert verify_result.exit_code == 0, verify_result.output
    assert json.loads(verify_result.stdout)["status"] == "pass"
    assert (output / "source-manifest.json").is_file()
    assert (output / "site-spec.json").is_file()
    assert (output / "visual-capture-plan.json").is_file()
    assert (output / "parity-matrix.json").is_file()
