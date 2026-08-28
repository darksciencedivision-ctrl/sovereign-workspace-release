"use strict";
/**
 * Status-bar SOURCE tests (phase-15a.statusbar) — the read glue that feeds the §11/15A status bar
 * from the REAL subscription governor's count over the D-IPC-01 channel.
 *
 * Two layers, mirroring the inspector source:
 *   (1) unit — a fake client proves the strict fetch + fail-closed display fold deterministically,
 *       with no subprocess;
 *   (2) live integration — the shell's REAL IpcClient reads a REAL seeded SubscriptionGovernor
 *       through a REAL IPC gateway (apps/desktop/test/fixtures/serve_seeded_governor.py) as
 *       separate OS services. This is the "Node client mirroring the IPC read path" the
 *       phase-15a.statusbar work unit requires — not a mock. Skips cleanly without py -3.12.
 */
const { test, before, after } = require("node:test");
const assert = require("node:assert");
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  StatusBarSourceError, fetchSubscriptionStatus, fetchStatusBarModel,
} = require("../statusbar/source");
const { IpcClient, IpcDisconnected } = require("../ipc/client");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const FIXTURE = path.join(__dirname, "fixtures", "serve_seeded_governor.py");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const row = (model, provider) => model.rows.find((r) => r.provider === provider);

// ---- (1) unit: fake client ---------------------------------------------------
function fakeClient(result, ok = true, error = null) {
  return {
    calls: [],
    async controlEvent(payload) {
      this.calls.push(payload.op);
      return ok ? { ok: true, op: payload.op, result } : { ok: false, op: payload.op, error };
    },
  };
}

test("fetchSubscriptionStatus calls exactly the read-only subscription_status op", async () => {
  const c = fakeClient({});
  await fetchSubscriptionStatus(c);
  assert.deepEqual(c.calls, ["subscription_status"]);
});

test("fetchStatusBarModel folds a live governor dict into n/2 rows", async () => {
  const c = fakeClient({
    "sub-anthropic": { provider: "claude_code", allowance: 2, active: ["a"], in_use: 1 },
    "sub-openai": { provider: "openai_codex_cli", allowance: 2, active: [], in_use: 0 },
  });
  const m = await fetchStatusBarModel(c);
  assert.equal(m.readable, true);
  assert.equal(row(m, "claude_code").label, "1/2");
  assert.equal(row(m, "openai_codex_cli").label, "0/2");
  assert.equal(m.summary.totalInUse, 1);
  assert.ok(!("error" in m), "no error on a clean read");
});

test("STRICT fetch fails closed: an ok:false payload throws StatusBarSourceError", async () => {
  const c = fakeClient(null, false, "surface fault");
  await assert.rejects(() => fetchSubscriptionStatus(c), StatusBarSourceError);
  await assert.rejects(() => fetchSubscriptionStatus(c), /subscription_status failed: surface fault/);
});

test("DISPLAY fold fails closed on ok:false: unknown model + error, NEVER a fabricated count", async () => {
  const c = fakeClient(null, false, "unsupported op 'subscription_status'");
  const m = await fetchStatusBarModel(c);
  assert.equal(m.readable, false);
  assert.ok(m.rows.every((r) => r.state === "unknown" && r.inUse === null));
  assert.ok(m.rows.every((r) => r.label.startsWith("—/")), "em-dash, not 0");
  assert.match(m.error, /unsupported op/);
});

test("DISPLAY fold fails closed on a transport fault: unknown model, error carried, no throw", async () => {
  const c = { async controlEvent() { throw new IpcDisconnected("gateway gone"); } };
  const m = await fetchStatusBarModel(c); // must NOT throw — the bar is always visible
  assert.equal(m.readable, false);
  assert.match(m.error, /gateway gone/); // the transport fault message is carried, not swallowed
});

// ---- (2) live: real IpcClient -> real gateway -> real seeded governor --------
function startFixture() {
  return new Promise((resolve, reject) => {
    const proc = spawn("py", ["-3.12", FIXTURE], { cwd: REPO_ROOT, env: { ...process.env } });
    const vals = {};
    let buf = "", err = "";
    const to = setTimeout(() => { proc.kill(); reject(new Error(`fixture creds timeout; stderr=${err}`)); }, 20000);
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
    proc.stderr.on("data", (d) => { err += d.toString(); });
    proc.on("error", (e) => { clearTimeout(to); reject(e); });
  });
}

let FX = null;
before(async () => { if (HAVE_PY) FX = await startFixture(); });
after(() => { if (FX) FX.proc.kill(); });

test("LIVE: the status-bar source reads the REAL seeded governor n/2 over the real IPC gateway", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const client = new IpcClient({ host: "127.0.0.1", port: FX.port, nodeId: "shell", token: FX.token, key: FX.key });
  const m = await fetchStatusBarModel(client);
  client.close();

  assert.equal(m.readable, true, "the governor was read for real, not faked");
  assert.equal(m.cap, 2);

  // seeded Anthropic subscription: one live terminal -> 1/2 active (a real acquire, real count)
  const a = row(m, "claude_code");
  assert.equal(a.subscriptionRef, "sub-anthropic");
  assert.equal(a.label, "1/2");
  assert.equal(a.inUse, 1);
  assert.equal(a.allowance, 2);
  assert.equal(a.state, "active");

  // seeded OpenAI subscription: no acquire -> honest 0/2 idle (read-and-empty, not unknown)
  const o = row(m, "openai_codex_cli");
  assert.equal(o.subscriptionRef, "sub-openai");
  assert.equal(o.label, "0/2");
  assert.equal(o.state, "idle");

  assert.equal(m.summary.totalInUse, 1);
});

test("LIVE: fail-closed — a wrong integrity key yields an unknown model, no fabricated count", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const client = new IpcClient({ host: "127.0.0.1", port: FX.port, nodeId: "shell", token: FX.token, key: "ff".repeat(32) });
  const m = await fetchStatusBarModel(client); // display contract: degrade, never throw
  client.close();
  assert.equal(m.readable, false);
  assert.ok(m.rows.every((r) => r.state === "unknown" && r.inUse === null));
  assert.ok(m.error, "the integrity failure is surfaced, not hidden");
});
