"""Versioned H6 orchestration contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HarnessModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HarnessMode(StrEnum):
    CONTRACT = "contract"
    BUILD = "build"
    SERVE = "serve"
    BROWSER = "browser"
    MUTATION = "mutation"
    REPAIR = "repair"
    REPRO = "repro"


class FailureClass(StrEnum):
    PRODUCT = "product"
    INFRASTRUCTURE = "infrastructure"
    BLOCKED = "blocked"
    HARNESS = "harness"


class LifecycleState(StrEnum):
    CREATED = "created"
    COMPILED = "compiled"
    INSTALLED = "installed"
    BUILT = "built"
    SERVING = "serving"
    READY = "ready"
    CHECKED = "checked"
    REPORTED = "reported"
    STOPPED = "stopped"
    CLEANED = "cleaned"
    RETAINED = "retained"
    ERROR = "error"


class FixtureSpec(HarnessModel):
    schema_version: Literal[1] = 1
    fixture_id: str
    source_archive: str
    source_sha256: str
    bundle_id: str
    expected_contract_artifact: str
    expected_contract_revision: str
    provenance: str
    sanitization: str
    license: str
    supported_modes: tuple[HarnessMode, ...]
    expected_warnings: tuple[str, ...] = ()
    viewport_hashes: dict[str, dict[str, str | int]]
    mutation_ids: tuple[str, ...]


class HarnessProfile(HarnessModel):
    schema_version: Literal[1] = 1
    run_id: str
    started_at: str
    source_revision: str | None
    source_dirty: bool
    fixture_id: str
    bundle_sha256: str
    expected_contract_revision: str
    compiler_version: str
    verifier_schema_version: int
    operating_system: str
    architecture: str
    python_version: str
    node_version: str
    npm_version: str
    astro_version: str
    playwright_version: str
    lockfile_sha256: str
    mode: HarnessMode
    suites: tuple[str, ...]
    browser: str
    viewports: tuple[str, ...]
    environment: dict[str, str]
    seed: int
    timeout_seconds: float
    jobs: int
    retry_policy: dict[str, int]
    workspace_root: str


class LifecycleEvent(HarnessModel):
    schema_version: Literal[1] = 1
    sequence: int = Field(ge=1)
    state: LifecycleState
    timestamp: str
    duration_ms: int = Field(ge=0)
    detail: str


class ProcessAttempt(HarnessModel):
    schema_version: Literal[1] = 1
    attempt: int = Field(ge=1)
    command: tuple[str, ...]
    cwd: str
    started_at: str
    duration_ms: int = Field(ge=0)
    exit_code: int | None
    timed_out: bool
    crashed: bool
    cleanup_ok: bool
    classification: FailureClass | None
    stdout_artifact: str
    stderr_artifact: str
    environment: dict[str, str]


class MutationDefinition(HarnessModel):
    schema_version: Literal[1] = 1
    mutation_id: str
    description: str
    check_id: str
    level: Literal["baseline", "migration", "parity"]
    layer: Literal["source", "built-output", "contract", "planning"]
    allowed_cascades: tuple[str, ...] = ()
    requires_browser: bool = False


class MutationReceipt(HarnessModel):
    schema_version: Literal[1] = 1
    mutation_id: str
    check_id: str
    subject: str
    contract_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    layer: str
    target_path: str
    before_sha256: str | None
    after_sha256: str | None
    before_bytes: int | None
    after_bytes: int | None
    diff_artifact: str
    applied_at: str


class EvalCaseResult(HarnessModel):
    schema_version: Literal[1] = 1
    case_id: str
    fixture_id: str
    suite: str
    status: Literal["pass", "fail", "error", "blocked"]
    failure_class: FailureClass | None = None
    mutation_id: str | None = None
    expected_check_id: str | None = None
    detected: bool | None = None
    localized: bool | None = None
    specific: bool | None = None
    primary_subject: str | None = None
    contract_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    unexpected_check_ids: tuple[str, ...] = ()
    verifier_status: str | None = None
    verifier_report: str | None = None
    mutation_receipt: str | None = None
    attempts: tuple[ProcessAttempt, ...] = ()
    duration_ms: int = Field(ge=0)
    workspace: str | None = None
    retained: bool = False
    message: str


class HarnessMetrics(HarnessModel):
    schema_version: Literal[1] = 1
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    detected_mutations: int = Field(ge=0)
    localized_mutations: int = Field(ge=0)
    specific_mutations: int = Field(ge=0)
    detection_recall: float = Field(ge=0, le=1)
    localization_rate: float = Field(ge=0, le=1)
    specificity_rate: float = Field(ge=0, le=1)
    cleanup_rate: float = Field(ge=0, le=1)
    repeatability_rate: float = Field(ge=0, le=1)
    total_duration_ms: int = Field(ge=0)


class RepeatDifference(HarnessModel):
    producer: str
    path: str
    expected_sha256: str
    actual_sha256: str


class RepeatComparison(HarnessModel):
    schema_version: Literal[1] = 1
    repeats: int = Field(ge=2)
    equivalent: bool
    normalized_artifacts: tuple[str, ...]
    differences: tuple[RepeatDifference, ...] = ()


class RepairReport(HarnessModel):
    schema_version: Literal[1] = 1
    case_id: str
    mutation_id: str
    status: Literal["pass", "fail", "blocked"]
    before_report: str
    task_artifact: str
    session_artifact: str
    diff_artifact: str
    after_report: str | None
    final_report: str | None
    protected_paths_unchanged: bool
    changed_files: tuple[str, ...]
    duration_ms: int = Field(ge=0)
    message: str


class HarnessSuiteReport(HarnessModel):
    schema_version: Literal[1] = 1
    run_id: str
    fixture_id: str
    suite: str
    status: Literal["pass", "fail", "error", "blocked"]
    profile: HarnessProfile
    cases: tuple[EvalCaseResult, ...]
    metrics: HarnessMetrics
    lifecycle_artifact: str
    junit_artifact: str
    portable_bundle: str | None = None
    repeat_comparison: RepeatComparison | None = None
    repair: RepairReport | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
