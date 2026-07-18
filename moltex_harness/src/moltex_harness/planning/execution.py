"""Validate and persist real Codex Desktop task-execution evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from moltex_harness.intake.serialization import write_json
from moltex_harness.models import TaskExecutionEvidence, TaskGraph

from .verify import TaskGraphVerifier


class TaskExecutionRecorder:
    def record(
        self, workspace: Path, evidence: TaskExecutionEvidence
    ) -> TaskExecutionEvidence:
        workspace = workspace.resolve(strict=True)
        graph_report = TaskGraphVerifier().verify(workspace)
        if graph_report.status != "pass":
            raise ValueError(
                f"Cannot record evidence for an invalid graph: {graph_report.errors[0]}"
            )
        graph = TaskGraph.model_validate_json(
            (workspace / ".moltex/tasks/task-graph.json").read_text(encoding="utf-8")
        )
        task = next(
            (item for item in graph.tasks if item.task_id == evidence.task_id), None
        )
        if task is None:
            raise ValueError(f"Unknown task ID: {evidence.task_id}")
        if not evidence.protected_paths_unchanged:
            raise ValueError("Task evidence reports a protected-authority modification")
        for changed in evidence.changed_files:
            if not any(self._matches(scope, changed) for scope in task.allowed_paths):
                raise ValueError(
                    f"Changed file is outside {task.task_id} scope: {changed}"
                )
            if any(self._matches(scope, changed) for scope in graph.protected_paths):
                raise ValueError(f"Changed file is protected: {changed}")
        commands = {item.command: item for item in evidence.command_results}
        if set(commands) != set(task.verification_commands):
            raise ValueError("Execution evidence does not cover every verification command")
        if any(item.exit_code != 0 for item in evidence.command_results):
            raise ValueError("A task verification command did not pass")
        self._verify_artifact(
            workspace, evidence.diff_artifact, evidence.diff_sha256
        )
        self._verify_artifact(
            workspace, evidence.session_artifact, evidence.session_sha256
        )
        destination = workspace / ".moltex/task-evidence" / task.task_id
        destination.mkdir(parents=True, exist_ok=True)
        write_json(destination / "execution.json", evidence)
        self._mark_execplan_complete(workspace, task.task_id)
        return evidence

    @staticmethod
    def _verify_artifact(workspace: Path, relative: str, expected: str) -> None:
        lexical = workspace
        for part in PurePosixPath(relative).parts:
            lexical = lexical / part
            if lexical.is_symlink():
                raise ValueError(f"Execution artifact is symlinked: {relative}")
        path = lexical.resolve(strict=True)
        if workspace not in path.parents or not path.is_file():
            raise ValueError(f"Execution artifact is missing or unsafe: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Execution artifact checksum mismatch: {relative}")

    @staticmethod
    def _matches(scope: str, candidate: str) -> bool:
        if scope.endswith("/**"):
            base = scope.removesuffix("/**")
            return candidate == base or candidate.startswith(base + "/")
        return candidate == scope

    @staticmethod
    def _mark_execplan_complete(workspace: Path, task_id: str) -> None:
        path = workspace / "EXECPLAN.md"
        text = path.read_text(encoding="utf-8")
        pending = f"- [ ] `{task_id}`"
        complete = f"- [x] `{task_id}`"
        if complete in text:
            return
        if text.count(pending) != 1:
            raise ValueError(f"ExecPlan has no unique row for {task_id}")
        path.write_text(text.replace(pending, complete, 1), encoding="utf-8")
