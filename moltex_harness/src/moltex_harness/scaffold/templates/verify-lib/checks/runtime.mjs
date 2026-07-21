import fs from "node:fs";
import path from "node:path";
import { checkResult } from "../results.mjs";
import { requestArtifact } from "../http.mjs";

const safeName = (value) => value.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "root";

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
    const profiles = [{ name: "desktop", width: 1440, height: 1200 }, { name: "mobile", width: 500, height: 844 }];
    const routes = contracts.publishedRoutes.slice(0, 5);
    for (const profile of profiles) {
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
          await page.screenshot({ path: screenshot, fullPage: true });
          const landmarks = await page.locator("main, nav[aria-label]").evaluateAll((items) => items.map((item) => item.tagName.toLowerCase()));
          const named = await page.locator("nav, a, button, input, select, textarea, img").evaluateAll((items) => items.map((item) => ({
            element: item.tagName.toLowerCase(),
            name: item.tagName.toLowerCase() === "nav" ? (item.getAttribute("aria-label") || "") : (item.getAttribute("aria-label") || item.getAttribute("alt") || item.textContent || item.getAttribute("value") || item.getAttribute("name") || ""),
          })));
          const unnamed = accessibleNameFailures(named);
          fs.writeFileSync(consoleArtifact, JSON.stringify({ schema_version: 1, route: route.target_url, viewport: profile, messages: consoleErrors }, null, 2) + "\n");
          checks.push(checkResult({ checkId: "browser.console", status: consoleErrors.length ? "fail" : "pass", severity: consoleErrors.length ? "error" : "info", subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: [], actual: consoleErrors, message: consoleErrors.length ? `Browser console/resource errors: ${consoleErrors.join("; ")}` : "No browser console, page, or local resource errors", artifacts: [screenshot, consoleArtifact, trace], durationMs: Date.now() - started }));
          checks.push(checkResult({ checkId: "a11y.landmarks", status: landmarks.includes("main") && landmarks.includes("nav") ? "pass" : "fail", severity: landmarks.includes("main") && landmarks.includes("nav") ? "info" : "error", subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: ["main", "nav"], actual: landmarks, message: landmarks.includes("main") && landmarks.includes("nav") ? "Required page landmarks are present" : "Page is missing main or labelled navigation landmark", artifacts: [screenshot] }));
          checks.push(checkResult({ checkId: "a11y.accessible-name", status: unnamed.length ? "fail" : "pass", severity: unnamed.length ? "error" : "info", subject: `${route.target_url}@${profile.name}`, contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: [], actual: unnamed, message: unnamed.length ? `Interactive/media elements lack accessible names: ${unnamed.join(", ")}` : "Interactive and media elements have accessible names", artifacts: [screenshot] }));
          artifactRecords.push({ schema_version: 1, artifact_id: `${route.contract_id}:${profile.name}`, kind: "screenshot", path: screenshot, route: route.target_url, viewport: profile, status: response?.status() ?? null });
          artifactRecords.push({ schema_version: 1, artifact_id: `console:${route.contract_id}:${profile.name}`, kind: "browser-console", path: consoleArtifact, route: route.target_url, viewport: profile, status: response?.status() ?? null });
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
