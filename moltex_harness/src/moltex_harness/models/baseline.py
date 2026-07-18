"""Versioned H3 conversion, acquisition, and baseline build receipts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BaselineModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConversionFinding(BaselineModel):
    severity: Literal["info", "warning", "error"]
    code: str
    classification: Literal["permanent", "blocked", "transient", "harness"]
    subject_id: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class ShortcodeDisposition(BaselineModel):
    name: str
    disposition: Literal["converted", "placeholder", "preserved"]
    count: int = Field(ge=1)


class ContentConversionReceipt(BaselineModel):
    schema_version: Literal[1] = 1
    record_id: str
    source_sha256: str
    output_sha256: str
    body_format: Literal["markdown", "sanitized_html"]
    sanitized_html: str
    editable_body: str
    shortcodes: tuple[ShortcodeDisposition, ...] = ()
    rewritten_urls: int = Field(ge=0)
    findings: tuple[ConversionFinding, ...] = ()


class AssetAcquisitionReceipt(BaselineModel):
    schema_version: Literal[1] = 1
    asset_id: str
    source_url: str
    final_source_url: str
    target_path: str
    acquisition_method: Literal["bundle", "source-fetch"]
    source_artifact: str | None
    bytes: int = Field(ge=0)
    sha256: str
    attempts: int = Field(ge=1)


class SourceVisualEvidence(BaselineModel):
    evidence_id: str
    route_contract_id: str
    source_url: str
    final_url: str
    viewport_name: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    artifact: str
    bytes: int = Field(gt=0)
    sha256: str


class RouteAvailabilityEvidence(BaselineModel):
    route_contract_id: str
    source_url: str
    final_url: str
    status_code: int = Field(ge=100, le=599)
    disposition: Literal["available", "omitted"]
    reason: str | None = None


class SourceVisualReceipt(BaselineModel):
    schema_version: Literal[2] = 2
    bundle_id: str
    capture_plan_id: str
    capture_plan_sha256: str
    browser: str
    browser_version: str
    route_availability: tuple[RouteAvailabilityEvidence, ...]
    evidence: tuple[SourceVisualEvidence, ...]


class BaselineCompilationReport(BaselineModel):
    schema_version: Literal[1] = 1
    status: Literal["compiled", "failed"]
    bundle_id: str | None
    code: str
    message: str
    classification: Literal["permanent", "blocked", "transient", "harness"] | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
