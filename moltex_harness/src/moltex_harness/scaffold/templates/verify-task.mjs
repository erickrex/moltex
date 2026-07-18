import fs from "node:fs";
import { loadContracts } from "./verify-lib/contracts.mjs";
import { sha256 } from "./verify-lib/files.mjs";
import { checkResult, exitCodeFor, suiteReport, writeJson } from "./verify-lib/results.mjs";

const taskId = process.argv.slice(2).find((item) => !item.startsWith("-"));
if (!/^T\d{3}$/.test(taskId ?? "")) {
  console.error("Usage: npm run verify:task -- T003");
  process.exit(64);
}
const started = Date.now();
const contracts = loadContracts();
const graph = contracts.taskGraph;
const task = graph?.tasks.find((item) => item.task_id === taskId);
const checks = [];
if (!task) {
  checks.push(checkResult({ checkId: "task.exists", status: "fail", severity: "critical", subject: taskId, expected: "task in .moltex/tasks/task-graph.json", actual: null, evidenceRefs: [".moltex/tasks/task-graph.json"], message: `Unknown task ${taskId}` }));
} else {
  const incomplete = task.dependencies.filter((dependency) => {
    const predecessor = graph.tasks.find((item) => item.task_id === dependency);
    return predecessor?.state !== "complete" || !fs.existsSync(`.moltex/task-evidence/${dependency}/execution.json`);
  });
  checks.push(checkResult({ checkId: "task.dependencies", status: incomplete.length ? "blocked" : "pass", severity: incomplete.length ? "critical" : "info", subject: taskId, contractIds: task.contract_ids, evidenceRefs: [`.moltex/tasks/${taskId}.json`], expected: task.dependencies, actual: task.dependencies.filter((item) => !incomplete.includes(item)), message: incomplete.length ? `Incomplete dependencies: ${incomplete.join(", ")}` : "All task dependencies have completion evidence" }));
  const file = `.moltex/task-evidence/${taskId}/execution.json`;
  let evidence = null;
  try { evidence = JSON.parse(fs.readFileSync(file, "utf8")); } catch { /* represented below */ }
  const artifactsValid = evidence && [[evidence.diff_artifact, evidence.diff_sha256], [evidence.session_artifact, evidence.session_sha256]].every(([artifact, digest]) => fs.existsSync(artifact) && sha256(fs.readFileSync(artifact)) === digest);
  const valid = evidence && evidence.task_id === taskId && evidence.protected_paths_unchanged && evidence.command_results.every((item) => item.exit_code === 0) && artifactsValid;
  checks.push(checkResult({ checkId: "task.completion-evidence", status: valid ? "pass" : (task.state === "complete" ? "fail" : "review"), severity: valid ? "info" : (task.state === "complete" ? "critical" : "warning"), subject: taskId, contractIds: task.contract_ids, evidenceRefs: [`.moltex/tasks/${taskId}.json`, file], expected: { successful_commands: true, protected_paths_unchanged: true, checksums: true }, actual: evidence, message: valid ? "Task execution evidence and artifact checksums are valid" : task.state === "complete" ? "Task is complete but its evidence is absent or invalid" : "Task is not complete; completion evidence is not yet required" }));
}
const report = suiteReport({ level: "task", bundleId: contracts.sourceManifest.bundle_id, checks, startedAt: new Date(started).toISOString(), durationMs: Date.now() - started });
const file = `.moltex/reports/tasks/${taskId}.json`;
writeJson(file, report);
console.log(`${taskId}: ${report.status}; report=${file}`);
process.exit(exitCodeFor(report.status));
