"""Shared source-evidence parsing after adapter validation."""

from __future__ import annotations

import csv
import hashlib
import io
from typing import Any

from moltex_harness.models import (
    ArtifactInventoryItem,
    EvidenceReference,
    RawArtifactEvidence,
    RawContentEvidence,
    RawMediaEvidence,
    RawSourceEvidence,
    RawSourceManifest,
)

from ..archive import SafeArchive
from ..errors import IntakeError
from .base import AdapterValidation


CAPABILITY_ARTIFACTS = (
    "acf_field_groups.json",
    "block_patterns.json",
    "block_usage.json",
    "custom_post_types.json",
    "customizer_settings.json",
    "database_schema.json",
    "elementor_data.json",
    "external_assets.json",
    "forms_config.json",
    "geodirectory.json",
    "hooks_registry.json",
    "integration_manifest.json",
    "kadence_blocks.json",
    "plugin_behaviors.json",
    "plugins/plugins_fingerprint.json",
    "shortcodes_inventory.json",
    "taxonomies.json",
    "theme_mods.json",
    "widgets.json",
)


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
                internal_links=value.get("internal_links", []),
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
        if artifact is not None and (
            not isinstance(artifact, str) or not bundle.has(artifact)
        ):
            raise IntakeError(
                "missing_media_artifact",
                "Media map references a missing artifact",
                artifact=path,
                pointer=f"/{index}/artifact",
            )
        metadata = (
            value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
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
                acquisition=(
                    value.get("acquisition")
                    if isinstance(value.get("acquisition"), dict)
                    else None
                ),
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
    source_manifest = RawSourceManifest(
        source_schema=validation.adapter,
        bundle_id=validation.bundle_id,
        archive_sha256=bundle.archive_sha256,
        exporter_version=validation.exporter_version,
        site_origin=validation.site_origin,
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
        content=_content(bundle, validation),
        navigation=navigation,
        media=_media(bundle, validation),
        seo=seo,
        redirects=_redirects(bundle, validation),
        capabilities=capabilities,
        html_references=sorted(html, key=lambda item: item.artifact),
        screenshot_references=_screenshots(bundle, validation),
        inventory=_inventory(bundle, validation),
        findings=sorted(
            validation.findings,
            key=lambda finding: (
                finding.severity,
                finding.code,
                finding.artifact or "",
                finding.pointer or "",
                finding.message,
            ),
        ),
    )
