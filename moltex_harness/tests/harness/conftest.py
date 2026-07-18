from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def synthetic_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "site"
    files: dict[str, object] = {
        ".moltex/contracts/contracts/routes.json": [
            {
                "contract_id": "route:page:42",
                "target_url": "/about/",
                "output_path": "about/index.html",
                "public": True,
                "required_content_markers": ["About Moltex"],
            }
        ],
        ".moltex/verification/baseline-expectations.json": {
            "routes": [
                {
                    "id": "route:page:42",
                    "output": "about/index.html",
                    "markers": ["About Moltex"],
                }
            ]
        },
        ".moltex/contracts/contracts/assets.json": [
            {
                "asset_id": "asset:logo",
                "target_path": "public/media/logo.png",
                "needs_decision": False,
            }
        ],
        "src/data/navigation.json": [
            {"id": "nav:about", "label": "About", "href": "/about/", "children": []}
        ],
        ".moltex/contracts/contracts/seo.json": [
            {
                "contract_id": "seo:page:42",
                "route_contract_id": "route:page:42",
            }
        ],
        ".moltex/contracts/contracts/redirects.json": [],
        ".moltex/contracts/contracts/capabilities.json": [
            {
                "capability_id": "capability:forms",
                "business_critical": True,
            }
        ],
        ".moltex/contracts/parity-matrix.json": [
            {"row_id": "parity:route:42", "subject_type": "route", "subject_id": "42"}
        ],
        ".moltex/parity-matrix.json": {
            "rows": [
                {
                    "row_id": "parity:route:42",
                    "subject_type": "route",
                    "subject_id": "42",
                }
            ]
        },
        ".moltex/tasks/task-graph.json": {
            "tasks": [
                {
                    "task_id": "T001",
                    "state": "ready",
                    "contract_ids": ["route:page:42"],
                }
            ]
        },
    }
    for relative, value in files.items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
    page = workspace / "dist/about/index.html"
    page.parent.mkdir(parents=True)
    page.write_text(
        '<html><head><title>About Moltex</title><link rel="canonical" '
        'href="https://example.test/about/"></head><body><nav aria-label="Primary">'
        '<a href="/about/">About</a></nav><article>About Moltex</article></body></html>',
        encoding="utf-8",
    )
    asset = workspace / "dist/media/logo.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"png")
    return workspace
