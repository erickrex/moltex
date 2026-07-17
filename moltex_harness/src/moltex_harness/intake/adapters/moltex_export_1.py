"""Adapter for the manifest-driven `moltex-export/1` contract."""

from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from moltex_harness.models import Finding, RawSourceEvidence

from ..archive import SafeArchive
from ..errors import IntakeError, UnsupportedExportError
from .base import AdapterValidation
from .common import compile_raw_evidence
from .legacy_1 import Legacy1Adapter


SCHEMA_ROOT = Path(__file__).parents[1] / "schemas" / "moltex-export-1"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class MoltexExport1Adapter:
    name = "moltex-export/1"

    def validate(self, bundle: SafeArchive) -> AdapterValidation:
        manifest = bundle.read_json("bundle.json")
        if not isinstance(manifest, dict):
            raise IntakeError(
                "invalid_manifest",
                "Bundle manifest must be a JSON object",
                artifact="bundle.json",
            )
        schema = manifest.get("schema")
        if schema != self.name:
            raise UnsupportedExportError(
                "unsupported_export",
                "Bundle declares an unsupported export schema",
                artifact="bundle.json",
                pointer="/schema",
            )
        self._validate_schema(manifest, "bundle.schema.json", "bundle.json")
        self._validate_bundle_identity(manifest)

        declared = self._declared_artifacts(manifest)
        compatibility_findings: list[Finding] = []
        actual_paths = set(bundle.paths())
        expected_paths = set(declared) | {"bundle.json"}
        missing = sorted(expected_paths - actual_paths)
        extras = sorted(actual_paths - expected_paths)
        if missing:
            raise IntakeError(
                "missing_artifact",
                "Manifest declares an artifact that is missing",
                artifact=missing[0],
                context={"count": len(missing)},
            )
        if extras:
            raise IntakeError(
                "undeclared_artifact",
                "Archive contains an artifact not declared by its manifest",
                artifact=extras[0],
                context={"count": len(extras)},
            )

        for path, receipt in sorted(declared.items()):
            item = bundle.item(path)
            if receipt["bytes"] != item.bytes:
                raise IntakeError(
                    "artifact_size_mismatch",
                    "Artifact size does not match its receipt",
                    artifact=path,
                )
            if receipt["sha256"] != item.sha256:
                raise IntakeError(
                    "checksum_mismatch",
                    "Artifact checksum does not match its receipt",
                    artifact=path,
                )
            schema_path = receipt.get("schema")
            if schema_path is not None:
                if not isinstance(schema_path, str) or not schema_path.startswith(
                    "schemas/"
                ):
                    raise IntakeError(
                        "invalid_schema_reference",
                        "Artifact schema reference is invalid",
                        artifact=path,
                    )
                schema_name = schema_path.removeprefix("schemas/")
                if schema_path not in declared:
                    raise IntakeError(
                        "missing_schema",
                        "Artifact references an undeclared schema",
                        artifact=path,
                    )
                instance = bundle.read_json(path)
                # Early moltex-export/1 fixtures serialized an empty taxonomy map
                # as [] rather than {}. The adapter preserves the raw value while
                # applying this single documented compatibility normalization.
                if (
                    path == "site_blueprint.json"
                    and isinstance(instance, dict)
                    and instance.get("taxonomies") == []
                ):
                    instance = dict(instance)
                    instance["taxonomies"] = {}
                    compatibility_findings.append(
                        Finding(
                            severity="warning",
                            code="v1_empty_taxonomies_normalized",
                            classification="observation",
                            message="Normalized the early v1 empty taxonomy-map encoding",
                            artifact=path,
                            pointer="/taxonomies",
                        )
                    )
                self._validate_schema(instance, schema_name, path)

        self._validate_registry(manifest, declared)
        completeness = self._object(bundle, "export_completeness.json")
        readiness = self._object(bundle, "migration_readiness.json")
        Legacy1Adapter._validate_readiness(readiness)
        counts = self._validate_counts(completeness, manifest, bundle)
        self._validate_privacy(manifest, completeness)
        if bool(manifest.get("complete")) != bool(completeness.get("complete")):
            raise IntakeError(
                "completeness_mismatch", "Manifest and completeness artifact disagree"
            )
        if (manifest.get("mode") == "complete") != bool(manifest.get("complete")):
            raise IntakeError(
                "completeness_mismatch", "Bundle mode and completeness status disagree"
            )

        warnings, findings = Legacy1Adapter._warnings(bundle)
        findings.extend(compatibility_findings)
        omissions: list[str] = []
        for optional in ("redirects_candidates.csv", "screenshots/manifest.json"):
            if not bundle.has(optional):
                omissions.append(optional)
                findings.append(
                    Finding(
                        severity="info",
                        code="optional_artifact_absent",
                        classification="omission",
                        message="Optional artifact is absent",
                        artifact=optional,
                    )
                )
        blockers = readiness.get("blockers", [])
        if blockers:
            findings.append(
                Finding(
                    severity="warning",
                    code="migration_blockers_reported",
                    classification="readiness",
                    message="Source export reports migration blockers",
                    artifact="migration_readiness.json",
                    pointer="/blockers",
                    context={"count": len(blockers)},
                )
            )
        return AdapterValidation(
            adapter=self.name,
            bundle_id=str(manifest["bundle_id"]),
            exporter_version=str(manifest["exporter_version"]),
            site_origin=str(manifest["site_origin"]),
            mode=str(manifest["mode"]),
            complete=bool(manifest["complete"]),
            privacy=manifest.get("privacy", {}),
            counts=counts,
            readiness=readiness,
            warnings=warnings,
            omissions=omissions,
            findings=findings,
            declared_artifacts=declared,
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
    def _declared_artifacts(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, receipt in enumerate(manifest["artifacts"]):
            path = receipt["path"]
            if (
                path == "bundle.json"
                or path in result
                or path.casefold() in {item.casefold() for item in result}
            ):
                raise IntakeError(
                    "duplicate_manifest_path",
                    "Manifest contains a duplicate artifact path",
                    artifact="bundle.json",
                    pointer=f"/artifacts/{index}/path",
                )
            result[path] = receipt
        return result

    @staticmethod
    def _validate_bundle_identity(manifest: dict[str, Any]) -> None:
        identity = dict(manifest)
        expected = identity.pop("bundle_id")
        identity.pop("created_at", None)
        actual = f"sha256:{hashlib.sha256(_canonical_json(identity)).hexdigest()}"
        if actual != expected:
            raise IntakeError(
                "bundle_identity_mismatch",
                "Bundle identity does not match its canonical manifest",
                artifact="bundle.json",
                pointer="/bundle_id",
            )

    @staticmethod
    def _validate_schema(instance: Any, schema_name: str, artifact: str) -> None:
        schema_path = SCHEMA_ROOT / schema_name
        if not schema_path.is_file():
            raise IntakeError(
                "unsupported_schema",
                "Artifact references an unsupported schema",
                artifact=artifact,
            )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = sorted(
            Draft202012Validator(schema).iter_errors(instance),
            key=lambda error: list(error.path),
        )
        if errors:
            error = errors[0]
            pointer = "/" + "/".join(str(part) for part in error.absolute_path)
            raise IntakeError(
                "schema_validation_failed",
                "Artifact does not satisfy its declared schema",
                artifact=artifact,
                pointer=pointer.rstrip("/"),
                context={"validator": error.validator},
            )

    @staticmethod
    def _validate_registry(
        manifest: dict[str, Any], declared: dict[str, dict[str, Any]]
    ) -> None:
        paths = sorted(declared)
        for index, rule in enumerate(manifest["artifact_registry"]):
            if not isinstance(rule, dict) or not rule.get("required"):
                continue
            exact = rule.get("path")
            pattern = rule.get("pattern")
            if exact and exact != "bundle.json" and exact not in declared:
                raise IntakeError(
                    "required_artifact_missing",
                    "Required registry artifact is not declared",
                    artifact="bundle.json",
                    pointer=f"/artifact_registry/{index}",
                )
            if pattern and not any(fnmatch.fnmatch(path, pattern) for path in paths):
                raise IntakeError(
                    "required_artifact_missing",
                    "Required registry pattern has no declared artifact",
                    artifact="bundle.json",
                    pointer=f"/artifact_registry/{index}",
                )

    @staticmethod
    def _validate_counts(
        completeness: dict[str, Any],
        manifest: dict[str, Any],
        bundle: SafeArchive,
    ) -> dict[str, Any]:
        post_types = completeness.get("post_types")
        manifest_counts = manifest.get("counts")
        if not isinstance(post_types, dict) or not isinstance(manifest_counts, dict):
            raise IntakeError("invalid_counts", "Bundle counts must be JSON objects")
        if post_types != manifest_counts:
            raise IntakeError(
                "count_mismatch", "Manifest and completeness counts disagree"
            )
        exported_total = 0
        for post_type, values in sorted(post_types.items()):
            if not isinstance(values, dict):
                raise IntakeError("invalid_counts", "Post-type count must be an object")
            numbers = []
            for key in ("discovered", "exported", "excluded", "failed"):
                number = values.get(key)
                if (
                    isinstance(number, bool)
                    or not isinstance(number, int)
                    or number < 0
                ):
                    raise IntakeError(
                        "invalid_counts",
                        "Post-type count must be a non-negative integer",
                    )
                numbers.append(number)
            discovered, exported, excluded, failed = numbers
            if discovered != exported + excluded + failed:
                raise IntakeError(
                    "count_mismatch",
                    "Post-type counts do not reconcile",
                    artifact="export_completeness.json",
                    pointer=f"/post_types/{post_type}",
                )
            exported_total += exported
            if (
                completeness.get("complete") is True
                and values.get("complete") is not True
            ):
                raise IntakeError(
                    "completeness_mismatch",
                    "Complete export has an incomplete post type",
                    artifact="export_completeness.json",
                    pointer=f"/post_types/{post_type}/complete",
                )
        actual_total = len(
            [
                path
                for path in bundle.paths()
                if path.startswith("content/") and path.endswith(".json")
            ]
        )
        if exported_total != actual_total:
            raise IntakeError(
                "content_count_mismatch",
                "Exported content count does not match content artifacts",
            )
        return post_types

    @staticmethod
    def _validate_privacy(
        manifest: dict[str, Any], completeness: dict[str, Any]
    ) -> None:
        privacy = manifest.get("privacy")
        if not isinstance(privacy, dict):
            raise IntakeError(
                "invalid_privacy", "Manifest privacy declaration must be an object"
            )
        manifest_statuses = privacy.get("excluded_statuses")
        completeness_statuses = completeness.get("excluded_statuses")
        if manifest_statuses is not None and sorted(manifest_statuses) != sorted(
            completeness_statuses or []
        ):
            raise IntakeError(
                "privacy_mismatch",
                "Privacy exclusions disagree with completeness evidence",
            )
        if privacy.get("private_content_included") is True:
            raise IntakeError(
                "privacy_violation", "Bundle declares that private content is included"
            )
        if privacy.get("secret_scan") not in (None, "pass"):
            raise IntakeError(
                "secret_scan_failed", "Bundle did not pass its declared secret scan"
            )
