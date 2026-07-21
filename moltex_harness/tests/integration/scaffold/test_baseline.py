from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path

from moltex_harness.contracts import ContractStore
from moltex_harness.scaffold import (
    NODE_VERSION,
    NPM_VERSION,
    BaselineService,
)
from moltex_harness.visuals.service import (
    CaptureResult,
    RouteProbeResult,
    SourceVisualService,
)


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


class OmitOneRouteProbe:
    def __init__(self, source_url: str) -> None:
        self.source_url = source_url

    def probe(self, url):
        if url == self.source_url:
            return RouteProbeResult(404, url)
        return RouteProbeResult(200, url)


def _node_runtime() -> str:
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
            and subprocess.check_output([item, "--version"], text=True).strip()
            == f"v{NODE_VERSION}"
        ),
        None,
    )
    if node is None:
        raise RuntimeError(f"Node {NODE_VERSION} is required for H3 acceptance")
    return node


def _npm_runtime(node: str, root: Path) -> str:
    npm = shutil.which("npm")
    candidates = [
        os.environ.get("MOLTEX_NPM_CLI"),
        str(Path(npm).parent / "node_modules/npm/bin/npm-cli.js") if npm else None,
    ]
    for candidate in candidates:
        if (
            candidate
            and Path(candidate).is_file()
            and subprocess.check_output([node, candidate, "--version"], text=True).strip()
            == NPM_VERSION
        ):
            return candidate
    bootstrap = next(
        (candidate for candidate in candidates if candidate and Path(candidate).is_file()),
        None,
    )
    if bootstrap is None:
        raise RuntimeError("An npm CLI is required to acquire the pinned npm runtime")
    toolchain = root / "npm-toolchain"
    toolchain.mkdir(parents=True)
    subprocess.run(
        [
            node,
            bootstrap,
            "install",
            "--prefix",
            str(toolchain),
            "--no-save",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            f"npm@{NPM_VERSION}",
        ],
        check=True,
    )
    npm_cli = toolchain / "node_modules/npm/bin/npm-cli.js"
    actual = subprocess.check_output([node, npm_cli, "--version"], text=True).strip()
    if actual != NPM_VERSION:
        raise RuntimeError(f"Expected npm {NPM_VERSION}, received {actual}")
    return str(npm_cli)


def _toolchain_environment(node: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = str(Path(node).parent) + os.pathsep + environment["PATH"]
    return environment


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
    assert (output / ".node-version").read_text(encoding="utf-8").strip() == NODE_VERSION
    assert "engine-strict=true" in (output / ".npmrc").read_text(encoding="utf-8")
    assert (output / "package-lock.json").is_file()
    assert (output / "src" / "pages" / "[...path].astro").is_file()
    assert (output / "public" / "sitemap.xml").is_file()
    assert (output / ".moltex" / "receipts" / "conversion.json").is_file()
    assert (output / ".moltex" / "evidence" / "source-visuals" / "capture-receipt.json").is_file()
    page_count = len(list((output / "src" / "pages").rglob("*.astro")))
    assert page_count == 2
    routes_data = json.loads(
        (output / "src/data/routes.json").read_text(encoding="utf-8")
    )
    assert len(routes_data) == len(golden_contracts.routes)
    assert page_count < len(routes_data)
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
    stories_route = next(item for item in routes_data if item["path"] == "stories")
    for record in golden_contracts.content_records:
        if record.content_type == "post":
            assert record.record_id in stories_route["listingRecordIds"]
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

    node = _node_runtime()
    npm_cli = _npm_runtime(node, tmp_path)
    toolchain_environment = _toolchain_environment(node)
    subprocess.run(
        [node, npm_cli, "ci"],
        cwd=output,
        check=True,
        env=toolchain_environment,
    )
    subprocess.run(
        [node, npm_cli, "run", "build"],
        cwd=output,
        check=True,
        env=toolchain_environment,
    )
    verification = json.loads(
        (output / ".moltex/reports/baseline-verification-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert verification["status"] == "pass"
    assert verification["toolchain"] == {
        "node": NODE_VERSION,
        "npm": NPM_VERSION,
    }
    assert json.loads(
        (output / ".moltex/reports/toolchain.json").read_text(encoding="utf-8")
    )["node"] == NODE_VERSION
    characteristics = json.loads(
        (output / ".moltex/reports/build-characteristics.json").read_text(
            encoding="utf-8"
        )
    )
    assert characteristics["duration_ms"] > 0
    assert characteristics["source_files"] == len(actual_src)
    assert characteristics["source_bytes"] > 0
    assert characteristics["output_files"] >= len(golden_contracts.routes)
    assert characteristics["output_bytes"] > 0

    expected_statuses = {"baseline": "pass", "migration": "fail", "parity": "fail"}
    for level in ("baseline", "migration", "parity"):
        self_verification = subprocess.run(
            [node, npm_cli, "run", "verify", "--", "--level", level],
            cwd=output,
            text=True,
            capture_output=True,
            env=toolchain_environment,
        )
        assert self_verification.returncode == (0 if level == "baseline" else 1), (
            self_verification.stdout + self_verification.stderr
        )
        suite = json.loads(
            (output / f".moltex/reports/verification-{level}.json").read_text(
                encoding="utf-8"
            )
        )
        assert suite["status"] == expected_statuses[level]
        assert suite["bundle_id"] == golden_contracts.source_manifest.bundle_id
        assert all(
            item["contract_ids"] and item["evidence_refs"]
            for item in suite["checks"]
            if item["status"] != "pass"
        )
    migration_placeholders = [
        item
        for item in json.loads(
            (output / ".moltex/reports/verification-migration.json").read_text(
                encoding="utf-8"
            )
        )["checks"]
        if item["check_id"] == "content.no-unresolved-placeholder"
        and item["status"] == "fail"
    ]
    assert {item["subject"] for item in migration_placeholders} == {
        "/visit/",
        "/contact/",
    }
    migration = json.loads(
        (output / ".moltex/reports/verification-migration.json").read_text(
            encoding="utf-8"
        )
    )
    assert migration["processes"][0]["status"] == "stopped"
    assert migration["processes"][0]["host"] == "127.0.0.1"
    parity = json.loads(
        (output / ".moltex/reports/verification-parity.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(item["kind"] == "playwright-trace" for item in parity["artifacts"])
    assert any(item["kind"] == "screenshot" for item in parity["artifacts"])
    for process in migration["processes"] + parity["processes"]:
        with socket.socket() as probe:
            assert probe.connect_ex((process["host"], process["port"])) != 0

    def assert_localized(
        check_id: str,
        level: str,
        files: list[Path],
        mutate,
    ) -> None:
        originals = {
            path: path.read_bytes() if path.is_file() else None for path in files
        }
        try:
            mutate()
            failed = subprocess.run(
                [
                    node,
                    "scripts/verify.mjs",
                    "--level",
                    level,
                    "--checks",
                    check_id,
                ],
                cwd=output,
                text=True,
                capture_output=True,
                env=toolchain_environment,
            )
            assert failed.returncode != 0, failed.stdout + failed.stderr
            report = json.loads(
                (
                    output / f".moltex/reports/verification-{level}.json"
                ).read_text(encoding="utf-8")
            )
            localized = [
                item
                for item in report["checks"]
                if item["check_id"] == check_id and item["status"] != "pass"
            ]
            assert localized, report
            assert all(item["subject"] for item in localized)
            assert all(item["contract_ids"] for item in localized)
            assert all(item["evidence_refs"] for item in localized)
        finally:
            for path, data in originals.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)

    site_spec = output / ".moltex/contracts/site-spec.json"
    assert_localized(
        "contract.integrity",
        "baseline",
        [site_spec],
        lambda: site_spec.write_bytes(site_spec.read_bytes() + b" "),
    )
    route_contract = next(route for route in golden_contracts.routes if route.public)
    route_output = output / "dist" / route_contract.output_path
    assert_localized(
        "build.output-inventory",
        "baseline",
        [route_output],
        route_output.unlink,
    )
    assert_localized(
        "route.expected-output",
        "baseline",
        [route_output],
        route_output.unlink,
    )
    marker = route_contract.required_content_markers[0]
    assert_localized(
        "content.required-marker",
        "baseline",
        [route_output],
        lambda: route_output.write_text(
            route_output.read_text(encoding="utf-8").replace(marker, "marker removed"),
            encoding="utf-8",
        ),
    )
    assert_localized(
        "link.internal-target",
        "migration",
        [route_output],
        lambda: route_output.write_text(
            route_output.read_text(encoding="utf-8").replace(
                "</article>", '<a href="/missing-target/">Broken</a></article>', 1
            ),
            encoding="utf-8",
        ),
    )
    navigation_path = output / "src/data/navigation.json"

    def mutate_navigation() -> None:
        navigation = json.loads(navigation_path.read_text(encoding="utf-8"))
        navigation[0]["label"] = "Mutated label"
        navigation_path.write_text(json.dumps(navigation), encoding="utf-8")

    assert_localized(
        "navigation.contract",
        "migration",
        [navigation_path],
        mutate_navigation,
    )
    asset_contract = next(asset for asset in golden_contracts.assets if not asset.needs_decision)
    asset_output = output / "dist" / asset_contract.target_path.removeprefix("public/")
    assert_localized(
        "asset.local-exists", "baseline", [asset_output], asset_output.unlink
    )
    assert_localized(
        "asset.checksum",
        "baseline",
        [asset_output],
        lambda: asset_output.write_bytes(asset_output.read_bytes() + b"mutated"),
    )
    assert_localized(
        "asset.contract",
        "baseline",
        [route_output],
        lambda: route_output.write_text(
            route_output.read_text(encoding="utf-8").replace(
                "</article>",
                '<img src="https://old.example.test/hotlink.png" alt="Hotlink"></article>',
                1,
            ),
            encoding="utf-8",
        ),
    )
    seo_contract = next(item for item in golden_contracts.seo if item.description is not None)
    seo_route = next(
        route
        for route in golden_contracts.routes
        if route.contract_id == seo_contract.route_contract_id
    )
    seo_output = output / "dist" / seo_route.output_path
    assert_localized(
        "seo.required-title",
        "migration",
        [seo_output],
        lambda: seo_output.write_text(
            re.sub(r"<title>.*?</title>", "<title>Mutated</title>", seo_output.read_text(encoding="utf-8"), count=1),
            encoding="utf-8",
        ),
    )
    assert_localized(
        "seo.canonical",
        "migration",
        [seo_output],
        lambda: seo_output.write_text(
            re.sub(r'(<link rel="canonical" href=")[^"]*', r"\1https://wrong.invalid/", seo_output.read_text(encoding="utf-8"), count=1),
            encoding="utf-8",
        ),
    )
    assert_localized(
        "seo.description",
        "migration",
        [seo_output],
        lambda: seo_output.write_text(
            re.sub(
                r'(<meta name="description" content=")[^"]*',
                r"\1Mutated description",
                seo_output.read_text(encoding="utf-8"),
                count=1,
            ),
            encoding="utf-8",
        ),
    )
    assert_localized(
        "seo.robots",
        "migration",
        [seo_output],
        lambda: seo_output.write_text(
            re.sub(
                r'(<meta name="robots" content=")[^"]*',
                r"\1noindex,nofollow",
                seo_output.read_text(encoding="utf-8"),
                count=1,
            ),
            encoding="utf-8",
        ),
    )
    seo_contracts_path = output / ".moltex/contracts/contracts/seo.json"

    def mutate_open_graph_contract() -> None:
        contracts = json.loads(seo_contracts_path.read_text(encoding="utf-8"))
        contracts[0]["open_graph"] = {"title": "Impossible Open Graph title"}
        seo_contracts_path.write_text(json.dumps(contracts), encoding="utf-8")

    assert_localized(
        "seo.open-graph",
        "migration",
        [seo_contracts_path],
        mutate_open_graph_contract,
    )
    sitemap_path = output / "src/data/sitemap.json"

    def mutate_sitemap() -> None:
        routes = json.loads(sitemap_path.read_text(encoding="utf-8"))
        sitemap_path.write_text(json.dumps(routes[1:]), encoding="utf-8")

    assert_localized("seo.sitemap", "migration", [sitemap_path], mutate_sitemap)
    redirects_path = output / ".moltex/contracts/contracts/redirects.json"

    def mutate_redirects() -> None:
        redirects_path.write_text(
            json.dumps(
                [
                    {"contract_id": "redirect:negative:a", "source_url": "/a/", "target_url": "/b/", "needs_decision": False},
                    {"contract_id": "redirect:negative:b", "source_url": "/b/", "target_url": "/a/", "needs_decision": False},
                ]
            ),
            encoding="utf-8",
        )

    assert_localized(
        "redirect.no-loop", "migration", [redirects_path], mutate_redirects
    )
    assert_localized(
        "redirect.contract",
        "migration",
        [redirects_path],
        lambda: redirects_path.write_text(
            json.dumps(
                [
                    {
                        "contract_id": "redirect:negative:manifest",
                        "source_url": "/legacy/",
                        "target_url": route_contract.target_url,
                        "status_code": 301,
                        "needs_decision": False,
                    }
                ]
            ),
            encoding="utf-8",
        ),
    )
    capabilities_path = output / ".moltex/contracts/contracts/capabilities.json"
    assert_localized(
        "capability.disposition",
        "migration",
        [capabilities_path],
        lambda: capabilities_path.write_text(
            json.dumps(
                [
                    {
                        "capability_id": "capability:negative",
                        "disposition": "needs_decision",
                        "target_behavior": None,
                        "verification_method": None,
                    }
                ]
            ),
            encoding="utf-8",
        ),
    )
    parity_path = output / ".moltex/contracts/parity-matrix.json"

    def mutate_parity() -> None:
        rows = json.loads(parity_path.read_text(encoding="utf-8"))
        rows.append(rows[0])
        parity_path.write_text(json.dumps(rows), encoding="utf-8")

    assert_localized(
        "parity.unique-subject", "parity", [parity_path], mutate_parity
    )
    task_graph_path = output / ".moltex/tasks/task-graph.json"
    assert_localized(
        "task.completion-evidence",
        "parity",
        [task_graph_path],
        lambda: (
            task_graph_path.parent.mkdir(parents=True, exist_ok=True),
            task_graph_path.write_text(
                json.dumps(
                    {
                        "tasks": [
                            {
                                "task_id": "T003",
                                "state": "complete",
                                "contract_ids": [route_contract.contract_id],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            ),
        ),
    )
    task_graph_path.parent.mkdir(parents=True, exist_ok=True)
    task_graph_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "T002",
                        "state": "pending",
                        "dependencies": [],
                        "contract_ids": [route_contract.contract_id],
                    },
                    {
                        "task_id": "T003",
                        "state": "pending",
                        "dependencies": ["T002"],
                        "contract_ids": [route_contract.contract_id],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    dependency_failure = subprocess.run(
        [node, "scripts/verify-task.mjs", "T003"],
        cwd=output,
        text=True,
        capture_output=True,
        env=toolchain_environment,
    )
    assert dependency_failure.returncode != 0
    dependency_report = json.loads(
        (output / ".moltex/reports/tasks/T003.json").read_text(encoding="utf-8")
    )
    dependency_finding = next(
        item
        for item in dependency_report["checks"]
        if item["check_id"] == "task.dependencies"
    )
    assert dependency_finding["status"] == "blocked"
    assert dependency_finding["contract_ids"]
    assert dependency_finding["evidence_refs"]
    task_graph_path.unlink()
    missing_slug = re.sub(
        r"[^a-z0-9]",
        "",
        golden_contracts.source_manifest.bundle_id,
        flags=re.IGNORECASE,
    )[:12]
    soft_404 = output / "dist" / f"__moltex_missing_{missing_slug}" / "index.html"
    assert_localized(
        "http.not-found",
        "migration",
        [soft_404],
        lambda: (
            soft_404.parent.mkdir(parents=True, exist_ok=True),
            soft_404.write_text("<h1>Soft 404</h1>", encoding="utf-8"),
        ),
    )
    assert_localized(
        "http.route-status",
        "migration",
        [route_output],
        route_output.unlink,
    )
    routes_path = output / ".moltex/contracts/contracts/routes.json"

    def mutate_route_content_type() -> None:
        routes = json.loads(routes_path.read_text(encoding="utf-8"))
        routes[0]["target_url"] = "/" + asset_contract.target_path.removeprefix(
            "public/"
        )
        routes_path.write_text(json.dumps(routes), encoding="utf-8")

    assert_localized(
        "http.content-type",
        "migration",
        [routes_path],
        mutate_route_content_type,
    )
    task_failure = subprocess.run(
        [node, "scripts/verify-task.mjs", "T003"],
        cwd=output,
        text=True,
        capture_output=True,
        env=toolchain_environment,
    )
    assert task_failure.returncode != 0
    assert "task.exists" in (
        output / ".moltex/reports/tasks/T003.json"
    ).read_text(encoding="utf-8")
    assert_localized(
        "browser.console",
        "parity",
        [route_output],
        lambda: route_output.write_text(
            route_output.read_text(encoding="utf-8").replace(
                "</body>", '<script>console.error("mutation")</script></body>', 1
            ),
            encoding="utf-8",
        ),
    )
    assert_localized(
        "a11y.accessible-name",
        "parity",
        [route_output],
        lambda: route_output.write_text(
            route_output.read_text(encoding="utf-8").replace(
                "</article>", '<img src="/media/does-not-matter.png"></article>', 1
            ),
            encoding="utf-8",
        ),
    )
    assert_localized(
        "a11y.landmarks",
        "parity",
        [route_output],
        lambda: route_output.write_text(
            route_output.read_text(encoding="utf-8")
            .replace("<main", "<div", 1)
            .replace("</main>", "</div>", 1),
            encoding="utf-8",
        ),
    )

    receipt_path = output / ".moltex/evidence/source-visuals/capture-receipt.json"
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    removed = receipt["evidence"].pop()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    visual_path = output / ".moltex/evidence/source-visuals" / removed["artifact"]
    visual_bytes = visual_path.read_bytes()
    visual_path.unlink()
    failed_visual = subprocess.run(
        [node, npm_cli, "run", "verify:baseline"],
        cwd=output,
        text=True,
        capture_output=True,
        env=toolchain_environment,
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
        [node, npm_cli, "run", "verify:baseline"],
        cwd=output,
        text=True,
        capture_output=True,
        env=toolchain_environment,
    )
    assert failed_body.returncode != 0
    assert f"missing body marker {route['id']}" in failed_body.stderr

    unpinned = subprocess.run(
        [node, "scripts/build.mjs"],
        cwd=output,
        text=True,
        capture_output=True,
    )
    assert unpinned.returncode != 0
    assert "npm 10.9.2" in unpinned.stderr


def test_unavailable_route_and_content_are_excluded_from_baseline(
    golden_contracts, capture_png, samples_dir, tmp_path
) -> None:
    contracts_dir = tmp_path / "contracts"
    ContractStore().write(contracts_dir, golden_contracts)
    omitted_target = next(
        target
        for target in golden_contracts.visual_capture_plan.targets
        if target.route_family == "post"
    )
    omitted_route = next(
        route
        for route in golden_contracts.routes
        if route.contract_id == omitted_target.route_contract_id
    )
    visuals = tmp_path / "visuals"
    SourceVisualService().capture(
        contracts_dir,
        visuals,
        FrozenCapture(capture_png),
        OmitOneRouteProbe(omitted_target.source_url),
    )
    output = tmp_path / "site"

    outcome = BaselineService().compile_archive(
        samples_dir / "golden-export.zip", output, visuals
    )

    assert outcome.exit_code == 0
    assert outcome.report.counts["omitted_routes"] == 1
    generated_routes = json.loads(
        (output / "src/data/routes.json").read_text(encoding="utf-8")
    )
    assert omitted_route.contract_id not in {
        route["routeId"] for route in generated_routes
    }
    assert not (
        output
        / "src/content/records"
        / f"{omitted_route.content_record_id.replace(':', '-')}.json"
    ).exists()
    expectations = json.loads(
        (output / ".moltex/verification/baseline-expectations.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["route_contract_id"] for item in expectations["omittedRoutes"]] == [
        omitted_route.contract_id
    ]
