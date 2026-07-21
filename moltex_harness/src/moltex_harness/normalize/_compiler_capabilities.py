"""Contract compiler implementation component."""

from __future__ import annotations

from typing import Any

from moltex_harness.intake.artifacts import CAPABILITY_CONSUMERS
from moltex_harness.intake.serialization import deterministic_json
from moltex_harness.models import (
    CapabilityDisposition,
    CapabilityDispositionKind,
    DecisionItem,
    EvidenceReference,
    NormalizationFinding,
    RawSourceEvidence,
    RouteContract,
)

from .primitives import (
    stable_token,
)

from ._compiler_support import (
    ContractCompilationError,
    _CompilerSupport,
    _field_ref,
    _json_pointer_token,
    _lineage,
)


class _CapabilityCompilerMixin(_CompilerSupport):
    def _capabilities(
        self,
        raw: RawSourceEvidence,
        routes: list[RouteContract],
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> list[CapabilityDisposition]:
        capabilities = self._page_builder_capabilities(raw, routes, findings, decisions)
        content_by_route = {
            route.contract_id: next(
                (
                    content
                    for content in raw.content
                    if str(content.source_id) == route.source_content_id
                ),
                None,
            )
            for route in routes
        }
        for artifact in raw.capabilities:
            if artifact.artifact not in CAPABILITY_CONSUMERS:
                raise ContractCompilationError(
                    "unsupported_capability_artifact",
                    f"No canonical capability consumer exists for {artifact.artifact}",
                )
            data = artifact.data if isinstance(artifact.data, dict) else {}
            if artifact.artifact == "integration_manifest.json":
                entries = data.get("integrations", [])
                for index, entry in enumerate(
                    entries if isinstance(entries, list) else []
                ):
                    if not isinstance(entry, dict):
                        continue
                    integration_id = str(
                        entry.get("integration_id") or f"integration-{index}"
                    )
                    target = str(entry.get("target") or "unknown").lower()
                    known_external = target in {
                        "youtube",
                        "vimeo",
                        "mapbox",
                        "google-maps",
                    }
                    disposition = (
                        CapabilityDispositionKind.EXTERNALIZE
                        if known_external
                        else CapabilityDispositionKind.NEEDS_DECISION
                    )
                    pattern = ""
                    if isinstance(entry.get("config"), dict):
                        pattern = str(entry["config"].get("pattern") or target)
                    observed = tuple(
                        sorted(
                            route_id
                            for route_id, content in content_by_route.items()
                            if content
                            and pattern
                            and pattern.lower() in content.original_html.lower()
                        )
                    )
                    ref = _field_ref(artifact.evidence, f"/integrations/{index}")
                    capability = CapabilityDisposition(
                        capability_id=f"capability:integration:{stable_token(integration_id)}",
                        capability_type=str(
                            entry.get("integration_type") or "integration"
                        ),
                        source_construct=integration_id,
                        source_plugin=None,
                        business_critical=bool(entry.get("business_critical", False)),
                        disposition=disposition,
                        target_behavior=f"Preserve the external {target} integration"
                        if known_external
                        else None,
                        verification_method="rendered_external_origin"
                        if known_external
                        else None,
                        required_operator_decision=None
                        if known_external
                        else "Choose integration target behavior",
                        observed_route_ids=observed,
                        lineage=_lineage(
                            CapabilityDisposition,
                            ref,
                            "integration-disposition/1",
                            decision=disposition.value,
                        ),
                    )
                    capabilities.append(capability)
                    self._capability_decision(capability, ref, findings, decisions)
            elif artifact.artifact == "forms_config.json":
                forms = data.get("forms", [])
                for index, form in enumerate(forms if isinstance(forms, list) else []):
                    if not isinstance(form, dict):
                        continue
                    identifier = str(form.get("id") or form.get("form_id") or index)
                    ref = _field_ref(artifact.evidence, f"/forms/{index}")
                    capability = CapabilityDisposition(
                        capability_id=f"capability:form:{stable_token(identifier)}",
                        capability_type="form",
                        source_construct=identifier,
                        source_plugin=str(form.get("plugin"))
                        if form.get("plugin")
                        else None,
                        business_critical=bool(form.get("business_critical", True)),
                        disposition=CapabilityDispositionKind.NEEDS_DECISION,
                        target_behavior=None,
                        verification_method=None,
                        required_operator_decision="Choose submission destination and privacy behavior",
                        observed_route_ids=(),
                        lineage=_lineage(
                            CapabilityDisposition,
                            ref,
                            "form-disposition/1",
                            decision="needs_decision",
                        ),
                    )
                    capabilities.append(capability)
                    self._capability_decision(capability, ref, findings, decisions)
            elif artifact.artifact == "shortcodes_inventory.json":
                summary_value = data.get("data")
                summary: dict[str, Any] = (
                    summary_value if isinstance(summary_value, dict) else data
                )
                used = int(summary.get("total_used", 0) or 0)
                if used:
                    ref = _field_ref(artifact.evidence, "/data/total_used")
                    capability = CapabilityDisposition(
                        capability_id="capability:shortcode:aggregate",
                        capability_type="shortcode",
                        source_construct=f"{used} used shortcode occurrences",
                        source_plugin=None,
                        business_critical=False,
                        disposition=CapabilityDispositionKind.NEEDS_DECISION,
                        target_behavior=None,
                        verification_method=None,
                        required_operator_decision="Map each used shortcode to target behavior",
                        observed_route_ids=(),
                        lineage=_lineage(
                            CapabilityDisposition,
                            ref,
                            "shortcode-disposition/1",
                            decision="needs_decision",
                        ),
                    )
                    capabilities.append(capability)
                    self._capability_decision(capability, ref, findings, decisions)
            elif artifact.artifact == "widgets.json":
                widgets = data.get("widgets")
                if isinstance(widgets, dict):
                    home = next(
                        (
                            route.contract_id
                            for route in routes
                            if route.target_url == "/"
                        ),
                        None,
                    )
                    for sidebar, entries in sorted(widgets.items()):
                        if not isinstance(entries, list) or not entries:
                            continue
                        ref = _field_ref(
                            artifact.evidence,
                            f"/widgets/{_json_pointer_token(str(sidebar))}",
                        )
                        capabilities.append(
                            CapabilityDisposition(
                                capability_id=f"capability:widget-area:{stable_token(sidebar)}",
                                capability_type="widget_area",
                                source_construct=str(sidebar),
                                source_plugin="wordpress-core",
                                business_critical=False,
                                disposition=CapabilityDispositionKind.REPRODUCE,
                                target_behavior="Reproduce visible widget-area content as static components",
                                verification_method="rendered_content_markers",
                                required_operator_decision=None,
                                observed_route_ids=(home,) if home else (),
                                lineage=_lineage(
                                    CapabilityDisposition,
                                    ref,
                                    "widget-area-disposition/1",
                                    decision="reproduce",
                                ),
                            )
                        )
            elif artifact.artifact == "plugins/plugins_fingerprint.json":
                fingerprints = data.get("fingerprints", [])
                for index, plugin in enumerate(
                    fingerprints if isinstance(fingerprints, list) else []
                ):
                    if not isinstance(plugin, dict) or not plugin.get("active"):
                        continue
                    slug = str(plugin.get("plugin_slug") or index)
                    if self._builder_from_plugin_slug(slug):
                        continue
                    if slug in {"moltex-exporter", "wordpress-seo"}:
                        continue
                    features_value = plugin.get("features")
                    features: dict[str, Any] = (
                        features_value if isinstance(features_value, dict) else {}
                    )
                    dynamic = sorted(
                        key
                        for key in ("has_rest_api", "has_cron_jobs", "has_widgets")
                        if features.get(key)
                    )
                    if not dynamic:
                        continue
                    ref = _field_ref(artifact.evidence, f"/fingerprints/{index}")
                    capability = CapabilityDisposition(
                        capability_id=f"capability:plugin:{stable_token(slug)}",
                        capability_type="dynamic_plugin",
                        source_construct=", ".join(dynamic),
                        source_plugin=slug,
                        business_critical=False,
                        disposition=CapabilityDispositionKind.NEEDS_DECISION,
                        target_behavior=None,
                        verification_method=None,
                        required_operator_decision="Choose static replacement or external service",
                        observed_route_ids=(),
                        lineage=_lineage(
                            CapabilityDisposition,
                            ref,
                            "plugin-capability-disposition/1",
                            decision="needs_decision",
                        ),
                    )
                    capabilities.append(capability)
                    self._capability_decision(capability, ref, findings, decisions)
            elif artifact.artifact == "geodirectory.json":
                post_types = data.get("post_types", {})
                if not isinstance(post_types, dict):
                    continue
                for post_type, configuration in sorted(post_types.items()):
                    if not isinstance(configuration, dict):
                        continue
                    token = stable_token(post_type)
                    observed = tuple(
                        sorted(
                            route_id
                            for route_id, content in content_by_route.items()
                            if content and content.content_type == post_type
                        )
                    )
                    ref = _field_ref(
                        artifact.evidence,
                        f"/post_types/{_json_pointer_token(str(post_type))}",
                    )
                    capabilities.append(
                        CapabilityDisposition(
                            capability_id=f"capability:geodirectory:{token}:listing",
                            capability_type="directory_listing",
                            source_construct=str(post_type),
                            source_plugin="geodirectory",
                            business_critical=True,
                            disposition=CapabilityDispositionKind.REPRODUCE,
                            target_behavior=(
                                "Reproduce public listing fields, location, gallery, "
                                "taxonomy, tabs, and approved review display"
                            ),
                            verification_method=(
                                "listing_contract_fields_and_rendered_content_markers"
                            ),
                            required_operator_decision=None,
                            observed_route_ids=observed,
                            lineage=_lineage(
                                CapabilityDisposition,
                                ref,
                                "geodirectory-listing-disposition/1",
                                decision="reproduce",
                            ),
                        )
                    )
                    interactive = {
                        key: configuration.get(key, [])
                        for key in ("search_fields", "sort_fields")
                        if isinstance(configuration.get(key), list)
                        and configuration.get(key)
                    }
                    if interactive:
                        interactive_ref = _field_ref(
                            artifact.evidence,
                            (
                                f"/post_types/"
                                f"{_json_pointer_token(str(post_type))}/search_fields"
                            ),
                        )
                        capability = CapabilityDisposition(
                            capability_id=(
                                f"capability:geodirectory:{token}:discovery"
                            ),
                            capability_type="directory_search_and_sort",
                            source_construct=", ".join(sorted(interactive)),
                            source_plugin="geodirectory",
                            business_critical=False,
                            disposition=CapabilityDispositionKind.NEEDS_DECISION,
                            target_behavior=None,
                            verification_method=None,
                            required_operator_decision=(
                                "Choose client-side static discovery, a replacement "
                                "service, or approved omission"
                            ),
                            observed_route_ids=observed,
                            lineage=_lineage(
                                CapabilityDisposition,
                                interactive_ref,
                                "geodirectory-discovery-disposition/1",
                                decision="needs_decision",
                            ),
                        )
                        capabilities.append(capability)
                        self._capability_decision(
                            capability, interactive_ref, findings, decisions
                        )
        unique = {item.capability_id: item for item in capabilities}
        if len(unique) != len(capabilities):
            raise ContractCompilationError(
                "capability_collision", "Capability IDs are not unique"
            )
        return list(unique.values())

    def _page_builder_capabilities(
        self,
        raw: RawSourceEvidence,
        routes: list[RouteContract],
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> list[CapabilityDisposition]:
        route_by_source = {route.source_content_id: route for route in routes}
        signals: dict[str, tuple[EvidenceReference, set[str], set[str]]] = {}

        def observe(
            builder: str,
            evidence: EvidenceReference,
            signal: str,
            route_id: str | None = None,
        ) -> None:
            existing = signals.get(builder)
            if existing is None:
                existing = (evidence, set(), set())
                signals[builder] = existing
            existing[1].add(signal)
            if route_id:
                existing[2].add(route_id)

        for artifact in raw.capabilities:
            if artifact.artifact != "plugins/plugins_fingerprint.json":
                continue
            data = artifact.data if isinstance(artifact.data, dict) else {}
            fingerprints = data.get("fingerprints", [])
            for index, plugin in enumerate(
                fingerprints if isinstance(fingerprints, list) else []
            ):
                if not isinstance(plugin, dict) or not plugin.get("active"):
                    continue
                slug = str(plugin.get("plugin_slug") or "")
                builder = self._builder_from_plugin_slug(slug)
                if builder:
                    observe(
                        builder,
                        _field_ref(artifact.evidence, f"/fingerprints/{index}"),
                        "active_plugin",
                    )

        for content in raw.content:
            route = route_by_source.get(str(content.source_id))
            route_id = route.contract_id if route else None
            metadata = deterministic_json(content.postmeta).lower()
            markup = content.original_html.lower()
            if any(
                marker in metadata
                for marker in ("_elementor_data", "_elementor_edit_mode")
            ):
                observe(
                    "elementor",
                    _field_ref(content.evidence, "/postmeta"),
                    "post_meta",
                    route_id,
                )
            if any(
                marker in markup
                for marker in (
                    "data-elementor",
                    "elementor-element",
                    "elementor-widget",
                )
            ):
                observe(
                    "elementor",
                    _field_ref(content.evidence, "/raw_html"),
                    "rendered_markup",
                    route_id,
                )
            if any(
                marker in metadata
                for marker in ("_et_pb_use_builder", "_et_pb_old_content")
            ):
                observe(
                    "divi",
                    _field_ref(content.evidence, "/postmeta"),
                    "post_meta",
                    route_id,
                )
            if "[et_pb_" in markup:
                observe(
                    "divi",
                    _field_ref(content.evidence, "/raw_html"),
                    "shortcode",
                    route_id,
                )
            elif any(marker in markup for marker in ("et_pb_section", "et_pb_module")):
                observe(
                    "divi",
                    _field_ref(content.evidence, "/raw_html"),
                    "rendered_markup",
                    route_id,
                )

        capabilities: list[CapabilityDisposition] = []
        for builder, (evidence, signal_names, route_ids) in sorted(signals.items()):
            capability = CapabilityDisposition(
                capability_id=f"capability:page-builder:{builder}",
                capability_type="unsupported_page_builder",
                source_construct=(
                    f"{builder.title()} evidence: {', '.join(sorted(signal_names))}"
                ),
                source_plugin=builder,
                business_critical=True,
                disposition=CapabilityDispositionKind.NEEDS_DECISION,
                target_behavior=None,
                verification_method=None,
                required_operator_decision=(
                    f"A dedicated accepted {builder.title()} adapter is required"
                ),
                observed_route_ids=tuple(sorted(route_ids)),
                lineage=_lineage(
                    CapabilityDisposition,
                    evidence,
                    "unsupported-page-builder/1",
                    decision="dedicated_adapter_required",
                ),
            )
            decision = self._decision(
                "unsupported-page-builder",
                capability.capability_id,
                (
                    f"Provide a dedicated accepted {builder.title()} adapter or migrate "
                    "from a supported content-led source."
                ),
                ("provide-dedicated-adapter", "use-supported-source"),
                evidence,
            )
            self._append_unique(decisions, decision)
            self._append_unique(
                findings,
                self._finding(
                    "unsupported_page_builder",
                    "error",
                    capability.capability_id,
                    (
                        f"{builder.title()} evidence blocks complete migration until a "
                        "dedicated adapter and fixtures are accepted."
                    ),
                    evidence,
                    decision.decision_id,
                ),
            )
            capabilities.append(capability)
        return capabilities

    @staticmethod
    def _builder_from_plugin_slug(slug: str) -> str | None:
        normalized = slug.strip().lower()
        if normalized in {"elementor", "elementor-pro"} or normalized.startswith(
            "elementor/"
        ):
            return "elementor"
        if normalized in {"divi", "divi-builder"} or normalized.startswith(
            ("divi/", "divi-builder/")
        ):
            return "divi"
        return None

    def _capability_decision(
        self,
        capability: CapabilityDisposition,
        evidence: EvidenceReference,
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> None:
        if capability.disposition != CapabilityDispositionKind.NEEDS_DECISION:
            return
        decision = self._decision(
            "capability-disposition",
            capability.capability_id,
            capability.required_operator_decision
            or "Choose target capability behavior.",
            ("reproduce", "replace", "externalize", "omit-with-approval"),
            evidence,
        )
        self._append_unique(decisions, decision)
        self._append_unique(
            findings,
            self._finding(
                "capability_needs_decision",
                "warning",
                capability.capability_id,
                "Capability has no evidence-grounded automatic disposition.",
                evidence,
                decision.decision_id,
            ),
        )
