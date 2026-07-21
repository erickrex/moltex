"""Versioned models emitted by the H1 intake boundary."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base for stable serialized contracts."""

    model_config = ConfigDict(extra="forbid")


class Finding(StrictModel):
    severity: Literal["info", "warning", "error"]
    code: str
    classification: Literal[
        "observation",
        "omission",
        "invalid_input",
        "unsupported_version",
        "privacy",
        "readiness",
        "harness_error",
    ]
    message: str
    artifact: str | None = None
    pointer: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ArtifactInventoryItem(StrictModel):
    path: str
    bytes: int = Field(ge=0)
    compressed_bytes: int = Field(ge=0)
    sha256: str
    kind: str | None = None
    required: bool | None = None
    schema_ref: str | None = None


class EvidenceReference(StrictModel):
    evidence_id: str
    bundle_id: str
    artifact: str
    pointer: str
    sha256: str


class SiteIdentity(StrictModel):
    """Exporter-declared identity used for display and safe workspace naming."""

    site_name: str = Field(min_length=1, max_length=300)
    domain: str = Field(min_length=1, max_length=253)
    workspace_slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )


class RawSourceManifest(StrictModel):
    schema_version: Literal[1] = 1
    source_schema: Literal["legacy-1", "moltex-export/1"]
    bundle_id: str
    archive_sha256: str
    exporter_version: str | None = None
    site_origin: str | None = None
    site_identity: SiteIdentity | None = None
    mode: str
    complete: bool
    privacy: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, Any] = Field(default_factory=dict)
    readiness: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    evidence: dict[str, EvidenceReference] = Field(default_factory=dict)


class RawContentEvidence(StrictModel):
    source_id: int | str
    content_type: str
    slug: str
    status: str
    title: str
    author: dict[str, Any] | list[Any]
    date_gmt: str
    modified_gmt: str
    taxonomies: dict[str, Any] | list[Any]
    original_html: str
    blocks: Any = None
    postmeta: dict[str, Any] | list[Any]
    featured_media: Any = None
    internal_links: list[Any] = Field(default_factory=list)
    legacy_permalink: str
    template: str | None = None
    geodirectory: dict[str, Any] | None = None
    evidence: EvidenceReference


class MediaAcquisition(StrictModel):
    """Source-side availability without prescribing a target implementation."""

    status: Literal["bundled", "deferred", "unavailable"]
    method: Literal["bundle", "source-fetch", "operator-decision"]
    runtime_policy: Literal["local-only"]


class RawMediaEvidence(StrictModel):
    source_url: str
    artifact: str | None
    source_id: int | str | None = None
    mime_type: str | None = None
    alt_text: str | None = None
    bytes: int | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    acquisition: MediaAcquisition | None = None
    evidence: EvidenceReference


class RawArtifactEvidence(StrictModel):
    artifact: str
    data: Any
    evidence: EvidenceReference


class LegacyPayloadEvidence(StrictModel):
    status: Literal["included", "sampled", "deferred", "unavailable", "omitted"]
    method: Literal[
        "bundle", "source-fetch", "targeted-export", "operator-decision", "none"
    ]
    artifact: str | None
    row_count: int = Field(ge=0)
    excluded_row_count: int | None = Field(default=None, ge=0)
    bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = None
    reason: str = Field(min_length=1, max_length=1000)


class RawLegacyEvidence(StrictModel):
    evidence_id: str
    artifact_type: Literal[
        "postmeta_field",
        "custom_table",
        "option",
        "shortcode",
        "block",
        "custom_post_type",
        "taxonomy",
        "widget",
        "integration",
        "media_reference",
    ]
    source_plugin: str
    ownership_confidence: Literal["high", "medium", "low", "unknown"]
    plugin_status: Literal["active", "inactive", "missing", "unknown"]
    source_identity: dict[str, Any]
    relationship_status: Literal["referenced", "unreferenced", "unknown"]
    public_reference_count: int = Field(ge=0)
    reference_evidence: tuple[str, ...] = Field(max_length=100)
    payload: LegacyPayloadEvidence
    source_lineage: tuple[str, ...] = Field(max_length=100)
    evidence: EvidenceReference


class RawSourceEvidence(StrictModel):
    schema_version: Literal[1] = 1
    source_manifest: RawSourceManifest
    site: list[RawArtifactEvidence]
    content: list[RawContentEvidence] = Field(default_factory=list)
    navigation: list[RawArtifactEvidence] = Field(default_factory=list)
    media: list[RawMediaEvidence] = Field(default_factory=list)
    seo: list[RawArtifactEvidence] = Field(default_factory=list)
    redirects: list[RawArtifactEvidence] = Field(default_factory=list)
    capabilities: list[RawArtifactEvidence] = Field(default_factory=list)
    legacy_evidence: list[RawLegacyEvidence] = Field(default_factory=list)
    legacy_index: RawArtifactEvidence | None = None
    html_references: list[RawArtifactEvidence] = Field(default_factory=list)
    screenshot_references: list[RawArtifactEvidence] = Field(default_factory=list)
    inventory: list[ArtifactInventoryItem] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class IntakeReport(StrictModel):
    schema_version: Literal[1] = 1
    status: Literal["accepted", "rejected", "failed"]
    source_archive: str
    archive_sha256: str | None = None
    adapter: str | None = None
    bundle_id: str | None = None
    limits: dict[str, int | float]
    inventory: dict[str, int] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)


class IntakeResult(StrictModel):
    report: IntakeReport
    evidence: RawSourceEvidence | None = None
