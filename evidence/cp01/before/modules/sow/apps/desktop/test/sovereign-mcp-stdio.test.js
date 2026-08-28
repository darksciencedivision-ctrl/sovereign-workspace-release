"use strict";

const { test } = require("node:test");
const assert = require("node:assert");
const { spawn, spawnSync } = require("node:child_process");
const { mkdtempSync, rmSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const readline = require("node:readline");
const { SovereignControlServer } = require("../control/sovereign-control-server");

const ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

test("standard stdio MCP handshake exposes provider-safe Sovereign tools", { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
  const server = new SovereignControlServer({ handlers: { list_models: () => [] } });
  await server.start();
  const temp = mkdtempSync(path.join(os.tmpdir(), "sovereign-mcp-stdio-"));
  const token = server.issueCredential({ node_id: "cond-stdio", role: "conductor", project_id: "proj" });
  const child = spawn("py", ["-3.12", "-m", "mcp_server.sovereign_tools"], {
    cwd: ROOT, env: { ...process.env, SOVEREIGN_CONTROL_PORT: String(server.port),
      SOVEREIGN_CONTROL_TOKEN: token, SOVEREIGN_STORE_ROOT: temp },
  });
  const lines = readline.createInterface({ input: child.stdout });
  const queue = [];
  lines.on("line", (line) => queue.push(JSON.parse(line)));
  const waitFor = async (id) => {
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline) {
      const found = queue.find((r) => r.id === id);
      if (found) return found;
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    throw new Error(`timed out waiting for MCP response ${id}`);
  };
  try {
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {
      protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "test", version: "1" },
    } })}\n`);
    const initialized = await waitFor(1);
    assert.equal(initialized.result.serverInfo.name, "sovereign");
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" })}\n`);
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} })}\n`);
    const listed = await waitFor(2);
    const names = listed.result.tools.map((tool) => tool.name);
    assert.ok(names.includes("spawn_worker"));
    assert.ok(names.includes("send_message"));
    assert.ok(names.includes("open_debate"));
    assert.ok(names.every((name) => /^[A-Za-z0-9_-]+$/.test(name)));
    assert.equal(server.connectionState("cond-stdio").state, "connected");
  } finally {
    child.stdin.end();
    await new Promise((resolve) => child.once("exit", resolve));
    lines.close();
    await server.stop();
    rmSync(temp, { recursive: true, force: true });
  }
});
