import fs from "node:fs";
import path from "node:path";
import { checkResult } from "../results.mjs";
import { requestArtifact } from "../http.mjs";

const safeName = (value) => value.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "root";
const pngDimensions = (file) => {
  const data = fs.readFileSync(file);
  if (data.length < 24 || data.toString("hex", 0, 8) !== "89504e470d0a1a0a") return null;
  return { width: data.readUInt32BE(16), height: data.readUInt32BE(20) };
};

export const httpChecks = async (contracts, baseUrl) => {
  const checks = [];
  for (const route of contracts.publishedRoutes) {
    const name = safeName(route.contract_id);
    const artifact = `.moltex/reports/http/${name}.response.json`;
    try {
      const { response } = await requestArtifact(baseUrl, route.target_url, artifact);
      checks.push(checkResult({
        checkId: "http.route-status", status: response.status === route.expected_status ? "pass" : "fail", severity: response.status === route.expected_status ? "info" : "critical",
        subject: route.target_url, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`],
        expected: route.expected_status, actual: response.status, message: response.status === route.expected_status ? "Preview returned the expected status" : `Preview returned ${response.status}; expected ${route.expected_status}`,
        artifacts: [artifact],
      }));
      const contentType = response.headers.get("content-type") ?? "";
      checks.push(checkResult({
        checkId: "http.content-type", status: contentType.includes("text/html") ? "pass" : "fail", severity: contentType.includes("text/html") ? "info" : "error",
        subject: route.target_url, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`],
        expected: "text/html", actual: contentType, message: contentType.includes("text/html") ? "Preview served HTML" : "Preview did not serve HTML", artifacts: [artifact],
      }));
    } catch (error) {
      checks.push(checkResult({ checkId: "http.route-status", status: "error", severity: "critical", subject: route.target_url, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: route.expected_status, actual: null, message: `HTTP probe failed: ${error.message}`, artifacts: [artifact] }));
    }
  }
  const missingRoute = `/__moltex_missing_${contracts.sourceManifest.bundle_id.replace(/[^a-z0-9]/gi, "").slice(0, 12)}/`;
  const missingArtifact = ".moltex/reports/http/not-found.response.json";
  try {
    const { response } = await requestArtifact(baseUrl, missingRoute, missingArtifact);
    checks.push(checkResult({
      checkId: "http.not-found", status: response.status === 404 ? "pass" : "fail", severity: response.status === 404 ? "info" : "critical",
      subject: missingRoute, contractIds: contracts.publishedRoutes.map((item) => item.contract_id), evidenceRefs: [".moltex/contracts/contracts/routes.json"],
      expected: 404, actual: response.status, message: response.status === 404 ? "Unknown public path returns a real 404" : `Unknown public path is a soft 404 with status ${response.status}`, artifacts: [missingArtifact],
    }));
  } catch (error) {
    checks.push(checkResult({ checkId: "http.not-found", status: "error", severity: "critical", subject: missingRoute, contractIds: contracts.publishedRoutes.map((item) => item.contract_id), evidenceRefs: [".moltex/contracts/contracts/routes.json"], expected: 404, actual: null, message: `404 probe failed: ${error.message}`, artifacts: [missingArtifact] }));
  }
  return checks;
};

const accessibleNameFailures = (nodes) => nodes.filter((node) => !node.name.trim()).map((node) => node.element);

export const browserChecks = async (contracts, baseUrl) => {
  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ headless: true });
  const checks = [];
  const artifactRecords = [];
  try {
    const plannedEvidence = contracts.expectations.visualPlan?.evidence ?? [];
    const profiles = [...new Map(plannedEvidence.map((item) => [
      item.viewport,
      { name: item.viewport, width: item.width, height: item.height },
    ])).values()];
    const routeById = new Map(contracts.publishedRoutes.map((route) => [route.contract_id, route]));
    for (const profile of profiles) {
      const routes = [...new Set(
        plannedEvidence
          .filter((item) => item.viewport === profile.name)
          .map((item) => item.routeId),
      )].map((routeId) => routeById.get(routeId)).filter(Boolean);
      const context = await browser.newContext({ viewport: { width: profile.width, height: profile.height } });
      const trace = `.moltex/reports/browser/${profile.name}.trace.zip`;
      fs.mkdirSync(path.dirname(trace), { recursive: true });
      await context.tracing.start({ screenshots: true, snapshots: true, sources: false });
      for (const route of routes) {
        const page = await context.newPage();
        const consoleErrors = [];
        page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
        page.on("pageerror", (error) => consoleErrors.push(error.message));
        page.on("requestfailed", (request) => consoleErrors.push(`request failed: ${request.url()} (${request.failure()?.errorText ?? "unknown"})`));
        page.on("response", (response) => { if (response.status() >= 400 && new URL(response.url()).origin === baseUrl) consoleErrors.push(`local resource ${response.status()}: ${response.url()}`); });
        const started = Date.now();
        try {
          const response = await page.goto(new URL(route.target_url, baseUrl).href, { waitUntil: "networkidle", timeout: 10000 });
          const screenshot = `.moltex/reports/browser/${safeName(route.contract_id)}-${profile.name}.png`;
          const consoleArtifact = `.moltex/reports/browser/${safeName(route.contract_id)}-${profile.name}.console.json`;
          const layoutArtifact = `.moltex/reports/browser/${safeName(route.contract_id)}-${profile.name}.layout.json`;
          await page.screenshot({ path: screenshot, fullPage: true });
          const landmarks = await page.locator("main, nav[aria-label]").evaluateAll((items) => items.map((item) => item.tagName.toLowerCase()));
          const named = await page.locator("nav, a, button, input, select, textarea, img").evaluateAll((items) => items.map((item) => ({
            element: item.tagName.toLowerCase(),
            name: item.tagName.toLowerCase() === "nav" ? (item.getAttribute("aria-label") || "") : (item.getAttribute("aria-label") || item.getAttribute("alt") || item.textContent || item.getAttribute("value") || item.getAttribute("name") || ""),
          })));
          const unnamed = accessibleNameFailures(named);
          const layout = await page.evaluate(() => {
            const root = document.documentElement;
            const unresolved = [...document.querySelectorAll('.moltex-placeholder, [data-moltex-dynamic-block]')]
              .map((item) => (item.textContent || '').trim().slice(0, 160));
            const verticallyStackedText = [...document.querySelectorAll('h1, h2, h3, p, a, button')]
              .filter((item) => {
                const text = (item.textContent || '').trim();
                const rect = item.getBoundingClientRect();
                return text.split(/\s+/).length >= 3 && rect.width < 90 && rect.height > rect.width * 2.5;
              })
              .map((item) => {
                const rect = item.getBoundingClientRect();
                return { element: item.tagName.toLowerCase(), text: (item.textContent || '').trim().slice(0, 120), width: Math.round(rect.width), height: Math.round(rect.height) };
              });
            return { viewportWidth: root.clientWidth, scrollWidth: root.scrollWidth, scrollHeight: root.scrollHeight, unresolved, verticallyStackedText };
          });
          fs.writeFileSync(consoleArtifact, JSON.stringify({ schema_version: 1, route: route.target_url, viewport: profile, messages: consoleErrors }, null, 2) + "\n");
          fs.writeFileSync(layoutArtifact, JSON.stringify({ schema_version: 1, route: route.target_url, viewport: profile, ...layout }, null, 2) + "\n");
          const planned = plannedEvidence.find((item) => item.routeId === route.contract_id && item.viewport === profile.name);
          const sourceScreenshot = planned ? `.moltex/evidence/source-visuals/${planned.artifact}` : null;
          const sourceDimensions = sourceScreenshot && fs.existsSync(sourceScreenshot) ? pngDimensions(sourceScreenshot) : null;
          const targetDimensions = pngDimensions(screenshot);
          const heightRatio = sourceDimensions && targetDimensions ? targetDimensions.height / sourceDimensions.height : null;
          checks.push(checkResult({ checkId: "browser.console", status: consoleErrors.length ? "fail" : "pass", severity: consoleErrors.length ? "error" : "info", subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: [], actual: consoleErrors, message: consoleErrors.length ? `Browser console/resource errors: ${consoleErrors.join("; ")}` : "No browser console, page, or local resource errors", artifacts: [screenshot, consoleArtifact, trace], durationMs: Date.now() - started }));
          checks.push(checkResult({ checkId: "a11y.landmarks", status: landmarks.includes("main") && landmarks.includes("nav") ? "pass" : "fail", severity: landmarks.includes("main") && landmarks.includes("nav") ? "info" : "error", subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: ["main", "nav"], actual: landmarks, message: landmarks.includes("main") && landmarks.includes("nav") ? "Required page landmarks are present" : "Page is missing main or labelled navigation landmark", artifacts: [screenshot] }));
          checks.push(checkResult({ checkId: "a11y.accessible-name", status: unnamed.length ? "fail" : "pass", severity: unnamed.length ? "error" : "info", subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: [], actual: unnamed, message: unnamed.length ? `Interactive/media elements lack accessible names: ${unnamed.join(", ")}` : "Interactive and media elements have accessible names", artifacts: [screenshot] }));
          checks.push(checkResult({
            checkId: "layout.horizontal-overflow", status: layout.scrollWidth <= layout.viewportWidth + 2 ? "pass" : "fail", severity: layout.scrollWidth <= layout.viewportWidth + 2 ? "info" : "error",
            subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: { maximumOverflow: 2 }, actual: layout,
            message: layout.scrollWidth <= layout.viewportWidth + 2 ? "Page has no horizontal viewport overflow" : `Page overflows horizontally by ${layout.scrollWidth - layout.viewportWidth}px`, artifacts: [screenshot],
          }));
          checks.push(checkResult({
            checkId: "layout.vertical-word-stacking", status: layout.verticallyStackedText.length ? "fail" : "pass", severity: layout.verticallyStackedText.length ? "critical" : "info",
            subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: [], actual: layout.verticallyStackedText,
            message: layout.verticallyStackedText.length ? "Text is constrained into suspicious vertical word columns" : "No suspicious vertical word stacking was detected", artifacts: [screenshot],
          }));
          checks.push(checkResult({
            checkId: "content.no-unresolved-placeholder", status: layout.unresolved.length ? "fail" : "pass", severity: layout.unresolved.length ? "critical" : "info",
            subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: [], actual: layout.unresolved,
            message: layout.unresolved.length ? "Published route contains unresolved source components" : "Published route contains no unresolved component markers", artifacts: [screenshot],
          }));
          checks.push(checkResult({
            checkId: "visual.page-height", status: heightRatio !== null && heightRatio >= 0.55 && heightRatio <= 1.8 ? "pass" : "fail", severity: heightRatio !== null && heightRatio >= 0.55 && heightRatio <= 1.8 ? "info" : "critical",
            subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`, sourceScreenshot].filter(Boolean), expected: { minimumRatio: 0.55, maximumRatio: 1.8 }, actual: { heightRatio, sourceDimensions, targetDimensions },
            message: heightRatio !== null && heightRatio >= 0.55 && heightRatio <= 1.8 ? "Rendered page height is within the gross source bound" : "Rendered page height differs grossly from source evidence", artifacts: [screenshot, sourceScreenshot, layoutArtifact].filter(Boolean),
          }));
          artifactRecords.push({ schema_version: 1, artifact_id: `${route.contract_id}:${profile.name}`, kind: "screenshot", path: screenshot, route: route.target_url, viewport: profile, status: response?.status() ?? null });
          artifactRecords.push({ schema_version: 1, artifact_id: `console:${route.contract_id}:${profile.name}`, kind: "browser-console", path: consoleArtifact, route: route.target_url, viewport: profile, status: response?.status() ?? null });
          artifactRecords.push({ schema_version: 1, artifact_id: `layout:${route.contract_id}:${profile.name}`, kind: "layout-metrics", path: layoutArtifact, route: route.target_url, viewport: profile, status: response?.status() ?? null });
        } catch (error) {
          checks.push(checkResult({ checkId: "browser.console", status: "error", severity: "critical", subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: "successful browser flow", actual: null, message: `Browser flow failed: ${error.message}`, artifacts: [trace] }));
        } finally { await page.close(); }
      }
      await context.tracing.stop({ path: trace });
      artifactRecords.push({ schema_version: 1, artifact_id: `trace:${profile.name}`, kind: "playwright-trace", path: trace, viewport: profile });
      await context.close();
    }
  } finally { await browser.close(); }
  return { checks, artifacts: artifactRecords };
};
