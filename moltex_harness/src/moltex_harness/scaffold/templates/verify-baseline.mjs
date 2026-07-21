import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const readJson = (file) => JSON.parse(fs.readFileSync(file, "utf8"));
const hash = (data) => crypto.createHash("sha256").update(data).digest("hex");
const posix = (value) => value.split(path.sep).join("/");
const decodeEntities = (value) => value.replace(
  /&(?:#x([0-9a-f]+)|#(\d+)|(amp|lt|gt|quot|apos|nbsp));/gi,
  (_, hex, decimal, named) => {
    if (hex) return String.fromCodePoint(Number.parseInt(hex, 16));
    if (decimal) return String.fromCodePoint(Number.parseInt(decimal, 10));
    return { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " }[named.toLowerCase()];
  },
);
const visibleText = (value) => {
  let decoded = value;
  for (let depth = 0; depth < 3; depth += 1) {
    const next = decodeEntities(decoded);
    if (next === decoded) break;
    decoded = next;
  }
  return decoded
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
};
const walk = (root) => {
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const item = path.join(root, entry.name);
    return entry.isDirectory() ? walk(item) : [item];
  });
};

const expectations = readJson(".moltex/verification/baseline-expectations.json");
const errors = [];
const routes = [];
const assets = [];
const actualNode = process.versions.node;
const actualNpm = process.env.npm_config_user_agent?.match(/(?:^|\s)npm\/([^\s]+)/)?.[1] ?? null;
if (actualNode !== expectations.toolchain.node) {
  errors.push(`Node toolchain mismatch: expected ${expectations.toolchain.node}, received ${actualNode}`);
}
if (actualNpm !== expectations.toolchain.npm) {
  errors.push(`npm toolchain mismatch: expected ${expectations.toolchain.npm}, received ${actualNpm ?? "unknown"}`);
}

const expectedHtml = new Set(expectations.routes.map((route) => route.output));
expectedHtml.add("404.html");
const actualHtml = new Set(
  walk("dist")
    .filter((file) => file.endsWith(".html"))
    .map((file) => posix(path.relative("dist", file))),
);
for (const output of expectedHtml) {
  if (!actualHtml.has(output)) errors.push(`missing route output: ${output}`);
}
for (const output of actualHtml) {
  if (!expectedHtml.has(output)) errors.push(`unexpected route output: ${output}`);
}

for (const route of expectations.routes) {
  const file = path.join("dist", ...route.output.split("/"));
  if (!fs.existsSync(file)) continue;
  const rendered = fs.readFileSync(file, "utf8");
  const article = rendered.match(/<article\b[^>]*>([\s\S]*?)<\/article>/i)?.[1] ?? "";
  const visibleArticle = visibleText(article);
  for (const marker of route.markers) {
    if (!visibleArticle.includes(visibleText(marker))) errors.push(`missing marker ${route.id}: ${marker}`);
  }
  for (const marker of route.bodyMarkers ?? []) {
    if (!visibleArticle.includes(visibleText(marker))) errors.push(`missing body marker ${route.id}: ${marker}`);
  }
  if (/(?:src|srcset)=["'][^"']*https?:\/\//i.test(rendered)) {
    errors.push(`production media hotlink in ${route.output}`);
  }
  if (/\s(?:on[a-z]+)\s*=|javascript:/i.test(rendered)) {
    errors.push(`executable content payload in ${route.output}`);
  }
  if (/<script\b/i.test(rendered)) {
    errors.push(`unexpected script element in ${route.output}`);
  }
  routes.push({ id: route.id, path: route.output, bytes: Buffer.byteLength(rendered) });
}

for (const record of expectations.contentRecords) {
  if (!fs.existsSync(record)) errors.push(`missing canonical content record: ${record}`);
}

for (const asset of expectations.assets) {
  const file = path.join("dist", ...asset.path.split("/"));
  if (!fs.existsSync(file)) {
    errors.push(`missing asset ${asset.id}: ${asset.path}`);
    continue;
  }
  const data = fs.readFileSync(file);
  const digest = hash(data);
  if (digest !== asset.sha256) errors.push(`asset checksum ${asset.id}`);
  assets.push({ id: asset.id, path: asset.path, bytes: data.length, sha256: digest });
}

const receipt = readJson(expectations.visualReceipt);
const expectedAvailability = new Map(
  expectations.routeAvailability.map((item) => [item.route_contract_id, item]),
);
const actualAvailability = new Map(
  receipt.route_availability.map((item) => [item.route_contract_id, item]),
);
if (
  actualAvailability.size !== receipt.route_availability.length ||
  actualAvailability.size !== expectedAvailability.size
) errors.push("route availability receipt coverage mismatch");
for (const [routeId, expected] of expectedAvailability) {
  const actual = actualAvailability.get(routeId);
  if (!actual || JSON.stringify(actual) !== JSON.stringify(expected)) {
    errors.push(`route availability binding mismatch: ${routeId}`);
  }
}
const expectedVisuals = new Map(
  expectations.visualPlan.evidence.map((item) => [item.evidenceId, item]),
);
const actualVisuals = new Map(receipt.evidence.map((item) => [item.evidence_id, item]));
if (receipt.bundle_id !== expectations.bundleId) errors.push("visual receipt bundle mismatch");
if (
  receipt.capture_plan_id !== expectations.visualPlan.id ||
  receipt.capture_plan_sha256 !== expectations.visualPlan.sha256
) errors.push("visual receipt plan mismatch");
if (actualVisuals.size !== receipt.evidence.length) errors.push("duplicate visual receipt entry");
if (actualVisuals.size !== expectedVisuals.size) errors.push("visual receipt target count mismatch");
for (const [evidenceId, expected] of expectedVisuals) {
  const actual = actualVisuals.get(evidenceId);
  if (!actual) {
    errors.push(`missing visual receipt entry: ${evidenceId}`);
    continue;
  }
  if (
    actual.route_contract_id !== expected.routeId ||
    actual.source_url !== expected.sourceUrl ||
    actual.final_url !== expected.finalUrl ||
    actual.viewport_name !== expected.viewport ||
    actual.width !== expected.width ||
    actual.height !== expected.height ||
    actual.artifact !== expected.artifact ||
    actual.bytes !== expected.bytes ||
    actual.sha256 !== expected.sha256
  ) errors.push(`visual evidence binding mismatch: ${evidenceId}`);
  const file = path.resolve(".moltex/evidence/source-visuals", actual.artifact);
  const visualRoot = path.resolve(".moltex/evidence/source-visuals");
  if (!file.startsWith(visualRoot + path.sep) || !fs.existsSync(file)) {
    errors.push(`missing visual ${evidenceId}`);
    continue;
  }
  const data = fs.readFileSync(file);
  if (data.length !== actual.bytes || hash(data) !== actual.sha256) {
    errors.push(`visual checksum ${evidenceId}`);
  }
}

fs.mkdirSync(".moltex/reports", { recursive: true });
fs.writeFileSync(
  ".moltex/reports/built-route-inventory.json",
  JSON.stringify(routes, null, 2) + "\n",
);
fs.writeFileSync(
  ".moltex/reports/built-asset-inventory.json",
  JSON.stringify(assets, null, 2) + "\n",
);
const report = {
  schema_version: 1,
  status: errors.length ? "fail" : "pass",
  checks: {
    toolchain: !errors.some((item) => item.includes("toolchain mismatch")),
    route_inventory: routes.length === expectations.routes.length,
    content_records: !errors.some((item) => item.includes("content record")),
    assets: assets.length === expectations.assets.length,
    visuals: !errors.some((item) => item.includes("visual")),
    route_availability: !errors.some((item) => item.includes("route availability")),
    no_production_media_hotlinks: !errors.some((item) => item.includes("hotlink")),
    no_executable_source_payloads: !errors.some((item) => item.includes("executable") || item.includes("script element")),
  },
  toolchain: { node: actualNode, npm: actualNpm },
  errors,
};
fs.writeFileSync(
  ".moltex/reports/baseline-verification-report.json",
  JSON.stringify(report, null, 2) + "\n",
);
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log(`Verified ${routes.length} routes and ${assets.length} assets`);
