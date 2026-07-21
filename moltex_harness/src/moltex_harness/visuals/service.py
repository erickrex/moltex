"""Bundle-bound source screenshot capture and verification."""

from __future__ import annotations

import hashlib
import shutil
import urllib.error
import urllib.request
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urljoin, urlsplit

from PIL import Image, ImageChops, UnidentifiedImageError

from moltex_harness.contracts import ContractStore, ContractVerifier
from moltex_harness.intake.serialization import deterministic_json, write_json
from moltex_harness.models import (
    RouteAvailabilityEvidence,
    SourceVisualEvidence,
    SourceVisualReceipt,
    VisualCaptureTarget,
)
from moltex_harness.network import PublicNetworkPolicy, PublicRedirectHandler


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
AvailabilityDisposition = Literal["available", "omitted"]


@dataclass(frozen=True, slots=True)
class CaptureResult:
    png: bytes
    final_url: str
    browser: str
    browser_version: str


@dataclass(frozen=True, slots=True)
class RouteProbeResult:
    status_code: int
    final_url: str


class CaptureBackend(Protocol):
    def capture(self, target: VisualCaptureTarget) -> CaptureResult: ...


class RouteProbe(Protocol):
    def probe(self, url: str) -> RouteProbeResult: ...


class PublicRouteProbe:
    def __init__(self, policy: PublicNetworkPolicy | None = None) -> None:
        self.policy = policy or PublicNetworkPolicy()

    def probe(self, url: str) -> RouteProbeResult:
        self.policy.require_public(url)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Moltex-Harness/0.1"},
        )
        opener = urllib.request.build_opener(PublicRedirectHandler(self.policy))
        try:
            with opener.open(request, timeout=20) as response:
                self.policy.require_public(response.geturl())
                return RouteProbeResult(response.status, response.geturl())
        except urllib.error.HTTPError as error:
            self.policy.require_public(error.geturl())
            return RouteProbeResult(error.code, error.geturl())
        except (urllib.error.URLError, TimeoutError) as error:
            raise ConnectionError(f"Route availability probe failed for {url}") from error


class PlaywrightCaptureBackend:
    def __init__(self, policy: PublicNetworkPolicy | None = None) -> None:
        self.policy = policy or PublicNetworkPolicy()

    def capture(self, target: VisualCaptureTarget) -> CaptureResult:
        from playwright.sync_api import sync_playwright

        self.policy.require_public(target.source_url)
        source_origin = self.policy.origin(target.source_url)
        blocked: list[str] = []
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": target.viewport.width, "height": target.viewport.height},
                device_scale_factor=1,
            )

            def enforce(route) -> None:
                request = route.request
                try:
                    self.policy.require_public(request.url)
                    if request.is_navigation_request() and self.policy.origin(
                        request.url
                    ) != source_origin:
                        raise ValueError("Off-origin navigation")
                except ValueError:
                    blocked.append(request.url)
                    route.abort("blockedbyclient")
                    return
                route.continue_()

            context.route("**/*", enforce)
            page = context.new_page()
            try:
                response = page.goto(
                    target.source_url, wait_until="networkidle", timeout=30_000
                )
            except Exception as error:
                if blocked:
                    browser.close()
                    raise ValueError(
                        "Source capture blocked a non-public or off-origin request"
                    ) from error
                browser.close()
                raise
            if blocked:
                browser.close()
                raise ValueError(
                    "Source capture blocked a non-public or off-origin request"
                )
            if response is None or not response.ok:
                browser.close()
                status = response.status if response is not None else "no response"
                raise ValueError(
                    f"Source capture returned HTTP {status} for {target.source_url}"
                )
            png = page.screenshot(full_page=True, type="png")
            final_url = page.url
            version = browser.version
            browser.close()
        return CaptureResult(png, final_url, "playwright-chromium", version)


class SourceVisualService:
    def __init__(self, policy: PublicNetworkPolicy | None = None) -> None:
        self.policy = policy or PublicNetworkPolicy()

    def capture(
        self,
        contract_dir: Path,
        output: Path,
        backend: CaptureBackend | None = None,
        route_probe: RouteProbe | None = None,
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
        default_backend = backend is None
        backend = backend or PlaywrightCaptureBackend(self.policy)
        try:
            availability = self._route_availability(
                contracts,
                route_probe or (PublicRouteProbe(self.policy) if default_backend else None),
                validate_network=default_backend,
            )
        except Exception:
            shutil.rmtree(output)
            raise
        omitted_route_ids = {
            item.route_contract_id
            for item in availability
            if item.disposition == "omitted"
        }
        evidence: list[SourceVisualEvidence] = []
        browser_identity: tuple[str, str] | None = None
        seen: set[str] = set()
        try:
            for target in plan.targets:
                if target.route_contract_id in omitted_route_ids:
                    continue
                if target.evidence_id in seen:
                    raise ValueError(
                        f"Duplicate visual evidence id: {target.evidence_id}"
                    )
                seen.add(target.evidence_id)
                if default_backend:
                    self.policy.require_public(target.source_url)
                result = backend.capture(target)
                if self._origin(result.final_url) != self._origin(target.source_url):
                    raise ValueError(
                        f"Off-origin source capture redirect: {result.final_url}"
                    )
                self._validate_png(
                    result.png, target.viewport.width, target.viewport.height
                )
                identity = (result.browser, result.browser_version)
                if browser_identity not in {None, identity}:
                    raise ValueError("A capture receipt cannot mix browser versions")
                browser_identity = identity
                safe_id = target.evidence_id.replace(":", "-")
                artifact = f"images/{safe_id}.png"
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
        except Exception:
            shutil.rmtree(output)
            raise
        browser, version = browser_identity or ("playwright-chromium", "unknown")
        plan_hash = hashlib.sha256(deterministic_json(plan).encode()).hexdigest()
        receipt = SourceVisualReceipt(
            bundle_id=contracts.source_manifest.bundle_id,
            capture_plan_id=plan.plan_id,
            capture_plan_sha256=plan_hash,
            browser=browser,
            browser_version=version,
            route_availability=availability,
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
        public_routes = {route.contract_id: route for route in contracts.routes if route.public}
        availability = {item.route_contract_id: item for item in receipt.route_availability}
        if (
            set(availability) != set(public_routes)
            or len(availability) != len(receipt.route_availability)
        ):
            raise ValueError("Route availability receipt is incomplete or duplicated")
        for route_id, item in availability.items():
            route = public_routes[route_id]
            expected_url = urljoin(
                contracts.site_spec.source_origin.rstrip("/") + "/",
                route.legacy_url,
            )
            if item.source_url != expected_url:
                raise ValueError(f"Route availability binding mismatch: {route_id}")
            self._validate_availability(item)
        omitted_route_ids = {
            route_id
            for route_id, item in availability.items()
            if item.disposition == "omitted"
        }
        expected = {
            target.evidence_id: target
            for target in plan.targets
            if target.route_contract_id not in omitted_route_ids
        }
        actual = {item.evidence_id: item for item in receipt.evidence}
        if set(actual) != set(expected) or len(actual) != len(receipt.evidence):
            raise ValueError("Visual receipt target set is incomplete or duplicated")
        destination.mkdir(parents=True, exist_ok=True)
        for evidence_id, visual in actual.items():
            target = expected[evidence_id]
            if (
                visual.route_contract_id != target.route_contract_id
                or visual.source_url != target.source_url
            ):
                raise ValueError(f"Visual evidence binding mismatch: {evidence_id}")
            if (
                visual.viewport_name != target.viewport.name
                or visual.width != target.viewport.width
                or visual.height != target.viewport.height
                or self._origin(visual.final_url) != self._origin(visual.source_url)
            ):
                raise ValueError(f"Visual evidence viewport or final URL mismatch: {evidence_id}")
            artifact = (source / visual.artifact).resolve()
            if source.resolve() not in artifact.parents or not artifact.is_file():
                raise ValueError(
                    f"Visual evidence artifact is missing: {visual.artifact}"
                )
            data = artifact.read_bytes()
            self._validate_png(data, visual.width, visual.height)
            if (
                len(data) != visual.bytes
                or hashlib.sha256(data).hexdigest() != visual.sha256
            ):
                raise ValueError(
                    f"Visual evidence checksum mismatch: {visual.artifact}"
                )
            target_path = destination / visual.artifact
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact, target_path)
        write_json(destination / "manifest.json", receipt.evidence)
        write_json(destination / "capture-receipt.json", receipt)
        return receipt

    def _route_availability(
        self,
        contracts,
        probe: RouteProbe | None,
        *,
        validate_network: bool,
    ) -> tuple[RouteAvailabilityEvidence, ...]:
        values: list[RouteAvailabilityEvidence] = []
        origin = contracts.site_spec.source_origin.rstrip("/") + "/"
        for route in contracts.routes:
            if not route.public:
                continue
            source_url = urljoin(origin, route.legacy_url)
            if validate_network:
                self.policy.require_public(source_url)
            result = probe.probe(source_url) if probe else RouteProbeResult(200, source_url)
            disposition, reason = self._availability_disposition(result, source_url)
            item = RouteAvailabilityEvidence(
                route_contract_id=route.contract_id,
                source_url=source_url,
                final_url=result.final_url,
                status_code=result.status_code,
                disposition=disposition,
                reason=reason,
            )
            self._validate_availability(item)
            values.append(item)
        return tuple(values)

    @classmethod
    def _availability_disposition(
        cls, result: RouteProbeResult, source_url: str | None = None
    ) -> tuple[AvailabilityDisposition, str | None]:
        final_path = urlsplit(result.final_url).path.lower()
        if result.status_code in {401, 403, 404, 410}:
            return "omitted", f"http_{result.status_code}"
        if "wp-login.php" in final_path or final_path.rstrip("/").endswith(("/login", "/sign-in")):
            return "omitted", "authentication_redirect"
        if source_url and cls._origin(result.final_url) != cls._origin(source_url):
            return "omitted", "off_origin_redirect"
        if 200 <= result.status_code < 300:
            return "available", None
        raise ValueError(
            f"Route availability returned HTTP {result.status_code} for {result.final_url}"
        )

    @classmethod
    def _validate_availability(cls, item: RouteAvailabilityEvidence) -> None:
        expected, reason = cls._availability_disposition(
            RouteProbeResult(item.status_code, item.final_url), item.source_url
        )
        if item.disposition != expected or item.reason != reason:
            raise ValueError(
                f"Route availability disposition mismatch: {item.route_contract_id}"
            )

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
    def _origin(url: str) -> tuple[str, str, int]:
        return PublicNetworkPolicy.origin(url)
