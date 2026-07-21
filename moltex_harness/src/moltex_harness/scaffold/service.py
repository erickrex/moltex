"""Compile an accepted bundle and source evidence into an Astro 5 baseline."""

from __future__ import annotations

import html
import hashlib
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
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
from .toolchain import NODE_VERSION, NPM_VERSION


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
            if contracts.site_spec.static_eligibility == "ineligible":
                return self._failure(
                    output,
                    contracts.source_manifest.bundle_id,
                    "static_ineligible",
                    "Source readiness marks this site ineligible for complete static migration",
                    "blocked",
                )
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
                omitted_route_ids = {
                    item.route_contract_id
                    for item in visual_receipt.route_availability
                    if item.disposition == "omitted"
                }
                omitted_content = {
                    route.content_record_id
                    for route in contracts.routes
                    if route.contract_id in omitted_route_ids
                    and route.content_record_id is not None
                }
                omitted_source_ids = {
                    record.source_id
                    for record in contracts.content_records
                    if record.record_id in omitted_content
                }
                omitted_content_keys = omitted_content | omitted_source_ids
                materialized_assets = tuple(
                    asset
                    for asset in contracts.assets
                    if not asset.referencing_content_ids
                    or not set(asset.referencing_content_ids).issubset(
                        omitted_content_keys
                    )
                )
                receipts = AssetMaterializer(self.media_fetcher).materialize(
                    materialized_assets, extraction, workspace
                )
                write_json(workspace / ".moltex" / "receipts" / "assets.json", receipts)
                conversion_receipts = self._generate(
                    workspace, contracts, omitted_route_ids
                )
                self._write_expectations(
                    workspace,
                    contracts,
                    receipts,
                    conversion_receipts,
                    visual_receipt,
                    omitted_route_ids,
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
                "content": len(conversion_receipts),
                "routes": sum(
                    1
                    for route in contracts.routes
                    if route.public and route.contract_id not in omitted_route_ids
                ),
                "assets": len(receipts),
                "visuals": len(visual_receipt.evidence),
                "omitted_routes": len(omitted_route_ids),
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

    def _generate(
        self,
        workspace: Path,
        contracts: Any,
        omitted_route_ids: set[str],
    ) -> tuple[Any, ...]:
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / "package.json", workspace / "package.json")
        shutil.copyfile(TEMPLATES / "package-lock.json", workspace / "package-lock.json")
        shutil.copyfile(TEMPLATES / ".node-version", workspace / ".node-version")
        shutil.copyfile(TEMPLATES / ".npmrc", workspace / ".npmrc")
        (workspace / "astro.config.mjs").write_text(
            "import { defineConfig } from 'astro/config';\nexport default defineConfig({ output: 'static', trailingSlash: 'always' });\n",
            encoding="utf-8",
        )
        write_json(
            workspace / "tsconfig.json",
            {"extends": "astro/tsconfigs/strict", "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}},
        )
        routes_by_id = {route.contract_id: route for route in contracts.routes}
        included_routes = tuple(
            route
            for route in contracts.routes
            if route.public and route.contract_id not in omitted_route_ids
        )
        included_record_ids = {
            route.content_record_id
            for route in included_routes
            if route.content_record_id is not None
        }
        seo_by_route = {item.route_contract_id: item for item in contracts.seo}
        url_map = {entry.source_url: entry.target_url for entry in contracts.url_map}
        media_map = {entry.source_url: entry.target_url for entry in contracts.media_map}
        assets_by_id = {asset.asset_id: asset for asset in contracts.assets}
        converter = ContentConverter(UrlRewriter(contracts.site_spec.source_origin, url_map, media_map))
        frontmatter = FrontmatterNormalizer()
        content_by_id: dict[str, dict[str, Any]] = {}
        receipts = []
        for record in contracts.content_records:
            if record.record_id not in included_record_ids:
                continue
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
        self._write_navigation(
            workspace, contracts, routes_by_id, omitted_route_ids
        )
        posts = [
            item["recordId"]
            for item in content_by_id.values()
            if item["contentType"] == "post"
        ]
        geodirectory = [
            item["recordId"]
            for item in content_by_id.values()
            if item["contentType"].startswith("gd_")
        ]
        generated_routes: list[dict[str, Any]] = []
        for route in included_routes:
            record_id = route.content_record_id or route.contract_id
            if record_id not in content_by_id:
                document = {
                    "recordId": record_id,
                    "contentType": "system",
                    "title": route.page_family.replace("_", " ").title(),
                    "renderedHtml": (
                        "<p>This route requires a target implementation.</p>"
                    ),
                    "seo": {},
                    "media": [],
                    "customFields": {},
                }
                content_by_id[record_id] = document
                safe_name = record_id.replace(":", "-") + ".json"
                write_json(
                    workspace / "src" / "content" / "records" / safe_name,
                    document,
                )
            listing_record_ids: list[str] = []
            if route.page_family == "listing":
                listing_record_ids = posts
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
                listing_record_ids = geodirectory
            if route.output_path != "404.html":
                generated_routes.append(
                    {
                        "routeId": route.contract_id,
                        "path": self._astro_route_path(route.output_path),
                        "recordId": record_id,
                        "listingRecordIds": listing_record_ids,
                    }
                )
        system_404 = {
            "recordId": "system:404",
            "contentType": "system",
            "title": "Page not found",
            "renderedHtml": "<p>The requested page could not be found.</p>",
            "seo": {"robots": "noindex", "structured_data_hints": []},
            "media": [],
            "customFields": {},
        }
        write_json(
            workspace / "src" / "content" / "records" / "system-404.json",
            system_404,
        )
        write_json(workspace / "src" / "data" / "routes.json", generated_routes)
        self._write_route_templates(workspace)
        self._write_metadata(workspace, contracts, omitted_route_ids)
        self._write_scripts(workspace)
        return tuple(receipts)

    @staticmethod
    def _write_shell(workspace: Path, site_name: str) -> None:
        write_json(workspace / "src" / "data" / "site.json", {"siteName": site_name})
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
            "---\nimport nav from '../data/navigation.json';\nimport site from '../data/site.json';\nimport NavigationList from '../components/NavigationList.astro';\n"
            "const { title, description = '', canonical = '', robots = 'index,follow', openGraph = {}, structuredDataHints = [] } = Astro.props;\n"
            "const ogItems = Array.isArray(openGraph.items) ? openGraph.items : [openGraph];\n"
            "const ogEntries = ogItems.flatMap((item) => item && (item.property || item.name || item.key) ? [[item.property || item.name || item.key, item.content ?? item.value ?? '']] : Object.entries(item ?? {}).filter(([key]) => key !== 'items'));\n---\n"
            "<!doctype html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            "<meta name=\"description\" content={description}><meta name=\"robots\" content={robots}><link rel=\"canonical\" href={canonical}>"
            "{ogEntries.map(([property, content]) => <meta property={String(property).startsWith('og:') ? String(property) : `og:${property}`} content={String(content)} />)}"
            "{structuredDataHints.map((hint) => <meta name=\"moltex:structured-data-hint\" content={hint} />)}<title>{title}</title></head>"
            "<body><a class=\"skip\" href=\"#content\">Skip to content</a><header><a href=\"/\">{site.siteName}</a><nav aria-label=\"Primary\"><NavigationList items={nav} /></nav></header>"
            "<main id=\"content\"><slot /></main><footer>Generated by Moltex</footer></body></html>"
            "<style is:global>:root{font-family:system-ui,sans-serif;color:#17202a}body{margin:0}header,main,footer{max-width:72rem;margin:auto;padding:1rem}nav>ul{display:flex;gap:1rem}nav ul{list-style:none;padding:0}.skip{position:absolute;left:-10000px}.skip:focus{left:1rem;background:white;padding:.5rem}img{max-width:100%;height:auto}.moltex-placeholder{border:2px dashed #8a6500;padding:1rem}.listing-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));gap:1rem}.listing-card{border:1px solid #ccd1d1;padding:1rem}</style>\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_navigation(
        workspace: Path,
        contracts: Any,
        routes: dict[str, Any],
        omitted_route_ids: set[str],
    ) -> None:
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
            if item.route_contract_id not in omitted_route_ids
        }
        navigation = []
        for source in contracts.site_spec.global_navigation:
            if source.navigation_id not in items:
                continue
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
    def _write_route_templates(workspace: Path) -> None:
        pages = workspace / "src" / "pages"
        pages.mkdir(parents=True, exist_ok=True)
        shared_render = (
            "<BaseLayout title={seo.title ?? record.title} description={seo.description ?? ''} canonical={seo.canonical_url ?? ''} robots={seo.robots ?? 'index,follow'} openGraph={seo.open_graph ?? {}} structuredDataHints={seo.structured_data_hints ?? []}>"
            "<article data-record-id={record.recordId}><h1>{record.title}</h1>"
            "{record.media?.map((media) => <img src={media.src} alt={media.alt} data-asset-id={media.assetId} />)}"
            "<div class=\"content\" set:html={record.renderedHtml} />"
            "{typedFields.length ? <dl class=\"typed-fields\">{typedFields.map(([key, value]) => <><dt>{key.replace('geodirectory.', '')}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value ?? '')}</dd></>)}</dl> : null}"
            "{listingItems.length ? <section class=\"listing-grid\" aria-label=\"Listings\">{listingItems.map((item) => <article class=\"listing-card\" data-record-id={item.recordId}><h2>{item.targetUrl ? <a href={item.targetUrl}>{item.title}</a> : item.title}</h2>{item.excerpt ? <p>{item.excerpt}</p> : null}</article>)}</section> : null}"
            "</article></BaseLayout>\n"
        )
        (pages / "[...path].astro").write_text(
            "---\nimport BaseLayout from '../layouts/BaseLayout.astro';\nimport routes from '../data/routes.json';\n"
            "const recordModules = import.meta.glob('../content/records/*.json', { eager: true, import: 'default' });\n"
            "const records = Object.values(recordModules) as any[];\n"
            "export function getStaticPaths() { return routes.map((route) => ({ params: { path: route.path || undefined }, props: route })); }\n"
            "const route = Astro.props;\nconst record = records.find((item) => item.recordId === route.recordId);\n"
            "if (!record) throw new Error(`Missing route record: ${route.recordId}`);\n"
            "const listingItems = route.listingRecordIds.map((id) => records.find((item) => item.recordId === id)).filter(Boolean);\n"
            "const seo = record.seo ?? {};\nconst typedFields = Object.entries(record.customFields ?? {}).filter(([key]) => key.startsWith('geodirectory.'));\n---\n"
            + shared_render,
            encoding="utf-8",
        )
        (pages / "404.astro").write_text(
            "---\nimport BaseLayout from '../layouts/BaseLayout.astro';\nimport record from '../content/records/system-404.json';\n"
            "const listingItems = [];\nconst seo = record.seo ?? {};\nconst typedFields = [];\n---\n"
            + shared_render,
            encoding="utf-8",
        )

    @staticmethod
    def _astro_route_path(output_path: str) -> str:
        if output_path == "index.html":
            return ""
        if output_path.endswith("/index.html"):
            return output_path.removesuffix("/index.html")
        raise ValueError(
            f"Data-driven routes require an index.html output path: {output_path}"
        )

    @staticmethod
    def _write_metadata(
        workspace: Path, contracts: Any, omitted_route_ids: set[str]
    ) -> None:
        seo_by_route = {item.route_contract_id: item for item in contracts.seo}
        sitemap = [
            route.target_url
            for route in contracts.routes
            if route.public
            and route.contract_id not in omitted_route_ids
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
            BaselineService._redirect_line(
                item.source_url, item.target_url, item.status_code
            )
            for item in contracts.redirects
            if not item.needs_decision
            and item.target_route_contract_id not in omitted_route_ids
        )
        public = workspace / "public"
        public.mkdir(exist_ok=True)
        (public / "_redirects").write_text(redirects + ("\n" if redirects else ""), encoding="utf-8")
        origin = contracts.site_spec.target_canonical_origin.rstrip("/")
        namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
        ET.register_namespace("", namespace)
        urlset = ET.Element(f"{{{namespace}}}urlset")
        for path in sitemap:
            url = ET.SubElement(urlset, f"{{{namespace}}}url")
            ET.SubElement(url, f"{{{namespace}}}loc").text = origin + path
        sitemap_xml = ET.tostring(
            urlset, encoding="utf-8", xml_declaration=True
        ) + b"\n"
        (public / "sitemap.xml").write_bytes(sitemap_xml)
        (workspace / "src" / "content.config.ts").write_text(
            "import { defineCollection } from 'astro:content';\nimport { glob } from 'astro/loaders';\nexport const collections = { records: defineCollection({ loader: glob({ pattern: '**/*.json', base: './src/content/records' }) }) };\n",
            encoding="utf-8",
        )

    @staticmethod
    def _redirect_line(source: str, target: str, status_code: int) -> str:
        if any(character.isspace() for character in source + target):
            raise ValueError("Redirect URLs must not contain whitespace")
        return f"{source} {target} {status_code}"

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
        omitted_route_ids: set[str],
    ) -> None:
        conversion_by_id = {
            receipt.record_id: receipt for receipt in conversion_receipts
        }
        plan = contracts.visual_capture_plan
        write_json(
            workspace / ".moltex" / "verification" / "baseline-expectations.json",
            {
                "bundleId": contracts.source_manifest.bundle_id,
                "toolchain": {"node": NODE_VERSION, "npm": NPM_VERSION},
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
                    and route.contract_id not in omitted_route_ids
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
                    if record.record_id in conversion_by_id
                ],
                "omittedRoutes": [
                    item.model_dump(mode="json")
                    for item in visual_receipt.route_availability
                    if item.disposition == "omitted"
                ],
                "routeAvailability": [
                    item.model_dump(mode="json")
                    for item in visual_receipt.route_availability
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
        shutil.copyfile(TEMPLATES / "verify.mjs", scripts / "verify.mjs")
        shutil.copyfile(TEMPLATES / "verify-task.mjs", scripts / "verify-task.mjs")
        shutil.copytree(TEMPLATES / "verify-lib", scripts / "verify-lib")
        shutil.copytree(
            TEMPLATES / "verifier-schemas",
            workspace / ".moltex" / "schemas" / "verifier",
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
