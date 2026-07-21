"""Contract compiler implementation component."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urljoin, urlsplit


from moltex_harness.intake.security import redact_text
from moltex_harness.models import (
    ContentRecord,
    CustomField,
    DecisionItem,
    NormalizationFinding,
    RawContentEvidence,
    RawSourceEvidence,
    RouteContract,
)

from .primitives import (
    normalize_content_title,
    normalize_gmt_datetime,
    normalize_internal_url,
    normalize_slug,
    stable_hash,
    stable_token,
)

from ._compiler_support import (
    _CompilerSupport,
    _field_ref,
    _json_pointer_token,
    _lineage,
)


class _ContentCompilerMixin(_CompilerSupport):
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
                if normalized and self._is_wordpress_control_path(normalized):
                    continue
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
                    title=normalize_content_title(
                        item.title, item.slug, item.content_type
                    ),
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
    def _is_wordpress_control_path(value: str) -> bool:
        path = urlsplit(value).path.rstrip("/") or "/"
        return (
            path == "/wp-admin"
            or path.startswith("/wp-admin/")
            or path
            in {
                "/wp-login.php",
                "/wp-register.php",
            }
        )

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
            disposition: Literal["seo", "source_metadata", "needs_decision"] = (
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
                    _ContentCompilerMixin._flatten_geodirectory_values(
                        field_value, field_key, field_pointer
                    )
                )
            else:
                output.append((field_key, field_value, field_pointer))
        return output
