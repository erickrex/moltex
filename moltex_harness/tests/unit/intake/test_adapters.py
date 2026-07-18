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


def _write_export(
    files: dict[str, bytes], manifest: dict[str, object], destination: Path
) -> Path:
    identity = dict(manifest)
    identity.pop("bundle_id", None)
    identity.pop("created_at", None)
    manifest["bundle_id"] = (
        f"sha256:{hashlib.sha256(_canonical_json(identity)).hexdigest()}"
    )
    files["bundle.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED
    ) as output_zip:
        for path, data in sorted(files.items()):
            output_zip.writestr(path, data)
    return destination


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
    files["media/media_map.json"] = (
        json.dumps(
            media_map,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )

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

    return _write_export(files, manifest, destination)


def _build_media_acquisition_export(
    source: Path,
    destination: Path,
    *,
    status: str,
    method: str,
    remove_artifact: bool,
) -> Path:
    with zipfile.ZipFile(source) as input_zip:
        files = {
            info.filename: input_zip.read(info.filename)
            for info in input_zip.infolist()
            if not info.is_dir() and info.filename != "bundle.json"
        }
        manifest = json.loads(input_zip.read("bundle.json"))

    media_map = json.loads(files["media/media_map.json"])
    source_artifact = media_map[1]["artifact"]
    if remove_artifact:
        media_map[1]["artifact"] = None
    media_map[1]["acquisition"] = {
        "status": status,
        "method": method,
        "runtime_policy": "local-only",
    }
    if remove_artifact:
        files.pop(source_artifact)
    files["media/media_map.json"] = (
        json.dumps(media_map, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )

    receipts = []
    for receipt in manifest["artifacts"]:
        path = receipt["path"]
        if remove_artifact and path == source_artifact:
            continue
        if path == "media/media_map.json":
            receipt = dict(receipt)
            receipt["bytes"] = len(files[path])
            receipt["sha256"] = hashlib.sha256(files[path]).hexdigest()
        receipts.append(receipt)
    manifest["artifacts"] = receipts
    return _write_export(files, manifest, destination)


def _build_deferred_media_export(source: Path, destination: Path) -> Path:
    return _build_media_acquisition_export(
        source,
        destination,
        status="deferred",
        method="source-fetch",
        remove_artifact=True,
    )


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


def test_deferred_media_inventory_is_preserved_without_a_binary(
    samples_dir: Path, tmp_path: Path
) -> None:
    archive = _build_deferred_media_export(
        samples_dir / "golden-export.zip", tmp_path / "deferred-export.zip"
    )
    outcome = IntakeService().inspect(archive, tmp_path / "report")

    assert outcome.exit_code == 0
    evidence = outcome.result.evidence
    assert evidence is not None
    deferred = next(item for item in evidence.media if item.artifact is None)
    assert deferred.bytes is None
    assert deferred.sha256 is None
    assert deferred.acquisition is not None
    assert deferred.acquisition.status == "deferred"
    assert deferred.acquisition.method == "source-fetch"
    assert deferred.acquisition.runtime_policy == "local-only"


@pytest.mark.parametrize(
    ("status", "method", "remove_artifact"),
    [
        ("bundled", "bundle", False),
        ("unavailable", "operator-decision", True),
    ],
)
def test_other_consistent_media_acquisition_states_are_accepted(
    samples_dir: Path,
    tmp_path: Path,
    status: str,
    method: str,
    remove_artifact: bool,
) -> None:
    archive = _build_media_acquisition_export(
        samples_dir / "golden-export.zip",
        tmp_path / f"valid-{status}.zip",
        status=status,
        method=method,
        remove_artifact=remove_artifact,
    )
    outcome = IntakeService().inspect(archive, tmp_path / f"valid-{status}-report")

    assert outcome.exit_code == 0
    evidence = outcome.result.evidence
    assert evidence is not None
    declared = next(item for item in evidence.media if item.acquisition is not None)
    assert declared.acquisition.status == status
    assert declared.acquisition.method == method
    assert (declared.artifact is None) == remove_artifact


@pytest.mark.parametrize(
    ("status", "method", "remove_artifact"),
    [
        ("bundled", "bundle", True),
        ("deferred", "source-fetch", False),
        ("unavailable", "operator-decision", False),
        ("bundled", "source-fetch", False),
        ("deferred", "operator-decision", True),
        ("unavailable", "source-fetch", True),
    ],
)
def test_contradictory_media_acquisition_is_rejected(
    samples_dir: Path,
    tmp_path: Path,
    status: str,
    method: str,
    remove_artifact: bool,
) -> None:
    archive = _build_media_acquisition_export(
        samples_dir / "golden-export.zip",
        tmp_path / f"invalid-{status}-{method}-{remove_artifact}.zip",
        status=status,
        method=method,
        remove_artifact=remove_artifact,
    )
    outcome = IntakeService().inspect(archive, tmp_path / "invalid-report")

    assert outcome.exit_code == 3
    assert outcome.result.report.status == "rejected"
    finding = outcome.result.report.findings[0]
    assert finding.code == "invalid_media_acquisition"
    assert finding.artifact == "media/media_map.json"
    assert finding.pointer == "/1/acquisition"


def test_geodirectory_evidence_is_preserved_at_intake(
    minimal_legacy_zip, tmp_path: Path
) -> None:
    listing = {
        "schema_version": 1,
        "id": 77,
        "type": "gd_nightclubs",
        "slug": "club-luna",
        "status": "publish",
        "title": "Club Luna",
        "author": {"display_name": "Editor"},
        "date_gmt": "2026-07-01 20:00:00",
        "modified_gmt": "2026-07-02 20:00:00",
        "taxonomies": {},
        "raw_html": "<p>Open nightly.</p>",
        "legacy_permalink": "/nightclubs/club-luna/",
        "postmeta": {},
        "geodirectory": {
            "address": {"city": "Madrid"},
            "geo": {"latitude": 40.42, "longitude": -3.70},
            "custom_fields": {"price_level": 3},
            "media": [],
            "reviews": [],
        },
    }
    config = {
        "schema_version": 1,
        "post_types": {"gd_nightclubs": {"fields": []}},
    }
    archive = minimal_legacy_zip(
        overrides={
            "site_blueprint.json": {
                "schema_version": 1,
                "site": {"url": "https://example.test"},
                "content": {"total_exported": 1},
                "plugins": [],
            },
            "export_completeness.json": {
                "schema_version": 1,
                "complete": True,
                "post_types": {
                    "gd_nightclubs": {
                        "discovered": 1,
                        "exported": 1,
                        "excluded": 0,
                        "failed": 0,
                        "complete": True,
                    }
                },
                "excluded_statuses": ["private", "draft"],
            },
        },
        additions={
            "content/gd_nightclubs/club-luna.json": json.dumps(listing).encode(),
            "geodirectory.json": json.dumps(config).encode(),
        },
    )

    outcome = IntakeService().inspect(archive, tmp_path / "geodirectory-report")

    assert outcome.exit_code == 0
    evidence = outcome.result.evidence
    assert evidence is not None
    assert evidence.content[0].geodirectory == listing["geodirectory"]
    assert (
        next(
            item
            for item in evidence.capabilities
            if item.artifact == "geodirectory.json"
        ).data
        == config
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
