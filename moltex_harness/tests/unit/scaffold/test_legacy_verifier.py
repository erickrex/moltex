from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from moltex_harness.scaffold import NODE_VERSION


def _node_runtime() -> str:
    candidates = (
        os.environ.get("MOLTEX_NODE"),
        shutil.which("node"),
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
        ),
    )
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        actual = subprocess.check_output([candidate, "--version"], text=True).strip()
        if actual == f"v{NODE_VERSION}":
            return candidate
    raise RuntimeError(f"Node {NODE_VERSION} is required for verifier acceptance")


def _run_legacy_checks(tmp_path: Path, html: str) -> list[dict[str, object]]:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(html, encoding="utf-8")
    module = (
        Path(__file__).parents[3]
        / "src/moltex_harness/scaffold/templates/verify-lib/checks/static.mjs"
    ).resolve()
    contracts = {
        "capabilities": [{"capability_id": "capability:legacy:shortcode:test"}],
        "decisions": [{"decision_id": "decision:legacy:test"}],
        "legacyEvidence": [
            {
                "contract_id": "legacy-contract:test",
                "source_evidence_id": "legacy:shortcode:test",
                "artifact_type": "shortcode",
                "classification": "referenced_orphan",
                "disposition": "decide",
                "payload_status": "omitted",
                "payload_artifact": None,
                "capability_id": "capability:legacy:shortcode:test",
                "decision_id": "decision:legacy:test",
            }
        ],
    }
    script = (
        f'import {{ legacyEvidenceChecks }} from {json.dumps(module.as_uri())};'
        f"console.log(JSON.stringify(legacyEvidenceChecks({json.dumps(contracts)})));"
    )
    completed = subprocess.run(
        [_node_runtime(), "--input-type=module", "--eval", script],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)
    assert isinstance(result, list)
    return result


def test_legacy_verifier_accepts_localized_placeholder(tmp_path: Path) -> None:
    checks = _run_legacy_checks(
        tmp_path,
        '<div data-moltex-evidence="legacy:shortcode:test">Replacement required</div>',
    )

    assert [(item["check_id"], item["status"]) for item in checks] == [
        ("legacy.evidence-disposition", "pass"),
        ("legacy.placeholder", "pass"),
    ]


def test_legacy_verifier_localizes_missing_placeholder_mutation(tmp_path: Path) -> None:
    checks = _run_legacy_checks(tmp_path, "<div>Placeholder marker removed</div>")
    placeholder = next(
        item for item in checks if item["check_id"] == "legacy.placeholder"
    )

    assert placeholder["status"] == "fail"
    assert placeholder["subject"] == "legacy-contract:test"
    assert placeholder["contract_ids"] == [
        "capability:legacy:shortcode:test",
        "legacy-contract:test",
    ]
