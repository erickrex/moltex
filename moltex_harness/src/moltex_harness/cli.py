"""Moltex harness command line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .contracts import CompilationService, ContractVerifier
from .intake.serialization import deterministic_json
from .intake.serialization import write_json
from .intake.service import IntakeService
from .scaffold import BaselineService
from .visuals import SourceVisualService


app = typer.Typer(
    help="Inspect Moltex exports and run migration-harness workflows.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Moltex migration harness."""


@app.command("inspect")
def inspect_command(
    archive: Annotated[Path, typer.Argument(help="Moltex export ZIP to inspect")],
    report_dir: Annotated[
        Path | None,
        typer.Option("--report-dir", help="Directory for deterministic H1 reports"),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option(
            "--json", help="Write the intake report to standard output as JSON"
        ),
    ] = False,
) -> None:
    """Safely inspect an export and compile raw source evidence."""

    destination = report_dir or Path("output") / "intake" / archive.stem
    outcome = IntakeService().inspect(archive, destination)
    if as_json:
        typer.echo(deterministic_json(outcome.result.report), nl=False)
    elif outcome.exit_code == 0:
        typer.echo(f"Accepted {archive.name}; reports written to {destination}")
    else:
        finding = outcome.result.report.findings[0]
        typer.echo(
            f"Rejected {archive.name}: {finding.code}: {finding.message}", err=True
        )
    if outcome.exit_code:
        raise typer.Exit(outcome.exit_code)


@app.command("compile-contracts")
def compile_contracts_command(
    archive: Annotated[Path, typer.Argument(help="Accepted Moltex export ZIP")],
    output: Annotated[
        Path,
        typer.Option("--output", help="Directory for deterministic H2 contracts"),
    ],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Write the compilation report as JSON"),
    ] = False,
) -> None:
    """Normalize one accepted export into evidence-linked migration contracts."""

    outcome = CompilationService().compile_archive(archive, output)
    if as_json:
        typer.echo(deterministic_json(outcome.report), nl=False)
    elif outcome.exit_code == 0:
        typer.echo(f"Compiled H2 contracts into {output}")
    else:
        typer.echo(
            f"Contract compilation failed: {outcome.report['code']}: {outcome.report['message']}",
            err=True,
        )
    if outcome.exit_code:
        raise typer.Exit(outcome.exit_code)


@app.command("verify-contracts")
def verify_contracts_command(
    contract_dir: Annotated[
        Path, typer.Argument(help="Materialized H2 contract directory")
    ],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Write the verification report as JSON"),
    ] = False,
) -> None:
    """Verify H2 schemas, receipts, cross-references, and evidence lineage."""

    report = ContractVerifier().verify(contract_dir)
    write_json(contract_dir / "contract-verification-report.json", report)
    if as_json:
        typer.echo(deterministic_json(report), nl=False)
    elif report.status == "pass":
        typer.echo(f"H2 contract verification passed ({report.files_checked} files)")
    else:
        typer.echo(f"H2 contract verification failed: {report.errors[0]}", err=True)
    if report.status != "pass":
        raise typer.Exit(6)


@app.command("capture-source")
def capture_source_command(
    contract_dir: Annotated[
        Path, typer.Argument(help="Verified H2 contract directory")
    ],
    output: Annotated[
        Path, typer.Option("--output", help="Protected source visual evidence directory")
    ],
) -> None:
    """Capture bundle-bound desktop and mobile source visual evidence."""

    try:
        receipt = SourceVisualService().capture(contract_dir, output)
    except Exception as error:
        typer.echo(f"Source capture failed: {error}", err=True)
        raise typer.Exit(7) from error
    typer.echo(f"Captured {len(receipt.evidence)} source visual targets into {output}")


@app.command("compile")
def compile_command(
    archive: Annotated[Path, typer.Argument(help="Accepted Moltex export ZIP")],
    output: Annotated[
        Path, typer.Option("--output", help="Generated Astro baseline repository")
    ],
    through: Annotated[
        str, typer.Option("--through", help="Compilation phase; H3 supports baseline")
    ] = "baseline",
    source_visuals: Annotated[
        Path | None,
        typer.Option("--source-visuals", help="Pre-captured bundle-bound visual receipt"),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Write the compilation report as JSON")
    ] = False,
) -> None:
    """Compile an export through the conservative H3 Astro baseline."""

    if through != "baseline":
        typer.echo("H3 only supports --through baseline", err=True)
        raise typer.Exit(2)
    outcome = BaselineService().compile_archive(archive, output, source_visuals)
    if as_json:
        typer.echo(deterministic_json(outcome.report), nl=False)
    elif outcome.exit_code == 0:
        typer.echo(f"Compiled H3 Astro baseline into {output}")
    else:
        typer.echo(f"Baseline compilation failed: {outcome.report.message}", err=True)
    if outcome.exit_code:
        raise typer.Exit(outcome.exit_code)


if __name__ == "__main__":
    app()
