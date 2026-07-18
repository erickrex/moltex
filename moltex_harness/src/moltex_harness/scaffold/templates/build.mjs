import { spawnSync } from "node:child_process";
import fs from "node:fs";

fs.mkdirSync(".moltex/reports", { recursive: true });
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
