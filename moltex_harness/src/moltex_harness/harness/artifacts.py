"""Immutable, portable H6 run artifact storage."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from moltex_harness.intake.serialization import write_json

from .files import contained, safe_relative, sha256_file


class ArtifactStore:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = (root / run_id).resolve()
        self.root.mkdir(parents=True, exist_ok=False)

    def write(self, relative: str, value: object) -> Path:
        safe_relative(relative)
        destination = self.root / relative
        if destination.exists():
            raise ValueError(f"Artifact is immutable and already exists: {relative}")
        write_json(destination, value)
        return destination

    def copy(self, source_root: Path, relative: str, destination: str | None = None) -> Path:
        source = contained(source_root, relative, must_exist=True)
        target_relative = destination or relative
        safe_relative(target_relative)
        target = self.root / target_relative
        if target.exists():
            raise ValueError(f"Artifact is immutable and already exists: {target_relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        return target

    def manifest(self) -> Path:
        files = [
            {
                "path": path.relative_to(self.root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(self.root.rglob("*"))
            if path.is_file() and path.name not in {"manifest.json", "artifacts.zip"}
        ]
        destination = self.root / "manifest.json"
        write_json(destination, {"schema_version": 1, "files": files})
        return destination

    def bundle(self) -> Path:
        self.manifest()
        destination = self.root / "artifacts.zip"
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.root.rglob("*")):
                if not path.is_file() or path == destination:
                    continue
                relative = path.relative_to(self.root).as_posix()
                info = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        return destination

    def read_manifest(self) -> dict[str, object]:
        return json.loads(self.manifest().read_text(encoding="utf-8"))
