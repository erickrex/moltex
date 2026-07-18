"""Independent deterministic validation of generated H4 task workspaces."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from moltex_harness.contracts import ContractStore, ContractVerifier
from moltex_harness.intake.serialization import deterministic_json
from moltex_harness.models import (
    PlanningParityMatrix,
    SourceVisualReceipt,
    TaskFamily,
    TaskGraph,
    TaskGraphVerificationReport,
    TaskState,
)
from moltex_harness.normalize.primitives import stable_hash

from .compiler import PROTECTED_PATHS


REQUIRED_WORKSPACE_FILES = (
    "AGENTS.md",
    "EXECPLAN.md",
    "MIGRATION.md",
    "README.md",
    ".moltex/codex-goal.md",
    ".moltex/qa-plan.md",
    ".moltex/parity-matrix.json",
)


class TaskGraphVerifier:
    def verify(self, workspace: Path) -> TaskGraphVerificationReport:
        errors: list[str] = []
        checks = {
            "h3_boundary": False,
            "graph_identity": False,
            "dependencies": False,
            "bounded_scope": False,
            "evidence": False,
            "contract_coverage": False,
            "planning_artifacts": False,
            "parity_matrix": False,
        }
        graph: TaskGraph | None = None
        contracts = None
        receipt: SourceVisualReceipt | None = None
        try:
            workspace = workspace.resolve(strict=True)
            self._require_h3_boundary(workspace)
            contracts, _ = ContractStore().load(workspace / ".moltex" / "contracts")
            receipt = SourceVisualReceipt.model_validate_json(
                (workspace / ".moltex/evidence/source-visuals/capture-receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            checks["h3_boundary"] = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            errors.append(f"H3 boundary is invalid: {error}")

        try:
            graph = TaskGraph.model_validate_json(
                (workspace / ".moltex/tasks/task-graph.json").read_text(
                    encoding="utf-8"
                )
            )
            expected_graph_id = (
                "task-graph:"
                + stable_hash(
                    graph.bundle_id,
                    deterministic_json(graph.tasks),
                    length=32,
                )
            )
            if graph.graph_id != expected_graph_id:
                raise ValueError("task graph identity does not bind its task definitions")
            if contracts and graph.bundle_id != contracts.source_manifest.bundle_id:
                raise ValueError("task graph bundle does not match H2 contracts")
            checks["graph_identity"] = True
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"Task graph is invalid: {error}")

        if graph is not None:
            self._check("dependencies", checks, errors, self._dependencies, graph)
            self._check("bounded_scope", checks, errors, self._bounded_scope, graph)
            self._check(
                "evidence", checks, errors, self._evidence, workspace, graph
            )
            self._check(
                "planning_artifacts",
                checks,
                errors,
                self._planning_artifacts,
                workspace,
                graph,
            )
        if graph is not None and contracts is not None and receipt is not None:
            self._check(
                "contract_coverage",
                checks,
                errors,
                self._contract_coverage,
                graph,
                contracts,
                receipt,
            )
            self._check(
                "parity_matrix",
                checks,
                errors,
                self._parity_matrix,
                workspace,
                graph,
                contracts,
                receipt,
            )
        return TaskGraphVerificationReport(
            status="pass" if not errors and all(checks.values()) else "fail",
            bundle_id=graph.bundle_id if graph else None,
            graph_id=graph.graph_id if graph else None,
            tasks_checked=len(graph.tasks) if graph else 0,
            checks=checks,
            errors=tuple(errors),
        )

    @staticmethod
    def _check(name, checks, errors, operation, *args) -> None:
        try:
            operation(*args)
            checks[name] = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            errors.append(f"{name}: {error}")

    @staticmethod
    def _require_h3_boundary(workspace: Path) -> None:
        package = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
        if package.get("scripts", {}).get("build") is None:
            raise ValueError("generated repository has no build command")
        report = json.loads(
            (workspace / ".moltex/reports/baseline-verification-report.json").read_text(
                encoding="utf-8"
            )
        )
        if report.get("status") != "pass" or not all(
            report.get("checks", {}).values()
        ):
            raise ValueError("H3 baseline verification has not passed")
        contracts = ContractVerifier().verify(workspace / ".moltex/contracts")
        if contracts.status != "pass":
            raise ValueError(f"H2 contract verification failed: {contracts.errors[0]}")

    @staticmethod
    def _dependencies(graph: TaskGraph) -> None:
        tasks = {task.task_id: task for task in graph.tasks}
        if len(tasks) != len(graph.tasks):
            raise ValueError("task IDs must be unique")
        if tuple(sorted(tasks)) != tuple(task.task_id for task in graph.tasks):
            raise ValueError("tasks must use deterministic ascending IDs")
        for task in graph.tasks:
            missing = set(task.dependencies) - set(tasks)
            if missing:
                raise ValueError(
                    f"{task.task_id} has missing dependencies {sorted(missing)}"
                )
            if task.state == TaskState.READY and task.dependencies:
                raise ValueError(f"ready task {task.task_id} cannot have dependencies")
        roots = tuple(task.task_id for task in graph.tasks if not task.dependencies)
        if graph.root_task_ids != roots:
            raise ValueError("root_task_ids do not match dependency roots")
        if graph.final_task_id not in tasks:
            raise ValueError("final task is missing")
        expected_final_dependencies = set(tasks) - {graph.final_task_id}
        if set(tasks[graph.final_task_id].dependencies) != expected_final_dependencies:
            raise ValueError("final task must depend on every preceding task")
        pending = set(tasks)
        resolved: set[str] = set()
        while pending:
            ready = {
                task_id
                for task_id in pending
                if set(tasks[task_id].dependencies).issubset(resolved)
            }
            if not ready:
                raise ValueError("task dependencies contain a cycle")
            resolved.update(ready)
            pending -= ready

    @staticmethod
    def _bounded_scope(graph: TaskGraph) -> None:
        if not set(PROTECTED_PATHS).issubset(graph.protected_paths):
            raise ValueError("task graph does not declare every protected authority path")
        for task in graph.tasks:
            if not set(graph.protected_paths).issubset(task.forbidden_paths):
                raise ValueError(
                    f"{task.task_id} does not forbid every protected authority path"
                )
            if len(task.allowed_paths) > 12:
                raise ValueError(f"{task.task_id} has an unbounded file scope")
            for allowed in task.allowed_paths:
                if any(
                    TaskGraphVerifier._scope_contains(protected, allowed)
                    for protected in graph.protected_paths
                ):
                    raise ValueError(
                        f"{task.task_id} allows protected path {allowed}"
                    )
            if not 30 <= task.estimated_minutes <= 60:
                raise ValueError(f"{task.task_id} is outside the H4 timebox")

    @staticmethod
    def _scope_contains(scope: str, candidate: str) -> bool:
        base = scope.removesuffix("/**")
        return candidate == base or candidate.startswith(base + "/")

    @staticmethod
    def _evidence(workspace: Path, graph: TaskGraph) -> None:
        for task in graph.tasks:
            seen: set[str] = set()
            for evidence in task.evidence:
                if evidence.path in seen:
                    raise ValueError(
                        f"{task.task_id} repeats evidence {evidence.path}"
                    )
                seen.add(evidence.path)
                path = TaskGraphVerifier._contained(workspace, evidence.path)
                if not path.is_file() or path.is_symlink():
                    raise ValueError(
                        f"{task.task_id} evidence is missing or unsafe: {evidence.path}"
                    )

    @staticmethod
    def _planning_artifacts(workspace: Path, graph: TaskGraph) -> None:
        for relative in REQUIRED_WORKSPACE_FILES:
            if not TaskGraphVerifier._contained(workspace, relative).is_file():
                raise ValueError(f"required planning artifact is missing: {relative}")
        for task in graph.tasks:
            json_path = workspace / ".moltex/tasks" / f"{task.task_id}.json"
            markdown_path = workspace / ".moltex/tasks" / f"{task.task_id}.md"
            materialized = type(task).model_validate_json(
                json_path.read_text(encoding="utf-8")
            )
            if materialized != task:
                raise ValueError(f"materialized JSON differs for {task.task_id}")
            markdown = markdown_path.read_text(encoding="utf-8")
            if task.task_id not in markdown or task.objective not in html_unescape(markdown):
                raise ValueError(f"task Markdown is incomplete for {task.task_id}")

    @staticmethod
    def _contract_coverage(graph: TaskGraph, contracts, receipt: SourceVisualReceipt) -> None:
        known_contracts = {
            *(route.contract_id for route in contracts.routes),
            *(asset.asset_id for asset in contracts.assets),
            *(item.contract_id for item in contracts.seo),
            *(item.contract_id for item in contracts.redirects),
            *(item.capability_id for item in contracts.capabilities),
        }
        for task in graph.tasks:
            unknown = set(task.contract_ids) - known_contracts
            unknown.update(
                contract_id
                for evidence in task.evidence
                for contract_id in evidence.contract_ids
                if contract_id not in known_contracts
            )
            if unknown:
                raise ValueError(
                    f"{task.task_id} references unknown contracts {sorted(unknown)}"
                )
        omitted = {
            item.route_contract_id
            for item in receipt.route_availability
            if item.disposition == "omitted"
        }
        referenced = {
            contract_id for task in graph.tasks for contract_id in task.contract_ids
        }
        if omitted & referenced:
            raise ValueError("confirmed omitted routes are assigned migration tasks")
        available = {
            item.route_contract_id
            for item in receipt.route_availability
            if item.disposition == "available"
        }
        route_family_coverage = {
            contract_id
            for task in graph.tasks
            if task.family == TaskFamily.ROUTE_FAMILY
            for contract_id in task.contract_ids
        }
        if route_family_coverage != available:
            raise ValueError("available routes do not have exact route-family task coverage")
        visual_routes = {item.route_contract_id for item in receipt.evidence}
        visual_coverage = {
            contract_id
            for task in graph.tasks
            if task.family == TaskFamily.VISUAL_RECONSTRUCTION
            for contract_id in task.contract_ids
        }
        if visual_coverage != visual_routes:
            raise ValueError("visual tasks do not exactly cover captured route evidence")
        visual_by_path = {
            f".moltex/evidence/source-visuals/{item.artifact}": item
            for item in receipt.evidence
        }
        for task in graph.tasks:
            attachments = {
                item.path: item for item in task.evidence if item.kind == "visual"
            }
            for path, attachment in attachments.items():
                source = visual_by_path.get(path)
                if source is None:
                    raise ValueError(
                        f"{task.task_id} references unknown visual evidence {path}"
                    )
                if attachment.contract_ids != (source.route_contract_id,) or attachment.evidence_ids != (source.evidence_id,):
                    raise ValueError(
                        f"{task.task_id} visual evidence binding is inconsistent"
                    )
            if task.family == TaskFamily.VISUAL_RECONSTRUCTION:
                expected_paths = {
                    path
                    for path, source in visual_by_path.items()
                    if source.route_contract_id in task.contract_ids
                }
                if set(attachments) != expected_paths:
                    raise ValueError(
                        f"{task.task_id} does not attach exact route visual evidence"
                    )
        capabilities = {item.capability_id for item in contracts.capabilities}
        capability_coverage = {
            contract_id
            for task in graph.tasks
            if task.family == TaskFamily.CAPABILITY_DISPOSITION
            for contract_id in task.contract_ids
        }
        if capability_coverage != capabilities:
            raise ValueError("capability tasks do not exactly cover capability contracts")
        decisions = {item.decision_id for item in contracts.decisions}
        decision_coverage = {
            item
            for task in graph.tasks
            for item in task.blocking_decision_ids
        }
        if decision_coverage != decisions:
            raise ValueError("blocking decision coverage is incomplete")

    @staticmethod
    def _parity_matrix(workspace: Path, graph: TaskGraph, contracts, receipt) -> None:
        matrix = PlanningParityMatrix.model_validate_json(
            (workspace / ".moltex/parity-matrix.json").read_text(encoding="utf-8")
        )
        if matrix.bundle_id != graph.bundle_id:
            raise ValueError("planning parity matrix bundle mismatch")
        if {row.row_id for row in matrix.rows} != {
            row.row_id for row in contracts.parity_matrix
        }:
            raise ValueError("planning parity matrix does not cover every H2 row")
        task_ids = {task.task_id for task in graph.tasks}
        omitted = {
            item.route_contract_id: item.reason
            for item in receipt.route_availability
            if item.disposition == "omitted"
        }
        for row in matrix.rows:
            if not set(row.task_ids).issubset(task_ids):
                raise ValueError(f"parity row {row.row_id} references an unknown task")
            if row.route_contract_id in omitted:
                if row.state != "omitted" or row.task_ids or row.omission_reason != omitted[row.route_contract_id]:
                    raise ValueError(f"omitted parity row {row.row_id} is inconsistent")
            elif row.state == "omitted":
                raise ValueError(f"available parity row {row.row_id} is marked omitted")

    @staticmethod
    def _contained(workspace: Path, relative: str) -> Path:
        lexical = workspace
        for part in PurePosixPath(relative).parts:
            lexical = lexical / part
            if lexical.is_symlink():
                raise ValueError(f"symlinked workspace path is unsafe: {relative}")
        path = lexical.resolve()
        if workspace not in path.parents:
            raise ValueError(f"path escapes workspace: {relative}")
        return path


def html_unescape(value: str) -> str:
    # Imported lazily in a tiny helper to keep the verifier's comparison explicit.
    import html

    return html.unescape(value)
