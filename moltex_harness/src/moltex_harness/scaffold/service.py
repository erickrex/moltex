"""Compile an accepted bundle and source evidence into an Astro 5 baseline."""

from __future__ import annotations

import json
import html
import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from moltex_harness.contracts import CompilationService, ContractStore, ContractVerifier
from moltex_harness.conversion import (
    ContentConverter,
    FrontmatterNormalizer,
    UrlRewriter,
    classify_failure,
)
from moltex_harness.intake.archive import ArchiveLimits, SafeArchive
from moltex_harness.intake.serialization import deterministic_json, write_json
from moltex_harness.models import BaselineCompilationReport
from moltex_harness.visuals import CaptureBackend, SourceVisualService

from .media import AssetMaterializer, MediaFetcher


TEMPLATES = Path(__file__).parent / "templates"
FailureClassification = Literal["permanent", "blocked", "transient", "harness"]


@dataclass(frozen=True, slots=True)
class BaselineOutcome:
    report: BaselineCompilationReport
    exit_code: int


class BaselineService:
    def __init__(
        self,
        *,
        media_fetcher: MediaFetcher | None = None,
        capture_backend: CaptureBackend | None = None,
    ) -> None:
        self.media_fetcher = media_fetcher
        self.capture_backend = capture_backend

    def compile_archive(
        self,
        archive: Path,
        output: Path,
        source_visuals: Path | None = None,
    ) -> BaselineOutcome:
        if output.exists() and any(output.iterdir()):
            return self._failure(output, None, "output_not_empty", "Baseline output directory must be empty")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="moltex-h3-") as temporary:
            root = Path(temporary)
            contracts_dir = root / "contracts"
            h2 = CompilationService().compile_archive(archive, contracts_dir)
            if h2.exit_code:
                return self._failure(output, h2.report.get("bundle_id"), "h2_failed", h2.report["message"])
            verification = ContractVerifier().verify(contracts_dir)
            if verification.status != "pass":
                return self._failure(output, verification.bundle_id, "h2_verification_failed", verification.errors[0])
            contracts, _ = ContractStore().load(contracts_dir)
            workspace = root / "workspace"
            try:
                workspace.mkdir(parents=True)
                shutil.copytree(contracts_dir, workspace / ".moltex" / "contracts")
                visual_destination = workspace / ".moltex" / "evidence" / "source-visuals"
                visuals = SourceVisualService()
                if source_visuals is None:
                    captured = root / "source-visuals"
                    visuals.capture(contracts_dir, captured, self.capture_backend)
                    source_visuals = captured
                visual_receipt = visuals.verify_and_copy(
                    contracts_dir, source_visuals, visual_destination
                )
                extraction = root / "bundle"
                safe_archive = SafeArchive(archive, extraction, ArchiveLimits())
                safe_archive.prepare()
                receipts = AssetMaterializer(self.media_fetcher).materialize(
                    contracts.assets, extraction, workspace
                )
                write_json(workspace / ".moltex" / "receipts" / "assets.json", receipts)
                conversion_receipts = self._generate(workspace, contracts)
                self._write_expectations(
                    workspace,
                    contracts,
                    receipts,
                    conversion_receipts,
                    visual_receipt,
                )
            except Exception as error:
                classification: FailureClassification = classify_failure(error).value
                return self._failure(
                    output,
                    contracts.source_manifest.bundle_id,
                    f"baseline_{classification}",
                    str(error),
                    classification,
                )
            if output.exists():
                output.rmdir()
            shutil.move(str(workspace), output)
        report = BaselineCompilationReport(
            status="compiled",
            bundle_id=contracts.source_manifest.bundle_id,
            code="baseline_compiled",
            message="H3 Astro baseline compiled successfully",
            counts={
                "content": len(contracts.content_records),
                "routes": len(contracts.routes),
                "assets": len(receipts),
                "visuals": len(contracts.visual_capture_plan.targets),
            },
            outputs={
                "workspace": ".",
                "conversion_receipts": ".moltex/receipts/conversion.json",
                "asset_receipts": ".moltex/receipts/assets.json",
                "source_visuals": ".moltex/evidence/source-visuals/capture-receipt.json",
            },
        )
        write_json(output / ".moltex" / "reports" / "baseline-compilation-report.json", report)
        return BaselineOutcome(report, 0)

    def _generate(self, workspace: Path, contracts: Any) -> tuple[Any, ...]:
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / "package.json", workspace / "package.json")
        shutil.copyfile(TEMPLATES / "package-lock.json", workspace / "package-lock.json")
        (workspace / "astro.config.mjs").write_text(
            "import { defineConfig } from 'astro/config';\nexport default defineConfig({ output: 'static', trailingSlash: 'always' });\n",
            encoding="utf-8",
        )
        write_json(
            workspace / "tsconfig.json",
            {"extends": "astro/tsconfigs/strict", "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}},
        )
        routes_by_id = {route.contract_id: route for route in contracts.routes}
        seo_by_route = {item.route_contract_id: item for item in contracts.seo}
        url_map = {entry.source_url: entry.target_url for entry in contracts.url_map}
        media_map = {entry.source_url: entry.target_url for entry in contracts.media_map}
        assets_by_id = {asset.asset_id: asset for asset in contracts.assets}
        converter = ContentConverter(UrlRewriter(contracts.site_spec.source_origin, url_map, media_map))
        frontmatter = FrontmatterNormalizer()
        content_by_id: dict[str, dict[str, Any]] = {}
        receipts = []
        for record in contracts.content_records:
            receipt = converter.convert(record)
            if any(finding.severity == "error" for finding in receipt.findings):
                raise ValueError(f"Unsafe content conversion: {record.record_id}")
            receipts.append(receipt)
            route = next((item for item in contracts.routes if item.content_record_id == record.record_id), None)
            seo = seo_by_route.get(route.contract_id) if route else None
            document = {
                **frontmatter.normalize(record, seo),
                "targetUrl": route.target_url if route else None,
                "excerpt": self._excerpt(receipt.sanitized_html),
                "media": [
                    {
                        "assetId": asset.asset_id,
                        "src": "/" + asset.target_path.removeprefix("public/").lstrip("/"),
                        "alt": asset.alt_text or "",
                        "mimeType": asset.mime_type,
                    }
                    for asset_id in record.required_media_ids
                    if (asset := assets_by_id.get(asset_id)) is not None
                    and not asset.needs_decision
                ],
                "bodyFormat": receipt.body_format,
                "body": receipt.editable_body,
                "renderedHtml": receipt.sanitized_html,
            }
            content_by_id[record.record_id] = document
            safe_name = record.record_id.replace(":", "-") + ".json"
            write_json(workspace / "src" / "content" / "records" / safe_name, document)
        write_json(workspace / ".moltex" / "receipts" / "conversion.json", receipts)
        self._write_shell(workspace, contracts.site_spec.site_name)
        self._write_navigation(workspace, contracts, routes_by_id)
        posts = [item for item in content_by_id.values() if item["contentType"] == "post"]
        geodirectory = [
            item for item in content_by_id.values() if item["contentType"].startswith("gd_")
        ]
        for route in contracts.routes:
            document = content_by_id.get(route.content_record_id or "", {
                "recordId": route.contract_id,
                "title": route.page_family.replace("_", " ").title(),
                "renderedHtml": "<p>This route requires a target implementation.</p>",
                "seo": {},
            })
            listing_items: list[dict[str, Any]] = []
            if route.page_family == "listing":
                listing_items = posts
            route_receipt = next(
                (
                    item
                    for item in receipts
                    if item.record_id == (route.content_record_id or "")
                ),
                None,
            )
            if route_receipt and any(
                disposition.name in {"gd_listings", "gd_loop", "gd_search"}
                for disposition in route_receipt.shortcodes
            ):
                listing_items = geodirectory
            self._write_page(workspace, route.output_path, document, listing_items)
        if not (workspace / "src" / "pages" / "404.astro").exists():
            self._write_page(
                workspace,
                "404.html",
                {"recordId": "system:404", "title": "Page not found", "renderedHtml": "<p>The requested page could not be found.</p>", "seo": {"robots": "noindex"}},
            )
        self._write_metadata(workspace, contracts)
        self._write_scripts(workspace)
        return tuple(receipts)

    @staticmethod
    def _write_shell(workspace: Path, site_name: str) -> None:
        component = workspace / "src" / "components" / "NavigationList.astro"
        component.parent.mkdir(parents=True, exist_ok=True)
        component.write_text(
            "---\nconst { items = [] } = Astro.props;\n---\n"
            '<ul>{items.map((item) => <li><a href={item.href}>{item.label}</a>'
            "{item.children?.length ? <Astro.self items={item.children} /> : null}</li>)}</ul>\n",
            encoding="utf-8",
        )
        layout = workspace / "src" / "layouts" / "BaseLayout.astro"
        layout.parent.mkdir(parents=True, exist_ok=True)
        layout.write_text(
            "---\nimport nav from '../data/navigation.json';\nimport NavigationList from '../components/NavigationList.astro';\n"
            "const { title, description = '', canonical = '', robots = 'index,follow', openGraph = {}, structuredDataHints = [] } = Astro.props;\n"
            "const ogItems = Array.isArray(openGraph.items) ? openGraph.items : [openGraph];\n"
            "const ogEntries = ogItems.flatMap((item) => item && (item.property || item.name || item.key) ? [[item.property || item.name || item.key, item.content ?? item.value ?? '']] : Object.entries(item ?? {}).filter(([key]) => key !== 'items'));\n---\n"
            "<!doctype html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            "<meta name=\"description\" content={description}><meta name=\"robots\" content={robots}><link rel=\"canonical\" href={canonical}>"
            "{ogEntries.map(([property, content]) => <meta property={String(property).startsWith('og:') ? String(property) : `og:${property}`} content={String(content)} />)}"
            "{structuredDataHints.map((hint) => <meta name=\"moltex:structured-data-hint\" content={hint} />)}<title>{title}</title></head>"
            f"<body><a class=\"skip\" href=\"#content\">Skip to content</a><header><a href=\"/\">{site_name}</a><nav aria-label=\"Primary\"><NavigationList items={{nav}} /></nav></header>"
            "<main id=\"content\"><slot /></main><footer>Generated by Moltex</footer></body></html>"
            "<style is:global>:root{font-family:system-ui,sans-serif;color:#17202a}body{margin:0}header,main,footer{max-width:72rem;margin:auto;padding:1rem}nav>ul{display:flex;gap:1rem}nav ul{list-style:none;padding:0}.skip{position:absolute;left:-10000px}.skip:focus{left:1rem;background:white;padding:.5rem}img{max-width:100%;height:auto}.moltex-placeholder{border:2px dashed #8a6500;padding:1rem}.listing-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));gap:1rem}.listing-card{border:1px solid #ccd1d1;padding:1rem}</style>\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_navigation(workspace: Path, contracts: Any, routes: dict[str, Any]) -> None:
        items = {
            item.navigation_id: {
                "id": item.navigation_id,
                "label": item.label,
                "href": (
                    routes[item.route_contract_id].target_url
                    if item.route_contract_id in routes
                    else "#"
                ),
                "order": item.order,
                "children": [],
            }
            for item in contracts.site_spec.global_navigation
        }
        navigation = []
        for source in contracts.site_spec.global_navigation:
            target = items[source.navigation_id]
            if source.parent_navigation_id in items:
                items[source.parent_navigation_id]["children"].append(target)
            else:
                navigation.append(target)

        def sort_tree(nodes: list[dict[str, Any]]) -> None:
            nodes.sort(key=lambda node: (node["order"], node["id"]))
            for node in nodes:
                sort_tree(node["children"])

        sort_tree(navigation)
        write_json(workspace / "src" / "data" / "navigation.json", navigation)

    @staticmethod
    def _write_page(
        workspace: Path,
        output_path: str,
        document: dict[str, Any],
        listing_items: list[dict[str, Any]] | None = None,
    ) -> None:
        pure = PurePosixPath(output_path)
        parts = list(pure.parts)
        if parts[-1] == "index.html":
            parts[-1] = "index.astro"
        elif parts[-1].endswith(".html"):
            parts[-1] = parts[-1][:-5] + ".astro"
        else:
            raise ValueError(f"Unsupported static output path: {output_path}")
        page = workspace / "src" / "pages" / Path(*parts)
        page.parent.mkdir(parents=True, exist_ok=True)
        layout_import = "../" * len(parts) + "layouts/BaseLayout.astro"
        literal = json.dumps(document, ensure_ascii=False).replace("</", "<\\/")
        listings_literal = json.dumps(listing_items or [], ensure_ascii=False).replace(
            "</", "<\\/"
        )
        page.write_text(
            f"---\nimport BaseLayout from '{layout_import}';\nconst record = {literal};\nconst listingItems = {listings_literal};\nconst seo = record.seo ?? {{}};\n"
            "const typedFields = Object.entries(record.customFields ?? {}).filter(([key]) => key.startsWith('geodirectory.'));\n---\n"
            "<BaseLayout title={seo.title ?? record.title} description={seo.description ?? ''} canonical={seo.canonical_url ?? ''} robots={seo.robots ?? 'index,follow'} openGraph={seo.open_graph ?? {}} structuredDataHints={seo.structured_data_hints ?? []}>"
            "<article data-record-id={record.recordId}><h1>{record.title}</h1>"
            "{record.media?.map((media) => <img src={media.src} alt={media.alt} data-asset-id={media.assetId} />)}"
            "<div class=\"content\" set:html={record.renderedHtml} />"
            "{typedFields.length ? <dl class=\"typed-fields\">{typedFields.map(([key, value]) => <><dt>{key.replace('geodirectory.', '')}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value ?? '')}</dd></>)}</dl> : null}"
            "{listingItems.length ? <section class=\"listing-grid\" aria-label=\"Listings\">{listingItems.map((item) => <article class=\"listing-card\" data-record-id={item.recordId}><h2>{item.targetUrl ? <a href={item.targetUrl}>{item.title}</a> : item.title}</h2>{item.excerpt ? <p>{item.excerpt}</p> : null}</article>)}</section> : null}"
            "</article></BaseLayout>\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_metadata(workspace: Path, contracts: Any) -> None:
        seo_by_route = {item.route_contract_id: item for item in contracts.seo}
        sitemap = [
            route.target_url
            for route in contracts.routes
            if route.public
            and route.expected_status == 200
            and "noindex"
            not in (
                seo.robots.lower()
                if (seo := seo_by_route.get(route.contract_id))
                else ""
            )
        ]
        write_json(workspace / "src" / "data" / "sitemap.json", sitemap)
        redirects = "\n".join(
            f"{item.source_url} {item.target_url} {item.status_code}"
            for item in contracts.redirects if not item.needs_decision
        )
        public = workspace / "public"
        public.mkdir(exist_ok=True)
        (public / "_redirects").write_text(redirects + ("\n" if redirects else ""), encoding="utf-8")
        origin = contracts.site_spec.target_canonical_origin.rstrip("/")
        sitemap_xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(
            f"<url><loc>{origin}{path}</loc></url>" for path in sitemap
        ) + "</urlset>\n"
        (public / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")
        (workspace / "src" / "content.config.ts").write_text(
            "import { defineCollection } from 'astro:content';\nimport { glob } from 'astro/loaders';\nexport const collections = { records: defineCollection({ loader: glob({ pattern: '**/*.json', base: './src/content/records' }) }) };\n",
            encoding="utf-8",
        )

    @staticmethod
    def _excerpt(value: str, limit: int = 240) -> str:
        text = html.unescape(re.sub(r"<[^>]+>", " ", value))
        return re.sub(r"\s+", " ", text).strip()[:limit]

    @staticmethod
    def _body_marker(value: str, limit: int = 80) -> str:
        candidates = [
            re.sub(r"\s+", " ", part).strip()
            for part in re.split(r"<[^>]+>", value)
        ]
        candidates = [part for part in candidates if part]
        return max(candidates, key=len, default="")[:limit]

    @staticmethod
    def _write_expectations(
        workspace: Path,
        contracts: Any,
        receipts: Any,
        conversion_receipts: Any,
        visual_receipt: Any,
    ) -> None:
        conversion_by_id = {
            receipt.record_id: receipt for receipt in conversion_receipts
        }
        plan = contracts.visual_capture_plan
        write_json(
            workspace / ".moltex" / "verification" / "baseline-expectations.json",
            {
                "bundleId": contracts.source_manifest.bundle_id,
                "sourceOrigin": contracts.site_spec.source_origin,
                "routes": [
                    {
                        "id": route.contract_id,
                        "output": route.output_path,
                        "markers": list(route.required_content_markers),
                        "bodyMarkers": [
                            marker
                            for marker in [
                                BaselineService._body_marker(
                                    conversion_by_id[route.content_record_id].sanitized_html
                                )
                                if route.content_record_id in conversion_by_id
                                else ""
                            ]
                            if marker
                        ],
                    }
                    for route in contracts.routes if route.public
                ],
                "assets": [
                    {"id": receipt.asset_id, "path": receipt.target_path.removeprefix("public/"), "sha256": receipt.sha256}
                    for receipt in receipts
                ],
                "contentRecords": [
                    "src/content/records/"
                    + record.record_id.replace(":", "-")
                    + ".json"
                    for record in contracts.content_records
                ],
                "visualPlan": {
                    "id": plan.plan_id,
                    "sha256": hashlib.sha256(
                        deterministic_json(plan).encode()
                    ).hexdigest(),
                    "evidence": [
                        {
                            "evidenceId": item.evidence_id,
                            "routeId": item.route_contract_id,
                            "sourceUrl": item.source_url,
                            "finalUrl": item.final_url,
                            "viewport": item.viewport_name,
                            "width": item.width,
                            "height": item.height,
                            "artifact": item.artifact,
                            "bytes": item.bytes,
                            "sha256": item.sha256,
                        }
                        for item in visual_receipt.evidence
                    ],
                },
                "visualReceipt": ".moltex/evidence/source-visuals/capture-receipt.json",
            },
        )

    @staticmethod
    def _write_scripts(workspace: Path) -> None:
        scripts = workspace / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / "build.mjs", scripts / "build.mjs")
        shutil.copyfile(
            TEMPLATES / "verify-baseline.mjs", scripts / "verify-baseline.mjs"
        )

    @staticmethod
    def _failure(
        output: Path,
        bundle_id: str | None,
        code: str,
        message: str,
        classification: FailureClassification | None = None,
    ) -> BaselineOutcome:
        report = BaselineCompilationReport(
            status="failed",
            bundle_id=bundle_id,
            code=code,
            message=message,
            classification=classification,
        )
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "baseline-compilation-report.json", report)
        return BaselineOutcome(report, 7)
