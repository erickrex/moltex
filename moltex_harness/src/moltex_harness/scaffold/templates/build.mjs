import { spawnSync } from "node:child_process";
import fs from "node:fs";

const expectedNode = "24.14.0";
const expectedNpm = "10.9.2";
const npmVersion = process.env.npm_config_user_agent?.match(/(?:^|\s)npm\/([^\s]+)/)?.[1] ?? null;
const toolchain = {
  schema_version: 1,
  node: process.versions.node,
  npm: npmVersion,
  expected_node: expectedNode,
  expected_npm: expectedNpm,
};
fs.mkdirSync(".moltex/reports", { recursive: true });
fs.writeFileSync(
  ".moltex/reports/toolchain.json",
  JSON.stringify(toolchain, null, 2) + "\n",
);
if (toolchain.node !== expectedNode || toolchain.npm !== expectedNpm) {
  const message = `Moltex requires Node ${expectedNode} and npm ${expectedNpm}; received Node ${toolchain.node} and npm ${toolchain.npm ?? "unknown"}.`;
  fs.writeFileSync(".moltex/reports/baseline-build.log", message + "\n");
  console.error(message);
  process.exit(1);
}
const build = spawnSync(
  process.execPath,
  ["node_modules/astro/astro.js", "build"],
  { encoding: "utf8" },
);
const output = (build.stdout ?? "") + (build.stderr ?? "");
fs.writeFileSync(".moltex/reports/baseline-build.log", output);
process.stdout.write(build.stdout ?? "");
process.stderr.write(build.stderr ?? "");
if (build.status) process.exit(build.status);

const verification = spawnSync(
  process.execPath,
  ["scripts/verify-baseline.mjs"],
  { stdio: "inherit" },
);
process.exit(verification.status ?? 1);
