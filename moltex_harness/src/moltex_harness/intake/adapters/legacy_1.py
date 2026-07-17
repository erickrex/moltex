"""Immutable adapter for pre-manifest Moltex legacy exports."""

from __future__ import annotations

from typing import Any

from moltex_harness.models import Finding, RawSourceEvidence

from ..archive import SafeArchive
from ..errors import IntakeError
from .base import AdapterValidation
from .common import compile_raw_evidence


LEGACY_REQUIRED = (
    "export_completeness.json",
    "forms_config.json",
    "media/media_map.json",
    "menus.json",
    "migration_readiness.json",
    "site_blueprint.json",
    "site_settings.json",
)


class Legacy1Adapter:
    name = "legacy-1"

    def validate(self, bundle: SafeArchive) -> AdapterValidation:
        for path in LEGACY_REQUIRED:
            bundle.item(path)

        blueprint = self._object(bundle, "site_blueprint.json")
        completeness = self._object(bundle, "export_completeness.json")
        readiness = self._object(bundle, "migration_readiness.json")
        self._validate_readiness(readiness)
        for path in LEGACY_REQUIRED:
            value = bundle.read_json(path)
            if isinstance(value, dict) and value.get("schema_version") != 1:
                raise IntakeError(
                    "unsupported_schema_version",
                    "Legacy artifact has an unsupported schema version",
                    artifact=path,
                )

        content_count = len(
            [
                path
                for path in bundle.paths()
                if path.startswith("content/")
                and path.endswith(".json")
                and len(path.split("/")) == 3
            ]
        )
        post_types = completeness.get("post_types")
        if not isinstance(post_types, dict):
            raise IntakeError(
                "invalid_completeness", "Completeness post_types must be an object"
            )
        expected = 0
        counts: dict[str, Any] = {}
        for post_type, count in sorted(post_types.items()):
            if not isinstance(count, dict):
                raise IntakeError(
                    "invalid_completeness", "Post-type completeness must be an object"
                )
            discovered = self._integer(count, "discovered", "export_completeness.json")
            exported = self._integer(count, "exported", "export_completeness.json")
            excluded = int(count.get("excluded", max(discovered - exported, 0)))
            failed = int(count.get("failed", 0))
            if discovered != exported + excluded + failed:
                raise IntakeError(
                    "count_mismatch",
                    "Legacy completeness counts do not reconcile",
                    artifact="export_completeness.json",
                    pointer=f"/post_types/{post_type}",
                )
            expected += exported
            counts[str(post_type)] = {
                "discovered": discovered,
                "exported": exported,
                "excluded": excluded,
                "failed": failed,
                "complete": bool(count.get("complete", False)),
            }
        if expected != content_count:
            raise IntakeError(
                "content_count_mismatch",
                "Legacy content count does not match completeness evidence",
            )

        blueprint_total = blueprint.get("content", {}).get("total_exported")
        if blueprint_total is not None and blueprint_total != content_count:
            raise IntakeError(
                "content_count_mismatch", "Site blueprint content total is inconsistent"
            )

        site = blueprint.get("site") if isinstance(blueprint.get("site"), dict) else {}
        plugins = (
            blueprint.get("plugins")
            if isinstance(blueprint.get("plugins"), list)
            else []
        )
        exporter_version = None
        for plugin in plugins:
            if (
                isinstance(plugin, dict)
                and "moltex" in str(plugin.get("name", "")).lower()
            ):
                exporter_version = (
                    str(plugin.get("version")) if plugin.get("version") else None
                )
                break

        warnings, findings = self._warnings(bundle)
        omissions = [
            path
            for path in (
                "bundle.json",
                "seo_full.json",
                "integration_manifest.json",
                "redirects_candidates.csv",
            )
            if not bundle.has(path)
        ]
        findings.extend(
            Finding(
                severity="info",
                code="legacy_omission",
                classification="omission",
                message="Artifact is not part of this legacy export",
                artifact=path,
            )
            for path in omissions
        )
        return AdapterValidation(
            adapter=self.name,
            bundle_id=f"sha256:{bundle.archive_sha256}",
            exporter_version=exporter_version,
            site_origin=site.get("url") or site.get("home_url"),
            mode="complete" if completeness.get("complete") else "discovery",
            complete=bool(completeness.get("complete")),
            privacy={
                "excluded_statuses": completeness.get("excluded_statuses", []),
                "private_content_included": False,
            },
            counts=counts,
            readiness=readiness,
            warnings=warnings,
            omissions=sorted(omissions),
            findings=findings,
        )

    def parse(
        self, bundle: SafeArchive, validation: AdapterValidation
    ) -> RawSourceEvidence:
        return compile_raw_evidence(bundle, validation)

    @staticmethod
    def _object(bundle: SafeArchive, path: str) -> dict[str, Any]:
        value = bundle.read_json(path)
        if not isinstance(value, dict):
            raise IntakeError(
                "invalid_json_shape", "Artifact must be a JSON object", artifact=path
            )
        return value

    @staticmethod
    def _integer(value: dict[str, Any], key: str, artifact: str) -> int:
        result = value.get(key)
        if isinstance(result, bool) or not isinstance(result, int) or result < 0:
            raise IntakeError(
                "invalid_count", "Artifact contains an invalid count", artifact=artifact
            )
        return result

    @staticmethod
    def _warnings(bundle: SafeArchive) -> tuple[list[str], list[Finding]]:
        if not bundle.has("error_log.json"):
            return [], []
        value = bundle.read_json("error_log.json")
        records = value.get("warnings", []) if isinstance(value, dict) else []
        warnings: list[str] = []
        findings: list[Finding] = []
        for index, record in enumerate(records if isinstance(records, list) else []):
            message = (
                str(record.get("message", "Export warning"))
                if isinstance(record, dict)
                else "Export warning"
            )
            warnings.append(message)
            findings.append(
                Finding(
                    severity="warning",
                    code="source_warning",
                    classification="observation",
                    message=message,
                    artifact="error_log.json",
                    pointer=f"/warnings/{index}",
                )
            )
        return warnings, findings

    @staticmethod
    def _validate_readiness(readiness: dict[str, Any]) -> None:
        blockers = readiness.get("blockers", [])
        eligible = readiness.get("eligible")
        if not isinstance(blockers, list):
            raise IntakeError(
                "invalid_readiness", "Readiness blockers must be an array"
            )
        if eligible is not None and not isinstance(eligible, bool):
            raise IntakeError(
                "invalid_readiness", "Readiness eligibility must be boolean"
            )
        if eligible is True and blockers:
            raise IntakeError(
                "readiness_mismatch", "Eligible export declares migration blockers"
            )
