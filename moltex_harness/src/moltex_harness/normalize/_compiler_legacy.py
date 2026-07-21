"""H2 classifications for bounded legacy plugin evidence."""

from __future__ import annotations

from typing import Literal

from moltex_harness.models import (
    CapabilityDisposition,
    CapabilityDispositionKind,
    DecisionItem,
    LegacyEvidenceContract,
    NormalizationFinding,
    RawLegacyEvidence,
    RawSourceEvidence,
    RouteContract,
)
from moltex_harness.conversion.gutenberg import SUPPORTED_PRESENTATION_BLOCKS

from ._compiler_support import _CompilerSupport, _lineage
from .primitives import stable_hash, stable_token


class _LegacyEvidenceCompilerMixin(_CompilerSupport):
    def _legacy_evidence_contracts(
        self,
        raw: RawSourceEvidence,
        routes: list[RouteContract],
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> tuple[list[LegacyEvidenceContract], list[CapabilityDisposition]]:
        route_by_artifact = {
            record.evidence.artifact: next(
                (
                    route.contract_id
                    for route in routes
                    if route.source_content_id == str(record.source_id)
                ),
                None,
            )
            for record in raw.content
        }
        contracts: list[LegacyEvidenceContract] = []
        capabilities: list[CapabilityDisposition] = []
        for item in raw.legacy_evidence:
            classification = self._legacy_classification(item)
            disposition = self._legacy_disposition(item, classification)
            contract_id = f"legacy-contract:{stable_hash(item.evidence_id, length=32)}"
            capability_id: str | None = None
            decision_id: str | None = None
            observed_route_set: set[str] = set()
            for reference in item.reference_evidence:
                route_id = route_by_artifact.get(reference.split("#", 1)[0])
                if route_id is not None:
                    observed_route_set.add(route_id)
            observed_routes = tuple(sorted(observed_route_set))
            if disposition in {"decide", "acquire"}:
                construct = self._legacy_source_construct(item)
                capability_id = (
                    f"capability:legacy:{stable_token(item.artifact_type)}:"
                    f"{stable_hash(item.evidence_id, length=16)}"
                )
                if disposition == "decide":
                    decision = self._decision(
                        "legacy-replacement",
                        capability_id,
                        (
                            f"Choose a deterministic Astro replacement for referenced "
                            f"{item.artifact_type} evidence {construct}."
                        ),
                        ("reproduce", "replace", "externalize", "omit-with-approval"),
                        item.evidence,
                    )
                    self._append_unique(decisions, decision)
                    decision_id = decision.decision_id
                    capability_disposition = CapabilityDispositionKind.NEEDS_DECISION
                    target_behavior = None
                    verification_method = None
                    required_decision = "Choose replacement behavior for public legacy evidence"
                else:
                    capability_disposition = CapabilityDispositionKind.REPRODUCE
                    target_behavior = "Acquire the bounded deferred payload before reproducing the observed public behavior"
                    verification_method = "legacy_payload_acquired_and_consumer_verified"
                    required_decision = None
                capabilities.append(
                    CapabilityDisposition(
                        capability_id=capability_id,
                        capability_type=f"legacy_{item.artifact_type}",
                        source_construct=construct,
                        source_plugin=None
                        if item.source_plugin == "unknown"
                        else item.source_plugin,
                        business_critical=item.relationship_status == "referenced",
                        disposition=capability_disposition,
                        target_behavior=target_behavior,
                        verification_method=verification_method,
                        required_operator_decision=required_decision,
                        observed_route_ids=observed_routes,
                        lineage=_lineage(
                            CapabilityDisposition,
                            item.evidence,
                            "legacy-capability/1",
                            decision=decision_id,
                        ),
                    )
                )
            contract = LegacyEvidenceContract(
                contract_id=contract_id,
                source_evidence_id=item.evidence_id,
                artifact_type=item.artifact_type,
                source_plugin=item.source_plugin,
                plugin_status=item.plugin_status,
                classification=classification,
                disposition=disposition,
                source_identity=item.source_identity,
                relationship_status=item.relationship_status,
                public_reference_count=item.public_reference_count,
                reference_evidence=item.reference_evidence,
                payload_status=item.payload.status,
                payload_method=item.payload.method,
                payload_artifact=item.payload.artifact,
                payload_sha256=item.payload.sha256,
                payload_bytes=item.payload.bytes,
                capability_id=capability_id,
                decision_id=decision_id,
                reason=item.payload.reason,
                lineage=_lineage(
                    LegacyEvidenceContract,
                    item.evidence,
                    "legacy-relevance/1",
                    decision=decision_id,
                ),
            )
            contracts.append(contract)
            finding_code = {
                "dormant": "legacy_evidence_dormant",
                "deferred": "legacy_payload_deferred",
                "referenced_orphan": "legacy_referenced_orphan",
                "required": "legacy_evidence_required",
                "unknown": "legacy_evidence_unknown",
            }[classification]
            severity: Literal["info", "warning", "error"] = (
                "warning" if disposition in {"decide", "acquire"} else "info"
            )
            self._append_unique(
                findings,
                self._finding(
                    finding_code,
                    severity,
                    contract_id,
                    (
                        f"Legacy {item.artifact_type} evidence is classified as "
                        f"{classification} with disposition {disposition}."
                    ),
                    item.evidence,
                    decision_id,
                ),
            )
        return contracts, capabilities

    @staticmethod
    def _legacy_classification(
        item: RawLegacyEvidence,
    ) -> Literal["required", "referenced_orphan", "dormant", "unknown", "deferred"]:
        referenced = (
            item.relationship_status == "referenced"
            or item.public_reference_count > 0
        )
        if item.payload.status == "deferred" and referenced:
            return "deferred"
        if item.plugin_status == "active" and referenced:
            return "required"
        if item.plugin_status in {"inactive", "missing"} and referenced:
            return "referenced_orphan"
        if (
            item.plugin_status in {"inactive", "missing"}
            and item.relationship_status == "unreferenced"
        ):
            return "dormant"
        return "unknown"

    @staticmethod
    def _legacy_disposition(
        item: RawLegacyEvidence,
        classification: Literal[
            "required", "referenced_orphan", "dormant", "unknown", "deferred"
        ],
    ) -> Literal["convert", "audit", "acquire", "decide"]:
        if classification == "dormant":
            return "audit"
        if classification == "deferred":
            return "acquire"
        if classification == "unknown" and item.relationship_status != "referenced":
            return "audit"
        if (
            item.artifact_type == "block"
            and item.source_identity.get("name", "").casefold()
            in SUPPORTED_PRESENTATION_BLOCKS
        ):
            return "convert"
        if item.artifact_type == "postmeta_field":
            return "convert"
        return "decide"

    @staticmethod
    def _legacy_source_construct(item: RawLegacyEvidence) -> str:
        for key in ("tag", "name", "table_name", "field_name"):
            if key in item.source_identity:
                return f"{item.artifact_type}:{item.source_identity[key]}"
        return f"{item.artifact_type}:{item.evidence_id}"
