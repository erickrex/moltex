from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from moltex_harness.intake.service import IntakeService


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _build_reduced_export(source: Path, destination: Path) -> Path:
    with zipfile.ZipFile(source) as input_zip:
        files = {
            info.filename: input_zip.read(info.filename)
            for info in input_zip.infolist()
            if not info.is_dir() and info.filename != "bundle.json"
        }
        manifest = json.loads(input_zip.read("bundle.json"))

    media_map = json.loads(files["media/media_map.json"])
    removed = {media_map[1]["artifact"]}
    media_map[1]["artifact"] = media_map[0]["artifact"]
    files["media/media_map.json"] = json.dumps(
        media_map,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8") + b"\n"

    snapshots = sorted(path for path in files if path.startswith("snapshots/"))
    removed.update(snapshots[2:])
    removed.update(
        path
        for path in files
        if path.startswith(("plugins/readmes/", "plugins/templates/"))
        or path == "plugins/plugins_templates_manifest.json"
    )
    for path in removed:
        files.pop(path, None)

    receipts = []
    for receipt in manifest["artifacts"]:
        path = receipt["path"]
        if path in removed:
            continue
        if path == "media/media_map.json":
            receipt = dict(receipt)
            receipt["bytes"] = len(files[path])
            receipt["sha256"] = hashlib.sha256(files[path]).hexdigest()
        receipts.append(receipt)
    manifest["artifacts"] = receipts

    identity = dict(manifest)
    identity.pop("bundle_id", None)
    identity.pop("created_at", None)
    manifest["bundle_id"] = (
        f"sha256:{hashlib.sha256(_canonical_json(identity)).hexdigest()}"
    )
    files["bundle.json"] = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8") + b"\n"

    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED
    ) as output_zip:
        for path, data in sorted(files.items()):
            output_zip.writestr(path, data)
    return destination


@pytest.mark.parametrize(
    ("filename", "adapter", "content_count"),
    [
        ("legacy-1-export.zip", "legacy-1", 7),
        ("moltex-export-1.zip", "moltex-export/1", 1),
        ("golden-export.zip", "moltex-export/1", 8),
    ],
)
def test_supported_sample_exports_compile_raw_evidence(
    samples_dir: Path,
    tmp_path: Path,
    filename: str,
    adapter: str,
    content_count: int,
) -> None:
    outcome = IntakeService().inspect(samples_dir / filename, tmp_path / filename)

    assert outcome.exit_code == 0
    assert outcome.result.report.status == "accepted"
    assert outcome.result.report.adapter == adapter
    assert outcome.result.evidence is not None
    assert len(outcome.result.evidence.content) == content_count
    assert outcome.result.evidence.source_manifest.source_schema == adapter
    assert (tmp_path / filename / "intake-report.json").is_file()
    assert (tmp_path / filename / "raw-source-evidence.json").is_file()

    if filename == "golden-export.zip":
        assert len(outcome.result.evidence.site) == 2
        assert len(outcome.result.evidence.media) == 2
        assert len(outcome.result.evidence.html_references) == 8
        assert len(outcome.result.evidence.screenshot_references) == 2


def test_all_emitted_evidence_references_resolve_once(
    samples_dir: Path, tmp_path: Path
) -> None:
    outcome = IntakeService().inspect(
        samples_dir / "golden-export.zip", tmp_path / "report"
    )
    evidence = outcome.result.evidence
    assert evidence is not None
    inventory = {item.path for item in evidence.inventory}
    references = list(evidence.source_manifest.evidence.values())
    references.extend(item.evidence for item in evidence.site)
    references.extend(item.evidence for item in evidence.content)
    references.extend(item.evidence for item in evidence.navigation)
    references.extend(item.evidence for item in evidence.media)
    references.extend(item.evidence for item in evidence.seo)
    references.extend(item.evidence for item in evidence.redirects)
    references.extend(item.evidence for item in evidence.capabilities)
    references.extend(item.evidence for item in evidence.html_references)
    references.extend(item.evidence for item in evidence.screenshot_references)

    assert all(reference.artifact in inventory for reference in references)
    assert len({reference.evidence_id for reference in references}) == len(references)


def test_reduced_export_with_shared_media_artifact_is_accepted(
    samples_dir: Path, tmp_path: Path
) -> None:
    archive = _build_reduced_export(
        samples_dir / "golden-export.zip", tmp_path / "reduced-export.zip"
    )
    outcome = IntakeService().inspect(archive, tmp_path / "report")

    assert outcome.exit_code == 0
    assert outcome.result.report.status == "accepted"
    evidence = outcome.result.evidence
    assert evidence is not None
    assert len(evidence.media) == 2
    assert len({item.artifact for item in evidence.media}) == 1
    assert len(evidence.html_references) == 2
    inventory = {item.path for item in evidence.inventory}
    assert not any(
        path.startswith(("plugins/readmes/", "plugins/templates/"))
        for path in inventory
    )


def test_checksum_mutation_is_rejected_before_parsing(
    samples_dir: Path,
    rewrite_zip,
    tmp_path: Path,
) -> None:
    archive = rewrite_zip(
        samples_dir / "moltex-export-1.zip",
        replacements={"site_settings.json": b'{"schema_version":1,"changed":true}'},
    )
    outcome = IntakeService().inspect(archive, tmp_path / "report")

    assert outcome.exit_code == 3
    assert outcome.result.report.findings[0].code in {
        "artifact_size_mismatch",
        "checksum_mismatch",
    }
    assert outcome.result.evidence is None


def test_missing_declared_artifact_is_rejected(
    samples_dir: Path,
    rewrite_zip,
    tmp_path: Path,
) -> None:
    archive = rewrite_zip(
        samples_dir / "moltex-export-1.zip",
        remove={"site_settings.json"},
    )
    outcome = IntakeService().inspect(archive, tmp_path / "report")
    assert outcome.exit_code == 3
    assert outcome.result.report.findings[0].code == "missing_artifact"


def test_unsupported_archive_has_distinct_exit_code(tmp_path: Path) -> None:
    import zipfile

    archive = tmp_path / "unknown.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("unknown.json", "{}")
    outcome = IntakeService().inspect(archive, tmp_path / "report")
    assert outcome.exit_code == 4
    assert outcome.result.report.findings[0].classification == "unsupported_version"


def test_invalid_json_report_does_not_echo_secret(
    minimal_legacy_zip,
    rewrite_zip,
    tmp_path: Path,
) -> None:
    source = minimal_legacy_zip()
    secret = "sk-proj_SUPERSECRETVALUE123456"
    archive = rewrite_zip(
        source,
        replacements={"site_settings.json": f'{{"api_key":"{secret}"'.encode()},
    )
    report_dir = tmp_path / "report"
    outcome = IntakeService().inspect(archive, report_dir)
    serialized = (report_dir / "intake-report.json").read_text(encoding="utf-8")
    assert outcome.exit_code == 3
    assert secret not in serialized
    assert outcome.result.report.findings[0].code == "invalid_json"


def test_output_is_deterministic(samples_dir: Path, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    service = IntakeService()
    assert service.inspect(samples_dir / "golden-export.zip", first).exit_code == 0
    assert service.inspect(samples_dir / "golden-export.zip", second).exit_code == 0
    assert (first / "intake-report.json").read_bytes() == (
        second / "intake-report.json"
    ).read_bytes()
    assert (first / "raw-source-evidence.json").read_bytes() == (
        second / "raw-source-evidence.json"
    ).read_bytes()


def test_expected_failure_catalog_is_current() -> None:
    catalog = Path(__file__).parents[2] / "fixtures" / "expected_failures.json"
    values = json.loads(catalog.read_text(encoding="utf-8"))
    assert {item["code"] for item in values} >= {
        "unsafe_path",
        "compression_ratio_limit",
        "duplicate_path",
        "checksum_mismatch",
        "missing_artifact",
        "unsupported_export",
    }
