"""Versioned, evidence-linked canonical contracts produced by H2."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .intake import ArtifactInventoryItem, EvidenceReference


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DerivedLineage(ContractModel):
    derived_by: str
    inputs: tuple[EvidenceReference, ...] = Field(min_length=1)
    decision: str | None = None


class LineagedModel(ContractModel):
    schema_version: Literal[1] = 1
    lineage: dict[str, DerivedLineage]

    @model_validator(mode="after")
    def require_complete_lineage(self) -> "LineagedModel":
        expected = set(type(self).model_fields) - {"schema_version", "lineage"}
        actual = set(self.lineage)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"lineage keys mismatch; missing={missing}, extra={extra}")
        return self


class StaticEligibility(StrEnum):
    ELIGIBLE = "eligible"
    NEEDS_DECISION = "needs_decision"
    INELIGIBLE = "ineligible"


class CapabilityDispositionKind(StrEnum):
    REPRODUCE = "reproduce"
    REPLACE = "replace"
    EXTERNALIZE = "externalize"
    OMIT_WITH_APPROVAL = "omit-with-approval"
    NEEDS_DECISION = "needs_decision"


class SourceManifest(LineagedModel):
    manifest_id: str
    bundle_id: str
    source_schema: str
    archive_sha256: str
    exporter_version: str | None
    site_id: str
    site_origin: str
    complete: bool
    privacy: dict[str, Any]
    counts: dict[str, Any]
    inventory: tuple[ArtifactInventoryItem, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    omissions: tuple[str, ...]
    raw_evidence_sha256: str


class NavigationItem(LineagedModel):
    navigation_id: str
    menu_id: str
    label: str
    route_contract_id: str | None
    parent_navigation_id: str | None
    order: int


class SiteSpec(LineagedModel):
    site_id: str
    site_name: str
    locale: str
    source_origin: str
    target_canonical_origin: str
    trailing_slash_policy: Literal["always", "never"]
    collection_definitions: tuple[dict[str, Any], ...]
    route_families: tuple[str, ...]
    global_navigation: tuple[NavigationItem, ...]
    global_layout_requirements: tuple[str, ...]
    capability_ids: tuple[str, ...]
    unresolved_decision_ids: tuple[str, ...]
    static_eligibility: StaticEligibility


class CustomField(LineagedModel):
    field_id: str
    key: str
    value: Any
    source_owner: str
    disposition: Literal["seo", "source_metadata", "needs_decision"]


class ContentRecord(LineagedModel):
    record_id: str
    source_id: str
    content_type: str
    legacy_url: str
    slug: str
    status: str
    title: str
    published_at: str
    modified_at: str
    author_ids: tuple[str, ...]
    taxonomy_ids: tuple[str, ...]
    relationships: dict[str, tuple[str, ...]]
    original_html: str
    normalized_body: dict[str, Any]
    custom_fields: tuple[CustomField, ...]
    required_media_ids: tuple[str, ...]
    internal_route_ids: tuple[str, ...]
    unresolved_internal_links: tuple[str, ...]


class RouteContract(LineagedModel):
    contract_id: str
    source_content_id: str
    content_record_id: str | None
    legacy_url: str
    target_url: str
    page_family: str
    output_path: str
    expected_status: int
    required_content_markers: tuple[str, ...]
    redirect_required: bool
    seo_contract_id: str
    public: bool


class AssetContract(LineagedModel):
    asset_id: str
    source_url: str
    bundle_path: str | None
    target_path: str
    checksum: str | None
    bytes: int | None
    mime_type: str | None
    alt_text: str | None
    referencing_content_ids: tuple[str, ...]
    transform: dict[str, Any] | None
    provenance: str
    acquisition_status: Literal["bundled", "deferred", "missing"]
    acquisition_method: Literal["bundle", "source-fetch", "operator-decision"]
    runtime_policy: Literal["local-only"]
    needs_decision: bool


class SeoContract(LineagedModel):
    contract_id: str
    route_contract_id: str
    target_route: str
    title: str
    description: str | None
    canonical_url: str
    robots: str
    open_graph: dict[str, Any]
    structured_data_hints: tuple[str, ...]
    precedence_decision: str
    needs_decision: bool


class RedirectContract(LineagedModel):
    contract_id: str
    source_url: str
    target_url: str
    status_code: int
    target_route_contract_id: str | None
    needs_decision: bool


class CapabilityDisposition(LineagedModel):
    capability_id: str
    capability_type: str
    source_construct: str
    source_plugin: str | None
    business_critical: bool
    disposition: CapabilityDispositionKind
    target_behavior: str | None
    verification_method: str | None
    required_operator_decision: str | None
    observed_route_ids: tuple[str, ...]


class UrlMapEntry(LineagedModel):
    source_url: str
    target_url: str
    route_contract_id: str


class MediaMapEntry(LineagedModel):
    source_url: str
    target_path: str
    target_url: str
    asset_contract_id: str
    acquisition_status: Literal["bundled", "deferred", "missing"]
    runtime_policy: Literal["local-only"]


class ViewportProfile(ContractModel):
    name: Literal["desktop-1440x1200", "mobile-500x844"]
    width: int
    height: int


class VisualCaptureTarget(LineagedModel):
    target_id: str
    evidence_id: str
    route_contract_id: str
    source_url: str
    viewport: ViewportProfile
    selection_reason: str
    route_family: str


class VisualCapturePlan(LineagedModel):
    plan_id: str
    source_bundle_id: str
    max_routes: int
    selected_route_ids: tuple[str, ...]
    targets: tuple[VisualCaptureTarget, ...]


class ParityRow(LineagedModel):
    row_id: str
    subject_type: Literal["route", "capability"]
    subject_id: str
    route_contract_id: str | None
    capability_id: str | None
    state: Literal["pending", "blocked", "approved"]
    required_checks: tuple[str, ...]


class NormalizationFinding(ContractModel):
    finding_id: str
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    subject_id: str | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    decision_id: str | None = None


class DecisionItem(ContractModel):
    decision_id: str
    kind: str
    severity: Literal["review", "blocking"]
    subject_id: str
    prompt: str
    options: tuple[str, ...]
    evidence: tuple[EvidenceReference, ...]


class ContractFileReceipt(ContractModel):
    path: str
    bytes: int = Field(ge=0)
    sha256: str
    model: str
    records: int = Field(ge=0)


class ContractIndex(ContractModel):
    schema_version: Literal[1] = 1
    bundle_id: str
    compiler_version: str
    files: tuple[ContractFileReceipt, ...]


class ContractSet(ContractModel):
    source_manifest: SourceManifest
    site_spec: SiteSpec
    content_records: tuple[ContentRecord, ...]
    routes: tuple[RouteContract, ...]
    assets: tuple[AssetContract, ...]
    seo: tuple[SeoContract, ...]
    redirects: tuple[RedirectContract, ...]
    capabilities: tuple[CapabilityDisposition, ...]
    url_map: tuple[UrlMapEntry, ...]
    media_map: tuple[MediaMapEntry, ...]
    visual_capture_plan: VisualCapturePlan
    parity_matrix: tuple[ParityRow, ...]
    findings: tuple[NormalizationFinding, ...]
    decisions: tuple[DecisionItem, ...]


class ContractVerificationReport(ContractModel):
    schema_version: Literal[1] = 1
    status: Literal["pass", "fail"]
    bundle_id: str | None
    files_checked: int
    checks: dict[str, bool]
    errors: tuple[str, ...] = ()
