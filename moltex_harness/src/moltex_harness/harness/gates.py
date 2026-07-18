"""H6 gates compare H5 findings with declared expectations only."""

from __future__ import annotations

from typing import Any

from .models import MutationDefinition, MutationReceipt


BLOCKING_STATUSES = {"fail", "blocked", "needs_decision", "error"}


class GateEvaluator:
    @staticmethod
    def clean(report: dict[str, Any]) -> tuple[bool, str]:
        blocking = [
            item
            for item in report["checks"]
            if item["status"] in BLOCKING_STATUSES
        ]
        if report["status"] not in {"pass", "review"} or blocking:
            ids = sorted({item["check_id"] for item in blocking})
            return False, f"Clean verifier has blocking findings: {ids}"
        return True, "Clean verifier has no blocking findings"

    @staticmethod
    def mutation(
        report: dict[str, Any],
        definition: MutationDefinition,
        receipt: MutationReceipt,
    ) -> tuple[bool, bool, bool, dict[str, Any] | None, tuple[str, ...]]:
        failures = [
            item
            for item in report["checks"]
            if item["status"] in BLOCKING_STATUSES
        ]
        primary = next(
            (
                item
                for item in failures
                if item["check_id"] == definition.check_id
                and item["status"] != "error"
            ),
            None,
        )
        detected = primary is not None
        localized = bool(
            primary
            and (
                primary["subject"] == receipt.subject
                or primary["subject"].startswith(receipt.subject)
                or receipt.subject.startswith(primary["subject"])
            )
            and set(primary["contract_ids"]) & set(receipt.contract_ids)
            and primary["evidence_refs"]
        )
        allowed = {definition.check_id, *definition.allowed_cascades}
        unexpected = tuple(
            sorted({item["check_id"] for item in failures if item["check_id"] not in allowed})
        )
        specific = not unexpected
        return detected, localized, specific, primary, unexpected
