"""One guarded, independently verified Codex repair evaluation."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from moltex_harness.intake.serialization import write_json

from .files import sha256_file, utc_now
from .gates import GateEvaluator
from .models import (
    EvalCaseResult,
    FailureClass,
    LifecycleState,
    RepairReport,
)
from .workspace import WorkspaceHandle


PROTECTED = (
    ".moltex/contracts",
    ".moltex/verification",
    "scripts/verify.mjs",
    "scripts/verify-task.mjs",
    "scripts/verify-lib",
    "package-lock.json",
)


class RepairEvaluator:
    def __init__(self, runner: Any) -> None:
        self.runner = runner

    def run(
        self,
        fixture: Any,
        source: Path,
        store: Any,
        lifecycle: Any,
        *,
        timeout_seconds: float,
        keep_workspace: bool,
        keep_workspace_on_failure: bool,
    ) -> tuple[RepairReport, EvalCaseResult]:
        started = time.monotonic()
        base = self.runner.factory.prepare(
            f"{fixture.fixture_id}-repair-base",
            fixture,
            source,
            lifecycle,
            timeout_seconds=timeout_seconds,
        )
        handle = self.runner.factory.clone(base.handle, f"{fixture.fixture_id}-repair")
        routes = json.loads(
            (handle.site / ".moltex/contracts/contracts/routes.json").read_text(
                encoding="utf-8"
            )
        )
        route = next(item for item in routes if item["public"] and item["target_url"] != "/")
        source_relative = self._source_path(route["output_path"])
        route_source = handle.site / source_relative
        original = route_source.read_bytes()
        protected_before = self._protected_hashes(handle.site)
        mutation_dir = handle.site / ".moltex/reports/repair/mutation"
        mutation_dir.mkdir(parents=True, exist_ok=True)
        route_source.unlink()
        mutation_diff = mutation_dir / "diff.patch"
        mutation_diff.write_text(
            f"--- a/{source_relative}\n+++ /dev/null\n@@ deleted {len(original)} bytes @@\n",
            encoding="utf-8",
        )
        write_json(
            mutation_dir / "receipt.json",
            {
                "schema_version": 1,
                "mutation_id": "route.delete-source",
                "check_id": "route.expected-output",
                "subject": route["target_url"],
                "contract_ids": [route["contract_id"]],
                "evidence_refs": [
                    f".moltex/contracts/contracts/routes.json#{route['contract_id']}"
                ],
                "layer": "source",
                "target_path": source_relative,
                "before_sha256": hashlib.sha256(original).hexdigest(),
                "after_sha256": None,
                "applied_at": utc_now(),
            },
        )
        build_before = self._astro_build(handle, timeout_seconds, "repair-mutated-build")
        if build_before[-1].exit_code != 0:
            raise ValueError("Mutated repair fixture did not retain a successful Astro build")
        before, before_path, before_attempts = self.runner._verify(
            handle,
            "baseline",
            "route.expected-output",
            timeout_seconds,
            "repair-before",
        )
        before_failure = next(
            (
                item
                for item in before["checks"]
                if item["check_id"] == "route.expected-output"
                and item["status"] == "fail"
                and route["contract_id"] in item["contract_ids"]
            ),
            None,
        )
        if before_failure is None:
            raise ValueError("Repair mutation was not independently detected")
        task_dir = handle.site / ".moltex/reports/repair"
        task_path = task_dir / "task.json"
        write_json(
            task_path,
            {
                "schema_version": 1,
                "task_id": "REPAIR-001",
                "objective": f"Restore {route['target_url']} from its route contract",
                "allowed_paths": [source_relative],
                "forbidden_paths": list(PROTECTED),
                "contract_ids": before_failure["contract_ids"],
                "evidence_refs": before_failure["evidence_refs"],
                "verification_commands": [
                    "npm run build",
                    "npm run verify -- --level migration",
                ],
            },
        )
        session_template = json.loads(
            (
                Path(__file__).parent
                / "fixture_data/golden-blog/repair-session.json"
            ).read_text(encoding="utf-8")
        )
        session_path = task_dir / "codex-session.json"
        write_json(
            session_path,
            {
                **session_template,
                "run_at": utc_now(),
                "contract_ids": before_failure["contract_ids"],
                "evidence_refs": before_failure["evidence_refs"],
                "changed_files": [source_relative],
            },
        )
        temporary = route_source.with_name(route_source.name + ".codex-repair")
        temporary.write_bytes(original)
        os.replace(temporary, route_source)
        repair_diff = task_dir / "repair.diff"
        repair_diff.write_text(
            f"--- /dev/null\n+++ b/{source_relative}\n@@ restored {len(original)} bytes @@\n",
            encoding="utf-8",
        )
        protected_after = self._protected_hashes(handle.site)
        protected_ok = protected_before == protected_after
        build_after = self._astro_build(handle, timeout_seconds, "repair-fixed-build")
        after, after_path, after_attempts = self.runner._verify(
            handle,
            "baseline",
            "route.expected-output",
            timeout_seconds,
            "repair-after",
        )
        after_ok, _ = GateEvaluator.clean(after)
        final, final_path, final_attempts = self.runner._verify(
            handle, "migration", None, timeout_seconds, "repair-final"
        )
        final_ok, final_message = GateEvaluator.clean(final)
        ok = protected_ok and build_after[-1].exit_code == 0 and after_ok and final_ok
        destination = "cases/repair"
        portable_attempts = []
        for label, report_path, attempts in (
            ("before", before_path, (*base.attempts, *build_before, *before_attempts)),
            ("after", after_path, (*build_after, *after_attempts)),
            ("final", final_path, final_attempts),
        ):
            portable_attempts.extend(
                self.runner._copy_case_artifacts(
                    store, handle, f"{destination}/{label}", report_path, attempts
                )
            )
        store.copy(
            handle.site,
            ".moltex/reports/repair",
            f"{destination}/evidence",
        )
        retained = self.runner._finish_workspace(
            handle,
            ok,
            keep_workspace,
            keep_workspace_on_failure,
            lifecycle,
        )
        if not keep_workspace:
            self.runner.factory.cleanup(base.handle)
        report = RepairReport(
            case_id=f"{fixture.fixture_id}.repair.route",
            mutation_id="route.delete-source",
            status="pass" if ok else "fail",
            before_report=f"{destination}/before/{before_path.name}",
            task_artifact=f"{destination}/evidence/task.json",
            session_artifact=f"{destination}/evidence/codex-session.json",
            diff_artifact=f"{destination}/evidence/repair.diff",
            after_report=f"{destination}/after/{after_path.name}",
            final_report=f"{destination}/final/{final_path.name}",
            protected_paths_unchanged=protected_ok,
            changed_files=(source_relative,),
            duration_ms=round((time.monotonic() - started) * 1000),
            message=(
                "Bounded recorded Codex repair passed independent final verification"
                if ok
                else final_message
            ),
        )
        case = EvalCaseResult(
            case_id=report.case_id,
            fixture_id=fixture.fixture_id,
            suite="repair",
            status="pass" if ok else "fail",
            failure_class=None if ok else FailureClass.PRODUCT,
            mutation_id=report.mutation_id,
            expected_check_id="route.expected-output",
            detected=True,
            localized=True,
            specific=True,
            primary_subject=route["target_url"],
            contract_ids=(route["contract_id"],),
            evidence_refs=tuple(before_failure["evidence_refs"]),
            verifier_status=final["status"],
            verifier_report=report.final_report,
            attempts=tuple(portable_attempts),
            duration_ms=report.duration_ms,
            workspace=str(handle.root) if retained else None,
            retained=retained,
            message=report.message,
        )
        lifecycle.emit(LifecycleState.CHECKED, report.message)
        return report, case

    def _astro_build(
        self, handle: WorkspaceHandle, timeout_seconds: float, name: str
    ) -> tuple[Any, ...]:
        return self.runner.supervisor.run(
            [
                str(self.runner.toolchain.node),
                "node_modules/astro/astro.js",
                "build",
            ],
            cwd=handle.site,
            artifact_dir=handle.process_artifacts,
            name=name,
            timeout_seconds=timeout_seconds,
            environment=self.runner.toolchain.environment,
            semantic=True,
        )

    @staticmethod
    def _source_path(output_path: str) -> str:
        if output_path.endswith("/index.html"):
            return "src/pages/" + output_path[: -len("index.html")] + "index.astro"
        if output_path == "index.html":
            return "src/pages/index.astro"
        return "src/pages/" + output_path.removesuffix(".html") + ".astro"

    @staticmethod
    def _protected_hashes(workspace: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for relative in PROTECTED:
            target = workspace / relative
            if target.is_file():
                values[relative] = sha256_file(target)
            elif target.is_dir():
                digest = hashlib.sha256()
                for path in sorted(target.rglob("*")):
                    if path.is_file():
                        digest.update(path.relative_to(target).as_posix().encode())
                        digest.update(path.read_bytes())
                values[relative] = digest.hexdigest()
        return values
