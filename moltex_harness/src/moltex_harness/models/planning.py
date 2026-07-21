"""Versioned H4 task-graph and workspace-planning models."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaskFamily(StrEnum):
    FOUNDATION = "foundation"
    GLOBAL_SHELL = "global-shell"
    ROUTE_FAMILY = "route-family"
    VISUAL_RECONSTRUCTION = "visual-reconstruction"
    CAPABILITY_DISPOSITION = "capability-disposition"
    LEGACY_ACQUISITION = "legacy-acquisition"
    PRODUCTION = "production"
    FINAL_PARITY = "final-parity"


class TaskState(StrEnum):
    READY = "ready"
    PENDING = "pending"
    BLOCKED = "blocked"
    COMPLETE = "complete"


def _workspace_path(value: str) -> str:
    if not value or "\\" in value or value.startswith("/"):
        raise ValueError("workspace paths must be non-empty relative POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError("workspace paths must remain inside the generated repository")
    return value


class TaskEvidence(PlanningModel):
    path: str
    kind: Literal["contract", "visual", "receipt", "report", "decision"]
    contract_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    reason: str = Field(min_length=1)

    _validate_path = field_validator("path")(_workspace_path)


class AcceptanceCheck(PlanningModel):
    check_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    command: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    blocking: bool = True

    @field_validator("command")
    @classmethod
    def single_line_command(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("acceptance commands must be single-line commands")
        return value


class CompletionEvidence(PlanningModel):
    kind: Literal[
        "diff", "command-report", "screenshot", "decision-record", "summary"
    ]
    path: str
    description: str = Field(min_length=1)

    _validate_path = field_validator("path")(_workspace_path)


class MigrationTask(PlanningModel):
    schema_version: Literal[1] = 1
    task_id: str = Field(pattern=r"^T[0-9]{3}$")
    family: TaskFamily
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    dependencies: tuple[str, ...] = ()
    risk: Literal["low", "medium", "high"]
    estimated_minutes: int = Field(ge=30, le=60)
    contract_ids: tuple[str, ...] = ()
    evidence: tuple[TaskEvidence, ...] = Field(min_length=1)
    allowed_paths: tuple[str, ...] = Field(min_length=1)
    forbidden_paths: tuple[str, ...] = Field(min_length=1)
    constraints: tuple[str, ...] = Field(min_length=1)
    expected_outputs: tuple[str, ...] = Field(min_length=1)
    acceptance_checks: tuple[AcceptanceCheck, ...] = Field(min_length=1)
    verification_commands: tuple[str, ...] = Field(min_length=1)
    completion_evidence: tuple[CompletionEvidence, ...] = Field(min_length=1)
    blocking_decision_ids: tuple[str, ...] = ()
    state: TaskState

    @field_validator("allowed_paths", "forbidden_paths")
    @classmethod
    def safe_scopes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_workspace_path(value) for value in values)

    @model_validator(mode="after")
    def consistent_task(self) -> "MigrationTask":
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("task dependencies must be unique")
        if self.task_id in self.dependencies:
            raise ValueError("a task cannot depend on itself")
        if len(set(self.allowed_paths)) != len(self.allowed_paths):
            raise ValueError("allowed paths must be unique")
        if len(set(self.forbidden_paths)) != len(self.forbidden_paths):
            raise ValueError("forbidden paths must be unique")
        if set(self.allowed_paths) & set(self.forbidden_paths):
            raise ValueError("allowed and forbidden paths cannot overlap")
        if self.blocking_decision_ids and self.state != TaskState.BLOCKED:
            raise ValueError("tasks with blocking decisions must be blocked")
        if self.state == TaskState.BLOCKED and not self.blocking_decision_ids:
            raise ValueError("blocked tasks must name their blocking decisions")
        commands = set(self.verification_commands)
        if any(check.command not in commands for check in self.acceptance_checks):
            raise ValueError("every acceptance command must be a verification command")
        return self


class TaskGraph(PlanningModel):
    schema_version: Literal[1] = 1
    graph_id: str
    bundle_id: str
    compiler_version: Literal["h4-planning/1"] = "h4-planning/1"
    root_task_ids: tuple[str, ...] = Field(min_length=1)
    final_task_id: str
    protected_paths: tuple[str, ...] = Field(min_length=1)
    tasks: tuple[MigrationTask, ...] = Field(min_length=1)

    @field_validator("protected_paths")
    @classmethod
    def safe_protected_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_workspace_path(value) for value in values)


class PlanningParityRow(PlanningModel):
    row_id: str
    subject_type: Literal["route", "capability"]
    subject_id: str
    route_contract_id: str | None
    capability_id: str | None
    state: Literal["pending", "blocked", "omitted", "approved"]
    required_checks: tuple[str, ...]
    task_ids: tuple[str, ...]
    omission_reason: str | None = None


class PlanningParityMatrix(PlanningModel):
    schema_version: Literal[1] = 1
    bundle_id: str
    rows: tuple[PlanningParityRow, ...]


class TaskGraphVerificationReport(PlanningModel):
    schema_version: Literal[1] = 1
    status: Literal["pass", "fail"]
    bundle_id: str | None
    graph_id: str | None
    tasks_checked: int = Field(ge=0)
    checks: dict[str, bool]
    errors: tuple[str, ...] = ()


class PlanningCompilationReport(PlanningModel):
    schema_version: Literal[1] = 1
    status: Literal["compiled", "failed"]
    bundle_id: str | None
    code: str
    message: str
    counts: dict[str, int] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)


class TaskCommandResult(PlanningModel):
    command: str
    exit_code: int
    report_path: str | None = None

    @field_validator("report_path")
    @classmethod
    def safe_optional_path(cls, value: str | None) -> str | None:
        return _workspace_path(value) if value is not None else None


class TaskExecutionEvidence(PlanningModel):
    schema_version: Literal[1] = 1
    task_id: str = Field(pattern=r"^T[0-9]{3}$")
    runner: Literal["codex-desktop"] = "codex-desktop"
    summary: str = Field(min_length=1)
    changed_files: tuple[str, ...] = Field(min_length=1)
    diff_artifact: str
    diff_sha256: str
    session_artifact: str
    session_sha256: str
    command_results: tuple[TaskCommandResult, ...] = Field(min_length=1)
    protected_paths_unchanged: bool

    @field_validator("changed_files", "diff_artifact", "session_artifact")
    @classmethod
    def safe_evidence_paths(cls, value: Any) -> Any:
        if isinstance(value, tuple):
            return tuple(_workspace_path(item) for item in value)
        return _workspace_path(value)
