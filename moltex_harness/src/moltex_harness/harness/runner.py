"""Thin H6 orchestration around the generated H5 verifier."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

from moltex_harness.intake.serialization import write_json

from .artifacts import ArtifactStore
from .fixtures import FixtureRegistry
from .gates import GateEvaluator
from .lifecycle import LifecycleRecorder
from .models import (
    EvalCaseResult,
    FailureClass,
    HarnessMode,
    HarnessSuiteReport,
    LifecycleState,
    MutationDefinition,
    ProcessAttempt,
    RepeatComparison,
    RepeatDifference,
)
from .mutations import MutationCatalog
from .processes import ProcessSupervisor
from .profiles import ProfileFactory
from .reporting import (
    VerifierReportReader,
    metrics,
    normalize_report,
    normalized_digest,
    write_junit,
)
from .toolchain import Toolchain
from .workspace import WorkspaceFactory, WorkspaceHandle


class HarnessRunner:
    def __init__(
        self,
        *,
        repository_root: Path | None = None,
        report_dir: Path | None = None,
        workspace_dir: Path | None = None,
        registry: FixtureRegistry | None = None,
        toolchain: Toolchain | None = None,
    ) -> None:
        self.registry = registry or FixtureRegistry(repository_root=repository_root)
        self.repository_root = self.registry.repository_root
        self.report_dir = (report_dir or self.repository_root / "output/harness").resolve()
        self.workspace_dir = (
            workspace_dir or self.report_dir / "workspaces"
        ).resolve()
        self.toolchain = toolchain or Toolchain.resolve()
        self.supervisor = ProcessSupervisor(
            ("CI", "PLAYWRIGHT_BROWSERS_PATH")
        )
        self.factory = WorkspaceFactory(
            self.workspace_dir, self.supervisor, self.toolchain
        )
        self.reader = VerifierReportReader()
        self.catalog = MutationCatalog()

    def run(
        self,
        *,
        fixture_id: str = "golden-blog",
        suite: str = "clean",
        mutation_id: str | None = None,
        repeat: int = 3,
        seed: int = 1337,
        jobs: int = 1,
        timeout_seconds: float = 180,
        keep_workspace: bool = False,
        keep_workspace_on_failure: bool = False,
    ) -> tuple[HarnessSuiteReport, Path]:
        fixture, source = self.registry.load(fixture_id)
        if mutation_id and suite != "mutations":
            raise ValueError("--mutation requires --suite mutations")
        if suite not in {"clean", "browser", "mutations", "repro", "repair"}:
            raise ValueError(f"Unknown eval suite: {suite}")
        if repeat < 2 and suite == "repro":
            raise ValueError("Repro suite requires --repeat of at least 2")
        mode = {
            "clean": HarnessMode.SERVE,
            "browser": HarnessMode.BROWSER,
            "mutations": HarnessMode.MUTATION,
            "repro": HarnessMode.REPRO,
            "repair": HarnessMode.REPAIR,
        }[suite]
        if mode not in fixture.supported_modes:
            raise ValueError(
                f"Fixture {fixture_id} does not support harness mode {mode.value}"
            )
        fixture_mutations = tuple(sorted(fixture.mutation_ids))
        published_mutations = tuple(
            item.mutation_id for item in self.catalog.list()
        )
        if fixture_mutations != published_mutations:
            raise ValueError(
                f"Fixture {fixture_id} mutation catalog is not pinned to the published catalog"
            )
        profile = ProfileFactory(self.repository_root, self.toolchain).create(
            fixture,
            mode,
            (suite,),
            self.workspace_dir,
            seed=seed,
            timeout_seconds=timeout_seconds,
            jobs=max(1, jobs),
        )
        self.report_dir.mkdir(parents=True, exist_ok=True)
        store = ArtifactStore(self.report_dir, profile.run_id)
        lifecycle = LifecycleRecorder(store.root / "lifecycle.jsonl")
        write_json(store.root / "profile.json", profile)
        cases: tuple[EvalCaseResult, ...] = ()
        comparison: RepeatComparison | None = None
        repair = None
        cleanup_ok = True
        try:
            if suite in {"clean", "browser"}:
                levels = (
                    ("parity",)
                    if suite == "browser"
                    else ("baseline", "migration", "parity")
                )
                cases = (
                    self._clean_case(
                        fixture,
                        source,
                        levels,
                        store,
                        lifecycle,
                        timeout_seconds,
                        keep_workspace,
                        keep_workspace_on_failure,
                    ),
                )
            elif suite == "mutations":
                selected = (
                    (self.catalog.get(mutation_id),)
                    if mutation_id
                    else tuple(
                        sorted(
                            self.catalog.list(),
                            key=lambda item: (item.requires_browser, item.mutation_id),
                        )
                    )
                )
                cases = self._mutation_suite(
                    fixture,
                    source,
                    selected,
                    store,
                    lifecycle,
                    timeout_seconds,
                    keep_workspace,
                    keep_workspace_on_failure,
                )
            elif suite == "repro":
                cases, comparison = self._repro_suite(
                    fixture,
                    source,
                    repeat,
                    store,
                    lifecycle,
                    timeout_seconds,
                    keep_workspace,
                    keep_workspace_on_failure,
                )
            else:
                from .repair import RepairEvaluator

                repair, repair_case = RepairEvaluator(self).run(
                    fixture,
                    source,
                    store,
                    lifecycle,
                    timeout_seconds=timeout_seconds,
                    keep_workspace=keep_workspace,
                    keep_workspace_on_failure=keep_workspace_on_failure,
                )
                cases = (repair_case,)
        except Exception as error:
            lifecycle.emit(LifecycleState.ERROR, str(error))
            failure_class = getattr(error, "failure_class", FailureClass.HARNESS)
            attempts = getattr(error, "attempts", ())
            cases = (
                EvalCaseResult(
                    case_id=f"{fixture_id}.{suite}.harness",
                    fixture_id=fixture_id,
                    suite=suite,
                    status="error" if failure_class != FailureClass.BLOCKED else "blocked",
                    failure_class=failure_class,
                    attempts=attempts,
                    duration_ms=0,
                    message=str(error),
                ),
            )
        finally:
            processes_clean = self.supervisor.cleanup()
            workspaces_clean = self.factory.cleanup_all()
            cleanup_ok = processes_clean and workspaces_clean
            lifecycle.emit(
                LifecycleState.STOPPED,
                "All supervised processes stopped"
                if cleanup_ok
                else "Process cleanup failed",
            )
        if not cleanup_ok:
            cases = (
                *cases,
                EvalCaseResult(
                    case_id=f"{fixture_id}.{suite}.cleanup",
                    fixture_id=fixture_id,
                    suite=suite,
                    status="error",
                    failure_class=FailureClass.HARNESS,
                    duration_ms=0,
                    message="Process or workspace cleanup left an orphan",
                ),
            )
        lifecycle.emit(LifecycleState.REPORTED, "Aggregated suite results")
        repeatability = 1.0 if comparison is None or comparison.equivalent else 0.0
        suite_metrics = metrics(cases, repeatability=repeatability)
        status = self._suite_status(cases, comparison)
        junit = write_junit(store.root / "junit.xml", suite, cases)
        report = HarnessSuiteReport(
            run_id=profile.run_id,
            fixture_id=fixture_id,
            suite=suite,
            status=status,
            profile=profile,
            cases=cases,
            metrics=suite_metrics,
            lifecycle_artifact="lifecycle.jsonl",
            junit_artifact=junit.relative_to(store.root).as_posix(),
            portable_bundle="artifacts.zip",
            repeat_comparison=comparison,
            repair=repair,
            metadata={
                "mutation_catalog_size": len(self.catalog.list()),
                "semantic_retries": 0,
            },
        )
        write_json(store.root / "summary.json", report)
        store.bundle()
        return report, store.root

    def _clean_case(
        self,
        fixture: Any,
        source: Path,
        levels: tuple[str, ...],
        store: ArtifactStore,
        lifecycle: LifecycleRecorder,
        timeout_seconds: float,
        keep_workspace: bool,
        keep_workspace_on_failure: bool,
    ) -> EvalCaseResult:
        started = time.monotonic()
        preparation = self.factory.prepare(
            f"{fixture.fixture_id}-clean",
            fixture,
            source,
            lifecycle,
            timeout_seconds=timeout_seconds,
        )
        attempts: list[ProcessAttempt] = []
        final_report: dict[str, Any] | None = None
        final_path: Path | None = None
        ok = True
        message = "Clean fixture passed all applicable deterministic gates"
        for level in levels:
            if level in {"migration", "parity"}:
                lifecycle.emit(LifecycleState.SERVING, f"Starting H5 {level} lifecycle")
            report, report_path, process_attempts = self._verify(
                preparation.handle,
                level,
                None,
                timeout_seconds,
                f"clean-{level}",
            )
            gate, detail = GateEvaluator.clean(report)
            ok = ok and gate
            if not gate:
                message = detail
            final_report, final_path = report, report_path
            copied_attempts = self._copy_case_artifacts(
                store,
                preparation.handle,
                f"cases/clean/{level}",
                report_path,
                (
                    (*preparation.attempts, *process_attempts)
                    if level == levels[0]
                    else process_attempts
                ),
            )
            attempts.extend(copied_attempts)
            if level in {"migration", "parity"}:
                lifecycle.emit(LifecycleState.READY, f"H5 {level} preview completed")
        lifecycle.emit(LifecycleState.CHECKED, message)
        retained = self._finish_workspace(
            preparation.handle,
            ok,
            keep_workspace,
            keep_workspace_on_failure,
            lifecycle,
        )
        return EvalCaseResult(
            case_id=f"{fixture.fixture_id}.clean",
            fixture_id=fixture.fixture_id,
            suite="clean",
            status="pass" if ok else "fail",
            failure_class=None if ok else FailureClass.PRODUCT,
            verifier_status=final_report["status"] if final_report else None,
            verifier_report=(
                f"cases/clean/{levels[-1]}/{final_path.name}"
                if final_path
                else None
            ),
            attempts=tuple(attempts),
            duration_ms=round((time.monotonic() - started) * 1000),
            workspace=str(preparation.handle.root) if retained else None,
            retained=retained,
            message=message,
        )

    def _mutation_suite(
        self,
        fixture: Any,
        source: Path,
        definitions: tuple[MutationDefinition, ...],
        store: ArtifactStore,
        lifecycle: LifecycleRecorder,
        timeout_seconds: float,
        keep_workspace: bool,
        keep_workspace_on_failure: bool,
    ) -> tuple[EvalCaseResult, ...]:
        base = self.factory.prepare(
            f"{fixture.fixture_id}-mutation-base",
            fixture,
            source,
            lifecycle,
            timeout_seconds=timeout_seconds,
        )
        preflight, _, preflight_attempts = self._verify(
            base.handle, "parity", None, timeout_seconds, "mutation-preflight"
        )
        preflight_ok, detail = GateEvaluator.clean(preflight)
        self._copy_case_artifacts(
            store,
            base.handle,
            "cases/mutation-preflight",
            base.handle.site / ".moltex/reports/verification-parity.json",
            preflight_attempts,
        )
        if not preflight_ok:
            raise ValueError(f"Mutation base is not clean: {detail}")
        results: list[EvalCaseResult] = []
        for definition in definitions:
            results.append(
                self._mutation_case(
                    fixture,
                    base.handle,
                    definition,
                    store,
                    lifecycle,
                    timeout_seconds,
                    keep_workspace,
                    keep_workspace_on_failure,
                )
            )
        if not keep_workspace:
            self.factory.cleanup(base.handle)
        return tuple(results)

    def _mutation_case(
        self,
        fixture: Any,
        base: WorkspaceHandle,
        definition: MutationDefinition,
        store: ArtifactStore,
        lifecycle: LifecycleRecorder,
        timeout_seconds: float,
        keep_workspace: bool,
        keep_workspace_on_failure: bool,
    ) -> EvalCaseResult:
        started = time.monotonic()
        handle = self.factory.clone(base, f"{fixture.fixture_id}-{definition.mutation_id}")
        receipt_dir = handle.site / ".moltex/reports/mutations" / definition.mutation_id
        try:
            application = self.catalog.apply(
                handle.site, definition.mutation_id, receipt_dir
            )
            write_json(receipt_dir / "receipt.json", application.receipt)
            report, report_path, attempts = self._verify(
                handle,
                definition.level,
                definition.check_id,
                timeout_seconds,
                definition.mutation_id,
            )
            detected, localized, specific, primary, unexpected = GateEvaluator.mutation(
                report, definition, application.receipt
            )
            ok = detected and localized and specific
            status: Literal["pass", "fail"] = "pass" if ok else "fail"
            message = (
                "Mutation detected and correctly localized"
                if ok
                else f"Mutation evaluation mismatch: detected={detected}, localized={localized}, specific={specific}"
            )
            destination = f"cases/{definition.mutation_id.replace('.', '-') }"
            portable_attempts = self._copy_case_artifacts(
                store, handle, destination, report_path, attempts
            )
            store.copy(
                handle.site,
                receipt_dir.relative_to(handle.site).as_posix(),
                f"{destination}/mutation",
            )
            retained = self._finish_workspace(
                handle,
                ok,
                keep_workspace,
                keep_workspace_on_failure,
                lifecycle,
            )
            return EvalCaseResult(
                case_id=f"{fixture.fixture_id}.{definition.mutation_id}",
                fixture_id=fixture.fixture_id,
                suite="mutations",
                status=status,
                failure_class=None if ok else FailureClass.PRODUCT,
                mutation_id=definition.mutation_id,
                expected_check_id=definition.check_id,
                detected=detected,
                localized=localized,
                specific=specific,
                primary_subject=primary["subject"] if primary else None,
                contract_ids=tuple(primary["contract_ids"]) if primary else (),
                evidence_refs=tuple(primary["evidence_refs"]) if primary else (),
                unexpected_check_ids=unexpected,
                verifier_status=report["status"],
                verifier_report=f"{destination}/verification-{definition.level}.json",
                mutation_receipt=f"{destination}/mutation/receipt.json",
                attempts=portable_attempts,
                duration_ms=round((time.monotonic() - started) * 1000),
                workspace=str(handle.root) if retained else None,
                retained=retained,
                message=message,
            )
        except Exception as error:
            retained = self._finish_workspace(
                handle,
                False,
                keep_workspace,
                keep_workspace_on_failure,
                lifecycle,
            )
            return EvalCaseResult(
                case_id=f"{fixture.fixture_id}.{definition.mutation_id}",
                fixture_id=fixture.fixture_id,
                suite="mutations",
                status="error",
                failure_class=FailureClass.HARNESS,
                mutation_id=definition.mutation_id,
                expected_check_id=definition.check_id,
                duration_ms=round((time.monotonic() - started) * 1000),
                workspace=str(handle.root) if retained else None,
                retained=retained,
                message=str(error),
            )

    def _repro_suite(
        self,
        fixture: Any,
        source: Path,
        repeat: int,
        store: ArtifactStore,
        lifecycle: LifecycleRecorder,
        timeout_seconds: float,
        keep_workspace: bool,
        keep_workspace_on_failure: bool,
    ) -> tuple[tuple[EvalCaseResult, ...], RepeatComparison]:
        cases: list[EvalCaseResult] = []
        reference: dict[str, str] | None = None
        differences: list[RepeatDifference] = []
        artifact_names = (
            ".moltex/contracts/contract-index.json",
            ".moltex/verification/baseline-expectations.json",
            ".moltex/reports/built-route-inventory.json",
            ".moltex/reports/built-asset-inventory.json",
        )
        for index in range(1, repeat + 1):
            started = time.monotonic()
            preparation = self.factory.prepare(
                f"{fixture.fixture_id}-repro-{index}",
                fixture,
                source,
                lifecycle,
                timeout_seconds=timeout_seconds,
            )
            report, report_path, verify_attempts = self._verify(
                preparation.handle,
                "migration",
                None,
                timeout_seconds,
                f"repro-{index}",
            )
            ok, message = GateEvaluator.clean(report)
            digests = {
                relative: normalized_digest(
                    normalize_report(report)
                    if relative.endswith("verification-migration.json")
                    else json.loads(
                        (preparation.handle.site / relative).read_text(encoding="utf-8")
                    )
                )
                for relative in (*artifact_names, ".moltex/reports/verification-migration.json")
            }
            if reference is None:
                reference = digests
            else:
                for relative, digest in digests.items():
                    if digest != reference[relative]:
                        differences.append(
                            RepeatDifference(
                                producer="h2-h5",
                                path=relative,
                                expected_sha256=reference[relative],
                                actual_sha256=digest,
                            )
                        )
            destination = f"cases/repro-{index}"
            portable_attempts = self._copy_case_artifacts(
                store,
                preparation.handle,
                destination,
                report_path,
                (*preparation.attempts, *verify_attempts),
            )
            retained = self._finish_workspace(
                preparation.handle,
                ok,
                keep_workspace,
                keep_workspace_on_failure,
                lifecycle,
            )
            cases.append(
                EvalCaseResult(
                    case_id=f"{fixture.fixture_id}.repro.{index}",
                    fixture_id=fixture.fixture_id,
                    suite="repro",
                    status="pass" if ok else "fail",
                    failure_class=None if ok else FailureClass.PRODUCT,
                    verifier_status=report["status"],
                    verifier_report=f"{destination}/verification-migration.json",
                    attempts=portable_attempts,
                    duration_ms=round((time.monotonic() - started) * 1000),
                    workspace=str(preparation.handle.root) if retained else None,
                    retained=retained,
                    message=message,
                )
            )
        comparison = RepeatComparison(
            repeats=repeat,
            equivalent=not differences,
            normalized_artifacts=(*artifact_names, ".moltex/reports/verification-migration.json"),
            differences=tuple(differences),
        )
        write_json(store.root / "repro-comparison.json", comparison)
        return tuple(cases), comparison

    def _verify(
        self,
        handle: WorkspaceHandle,
        level: str,
        check_id: str | None,
        timeout_seconds: float,
        name: str,
    ) -> tuple[dict[str, Any], Path, tuple[Any, ...]]:
        command = [
            str(self.toolchain.node),
            "scripts/verify.mjs",
            "--level",
            level,
        ]
        if check_id:
            command.extend(["--checks", check_id])
        attempts = self.supervisor.run(
            command,
            cwd=handle.site,
            artifact_dir=handle.process_artifacts,
            name=name.replace(".", "-"),
            timeout_seconds=timeout_seconds,
            environment=self.toolchain.environment,
            semantic=True,
            infrastructure_retries=0,
        )
        report, path = self.reader.read(handle.site, level)
        return report, path, attempts

    def _copy_case_artifacts(
        self,
        store: ArtifactStore,
        handle: WorkspaceHandle,
        destination: str,
        report_path: Path,
        attempts: tuple[ProcessAttempt, ...],
    ) -> tuple[ProcessAttempt, ...]:
        store.copy(
            handle.site,
            report_path.relative_to(handle.site).as_posix(),
            f"{destination}/{report_path.name}",
        )
        browser = handle.site / ".moltex/reports/browser"
        if browser.is_dir():
            store.copy(
                handle.site,
                browser.relative_to(handle.site).as_posix(),
                f"{destination}/browser",
            )
        http = handle.site / ".moltex/reports/http"
        if http.is_dir():
            store.copy(
                handle.site,
                http.relative_to(handle.site).as_posix(),
                f"{destination}/http",
            )
        copied: set[Path] = set()
        portable: list[ProcessAttempt] = []
        for attempt in attempts:
            artifact_paths: dict[str, str] = {}
            for value in (attempt.stdout_artifact, attempt.stderr_artifact):
                source = Path(value)
                target = f"{destination}/processes/{source.name}"
                artifact_paths[value] = target
                if source not in copied and source.is_file():
                    copied.add(source)
                    try:
                        relative = source.relative_to(handle.root).as_posix()
                        source_root = handle.root
                    except ValueError:
                        relative = source.name
                        source_root = source.parent
                    store.copy(source_root, relative, target)
            command = attempt.command
            if command:
                command = (
                    ("npm", *command[2:])
                    if len(command) > 1
                    and Path(command[1]).name.casefold() == "npm-cli.js"
                    else ("node", *command[1:])
                )
            portable.append(
                attempt.model_copy(
                    update={
                        "command": command,
                        "cwd": "<workspace>/site",
                        "stdout_artifact": artifact_paths[attempt.stdout_artifact],
                        "stderr_artifact": artifact_paths[attempt.stderr_artifact],
                    }
                )
            )
        return tuple(portable)

    def _finish_workspace(
        self,
        handle: WorkspaceHandle,
        passed: bool,
        keep_workspace: bool,
        keep_workspace_on_failure: bool,
        lifecycle: LifecycleRecorder,
    ) -> bool:
        retain = keep_workspace or (not passed and keep_workspace_on_failure)
        if retain:
            self.factory.retain(handle)
            lifecycle.emit(LifecycleState.RETAINED, f"Retained {handle.root}")
            return True
        cleaned = self.factory.cleanup(handle)
        lifecycle.emit(
            LifecycleState.CLEANED,
            f"Cleaned {handle.root}" if cleaned else f"Failed to clean {handle.root}",
        )
        return not cleaned

    @staticmethod
    def _suite_status(
        cases: tuple[EvalCaseResult, ...], comparison: RepeatComparison | None
    ) -> Literal["pass", "fail", "error", "blocked"]:
        if any(item.status == "error" for item in cases):
            return "error"
        if any(item.status == "blocked" for item in cases):
            return "blocked"
        if any(item.status == "fail" for item in cases):
            return "fail"
        if comparison is not None and not comparison.equivalent:
            return "fail"
        return "pass"
