from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


TEMPLATES = Path(__file__).parents[3] / "src/moltex_harness/scaffold/templates"


def test_h5_verifier_is_packaged_and_self_contained() -> None:
    package = json.loads((TEMPLATES / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"] == {
        "postinstall": "playwright install chromium",
        "dev": "astro dev",
        "build": "node scripts/build.mjs",
        "verify": "node scripts/verify.mjs",
        "verify:baseline": "node scripts/verify-baseline.mjs",
        "verify:task": "node scripts/verify-task.mjs",
    }
    verifier_files = [
        TEMPLATES / "verify.mjs",
        TEMPLATES / "verify-task.mjs",
        *sorted((TEMPLATES / "verify-lib").rglob("*.mjs")),
    ]
    assert len(verifier_files) >= 8
    source = "\n".join(path.read_text(encoding="utf-8") for path in verifier_files)
    assert "moltex_harness" not in source
    assert "openai" not in source.lower()
    assert "wordpress" not in source.lower()
    assert "127.0.0.1" in source


def test_h5_report_schemas_are_valid_draft_2020_12() -> None:
    schemas = sorted((TEMPLATES / "verifier-schemas").glob("*.json"))

    assert {path.name for path in schemas} == {
        "artifact.schema.json",
        "check-result.schema.json",
        "finding.schema.json",
        "process-result.schema.json",
        "suite-report.schema.json",
    }
    for path in schemas:
        Draft202012Validator.check_schema(
            json.loads(path.read_text(encoding="utf-8"))
        )
