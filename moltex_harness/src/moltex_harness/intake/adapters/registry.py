"""Deterministic export adapter selection."""

from __future__ import annotations

from ..archive import SafeArchive
from ..errors import UnsupportedExportError
from .base import ExportAdapter
from .legacy_1 import LEGACY_REQUIRED, Legacy1Adapter
from .moltex_export_1 import MoltexExport1Adapter


def select_adapter(bundle: SafeArchive) -> ExportAdapter:
    if bundle.has("bundle.json"):
        manifest = bundle.read_json("bundle.json")
        if isinstance(manifest, dict) and manifest.get("schema") == "moltex-export/1":
            return MoltexExport1Adapter()
        raise UnsupportedExportError(
            "unsupported_export",
            "No adapter supports the bundle manifest schema",
            artifact="bundle.json",
            pointer="/schema",
        )
    if all(bundle.has(path) for path in LEGACY_REQUIRED):
        return Legacy1Adapter()
    raise UnsupportedExportError(
        "unsupported_export",
        "Archive is neither a supported legacy export nor moltex-export/1",
    )
