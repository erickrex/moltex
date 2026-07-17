from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from moltex_harness.intake.archive import ArchiveLimits, SafeArchive
from moltex_harness.intake.errors import IntakeError


@pytest.mark.parametrize(
    "member",
    [
        "../escape.json",
        "/absolute.json",
        "C:/drive.json",
        "safe/../../escape.json",
        "safe/control\x01.json",
    ],
)
def test_unsafe_member_paths_are_rejected(tmp_path: Path, member: str) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(member, b"{}")

    with pytest.raises(IntakeError) as failure:
        SafeArchive(archive, tmp_path / "out", ArchiveLimits()).prepare()

    assert failure.value.code == "unsafe_path"
    assert not (tmp_path / "escape.json").exists()


def test_backslash_path_is_rejected_by_normalizer() -> None:
    from moltex_harness.intake.archive import normalize_member_path

    with pytest.raises(IntakeError) as failure:
        normalize_member_path("safe\\windows.json", ArchiveLimits())
    assert failure.value.code == "unsafe_path"


def test_duplicate_normalized_path_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("same.json", b"{}")
        with pytest.warns(UserWarning, match="Duplicate name"):
            bundle.writestr("same.json", b"{}")

    with pytest.raises(IntakeError, match="duplicate") as failure:
        SafeArchive(archive, tmp_path / "out", ArchiveLimits()).prepare()
    assert failure.value.code == "duplicate_path"


def test_case_colliding_path_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "collision.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Content/item.json", b"{}")
        bundle.writestr("content/item.json", b"{}")

    with pytest.raises(IntakeError) as failure:
        SafeArchive(archive, tmp_path / "out", ArchiveLimits()).prepare()
    assert failure.value.code == "case_collision"


def test_symbolic_link_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(link, "target")

    with pytest.raises(IntakeError) as failure:
        SafeArchive(archive, tmp_path / "out", ArchiveLimits()).prepare()
    assert failure.value.code == "unsafe_member_type"


def test_compression_ratio_boundary_is_enforced(tmp_path: Path) -> None:
    archive = tmp_path / "compressed.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("zeros.bin", b"0" * 100_000)

    with pytest.raises(IntakeError) as failure:
        SafeArchive(
            archive,
            tmp_path / "out",
            ArchiveLimits(max_compression_ratio=2.0),
        ).prepare()
    assert failure.value.code == "compression_ratio_limit"


def test_file_count_and_expanded_size_boundaries_are_enforced(tmp_path: Path) -> None:
    archive = tmp_path / "limits.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("one", b"1234")
        bundle.writestr("two", b"5678")

    with pytest.raises(IntakeError) as count_failure:
        SafeArchive(archive, tmp_path / "count", ArchiveLimits(max_files=1)).prepare()
    assert count_failure.value.code == "file_count_limit"

    with pytest.raises(IntakeError) as size_failure:
        SafeArchive(
            archive, tmp_path / "size", ArchiveLimits(max_total_bytes=7)
        ).prepare()
    assert size_failure.value.code == "expanded_size_limit"
