"""Dynamic loopback ports and bounded readiness predicates."""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class PortAllocator:
    @staticmethod
    def allocate() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1", 0))
            return int(server.getsockname()[1])


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    ready: bool
    attempts: int
    last_status: int | None
    last_error: str | None
    duration_ms: int


class ReadinessProbe:
    def wait(
        self,
        url: str,
        *,
        timeout_seconds: float,
        interval_seconds: float = 0.1,
        accepted_statuses: tuple[int, ...] = (200,),
    ) -> ReadinessResult:
        started = time.monotonic()
        deadline = started + timeout_seconds
        attempts = 0
        last_status: int | None = None
        last_error: str | None = None
        while time.monotonic() < deadline:
            attempts += 1
            try:
                remaining = max(0.01, deadline - time.monotonic())
                with urllib.request.urlopen(url, timeout=min(1, remaining)) as response:
                    last_status = response.status
                    if response.status in accepted_statuses:
                        return ReadinessResult(
                            True,
                            attempts,
                            last_status,
                            None,
                            round((time.monotonic() - started) * 1000),
                        )
            except urllib.error.HTTPError as error:
                last_status = error.code
                last_error = str(error)
            except (OSError, urllib.error.URLError) as error:
                last_error = str(error)
            time.sleep(min(interval_seconds, max(0, deadline - time.monotonic())))
        return ReadinessResult(
            False,
            attempts,
            last_status,
            last_error,
            round((time.monotonic() - started) * 1000),
        )
