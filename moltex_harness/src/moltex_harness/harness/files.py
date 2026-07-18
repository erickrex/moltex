"""Contained filesystem and stable serialization helpers for H6."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: str) -> PurePosixPath:
    if not value or "\\" in value or value.startswith("/"):
        raise ValueError(f"Unsafe relative path: {value}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError(f"Unsafe relative path: {value}")
    return path


def contained(root: Path, relative: str, *, must_exist: bool = False) -> Path:
    pure = safe_relative(relative)
    current = root.resolve(strict=True)
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            resolved = current.resolve(strict=True)
            if root.resolve(strict=True) not in resolved.parents:
                raise ValueError(f"Path escapes workspace through symlink: {relative}")
    resolved = current.resolve(strict=must_exist)
    root_resolved = root.resolve(strict=True)
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path escapes workspace: {relative}")
    return resolved


def stable_json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
