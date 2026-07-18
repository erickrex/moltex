"""Bundle-bound source screenshot capture and verification."""

from __future__ import annotations

import hashlib
import shutil
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from PIL import Image, ImageChops, UnidentifiedImageError

from moltex_harness.contracts import ContractStore, ContractVerifier
from moltex_harness.intake.serialization import deterministic_json, write_json
from moltex_harness.models import SourceVisualEvidence, SourceVisualReceipt, VisualCaptureTarget


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class CaptureResult:
    png: bytes
    final_url: str
    browser: str
    browser_version: str


class CaptureBackend(Protocol):
    def capture(self, target: VisualCaptureTarget) -> CaptureResult: ...


class PlaywrightCaptureBackend:
    def capture(self, target: VisualCaptureTarget) -> CaptureResult:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": target.viewport.width, "height": target.viewport.height},
                device_scale_factor=1,
            )
            response = page.goto(target.source_url, wait_until="networkidle", timeout=30_000)
            if response is None or not response.ok:
                browser.close()
                raise ValueError(f"Source capture failed for {target.source_url}")
            png = page.screenshot(full_page=True, type="png")
            final_url = page.url
            version = browser.version
            browser.close()
        return CaptureResult(png, final_url, "playwright-chromium", version)


class SourceVisualService:
    def capture(
        self,
        contract_dir: Path,
        output: Path,
        backend: CaptureBackend | None = None,
    ) -> SourceVisualReceipt:
        if output.exists() and any(output.iterdir()):
            raise ValueError("Source visual output directory must be empty")
        verification = ContractVerifier().verify(contract_dir)
        if verification.status != "pass":
            raise ValueError("H2 contracts must pass verification before source capture")
        contracts, _ = ContractStore().load(contract_dir)
        plan = contracts.visual_capture_plan
        output.mkdir(parents=True, exist_ok=True)
        evidence_dir = output / "images"
        evidence_dir.mkdir(exist_ok=True)
        backend = backend or PlaywrightCaptureBackend()
        evidence: list[SourceVisualEvidence] = []
        browser_identity: tuple[str, str] | None = None
        seen: set[str] = set()
        for target in plan.targets:
            if target.evidence_id in seen:
                raise ValueError(f"Duplicate visual evidence id: {target.evidence_id}")
            seen.add(target.evidence_id)
            self._require_public_http(target.source_url)
            result = backend.capture(target)
            if self._origin(result.final_url) != self._origin(target.source_url):
                raise ValueError(f"Off-origin source capture redirect: {result.final_url}")
            self._validate_png(
                result.png, target.viewport.width, target.viewport.height
            )
            identity = (result.browser, result.browser_version)
            if browser_identity not in {None, identity}:
                raise ValueError("A capture receipt cannot mix browser versions")
            browser_identity = identity
            artifact = f"images/{target.evidence_id}.png"
            (output / artifact).write_bytes(result.png)
            evidence.append(
                SourceVisualEvidence(
                    evidence_id=target.evidence_id,
                    route_contract_id=target.route_contract_id,
                    source_url=target.source_url,
                    final_url=result.final_url,
                    viewport_name=target.viewport.name,
                    width=target.viewport.width,
                    height=target.viewport.height,
                    artifact=artifact,
                    bytes=len(result.png),
                    sha256=hashlib.sha256(result.png).hexdigest(),
                )
            )
        browser, version = browser_identity or ("playwright-chromium", "unknown")
        plan_hash = hashlib.sha256(deterministic_json(plan).encode()).hexdigest()
        receipt = SourceVisualReceipt(
            bundle_id=contracts.source_manifest.bundle_id,
            capture_plan_id=plan.plan_id,
            capture_plan_sha256=plan_hash,
            browser=browser,
            browser_version=version,
            evidence=tuple(evidence),
        )
        write_json(output / "manifest.json", receipt.evidence)
        write_json(output / "capture-receipt.json", receipt)
        return receipt

    def verify_and_copy(self, contract_dir: Path, source: Path, destination: Path) -> SourceVisualReceipt:
        contracts, _ = ContractStore().load(contract_dir)
        receipt = SourceVisualReceipt.model_validate_json(
            (source / "capture-receipt.json").read_text(encoding="utf-8")
        )
        plan = contracts.visual_capture_plan
        if receipt.bundle_id != contracts.source_manifest.bundle_id:
            raise ValueError("Visual receipt belongs to a different source bundle")
        expected_hash = hashlib.sha256(deterministic_json(plan).encode()).hexdigest()
        if receipt.capture_plan_id != plan.plan_id or receipt.capture_plan_sha256 != expected_hash:
            raise ValueError("Visual receipt does not match the H2 capture plan")
        expected = {target.evidence_id: target for target in plan.targets}
        actual = {item.evidence_id: item for item in receipt.evidence}
        if set(actual) != set(expected) or len(actual) != len(receipt.evidence):
            raise ValueError("Visual receipt target set is incomplete or duplicated")
        destination.mkdir(parents=True, exist_ok=True)
        for evidence_id, item in actual.items():
            target = expected[evidence_id]
            if item.route_contract_id != target.route_contract_id or item.source_url != target.source_url:
                raise ValueError(f"Visual evidence binding mismatch: {evidence_id}")
            if (
                item.viewport_name != target.viewport.name
                or item.width != target.viewport.width
                or item.height != target.viewport.height
                or self._origin(item.final_url) != self._origin(item.source_url)
            ):
                raise ValueError(f"Visual evidence viewport or final URL mismatch: {evidence_id}")
            artifact = (source / item.artifact).resolve()
            if source.resolve() not in artifact.parents or not artifact.is_file():
                raise ValueError(f"Visual evidence artifact is missing: {item.artifact}")
            data = artifact.read_bytes()
            self._validate_png(data, item.width, item.height)
            if len(data) != item.bytes or hashlib.sha256(data).hexdigest() != item.sha256:
                raise ValueError(f"Visual evidence checksum mismatch: {item.artifact}")
            target_path = destination / item.artifact
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact, target_path)
        write_json(destination / "manifest.json", receipt.evidence)
        write_json(destination / "capture-receipt.json", receipt)
        return receipt

    @staticmethod
    def _validate_png(data: bytes, width: int, minimum_height: int) -> None:
        if not data.startswith(PNG_SIGNATURE):
            raise ValueError("Source capture is not a PNG")
        try:
            with Image.open(BytesIO(data)) as source:
                source.verify()
            with Image.open(BytesIO(data)) as source:
                if source.format != "PNG" or source.width != width:
                    raise ValueError("Source capture does not match its viewport width")
                if source.height < minimum_height or source.height > 30_000:
                    raise ValueError("Source capture height is outside the allowed bounds")
                image = source.convert("RGB")
                background = Image.new("RGB", image.size, image.getpixel((0, 0)))
                if ImageChops.difference(image, background).getbbox() is None:
                    raise ValueError("Source capture is blank")
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("Source capture is not a decodable PNG") from error

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int | None]:
        parsed = urlsplit(url)
        return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port

    @classmethod
    def _require_public_http(cls, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise ValueError(f"Visual capture requires a public HTTP URL: {url}")
