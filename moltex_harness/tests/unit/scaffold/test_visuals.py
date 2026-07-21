from __future__ import annotations

import json
import time
from io import BytesIO

import pytest
from PIL import Image

from moltex_harness.contracts import ContractStore
from moltex_harness.network import PublicNetworkPolicy
from moltex_harness.visuals.service import (
    CaptureResult,
    PlaywrightCaptureBackend,
    RouteProbeResult,
    SourceVisualService,
)


class FakeCapture:
    def __init__(self, render) -> None:
        self.render = render

    def capture(self, target):
        return CaptureResult(
            self.render(target.viewport.width, target.viewport.height),
            target.source_url,
            "test-chromium",
            "1.0",
        )


class BatchCapture(FakeCapture):
    def __init__(self, render) -> None:
        super().__init__(render)
        self.batch_calls = 0
        self.capture_calls = 0
        self.browser_launches = 0
        self.max_concurrent_pages = 1

    def capture(self, target):
        self.capture_calls += 1
        return super().capture(target)

    def capture_all(self, targets):
        self.batch_calls += 1
        self.browser_launches += 1
        return tuple(super(BatchCapture, self).capture(target) for target in targets)


class OffOriginCapture(FakeCapture):
    def capture(self, target):
        result = super().capture(target)
        return CaptureResult(
            result.png,
            "https://different.example/redirected/",
            result.browser,
            result.browser_version,
        )


class BlankCapture:
    def capture(self, target):
        image = Image.new(
            "RGB", (target.viewport.width, target.viewport.height), "white"
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return CaptureResult(
            buffer.getvalue(), target.source_url, "test-chromium", "1.0"
        )


class FakeProbe:
    def __init__(self, results=None) -> None:
        self.results = results or {}

    def probe(self, url):
        return self.results.get(url, RouteProbeResult(200, url))


def test_same_origin_path_redirect_is_an_omitted_route_disposition() -> None:
    disposition, reason = SourceVisualService._availability_disposition(
        RouteProbeResult(200, "https://example.test/"),
        "https://example.test/form/2026/",
    )

    assert disposition == "omitted"
    assert reason == "same_origin_redirect"


class SlowProbe:
    def probe(self, url):
        time.sleep(0.05)
        return RouteProbeResult(200, url)


def test_visual_receipt_is_bundle_bound_and_checksum_verified(
    golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    source = tmp_path / "source"
    receipt = SourceVisualService().capture(
        contracts_dir, source, FakeCapture(capture_png)
    )

    assert all(":" not in item.artifact for item in receipt.evidence)

    destination = tmp_path / "protected"
    verified = SourceVisualService().verify_and_copy(contracts_dir, source, destination)

    assert verified.bundle_id == golden_contracts.source_manifest.bundle_id
    assert len(receipt.evidence) == len(golden_contracts.visual_capture_plan.targets)
    assert (destination / "capture-receipt.json").is_file()


def test_visual_capture_batches_all_targets_in_one_browser_session(
    golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    backend = BatchCapture(capture_png)

    receipt = SourceVisualService().capture(
        contracts_dir, tmp_path / "source", backend, FakeProbe()
    )

    assert backend.batch_calls == 1
    assert backend.capture_calls == 0
    assert receipt.resources == {
        "browser_launches": 1,
        "blocked_subresources": 0,
        "max_concurrent_pages": 1,
        "probe_workers": min(8, len(golden_contracts.routes)),
        "capture_targets": len(golden_contracts.visual_capture_plan.targets),
    }
    assert [item.evidence_id for item in receipt.evidence] == [
        target.evidence_id for target in golden_contracts.visual_capture_plan.targets
    ]


def test_browser_blocks_private_subresources_without_failing_public_navigation() -> None:
    public = "93.184.216.34"
    policy = PublicNetworkPolicy(
        lambda host, _port: ("127.0.0.1",) if host == "private.example" else (public,)
    )
    backend = PlaywrightCaptureBackend(policy)
    source_origin = policy.origin("https://source.example/")

    assert backend.request_disposition(
        "http://private.example/asset.png",
        is_navigation=False,
        source_origin=source_origin,
    ) == "abort"
    assert backend.request_disposition(
        "http://private.example/",
        is_navigation=True,
        source_origin=source_origin,
    ) == "fail"
    assert backend.request_disposition(
        "https://cdn.example/asset.png",
        is_navigation=False,
        source_origin=source_origin,
    ) == "continue"
    assert backend.request_disposition(
        "https://different.example/",
        is_navigation=True,
        source_origin=source_origin,
    ) == "fail"
    assert backend.request_disposition(
        "https://source.example/article/",
        is_navigation=True,
        source_origin=source_origin,
    ) == "continue"


def test_route_probes_obey_one_global_deadline(
    golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    service = SourceVisualService(probe_deadline_seconds=0.001)

    with pytest.raises(TimeoutError, match="global deadline"):
        service.capture(
            contracts_dir,
            tmp_path / "source",
            FakeCapture(capture_png),
            SlowProbe(),
        )

    assert not (tmp_path / "source").exists()


def test_confirmed_unavailable_route_is_recorded_and_not_captured(
    golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    omitted_target = golden_contracts.visual_capture_plan.targets[0]
    source = tmp_path / "source"

    receipt = SourceVisualService().capture(
        contracts_dir,
        source,
        FakeCapture(capture_png),
        FakeProbe(
            {
                omitted_target.source_url: RouteProbeResult(
                    404, omitted_target.source_url
                )
            }
        ),
    )

    omitted = [
        item for item in receipt.route_availability if item.disposition == "omitted"
    ]
    assert [item.route_contract_id for item in omitted] == [
        omitted_target.route_contract_id
    ]
    assert omitted[0].reason == "http_404"
    assert not any(
        item.route_contract_id == omitted_target.route_contract_id
        for item in receipt.evidence
    )
    SourceVisualService().verify_and_copy(contracts_dir, source, tmp_path / "protected")


def test_transient_or_server_route_failure_is_not_omitted(
    golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    target = golden_contracts.visual_capture_plan.targets[0]
    output = tmp_path / "source"

    with pytest.raises(ValueError, match="HTTP 500"):
        SourceVisualService().capture(
            contracts_dir,
            output,
            FakeCapture(capture_png),
            FakeProbe({target.source_url: RouteProbeResult(500, target.source_url)}),
        )

    assert not output.exists()


def test_capture_rejects_off_origin_and_blank_evidence(
    golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)

    with pytest.raises(ValueError, match="Off-origin"):
        SourceVisualService().capture(
            contracts_dir, tmp_path / "off-origin", OffOriginCapture(capture_png)
        )
    assert not (tmp_path / "off-origin").exists()
    with pytest.raises(ValueError, match="blank"):
        SourceVisualService().capture(contracts_dir, tmp_path / "blank", BlankCapture())
    assert not (tmp_path / "blank").exists()


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "checksum"])
def test_visual_verification_rejects_receipt_mutations(
    mutation, golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    source = tmp_path / "source"
    SourceVisualService().capture(contracts_dir, source, FakeCapture(capture_png))
    receipt_path = source / "capture-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if mutation == "missing":
        (source / receipt["evidence"][0]["artifact"]).unlink()
    elif mutation == "duplicate":
        receipt["evidence"].append(receipt["evidence"][0])
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    else:
        receipt["evidence"][0]["sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ValueError):
        SourceVisualService().verify_and_copy(
            contracts_dir, source, tmp_path / "protected"
        )
