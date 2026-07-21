from __future__ import annotations

import hashlib
import urllib.error

import pytest

from moltex_harness.network import PublicNetworkPolicy
from moltex_harness.scaffold import AssetMaterializer, FetchResult, PublicHttpFetcher


PNG = b"\x89PNG\r\n\x1a\nvalid-test-payload"


class FakeFetcher:
    def __init__(self, data: bytes, content_type: str | None = None) -> None:
        self.data = data
        self.content_type = content_type

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(self.data, url + "?resolved=1", 2, self.content_type)


def test_deferred_media_is_written_to_contract_path(golden_contracts, tmp_path) -> None:
    data = PNG
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
            "bytes": len(PNG),
            "acquisition_status": "deferred",
            "acquisition_method": "source-fetch",
        }
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        AssetMaterializer(FakeFetcher(PNG)).materialize(
            (asset,), tmp_path / "bundle", tmp_path / "site"
        )


@pytest.mark.parametrize(
    ("payload", "content_type", "message"),
    [
        (b"<!doctype html><title>not an image</title>", "text/html", "HTML response"),
        (b"plain text", "image/png", "signature mismatch"),
    ],
)
def test_media_payload_must_match_declared_type(
    golden_contracts, tmp_path, payload, content_type, message
) -> None:
    source = golden_contracts.assets[0]
    asset = source.model_copy(
        update={
            "bundle_path": None,
            "checksum": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "acquisition_status": "deferred",
            "acquisition_method": "source-fetch",
        }
    )

    with pytest.raises(ValueError, match=message):
        AssetMaterializer(FakeFetcher(payload, content_type)).materialize(
            (asset,), tmp_path / "bundle", tmp_path / "site"
        )


def test_active_svg_is_rejected(golden_contracts, tmp_path) -> None:
    payload = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    source = golden_contracts.assets[0]
    asset = source.model_copy(
        update={
            "bundle_path": None,
            "checksum": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "mime_type": "image/svg+xml",
            "acquisition_status": "deferred",
            "acquisition_method": "source-fetch",
        }
    )

    with pytest.raises(ValueError, match="Active SVG"):
        AssetMaterializer(FakeFetcher(payload, "image/svg+xml")).materialize(
            (asset,), tmp_path / "bundle", tmp_path / "site"
        )


class ErrorOpener:
    def __init__(self, status: int) -> None:
        self.status = status
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        raise urllib.error.HTTPError(
            request.full_url, self.status, "failure", {}, None
        )


def test_permanent_http_error_is_not_retried(monkeypatch) -> None:
    opener = ErrorOpener(404)
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: opener)
    policy = PublicNetworkPolicy(lambda host, port: ("93.184.216.34",))

    with pytest.raises(ValueError, match="Permanent media HTTP failure 404"):
        PublicHttpFetcher(policy).fetch("https://example.test/missing.png")

    assert opener.calls == 1


def test_transient_http_error_is_retried_once(monkeypatch) -> None:
    opener = ErrorOpener(503)
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: opener)
    policy = PublicNetworkPolicy(lambda host, port: ("93.184.216.34",))

    with pytest.raises(ConnectionError, match="after two attempts"):
        PublicHttpFetcher(policy).fetch("https://example.test/busy.png")

    assert opener.calls == 2
