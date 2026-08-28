"use strict";
/**
 * Inspector SOURCE tests — the read glue that feeds the §10.3 inspector from real MCP state.
 *
 * Two layers:
 *   (1) unit — a fake client proves the sweep-all-statuses + fold + fail-closed behaviour
 *       deterministically, with no subprocess;
 *   (2) live integration — the shell's REAL IpcClient reads a REAL seeded MCP server through a
 *       REAL IPC gateway (apps/desktop/test/fixtures/serve_seeded_mcp.py) as separate OS services.
 *       This is the "Node client mirroring client.py reading real MCP resources" proof the
 *       phase-14a.inspector work unit requires — not a mock. Skips cleanly without py -3.12.
 */
const { test, before, after } = require("node:test");
const assert = require("node:assert");
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  ALL_STATUSES, InspectorSourceError, readAllEntries, fetchInspectorModel,
} = require("../inspector/source");
const { IpcClient, IpcDisconnected } = require("../ipc/client");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const FIXTURE = path.join(__dirname, "fixtures", "serve_seeded_mcp.py");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

// ---- (1) unit: fake client ---------------------------------------------------
function fakeClient(entriesByStatus) {
  return {
    calls: [],
    async controlEvent(payload) {
      this.calls.push(payload.status);
      const rows = entriesByStatus[payload.status] || [];
      return { ok: true, op: "read_status", result: rows };
    },
  };
}
const E = (id, over = {}) => ({
  entry_id: id, kind: "finding", status: "ACCEPTED", content_hash: `sha256:${"a".repeat(64)}`,
  provenance: { author_node: "n", task_id: "t-1", ts: "z", directive_version: "v2.4", confidence: "high" },
  ...over,
});

test("readAllEntries sweeps EVERY lifecycle status exactly once", async () => {
  const c = fakeClient({});
  await readAllEntries(c);
  assert.deepEqual(c.calls, ALL_STATUSES);
});

test("readAllEntries dedupes an entry seen at the SAME status, but PRESERVES a cross-status divergence for the fold", async () => {
  const c = fakeClient({
    CANDIDATE: [E("m-1", { status: "CANDIDATE" })],
    ACCEPTED: [E("m-2"), E("m-1", { status: "ACCEPTED" })], // m-1 diverges: two statuses
  });
  const rows = await readAllEntries(c);
  // (id,status) union: m-1 survives at BOTH statuses so buildInspectorModel can flag the anomaly;
  // it is NOT silently collapsed at the read layer (that would swallow the divergence).
  assert.equal(rows.filter((r) => r.entry_id === "m-1").length, 2);
  assert.equal(rows.filter((r) => r.entry_id === "m-2").length, 1);
  // and the divergence reaches the fold's status-divergence anomaly (the safety net is real):
  const { model } = await fetchInspectorModel(c);
  assert.equal(model.anomalies.filter((a) => a.kind === "status-divergence").length, 1);
  const t1 = model.tasks.find((t) => t.taskId === "t-1");
  assert.equal(t1.artifacts.find((a) => a.entryId === "m-1").status, "ACCEPTED"); // most-advanced kept
});

test("fetchInspectorModel folds live rows into the per-task model + honest routingReadable=false", async () => {
  const c = fakeClient({
    CANDIDATE: [E("m-1", { status: "CANDIDATE" })],
    ACCEPTED: [
      E("m-g", { kind: "decision", provenance: { author_node: "gate-1", task_id: "t-1", ts: "z",
        directive_version: "v2.4", confidence: "high", gate_result: "ACCEPTED by gate:gate-1" } }),
      E("m-orphan", { provenance: { author_node: "n", task_id: null, ts: "z",
        directive_version: "v2.4", confidence: "high" } }),
    ],
  });
  const { model, summary, routingReadable } = await fetchInspectorModel(c);
  assert.equal(routingReadable, false);
  const t1 = model.tasks.find((t) => t.taskId === "t-1");
  assert.equal(t1.artifacts.length, 1, "the finding is an artifact");
  assert.equal(t1.gateChain.length, 1, "the decision is a derived gate row");
  assert.equal(t1.gateChain[0].derived, true);
  assert.equal(t1.gateChain[0].verdict, "ACCEPTED by gate:gate-1");
  assert.equal(model.unattributed.artifacts.length, 1, "the null-task entry is unattributed, not dropped");
  assert.equal(summary.taskCount, 1);
});

test("fail-closed: an ok:false payload throws InspectorSourceError (a partial read is a failed read)", async () => {
  const c = {
    async controlEvent(p) {
      if (p.status === "REJECTED") return { ok: false, op: "read_status", error: "policy: denied" };
      return { ok: true, op: "read_status", result: [] };
    },
  };
  await assert.rejects(() => readAllEntries(c), /read_status\(REJECTED\) failed: policy: denied/);
  await assert.rejects(() => readAllEntries(c), InspectorSourceError);
});

test("fail-closed: a transport error PROPAGATES (never a half-built model)", async () => {
  const c = { async controlEvent() { throw new IpcDisconnected("gateway gone"); } };
  await assert.rejects(() => fetchInspectorModel(c), IpcDisconnected);
});

// ---- (2) live: real IpcClient -> real gateway -> real seeded MCP -------------
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

test("LIVE: the inspector source reads REAL seeded MCP entries over the real IPC gateway", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const client = new IpcClient({ host: "127.0.0.1", port: FX.port, nodeId: "shell", token: FX.token, key: FX.key });
  const { model, summary, routingReadable } = await fetchInspectorModel(client);
  client.close();

  // routing is honestly unreadable (ScopedContext is ephemeral) — asserted, never faked
  assert.equal(routingReadable, false);

  // task t-1: exactly the seeded work artifact (finding) + the derived gate row (decision)
  const t1 = model.tasks.find((t) => t.taskId === "t-1");
  assert.ok(t1, "t-1 present from real provenance.task_id");
  assert.equal(t1.artifacts.length, 1, "one non-decision artifact for t-1");
  const art = t1.artifacts[0];
  assert.equal(art.kind, "finding");
  assert.equal(art.status, "CANDIDATE");
  assert.match(art.hash, /^sha256:[0-9a-f]{64}$/, "real CAS content hash surfaced");
  assert.equal(art.author, "worker-A");
  assert.deepEqual(art.provenance.source_artifacts, ["m-objective"], "full provenance survives (need-to-know trace)");

  assert.equal(t1.gateChain.length, 1, "the seeded gate DECISION becomes one derived gate row");
  const g = t1.gateChain[0];
  assert.equal(g.derived, true, "reconstructed from a decision entry, never presented as a native verdict");
  assert.equal(g.verdict, "ACCEPTED by gate:gate-1", "verdict read from real provenance.gate_result");
  assert.equal(g.author, "gate-1");
  assert.equal(g.entryStatus, "ACCEPTED");

  // the unattributed CANDIDATE is visible, not dropped (invariant 27)
  assert.equal(model.unattributed.artifacts.length, 1, "orphan entry surfaced in unattributed bucket");
  assert.equal(model.unattributed.artifacts[0].author, "worker-B");

  assert.equal(summary.taskCount, 1);
  assert.equal(summary.unattributedCount, 1);
});

test("LIVE: fail-closed — a wrong integrity key drops the connection (no fabricated model)", { skip: !HAVE_PY && "py -3.12 unavailable" }, async () => {
  const client = new IpcClient({ host: "127.0.0.1", port: FX.port, nodeId: "shell", token: FX.token, key: "ff".repeat(32) });
  await assert.rejects(() => fetchInspectorModel(client), IpcDisconnected);
  client.close();
});
