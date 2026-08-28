"use strict";
/**
 * Integration: the REAL IpcSupervisor recovering across a REAL Python gateway RESTART.
 *
 * Directive §9 track 14A requires "UI recovery after process restart": when the control plane
 * goes down and comes back, the shell must (a) fail closed during the gap — admission SHUT,
 * sessions torn down — and (b) re-admit ONLY once the channel is re-verified. This proves the
 * whole edge against live processes, not fakes:
 *
 *   gateway up      -> supervisor SUPERVISED, admission OPEN
 *   gateway KILLED  -> supervisor DEGRADED, onSupervisionLost fires, admission SHUT
 *   gateway RESTART -> supervisor re-probes, RESTORED on a NEW epoch, admission OPEN again
 *
 * The restarted gateway re-issues the SAME per-node credential (IPC_FIXED_TOKEN/IPC_FIXED_KEY),
 * modelling a control plane whose credential store survives a restart, so the shell's existing
 * IpcClient reconnects and re-verifies — the reconnection path itself is what is under test.
 *
 * Requires `py -3.12` on PATH; skips cleanly otherwise (never a spurious fail).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { spawn, spawnSync } = require("node:child_process");
const net = require("node:net");
const crypto = require("node:crypto");
const path = require("node:path");
const { IpcClient } = require("../ipc/client");
const { IpcSupervisor } = require("../supervisor");
const { SessionManager } = require("../../../terminal/conpty/session-manager");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// A free localhost port we can re-bind on restart (allow_reuse_address is set on the server).
function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const p = srv.address().port;
      srv.close(() => resolve(p));
    });
  });
}

// Start run_gateway on a FIXED port with a FIXED credential; resolve once it prints its handshake.
function startGatewayFixed({ port, token, key }) {
  return new Promise((resolve, reject) => {
    const proc = spawn("py", ["-3.12", "-m", "control_plane.ipc.run_gateway", String(port)], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        SOVEREIGN_IPC_NODE: "shell", SOVEREIGN_IPC_ROLE: "shell", SOVEREIGN_IPC_PROJECT: "proj",
        IPC_ALLOW_FIXED_CRED: "1", IPC_FIXED_TOKEN: token, IPC_FIXED_KEY: key,
      },
    });
    let buf = "";
    const to = setTimeout(() => { proc.kill(); reject(new Error("gateway handshake timed out")); }, 15000);
    proc.stdout.on("data", (d) => {
      buf += d.toString();
      if (/IPC_TOKEN=/.test(buf) && /IPC_KEY=/.test(buf) && /IPC_PORT=/.test(buf)) {
        clearTimeout(to);
        resolve(proc);
      }
    });
    proc.on("error", (e) => { clearTimeout(to); reject(e); });
  });
}

/**
 * U458 corrective B. This used to be `proc.on("exit", resolve); proc.kill()`, which HANGS FOREVER on
 * an already-exited child: `exit` has already fired and will not fire again. Harmless while it was
 * only ever called on a live gateway — but the unconditional teardown fence added below calls it on
 * whatever `gw` currently is, which may be a corpse if the test threw after step (b) killed it.
 * A cleanup path that can hang is not a cleanup path.
 */
const killAndWait = (proc, timeoutMs = 10000) => new Promise((resolve) => {
  if (!proc || proc.exitCode !== null || proc.signalCode !== null) { resolve(true); return; }
  let settled = false;
  const done = (v) => { if (!settled) { settled = true; clearTimeout(t); resolve(v); } };
  const t = setTimeout(() => done(false), timeoutMs);
  proc.on("exit", () => done(true));
  try { proc.kill(); } catch { done(false); }
});

test("supervisor recovers across a real gateway restart — fail-closed in the gap, re-admit only after re-verify",
  { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
    const port = await freePort();
    const token = crypto.randomBytes(18).toString("base64url");
    const key = crypto.randomBytes(32).toString("hex");

    let gw = await startGatewayFixed({ port, token, key });
    const client = new IpcClient({ host: "127.0.0.1", port, nodeId: "shell", token, key, timeoutMs: 2000 });

    // U458 corrective B. Everything below used to run un-fenced, with the teardown as the last
    // three statements — so the FIRST failing assertion (which, under W-41's regression, was the
    // very first one) left `gw` alive with its stdout piped here and this process never exited.
    // `gw` is REASSIGNED mid-test, so the fence must close over the variable and not over the
    // value it had when the try opened: it is the CURRENT gateway that has to be reaped.
    try {
    let lost = 0, restored = 0;
    let mgr = null;
    const sup = new IpcSupervisor({
      client, heartbeatMs: 60000,
      // exactly as main.js wires it: the loss edge tears every session down (fail-closed)
      onSupervisionLost: () => { lost += 1; if (mgr) mgr.killAll(); },
      onSupervisionRestored: () => { restored += 1; },
    });

    // (a) up -> SUPERVISED, admission open, epoch 1
    await sup.start();
    assert.strictEqual(sup.ready, true, "must reach SUPERVISED on the live channel");
    assert.strictEqual(sup.supervisionState().epoch, 1);
    const fakePty = { pid: 7, onData() {}, onExit() {}, write() {}, resize() {}, kill() { this.killed = true; } };
    mgr = new SessionManager({ ptyFactory: () => fakePty, supervisor: sup });
    assert.strictEqual(mgr.spawn({ id: "p1", nodeId: "shell", spec: {} }).state, "RUNNING");

    // (b) KILLED -> DEGRADED, onSupervisionLost fires, admission shut, sessions torn down
    await killAndWait(gw);
    await wait(400);
    await sup._probe();
    assert.strictEqual(sup.ready, false, "must be DENIED while the control plane is down");
    assert.strictEqual(sup.supervisionState().state, "DEGRADED");
    assert.strictEqual(lost, 1, "onSupervisionLost must fire on the loss edge");
    assert.strictEqual(fakePty.killed, true, "the running session must be torn down in the gap");
    assert.strictEqual(sup.admit({ id: "x", nodeId: "shell", pid: 1 }).supervised, false);

    // one more failed probe advances DEGRADED -> RECOVERING (still shut)
    await sup._probe();
    assert.strictEqual(sup.supervisionState().state, "RECOVERING");
    assert.strictEqual(sup.ready, false);

    // (c) RESTART on the same port + same credential -> re-probe -> RESTORED on a new epoch
    gw = await startGatewayFixed({ port, token, key });
    await wait(300);
    await sup._probe();
    assert.strictEqual(sup.ready, true, "must re-admit once the channel re-verifies");
    assert.strictEqual(sup.supervisionState().state, "SUPERVISED");
    assert.strictEqual(sup.supervisionState().epoch, 2, "a re-established channel is a new supervision generation");
    assert.strictEqual(restored, 1, "onSupervisionRestored must fire exactly once on recovery");
    // re-admission works ONLY now, on the re-verified channel
    assert.strictEqual(mgr.spawn({ id: "p2", nodeId: "shell", spec: {} }).state, "RUNNING");

    sup.stop();
    } finally {
      client.close();
      await killAndWait(gw);
    }
  });
