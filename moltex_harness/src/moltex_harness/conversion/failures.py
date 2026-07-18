"""Shared classification used to prevent retries of semantic failures."""

from __future__ import annotations

from enum import StrEnum


class FailureClass(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    BLOCKED = "blocked"
    HARNESS = "harness"


def classify_failure(error: BaseException) -> FailureClass:
    if isinstance(error, (ConnectionError, TimeoutError)):
        return FailureClass.TRANSIENT
    if isinstance(error, (FileNotFoundError, PermissionError)):
        return FailureClass.BLOCKED
    if isinstance(error, (ValueError, UnicodeError)):
        return FailureClass.PERMANENT
    return FailureClass.HARNESS
