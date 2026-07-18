"""Cross-file verifier for materialized H2 contracts."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from moltex_harness.models import (
    ContractSet,
    ContractVerificationReport,
    EvidenceReference,
)

from .store import FILE_LAYOUT, ContractStore


class ContractVerifier:
    def verify(self, source: Path) -> ContractVerificationReport:
        errors: list[str] = []
        checks: dict[str, bool] = {}
        bundle_id: str | None = None
        files_checked = 0
        try:
            contracts, index = ContractStore().load(source)
            bundle_id = index.bundle_id
            errors.extend(self._verify_receipts(source, index))
            files_checked = len(index.files)
            checks["file_integrity"] = not errors
            cross_errors = self._verify_cross_contracts(contracts)
            errors.extend(cross_errors)
            checks["cross_contract_integrity"] = not cross_errors
            lineage_errors = self._verify_lineage(contracts)
            errors.extend(lineage_errors)
            checks["evidence_lineage"] = not lineage_errors
        except (OSError, ValueError, ValidationError) as error:
            errors.append(f"contract_load: {type(error).__name__}")
            checks.setdefault("file_integrity", False)
            checks.setdefault("cross_contract_integrity", False)
            checks.setdefault("evidence_lineage", False)
        return ContractVerificationReport(
            status="fail" if errors else "pass",
            bundle_id=bundle_id,
            files_checked=files_checked,
            checks=checks,
            errors=tuple(errors),
        )

    @staticmethod
    def _verify_receipts(source: Path, index: Any) -> list[str]:
        errors: list[str] = []
        expected = {path for path, _, _ in FILE_LAYOUT}
        declared = {receipt.path for receipt in index.files}
        if declared != expected:
            errors.append(
                "contract_index_paths: index does not declare the exact H2 artifact set"
            )
        for receipt in index.files:
            if receipt.path not in expected:
                continue
            pure = PurePosixPath(receipt.path)
            if pure.is_absolute() or ".." in pure.parts or "\\" in receipt.path:
                errors.append(f"unsafe_contract_path: {receipt.path}")
                continue
            path = source / Path(*pure.parts)
            if not path.is_file():
                errors.append(f"missing_contract_file: {receipt.path}")
                continue
            data = path.read_bytes()
            if len(data) != receipt.bytes:
                errors.append(f"contract_size_mismatch: {receipt.path}")
            if hashlib.sha256(data).hexdigest() != receipt.sha256:
                errors.append(f"contract_checksum_mismatch: {receipt.path}")
        return errors

    @staticmethod
    def _verify_cross_contracts(contracts: ContractSet) -> list[str]:
        errors: list[str] = []
        routes = {route.contract_id: route for route in contracts.routes}
        content = {record.record_id: record for record in contracts.content_records}
        assets = {asset.asset_id: asset for asset in contracts.assets}
        capabilities = {item.capability_id: item for item in contracts.capabilities}
        public_records = {
            record.record_id
            for record in contracts.content_records
            if record.status == "publish"
        }
        content_route_ids = [
            route.content_record_id
            for route in contracts.routes
            if route.content_record_id is not None
        ]
        route_records = set(content_route_ids)
        if route_records != public_records or len(content_route_ids) != len(
            route_records
        ):
            errors.append("route_coverage: public content must have exactly one route")
        if len(routes) != len(contracts.routes):
            errors.append("route_ids: route contract IDs are not unique")
        if len({route.target_url for route in contracts.routes}) != len(
            contracts.routes
        ):
            errors.append("route_targets: target URLs are not unique")
        seo_counts = Counter(item.route_contract_id for item in contracts.seo)
        if set(seo_counts) != set(routes) or any(
            count != 1 for count in seo_counts.values()
        ):
            errors.append(
                "seo_coverage: every route must have exactly one SEO contract"
            )
        for record in contracts.content_records:
            missing_assets = set(record.required_media_ids) - set(assets)
            missing_routes = set(record.internal_route_ids) - set(routes)
            if missing_assets:
                errors.append(f"content_media_reference: {record.record_id}")
            if missing_routes:
                errors.append(f"content_route_reference: {record.record_id}")
        for asset in contracts.assets:
            if set(asset.referencing_content_ids) - {
                item.source_id for item in content.values()
            }:
                errors.append(f"asset_content_reference: {asset.asset_id}")
        for redirect in contracts.redirects:
            if (
                redirect.target_route_contract_id
                and redirect.target_route_contract_id not in routes
            ):
                errors.append(f"redirect_target_reference: {redirect.contract_id}")
        redirect_sources = {redirect.source_url for redirect in contracts.redirects}
        if any(
            route.redirect_required and route.legacy_url not in redirect_sources
            for route in contracts.routes
        ):
            errors.append(
                "redirect_coverage: changed legacy routes require redirect contracts"
            )
        parity_subjects = {
            (row.subject_type, row.subject_id) for row in contracts.parity_matrix
        }
        expected_parity = {
            ("route", route.source_content_id) for route in routes.values()
        } | {("capability", capability_id) for capability_id in capabilities}
        if parity_subjects != expected_parity or len(parity_subjects) != len(
            contracts.parity_matrix
        ):
            errors.append(
                "parity_coverage: each public item and capability needs exactly one row"
            )
        selected = set(contracts.visual_capture_plan.selected_route_ids)
        if not selected or selected - set(routes):
            errors.append("visual_routes: selected visual routes must resolve")
        if len(selected) > contracts.visual_capture_plan.max_routes:
            errors.append("visual_bound: visual route selection exceeds its bound")
        target_profiles: dict[str, set[str]] = defaultdict(set)
        for target in contracts.visual_capture_plan.targets:
            if target.route_contract_id not in selected:
                errors.append(f"visual_target_reference: {target.target_id}")
            target_profiles[target.route_contract_id].add(target.viewport.name)
        required_profiles = {"desktop-1440x1200", "mobile-500x844"}
        if any(target_profiles[route_id] != required_profiles for route_id in selected):
            errors.append(
                "visual_viewports: every selected route needs both pinned viewports"
            )
        if contracts.site_spec.static_eligibility == "eligible" and contracts.decisions:
            errors.append(
                "eligibility_decisions: eligible site has unresolved decisions"
            )
        decision_ids = {decision.decision_id for decision in contracts.decisions}
        if set(contracts.site_spec.unresolved_decision_ids) != decision_ids:
            errors.append("decision_queue: site spec and decision queue disagree")
        if set(contracts.site_spec.capability_ids) != set(capabilities):
            errors.append(
                "capability_index: site spec and capability contracts disagree"
            )
        url_routes = {entry.route_contract_id for entry in contracts.url_map}
        if url_routes != set(routes):
            errors.append("url_map_coverage: every route must be represented")
        media_assets = {entry.asset_contract_id for entry in contracts.media_map}
        if media_assets != set(assets):
            errors.append("media_map_coverage: every asset must be represented")
        media_target_paths: set[str] = set()
        media_target_urls: set[str] = set()
        for entry in contracts.media_map:
            asset = assets.get(entry.asset_contract_id)
            expected_url = "/" + entry.target_path.removeprefix("public/")
            if (
                not entry.target_path.startswith("public/media/")
                or not entry.target_url.startswith("/media/")
                or entry.target_url != expected_url
            ):
                errors.append(f"media_local_target: {entry.asset_contract_id}")
            if (
                entry.target_path in media_target_paths
                or entry.target_url in media_target_urls
            ):
                errors.append(f"media_target_collision: {entry.asset_contract_id}")
            media_target_paths.add(entry.target_path)
            media_target_urls.add(entry.target_url)
            if asset and (
                asset.target_path != entry.target_path
                or asset.acquisition_status != entry.acquisition_status
                or asset.runtime_policy != entry.runtime_policy
            ):
                errors.append(f"media_asset_map_mismatch: {entry.asset_contract_id}")
        for asset in assets.values():
            if asset.acquisition_status == "bundled" and not asset.bundle_path:
                errors.append(f"media_bundled_artifact: {asset.asset_id}")
            if asset.acquisition_status == "deferred" and (
                asset.bundle_path is not None
                or asset.acquisition_method != "source-fetch"
                or asset.needs_decision
            ):
                errors.append(f"media_deferred_contract: {asset.asset_id}")
        return errors

    def _verify_lineage(self, contracts: ContractSet) -> list[str]:
        errors: list[str] = []
        inventory = {
            item.path: item.sha256 for item in contracts.source_manifest.inventory
        }
        references = list(self._evidence_references(contracts))
        for reference in references:
            if reference.bundle_id != contracts.source_manifest.bundle_id:
                errors.append(f"evidence_bundle: {reference.evidence_id}")
            elif inventory.get(reference.artifact) != reference.sha256:
                errors.append(f"evidence_artifact: {reference.evidence_id}")
            if reference.pointer and not reference.pointer.startswith("/"):
                errors.append(f"evidence_pointer: {reference.evidence_id}")
        if not references:
            errors.append("evidence_empty: no evidence references were found")
        return errors

    def _evidence_references(self, value: Any) -> Iterable[EvidenceReference]:
        if isinstance(value, EvidenceReference):
            yield value
            return
        if isinstance(value, BaseModel):
            for field in type(value).model_fields:
                yield from self._evidence_references(getattr(value, field))
            return
        if isinstance(value, dict):
            for item in value.values():
                yield from self._evidence_references(item)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                yield from self._evidence_references(item)
