"""Adapter protocol and validated source metadata."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from moltex_harness.models import Finding, RawSourceEvidence

from ..archive import SafeArchive


class AdapterValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: str
    bundle_id: str
    exporter_version: str | None = None
    site_origin: str | None = None
    mode: str
    complete: bool
    privacy: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, Any] = Field(default_factory=dict)
    readiness: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    declared_artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ExportAdapter(Protocol):
    name: str

    def validate(self, bundle: SafeArchive) -> AdapterValidation:
        """Validate all source-format invariants before evidence is consumed."""

    def parse(
        self, bundle: SafeArchive, validation: AdapterValidation
    ) -> RawSourceEvidence:
        """Compile source observations without target decisions."""
