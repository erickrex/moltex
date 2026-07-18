import fs from "node:fs";
import path from "node:path";

export const STATUSES = new Set(["pass", "fail", "review", "blocked", "needs_decision", "error"]);
export const SEVERITIES = new Set(["info", "warning", "error", "critical"]);

const stable = (value) => {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
};

export const checkResult = ({
  checkId,
  status,
  severity = status === "pass" ? "info" : "error",
  subject,
  contractIds = [],
  evidenceRefs = [],
  expected = null,
  actual = null,
  message,
  artifacts = [],
  durationMs = 0,
}) => {
  if (!checkId || !subject || !message || !STATUSES.has(status) || !SEVERITIES.has(severity)) {
    throw new Error(`Invalid CheckResult for ${checkId ?? "unknown"}`);
  }
  return {
    schema_version: 1,
    check_id: checkId,
    status,
    severity,
    subject,
    contract_ids: [...new Set(contractIds)].sort(),
    evidence_refs: [...new Set(evidenceRefs)].sort(),
    expected,
    actual,
    message,
    artifacts: [...new Set(artifacts)].sort(),
    duration_ms: Math.max(0, Math.round(durationMs)),
  };
};

export const finding = (result) => ({
  schema_version: 1,
  finding_id: `${result.check_id}:${result.subject}`,
  check_id: result.check_id,
  status: result.status,
  severity: result.severity,
  subject: result.subject,
  contract_ids: result.contract_ids,
  evidence_refs: result.evidence_refs,
  message: result.message,
});

const STATUS_RANK = { pass: 0, review: 1, needs_decision: 2, blocked: 3, fail: 4, error: 5 };
export const aggregateStatus = (checks) => checks.reduce(
  (status, item) => STATUS_RANK[item.status] > STATUS_RANK[status] ? item.status : status,
  "pass",
);

export const writeJson = (file, value) => {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(stable(value), null, 2) + "\n");
};

export const suiteReport = ({ level, bundleId, checks, processes = [], artifacts = [], startedAt, durationMs }) => ({
  schema_version: 1,
  suite: `moltex-${level}`,
  level,
  bundle_id: bundleId,
  status: aggregateStatus(checks),
  started_at: startedAt,
  duration_ms: Math.max(0, Math.round(durationMs)),
  counts: Object.fromEntries([...STATUSES].sort().map((status) => [status, checks.filter((item) => item.status === status).length])),
  checks: [...checks].sort((a, b) => `${a.check_id}:${a.subject}`.localeCompare(`${b.check_id}:${b.subject}`)),
  findings: checks.filter((item) => item.status !== "pass").map(finding),
  processes,
  artifacts,
});

export const exitCodeFor = (status) => ({ pass: 0, review: 0, needs_decision: 2, blocked: 3, fail: 1, error: 4 }[status] ?? 4);
