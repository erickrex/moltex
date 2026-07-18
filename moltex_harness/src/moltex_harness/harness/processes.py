"""Bounded subprocess execution and process-tree cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .files import utc_now
from .models import FailureClass, ProcessAttempt


TRANSIENT_MARKERS = (
    "econnreset",
    "etimedout",
    "network timeout",
    "socket hang up",
    "port is already in use",
    "address already in use",
)


@dataclass(slots=True)
class ManagedProcess:
    process: subprocess.Popen[str]
    command: tuple[str, ...]
    cwd: Path
    stdout_path: Path
    stderr_path: Path
    stdout_stream: TextIO
    stderr_stream: TextIO
    started_at: str
    started: float


class ProcessSupervisor:
    def __init__(self, environment_allowlist: tuple[str, ...] = ()) -> None:
        self.environment_allowlist = environment_allowlist
        self._managed: list[ManagedProcess] = []

    def start(
        self,
        command: list[str],
        *,
        cwd: Path,
        artifact_dir: Path,
        name: str,
        environment: dict[str, str] | None = None,
    ) -> ManagedProcess:
        if not command or any(not isinstance(item, str) for item in command):
            raise ValueError("Process commands must be non-empty argument arrays")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / f"{name}.stdout.log"
        stderr_path = artifact_dir / f"{name}.stderr.log"
        stdout_stream = stdout_path.open("w", encoding="utf-8")
        stderr_stream = stderr_path.open("w", encoding="utf-8")
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_stream,
                stderr=stderr_stream,
                text=True,
                start_new_session=os.name != "nt",
                creationflags=creationflags,
            )
        except (OSError, subprocess.SubprocessError):
            stdout_stream.close()
            stderr_stream.close()
            raise
        managed = ManagedProcess(
            process=process,
            command=tuple(command),
            cwd=cwd,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            stdout_stream=stdout_stream,
            stderr_stream=stderr_stream,
            started_at=utc_now(),
            started=time.monotonic(),
        )
        self._managed.append(managed)
        return managed

    def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        artifact_dir: Path,
        name: str,
        timeout_seconds: float,
        environment: dict[str, str] | None = None,
        semantic: bool = True,
        infrastructure_retries: int = 0,
    ) -> tuple[ProcessAttempt, ...]:
        attempts: list[ProcessAttempt] = []
        for attempt_number in range(1, infrastructure_retries + 2):
            managed = self.start(
                command,
                cwd=cwd,
                artifact_dir=artifact_dir,
                name=f"{name}-attempt-{attempt_number}",
                environment=environment,
            )
            timed_out = False
            exit_code: int | None
            try:
                exit_code = managed.process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                self.stop(managed)
                exit_code = managed.process.poll()
            finally:
                self._close_streams(managed)
            crashed = exit_code is None or exit_code < 0 or (
                not semantic
                and (exit_code in {3, 9, 134} or exit_code >= 0x80000000)
            )
            stderr = managed.stderr_path.read_text(
                encoding="utf-8", errors="replace"
            )
            classification = self._classify(
                exit_code, timed_out, crashed, stderr, semantic
            )
            cleanup_ok = managed.process.poll() is not None
            attempts.append(
                ProcessAttempt(
                    attempt=attempt_number,
                    command=managed.command,
                    cwd=str(cwd),
                    started_at=managed.started_at,
                    duration_ms=round((time.monotonic() - managed.started) * 1000),
                    exit_code=exit_code,
                    timed_out=timed_out,
                    crashed=crashed,
                    cleanup_ok=cleanup_ok,
                    classification=classification,
                    stdout_artifact=managed.stdout_path.as_posix(),
                    stderr_artifact=managed.stderr_path.as_posix(),
                    environment={
                        key: (environment or os.environ).get(key, "")
                        for key in self.environment_allowlist
                        if key in (environment or os.environ)
                    },
                )
            )
            if exit_code == 0:
                break
            if classification != FailureClass.INFRASTRUCTURE:
                break
        return tuple(attempts)

    def stop(self, managed: ManagedProcess) -> bool:
        process = managed.process
        if process.poll() is not None:
            self._close_streams(managed)
            return True
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
            else:
                getattr(os, "killpg")(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                return False
        finally:
            self._close_streams(managed)
        return process.poll() is not None

    def cleanup(self) -> bool:
        results = [self.stop(item) for item in reversed(self._managed)]
        return all(results)

    @staticmethod
    def _close_streams(managed: ManagedProcess) -> None:
        for stream in (managed.stdout_stream, managed.stderr_stream):
            if not stream.closed:
                stream.close()

    @staticmethod
    def _classify(
        exit_code: int | None,
        timed_out: bool,
        crashed: bool,
        stderr: str,
        semantic: bool,
    ) -> FailureClass | None:
        if exit_code == 0:
            return None
        if timed_out or crashed:
            return FailureClass.INFRASTRUCTURE
        if any(marker in stderr.lower() for marker in TRANSIENT_MARKERS):
            return FailureClass.INFRASTRUCTURE
        return FailureClass.PRODUCT if semantic else FailureClass.HARNESS
