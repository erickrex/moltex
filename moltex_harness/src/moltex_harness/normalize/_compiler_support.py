"""Shared evidence, lineage, and diagnostic support for contract compilation."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from html.parser import HTMLParser
from typing import Any, Iterable, Literal, TypeVar

from pydantic import BaseModel

from moltex_harness.intake.serialization import deterministic_json
from moltex_harness.models import (
    ContractSet,
    DecisionItem,
    DerivedLineage,
    EvidenceReference,
    EvidenceResolution,
    NormalizationFinding,
    RawArtifactEvidence,
    RawContentEvidence,
    RawMediaEvidence,
    RawSourceEvidence,
)
from moltex_harness.models.contracts import LineagedModel

from .primitives import (
    stable_hash,
)


class ContractCompilationError(ValueError):
    """A permanent semantic contradiction in accepted raw evidence."""

    exit_code = 6

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _MediaSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in {"img", "source", "video", "audio"}:
            return
        for name, value in attrs:
            if name.lower() == "src" and value:
                self.sources.add(value)


TLineaged = TypeVar("TLineaged", bound=LineagedModel)


def _field_ref(base: EvidenceReference, pointer: str) -> EvidenceReference:
    root = base.pointer.rstrip("/")
    suffix = pointer if pointer.startswith("/") else f"/{pointer}"
    combined = f"{root}{suffix}" if root else suffix
    identity = stable_hash(base.bundle_id, base.artifact, combined, length=40)
    return EvidenceReference(
        evidence_id=f"ev:{identity}",
        bundle_id=base.bundle_id,
        artifact=base.artifact,
        pointer=combined,
        sha256=base.sha256,
    )


def _lineage(
    model: type[TLineaged],
    inputs: EvidenceReference | Iterable[EvidenceReference],
    rule: str,
    *,
    decision: str | None = None,
    overrides: dict[str, tuple[Iterable[EvidenceReference], str, str | None]]
    | None = None,
) -> dict[str, DerivedLineage]:
    refs = (inputs,) if isinstance(inputs, EvidenceReference) else tuple(inputs)
    fields = set(model.model_fields) - {"schema_version", "lineage"}
    result = {
        field: DerivedLineage(derived_by=rule, inputs=refs, decision=decision)
        for field in fields
    }
    for field, (field_inputs, field_rule, field_decision) in (overrides or {}).items():
        result[field] = DerivedLineage(
            derived_by=field_rule,
            inputs=tuple(field_inputs),
            decision=field_decision,
        )
    return result


def _json_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


class _CompilerSupport:
    def _evidence_resolutions(
        self, raw: RawSourceEvidence, contracts: ContractSet
    ) -> tuple[EvidenceResolution, ...]:
        documents = self._source_documents(raw)
        inventory = {item.path: item.sha256 for item in raw.inventory}
        resolutions: dict[str, EvidenceResolution] = {}
        for reference in self._evidence_references(contracts):
            artifact_hash = inventory.get(reference.artifact)
            if artifact_hash != reference.sha256:
                raise ContractCompilationError(
                    "evidence_artifact_mismatch",
                    f"Evidence artifact cannot be resolved: {reference.artifact}",
                )
            value: Any = None
            if reference.pointer:
                if reference.artifact not in documents:
                    raise ContractCompilationError(
                        "evidence_document_missing",
                        f"No typed source document is available for {reference.artifact}",
                    )
                try:
                    value = self._resolve_pointer(
                        documents[reference.artifact], reference.pointer
                    )
                except (KeyError, IndexError, TypeError, ValueError) as error:
                    raise ContractCompilationError(
                        "evidence_pointer_missing",
                        f"Evidence pointer does not resolve: {reference.artifact}{reference.pointer}",
                    ) from error
            resolution = EvidenceResolution(
                evidence_id=reference.evidence_id,
                bundle_id=reference.bundle_id,
                artifact=reference.artifact,
                pointer=reference.pointer,
                artifact_sha256=reference.sha256,
                value_sha256=hashlib.sha256(
                    deterministic_json(value).encode("utf-8")
                ).hexdigest(),
            )
            existing = resolutions.get(reference.evidence_id)
            if existing and existing != resolution:
                raise ContractCompilationError(
                    "evidence_id_collision",
                    f"Evidence ID maps to conflicting source locations: {reference.evidence_id}",
                )
            resolutions[reference.evidence_id] = resolution
        return tuple(sorted(resolutions.values(), key=lambda item: item.evidence_id))

    @staticmethod
    def _evidence_references(value: Any) -> Iterable[EvidenceReference]:
        if isinstance(value, EvidenceReference):
            yield value
        elif isinstance(value, BaseModel):
            for field in type(value).model_fields:
                if field != "evidence_resolutions":
                    yield from _CompilerSupport._evidence_references(
                        getattr(value, field)
                    )
        elif isinstance(value, dict):
            for item in value.values():
                yield from _CompilerSupport._evidence_references(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from _CompilerSupport._evidence_references(item)

    @staticmethod
    def _source_documents(raw: RawSourceEvidence) -> dict[str, Any]:
        documents = {
            item.artifact: item.data
            for collection in (
                raw.site,
                raw.navigation,
                raw.seo,
                raw.redirects,
                raw.capabilities,
            )
            for item in collection
        }
        for content_item in raw.content:
            document = content_item.model_dump(mode="json", exclude={"evidence"})
            document["raw_html"] = document.pop("original_html")
            documents[content_item.evidence.artifact] = document
        media_by_artifact: dict[str, list[RawMediaEvidence]] = defaultdict(list)
        for media_item in raw.media:
            media_by_artifact[media_item.evidence.artifact].append(media_item)
        for artifact, items in media_by_artifact.items():
            documents[artifact] = [
                item.model_dump(mode="json", exclude={"evidence"}) for item in items
            ]
        source = raw.source_manifest
        documents.setdefault(
            "bundle.json",
            {
                "privacy": source.privacy,
                "counts": source.counts,
                "readiness": source.readiness,
            },
        )
        documents.setdefault(
            "export_completeness.json",
            {"post_types": source.counts, "excluded_statuses": []},
        )
        documents.setdefault("migration_readiness.json", source.readiness)
        return documents

    @staticmethod
    def _resolve_pointer(document: Any, pointer: str) -> Any:
        if not pointer:
            return document
        if not pointer.startswith("/"):
            raise ValueError("JSON pointer must be absolute")
        value = document
        for token in pointer[1:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                value = value[int(token)]
            elif isinstance(value, dict):
                value = value[token]
            else:
                raise TypeError("JSON pointer traverses a scalar")
        return value

    @staticmethod
    def _artifact(raw: RawSourceEvidence, path: str) -> RawArtifactEvidence:
        for artifact in (
            *raw.site,
            *raw.navigation,
            *raw.seo,
            *raw.redirects,
            *raw.capabilities,
        ):
            if artifact.artifact == path:
                return artifact
        raise ContractCompilationError(
            "missing_raw_artifact", f"Raw evidence is missing {path}"
        )

    @staticmethod
    def _nested_id(value: Any) -> str | None:
        if isinstance(value, dict) and value.get("id") is not None:
            return str(value["id"])
        if isinstance(value, (int, str)) and str(value) not in {"", "0"}:
            return str(value)
        return None

    @staticmethod
    def _trailing_policy(
        site: dict[str, Any], content: list[RawContentEvidence]
    ) -> Literal["always", "never"]:
        permalink = str(site.get("permalink_structure", ""))
        if permalink:
            return "always" if permalink.endswith("/") else "never"
        non_root = [
            item.legacy_permalink for item in content if item.legacy_permalink != "/"
        ]
        return (
            "always"
            if not non_root
            or sum(url.endswith("/") for url in non_root) * 2 >= len(non_root)
            else "never"
        )

    @staticmethod
    def _finding(
        code: str,
        severity: Literal["info", "warning", "error"],
        subject: str,
        message: str,
        evidence: EvidenceReference,
        decision_id: str | None = None,
    ) -> NormalizationFinding:
        return NormalizationFinding(
            finding_id=f"finding:{stable_hash(code, subject, evidence.evidence_id)}",
            severity=severity,
            code=code,
            message=message,
            subject_id=subject,
            evidence=(evidence,),
            decision_id=decision_id,
        )

    @staticmethod
    def _decision(
        kind: str,
        subject: str,
        prompt: str,
        options: tuple[str, ...],
        evidence: EvidenceReference,
    ) -> DecisionItem:
        return DecisionItem(
            decision_id=f"decision:{stable_hash(kind, subject)}",
            kind=kind,
            severity="blocking",
            subject_id=subject,
            prompt=prompt,
            options=options,
            evidence=(evidence,),
        )

    @staticmethod
    def _append_unique(values: list[Any], value: Any) -> None:
        identifier = getattr(value, "decision_id", None) or getattr(
            value, "finding_id", None
        )
        if not any(
            (getattr(item, "decision_id", None) or getattr(item, "finding_id", None))
            == identifier
            for item in values
        ):
            values.append(value)
