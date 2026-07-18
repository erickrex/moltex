from __future__ import annotations

import json
from io import BytesIO

import pytest
from PIL import Image

from moltex_harness.contracts import ContractStore
from moltex_harness.visuals.service import CaptureResult, SourceVisualService


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


def test_visual_receipt_is_bundle_bound_and_checksum_verified(
    golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    source = tmp_path / "source"
    receipt = SourceVisualService().capture(
        contracts_dir, source, FakeCapture(capture_png)
    )

    destination = tmp_path / "protected"
    verified = SourceVisualService().verify_and_copy(contracts_dir, source, destination)

    assert verified.bundle_id == golden_contracts.source_manifest.bundle_id
    assert len(receipt.evidence) == len(golden_contracts.visual_capture_plan.targets)
    assert (destination / "capture-receipt.json").is_file()


def test_capture_rejects_off_origin_and_blank_evidence(
    golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)

    with pytest.raises(ValueError, match="Off-origin"):
        SourceVisualService().capture(
            contracts_dir, tmp_path / "off-origin", OffOriginCapture(capture_png)
        )
    with pytest.raises(ValueError, match="blank"):
        SourceVisualService().capture(
            contracts_dir, tmp_path / "blank", BlankCapture()
        )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "checksum"])
def test_visual_verification_rejects_receipt_mutations(
    mutation, golden_contracts, capture_png, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    source = tmp_path / "source"
    SourceVisualService().capture(
        contracts_dir, source, FakeCapture(capture_png)
    )
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
