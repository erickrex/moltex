"""Bounded, path-contained ZIP handling for hostile export archives."""

from __future__ import annotations

import hashlib
import json
import stat
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from moltex_harness.models import ArtifactInventoryItem

from .errors import IntakeError


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_archive_bytes: int = 100 * 1024 * 1024
    max_files: int = 5_000
    max_total_bytes: int = 250 * 1024 * 1024
    max_file_bytes: int = 50 * 1024 * 1024
    max_json_bytes: int = 10 * 1024 * 1024
    max_compression_ratio: float = 200.0
    max_path_depth: int = 16
    max_path_length: int = 240

    def serialized(self) -> dict[str, int | float]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_member_path(name: str, limits: ArchiveLimits) -> str:
    """Return the canonical POSIX name or reject it before extraction."""

    normalized = unicodedata.normalize("NFC", name)
    if not normalized or "\x00" in normalized:
        raise IntakeError("unsafe_path", "Archive contains an empty or NUL path")
    if any(ord(character) < 32 for character in normalized):
        raise IntakeError("unsafe_path", "Archive path contains control characters")
    if "\\" in normalized:
        raise IntakeError("unsafe_path", "Archive path contains a backslash")
    if normalized.startswith("/") or PureWindowsPath(normalized).drive:
        raise IntakeError("unsafe_path", "Archive path is absolute or drive-qualified")

    trimmed = normalized.rstrip("/")
    parts = PurePosixPath(trimmed).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise IntakeError(
            "unsafe_path", "Archive path contains traversal or dot segments"
        )
    if any(":" in part for part in parts):
        raise IntakeError(
            "unsafe_path", "Archive path contains a drive or stream separator"
        )
    canonical = "/".join(parts)
    if len(canonical) > limits.max_path_length:
        raise IntakeError(
            "path_limit", "Archive path exceeds the configured length limit"
        )
    if len(parts) > limits.max_path_depth:
        raise IntakeError(
            "path_limit", "Archive path exceeds the configured depth limit"
        )
    return canonical


class SafeArchive:
    """Preflight and extract a ZIP without trusting its member metadata."""

    def __init__(self, archive: Path, destination: Path, limits: ArchiveLimits) -> None:
        self.archive = archive
        self.destination = destination.resolve()
        self.limits = limits
        self.archive_sha256 = ""
        self.inventory: list[ArtifactInventoryItem] = []
        self._infos: list[tuple[zipfile.ZipInfo, str]] = []
        self._by_path: dict[str, ArtifactInventoryItem] = {}

    def prepare(self) -> None:
        if not self.archive.is_file():
            raise IntakeError("archive_missing", "The requested archive does not exist")
        archive_bytes = self.archive.stat().st_size
        if archive_bytes > self.limits.max_archive_bytes:
            raise IntakeError(
                "archive_limit", "Archive exceeds the configured byte limit"
            )
        self.archive_sha256 = sha256_file(self.archive)
        try:
            with zipfile.ZipFile(self.archive) as bundle:
                self._preflight(bundle)
                self._extract(bundle)
        except zipfile.BadZipFile as exc:
            raise IntakeError(
                "invalid_zip", "Input is not a valid ZIP archive"
            ) from exc

    def _preflight(self, bundle: zipfile.ZipFile) -> None:
        seen: set[str] = set()
        seen_casefold: set[str] = set()
        total = 0
        file_count = 0
        for info in bundle.infolist():
            path = normalize_member_path(info.filename, self.limits)
            folded = path.casefold()
            if path in seen:
                raise IntakeError(
                    "duplicate_path", "Archive contains a duplicate normalized path"
                )
            if folded in seen_casefold:
                raise IntakeError(
                    "case_collision", "Archive paths collide when case-folded"
                )
            seen.add(path)
            seen_casefold.add(folded)

            mode = info.external_attr >> 16
            member_type = stat.S_IFMT(mode)
            if member_type == stat.S_IFLNK:
                raise IntakeError(
                    "unsafe_member_type", "Archive contains a symbolic link"
                )
            # Some ZIP writers store only permission bits and no Unix type.
            # An explicit type must be a regular file or directory.
            if member_type and member_type not in {stat.S_IFREG, stat.S_IFDIR}:
                raise IntakeError(
                    "unsafe_member_type", "Archive contains a special file"
                )
            if info.flag_bits & 0x1:
                raise IntakeError(
                    "encrypted_member", "Encrypted archive members are unsupported"
                )
            if info.is_dir():
                continue

            file_count += 1
            total += info.file_size
            if file_count > self.limits.max_files:
                raise IntakeError(
                    "file_count_limit",
                    "Archive exceeds the configured file-count limit",
                )
            if info.file_size > self.limits.max_file_bytes:
                raise IntakeError(
                    "file_size_limit",
                    "Archive member exceeds the configured byte limit",
                )
            if total > self.limits.max_total_bytes:
                raise IntakeError(
                    "expanded_size_limit", "Archive exceeds the expanded-byte limit"
                )
            if (
                info.file_size
                and info.file_size / max(info.compress_size, 1)
                > self.limits.max_compression_ratio
            ):
                raise IntakeError(
                    "compression_ratio_limit",
                    "Archive member exceeds the compression-ratio limit",
                )
            self._infos.append((info, path))

    def _extract(self, bundle: zipfile.ZipFile) -> None:
        self.destination.mkdir(parents=True, exist_ok=True)
        actual_total = 0
        for info, path in self._infos:
            target = (self.destination / Path(*PurePosixPath(path).parts)).resolve()
            if self.destination not in target.parents:
                raise IntakeError(
                    "path_escape", "Archive member escapes the extraction directory"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            actual_size = 0
            with bundle.open(info, "r") as source, target.open("xb") as output:
                while chunk := source.read(64 * 1024):
                    actual_size += len(chunk)
                    actual_total += len(chunk)
                    if (
                        actual_size > self.limits.max_file_bytes
                        or actual_total > self.limits.max_total_bytes
                    ):
                        raise IntakeError(
                            "expanded_size_limit",
                            "Archive expanded beyond its declared limits",
                        )
                    digest.update(chunk)
                    output.write(chunk)
            if actual_size != info.file_size:
                raise IntakeError(
                    "size_mismatch",
                    "Archive member size differs from ZIP metadata",
                    artifact=path,
                )
            item = ArtifactInventoryItem(
                path=path,
                bytes=actual_size,
                compressed_bytes=info.compress_size,
                sha256=digest.hexdigest(),
            )
            self.inventory.append(item)
            self._by_path[path] = item
        self.inventory.sort(key=lambda item: item.path)

    def has(self, path: str) -> bool:
        return path in self._by_path

    def item(self, path: str) -> ArtifactInventoryItem:
        try:
            return self._by_path[path]
        except KeyError as exc:
            raise IntakeError(
                "missing_artifact", "A required artifact is missing", artifact=path
            ) from exc

    def paths(self) -> list[str]:
        return sorted(self._by_path)

    def file_path(self, path: str) -> Path:
        self.item(path)
        return self.destination / Path(*PurePosixPath(path).parts)

    def read_bytes(self, path: str, *, maximum: int | None = None) -> bytes:
        item = self.item(path)
        limit = self.limits.max_file_bytes if maximum is None else maximum
        if item.bytes > limit:
            raise IntakeError(
                "document_size_limit",
                "Artifact exceeds the parser byte limit",
                artifact=path,
            )
        return self.file_path(path).read_bytes()

    def read_text(self, path: str, *, maximum: int | None = None) -> str:
        try:
            return self.read_bytes(path, maximum=maximum).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IntakeError(
                "invalid_encoding", "Artifact is not valid UTF-8", artifact=path
            ) from exc

    def read_json(self, path: str) -> Any:
        try:
            return json.loads(self.read_text(path, maximum=self.limits.max_json_bytes))
        except json.JSONDecodeError as exc:
            raise IntakeError(
                "invalid_json",
                "Artifact contains invalid JSON",
                artifact=path,
                context={"line": exc.lineno, "column": exc.colno},
            ) from exc
