"""Contained local asset acquisition with deterministic receipts."""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from moltex_harness.models import AssetAcquisitionReceipt, AssetContract
from moltex_harness.network import PublicNetworkPolicy, PublicRedirectHandler


MAX_FETCH_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class FetchResult:
    data: bytes
    final_url: str
    attempts: int = 1
    content_type: str | None = None


class MediaFetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


class PublicHttpFetcher:
    def __init__(self, policy: PublicNetworkPolicy | None = None) -> None:
        self.policy = policy or PublicNetworkPolicy()

    def fetch(self, url: str) -> FetchResult:
        self.policy.require_public(url)
        request = urllib.request.Request(url, headers={"User-Agent": "Moltex-Harness/0.1"})
        opener = urllib.request.build_opener(PublicRedirectHandler(self.policy))
        for attempt in range(2):
            try:
                with opener.open(request, timeout=20) as response:
                    final_url = response.geturl()
                    self.policy.require_public(final_url)
                    content_type = response.headers.get_content_type()
                    data = response.read(MAX_FETCH_BYTES + 1)
                break
            except urllib.error.HTTPError as error:
                if error.code not in {408, 429} and error.code < 500:
                    raise ValueError(
                        f"Permanent media HTTP failure {error.code} for {url}"
                    ) from error
                if attempt == 1:
                    raise ConnectionError(
                        f"Transient media fetch failure for {url} after two attempts"
                    ) from error
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == 1:
                    raise ConnectionError(
                        f"Transient media fetch failure for {url} after two attempts"
                    ) from error
        if len(data) > MAX_FETCH_BYTES:
            raise ValueError(f"Media response exceeds {MAX_FETCH_BYTES} bytes: {url}")
        return FetchResult(data, final_url, attempt + 1, content_type)


class AssetMaterializer:
    def __init__(self, fetcher: MediaFetcher | None = None) -> None:
        self.fetcher = fetcher or PublicHttpFetcher()

    def materialize(
        self,
        assets: tuple[AssetContract, ...],
        extracted_bundle: Path,
        workspace: Path,
    ) -> tuple[AssetAcquisitionReceipt, ...]:
        receipts: list[AssetAcquisitionReceipt] = []
        root = workspace.resolve()
        for asset in assets:
            if asset.needs_decision or asset.acquisition_status == "missing":
                if asset.referencing_content_ids:
                    raise ValueError(f"Required asset cannot be acquired: {asset.asset_id}")
                continue
            target = (root / Path(*PurePosixPath(asset.target_path).parts)).resolve()
            if root not in target.parents or target == root:
                raise ValueError(f"Asset target escapes workspace: {asset.target_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            method: Literal["bundle", "source-fetch"]
            if asset.acquisition_status == "bundled":
                if not asset.bundle_path:
                    raise ValueError(f"Bundled asset has no artifact: {asset.asset_id}")
                source = (extracted_bundle / Path(*PurePosixPath(asset.bundle_path).parts)).resolve()
                if extracted_bundle.resolve() not in source.parents or not source.is_file():
                    raise ValueError(f"Bundled asset is missing: {asset.bundle_path}")
                data = source.read_bytes()
                method = "bundle"
                artifact = asset.bundle_path
                final_url = asset.source_url
                attempts = 1
                response_content_type = None
            else:
                result = self.fetcher.fetch(asset.source_url)
                data = result.data
                method = "source-fetch"
                artifact = None
                final_url = result.final_url
                attempts = result.attempts
                response_content_type = result.content_type
            self._validate_payload(asset, data, response_content_type)
            digest = hashlib.sha256(data).hexdigest()
            if asset.checksum and digest != asset.checksum:
                raise ValueError(f"Asset checksum mismatch: {asset.asset_id}")
            if asset.bytes is not None and len(data) != asset.bytes:
                raise ValueError(f"Asset byte count mismatch: {asset.asset_id}")
            target.write_bytes(data)
            receipts.append(
                AssetAcquisitionReceipt(
                    asset_id=asset.asset_id,
                    source_url=asset.source_url,
                    final_source_url=final_url,
                    target_path=asset.target_path,
                    acquisition_method=method,
                    source_artifact=artifact,
                    bytes=len(data),
                    sha256=digest,
                    attempts=attempts,
                )
            )
        return tuple(receipts)

    @staticmethod
    def _validate_payload(
        asset: AssetContract, data: bytes, response_content_type: str | None
    ) -> None:
        if not data:
            raise ValueError(f"Asset payload is empty: {asset.asset_id}")
        expected = AssetMaterializer._normalize_mime(asset.mime_type)
        response = AssetMaterializer._normalize_mime(response_content_type)
        detected = AssetMaterializer._detect_mime(data)
        if response in {"text/html", "application/xhtml+xml"} or detected == "text/html":
            raise ValueError(f"HTML response rejected as media: {asset.asset_id}")
        if response and response != "application/octet-stream" and expected:
            if response != expected:
                raise ValueError(
                    f"Media response MIME mismatch for {asset.asset_id}: {response}"
                )
        if expected and expected != "application/octet-stream":
            if detected != expected:
                raise ValueError(
                    f"Media payload signature mismatch for {asset.asset_id}: {expected}"
                )
        if detected == "image/svg+xml":
            AssetMaterializer._reject_active_svg(asset.asset_id, data)

    @staticmethod
    def _normalize_mime(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.split(";", 1)[0].strip().lower()
        return {"image/jpg": "image/jpeg"}.get(normalized, normalized)

    @staticmethod
    def _detect_mime(data: bytes) -> str | None:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        if data.startswith(b"%PDF-"):
            return "application/pdf"
        if len(data) >= 12 and data[4:8] == b"ftyp":
            return "video/mp4"
        if data.startswith(b"ID3") or data.startswith(b"\xff\xfb"):
            return "audio/mpeg"
        prefix = data[:4096].lstrip().lower()
        if prefix.startswith(b"<svg") or (
            prefix.startswith(b"<?xml") and b"<svg" in prefix
        ):
            return "image/svg+xml"
        if prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
            return "text/html"
        return None

    @staticmethod
    def _reject_active_svg(asset_id: str, data: bytes) -> None:
        svg = data.decode("utf-8", errors="ignore")
        active_patterns = (
            r"<\s*script\b",
            r"\bon[a-z]+\s*=",
            r"(?:href|src)\s*=\s*['\"]\s*(?:javascript:|https?:|//)",
            r"<\s*foreignObject\b",
            r"\bdata:\s*text/html",
        )
        if any(re.search(pattern, svg, re.IGNORECASE) for pattern in active_patterns):
            raise ValueError(f"Active SVG payload rejected: {asset_id}")
