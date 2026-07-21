from __future__ import annotations

from types import SimpleNamespace

import pytest

from moltex_harness.intake.adapters.common import _validate_legacy_payload
from moltex_harness.intake.errors import IntakeError
from moltex_harness.models import LegacyPayloadEvidence


class _Bundle:
    def __init__(self) -> None:
        self.items = {
            "legacy/tables/payload.json": SimpleNamespace(
                bytes=12, sha256="a" * 64
            )
        }

    def has(self, path: str) -> bool:
        return path in self.items

    def item(self, path: str):
        return self.items[path]


def test_legacy_payload_acquisition_consistency() -> None:
    bundle = _Bundle()
    included = LegacyPayloadEvidence(
        status="included",
        method="bundle",
        artifact="legacy/tables/payload.json",
        row_count=1,
        bytes=12,
        sha256="a" * 64,
        reason="Reachable public row",
    )
    _validate_legacy_payload(
        bundle, "legacy_evidence_index.json", "/entries/0", included  # type: ignore[arg-type]
    )

    invalid = (
        included.model_copy(update={"artifact": None}),
        included.model_copy(
            update={"status": "deferred", "method": "targeted-export"}
        ),
        included.model_copy(update={"status": "omitted", "method": "none"}),
        included.model_copy(update={"sha256": "b" * 64}),
    )
    for payload in invalid:
        with pytest.raises(IntakeError):
            _validate_legacy_payload(
                bundle,  # type: ignore[arg-type]
                "legacy_evidence_index.json",
                "/entries/0",
                payload,
            )
