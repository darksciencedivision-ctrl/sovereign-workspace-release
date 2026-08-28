"use strict";
/**
 * Integration: the REAL IpcSupervisor wired to the REAL Python gateway (the exact
 * configuration apps/desktop/main.js launches — default EchoControlSurface, no --mcp).
 *
 * This closes the gap the gate-validator flagged: the supervisor's readiness heartbeat
 * (op:"health") must actually be satisfiable by the gateway the shell spawns, so admission
 * reaches supervised:true and a terminal node can spawn — AND it must flip to teardown when
 * the control-plane channel is lost. Both are asserted here against live processes, not fakes.
 */
const { test, before, after } = require("node:test");
const assert = require("node:assert");
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");
const { IpcClient, IpcBusy, IpcDisconnected } = require("../ipc/client");
const { IpcSupervisor, MAX_BUSY_SKIPS } = require("../supervisor");
const { SessionManager } = require("../../../terminal/conpty/session-manager");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

function startGateway() {
  return new Promise((resolve, reject) => {
    const proc = spawn("py", ["-3.12", "-m", "control_plane.ipc.run_gateway"], {
      cwd: REPO_ROOT,
      env: { ...process.env, SOVEREIGN_IPC_NODE: "shell", SOVEREIGN_IPC_ROLE: "shell", SOVEREIGN_IPC_PROJECT: "proj" },
    });
    const vals = {};
    let buf = "";
    const to = setTimeout(() => { proc.kill(); reject(new Error("gateway handshake timed out")); }, 15000);
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

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/** U458 corrective B: kill AND wait for the exit. `kill()` alone returns before the child is
 *  reaped, so a caller that only signals can still leave the handle attached to this event loop. */
const killAndWait = (proc, timeoutMs = 10000) => new Promise((resolve) => {
  if (!proc || proc.exitCode !== null || proc.signalCode !== null) { resolve(true); return; }
  let settled = false;
  const done = (v) => { if (!settled) { settled = true; clearTimeout(t); resolve(v); } };
  const t = setTimeout(() => done(false), timeoutMs);
  proc.on("exit", () => done(true));
  try { proc.kill(); } catch { done(false); }
});

let GW = null;
before(async () => { if (HAVE_PY) GW = await startGateway(); });
after(async () => { if (GW) await killAndWait(GW.proc); });

test("a never-started supervisor refuses admission (fail-closed before any probe)", () => {
  const sup = new IpcSupervisor({ client: { controlEvent: async () => ({ ok: true }) } });
  assert.strictEqual(sup.ready, false);
  assert.strictEqual(sup.admit({ id: "s1", nodeId: "n", pid: 1 }).supervised, false);
});

test("health heartbeat reaches READY against the default (echo) gateway main.js spawns", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const client = new IpcClient({ host: "127.0.0.1", port: GW.port, nodeId: "shell", token: GW.token, key: GW.key, timeoutMs: 2000 });
  const sup = new IpcSupervisor({ client, heartbeatMs: 60000 });
  const ready = await sup.start();
  assert.strictEqual(ready, true, "supervisor must reach READY on a verified channel");
  assert.strictEqual(sup.admit({ id: "s1", nodeId: "shell", pid: 42 }).supervised, true);
  sup.stop();
  client.close();
});

test("an admitted SessionManager spawns a supervised session against the live channel", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const client = new IpcClient({ host: "127.0.0.1", port: GW.port, nodeId: "shell", token: GW.token, key: GW.key, timeoutMs: 2000 });
  const sup = new IpcSupervisor({ client, heartbeatMs: 60000 });
  await sup.start();
  // fake pty so no native addon is needed; the supervision path is the real one
  const fakePty = { pid: 999, onData() {}, onExit() {}, write() {}, resize() {}, kill() { this.killed = true; } };
  const mgr = new SessionManager({ ptyFactory: () => fakePty, supervisor: sup });
  const s = mgr.spawn({ id: "p1", nodeId: "shell", spec: {} });
  assert.strictEqual(s.state, "RUNNING");
  assert.strictEqual(fakePty.killed, undefined); // admitted -> not killed
  mgr.killAll();
  sup.stop();
  client.close();
});

// ---- BUSY is not LOST (Phase 17A `.roundtrip`) ------------------------------
// The sequential control channel carries both the 5 s health heartbeat and `notify()`'s
// session-event reports, so they collide. Scoring that collision as "supervision LOST" tore down
// every session — including the operator's live conductor mid-conversation — on evidence that the
// channel was ALIVE. Observed once in three live self-check runs; found by the gate-validator.
test("a BUSY channel is a skipped beat, not a supervision loss", async () => {
  let lostFired = false;
  const client = {
    controlEvent: async () => { throw new IpcBusy("control channel is busy (one request in flight)"); },
  };
  const sup = new IpcSupervisor({ client, heartbeatMs: 60000, onSupervisionLost: () => { lostFired = true; } });
  // reach READY on a real answer first, then start colliding
  sup._client = { controlEvent: async () => ({ ok: true }) };
  await sup.start();
  assert.strictEqual(sup.ready, true);
  sup._client = client;
  await sup._probe();
  assert.strictEqual(sup.ready, true, "one busy beat must not tear the operator's sessions down");
  assert.strictEqual(lostFired, false);
  sup.stop();
});

test("BUSY forever is still fail-closed once the skip budget is spent", async () => {
  let lostFired = false;
  const sup = new IpcSupervisor({
    client: { controlEvent: async () => ({ ok: true }) },
    heartbeatMs: 60000,
    onSupervisionLost: () => { lostFired = true; },
  });
  await sup.start();
  assert.strictEqual(sup.ready, true);
  sup._client = {
    controlEvent: async () => { throw new IpcBusy("control channel is busy (one request in flight)"); },
  };
  for (let i = 0; i < MAX_BUSY_SKIPS; i++) await sup._probe();
  assert.strictEqual(sup.ready, true, `${MAX_BUSY_SKIPS} skips are within budget`);
  await sup._probe();                       // one beat past the budget
  assert.strictEqual(sup.ready, false, "a channel that is busy forever is not a verified channel");
  assert.strictEqual(lostFired, true);
  sup.stop();
});

test("a genuine transport fault is still an IMMEDIATE loss (no skip budget)", async () => {
  let lostFired = false;
  const sup = new IpcSupervisor({
    client: { controlEvent: async () => ({ ok: true }) },
    heartbeatMs: 60000,
    onSupervisionLost: () => { lostFired = true; },
  });
  await sup.start();
  sup._client = { controlEvent: async () => { throw new IpcDisconnected("socket closed"); } };
  await sup._probe();
  assert.strictEqual(sup.ready, false);
  assert.strictEqual(lostFired, true);
  sup.stop();
});

test("a busy beat does not spend the budget once the channel answers again", async () => {
  const sup = new IpcSupervisor({ client: { controlEvent: async () => ({ ok: true }) }, heartbeatMs: 60000 });
  await sup.start();
  const busy = { controlEvent: async () => { throw new IpcBusy("busy"); } };
  const ok = { controlEvent: async () => ({ ok: true }) };
  for (let i = 0; i < 10; i++) {
    sup._client = busy; await sup._probe();
    sup._client = ok; await sup._probe();
  }
  assert.strictEqual(sup.ready, true, "an intermittent collision must never accumulate into a loss");
  sup.stop();
});

test("losing the control-plane channel flips to DENIED and tears sessions down", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const gw = await startGateway(); // a private gateway we can kill without disturbing the shared one
  const client = new IpcClient({ host: "127.0.0.1", port: gw.port, nodeId: "shell", token: gw.token, key: gw.key, timeoutMs: 2000 });
  // U458 corrective B. The teardown below used to be the LAST STATEMENTS of the test body, so any
  // assertion that threw skipped them — the private gateway stayed alive with its stdout piped
  // here, the event loop never drained, and `node --test` (which runs with --test-timeout=0) never
  // returned. A suite that cannot report is worse than one that reports red: that is why W-41's
  // regression went unnoticed for a whole tier. The cleanup is unconditional now.
  try {
    let lostFired = false;
    const sup = new IpcSupervisor({ client, heartbeatMs: 60000, onSupervisionLost: () => { lostFired = true; } });
    try {
      await sup.start();
      assert.strictEqual(sup.ready, true);

      gw.proc.kill();            // kill the governor
      await wait(400);           // let the socket close propagate
      await sup._probe();        // force the next heartbeat deterministically

      assert.strictEqual(sup.ready, false, "must go DENIED when the channel is lost");
      assert.strictEqual(lostFired, true, "onSupervisionLost must fire so the manager tears sessions down");
      assert.strictEqual(sup.admit({ id: "s", nodeId: "shell", pid: 1 }).supervised, false);
    } finally {
      sup.stop();
    }
  } finally {
    client.close();
    await killAndWait(gw.proc);
  }
});
