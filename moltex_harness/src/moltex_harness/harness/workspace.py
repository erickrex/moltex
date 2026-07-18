"""Disposable, isolated H6 workspace construction."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from moltex_harness.contracts import CompilationService
from moltex_harness.planning import PlanningService
from moltex_harness.scaffold import BaselineService
from moltex_harness.visuals import SourceVisualService
from moltex_harness.visuals.service import CaptureResult

from .lifecycle import LifecycleRecorder
from .models import FailureClass, FixtureSpec, LifecycleState, ProcessAttempt
from .processes import ProcessSupervisor
from .toolchain import Toolchain


@dataclass(frozen=True, slots=True)
class WorkspaceHandle:
    case_id: str
    root: Path
    site: Path
    process_artifacts: Path


@dataclass(frozen=True, slots=True)
class WorkspacePreparation:
    handle: WorkspaceHandle
    attempts: tuple[ProcessAttempt, ...]


class FrozenFixtureCapture:
    """Render reviewed fixture evidence whose hashes are pinned in fixture.json."""

    def __init__(self, expected: dict[str, dict[str, str | int]]) -> None:
        self.expected = expected

    def capture(self, target: object) -> CaptureResult:
        viewport = getattr(target, "viewport")
        image = Image.new("RGB", (viewport.width, viewport.height), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (0, 0, viewport.width, max(1, viewport.height // 5)), fill="#17324d"
        )
        draw.rectangle(
            (
                viewport.width // 8,
                viewport.height // 3,
                viewport.width * 7 // 8,
                viewport.height * 2 // 3,
            ),
            fill="#d7e8c5",
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        data = buffer.getvalue()
        expected = self.expected[viewport.name]
        import hashlib

        digest = hashlib.sha256(data).hexdigest()
        if len(data) != expected["bytes"] or digest != expected["sha256"]:
            raise ValueError(
                f"Frozen visual fixture changed for {viewport.name}: {digest}"
            )
        return CaptureResult(data, getattr(target, "source_url"), "frozen-chromium", "1.0")


class WorkspaceFactory:
    def __init__(
        self,
        root: Path,
        supervisor: ProcessSupervisor,
        toolchain: Toolchain,
    ) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.supervisor = supervisor
        self.toolchain = toolchain
        self._handles: list[WorkspaceHandle] = []
        self._retained: set[Path] = set()

    def prepare(
        self,
        case_id: str,
        fixture: FixtureSpec,
        source_archive: Path,
        lifecycle: LifecycleRecorder,
        *,
        timeout_seconds: float,
    ) -> WorkspacePreparation:
        handle = self.create(case_id)
        lifecycle.emit(LifecycleState.CREATED, f"Created {handle.root}")
        contracts = handle.root / "contracts"
        h2 = CompilationService().compile_archive(source_archive, contracts)
        if h2.exit_code:
            raise ValueError(f"Fixture contract compilation failed: {h2.report['message']}")
        visuals = handle.root / "source-visuals"
        receipt = SourceVisualService().capture(
            contracts,
            visuals,
            FrozenFixtureCapture(fixture.viewport_hashes),
        )
        if receipt.bundle_id != fixture.bundle_id:
            raise ValueError("Frozen visual receipt is bound to the wrong fixture")
        outcome = BaselineService().compile_archive(
            source_archive, handle.site, visuals
        )
        if outcome.exit_code:
            raise ValueError(f"Fixture baseline compilation failed: {outcome.report.message}")
        lifecycle.emit(LifecycleState.COMPILED, "Compiled H1-H3 fixture workspace")
        environment = self.toolchain.environment
        install = self.supervisor.run(
            [str(self.toolchain.node), str(self.toolchain.npm_cli), "ci"],
            cwd=handle.site,
            artifact_dir=handle.process_artifacts,
            name="npm-ci",
            timeout_seconds=timeout_seconds,
            environment=environment,
            semantic=False,
            infrastructure_retries=1,
        )
        if install[-1].exit_code != 0:
            raise WorkspaceCommandError("npm ci failed", install)
        lifecycle.emit(LifecycleState.INSTALLED, "Installed exact package-lock dependencies")
        build = self.supervisor.run(
            [str(self.toolchain.node), str(self.toolchain.npm_cli), "run", "build"],
            cwd=handle.site,
            artifact_dir=handle.process_artifacts,
            name="npm-build",
            timeout_seconds=timeout_seconds,
            environment=environment,
            semantic=True,
        )
        if build[-1].exit_code != 0:
            raise WorkspaceCommandError("npm run build failed", (*install, *build))
        lifecycle.emit(LifecycleState.BUILT, "Built and baseline-verified the fixture")
        planning = PlanningService().compile_workspace(handle.site)
        if planning.exit_code:
            raise ValueError(f"Fixture H4 planning failed: {planning.report.message}")
        return WorkspacePreparation(handle, (*install, *build))

    def create(self, case_id: str) -> WorkspaceHandle:
        safe = "".join(character if character.isalnum() else "-" for character in case_id)
        root = Path(tempfile.mkdtemp(prefix=f"{safe}-", dir=self.root)).resolve()
        handle = WorkspaceHandle(
            case_id=case_id,
            root=root,
            site=root / "site",
            process_artifacts=root / "processes",
        )
        self._handles.append(handle)
        return handle

    def clone(self, source: WorkspaceHandle, case_id: str) -> WorkspaceHandle:
        target = self.create(case_id)

        def ignore(directory: str, names: list[str]) -> set[str]:
            path = Path(directory)
            ignored = {".git", ".astro"} & set(names)
            if path.name == ".moltex" and "reports" in names:
                ignored.add("reports")
            return ignored

        shutil.copytree(
            source.site,
            target.site,
            copy_function=os.link,
            ignore=ignore,
        )
        (target.site / ".moltex/reports").mkdir(parents=True, exist_ok=True)
        return target

    def retain(self, handle: WorkspaceHandle) -> None:
        self._retained.add(handle.root)

    def cleanup(self, handle: WorkspaceHandle) -> bool:
        if not handle.root.exists():
            return True
        resolved = handle.root.resolve(strict=True)
        if resolved.parent == resolved:
            raise ValueError("Refusing to clean a filesystem root")
        for attempt in range(5):
            try:
                shutil.rmtree(resolved)
                break
            except OSError:
                if attempt == 4:
                    return False
                time.sleep(0.2 * (attempt + 1))
        if handle in self._handles:
            self._handles.remove(handle)
        return not resolved.exists()

    def cleanup_all(self) -> bool:
        results = []
        for handle in tuple(self._handles):
            if handle.root in self._retained:
                continue
            try:
                results.append(self.cleanup(handle))
            except OSError:
                results.append(False)
        return all(results)


class WorkspaceCommandError(RuntimeError):
    def __init__(self, message: str, attempts: tuple[ProcessAttempt, ...]) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.failure_class = attempts[-1].classification or FailureClass.HARNESS
