from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from moltex_harness.harness.artifacts import ArtifactStore
from moltex_harness.harness.gates import GateEvaluator
from moltex_harness.harness.models import MutationReceipt, ProcessAttempt
from moltex_harness.harness.mutations import MutationCatalog
from moltex_harness.harness.reporting import VerifierReportReader, normalize_report
from moltex_harness.harness.runner import HarnessRunner
from moltex_harness.harness.workspace import WorkspaceHandle


def test_malformed_verifier_report_is_harness_error(
    synthetic_workspace: Path,
) -> None:
    templates = (
        Path(__file__).parents[2]
        / "src/moltex_harness/scaffold/templates/verifier-schemas"
    )
    schemas = synthetic_workspace / ".moltex/schemas/verifier"
    shutil.copytree(templates, schemas)
    report = synthetic_workspace / ".moltex/reports/verification-baseline.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('{"status":"pass"}', encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed verifier report"):
        VerifierReportReader().read(synthetic_workspace, "baseline")


def test_artifact_store_rejects_missing_path_and_builds_portable_zip(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "report.json").write_text("{}", encoding="utf-8")
    store = ArtifactStore(tmp_path / "reports", "run-1")

    store.copy(source, "report.json")
    with pytest.raises((FileNotFoundError, ValueError)):
        store.copy(source, "missing.json")
    bundle = store.bundle()

    assert bundle.is_file()
    manifest = json.loads((store.root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"][0]["path"] == "report.json"


def test_gate_requires_detector_subject_contract_and_evidence() -> None:
    definition = MutationCatalog().get("route.delete-output")
    receipt = MutationReceipt(
        mutation_id=definition.mutation_id,
        check_id=definition.check_id,
        subject="/about/",
        contract_ids=("route:page:42",),
        evidence_refs=("routes.json#route:page:42",),
        layer="built-output",
        target_path="dist/about/index.html",
        before_sha256="a",
        after_sha256=None,
        before_bytes=10,
        after_bytes=None,
        diff_artifact="diff.patch",
        applied_at="2026-07-18T00:00:00Z",
    )
    report = {
        "checks": [
            {
                "check_id": "route.expected-output",
                "status": "fail",
                "subject": "/about/",
                "contract_ids": ["route:page:42"],
                "evidence_refs": ["routes.json#route:page:42"],
            }
        ]
    }

    detected, localized, specific, _, unexpected = GateEvaluator.mutation(
        report, definition, receipt
    )

    assert detected and localized and specific
    assert unexpected == ()


def test_report_normalization_removes_dynamic_preview_identity() -> None:
    report = {
        "started_at": "volatile",
        "duration_ms": 123,
        "checks": [],
        "processes": [
            {
                "command": ["C:/node.exe", "astro", "--port", "54321"],
                "pid": 42,
                "port": 54321,
                "started_at": "volatile",
                "duration_ms": 99,
                "exit_code": None,
            }
        ],
    }

    normalized = normalize_report(report)

    assert normalized["processes"][0]["command"] == [
        "<node>",
        "astro",
        "--port",
        "<port>",
    ]
    assert "pid" not in normalized["processes"][0]


def test_case_artifacts_accept_setup_logs_from_base_workspace(tmp_path: Path) -> None:
    root = tmp_path / "clone"
    site = root / "site"
    reports = site / ".moltex/reports"
    reports.mkdir(parents=True)
    report_path = reports / "verification-baseline.json"
    report_path.write_text("{}", encoding="utf-8")
    external = tmp_path / "base/processes"
    external.mkdir(parents=True)
    stdout = external / "npm-ci.stdout.log"
    stderr = external / "npm-ci.stderr.log"
    stdout.write_text("installed", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    attempt = ProcessAttempt(
        attempt=1,
        command=("C:/node.exe", "C:/npm-cli.js", "ci"),
        cwd=str(tmp_path / "base/site"),
        started_at="2026-07-18T00:00:00Z",
        duration_ms=1,
        exit_code=0,
        timed_out=False,
        crashed=False,
        cleanup_ok=True,
        classification=None,
        stdout_artifact=str(stdout),
        stderr_artifact=str(stderr),
        environment={},
    )
    store = ArtifactStore(tmp_path / "artifacts", "run")
    handle = WorkspaceHandle("case", root, site, root / "processes")

    portable = HarnessRunner._copy_case_artifacts(
        object.__new__(HarnessRunner),
        store,
        handle,
        "cases/base",
        report_path,
        (attempt,),
    )

    assert portable[0].stdout_artifact == "cases/base/processes/npm-ci.stdout.log"
    assert (store.root / portable[0].stdout_artifact).read_text() == "installed"
