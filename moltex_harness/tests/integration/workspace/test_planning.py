from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from typer.testing import CliRunner

from moltex_harness.cli import app
from moltex_harness.contracts import ContractStore
from moltex_harness.intake.serialization import write_json
from moltex_harness.intake.serialization import deterministic_json
from moltex_harness.models import (
    TaskCommandResult,
    TaskExecutionEvidence,
    TaskGraph,
)
from moltex_harness.planning import (
    PlanningService,
    TaskExecutionRecorder,
    TaskGraphVerifier,
)
from moltex_harness.normalize.primitives import stable_hash
from moltex_harness.scaffold import BaselineService
from moltex_harness.visuals.service import CaptureResult, SourceVisualService


class FrozenCapture:
    def __init__(self, render) -> None:
        self.render = render

    def capture(self, target):
        return CaptureResult(
            self.render(target.viewport.width, target.viewport.height),
            target.source_url,
            "frozen-chromium",
            "1.0",
        )


def _workspace(golden_contracts, capture_png, samples_dir, tmp_path):
    contract_dir = tmp_path / "contracts"
    ContractStore().write(contract_dir, golden_contracts)
    visuals = tmp_path / "visuals"
    SourceVisualService().capture(
        contract_dir, visuals, FrozenCapture(capture_png)
    )
    workspace = tmp_path / "site"
    outcome = BaselineService().compile_archive(
        samples_dir / "golden-export.zip", workspace, visuals
    )
    assert outcome.exit_code == 0
    write_json(
        workspace / ".moltex/reports/baseline-verification-report.json",
        {
            "schema_version": 1,
            "status": "pass",
            "checks": {"fixture-h3-boundary": True},
            "errors": [],
        },
    )
    return workspace


def test_h4_workspace_is_complete_and_independently_verifiable(
    golden_contracts, capture_png, samples_dir, tmp_path
) -> None:
    workspace = _workspace(golden_contracts, capture_png, samples_dir, tmp_path)

    cli_plan = CliRunner().invoke(
        app, ["plan-workspace", str(workspace), "--json"]
    )
    report = TaskGraphVerifier().verify(workspace)

    assert cli_plan.exit_code == 0, cli_plan.output
    assert json.loads(cli_plan.stdout)["status"] == "compiled"
    assert report.status == "pass"
    assert (workspace / "AGENTS.md").is_file()
    assert (workspace / "EXECPLAN.md").is_file()
    assert (workspace / "MIGRATION.md").is_file()
    assert (workspace / "README.md").is_file()
    assert (workspace / ".moltex/codex-goal.md").is_file()
    assert (workspace / ".moltex/qa-plan.md").is_file()
    graph = TaskGraph.model_validate_json(
        (workspace / ".moltex/tasks/task-graph.json").read_text(encoding="utf-8")
    )
    assert report.tasks_checked == len(graph.tasks)
    assert all((workspace / f".moltex/tasks/{task.task_id}.md").is_file() for task in graph.tasks)

    cli = CliRunner().invoke(app, ["verify-task-graph", str(workspace), "--json"])
    assert cli.exit_code == 0, cli.output
    assert json.loads(cli.stdout)["status"] == "pass"


def test_graph_verifier_localizes_each_check_mutation(
    golden_contracts, capture_png, samples_dir, tmp_path
) -> None:
    clean = _workspace(golden_contracts, capture_png, samples_dir, tmp_path)
    assert PlanningService().compile_workspace(clean).exit_code == 0

    for check in (
        "h3_boundary",
        "graph_identity",
        "dependencies",
        "bounded_scope",
        "evidence",
        "contract_coverage",
        "planning_artifacts",
        "parity_matrix",
    ):
        workspace = tmp_path / f"mutation-{check}"
        shutil.copytree(clean, workspace)
        if check == "h3_boundary":
            report_path = workspace / ".moltex/reports/baseline-verification-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["status"] = "fail"
            write_json(report_path, report)
        elif check == "graph_identity":
            path = workspace / ".moltex/tasks/task-graph.json"
            graph = json.loads(path.read_text(encoding="utf-8"))
            graph["graph_id"] = "task-graph:mutated"
            write_json(path, graph)
        elif check == "dependencies":
            graph = _load_graph(workspace)
            task = graph.tasks[1].model_copy(update={"dependencies": ("T999",)})
            _write_mutated_graph(workspace, graph, task)
        elif check == "bounded_scope":
            graph = _load_graph(workspace)
            task = graph.tasks[0].model_copy(
                update={
                    "allowed_paths": (
                        *graph.tasks[0].allowed_paths,
                        ".moltex/contracts/site-spec.json",
                    )
                }
            )
            _write_mutated_graph(workspace, graph, task)
        elif check == "evidence":
            (workspace / "src/data/navigation.json").unlink()
        elif check == "contract_coverage":
            graph = _load_graph(workspace)
            task = next(
                item for item in graph.tasks if item.family.value == "route-family"
            )
            changed = task.model_copy(update={"contract_ids": task.contract_ids[1:]})
            _write_mutated_graph(workspace, graph, changed)
        elif check == "planning_artifacts":
            (workspace / "README.md").unlink()
        else:
            path = workspace / ".moltex/parity-matrix.json"
            matrix = json.loads(path.read_text(encoding="utf-8"))
            matrix["rows"] = matrix["rows"][1:]
            write_json(path, matrix)

        report = TaskGraphVerifier().verify(workspace)

        assert report.status == "fail", check
        assert not report.checks[check], (check, report.errors)


def test_real_task_evidence_is_scope_and_command_checked(
    golden_contracts, capture_png, samples_dir, tmp_path
) -> None:
    workspace = _workspace(golden_contracts, capture_png, samples_dir, tmp_path)
    assert PlanningService().compile_workspace(workspace).exit_code == 0
    evidence_dir = workspace / ".moltex/task-evidence/T001"
    evidence_dir.mkdir(parents=True)
    patch = evidence_dir / "changes.patch"
    session = evidence_dir / "session.md"
    patch.write_text("diff --git a/src/styles/tokens.css b/src/styles/tokens.css\n", encoding="utf-8")
    session.write_text("Codex Desktop completed the bounded foundation task.\n", encoding="utf-8")
    evidence = TaskExecutionEvidence(
        task_id="T001",
        summary="Added and verified the local design-token foundation.",
        changed_files=("src/styles/tokens.css",),
        diff_artifact=".moltex/task-evidence/T001/changes.patch",
        diff_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),
        session_artifact=".moltex/task-evidence/T001/session.md",
        session_sha256=hashlib.sha256(session.read_bytes()).hexdigest(),
        command_results=(
            TaskCommandResult(command="npm run build", exit_code=0),
            TaskCommandResult(command="npm run verify", exit_code=0),
        ),
        protected_paths_unchanged=True,
    )

    rejected = evidence.model_copy(update={"changed_files": ("package.json",)})
    with pytest.raises(ValueError, match="outside T001 scope"):
        TaskExecutionRecorder().record(workspace, rejected)
    input_path = evidence_dir / "execution-input.json"
    write_json(input_path, evidence)
    result = CliRunner().invoke(
        app, ["record-task-execution", str(workspace), str(input_path)]
    )

    assert result.exit_code == 0, result.output
    assert (evidence_dir / "execution.json").is_file()
    assert "- [x] `T001`" in (workspace / "EXECPLAN.md").read_text(
        encoding="utf-8"
    )


def _load_graph(workspace) -> TaskGraph:
    return TaskGraph.model_validate_json(
        (workspace / ".moltex/tasks/task-graph.json").read_text(encoding="utf-8")
    )


def _write_mutated_graph(workspace, graph: TaskGraph, changed_task) -> None:
    tasks = tuple(
        changed_task if task.task_id == changed_task.task_id else task
        for task in graph.tasks
    )
    graph_id = "task-graph:" + stable_hash(
        graph.bundle_id, deterministic_json(tasks), length=32
    )
    changed_graph = graph.model_copy(update={"tasks": tasks, "graph_id": graph_id})
    write_json(workspace / ".moltex/tasks/task-graph.json", changed_graph)
    write_json(
        workspace / f".moltex/tasks/{changed_task.task_id}.json", changed_task
    )
