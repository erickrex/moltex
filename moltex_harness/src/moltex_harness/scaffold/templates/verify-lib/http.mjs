import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";

const allocatePort = () => new Promise((resolve, reject) => {
  const server = net.createServer();
  server.unref();
  server.once("error", reject);
  server.listen(0, "127.0.0.1", () => {
    const { port } = server.address();
    server.close(() => resolve(port));
  });
});

const waitForReady = async (url, child, timeoutMs = 15000) => {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Preview exited before readiness with ${child.exitCode}`);
    try {
      const response = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(1000) });
      if (response.status < 500) return response.status;
    } catch (error) { lastError = error; }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Preview readiness timed out: ${lastError?.message ?? "no response"}`);
};

const closeChild = async (child) => {
  if (child.exitCode !== null) return child.exitCode;
  const exited = new Promise((resolve) => child.once("exit", (code) => resolve(code)));
  child.kill("SIGTERM");
  const result = await Promise.race([exited, new Promise((resolve) => setTimeout(() => resolve(null), 3000))]);
  if (result === null && child.exitCode === null) child.kill("SIGKILL");
  await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 2000))]);
  return child.exitCode;
};

export const withPreview = async (action) => {
  const started = Date.now();
  const port = await allocatePort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const logFile = ".moltex/reports/processes/preview.log";
  fs.mkdirSync(path.dirname(logFile), { recursive: true });
  const output = fs.createWriteStream(logFile, { flags: "w" });
  const child = spawn(process.execPath, ["node_modules/astro/astro.js", "preview", "--host", "127.0.0.1", "--port", String(port)], {
    cwd: process.cwd(), env: { ...process.env, NO_COLOR: "1" }, stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
  });
  child.stdout.pipe(output);
  child.stderr.pipe(output);
  const processResult = {
    schema_version: 1, process_id: "astro-preview", command: [process.execPath, "node_modules/astro/astro.js", "preview", "--host", "127.0.0.1", "--port", String(port)],
    pid: child.pid, host: "127.0.0.1", port, status: "starting", started_at: new Date(started).toISOString(), duration_ms: 0,
    readiness_attempts: 1, exit_code: null, log_artifact: logFile,
  };
  try {
    processResult.readiness_status = await waitForReady(baseUrl, child);
    processResult.status = "ready";
    return { value: await action(baseUrl), processResult };
  } catch (error) {
    processResult.status = "error";
    processResult.error = error.message;
    throw Object.assign(error, { processResult });
  } finally {
    processResult.exit_code = await closeChild(child);
    processResult.duration_ms = Date.now() - started;
    processResult.status = processResult.status === "error" ? "error" : "stopped";
    output.end();
  }
};

export const requestArtifact = async (baseUrl, route, artifact) => {
  const started = Date.now();
  const response = await fetch(new URL(route, baseUrl), { redirect: "manual", signal: AbortSignal.timeout(5000) });
  const body = Buffer.from(await response.arrayBuffer());
  const headers = Object.fromEntries([...response.headers.entries()].sort(([a], [b]) => a.localeCompare(b)));
  const record = { schema_version: 1, url: new URL(route, baseUrl).href, status: response.status, headers, bytes: body.length, duration_ms: Date.now() - started };
  fs.mkdirSync(path.dirname(artifact), { recursive: true });
  fs.writeFileSync(artifact, JSON.stringify(record, null, 2) + "\n");
  return { response, body, record };
};
