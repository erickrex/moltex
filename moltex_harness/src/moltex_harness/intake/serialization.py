"""Stable JSON persistence for versioned intake artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def deterministic_json(value: BaseModel | Any) -> str:
    value = _jsonable(value)
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def write_json(path: Path, value: BaseModel | Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(deterministic_json(value), encoding="utf-8", newline="\n")
    try:
        temporary.replace(path)
    except PermissionError:
        # Windows may deny replace-over-existing even when both files are in
        # the same directory. The output path is harness-owned and bounded.
        path.unlink(missing_ok=True)
        temporary.replace(path)
