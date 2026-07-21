"""Versioned reports for one self-contained site pipeline run."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .intake import SiteIdentity


PipelinePhase = Literal[
    "preflight",
    "eligibility",
    "baseline",
    "build",
    "planning",
    "publish",
    "workspace_ready",
]


class PipelineStageReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str
    duration_ms: int = Field(ge=0)
    artifacts: int = Field(ge=0)
    bytes: int = Field(ge=0)


class SitePipelineReport(BaseModel):
    """Stable summary of creating one complete generated site workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    status: Literal["migration_planned", "workspace_ready", "blocked", "failed"]
    phase: PipelinePhase
    code: str
    message: str
    output: str | None = None
    diagnostics: str | None = None
    site_identity: SiteIdentity | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    stages: tuple[PipelineStageReport, ...] = ()
