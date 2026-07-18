from __future__ import annotations

import socket
import sys
from pathlib import Path

from moltex_harness.harness.models import FailureClass
from moltex_harness.harness.processes import ProcessSupervisor
from moltex_harness.harness.readiness import PortAllocator, ReadinessProbe


def test_timeout_is_classified_and_process_is_cleaned(tmp_path: Path) -> None:
    supervisor = ProcessSupervisor()

    attempts = supervisor.run(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        artifact_dir=tmp_path / "logs",
        name="timeout",
        timeout_seconds=0.1,
        semantic=False,
    )

    assert len(attempts) == 1
    assert attempts[0].timed_out
    assert attempts[0].classification == FailureClass.INFRASTRUCTURE
    assert attempts[0].cleanup_ok
    assert supervisor.cleanup()


def test_crash_and_semantic_failure_have_distinct_retry_policy(
    tmp_path: Path,
) -> None:
    supervisor = ProcessSupervisor()
    crash = supervisor.run(
        [sys.executable, "-c", "import os; os.abort()"],
        cwd=tmp_path,
        artifact_dir=tmp_path / "logs",
        name="crash",
        timeout_seconds=5,
        semantic=False,
        infrastructure_retries=1,
    )
    semantic = supervisor.run(
        [sys.executable, "-c", "raise SystemExit(3)"],
        cwd=tmp_path,
        artifact_dir=tmp_path / "logs",
        name="semantic",
        timeout_seconds=5,
        semantic=True,
        infrastructure_retries=1,
    )

    assert len(crash) == 2
    assert all(item.classification == FailureClass.INFRASTRUCTURE for item in crash)
    assert len(semantic) == 1
    assert semantic[0].classification == FailureClass.PRODUCT


def test_readiness_has_bounded_failure_and_dynamic_port() -> None:
    port = PortAllocator.allocate()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0

    result = ReadinessProbe().wait(
        f"http://127.0.0.1:{port}/",
        timeout_seconds=0.2,
        interval_seconds=0.02,
    )

    assert not result.ready
    assert result.attempts >= 1
    assert result.duration_ms < 1000
