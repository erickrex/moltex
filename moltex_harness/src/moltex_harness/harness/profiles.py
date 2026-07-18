"""Capture reproducible H6 run identity without recording secrets."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import uuid
from pathlib import Path

from moltex_harness.scaffold import NODE_VERSION, NPM_VERSION

from .files import sha256_file, utc_now
from .models import FixtureSpec, HarnessMode, HarnessProfile
from .toolchain import Toolchain


ALLOWED_ENVIRONMENT = (
    "CI",
    "MOLTEX_NODE",
    "MOLTEX_NPM_CLI",
    "PLAYWRIGHT_BROWSERS_PATH",
)


class ProfileFactory:
    def __init__(self, repository_root: Path, toolchain: Toolchain) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.toolchain = toolchain

    def create(
        self,
        fixture: FixtureSpec,
        mode: HarnessMode,
        suites: tuple[str, ...],
        workspace_root: Path,
        *,
        seed: int,
        timeout_seconds: float,
        jobs: int,
    ) -> HarnessProfile:
        started = utc_now()
        token = hashlib.sha256(
            f"{fixture.fixture_id}:{mode.value}:{seed}:{started}:{uuid.uuid4().hex}".encode()
        ).hexdigest()[:12]
        package = json.loads(
            (
                self.repository_root
                / "moltex_harness/src/moltex_harness/scaffold/templates/package.json"
            ).read_text(encoding="utf-8")
        )
        revision = self._git(["rev-parse", "HEAD"])
        dirty = bool(self._git(["status", "--porcelain"]))
        lockfile = (
            self.repository_root
            / "moltex_harness/src/moltex_harness/scaffold/templates/package-lock.json"
        )
        return HarnessProfile(
            run_id=f"{started[:10].replace('-', '')}-{token}",
            started_at=started,
            source_revision=revision or None,
            source_dirty=dirty,
            fixture_id=fixture.fixture_id,
            bundle_sha256=fixture.source_sha256,
            expected_contract_revision=fixture.expected_contract_revision,
            compiler_version="h6-harness/1",
            verifier_schema_version=1,
            operating_system=platform.system(),
            architecture=platform.machine(),
            python_version=platform.python_version(),
            node_version=NODE_VERSION,
            npm_version=NPM_VERSION,
            astro_version=package["dependencies"]["astro"],
            playwright_version=package["dependencies"]["playwright"],
            lockfile_sha256=sha256_file(lockfile),
            mode=mode,
            suites=suites,
            browser="chromium",
            viewports=("desktop-1440x1200", "mobile-500x844"),
            environment={
                key: os.environ[key]
                for key in ALLOWED_ENVIRONMENT
                if key in os.environ
            },
            seed=seed,
            timeout_seconds=timeout_seconds,
            jobs=jobs,
            retry_policy={"infrastructure": 1, "semantic": 0},
            workspace_root=str(workspace_root.resolve()),
        )

    def _git(self, arguments: list[str]) -> str:
        try:
            return subprocess.check_output(
                ["git", *arguments],
                cwd=self.repository_root,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).strip()
        except (OSError, subprocess.SubprocessError):
            return ""
