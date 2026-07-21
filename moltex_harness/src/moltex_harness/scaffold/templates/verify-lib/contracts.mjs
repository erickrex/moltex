import fs from "node:fs";
import { readJson, sha256 } from "./files.mjs";

const CONTRACT_ROOT = ".moltex/contracts";
const contract = (name) => readJson(`${CONTRACT_ROOT}/contracts/${name}.json`, []);

export const loadContracts = () => {
  const index = readJson(`${CONTRACT_ROOT}/contract-index.json`);
  const sourceManifest = readJson(`${CONTRACT_ROOT}/source-manifest.json`);
  const siteSpec = readJson(`${CONTRACT_ROOT}/site-spec.json`);
  const routes = contract("routes");
  const assets = contract("assets");
  const seo = contract("seo");
  const expectations = readJson(".moltex/verification/baseline-expectations.json");
  const publishedRouteIds = new Set(expectations.routes.map((item) => item.id));
  const publishedAssetIds = new Set(expectations.assets.map((item) => item.id));
  return {
    index,
    sourceManifest,
    siteSpec,
    routes,
    assets,
    seo,
    publishedRoutes: routes.filter((item) => item.public && publishedRouteIds.has(item.contract_id)),
    publishedAssets: assets.filter((item) => publishedAssetIds.has(item.asset_id)),
    publishedSeo: seo.filter((item) => publishedRouteIds.has(item.route_contract_id)),
    redirects: contract("redirects"),
    capabilities: contract("capabilities"),
    parity: readJson(`${CONTRACT_ROOT}/parity-matrix.json`, []),
    expectations,
    taskGraph: readJson(".moltex/tasks/task-graph.json", null),
    planningParity: readJson(".moltex/parity-matrix.json", null),
  };
};

export const verifyContractReceipts = (contracts) => {
  const errors = [];
  if (contracts.index.bundle_id !== contracts.sourceManifest.bundle_id) errors.push("bundle ID mismatch");
  for (const receipt of contracts.index.files ?? []) {
    const file = `${CONTRACT_ROOT}/${receipt.path}`;
    if (!fs.existsSync(file)) { errors.push(`missing ${receipt.path}`); continue; }
    const data = fs.readFileSync(file);
    if (data.length !== receipt.bytes || sha256(data) !== receipt.sha256) errors.push(`checksum ${receipt.path}`);
  }
  if (contracts.expectations.bundleId !== contracts.sourceManifest.bundle_id) errors.push("expectation bundle ID mismatch");
  if (contracts.publishedRoutes.length !== contracts.expectations.routes.length) errors.push("unknown published route expectation");
  if (contracts.publishedAssets.length !== contracts.expectations.assets.length) errors.push("unknown published asset expectation");
  const omitted = new Set((contracts.expectations.omittedRoutes ?? []).map((item) => item.route_contract_id));
  if (contracts.publishedRoutes.some((item) => omitted.has(item.contract_id))) errors.push("route is both published and omitted");
  return errors;
};
