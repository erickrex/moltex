import fs from "node:fs";
import { readJson, sha256 } from "./files.mjs";

const CONTRACT_ROOT = ".moltex/contracts";
const contract = (name) => readJson(`${CONTRACT_ROOT}/contracts/${name}.json`, []);

export const loadContracts = () => {
  const index = readJson(`${CONTRACT_ROOT}/contract-index.json`);
  const sourceManifest = readJson(`${CONTRACT_ROOT}/source-manifest.json`);
  const siteSpec = readJson(`${CONTRACT_ROOT}/site-spec.json`);
  return {
    index,
    sourceManifest,
    siteSpec,
    routes: contract("routes"),
    assets: contract("assets"),
    seo: contract("seo"),
    redirects: contract("redirects"),
    capabilities: contract("capabilities"),
    parity: readJson(`${CONTRACT_ROOT}/parity-matrix.json`, []),
    expectations: readJson(".moltex/verification/baseline-expectations.json"),
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
  return errors;
};
