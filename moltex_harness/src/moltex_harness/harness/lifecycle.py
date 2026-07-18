"""Single H6 lifecycle event stream."""

from __future__ import annotations

import time
from pathlib import Path

from moltex_harness.intake.serialization import deterministic_json

from .files import utc_now
from .models import LifecycleEvent, LifecycleState


class LifecycleRecorder:
    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self.destination.write_text("", encoding="utf-8")
        self._started = time.monotonic()
        self._last = self._started
        self._sequence = 0

    def emit(self, state: LifecycleState, detail: str) -> LifecycleEvent:
        now = time.monotonic()
        self._sequence += 1
        event = LifecycleEvent(
            sequence=self._sequence,
            state=state,
            timestamp=utc_now(),
            duration_ms=round((now - self._last) * 1000),
            detail=detail,
        )
        with self.destination.open("a", encoding="utf-8") as stream:
            stream.write(deterministic_json(event))
        self._last = now
        return event
