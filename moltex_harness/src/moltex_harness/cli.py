"""Moltex harness command line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .contracts import CompilationService, ContractVerifier
from .intake.serialization import deterministic_json
from .intake.serialization import write_json
from .intake.service import IntakeService
from .models import TaskExecutionEvidence
from .planning import PlanningService, TaskExecutionRecorder, TaskGraphVerifier
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


@app.command("plan-workspace")
def plan_workspace_command(
    workspace: Annotated[
        Path, typer.Argument(help="Passing generated H3 Astro repository")
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Write the H4 compilation report as JSON")
    ] = False,
) -> None:
    """Generate the bounded H4 Codex task graph and planning workspace."""

    outcome = PlanningService().compile_workspace(workspace)
    if as_json:
        typer.echo(deterministic_json(outcome.report), nl=False)
    elif outcome.exit_code == 0:
        typer.echo(
            f"Compiled {outcome.report.counts['tasks']} H4 tasks into {workspace}"
        )
    else:
        typer.echo(f"H4 planning failed: {outcome.report.message}", err=True)
    if outcome.exit_code:
        raise typer.Exit(outcome.exit_code)


@app.command("verify-task-graph")
def verify_task_graph_command(
    workspace: Annotated[
        Path, typer.Argument(help="Generated H4 Astro/Codex repository")
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Write the graph report as JSON")
    ] = False,
) -> None:
    """Validate H4 task dependencies, scope, evidence, and coverage."""

    report = TaskGraphVerifier().verify(workspace)
    reports = workspace / ".moltex" / "reports"
    if reports.is_dir():
        write_json(reports / "task-graph-verification-report.json", report)
    if as_json:
        typer.echo(deterministic_json(report), nl=False)
    elif report.status == "pass":
        typer.echo(f"H4 task graph passed ({report.tasks_checked} tasks)")
    else:
        typer.echo(f"H4 task graph failed: {report.errors[0]}", err=True)
    if report.status != "pass":
        raise typer.Exit(8)


@app.command("record-task-execution")
def record_task_execution_command(
    workspace: Annotated[
        Path, typer.Argument(help="Generated H4 Astro/Codex repository")
    ],
    evidence_file: Annotated[
        Path, typer.Argument(help="TaskExecutionEvidence JSON file")
    ],
) -> None:
    """Validate and retain evidence from one real Codex Desktop task."""

    try:
        evidence = TaskExecutionEvidence.model_validate_json(
            evidence_file.read_text(encoding="utf-8")
        )
        TaskExecutionRecorder().record(workspace, evidence)
    except (OSError, ValueError) as error:
        typer.echo(f"Task execution evidence rejected: {error}", err=True)
        raise typer.Exit(8) from error
    typer.echo(f"Recorded Codex Desktop evidence for {evidence.task_id}")


@app.command("eval")
def eval_command(
    fixture: Annotated[
        str, typer.Option("--fixture", help="Immutable fixture ID")
    ] = "golden-blog",
    suite: Annotated[
        str,
        typer.Option(
            "--suite", help="clean, browser, mutations, repro, or repair"
        ),
    ] = "clean",
    mutation: Annotated[
        str | None, typer.Option("--mutation", help="Run one published mutation")
    ] = None,
    repeat: Annotated[
        int, typer.Option("--repeat", min=2, help="Fresh runs for repro suite")
    ] = 3,
    report_dir: Annotated[
        Path | None,
        typer.Option("--report-dir", help="Portable H6 report destination"),
    ] = None,
    keep_workspace: Annotated[
        bool, typer.Option("--keep-workspace", help="Retain every disposable workspace")
    ] = False,
    keep_workspace_on_failure: Annotated[
        bool,
        typer.Option(
            "--keep-workspace-on-failure",
            help="Retain only failed or harness-error workspaces",
        ),
    ] = False,
    seed: Annotated[int, typer.Option("--seed", help="Reproducible case seed")] = 1337,
    jobs: Annotated[
        int, typer.Option("--jobs", min=1, help="Bounded independent case jobs")
    ] = 1,
    timeout: Annotated[
        float,
        typer.Option("--timeout", min=1, help="Per-transition timeout in seconds"),
    ] = 180,
    as_json: Annotated[
        bool, typer.Option("--json", help="Write the H6 suite report as JSON")
    ] = False,
    list_fixtures: Annotated[
        bool, typer.Option("--list-fixtures", help="List immutable fixtures and exit")
    ] = False,
    list_mutations: Annotated[
        bool, typer.Option("--list-mutations", help="List published mutations and exit")
    ] = False,
) -> None:
    """Run isolated clean, mutation, reproducibility, or repair evaluations."""

    from .harness import FixtureRegistry, HarnessRunner
    from .harness.mutations import MutationCatalog

    if list_fixtures:
        typer.echo("\n".join(FixtureRegistry().list()))
        return
    if list_mutations:
        for item in MutationCatalog().list():
            typer.echo(f"{item.mutation_id}\t{item.check_id}")
        return
    try:
        report, destination = HarnessRunner(report_dir=report_dir).run(
            fixture_id=fixture,
            suite=suite,
            mutation_id=mutation,
            repeat=repeat,
            seed=seed,
            jobs=jobs,
            timeout_seconds=timeout,
            keep_workspace=keep_workspace,
            keep_workspace_on_failure=keep_workspace_on_failure,
        )
    except ValueError as error:
        typer.echo(f"Eval configuration rejected: {error}", err=True)
        raise typer.Exit(2) from error
    if as_json:
        typer.echo(deterministic_json(report), nl=False)
    else:
        typer.echo(
            f"H6 {suite} suite {report.status}: {report.metrics.passed_cases}/"
            f"{report.metrics.total_cases} cases; artifacts: {destination}"
        )
    if report.status == "fail":
        raise typer.Exit(1)
    if report.status == "error":
        raise typer.Exit(10)
    if report.status == "blocked":
        raise typer.Exit(11)


if __name__ == "__main__":
    app()
