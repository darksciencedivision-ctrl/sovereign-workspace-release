"use strict";
/**
 * U458 corrective B — a REAL failed control-channel bootstrap, in its own process.
 *
 * The property under test cannot be asserted from inside the process that would leak: "this process
 * exits" is only observable to a parent. So this script performs the failure and does nothing else,
 * and `gateway-bootstrap-teardown.test.js` runs it as a child and watches whether it comes back.
 *
 * The failure injected is a WRONG KEY — a genuine bootstrap failure on the real product path, not a
 * simulated one and not a re-introduction of the U458 signing defect. The gateway mints its own
 * credential; this script connects with a key that is not it, so every envelope is refused for
 * integrity and the supervisor never reaches READY. That is exactly the shape of the condition that
 * left five test files hanging for a whole tier.
 *
 * Exit codes: 0 = the failure was observed AND the gateway was reaped. 1 = the supervisor became
 * ready under a wrong key, which would be a far worse finding than the leak. 2 = setup failed.
 */
const path = require("node:path");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const { IpcClient } = require("../../ipc/client");
const { IpcSupervisor } = require("../../supervisor");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..", "..");

function startGateway() {
  return new Promise((resolve, reject) => {
    const proc = spawn("py", ["-3.12", "-m", "control_plane.ipc.run_gateway"], {
      cwd: REPO_ROOT,
      env: { ...process.env, SOVEREIGN_IPC_NODE: "shell", SOVEREIGN_IPC_ROLE: "shell", SOVEREIGN_IPC_PROJECT: "proj" },
    });
    const vals = {};
    let buf = "";
    const to = setTimeout(() => { proc.kill(); reject(new Error("gateway handshake timed out")); }, 20000);
    proc.stdout.on("data", (d) => {
      buf += d.toString();
      for (const line of buf.split(/\r?\n/)) {
        const m = /^(IPC_PORT|IPC_TOKEN|IPC_KEY)=(.+)$/.exec(line.trim());
        if (m) vals[m[1]] = m[2];
      }
      if (vals.IPC_PORT && vals.IPC_TOKEN && vals.IPC_KEY) {
        clearTimeout(to);
        resolve({ proc, port: Number(vals.IPC_PORT), token: vals.IPC_TOKEN });
      }
    });
    proc.on("error", (e) => { clearTimeout(to); reject(e); });
  });
}

const killAndWait = (proc, timeoutMs = 10000) => new Promise((resolve) => {
  if (!proc || proc.exitCode !== null || proc.signalCode !== null) { resolve(true); return; }
  let settled = false;
  const done = (v) => { if (!settled) { settled = true; clearTimeout(t); resolve(v); } };
  const t = setTimeout(() => done(false), timeoutMs);
  proc.on("exit", () => done(true));
  try { proc.kill(); } catch { done(false); }
});

async function main() {
  let gw;
  try {
    gw = await startGateway();
  } catch (e) {
    process.stderr.write(`setup: ${e.message}\n`);
    return 2;
  }
  // Reported BEFORE anything can fail, so the parent can look for this exact process even if the
  // teardown line below never prints. A global "how many gateways exist" count would be measuring
  // the whole machine — and the desktop suite runs these files concurrently, each with its own.
  process.stdout.write(`GATEWAY_PID ${gw.proc.pid}\n`);
  const client = new IpcClient({
    host: "127.0.0.1", port: gw.port, nodeId: "shell", token: gw.token,
    key: crypto.randomBytes(32).toString("hex"),   // NOT the gateway's key
    timeoutMs: 2000,
  });
  const sup = new IpcSupervisor({ client, heartbeatMs: 60000 });
  try {
    const ready = await sup.start().catch(() => false);
    if (ready === true || sup.ready === true) {
      process.stderr.write("the supervisor reached READY under a wrong key\n");
      return 1;
    }
    process.stdout.write("BOOTSTRAP_FAILED_AS_EXPECTED\n");
    return 0;
  } finally {
    // The whole point. Unconditional, and it WAITS — signalling is not reaping.
    try { sup.stop(); } catch { /* teardown must never throw */ }
    try { client.close(); } catch { /* same */ }
    await killAndWait(gw.proc);
    process.stdout.write(`GATEWAY_REAPED pid=${gw.proc.pid}\n`);
  }
}

main().then((code) => { process.exitCode = code; },
  (e) => { process.stderr.write(`${e && e.stack}\n`); process.exitCode = 2; });
