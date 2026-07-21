from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from jsonschema import Draft202012Validator

from moltex_harness.scaffold import NODE_VERSION


TEMPLATES = Path(__file__).parents[3] / "src/moltex_harness/scaffold/templates"


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
        if (
            candidate
            and Path(candidate).is_file()
            and subprocess.check_output(
                [candidate, "--version"], text=True
            ).strip()
            == f"v{NODE_VERSION}"
        ):
            return candidate
    raise RuntimeError(f"Node {NODE_VERSION} is required for H5 tests")


def test_h5_verifier_is_packaged_and_self_contained() -> None:
    package = json.loads((TEMPLATES / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"] == {
        "postinstall": "playwright install chromium",
        "dev": "astro dev",
        "build": "node scripts/build.mjs",
        "verify": "node scripts/verify.mjs",
        "verify:baseline": "node scripts/verify-baseline.mjs",
        "verify:parity": "node scripts/verify.mjs --level parity",
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


def test_h5_checks_only_published_routes_and_materialized_assets(
    tmp_path: Path,
) -> None:
    contract_root = tmp_path / ".moltex/contracts"
    (contract_root / "contracts").mkdir(parents=True)
    (tmp_path / ".moltex/verification").mkdir(parents=True)
    (tmp_path / "src/data").mkdir(parents=True)
    (tmp_path / "dist").mkdir()
    live_route = {
        "contract_id": "route:live",
        "target_url": "/",
        "output_path": "index.html",
        "expected_status": 200,
        "public": True,
        "required_content_markers": ["Live"],
    }
    omitted_route = {
        "contract_id": "route:omitted",
        "target_url": "/omitted/",
        "output_path": "omitted/index.html",
        "expected_status": 200,
        "public": True,
        "required_content_markers": ["Omitted"],
    }
    seo = [
        {
            "schema_version": 1,
            "contract_id": "seo:live",
            "route_contract_id": "route:live",
            "target_route": "/",
            "title": "Live",
            "description": None,
            "canonical_url": "https://example.test/",
            "robots": "index,follow",
            "open_graph": {},
        },
        {
            "schema_version": 1,
            "contract_id": "seo:omitted",
            "route_contract_id": "route:omitted",
            "target_route": "/omitted/",
            "title": "Omitted",
            "description": None,
            "canonical_url": "https://example.test/omitted/",
            "robots": "index,follow",
            "open_graph": {},
        },
    ]
    documents = {
        "contract-index.json": {"bundle_id": "bundle:test", "files": []},
        "source-manifest.json": {
            "bundle_id": "bundle:test",
            "manifest_id": "manifest:test",
        },
        "site-spec.json": {"global_navigation": [], "capability_ids": []},
        "contracts/routes.json": [live_route, omitted_route],
        "contracts/assets.json": [
            {
                "asset_id": "asset:deferred",
                "target_path": "public/media/deferred.jpg",
                "needs_decision": False,
                "checksum": None,
                "mime_type": "image/jpeg",
            }
        ],
        "contracts/seo.json": seo,
        "contracts/redirects.json": [],
        "contracts/capabilities.json": [],
        "parity-matrix.json": [],
    }
    for relative, value in documents.items():
        path = contract_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
    (tmp_path / ".moltex/verification/baseline-expectations.json").write_text(
        json.dumps(
            {
                "bundleId": "bundle:test",
                "routes": [
                    {"id": "route:live", "output": "index.html", "markers": ["Live"]}
                ],
                "assets": [],
                "omittedRoutes": [
                    {"route_contract_id": "route:omitted", "reason": "http_404"}
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "src/data/sitemap.json").write_text('["/"]', encoding="utf-8")
    (tmp_path / "dist/sitemap.xml").write_text("<loc>/</loc>", encoding="utf-8")
    (tmp_path / "dist/index.html").write_text(
        '<html><head><title>Live</title><link rel="canonical" '
        'href="https://example.test/"><meta name="robots" '
        'content="index,follow"></head><body><article>Live<a href="#">'
        "Placeholder</a></article></body></html>",
        encoding="utf-8",
    )
    contracts_module = (TEMPLATES / "verify-lib/contracts.mjs").as_uri()
    checks_module = (TEMPLATES / "verify-lib/checks/static.mjs").as_uri()
    script = (
        f'import {{ loadContracts }} from "{contracts_module}";'
        f'import {{ routeAndContentChecks, assetChecks, linkChecks, seoChecks }} '
        f'from "{checks_module}";'
        "const contracts=loadContracts();"
        "const checks=[...routeAndContentChecks(contracts),...assetChecks(contracts),"
        "...linkChecks(contracts),...seoChecks(contracts)];"
        "console.log(JSON.stringify({"
        "routes:contracts.publishedRoutes.map(item=>item.contract_id),"
        "assets:contracts.publishedAssets.map(item=>item.asset_id),"
        "failures:checks.filter(item=>![\"pass\",\"review\"].includes(item.status))}));"
    )

    completed = subprocess.run(
        [_node_runtime(), "--input-type=module", "--eval", script],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result == {"routes": ["route:live"], "assets": [], "failures": []}
