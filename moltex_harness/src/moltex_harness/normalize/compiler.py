"""Deterministic H2 compiler from raw source evidence to migration contracts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any, Iterable, Literal, TypeVar
from urllib.parse import urljoin, urlsplit

from moltex_harness.intake.serialization import deterministic_json
from moltex_harness.intake.security import redact_text
from moltex_harness.models import (
    AssetContract,
    CapabilityDisposition,
    CapabilityDispositionKind,
    ContentRecord,
    ContractSet,
    CustomField,
    DecisionItem,
    DerivedLineage,
    EvidenceReference,
    MediaMapEntry,
    NavigationItem,
    NormalizationFinding,
    ParityRow,
    RawArtifactEvidence,
    RawContentEvidence,
    RawMediaEvidence,
    RawSourceEvidence,
    RedirectContract,
    RouteContract,
    SeoContract,
    SiteSpec,
    SourceManifest,
    StaticEligibility,
    UrlMapEntry,
    ViewportProfile,
    VisualCapturePlan,
    VisualCaptureTarget,
)
from moltex_harness.models.contracts import LineagedModel

from .primitives import (
    NormalizationValueError,
    absolute_url,
    normalize_gmt_datetime,
    normalize_internal_url,
    normalize_origin,
    normalize_route_path,
    normalize_slug,
    output_path,
    stable_hash,
    stable_token,
)


class ContractCompilationError(ValueError):
    """A permanent semantic contradiction in accepted raw evidence."""

    exit_code = 6

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _MediaSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in {"img", "source", "video", "audio"}:
            return
        for name, value in attrs:
            if name.lower() == "src" and value:
                self.sources.add(value)


TLineaged = TypeVar("TLineaged", bound=LineagedModel)


def _field_ref(base: EvidenceReference, pointer: str) -> EvidenceReference:
    root = base.pointer.rstrip("/")
    suffix = pointer if pointer.startswith("/") else f"/{pointer}"
    combined = f"{root}{suffix}" if root else suffix
    identity = stable_hash(base.bundle_id, base.artifact, combined, length=40)
    return EvidenceReference(
        evidence_id=f"ev:{identity}",
        bundle_id=base.bundle_id,
        artifact=base.artifact,
        pointer=combined,
        sha256=base.sha256,
    )


def _lineage(
    model: type[TLineaged],
    inputs: EvidenceReference | Iterable[EvidenceReference],
    rule: str,
    *,
    decision: str | None = None,
    overrides: dict[str, tuple[Iterable[EvidenceReference], str, str | None]]
    | None = None,
) -> dict[str, DerivedLineage]:
    refs = (inputs,) if isinstance(inputs, EvidenceReference) else tuple(inputs)
    fields = set(model.model_fields) - {"schema_version", "lineage"}
    result = {
        field: DerivedLineage(derived_by=rule, inputs=refs, decision=decision)
        for field in fields
    }
    for field, (field_inputs, field_rule, field_decision) in (overrides or {}).items():
        result[field] = DerivedLineage(
            derived_by=field_rule,
            inputs=tuple(field_inputs),
            decision=field_decision,
        )
    return result


def _json_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


class ContractCompiler:
    """Compile H1 evidence without generating target files or Astro code."""

    compiler_version = "h2-contracts/1"
    max_visual_routes = 12

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
        site_values = (
            site_data.get("site") if isinstance(site_data.get("site"), dict) else {}
        )
        core = (
            settings_data.get("core")
            if isinstance(settings_data.get("core"), dict)
            else {}
        )
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
        reading = (
            settings_data.get("reading")
            if isinstance(settings_data.get("reading"), dict)
            else {}
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
        visual_plan = self._visual_plan(raw, routes, capabilities, origin)

        return ContractSet(
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
            url_map=tuple(
                sorted(url_map, key=lambda item: (item.source_url, item.target_url))
            ),
            media_map=tuple(sorted(media_map, key=lambda item: item.source_url)),
            visual_capture_plan=visual_plan,
            parity_matrix=tuple(sorted(parity, key=lambda item: item.row_id)),
            findings=tuple(sorted(findings, key=lambda item: item.finding_id)),
            decisions=tuple(sorted(decisions, key=lambda item: item.decision_id)),
        )

    @staticmethod
    def _artifact(raw: RawSourceEvidence, path: str) -> RawArtifactEvidence:
        for artifact in (
            *raw.site,
            *raw.navigation,
            *raw.seo,
            *raw.redirects,
            *raw.capabilities,
        ):
            if artifact.artifact == path:
                return artifact
        raise ContractCompilationError(
            "missing_raw_artifact", f"Raw evidence is missing {path}"
        )

    @staticmethod
    def _nested_id(value: Any) -> str | None:
        if isinstance(value, dict) and value.get("id") is not None:
            return str(value["id"])
        if isinstance(value, (int, str)) and str(value) not in {"", "0"}:
            return str(value)
        return None

    @staticmethod
    def _trailing_policy(
        site: dict[str, Any], content: list[RawContentEvidence]
    ) -> Literal["always", "never"]:
        permalink = str(site.get("permalink_structure", ""))
        if permalink:
            return "always" if permalink.endswith("/") else "never"
        non_root = [
            item.legacy_permalink for item in content if item.legacy_permalink != "/"
        ]
        return (
            "always"
            if not non_root
            or sum(url.endswith("/") for url in non_root) * 2 >= len(non_root)
            else "never"
        )

    def _routes(
        self,
        raw: RawSourceEvidence,
        origin: str,
        trailing: str,
        front_id: str | None,
        posts_id: str | None,
    ) -> list[RouteContract]:
        routes: list[RouteContract] = []
        targets: dict[str, str] = {}
        for item in raw.content:
            if item.status != "publish":
                continue
            source_id = str(item.source_id)
            record_id = (
                f"content:{stable_token(item.content_type)}:{stable_token(source_id)}"
            )
            route_id = (
                f"route:{stable_token(item.content_type)}:{stable_token(source_id)}"
            )
            target = normalize_route_path(item.legacy_permalink, origin, trailing)
            legacy_parts = urlsplit(item.legacy_permalink)
            if target == "/" and legacy_parts.query and source_id != front_id:
                target = normalize_route_path(
                    f"/{normalize_slug(item.slug)}/", origin, trailing
                )
            if source_id == front_id:
                target = "/"
            if target in targets:
                raise ContractCompilationError(
                    "route_collision",
                    f"{route_id} and {targets[target]} normalize to {target}",
                )
            targets[target] = route_id
            family = (
                "home"
                if target == "/"
                else "listing"
                if source_id == posts_id
                else item.content_type
            )
            marker = item.title.strip() or record_id
            ref = item.evidence
            routes.append(
                RouteContract(
                    contract_id=route_id,
                    source_content_id=source_id,
                    content_record_id=record_id,
                    legacy_url=item.legacy_permalink,
                    target_url=target,
                    page_family=family,
                    output_path=output_path(target),
                    expected_status=200,
                    required_content_markers=(marker,),
                    redirect_required=normalize_route_path(
                        item.legacy_permalink, origin, trailing
                    )
                    != target,
                    seo_contract_id=f"seo:{stable_token(item.content_type)}:{stable_token(source_id)}",
                    public=True,
                    lineage=_lineage(
                        RouteContract,
                        ref,
                        "route-preserve-public-source/1",
                        overrides={
                            "target_url": (
                                (ref,),
                                "route-normalization/1",
                                "preserve_legacy_path",
                            ),
                            "page_family": ((ref,), "route-family/1", family),
                        },
                    ),
                )
            )
        if not any(route.target_url == "/" for route in routes):
            settings = self._artifact(raw, "site_settings.json")
            settings_data = settings.data if isinstance(settings.data, dict) else {}
            core = (
                settings_data.get("core")
                if isinstance(settings_data.get("core"), dict)
                else {}
            )
            marker = str(core.get("site_title") or core.get("name") or "Home")
            routes.append(
                RouteContract(
                    contract_id="route:site:home",
                    source_content_id="site:home",
                    content_record_id=None,
                    legacy_url="/",
                    target_url="/",
                    page_family="home",
                    output_path="index.html",
                    expected_status=200,
                    required_content_markers=(marker,),
                    redirect_required=False,
                    seo_contract_id="seo:site:home",
                    public=True,
                    lineage=_lineage(
                        RouteContract,
                        settings.evidence,
                        "posts-index-home-route/1",
                        decision="wordpress_show_on_front_posts",
                    ),
                )
            )
        return routes

    def _assets(
        self,
        raw: RawSourceEvidence,
        origin: str,
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> tuple[list[AssetContract], list[MediaMapEntry], dict[str, tuple[str, ...]]]:
        observations: dict[str, dict[str, Any]] = {}
        by_source_id: dict[str, str] = {}
        by_url: dict[str, str] = {}
        for item in raw.media:
            asset_id = f"asset:{stable_token(item.source_id if item.source_id is not None else stable_hash(item.source_url))}"
            observations[asset_id] = {
                "raw": item,
                "source_url": item.source_url,
                "refs": set(),
                "evidence": item.evidence,
            }
            by_url[item.source_url] = asset_id
            if item.source_id is not None:
                by_source_id[str(item.source_id)] = asset_id

        content_assets: dict[str, set[str]] = defaultdict(set)
        for content in raw.content:
            content_id = str(content.source_id)
            references: set[str] = set()
            featured = (
                content.featured_media
                if isinstance(content.featured_media, dict)
                else {}
            )
            featured_id = (
                str(featured.get("id")) if featured.get("id") is not None else None
            )
            featured_url = str(featured.get("url")) if featured.get("url") else None
            if featured_id and featured_id in by_source_id:
                references.add(by_source_id[featured_id])
            elif featured_url and featured_url in by_url:
                references.add(by_url[featured_url])
            elif featured_url:
                references.add(
                    self._add_missing_media(
                        observations, featured_url, content.evidence
                    )
                )

            geodirectory = (
                content.geodirectory if isinstance(content.geodirectory, dict) else {}
            )
            geodirectory_media = geodirectory.get("media", [])
            if isinstance(geodirectory_media, list):
                for index, media in enumerate(geodirectory_media):
                    if not isinstance(media, dict) or not media.get("url"):
                        continue
                    source_url = str(media["url"])
                    absolute = (
                        absolute_url(origin, source_url)
                        if source_url.startswith("/")
                        else source_url
                    )
                    if absolute in by_url:
                        references.add(by_url[absolute])
                    elif source_url in by_url:
                        references.add(by_url[source_url])
                    else:
                        references.add(
                            self._add_missing_media(
                                observations,
                                absolute,
                                _field_ref(
                                    content.evidence,
                                    f"/geodirectory/media/{index}/url",
                                ),
                            )
                        )

            parser = _MediaSourceParser()
            parser.feed(content.original_html)
            for source in sorted(parser.sources):
                absolute = (
                    absolute_url(origin, source) if source.startswith("/") else source
                )
                if absolute in by_url:
                    references.add(by_url[absolute])
                elif source in by_url:
                    references.add(by_url[source])
                elif "/wp-content/uploads/" in absolute:
                    references.add(
                        self._add_missing_media(
                            observations, absolute, content.evidence
                        )
                    )
            for asset_id in references:
                observations[asset_id]["refs"].add(content_id)
                content_assets[content_id].add(asset_id)

        assets: list[AssetContract] = []
        media_map: list[MediaMapEntry] = []
        target_paths: dict[str, str] = {}
        for asset_id, observation in sorted(observations.items()):
            item: RawMediaEvidence | None = observation["raw"]
            source_url = observation["source_url"]
            evidence: EvidenceReference = observation["evidence"]
            bundle_path = item.artifact if item else None
            target_path = self._media_target_path(asset_id, source_url, item)
            target_url = "/" + target_path.removeprefix("public/")
            existing = target_paths.get(target_path)
            if existing and existing != asset_id:
                raise ContractCompilationError(
                    "asset_collision",
                    "Different assets normalize to the same target path",
                )
            target_paths[target_path] = asset_id

            declared = item.acquisition if item else None
            if bundle_path:
                acquisition_status: Literal["bundled", "deferred", "missing"] = (
                    "bundled"
                )
                acquisition_method: Literal[
                    "bundle", "source-fetch", "operator-decision"
                ] = "bundle"
            elif declared and declared.status == "deferred":
                acquisition_status = "deferred"
                acquisition_method = "source-fetch"
            else:
                acquisition_status = "missing"
                acquisition_method = "operator-decision"
            needs_decision = acquisition_status == "missing"
            if needs_decision:
                decision = self._decision(
                    "missing-media",
                    asset_id,
                    "Choose how to replace or externalize a media reference absent from the bundle.",
                    ("replace", "externalize", "omit-with-approval"),
                    evidence,
                )
                self._append_unique(decisions, decision)
                self._append_unique(
                    findings,
                    self._finding(
                        "missing_media_reference",
                        "warning",
                        asset_id,
                        "A referenced media URL has no local bundle artifact.",
                        evidence,
                        decision.decision_id,
                    ),
                )
            assets.append(
                AssetContract(
                    asset_id=asset_id,
                    source_url=source_url,
                    bundle_path=bundle_path,
                    target_path=target_path,
                    checksum=item.sha256 if item else None,
                    bytes=item.bytes if item else None,
                    mime_type=item.mime_type if item else None,
                    alt_text=item.alt_text if item else None,
                    referencing_content_ids=tuple(sorted(observation["refs"])),
                    transform=(
                        {"operation": "acquire-source", "stage": "h3"}
                        if acquisition_status == "deferred"
                        else None
                    ),
                    provenance=(
                        "source-bundle"
                        if acquisition_status == "bundled"
                        else "deferred-public-source"
                        if acquisition_status == "deferred"
                        else "missing-source-reference"
                    ),
                    acquisition_status=acquisition_status,
                    acquisition_method=acquisition_method,
                    runtime_policy="local-only",
                    needs_decision=needs_decision,
                    lineage=_lineage(AssetContract, evidence, "asset-map/1"),
                )
            )
            media_map.append(
                MediaMapEntry(
                    source_url=source_url,
                    target_path=target_path,
                    target_url=target_url,
                    asset_contract_id=asset_id,
                    acquisition_status=acquisition_status,
                    runtime_policy="local-only",
                    lineage=_lineage(MediaMapEntry, evidence, "media-url-map/1"),
                )
            )
        return (
            assets,
            media_map,
            {key: tuple(sorted(value)) for key, value in content_assets.items()},
        )

    @staticmethod
    def _media_target_path(
        asset_id: str,
        source_url: str,
        item: RawMediaEvidence | None,
    ) -> str:
        """Assign a stable collision-resistant local destination for every source URL."""
        source_path = PurePosixPath(urlsplit(source_url).path)
        suffix = source_path.suffix.lower()
        if suffix not in {
            ".avif",
            ".gif",
            ".jpeg",
            ".jpg",
            ".m4a",
            ".mp3",
            ".mp4",
            ".ogg",
            ".pdf",
            ".png",
            ".svg",
            ".wav",
            ".webm",
            ".webp",
        }:
            suffix = ""
        if not suffix and item and item.mime_type:
            suffix = {
                "image/avif": ".avif",
                "image/gif": ".gif",
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/svg+xml": ".svg",
                "image/webp": ".webp",
                "video/mp4": ".mp4",
            }.get(item.mime_type.lower(), "")
        suffix = suffix or ".bin"
        stem = stable_token(source_path.stem or "media")[:80]
        identity = stable_token(asset_id)[:80]
        filename = f"{identity}-{stem}-{stable_hash(source_url, length=12)}{suffix}"
        return f"public/media/{filename}"

    @staticmethod
    def _add_missing_media(
        observations: dict[str, dict[str, Any]],
        source_url: str,
        evidence: EvidenceReference,
    ) -> str:
        asset_id = f"asset:missing:{stable_hash(source_url)}"
        observations.setdefault(
            asset_id,
            {
                "raw": None,
                "source_url": source_url,
                "refs": set(),
                "evidence": evidence,
            },
        )
        return asset_id

    def _content_records(
        self,
        raw: RawSourceEvidence,
        origin: str,
        trailing: str,
        route_by_path: dict[str, RouteContract],
        route_by_legacy: dict[str, RouteContract],
        media_ids_by_content: dict[str, tuple[str, ...]],
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> list[ContentRecord]:
        records: list[ContentRecord] = []
        for item in raw.content:
            source_id = str(item.source_id)
            record_id = (
                f"content:{stable_token(item.content_type)}:{stable_token(source_id)}"
            )
            internal_routes: set[str] = set()
            unresolved: set[str] = set()
            for index, link in enumerate(item.internal_links):
                value = str(link)
                route = route_by_legacy.get(value) or route_by_legacy.get(
                    urljoin(origin.rstrip("/") + "/", value)
                )
                normalized = normalize_internal_url(value, origin, trailing)
                if route is None:
                    route = route_by_path.get(normalized) if normalized else None
                if route:
                    internal_routes.add(route.contract_id)
                else:
                    unresolved.add(redact_text(normalized or value))
                    ref = _field_ref(item.evidence, f"/internal_links/{index}")
                    decision = self._decision(
                        "missing-internal-route",
                        f"{record_id}:{stable_hash(value)}",
                        "Resolve, replace, or explicitly approve omission of the missing internal route.",
                        ("resolve", "replace", "omit-with-approval"),
                        ref,
                    )
                    self._append_unique(decisions, decision)
                    self._append_unique(
                        findings,
                        self._finding(
                            "missing_internal_reference",
                            "warning",
                            record_id,
                            "An internal link does not resolve to a public route contract.",
                            ref,
                            decision.decision_id,
                        ),
                    )
            author_ids = self._author_ids(item.author)
            taxonomy_ids = self._taxonomy_ids(item.taxonomies)
            custom_fields = self._custom_fields(item)
            media_ids = media_ids_by_content.get(source_id, ())
            relationships = {
                "internal_routes": tuple(sorted(internal_routes)),
                "media": tuple(media_ids),
            }
            records.append(
                ContentRecord(
                    record_id=record_id,
                    source_id=source_id,
                    content_type=stable_token(item.content_type),
                    legacy_url=item.legacy_permalink,
                    slug=normalize_slug(item.slug),
                    status=item.status,
                    title=item.title.strip(),
                    published_at=normalize_gmt_datetime(item.date_gmt),
                    modified_at=normalize_gmt_datetime(item.modified_gmt),
                    author_ids=author_ids,
                    taxonomy_ids=taxonomy_ids,
                    relationships=relationships,
                    original_html=item.original_html,
                    normalized_body={
                        "format": "html",
                        "content": item.original_html,
                        "conversion_status": "pending_h3",
                    },
                    custom_fields=custom_fields,
                    required_media_ids=tuple(media_ids),
                    internal_route_ids=tuple(sorted(internal_routes)),
                    unresolved_internal_links=tuple(sorted(unresolved)),
                    lineage=_lineage(
                        ContentRecord,
                        item.evidence,
                        "content-normalization/1",
                        overrides={
                            "title": (
                                (_field_ref(item.evidence, "/title"),),
                                "content-title/1",
                                None,
                            ),
                            "normalized_body": (
                                (_field_ref(item.evidence, "/raw_html"),),
                                "body-preserve-html/1",
                                "conversion_deferred_h3",
                            ),
                            "internal_route_ids": (
                                (_field_ref(item.evidence, "/internal_links"),),
                                "internal-link-resolution/1",
                                None,
                            ),
                        },
                    ),
                )
            )
        return records

    @staticmethod
    def _author_ids(value: dict[str, Any] | list[Any]) -> tuple[str, ...]:
        values = value if isinstance(value, list) else [value]
        result: set[str] = set()
        for author in values:
            if not isinstance(author, dict):
                continue
            identity = (
                author.get("id")
                or author.get("ID")
                or author.get("slug")
                or author.get("user_login")
            )
            if identity is None:
                identity = f"name-{stable_hash(author.get('display_name', 'unknown'), length=12)}"
            result.add(f"author:{stable_token(identity)}")
        return tuple(sorted(result))

    @staticmethod
    def _taxonomy_ids(value: dict[str, Any] | list[Any]) -> tuple[str, ...]:
        entries: list[tuple[str, Any]] = []
        if isinstance(value, dict):
            for taxonomy, terms in value.items():
                for term in terms if isinstance(terms, list) else [terms]:
                    entries.append((str(taxonomy), term))
        else:
            entries.extend(("term", term) for term in value)
        result: set[str] = set()
        for taxonomy, term in entries:
            if isinstance(term, dict):
                identity = (
                    term.get("term_id")
                    or term.get("id")
                    or term.get("slug")
                    or term.get("name")
                )
                taxonomy = str(term.get("taxonomy") or taxonomy)
            else:
                identity = term
            if identity is not None:
                result.add(f"term:{stable_token(taxonomy)}:{stable_token(identity)}")
        return tuple(sorted(result))

    def _custom_fields(self, item: RawContentEvidence) -> tuple[CustomField, ...]:
        if isinstance(item.postmeta, dict):
            entries = sorted(item.postmeta.items())
        else:
            entries = [(str(index), value) for index, value in enumerate(item.postmeta)]
        output: list[CustomField] = []
        for key, value in entries:
            owner = (
                "yoast"
                if key.startswith("_yoast_")
                else "wordpress"
                if key.startswith("_")
                else "unknown"
            )
            disposition = (
                "seo"
                if owner == "yoast"
                else "source_metadata"
                if owner == "wordpress"
                else "needs_decision"
            )
            ref = _field_ref(item.evidence, f"/postmeta/{_json_pointer_token(key)}")
            output.append(
                CustomField(
                    field_id=f"field:{stable_token(item.content_type)}:{stable_token(item.source_id)}:{stable_hash(key, length=12)}",
                    key=key,
                    value=value,
                    source_owner=owner,
                    disposition=disposition,
                    lineage=_lineage(
                        CustomField,
                        ref,
                        "custom-field-ownership/1",
                        decision=disposition,
                    ),
                )
            )

        geodirectory = item.geodirectory if isinstance(item.geodirectory, dict) else {}
        geodirectory_values: list[tuple[str, Any, str]] = []
        for section in (
            "address",
            "geo",
            "custom_fields",
            "legacy_public_postmeta",
            "review_summary",
        ):
            value = geodirectory.get(section)
            if isinstance(value, dict):
                geodirectory_values.extend(
                    self._flatten_geodirectory_values(
                        value,
                        f"geodirectory.{section}",
                        f"/{section}",
                    )
                )
        reviews = geodirectory.get("reviews")
        if isinstance(reviews, list):
            geodirectory_values.append(("geodirectory.reviews", reviews, "/reviews"))

        for key, value, pointer in sorted(geodirectory_values):
            ref = _field_ref(item.evidence, f"/geodirectory{pointer}")
            output.append(
                CustomField(
                    field_id=(
                        f"field:{stable_token(item.content_type)}:"
                        f"{stable_token(item.source_id)}:{stable_hash(key, length=12)}"
                    ),
                    key=key,
                    value=value,
                    source_owner="geodirectory",
                    disposition="source_metadata",
                    lineage=_lineage(
                        CustomField,
                        ref,
                        "geodirectory-field-ownership/1",
                        decision="source_metadata",
                    ),
                )
            )
        return tuple(output)

    @staticmethod
    def _flatten_geodirectory_values(
        value: dict[str, Any], prefix: str, pointer: str
    ) -> list[tuple[str, Any, str]]:
        output: list[tuple[str, Any, str]] = []
        for key, field_value in sorted(value.items()):
            field_key = f"{prefix}.{key}"
            field_pointer = f"{pointer}/{_json_pointer_token(str(key))}"
            if isinstance(field_value, dict):
                output.extend(
                    ContractCompiler._flatten_geodirectory_values(
                        field_value, field_key, field_pointer
                    )
                )
            else:
                output.append((field_key, field_value, field_pointer))
        return output

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
            refs = (
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

    def _capabilities(
        self,
        raw: RawSourceEvidence,
        routes: list[RouteContract],
        findings: list[NormalizationFinding],
        decisions: list[DecisionItem],
    ) -> list[CapabilityDisposition]:
        capabilities: list[CapabilityDisposition] = []
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
                summary = (
                    data.get("data") if isinstance(data.get("data"), dict) else data
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
                    if slug in {"moltex-exporter", "wordpress-seo"}:
                        continue
                    features = (
                        plugin.get("features")
                        if isinstance(plugin.get("features"), dict)
                        else {}
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

    def _navigation(
        self,
        raw: RawSourceEvidence,
        route_by_source: dict[str, RouteContract],
        route_by_path: dict[str, RouteContract],
        origin: str,
        trailing: str,
        findings: list[NormalizationFinding],
    ) -> list[NavigationItem]:
        result: list[NavigationItem] = []
        for artifact in raw.navigation:
            data = artifact.data if isinstance(artifact.data, dict) else {}
            menus = data.get("menus", [])
            for menu_index, menu in enumerate(menus if isinstance(menus, list) else []):
                if not isinstance(menu, dict):
                    continue
                menu_id = f"menu:{stable_token(menu.get('term_id') or menu.get('slug') or menu_index)}"
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
        trailing: str,
        content: list[ContentRecord],
        routes: list[RouteContract],
        navigation: list[NavigationItem],
        capabilities: list[CapabilityDisposition],
        decisions: list[DecisionItem],
    ) -> SiteSpec:
        site_data = blueprint.data if isinstance(blueprint.data, dict) else {}
        source_site = (
            site_data.get("site") if isinstance(site_data.get("site"), dict) else {}
        )
        settings_data = settings.data if isinstance(settings.data, dict) else {}
        core = (
            settings_data.get("core")
            if isinstance(settings_data.get("core"), dict)
            else {}
        )
        site_name = str(
            source_site.get("site_title")
            or core.get("site_title")
            or core.get("name")
            or "Untitled site"
        )
        locale = str(
            source_site.get("language")
            or settings_data.get("language", {}).get("locale")
            or "und"
        )
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
        theme = (
            site_data.get("theme") if isinstance(site_data.get("theme"), dict) else {}
        )
        layout = ["responsive-desktop-mobile", "preserve-global-navigation"]
        if theme.get("name"):
            layout.append(f"source-theme-evidence:{theme['name']}")
        readiness = raw.source_manifest.readiness
        eligible = readiness.get("eligible")
        blockers = readiness.get("blockers", [])
        if eligible is False or blockers:
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
        for family in sorted({route.page_family for route in routes}):
            representative = sorted(
                (route for route in routes if route.page_family == family),
                key=lambda route: (route.target_url, route.contract_id),
            )[0]
            chosen.setdefault(
                representative.contract_id, (representative, f"representative:{family}")
            )
        route_lookup = {route.contract_id: route for route in routes}
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
        if len(selected) > self.max_visual_routes:
            raise ContractCompilationError(
                "visual_plan_limit",
                "Required representative visual routes exceed the bounded plan limit",
            )
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
            max_routes=self.max_visual_routes,
            selected_route_ids=tuple(
                sorted(route.contract_id for route, _ in selected)
            ),
            targets=tuple(targets),
            lineage=_lineage(VisualCapturePlan, plan_evidence, "visual-capture-plan/1"),
        )

    @staticmethod
    def _finding(
        code: str,
        severity: Literal["info", "warning", "error"],
        subject: str,
        message: str,
        evidence: EvidenceReference,
        decision_id: str | None = None,
    ) -> NormalizationFinding:
        return NormalizationFinding(
            finding_id=f"finding:{stable_hash(code, subject, evidence.evidence_id)}",
            severity=severity,
            code=code,
            message=message,
            subject_id=subject,
            evidence=(evidence,),
            decision_id=decision_id,
        )

    @staticmethod
    def _decision(
        kind: str,
        subject: str,
        prompt: str,
        options: tuple[str, ...],
        evidence: EvidenceReference,
    ) -> DecisionItem:
        return DecisionItem(
            decision_id=f"decision:{stable_hash(kind, subject)}",
            kind=kind,
            severity="blocking",
            subject_id=subject,
            prompt=prompt,
            options=options,
            evidence=(evidence,),
        )

    @staticmethod
    def _append_unique(values: list[Any], value: Any) -> None:
        identifier = getattr(value, "decision_id", None) or getattr(
            value, "finding_id", None
        )
        if not any(
            (getattr(item, "decision_id", None) or getattr(item, "finding_id", None))
            == identifier
            for item in values
        ):
            values.append(value)
