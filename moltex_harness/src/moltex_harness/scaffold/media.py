"""Contained local asset acquisition with deterministic receipts."""

from __future__ import annotations

import hashlib
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
                    data = response.read(MAX_FETCH_BYTES + 1)
                break
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == 1:
                    raise ConnectionError(
                        f"Transient media fetch failure for {url} after two attempts"
                    ) from error
        if len(data) > MAX_FETCH_BYTES:
            raise ValueError(f"Media response exceeds {MAX_FETCH_BYTES} bytes: {url}")
        return FetchResult(data, final_url, attempt + 1)


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
            else:
                result = self.fetcher.fetch(asset.source_url)
                data = result.data
                method = "source-fetch"
                artifact = None
                final_url = result.final_url
                attempts = result.attempts
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
