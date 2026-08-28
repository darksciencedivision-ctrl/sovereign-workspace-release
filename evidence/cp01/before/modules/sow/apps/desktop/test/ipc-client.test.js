"use strict";
/**
 * Integration: the shell's Node IpcClient against the REAL Python IPC gateway
 * (control_plane/ipc/run_gateway.py) as a genuinely separate OS process. This is the
 * cross-language proof that the shell speaks the exact D-IPC-01 contract client.py speaks:
 * a Node-built signed envelope@1.0 is accepted by the Python gateway, and the gateway's
 * signed response verifies under the same per-node key. Fail-closed paths (bad token, wrong
 * key) are asserted to drop the connection, not to proceed.
 *
 * Requires `py -3.12` on PATH (canonical interpreter, D-LANG-01) and Node's global WebSocket.
 * Skips with a clear message if the interpreter is unavailable, rather than failing spuriously.
 */
const { test, before, after } = require("node:test");
const assert = require("node:assert");
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");
const { IpcClient, IpcDisconnected } = require("../ipc/client");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

function startGateway(env = {}) {
  return new Promise((resolve, reject) => {
    const proc = spawn("py", ["-3.12", "-m", "control_plane.ipc.run_gateway"], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        SOVEREIGN_IPC_NODE: "shell", SOVEREIGN_IPC_ROLE: "operator", SOVEREIGN_IPC_PROJECT: "proj",
        ...env,
      },
    });
    const vals = {};
    let buf = "";
    const to = setTimeout(() => { proc.kill(); reject(new Error("gateway did not report creds in time")); }, 15000);
    proc.stdout.on("data", (d) => {
      buf += d.toString();
      for (const line of buf.split(/\r?\n/)) {
        const m = /^(IPC_PORT|IPC_TOKEN|IPC_KEY)=(.+)$/.exec(line.trim());
        if (m) vals[m[1]] = m[2];
      }
      if (vals.IPC_PORT && vals.IPC_TOKEN && vals.IPC_KEY) {
        clearTimeout(to);
        resolve({ proc, port: Number(vals.IPC_PORT), token: vals.IPC_TOKEN, key: vals.IPC_KEY });
      }
    });
    proc.on("error", (e) => { clearTimeout(to); reject(e); });
  });
}

let GW = null;
before(async () => { if (HAVE_PY) GW = await startGateway(); });
after(() => { if (GW) GW.proc.kill(); });

test("signed control_event round-trips through the real Python gateway", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const c = new IpcClient({ host: "127.0.0.1", port: GW.port, nodeId: "shell", token: GW.token, key: GW.key });
  const res = await c.controlEvent({ op: "ping", nonce: "hello-42" });
  assert.strictEqual(res.ok, true);
  assert.strictEqual(res.op, "ping");
  assert.strictEqual(res.result.pong, "hello-42");
  assert.strictEqual(res.result.node, "shell");
  c.close();
});

test("an unsupported op returns a signed error payload (not a crash, not a fabrication)", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const c = new IpcClient({ host: "127.0.0.1", port: GW.port, nodeId: "shell", token: GW.token, key: GW.key });
  const res = await c.controlEvent({ op: "definitely-not-real" });
  assert.strictEqual(res.ok, false);
  assert.match(res.error, /unsupported op/);
  c.close();
});

test("a bad credential is dropped by the gateway — client fails closed (IpcDisconnected)", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const c = new IpcClient({ host: "127.0.0.1", port: GW.port, nodeId: "shell", token: "not-a-real-token", key: GW.key });
  await assert.rejects(() => c.controlEvent({ op: "ping" }), IpcDisconnected);
  c.close();
});

test("a wrong integrity key is rejected by the gateway — client fails closed", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  // valid token, but a key that does not match the issued one -> integrity check fails at the gateway
  const wrongKey = "ff".repeat(32);
  const c = new IpcClient({ host: "127.0.0.1", port: GW.port, nodeId: "shell", token: GW.token, key: wrongKey });
  await assert.rejects(() => c.controlEvent({ op: "ping" }), IpcDisconnected);
  c.close();
});

test("a spoofed from_node (identity mismatch) is dropped — client fails closed", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const c = new IpcClient({ host: "127.0.0.1", port: GW.port, nodeId: "not-shell", token: GW.token, key: GW.key });
  await assert.rejects(() => c.controlEvent({ op: "ping" }), IpcDisconnected);
  c.close();
});
