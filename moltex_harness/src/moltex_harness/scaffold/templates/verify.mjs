import fs from "node:fs";
import path from "node:path";
import { loadContracts } from "./verify-lib/contracts.mjs";
import { walk, posix } from "./verify-lib/files.mjs";
import { checkResult, exitCodeFor, suiteReport, writeJson } from "./verify-lib/results.mjs";
import { withPreview } from "./verify-lib/http.mjs";
import {
  assetChecks, buildChecks, capabilityChecks, contractChecks, linkChecks, navigationChecks,
  parityChecks, redirectChecks, routeAndContentChecks, seoChecks, taskChecks,
} from "./verify-lib/checks/static.mjs";
import { browserChecks, httpChecks } from "./verify-lib/checks/runtime.mjs";
import { validateRegisteredChecks } from "./verify-lib/checks/registry.mjs";

const argument = (name, fallback = null) => {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
};
const level = argument("--level", "baseline");
if (!["baseline", "migration", "parity"].includes(level)) {
  console.error(`Unknown verification level: ${level}`);
  process.exit(64);
}
const selected = new Set((argument("--checks", "") || "").split(",").filter(Boolean));
const allows = (checkId) => selected.size === 0 || selected.has(checkId);
const filter = (items) => items.filter((item) => allows(item.check_id));
const started = Date.now();
const startedAt = new Date(started).toISOString();
let checks = [];
let processes = [];
let artifacts = [];
let contracts = null;

try {
  contracts = loadContracts();
  checks.push(...filter(contractChecks(contracts)));
  checks.push(...filter(buildChecks(contracts)));
  checks.push(...filter(routeAndContentChecks(contracts)));
  checks.push(...filter(assetChecks(contracts)));

  const actualRoutes = walk("dist").filter((file) => file.endsWith(".html")).map((file) => ({ path: posix(path.relative("dist", file)), bytes: fs.statSync(file).size }));
  const actualAssets = contracts.assets.filter((asset) => {
    const target = asset.target_path.startsWith("public/") ? path.join("dist", asset.target_path.slice(7)) : path.join("dist", asset.target_path);
    return fs.existsSync(target);
  }).map((asset) => ({ id: asset.asset_id, path: asset.target_path, bytes: asset.bytes, sha256: asset.checksum }));
  writeJson(".moltex/reports/built-route-inventory.json", actualRoutes);
  writeJson(".moltex/reports/built-asset-inventory.json", actualAssets);
  artifacts.push(
    { schema_version: 1, artifact_id: "built-routes", kind: "inventory", path: ".moltex/reports/built-route-inventory.json" },
    { schema_version: 1, artifact_id: "built-assets", kind: "inventory", path: ".moltex/reports/built-asset-inventory.json" },
  );

  if (level !== "baseline") {
    checks.push(...filter(linkChecks(contracts)));
    checks.push(...filter(navigationChecks(contracts)));
    checks.push(...filter(seoChecks(contracts)));
    checks.push(...filter(redirectChecks(contracts)));
    checks.push(...filter(capabilityChecks(contracts)));
    if (selected.size === 0 || selected.has("http.route-status") || selected.has("http.content-type") || selected.has("http.not-found")) {
      try {
        const preview = await withPreview(async (baseUrl) => filter(await httpChecks(contracts, baseUrl)));
        checks.push(...preview.value);
        processes.push(preview.processResult);
      } catch (error) {
        if (error.processResult) processes.push(error.processResult);
        checks.push(checkResult({ checkId: "verification.preview", status: "error", severity: "critical", subject: "astro-preview", evidenceRefs: ["dist"], expected: "ready production preview", actual: null, message: error.message, artifacts: [".moltex/reports/processes/preview.log"] }));
      }
    }
  }

  if (level === "parity") {
    checks.push(...filter(taskChecks(contracts)));
    checks.push(...filter(parityChecks(contracts)));
    if (selected.size === 0 || [...selected].some((item) => item.startsWith("browser.") || item.startsWith("a11y."))) {
      try {
        const preview = await withPreview(async (baseUrl) => browserChecks(contracts, baseUrl));
        checks.push(...filter(preview.value.checks));
        artifacts.push(...preview.value.artifacts);
        processes.push(preview.processResult);
      } catch (error) {
        if (error.processResult) processes.push(error.processResult);
        checks.push(checkResult({ checkId: "browser.lifecycle", status: "error", severity: "critical", subject: "chromium", evidenceRefs: ["dist"], expected: "completed browser flows", actual: null, message: error.message, artifacts: [".moltex/reports/processes/preview.log"] }));
      }
    }
    for (const evidence of contracts.expectations.visualPlan.evidence) {
      checks.push(checkResult({
        checkId: "visual.parity-review", status: "review", severity: "warning", subject: `${evidence.routeId}@${evidence.viewport}`,
        contractIds: [evidence.routeId], evidenceRefs: [`.moltex/evidence/source-visuals/${evidence.artifact}`],
        expected: "named human or visual-review approval", actual: "automated evidence captured", message: "Visual evidence is available; automated signals do not approve parity",
        artifacts: artifacts.filter((item) => item.kind === "screenshot" && item.artifact_id.startsWith(`${evidence.routeId}:`)).map((item) => item.path),
      }));
    }
  }
} catch (error) {
  checks.push(checkResult({ checkId: "verification.harness", status: "error", severity: "critical", subject: level, evidenceRefs: [], expected: "completed verification", actual: null, message: error.stack ?? error.message }));
}

try { validateRegisteredChecks(checks); }
catch (error) { checks.push(checkResult({ checkId: "verification.harness", status: "error", severity: "critical", subject: level, expected: "registered versioned check IDs", actual: null, message: error.message })); }
const report = suiteReport({ level, bundleId: contracts?.sourceManifest?.bundle_id ?? null, checks, processes, artifacts, startedAt, durationMs: Date.now() - started });
const reportFile = `.moltex/reports/verification-${level}.json`;
writeJson(reportFile, report);
console.log(`${level} verification: ${report.status} (${checks.length} checks); report=${reportFile}`);
process.exit(exitCodeFor(report.status));
