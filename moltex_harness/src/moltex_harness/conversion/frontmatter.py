"""Typed, deterministic frontmatter normalization from H2 records."""

from __future__ import annotations

import math
from typing import Any

from moltex_harness.models import ContentRecord, SeoContract


class FrontmatterNormalizer:
    def normalize(
        self, record: ContentRecord, seo: SeoContract | None
    ) -> dict[str, Any]:
        return {
            "recordId": record.record_id,
            "sourceId": record.source_id,
            "title": record.title,
            "slug": record.slug,
            "contentType": record.content_type,
            "status": record.status,
            "publishedAt": record.published_at,
            "modifiedAt": record.modified_at,
            "authors": list(record.author_ids),
            "taxonomies": list(record.taxonomy_ids),
            "relationships": {
                key: list(value) for key, value in sorted(record.relationships.items())
            },
            "customFields": {
                field.key: self._json_value(field.value)
                for field in sorted(record.custom_fields, key=lambda item: item.key)
            },
            "seo": seo.model_dump(mode="json", exclude={"lineage"}) if seo else {},
            "source": {"legacyUrl": record.legacy_url, "sourceId": record.source_id},
        }

    def _json_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Custom field contains a non-finite number")
            return value
        if isinstance(value, (list, tuple)):
            return [self._json_value(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._json_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        raise ValueError(f"Unsupported custom-field value: {type(value).__name__}")
