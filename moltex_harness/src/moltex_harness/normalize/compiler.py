"""Deterministic H2 compiler from raw source evidence to migration contracts."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from moltex_harness.models import (
    ContractSet,
    DecisionItem,
    NormalizationFinding,
    RawSourceEvidence,
    RouteContract,
)

from ._compiler_assets import _AssetCompilerMixin
from ._compiler_capabilities import _CapabilityCompilerMixin
from ._compiler_content import _ContentCompilerMixin
from ._compiler_legacy import _LegacyEvidenceCompilerMixin
from ._compiler_outputs import _OutputCompilerMixin
from ._compiler_routes import _RouteCompilerMixin
from ._compiler_seo import _SeoCompilerMixin
from ._compiler_support import ContractCompilationError
from .primitives import normalize_origin, stable_hash


class ContractCompiler(
    _RouteCompilerMixin,
    _AssetCompilerMixin,
    _ContentCompilerMixin,
    _SeoCompilerMixin,
    _CapabilityCompilerMixin,
    _LegacyEvidenceCompilerMixin,
    _OutputCompilerMixin,
):
    """Compile H1 evidence without generating target files or Astro code."""

    compiler_version = "h2-contracts/1"
    def compile(self, raw: RawSourceEvidence) -> ContractSet:
        if not isinstance(raw, RawSourceEvidence):
            raise ContractCompilationError(
                "normalized_input_rejected",
                "H2 accepts RawSourceEvidence only; canonical contracts cannot be normalized twice",
            )
        findings: list[NormalizationFinding] = []
        decisions: list[DecisionItem] = []
        blueprint = self._artifact(raw, "site_blueprint.json")
        settings = self._artifact(raw, "site_settings.json")
        site_data = blueprint.data if isinstance(blueprint.data, dict) else {}
        settings_data = settings.data if isinstance(settings.data, dict) else {}
        site_value = site_data.get("site")
        site_values: dict[str, Any] = site_value if isinstance(site_value, dict) else {}
        core_value = settings_data.get("core")
        core: dict[str, Any] = core_value if isinstance(core_value, dict) else {}
        origin = normalize_origin(
            str(
                raw.source_manifest.site_origin
                or site_values.get("url")
                or core.get("site_url")
                or ""
            )
        )
        trailing_policy = self._trailing_policy(site_values, raw.content)
        site_id = f"site:{stable_hash(origin)}"
        reading_value = settings_data.get("reading")
        reading: dict[str, Any] = (
            reading_value if isinstance(reading_value, dict) else {}
        )
        front_id = self._nested_id(reading.get("page_on_front"))
        posts_id = self._nested_id(reading.get("page_for_posts"))

        routes = self._routes(raw, origin, trailing_policy, front_id, posts_id)
        route_by_source = {route.source_content_id: route for route in routes}
        route_by_path = {route.target_url: route for route in routes}
        route_by_legacy: dict[str, RouteContract] = {}
        for route in routes:
            route_by_legacy[route.legacy_url] = route
            route_by_legacy[urljoin(origin.rstrip("/") + "/", route.legacy_url)] = route
        if len(route_by_path) != len(routes):
            raise ContractCompilationError(
                "route_collision",
                "Multiple public records normalize to one target route",
            )

        assets, media_map, media_ids_by_content = self._assets(
            raw, origin, findings, decisions
        )
        content_records = self._content_records(
            raw,
            origin,
            trailing_policy,
            route_by_path,
            route_by_legacy,
            media_ids_by_content,
            findings,
            decisions,
        )
        content_by_id = {record.source_id: record for record in content_records}
        seo = self._seo(
            raw,
            routes,
            content_by_id,
            origin,
            trailing_policy,
            findings,
            decisions,
        )
        redirects = self._redirects(
            raw, routes, origin, trailing_policy, findings, decisions
        )
        capabilities = self._capabilities(raw, routes, findings, decisions)
        legacy_evidence, legacy_capabilities = self._legacy_evidence_contracts(
            raw, routes, findings, decisions
        )
        capabilities.extend(legacy_capabilities)
        capability_ids = [item.capability_id for item in capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ContractCompilationError(
                "legacy_capability_collision",
                "Legacy evidence produced a duplicate capability identity",
            )
        navigation = self._navigation(
            raw,
            route_by_source,
            route_by_path,
            origin,
            trailing_policy,
            findings,
        )
        url_map = self._url_map(routes, origin)
        source_manifest = self._source_manifest(raw, site_id, origin)
        site_spec = self._site_spec(
            raw,
            blueprint,
            settings,
            site_id,
            origin,
            trailing_policy,
            content_records,
            routes,
            navigation,
            capabilities,
            decisions,
        )
        parity = self._parity(routes, capabilities)
        visual_plan = self._visual_plan(
            raw,
            routes,
            capabilities,
            navigation,
            content_records,
            origin,
        )

        contracts = ContractSet(
            source_manifest=source_manifest,
            site_spec=site_spec,
            content_records=tuple(
                sorted(content_records, key=lambda item: item.record_id)
            ),
            routes=tuple(sorted(routes, key=lambda item: item.contract_id)),
            assets=tuple(sorted(assets, key=lambda item: item.asset_id)),
            seo=tuple(sorted(seo, key=lambda item: item.contract_id)),
            redirects=tuple(sorted(redirects, key=lambda item: item.contract_id)),
            capabilities=tuple(
                sorted(capabilities, key=lambda item: item.capability_id)
            ),
            legacy_evidence=tuple(
                sorted(legacy_evidence, key=lambda item: item.contract_id)
            ),
            url_map=tuple(
                sorted(url_map, key=lambda item: (item.source_url, item.target_url))
            ),
            media_map=tuple(sorted(media_map, key=lambda item: item.source_url)),
            visual_capture_plan=visual_plan,
            parity_matrix=tuple(sorted(parity, key=lambda item: item.row_id)),
            findings=tuple(sorted(findings, key=lambda item: item.finding_id)),
            decisions=tuple(sorted(decisions, key=lambda item: item.decision_id)),
        )
        return contracts.model_copy(
            update={"evidence_resolutions": self._evidence_resolutions(raw, contracts)}
        )
