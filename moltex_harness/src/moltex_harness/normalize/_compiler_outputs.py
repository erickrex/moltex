"""Navigation, manifest, site, parity, and visual-plan compilation."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Literal
from urllib.parse import urljoin


from moltex_harness.intake.serialization import deterministic_json
from moltex_harness.models import (
    CapabilityDisposition,
    CapabilityDispositionKind,
    ContentRecord,
    DecisionItem,
    NavigationItem,
    NormalizationFinding,
    ParityRow,
    RawArtifactEvidence,
    RawSourceEvidence,
    RouteContract,
    SiteSpec,
    SourceManifest,
    StaticEligibility,
    UrlMapEntry,
    ViewportProfile,
    VisualCapturePlan,
    VisualCaptureTarget,
)

from .primitives import (
    NormalizationValueError,
    normalize_route_path,
    stable_hash,
    stable_token,
)

from ._compiler_support import (
    ContractCompilationError,
    _CompilerSupport,
    _field_ref,
    _lineage,
)


_VISUAL_BLOCK_COMMENT = re.compile(
    r"<!--\s*wp:([a-z0-9_-]+(?:/[a-z0-9_-]+)?)(?:\s+(\{.*?\}))?\s*/?-->",
    re.IGNORECASE | re.DOTALL,
)


class _OutputCompilerMixin(_CompilerSupport):

    def _navigation(
        self,
        raw: RawSourceEvidence,
        route_by_source: dict[str, RouteContract],
        route_by_path: dict[str, RouteContract],
        origin: str,
        trailing: Literal["always", "never"],
        findings: list[NormalizationFinding],
    ) -> list[NavigationItem]:
        result: list[NavigationItem] = []
        for artifact in raw.navigation:
            data = artifact.data if isinstance(artifact.data, dict) else {}
            menus = data.get("menus", [])
            for menu_index, menu in enumerate(menus if isinstance(menus, list) else []):
                if not isinstance(menu, dict):
                    continue
                menu_id = self._menu_id(menu, menu_index)
                items = menu.get("items", [])
                raw_ids = {
                    str(item.get("id")): f"navigation:{stable_token(item.get('id'))}"
                    for item in items
                    if isinstance(item, dict) and item.get("id") is not None
                }
                for item_index, item in enumerate(
                    items if isinstance(items, list) else []
                ):
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("id") or item_index)
                    navigation_id = raw_ids.get(
                        item_id, f"navigation:{stable_token(item_id)}"
                    )
                    object_id = (
                        str(item.get("object_id"))
                        if item.get("object_id") is not None
                        else ""
                    )
                    route = route_by_source.get(object_id)
                    if route is None and item.get("url"):
                        try:
                            path = normalize_route_path(
                                str(item["url"]), origin, trailing
                            )
                            route = route_by_path.get(path)
                        except NormalizationValueError:
                            route = None
                    ref = _field_ref(
                        artifact.evidence, f"/menus/{menu_index}/items/{item_index}"
                    )
                    if route is None:
                        self._append_unique(
                            findings,
                            self._finding(
                                "menu_route_missing",
                                "warning",
                                navigation_id,
                                "Navigation item does not resolve to a public route contract.",
                                ref,
                            ),
                        )
                    parent = str(item.get("parent_id") or "0")
                    result.append(
                        NavigationItem(
                            navigation_id=navigation_id,
                            menu_id=menu_id,
                            label=str(item.get("title") or "").strip(),
                            route_contract_id=route.contract_id if route else None,
                            parent_navigation_id=raw_ids.get(parent)
                            if parent != "0"
                            else None,
                            order=int(item.get("menu_order") or item_index),
                            lineage=_lineage(
                                NavigationItem, ref, "menu-route-resolution/1"
                            ),
                        )
                    )
        return sorted(
            result, key=lambda item: (item.menu_id, item.order, item.navigation_id)
        )

    @staticmethod
    def _menu_id(menu: dict[str, Any], menu_index: int) -> str:
        identity = stable_token(
            menu.get("term_id") or menu.get("slug") or menu_index
        )
        locations = menu.get("locations", [])
        is_primary = isinstance(locations, list) and "primary" in locations
        return f"menu:{'primary:' if is_primary else ''}{identity}"

    @staticmethod
    def _url_map(routes: list[RouteContract], origin: str) -> list[UrlMapEntry]:
        entries: list[UrlMapEntry] = []
        seen: set[str] = set()
        for route in routes:
            evidence = route.lineage["legacy_url"].inputs
            sources = (
                route.legacy_url,
                urljoin(origin.rstrip("/") + "/", route.legacy_url),
            )
            for source in sources:
                if source in seen:
                    continue
                seen.add(source)
                entries.append(
                    UrlMapEntry(
                        source_url=source,
                        target_url=route.target_url,
                        route_contract_id=route.contract_id,
                        lineage=_lineage(UrlMapEntry, evidence, "immutable-url-map/1"),
                    )
                )
        return entries

    def _source_manifest(
        self, raw: RawSourceEvidence, site_id: str, origin: str
    ) -> SourceManifest:
        source = raw.source_manifest
        bundle_ref = source.evidence["bundle"]
        blockers = source.readiness.get("blockers", [])
        blocker_values = (
            tuple(str(value) for value in blockers)
            if isinstance(blockers, list)
            else ()
        )
        raw_hash = hashlib.sha256(deterministic_json(raw).encode("utf-8")).hexdigest()
        return SourceManifest(
            manifest_id=f"source-manifest:{stable_hash(source.bundle_id)}",
            bundle_id=source.bundle_id,
            source_schema=source.source_schema,
            archive_sha256=source.archive_sha256,
            exporter_version=source.exporter_version,
            site_id=site_id,
            site_origin=origin,
            complete=source.complete,
            privacy=source.privacy,
            counts=source.counts,
            inventory=tuple(raw.inventory),
            warnings=tuple(source.warnings),
            blockers=blocker_values,
            omissions=tuple(source.omissions),
            raw_evidence_sha256=raw_hash,
            lineage=_lineage(
                SourceManifest,
                bundle_ref,
                "h1-source-manifest/1",
                overrides={
                    "site_id": ((source.evidence["site"],), "site-identity/1", None),
                    "site_origin": (
                        (source.evidence["site"],),
                        "origin-normalization/1",
                        None,
                    ),
                    "counts": ((source.evidence["counts"],), "intake-counts/1", None),
                    "privacy": (
                        (source.evidence["privacy"],),
                        "intake-privacy/1",
                        None,
                    ),
                    "blockers": (
                        (source.evidence["readiness"],),
                        "intake-readiness/1",
                        None,
                    ),
                    "raw_evidence_sha256": (
                        (bundle_ref,),
                        "raw-evidence-serialization/1",
                        None,
                    ),
                },
            ),
        )

    def _site_spec(
        self,
        raw: RawSourceEvidence,
        blueprint: RawArtifactEvidence,
        settings: RawArtifactEvidence,
        site_id: str,
        origin: str,
        trailing: Literal["always", "never"],
        content: list[ContentRecord],
        routes: list[RouteContract],
        navigation: list[NavigationItem],
        capabilities: list[CapabilityDisposition],
        decisions: list[DecisionItem],
    ) -> SiteSpec:
        site_data = blueprint.data if isinstance(blueprint.data, dict) else {}
        source_site_value = site_data.get("site")
        source_site: dict[str, Any] = (
            source_site_value if isinstance(source_site_value, dict) else {}
        )
        settings_data = settings.data if isinstance(settings.data, dict) else {}
        core_value = settings_data.get("core")
        core: dict[str, Any] = core_value if isinstance(core_value, dict) else {}
        site_name = str(
            source_site.get("site_title")
            or core.get("site_title")
            or core.get("name")
            or "Untitled site"
        )
        language_value = settings_data.get("language")
        language: dict[str, Any] = (
            language_value if isinstance(language_value, dict) else {}
        )
        locale = str(source_site.get("language") or language.get("locale") or "und")
        collections: list[dict[str, Any]] = []
        counts: dict[str, int] = defaultdict(int)
        for record in content:
            if record.status == "publish":
                counts[record.content_type] += 1
        for content_type, count in sorted(counts.items()):
            collections.append(
                {
                    "id": f"collection:{stable_token(content_type)}",
                    "content_type": content_type,
                    "public_records": count,
                }
            )
        theme_value = site_data.get("theme")
        theme: dict[str, Any] = theme_value if isinstance(theme_value, dict) else {}
        layout = ["responsive-desktop-mobile", "preserve-global-navigation"]
        if theme.get("name"):
            layout.append(f"source-theme-evidence:{theme['name']}")
        readiness = raw.source_manifest.readiness
        eligible = readiness.get("eligible")
        blockers = readiness.get("blockers", [])
        unsupported_builder = any(
            item.capability_type == "unsupported_page_builder" for item in capabilities
        )
        if eligible is False or blockers or unsupported_builder:
            static_eligibility = StaticEligibility.INELIGIBLE
        elif any(decision.severity == "blocking" for decision in decisions):
            static_eligibility = StaticEligibility.NEEDS_DECISION
        else:
            static_eligibility = StaticEligibility.ELIGIBLE
        refs = (blueprint.evidence, settings.evidence)
        return SiteSpec(
            site_id=site_id,
            site_name=site_name,
            locale=locale,
            source_origin=origin,
            target_canonical_origin=origin,
            trailing_slash_policy=trailing,
            collection_definitions=tuple(collections),
            route_families=tuple(sorted({route.page_family for route in routes})),
            global_navigation=tuple(navigation),
            global_layout_requirements=tuple(layout),
            capability_ids=tuple(sorted(item.capability_id for item in capabilities)),
            unresolved_decision_ids=tuple(
                sorted(item.decision_id for item in decisions)
            ),
            static_eligibility=static_eligibility,
            lineage=_lineage(
                SiteSpec,
                refs,
                "site-spec/1",
                overrides={
                    "target_canonical_origin": (
                        (blueprint.evidence,),
                        "canonical-origin-preserve-source/1",
                        "preserve_source_origin",
                    ),
                    "global_navigation": (
                        (
                            raw.navigation[0].evidence
                            if raw.navigation
                            else blueprint.evidence,
                        ),
                        "menu-route-resolution/1",
                        None,
                    ),
                    "static_eligibility": (
                        (raw.source_manifest.evidence["readiness"],),
                        "static-eligibility/1",
                        static_eligibility.value,
                    ),
                },
            ),
        )

    @staticmethod
    def _parity(
        routes: list[RouteContract], capabilities: list[CapabilityDisposition]
    ) -> list[ParityRow]:
        rows: list[ParityRow] = []
        for route in routes:
            evidence = route.lineage["contract_id"].inputs
            rows.append(
                ParityRow(
                    row_id=f"parity:route:{stable_hash(route.contract_id)}",
                    subject_type="route",
                    subject_id=route.source_content_id,
                    route_contract_id=route.contract_id,
                    capability_id=None,
                    state="pending",
                    required_checks=("content", "layout", "responsive", "seo"),
                    lineage=_lineage(ParityRow, evidence, "parity-route-seed/1"),
                )
            )
        for capability in capabilities:
            evidence = capability.lineage["capability_id"].inputs
            rows.append(
                ParityRow(
                    row_id=f"parity:capability:{stable_hash(capability.capability_id)}",
                    subject_type="capability",
                    subject_id=capability.capability_id,
                    route_contract_id=None,
                    capability_id=capability.capability_id,
                    state="blocked"
                    if capability.disposition
                    == CapabilityDispositionKind.NEEDS_DECISION
                    else "pending",
                    required_checks=("disposition", "target_behavior", "verification"),
                    lineage=_lineage(ParityRow, evidence, "parity-capability-seed/1"),
                )
            )
        return rows

    def _visual_plan(
        self,
        raw: RawSourceEvidence,
        routes: list[RouteContract],
        capabilities: list[CapabilityDisposition],
        navigation: list[NavigationItem],
        content: list[ContentRecord],
        origin: str,
    ) -> VisualCapturePlan:
        if not routes:
            raise ContractCompilationError(
                "visual_plan_empty", "No public route is available for visual capture"
            )
        chosen: dict[str, tuple[RouteContract, str]] = {}
        home = next((route for route in routes if route.target_url == "/"), None)
        if home:
            chosen[home.contract_id] = (home, "homepage")
        route_lookup = {route.contract_id: route for route in routes}
        primary_menu_ids = {
            item.menu_id
            for item in navigation
            if item.menu_id.startswith("menu:primary:")
        }
        if not primary_menu_ids and navigation:
            menu_sizes: dict[str, int] = defaultdict(int)
            for item in navigation:
                menu_sizes[item.menu_id] += 1
            primary_menu_ids = {
                max(menu_sizes, key=lambda menu_id: (menu_sizes[menu_id], menu_id))
            }
        for item in sorted(navigation, key=lambda value: (value.order, value.navigation_id)):
            route = route_lookup.get(item.route_contract_id or "")
            if route is not None and item.menu_id in primary_menu_ids:
                chosen.setdefault(route.contract_id, (route, "primary-navigation"))
        for family in sorted({route.page_family for route in routes}):
            representative = sorted(
                (route for route in routes if route.page_family == family),
                key=lambda route: (route.target_url, route.contract_id),
            )[0]
            chosen.setdefault(
                representative.contract_id, (representative, f"representative:{family}")
            )
        content_by_id = {record.record_id: record for record in content}
        covered_signatures: set[str] = set()
        for route, _ in chosen.values():
            record = content_by_id.get(route.content_record_id or "")
            if record is not None:
                covered_signatures.update(self._visual_block_signatures(record.original_html))
        for route in sorted(routes, key=lambda value: (value.target_url, value.contract_id)):
            record = content_by_id.get(route.content_record_id or "")
            if record is None:
                continue
            signatures = self._visual_block_signatures(record.original_html)
            novel = signatures - covered_signatures
            if novel:
                chosen.setdefault(
                    route.contract_id,
                    (route, f"block-signatures:{len(novel)}"),
                )
                covered_signatures.update(signatures)
        for capability in sorted(capabilities, key=lambda item: item.capability_id):
            if (
                not capability.business_critical
                and capability.disposition != CapabilityDispositionKind.NEEDS_DECISION
            ):
                continue
            observed = capability.observed_route_ids or (
                (home.contract_id,) if home else ()
            )
            route = next(
                (
                    route_lookup[route_id]
                    for route_id in observed
                    if route_id in route_lookup
                ),
                None,
            )
            if route:
                chosen.setdefault(
                    route.contract_id,
                    (route, f"capability:{capability.capability_id}"),
                )
        selected = list(chosen.values())
        viewports = (
            ViewportProfile(name="desktop-1440x1200", width=1440, height=1200),
            ViewportProfile(name="mobile-500x844", width=500, height=844),
        )
        targets: list[VisualCaptureTarget] = []
        for route, reason in sorted(selected, key=lambda item: item[0].contract_id):
            route_evidence = route.lineage["contract_id"].inputs
            source_url = urljoin(origin.rstrip("/") + "/", route.legacy_url)
            for viewport in viewports:
                target_id = f"visual:{stable_hash(raw.source_manifest.bundle_id, route.contract_id, viewport.name)}"
                targets.append(
                    VisualCaptureTarget(
                        target_id=target_id,
                        evidence_id=f"visual-evidence:{stable_hash(route.contract_id, viewport.name, length=32)}",
                        route_contract_id=route.contract_id,
                        source_url=source_url,
                        viewport=viewport,
                        selection_reason=reason,
                        route_family=route.page_family,
                        lineage=_lineage(
                            VisualCaptureTarget,
                            route_evidence,
                            "visual-target-selection/1",
                            decision=reason,
                        ),
                    )
                )
        target_ids = tuple(target.target_id for target in targets)
        plan_id = f"visual-plan:{stable_hash(raw.source_manifest.bundle_id, *target_ids, length=32)}"
        plan_evidence = tuple(
            reference
            for route, _ in selected
            for reference in route.lineage["contract_id"].inputs
        )
        return VisualCapturePlan(
            plan_id=plan_id,
            source_bundle_id=raw.source_manifest.bundle_id,
            max_routes=len(routes),
            selected_route_ids=tuple(
                sorted(route.contract_id for route, _ in selected)
            ),
            targets=tuple(targets),
            lineage=_lineage(VisualCapturePlan, plan_evidence, "visual-capture-plan/1"),
        )

    @staticmethod
    def _visual_block_signatures(source: str) -> set[str]:
        """Identify distinct block attribute shapes without coupling to values."""

        def shape(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    str(key): shape(item)
                    for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                }
            if isinstance(value, list):
                return sorted(
                    {
                        json.dumps(shape(item), sort_keys=True, separators=(",", ":"))
                        for item in value
                    }
                )
            if value is None:
                return "null"
            if isinstance(value, bool):
                return "boolean"
            if isinstance(value, (int, float)):
                return "number"
            return "string"

        signatures: set[str] = set()
        for match in _VISUAL_BLOCK_COMMENT.finditer(source):
            name = match.group(1).casefold()
            name = name if "/" in name else f"core/{name}"
            attributes: Any = {}
            if match.group(2):
                try:
                    attributes = json.loads(match.group(2))
                except json.JSONDecodeError:
                    attributes = {"$malformed": True}
            payload = json.dumps(shape(attributes), sort_keys=True, separators=(",", ":"))
            signatures.add(f"{name}:{hashlib.sha256(payload.encode()).hexdigest()[:16]}")
        return signatures
