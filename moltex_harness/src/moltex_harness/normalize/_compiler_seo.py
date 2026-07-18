"""Contract compiler implementation component."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any


from moltex_harness.models import (
    ContentRecord,
    DecisionItem,
    EvidenceReference,
    NormalizationFinding,
    RawSourceEvidence,
    RedirectContract,
    RouteContract,
    SeoContract,
)

from .primitives import (
    NormalizationValueError,
    absolute_url,
    normalize_route_path,
    stable_hash,
)

from ._compiler_support import (
    ContractCompilationError,
    _CompilerSupport,
    _field_ref,
    _lineage,
)


class _SeoCompilerMixin(_CompilerSupport):
    def _seo(
        self,
        raw: RawSourceEvidence,
        routes: list[RouteContract],
        content_by_id: dict[str, ContentRecord],
        origin: str,
        trailing: str,
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> list[SeoContract]:
        evidence = raw.seo[0].evidence if raw.seo else raw.site[0].evidence
        pages: list[Any] = []
        if raw.seo and isinstance(raw.seo[0].data, dict):
            candidate = raw.seo[0].data.get("pages", [])
            pages = candidate if isinstance(candidate, list) else []
        by_route: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        for index, page in enumerate(pages):
            if not isinstance(page, dict) or not page.get("canonical_url"):
                continue
            try:
                route_path = normalize_route_path(
                    str(page["canonical_url"]), origin, trailing
                )
            except NormalizationValueError:
                continue
            by_route[route_path].append((index, page))

        contracts: list[SeoContract] = []
        for route in routes:
            record = content_by_id.get(route.source_content_id)
            matches = by_route.get(route.target_url, [])
            needs_decision = False
            precedence = "content_fallback/1"
            title = record.title if record else route.required_content_markers[0]
            description = None
            canonical = absolute_url(origin, route.target_url)
            robots = "index,follow"
            open_graph: dict[str, Any] = {}
            hints: tuple[str, ...] = ()
            refs: tuple[EvidenceReference, ...] = (
                record.lineage["title"].inputs[0]
                if record
                else route.lineage["required_content_markers"].inputs[0],
            )
            if matches:
                fingerprints = {
                    json.dumps(
                        {
                            key: page.get(key)
                            for key in (
                                "resolved_title",
                                "meta_description",
                                "canonical_url",
                                "noindex",
                                "nofollow",
                                "og_metadata",
                                "schema_type_hints",
                            )
                        },
                        sort_keys=True,
                        default=str,
                    )
                    for _, page in matches
                }
                index, page = sorted(matches, key=lambda item: item[0])[0]
                page_ref = _field_ref(evidence, f"/pages/{index}")
                refs = (
                    page_ref,
                    record.lineage["title"].inputs[0]
                    if record
                    else route.lineage["required_content_markers"].inputs[0],
                )
                if len(fingerprints) > 1:
                    needs_decision = True
                    precedence = "seo_conflict_needs_decision/1"
                    decision = self._decision(
                        "seo-conflict",
                        route.contract_id,
                        "Choose the authoritative SEO evidence for this route.",
                        ("seo_full", "content_metadata", "operator_value"),
                        page_ref,
                    )
                    self._append_unique(decisions, decision)
                    self._append_unique(
                        findings,
                        self._finding(
                            "seo_evidence_conflict",
                            "warning",
                            route.contract_id,
                            "Conflicting SEO records target the same route.",
                            page_ref,
                            decision.decision_id,
                        ),
                    )
                else:
                    title = str(
                        page.get("resolved_title")
                        or page.get("title_template")
                        or title
                    )
                    description = (
                        str(page["meta_description"])
                        if page.get("meta_description")
                        else None
                    )
                    canonical = absolute_url(
                        origin,
                        normalize_route_path(
                            str(page.get("canonical_url") or route.target_url),
                            origin,
                            trailing,
                        ),
                    )
                    flags = []
                    flags.append("noindex" if page.get("noindex") else "index")
                    flags.append("nofollow" if page.get("nofollow") else "follow")
                    robots = ",".join(flags)
                    raw_og = page.get("og_metadata")
                    open_graph = (
                        raw_og if isinstance(raw_og, dict) else {"items": raw_og or []}
                    )
                    raw_hints = page.get("schema_type_hints")
                    hints = (
                        tuple(sorted(str(value) for value in raw_hints))
                        if isinstance(raw_hints, list)
                        else ()
                    )
                    precedence = "seo_full_over_content/1"
            else:
                self._append_unique(
                    findings,
                    self._finding(
                        "seo_fallback_used",
                        "info",
                        route.contract_id,
                        "No route-specific SEO evidence exists; content title is preserved.",
                        refs[0],
                    ),
                )
            contracts.append(
                SeoContract(
                    contract_id=route.seo_contract_id,
                    route_contract_id=route.contract_id,
                    target_route=route.target_url,
                    title=title,
                    description=description,
                    canonical_url=canonical,
                    robots=robots,
                    open_graph=open_graph,
                    structured_data_hints=hints,
                    precedence_decision=precedence,
                    needs_decision=needs_decision,
                    lineage=_lineage(
                        SeoContract, refs, precedence, decision=precedence
                    ),
                )
            )
        return contracts

    def _redirects(
        self,
        raw: RawSourceEvidence,
        routes: list[RouteContract],
        origin: str,
        trailing: str,
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> list[RedirectContract]:
        route_by_path = {route.target_url: route for route in routes}
        contracts: list[RedirectContract] = []
        for artifact in raw.redirects:
            rows = artifact.data if isinstance(artifact.data, list) else []
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                source = str(
                    row.get("source") or row.get("from") or row.get("source_url") or ""
                )
                target = str(
                    row.get("target") or row.get("to") or row.get("target_url") or ""
                )
                if not source or not target:
                    continue
                source_path = normalize_route_path(source, origin, trailing)
                target_path = normalize_route_path(target, origin, trailing)
                target_route = route_by_path.get(target_path)
                status = int(row.get("status") or row.get("status_code") or 301)
                ref = _field_ref(artifact.evidence, f"/{index}")
                needs_decision = target_route is None
                if needs_decision:
                    decision = self._decision(
                        "redirect-target",
                        source_path,
                        "Choose a valid public target for this redirect.",
                        ("map_to_route", "externalize", "omit-with-approval"),
                        ref,
                    )
                    self._append_unique(decisions, decision)
                    self._append_unique(
                        findings,
                        self._finding(
                            "redirect_target_missing",
                            "warning",
                            source_path,
                            "Redirect target does not resolve to a public route.",
                            ref,
                            decision.decision_id,
                        ),
                    )
                contracts.append(
                    RedirectContract(
                        contract_id=f"redirect:{stable_hash(source_path, target_path)}",
                        source_url=source_path,
                        target_url=target_path,
                        status_code=status,
                        target_route_contract_id=target_route.contract_id
                        if target_route
                        else None,
                        needs_decision=needs_decision,
                        lineage=_lineage(
                            RedirectContract, ref, "redirect-normalization/1"
                        ),
                    )
                )
        declared_sources = {contract.source_url for contract in contracts}
        for route in routes:
            if not route.redirect_required or route.legacy_url in declared_sources:
                continue
            contracts.append(
                RedirectContract(
                    contract_id=f"redirect:route:{stable_hash(route.contract_id)}",
                    source_url=route.legacy_url,
                    target_url=route.target_url,
                    status_code=301,
                    target_route_contract_id=route.contract_id,
                    needs_decision=False,
                    lineage=_lineage(
                        RedirectContract,
                        route.lineage["legacy_url"].inputs,
                        "route-change-redirect/1",
                        decision="preserve_legacy_access",
                    ),
                )
            )
        if len({item.source_url for item in contracts}) != len(contracts):
            raise ContractCompilationError(
                "redirect_collision", "More than one redirect has the same source URL"
            )
        return contracts
