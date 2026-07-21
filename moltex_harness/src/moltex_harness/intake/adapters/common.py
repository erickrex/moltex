"""Shared source-evidence parsing after adapter validation."""

from __future__ import annotations

import csv
import hashlib
import io
from typing import Any, Literal, cast

from moltex_harness.models import (
    ArtifactInventoryItem,
    EvidenceReference,
    Finding,
    MediaAcquisition,
    LegacyPayloadEvidence,
    RawArtifactEvidence,
    RawContentEvidence,
    RawMediaEvidence,
    RawLegacyEvidence,
    RawSourceEvidence,
    RawSourceManifest,
)

from ..archive import SafeArchive
from ..artifacts import CAPABILITY_ARTIFACTS
from ..errors import IntakeError
from .base import AdapterValidation


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def evidence_ref(
    bundle: SafeArchive,
    bundle_id: str,
    artifact: str,
    pointer: str = "",
) -> EvidenceReference:
    item = bundle.item(artifact)
    identity = hashlib.sha256(
        f"{bundle_id}\x00{artifact}\x00{pointer}".encode("utf-8")
    ).hexdigest()
    return EvidenceReference(
        evidence_id=f"evidence:{identity}",
        bundle_id=bundle_id,
        artifact=artifact,
        pointer=pointer,
        sha256=item.sha256,
    )


def artifact_evidence(
    bundle: SafeArchive,
    bundle_id: str,
    artifact: str,
    *,
    pointer: str = "",
    data: Any | None = None,
) -> RawArtifactEvidence:
    if data is None:
        data = bundle.read_json(artifact)
    return RawArtifactEvidence(
        artifact=artifact,
        data=data,
        evidence=evidence_ref(bundle, bundle_id, artifact, pointer),
    )


def _content(
    bundle: SafeArchive, validation: AdapterValidation
) -> list[RawContentEvidence]:
    result: list[RawContentEvidence] = []
    for path in bundle.paths():
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "content" or not path.endswith(".json"):
            continue
        value = bundle.read_json(path)
        if not isinstance(value, dict):
            raise IntakeError(
                "invalid_content",
                "Content artifact must be a JSON object",
                artifact=path,
            )
        required = (
            "id",
            "type",
            "slug",
            "status",
            "title",
            "author",
            "date_gmt",
            "modified_gmt",
            "taxonomies",
            "raw_html",
            "legacy_permalink",
            "postmeta",
        )
        missing = [key for key in required if key not in value]
        if missing:
            raise IntakeError(
                "invalid_content",
                "Content artifact is missing required fields",
                artifact=path,
                context={"fields": sorted(missing)},
            )
        internal_links = value.get("internal_links", [])
        if isinstance(internal_links, dict):
            if not all(str(key).isdigit() for key in internal_links):
                raise IntakeError(
                    "invalid_content",
                    "Content internal links must be an array or a numeric-key object",
                    artifact=path,
                    pointer="/internal_links",
                )
            internal_links = [
                internal_links[key]
                for key in sorted(internal_links, key=lambda item: int(item))
            ]
        if not isinstance(internal_links, list):
            raise IntakeError(
                "invalid_content",
                "Content internal links must be an array",
                artifact=path,
                pointer="/internal_links",
            )
        result.append(
            RawContentEvidence(
                source_id=value["id"],
                content_type=str(value["type"]),
                slug=str(value["slug"]),
                status=str(value["status"]),
                title=str(value["title"]),
                author=value["author"],
                date_gmt=str(value["date_gmt"]),
                modified_gmt=str(value["modified_gmt"]),
                taxonomies=value["taxonomies"],
                original_html=str(value["raw_html"]),
                blocks=value.get("blocks"),
                postmeta=value["postmeta"],
                featured_media=value.get("featured_media"),
                internal_links=internal_links,
                legacy_permalink=str(value["legacy_permalink"]),
                template=value.get("template"),
                geodirectory=(
                    value.get("geodirectory")
                    if isinstance(value.get("geodirectory"), dict)
                    else None
                ),
                evidence=evidence_ref(bundle, validation.bundle_id, path),
            )
        )
    return sorted(
        result, key=lambda item: (item.content_type, str(item.source_id), item.slug)
    )


def _media(
    bundle: SafeArchive, validation: AdapterValidation
) -> list[RawMediaEvidence]:
    path = "media/media_map.json"
    if not bundle.has(path):
        return []
    values = bundle.read_json(path)
    if not isinstance(values, list):
        raise IntakeError(
            "invalid_media_map", "Media map must be a JSON array", artifact=path
        )
    result: list[RawMediaEvidence] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict) or not isinstance(value.get("wp_src"), str):
            raise IntakeError(
                "invalid_media_map", "Media map entry is invalid", artifact=path
            )
        artifact = value.get("artifact")
        acquisition = value.get("acquisition")
        acquisition_model: MediaAcquisition | None = None
        if acquisition is not None:
            expected = {
                "bundled": ("bundle", True),
                "deferred": ("source-fetch", False),
                "unavailable": ("operator-decision", False),
            }
            if not isinstance(acquisition, dict):
                raise IntakeError(
                    "invalid_media_acquisition",
                    "Media acquisition declaration must be an object",
                    artifact=path,
                    pointer=f"/{index}/acquisition",
                )
            status = acquisition.get("status")
            declaration = expected.get(status) if isinstance(status, str) else None
            if (
                declaration is None
                or acquisition.get("method") != declaration[0]
                or acquisition.get("runtime_policy") != "local-only"
                or (artifact is not None) != declaration[1]
            ):
                raise IntakeError(
                    "invalid_media_acquisition",
                    "Media acquisition declaration contradicts its artifact state",
                    artifact=path,
                    pointer=f"/{index}/acquisition",
                )
            acquisition_model = MediaAcquisition.model_validate(acquisition)
        if artifact is not None and (
            not isinstance(artifact, str) or not bundle.has(artifact)
        ):
            raise IntakeError(
                "missing_media_artifact",
                "Media map references a missing artifact",
                artifact=path,
                pointer=f"/{index}/artifact",
            )
        metadata_value = value.get("metadata")
        metadata: dict[str, Any] = (
            metadata_value if isinstance(metadata_value, dict) else {}
        )
        file_item = bundle.item(artifact) if artifact else None
        result.append(
            RawMediaEvidence(
                source_url=value["wp_src"],
                artifact=artifact,
                source_id=metadata.get("id"),
                mime_type=metadata.get("mime_type") or value.get("type"),
                alt_text=metadata.get("alt"),
                bytes=file_item.bytes if file_item else None,
                sha256=file_item.sha256 if file_item else None,
                metadata=metadata,
                acquisition=acquisition_model,
                evidence=evidence_ref(bundle, validation.bundle_id, path, f"/{index}"),
            )
        )
    return sorted(result, key=lambda item: (item.source_url, item.artifact or ""))


def _redirects(
    bundle: SafeArchive, validation: AdapterValidation
) -> list[RawArtifactEvidence]:
    path = "redirects_candidates.csv"
    if not bundle.has(path):
        return []
    reader = csv.DictReader(io.StringIO(bundle.read_text(path)))
    rows = [dict(sorted(row.items())) for row in reader]
    return [artifact_evidence(bundle, validation.bundle_id, path, data=rows)]


def _screenshots(
    bundle: SafeArchive, validation: AdapterValidation
) -> list[RawArtifactEvidence]:
    manifest_path = "screenshots/manifest.json"
    if not bundle.has(manifest_path):
        return []
    manifest = bundle.read_json(manifest_path)
    values = manifest.get("screenshots", []) if isinstance(manifest, dict) else []
    if not isinstance(values, list):
        raise IntakeError(
            "invalid_screenshot_manifest",
            "Screenshot manifest entries must be an array",
        )
    result: list[RawArtifactEvidence] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict) or not isinstance(value.get("artifact"), str):
            raise IntakeError(
                "invalid_screenshot_manifest", "Screenshot manifest entry is invalid"
            )
        artifact = value["artifact"]
        item = bundle.item(artifact)
        if value.get("bytes") != item.bytes or value.get("sha256") != item.sha256:
            raise IntakeError(
                "screenshot_integrity_mismatch",
                "Screenshot metadata does not match the referenced artifact",
                artifact=manifest_path,
                pointer=f"/screenshots/{index}",
            )
        result.append(
            RawArtifactEvidence(
                artifact=artifact,
                data=value,
                evidence=evidence_ref(
                    bundle,
                    validation.bundle_id,
                    manifest_path,
                    f"/screenshots/{index}",
                ),
            )
        )
    return sorted(result, key=lambda item: item.artifact)


def _inventory(
    bundle: SafeArchive, validation: AdapterValidation
) -> list[ArtifactInventoryItem]:
    output: list[ArtifactInventoryItem] = []
    for item in bundle.inventory:
        declared = validation.declared_artifacts.get(item.path, {})
        output.append(
            item.model_copy(
                update={
                    "kind": declared.get("kind"),
                    "required": declared.get("required"),
                    "schema_ref": declared.get("schema"),
                }
            )
        )
    return output


def _legacy_evidence(
    bundle: SafeArchive,
    validation: AdapterValidation,
    content: list[RawContentEvidence],
) -> tuple[list[RawLegacyEvidence], list[Finding]]:
    """Validate the bounded legacy index or conservatively adapt older bundles."""

    path = "legacy_evidence_index.json"
    if not bundle.has(path):
        return _adapt_legacy_evidence(bundle, validation, content)
    value = bundle.read_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        raise IntakeError(
            "invalid_legacy_evidence",
            "Legacy evidence index must contain an entries array",
            artifact=path,
        )
    entries = value["entries"]
    if len(entries) > 5000:
        raise IntakeError(
            "legacy_evidence_limit",
            "Legacy evidence index exceeds the supported entry limit",
            artifact=path,
            pointer="/entries",
        )
    seen: set[str] = set()
    total_payload_bytes = 0
    result: list[RawLegacyEvidence] = []
    for index, entry in enumerate(entries):
        pointer = f"/entries/{index}"
        if not isinstance(entry, dict):
            raise IntakeError(
                "invalid_legacy_evidence",
                "Legacy evidence entry must be an object",
                artifact=path,
                pointer=pointer,
            )
        evidence_id = entry.get("evidence_id")
        if not isinstance(evidence_id, str) or evidence_id in seen:
            raise IntakeError(
                "duplicate_legacy_evidence",
                "Legacy evidence IDs must be non-empty and unique",
                artifact=path,
                pointer=f"{pointer}/evidence_id",
            )
        seen.add(evidence_id)
        references = entry.get("reference_evidence")
        if not isinstance(references, list) or len(references) > 100:
            raise IntakeError(
                "legacy_reference_limit",
                "Legacy evidence references must be a bounded array",
                artifact=path,
                pointer=f"{pointer}/reference_evidence",
            )
        for reference in references:
            if not isinstance(reference, str):
                raise IntakeError(
                    "invalid_legacy_reference",
                    "Legacy evidence reference must be a string",
                    artifact=path,
                    pointer=f"{pointer}/reference_evidence",
                )
            artifact = reference.split("#", 1)[0]
            if not artifact or not bundle.has(artifact):
                raise IntakeError(
                    "broken_legacy_reference",
                    "Legacy evidence references a missing artifact",
                    artifact=path,
                    pointer=f"{pointer}/reference_evidence",
                    context={"reference": reference},
                )
        payload_value = entry.get("payload")
        try:
            payload = LegacyPayloadEvidence.model_validate(payload_value)
        except ValueError as error:
            raise IntakeError(
                "invalid_legacy_payload",
                "Legacy payload declaration is invalid",
                artifact=path,
                pointer=f"{pointer}/payload",
                context={"error": str(error)},
            ) from error
        _validate_legacy_payload(bundle, path, pointer, payload)
        total_payload_bytes += payload.bytes or 0
        if total_payload_bytes > 104_857_600:
            raise IntakeError(
                "legacy_payload_limit",
                "Legacy payload bytes exceed the intake limit",
                artifact=path,
            )
        try:
            result.append(
                RawLegacyEvidence.model_validate(
                    {
                        **entry,
                        "evidence": evidence_ref(
                            bundle, validation.bundle_id, path, pointer
                        ).model_dump(mode="json"),
                    }
                )
            )
        except ValueError as error:
            raise IntakeError(
                "invalid_legacy_evidence",
                "Legacy evidence entry is invalid",
                artifact=path,
                pointer=pointer,
                context={"error": str(error)},
            ) from error
    return sorted(result, key=lambda item: item.evidence_id), []


def _validate_legacy_payload(
    bundle: SafeArchive,
    index_path: str,
    pointer: str,
    payload: LegacyPayloadEvidence,
) -> None:
    if payload.status in {"included", "sampled"}:
        if (
            payload.method != "bundle"
            or payload.artifact is None
            or payload.bytes is None
            or payload.sha256 is None
            or not bundle.has(payload.artifact)
        ):
            raise IntakeError(
                "invalid_legacy_acquisition",
                "Included or sampled legacy payload must reference a bundled artifact",
                artifact=index_path,
                pointer=f"{pointer}/payload",
            )
        item = bundle.item(payload.artifact)
        if item.bytes != payload.bytes or item.sha256 != payload.sha256:
            raise IntakeError(
                "legacy_payload_integrity",
                "Legacy payload receipt does not match its artifact",
                artifact=index_path,
                pointer=f"{pointer}/payload",
            )
    elif payload.status == "deferred":
        if payload.artifact is not None or payload.method not in {
            "source-fetch",
            "targeted-export",
            "operator-decision",
        }:
            raise IntakeError(
                "invalid_legacy_acquisition",
                "Deferred legacy payload has an inconsistent acquisition declaration",
                artifact=index_path,
                pointer=f"{pointer}/payload",
            )
    elif payload.artifact is not None:
        raise IntakeError(
            "invalid_legacy_acquisition",
            "Unavailable or omitted legacy payload cannot name an artifact",
            artifact=index_path,
            pointer=f"{pointer}/payload",
        )


def _adapt_legacy_evidence(
    bundle: SafeArchive,
    validation: AdapterValidation,
    content: list[RawContentEvidence],
) -> tuple[list[RawLegacyEvidence], list[Finding]]:
    """Preserve old observations as unknown without inventing ownership or reachability."""

    groups: dict[tuple[str, str], list[RawContentEvidence]] = {}
    for record in content:
        if isinstance(record.postmeta, dict):
            for key in record.postmeta:
                groups.setdefault((record.content_type, str(key)), []).append(record)
    result: list[RawLegacyEvidence] = []
    for (content_type, field_name), records in sorted(groups.items()):
        identity = hashlib.sha256(
            f"postmeta_field\x00{content_type}\x00{field_name}".encode()
        ).hexdigest()
        first = records[0]
        result.append(
            RawLegacyEvidence(
                evidence_id=f"legacy:postmeta_field:{identity}",
                artifact_type="postmeta_field",
                source_plugin="unknown",
                ownership_confidence="unknown",
                plugin_status="unknown",
                source_identity={"post_type": content_type, "field_name": field_name},
                relationship_status="unknown",
                public_reference_count=0,
                reference_evidence=tuple(
                    f"{record.evidence.artifact}#/postmeta/{_pointer_token(field_name)}"
                    for record in records[:100]
                ),
                payload=LegacyPayloadEvidence(
                    status="omitted",
                    method="none",
                    artifact=None,
                    row_count=len(records),
                    reason="Compatibility adapter preserves the original content artifacts.",
                ),
                source_lineage=("compatibility-adapter:postmeta",),
                evidence=first.evidence,
            )
        )
    table_path = "plugins/database_tables.json"
    if bundle.has(table_path):
        table_data = bundle.read_json(table_path)
        by_plugin = table_data.get("by_plugin", {}) if isinstance(table_data, dict) else {}
        if isinstance(by_plugin, dict):
            for plugin, tables in sorted(by_plugin.items()):
                if not isinstance(tables, list):
                    continue
                for index, table in enumerate(tables):
                    if not isinstance(table, dict) or not table.get("table_name"):
                        continue
                    name = str(table["table_name"])
                    identity = hashlib.sha256(f"custom_table\x00{name}".encode()).hexdigest()
                    result.append(
                        RawLegacyEvidence(
                            evidence_id=f"legacy:custom_table:{identity}",
                            artifact_type="custom_table",
                            source_plugin="unknown",
                            ownership_confidence="unknown",
                            plugin_status="unknown",
                            source_identity={"table_name": name},
                            relationship_status="unknown",
                            public_reference_count=0,
                            reference_evidence=(),
                            payload=LegacyPayloadEvidence(
                                status="omitted",
                                method="none",
                                artifact=None,
                                row_count=int(table.get("row_count", 0)),
                                reason="Compatibility adapter retains compact table inventory only.",
                            ),
                            source_lineage=("compatibility-adapter:database-table",),
                            evidence=evidence_ref(bundle, validation.bundle_id, table_path),
                        )
                    )
    finding = Finding(
        severity="warning",
        code="legacy_evidence_compatibility_adapter",
        classification="observation",
        message="Bundle predates the legacy evidence index; ownership and reachability remain conservative unknowns",
        artifact="legacy_evidence_index.json",
        context={"entries": len(result)},
    )
    return sorted(result, key=lambda item: item.evidence_id), [finding]


def compile_raw_evidence(
    bundle: SafeArchive, validation: AdapterValidation
) -> RawSourceEvidence:
    """Compile only observations available in the accepted source bundle."""

    site = [
        artifact_evidence(bundle, validation.bundle_id, path)
        for path in ("site_blueprint.json", "site_settings.json")
        if bundle.has(path)
    ]
    navigation = (
        [artifact_evidence(bundle, validation.bundle_id, "menus.json")]
        if bundle.has("menus.json")
        else []
    )
    seo = (
        [artifact_evidence(bundle, validation.bundle_id, "seo_full.json")]
        if bundle.has("seo_full.json")
        else []
    )
    capabilities = [
        artifact_evidence(bundle, validation.bundle_id, path)
        for path in CAPABILITY_ARTIFACTS
        if bundle.has(path)
    ]
    html = [
        RawArtifactEvidence(
            artifact=path,
            data={"bytes": bundle.item(path).bytes, "sha256": bundle.item(path).sha256},
            evidence=evidence_ref(bundle, validation.bundle_id, path),
        )
        for path in bundle.paths()
        if path.endswith(".html")
        and (path.startswith("html_snapshots/") or path.startswith("snapshots/"))
    ]
    content = _content(bundle, validation)
    legacy_evidence, legacy_findings = _legacy_evidence(
        bundle, validation, content
    )
    source_manifest = RawSourceManifest(
        source_schema=cast(
            Literal["legacy-1", "moltex-export/1"], validation.adapter
        ),
        bundle_id=validation.bundle_id,
        archive_sha256=bundle.archive_sha256,
        exporter_version=validation.exporter_version,
        site_origin=validation.site_origin,
        site_identity=validation.site_identity,
        mode=validation.mode,
        complete=validation.complete,
        privacy=validation.privacy,
        counts=validation.counts,
        readiness=validation.readiness,
        warnings=validation.warnings,
        omissions=validation.omissions,
        evidence={
            "bundle": evidence_ref(
                bundle,
                validation.bundle_id,
                "bundle.json" if bundle.has("bundle.json") else "site_blueprint.json",
            ),
            "site": evidence_ref(
                bundle, validation.bundle_id, "site_blueprint.json", "/site"
            ),
            "counts": evidence_ref(
                bundle,
                validation.bundle_id,
                "export_completeness.json",
                "/post_types",
            ),
            "privacy": evidence_ref(
                bundle,
                validation.bundle_id,
                "bundle.json"
                if bundle.has("bundle.json")
                else "export_completeness.json",
                "/privacy" if bundle.has("bundle.json") else "/excluded_statuses",
            ),
            "readiness": evidence_ref(
                bundle,
                validation.bundle_id,
                "migration_readiness.json",
            ),
        },
    )
    return RawSourceEvidence(
        source_manifest=source_manifest,
        site=site,
        content=content,
        navigation=navigation,
        media=_media(bundle, validation),
        seo=seo,
        redirects=_redirects(bundle, validation),
        capabilities=capabilities,
        legacy_evidence=legacy_evidence,
        legacy_index=(
            artifact_evidence(
                bundle, validation.bundle_id, "legacy_evidence_index.json"
            )
            if bundle.has("legacy_evidence_index.json")
            else None
        ),
        html_references=sorted(html, key=lambda item: item.artifact),
        screenshot_references=_screenshots(bundle, validation),
        inventory=_inventory(bundle, validation),
        findings=sorted(
            [*validation.findings, *legacy_findings],
            key=lambda finding: (
                finding.severity,
                finding.code,
                finding.artifact or "",
                finding.pointer or "",
                finding.message,
            ),
        ),
    )
