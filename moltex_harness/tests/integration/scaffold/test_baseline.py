from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from moltex_harness.contracts import ContractStore
from moltex_harness.scaffold import BaselineService
from moltex_harness.visuals.service import CaptureResult, SourceVisualService


class FrozenCapture:
    def __init__(self, render) -> None:
        self.render = render

    def capture(self, target):
        return CaptureResult(
            self.render(target.viewport.width, target.viewport.height),
            target.source_url,
            "frozen-chromium",
            "1.0",
        )


def _node_runtime() -> tuple[str, str]:
    candidates = [
        os.environ.get("MOLTEX_NODE"),
        shutil.which("node"),
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
        ),
    ]
    node = next(
        (
            item
            for item in candidates
            if item
            and Path(item).is_file()
            and int(
                subprocess.check_output([item, "--version"], text=True)
                .strip()
                .lstrip("v")
                .split(".")[0]
            )
            >= 22
        ),
        None,
    )
    npm = shutil.which("npm")
    npm_cli = (
        Path(npm).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if npm
        else Path()
    )
    if node is None or not npm_cli.is_file():
        raise RuntimeError("Node 22+ and the npm CLI are required for H3 acceptance")
    return node, str(npm_cli)


def test_golden_export_compiles_complete_astro_baseline(
    golden_contracts, capture_png, samples_dir, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    visuals = tmp_path / "visuals"
    source_receipt = SourceVisualService().capture(
        contracts_dir, visuals, FrozenCapture(capture_png)
    )
    reviewed_visuals = json.loads(
        (
            samples_dir.parent
            / "moltex_harness/tests/fixtures/golden_h3_visuals.json"
        ).read_text(encoding="utf-8")
    )
    for evidence in source_receipt.evidence:
        expected_visual = reviewed_visuals[evidence.viewport_name]
        assert evidence.bytes == expected_visual["bytes"]
        assert evidence.sha256 == expected_visual["sha256"]
    output = tmp_path / "site"

    outcome = BaselineService().compile_archive(
        samples_dir / "golden-export.zip", output, visuals
    )

    assert outcome.exit_code == 0
    assert (output / "package-lock.json").is_file()
    assert (output / "src" / "pages" / "index.astro").is_file()
    assert (output / "public" / "sitemap.xml").is_file()
    assert (output / ".moltex" / "receipts" / "conversion.json").is_file()
    assert (output / ".moltex" / "evidence" / "source-visuals" / "capture-receipt.json").is_file()
    page_count = len(list((output / "src" / "pages").rglob("*.astro")))
    assert page_count >= len(golden_contracts.routes)
    expected = json.loads(
        (samples_dir.parent / "moltex_harness" / "tests" / "fixtures" / "golden_h3_workspace.json").read_text(
            encoding="utf-8"
        )
    )
    actual_src = sorted(
        path.relative_to(output).as_posix()
        for path in (output / "src").rglob("*")
        if path.is_file()
    )
    actual_public = sorted(
        path.relative_to(output).as_posix()
        for path in (output / "public").rglob("*")
        if path.is_file()
    )
    assert actual_src == expected["src"]
    assert actual_public == expected["public"]

    navigation = json.loads(
        (output / "src/data/navigation.json").read_text(encoding="utf-8")
    )
    stories_navigation = next(item for item in navigation if item["label"] == "Stories")
    assert [item["label"] for item in stories_navigation["children"]] == [
        "Autumn workshops",
        "Shoreline notes",
        "Community suppers",
    ]
    stories_page = (output / "src/pages/stories/index.astro").read_text(
        encoding="utf-8"
    )
    for record in golden_contracts.content_records:
        if record.content_type == "post":
            assert record.title in stories_page
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (output / "src/content/records").glob("*.json")
    ]
    assert all(
        item["seo"].get("structured_data_hints") is not None
        for item in records
        if item["seo"]
    )
    assert all(
        media["src"].startswith("/media/")
        for item in records
        for media in item["media"]
    )

    repeated = tmp_path / "site-repeated"
    repeated_outcome = BaselineService().compile_archive(
        samples_dir / "golden-export.zip", repeated, visuals
    )
    assert repeated_outcome.exit_code == 0
    original_files = {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }
    repeated_files = {
        path.relative_to(repeated).as_posix(): path.read_bytes()
        for path in repeated.rglob("*")
        if path.is_file()
    }
    assert repeated_files == original_files

    node, npm_cli = _node_runtime()
    subprocess.run([node, npm_cli, "ci"], cwd=output, check=True)
    subprocess.run([node, "scripts/build.mjs"], cwd=output, check=True)
    verification = json.loads(
        (output / ".moltex/reports/baseline-verification-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert verification["status"] == "pass"

    receipt_path = output / ".moltex/evidence/source-visuals/capture-receipt.json"
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    removed = receipt["evidence"].pop()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    visual_path = output / ".moltex/evidence/source-visuals" / removed["artifact"]
    visual_bytes = visual_path.read_bytes()
    visual_path.unlink()
    failed_visual = subprocess.run(
        [node, "scripts/verify-baseline.mjs"],
        cwd=output,
        text=True,
        capture_output=True,
    )
    assert failed_visual.returncode != 0
    assert "visual receipt target count mismatch" in failed_visual.stderr
    receipt_path.write_bytes(receipt_bytes)
    visual_path.write_bytes(visual_bytes)

    expectations = json.loads(
        (output / ".moltex/verification/baseline-expectations.json").read_text(
            encoding="utf-8"
        )
    )
    route = next(item for item in expectations["routes"] if item["bodyMarkers"])
    built_page = output / "dist" / route["output"]
    rendered = built_page.read_text(encoding="utf-8")
    built_page.write_text(
        re.sub(
            r"<article\b[^>]*>[\s\S]*?</article>",
            '<article data-record-id="mutated">Body removed</article>',
            rendered,
            count=1,
        ),
        encoding="utf-8",
    )
    failed_body = subprocess.run(
        [node, "scripts/verify-baseline.mjs"],
        cwd=output,
        text=True,
        capture_output=True,
    )
    assert failed_body.returncode != 0
    assert f"missing body marker {route['id']}" in failed_body.stderr
