"""Classified failures at the untrusted archive boundary."""

from __future__ import annotations

from typing import Any


class IntakeError(Exception):
    """A safe, user-facing intake rejection."""

    exit_code = 3
    classification = "invalid_input"

    def __init__(
        self,
        code: str,
        message: str,
        *,
        artifact: str | None = None,
        pointer: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.artifact = artifact
        self.pointer = pointer
        self.context = context or {}


class UnsupportedExportError(IntakeError):
    exit_code = 4
    classification = "unsupported_version"


class HarnessError(IntakeError):
    exit_code = 5
    classification = "harness_error"
