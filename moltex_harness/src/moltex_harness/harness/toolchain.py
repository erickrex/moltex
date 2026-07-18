"""Resolve and validate the exact H5 generated-workspace toolchain."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from moltex_harness.scaffold import NODE_VERSION, NPM_VERSION


@dataclass(frozen=True, slots=True)
class Toolchain:
    node: Path
    npm_cli: Path

    @property
    def environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PATH"] = (
            str(self.node.parent) + os.pathsep + environment.get("PATH", "")
        )
        return environment

    @classmethod
    def resolve(cls, *, allow_bootstrap: bool = True) -> "Toolchain":
        node = cls._node()
        npm = cls._npm(node, allow_bootstrap=allow_bootstrap)
        return cls(node=node, npm_cli=npm)

    @staticmethod
    def _version(command: list[str]) -> str | None:
        try:
            return subprocess.check_output(
                command, text=True, stderr=subprocess.DEVNULL, timeout=10
            ).strip()
        except (OSError, subprocess.SubprocessError):
            return None

    @classmethod
    def _node(cls) -> Path:
        executable = shutil.which("node")
        candidates = (
            os.environ.get("MOLTEX_NODE"),
            executable,
            str(
                Path.home()
                / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
            ),
        )
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                path = Path(candidate).resolve()
                if cls._version([str(path), "--version"]) == f"v{NODE_VERSION}":
                    return path
        raise ValueError(f"Node {NODE_VERSION} is required for harness evaluation")

    @classmethod
    def _npm(cls, node: Path, *, allow_bootstrap: bool) -> Path:
        executable = shutil.which("npm")
        candidates = [
            os.environ.get("MOLTEX_NPM_CLI"),
            str(Path(executable).parent / "node_modules/npm/bin/npm-cli.js")
            if executable
            else None,
            str(
                Path(tempfile.gettempdir())
                / f"moltex-h4-npm-{NPM_VERSION}/node_modules/npm/bin/npm-cli.js"
            ),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                path = Path(candidate).resolve()
                if cls._version([str(node), str(path), "--version"]) == NPM_VERSION:
                    return path
        if not allow_bootstrap:
            raise ValueError(f"npm {NPM_VERSION} is required for harness evaluation")
        bootstrap = next(
            (Path(item) for item in candidates if item and Path(item).is_file()), None
        )
        if bootstrap is None:
            raise ValueError("No npm CLI is available to acquire the pinned npm runtime")
        target = Path(tempfile.gettempdir()) / f"moltex-h6-npm-{NPM_VERSION}"
        subprocess.run(
            [
                str(node),
                str(bootstrap),
                "install",
                "--prefix",
                str(target),
                "--no-save",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                f"npm@{NPM_VERSION}",
            ],
            check=True,
            timeout=120,
        )
        acquired = target / "node_modules/npm/bin/npm-cli.js"
        if cls._version([str(node), str(acquired), "--version"]) != NPM_VERSION:
            raise ValueError(f"Failed to acquire npm {NPM_VERSION}")
        return acquired
