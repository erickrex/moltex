from __future__ import annotations

import hashlib
import pytest

from moltex_harness.scaffold import AssetMaterializer, FetchResult


class FakeFetcher:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(self.data, url + "?resolved=1", 2)


def test_deferred_media_is_written_to_contract_path(golden_contracts, tmp_path) -> None:
    data = b"future-media"
    source = golden_contracts.assets[0]
    asset = source.model_copy(
        update={
            "bundle_path": None,
            "checksum": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "acquisition_status": "deferred",
            "acquisition_method": "source-fetch",
        }
    )

    receipt = AssetMaterializer(FakeFetcher(data)).materialize(
        (asset,), tmp_path / "bundle", tmp_path / "site"
    )[0]

    assert (tmp_path / "site" / asset.target_path).read_bytes() == data
    assert receipt.acquisition_method == "source-fetch"
    assert receipt.final_source_url.endswith("?resolved=1")
    assert receipt.attempts == 2


def test_referenced_missing_media_blocks_baseline(golden_contracts, tmp_path) -> None:
    source = golden_contracts.assets[0]
    asset = source.model_copy(
        update={
            "bundle_path": None,
            "checksum": None,
            "bytes": None,
            "acquisition_status": "missing",
            "acquisition_method": "operator-decision",
            "needs_decision": True,
        }
    )

    with pytest.raises(ValueError, match="Required asset"):
        AssetMaterializer().materialize((asset,), tmp_path / "bundle", tmp_path / "site")


def test_media_checksum_mismatch_is_rejected(golden_contracts, tmp_path) -> None:
    source = golden_contracts.assets[0]
    asset = source.model_copy(
        update={
            "bundle_path": None,
            "checksum": "0" * 64,
            "bytes": len(b"unexpected"),
            "acquisition_status": "deferred",
            "acquisition_method": "source-fetch",
        }
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        AssetMaterializer(FakeFetcher(b"unexpected")).materialize(
            (asset,), tmp_path / "bundle", tmp_path / "site"
        )
