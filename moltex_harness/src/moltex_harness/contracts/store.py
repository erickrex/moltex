"""Deterministic materialization and loading of H2 contract artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from moltex_harness.intake.serialization import deterministic_json, write_json
from moltex_harness.models import (
    AssetContract,
    CapabilityDisposition,
    ContentRecord,
    ContractFileReceipt,
    ContractIndex,
    ContractSet,
    DecisionItem,
    MediaMapEntry,
    NormalizationFinding,
    ParityRow,
    RedirectContract,
    RouteContract,
    SeoContract,
    SiteSpec,
    SourceManifest,
    UrlMapEntry,
    VisualCapturePlan,
)


FILE_LAYOUT: tuple[tuple[str, str, str], ...] = (
    ("source-manifest.json", "source_manifest", "SourceManifest"),
    ("site-spec.json", "site_spec", "SiteSpec"),
    ("content-records.json", "content_records", "ContentRecord[]"),
    ("contracts/routes.json", "routes", "RouteContract[]"),
    ("contracts/assets.json", "assets", "AssetContract[]"),
    ("contracts/seo.json", "seo", "SeoContract[]"),
    ("contracts/redirects.json", "redirects", "RedirectContract[]"),
    ("contracts/capabilities.json", "capabilities", "CapabilityDisposition[]"),
    ("maps/url-map.json", "url_map", "UrlMapEntry[]"),
    ("maps/media-map.json", "media_map", "MediaMapEntry[]"),
    ("visual-capture-plan.json", "visual_capture_plan", "VisualCapturePlan"),
    ("parity-matrix.json", "parity_matrix", "ParityRow[]"),
    ("normalization-findings.json", "findings", "NormalizationFinding[]"),
    ("decision-queue.json", "decisions", "DecisionItem[]"),
)


MODEL_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "source_manifest": TypeAdapter(SourceManifest),
    "site_spec": TypeAdapter(SiteSpec),
    "content_records": TypeAdapter(tuple[ContentRecord, ...]),
    "routes": TypeAdapter(tuple[RouteContract, ...]),
    "assets": TypeAdapter(tuple[AssetContract, ...]),
    "seo": TypeAdapter(tuple[SeoContract, ...]),
    "redirects": TypeAdapter(tuple[RedirectContract, ...]),
    "capabilities": TypeAdapter(tuple[CapabilityDisposition, ...]),
    "url_map": TypeAdapter(tuple[UrlMapEntry, ...]),
    "media_map": TypeAdapter(tuple[MediaMapEntry, ...]),
    "visual_capture_plan": TypeAdapter(VisualCapturePlan),
    "parity_matrix": TypeAdapter(tuple[ParityRow, ...]),
    "findings": TypeAdapter(tuple[NormalizationFinding, ...]),
    "decisions": TypeAdapter(tuple[DecisionItem, ...]),
}


class ContractStore:
    compiler_version = "h2-contracts/1"

    def write(self, destination: Path, contracts: ContractSet) -> ContractIndex:
        destination.mkdir(parents=True, exist_ok=True)
        receipts: list[ContractFileReceipt] = []
        for relative_path, attribute, model_name in FILE_LAYOUT:
            value = getattr(contracts, attribute)
            serialized = deterministic_json(value).encode("utf-8")
            path = destination / Path(relative_path)
            write_json(path, value)
            records = len(value) if isinstance(value, tuple) else 1
            receipts.append(
                ContractFileReceipt(
                    path=relative_path,
                    bytes=len(serialized),
                    sha256=hashlib.sha256(serialized).hexdigest(),
                    model=model_name,
                    records=records,
                )
            )
        index = ContractIndex(
            bundle_id=contracts.source_manifest.bundle_id,
            compiler_version=self.compiler_version,
            files=tuple(receipts),
            evidence_resolutions=contracts.evidence_resolutions,
        )
        write_json(destination / "contract-index.json", index)
        return index

    def load(self, source: Path) -> tuple[ContractSet, ContractIndex]:
        index_data = json.loads(
            (source / "contract-index.json").read_text(encoding="utf-8")
        )
        index = ContractIndex.model_validate(index_data)
        values: dict[str, Any] = {}
        for relative_path, attribute, _ in FILE_LAYOUT:
            path = source / Path(relative_path)
            data = json.loads(path.read_text(encoding="utf-8"))
            values[attribute] = MODEL_ADAPTERS[attribute].validate_python(data)
        return ContractSet(
            **values, evidence_resolutions=index.evidence_resolutions
        ), index
