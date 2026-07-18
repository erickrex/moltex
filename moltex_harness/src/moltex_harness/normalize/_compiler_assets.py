"""Contract compiler implementation component."""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import urlsplit


from moltex_harness.models import (
    AssetContract,
    DecisionItem,
    EvidenceReference,
    MediaMapEntry,
    NormalizationFinding,
    RawMediaEvidence,
    RawSourceEvidence,
)

from .primitives import (
    absolute_url,
    stable_hash,
    stable_token,
)

from ._compiler_support import (
    ContractCompilationError,
    _CompilerSupport,
    _field_ref,
    _lineage,
    _MediaSourceParser,
)


class _AssetCompilerMixin(_CompilerSupport):
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
            media_item: RawMediaEvidence | None = observation["raw"]
            source_url = observation["source_url"]
            evidence: EvidenceReference = observation["evidence"]
            bundle_path = media_item.artifact if media_item else None
            target_path = self._media_target_path(asset_id, source_url, media_item)
            target_url = "/" + target_path.removeprefix("public/")
            existing = target_paths.get(target_path)
            if existing and existing != asset_id:
                raise ContractCompilationError(
                    "asset_collision",
                    "Different assets normalize to the same target path",
                )
            target_paths[target_path] = asset_id

            declared = media_item.acquisition if media_item else None
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
                    checksum=media_item.sha256 if media_item else None,
                    bytes=media_item.bytes if media_item else None,
                    mime_type=media_item.mime_type if media_item else None,
                    alt_text=media_item.alt_text if media_item else None,
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
