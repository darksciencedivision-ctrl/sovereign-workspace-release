"use strict";
/**
 * U335 (unit 19.7) — the assignment gate. The property under test is the one the audit found
 * missing: a worker whose PANE is alive and READY, but whose node has not talked to the Sovereign
 * MCP gateway inside the staleness window, is not handed a task.
 *
 * The negative control matters as much: a worker that HAS called recently is assignable, and a
 * refusal writes nothing down, so the same worker becomes assignable again the moment it calls.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { assignmentRefusal } = require("../control/assignment-gate");
const { SovereignControlServer } = require("../control/sovereign-control-server");

const ready = (over = {}) => ({ nodeId: "w-1", state: "running", operationalState: "READY", ...over });
const connected = (over = {}) => ({ state: "connected", fresh: true, last_seen: "2026-08-13T00:00:00.000Z",
  last_seen_age_ms: 12, stale_after_ms: 180000, ...over });

test("a running, READY worker whose node called recently is assignable", () => {
  assert.equal(assignmentRefusal({ nodeId: "w-1", record: ready(), mcp: connected() }), null);
});

test("a READY pane over a node that has gone silent is REFUSED — the audited case", () => {
  const refusal = assignmentRefusal({
    nodeId: "w-1", record: ready(),
    mcp: connected({ state: "stale", fresh: false, last_seen_age_ms: 240000 }),
  });
  assert.ok(refusal, "a stale MCP session must not be assignable off pane state alone");
  assert.equal(refusal.code, "mcp_unverified");
  assert.equal(refusal.retryable, true);
  assert.match(refusal.reason, /UNVERIFIED/);
  assert.match(refusal.reason, /240000 ms ago/);
  assert.match(refusal.reason, /180000 ms staleness window/);
  // The refusal must name an exit that EXISTS in the shipped product, or a conductor reading it will
  // drop a healthy idle worker (or, as round 1 found, follow an instruction to re-run a readiness
  // check that no code path offers for a READY worker).
  assert.match(refusal.reason, /Provoke it with send_message to that node/);
  assert.match(refusal.reason, /clears on the node's next gateway call/);
  assert.equal(refusal.last_seen_age_ms, 240000);
});

test("a node that has never called is refused as never-connected, not as stale", () => {
  const refusal = assignmentRefusal({ nodeId: "w-1", record: ready(),
    mcp: { state: "configured", fresh: false, last_seen: null, last_seen_age_ms: null, stale_after_ms: 180000 } });
  assert.equal(refusal.code, "mcp_never_connected");
  assert.equal(refusal.retryable, true);
});

test("no gateway to ask is a refusal, not a pass — fail closed on ambiguity", () => {
  const refusal = assignmentRefusal({ nodeId: "w-1", record: ready(), mcp: null });
  assert.equal(refusal.code, "mcp_unreadable");
  assert.equal(refusal.mcp_state, null);
});

test("the process is consulted first: a dead pane is reported as dead, never as a connection fault", () => {
  const exited = assignmentRefusal({ nodeId: "w-1", record: ready({ state: "terminating" }),
    mcp: connected({ state: "stale", fresh: false }) });
  assert.equal(exited.code, "worker_not_running");
  assert.equal(exited.retryable, false);
  assert.equal(assignmentRefusal({ nodeId: "w-1", record: null, mcp: connected() }).code, "worker_not_running");
});

test("a pane that has not reached READY keeps its own refusal and its own wording", () => {
  const refusal = assignmentRefusal({ nodeId: "w-1", record: ready({ operationalState: "STALLED" }),
    mcp: connected() });
  assert.equal(refusal.code, "worker_not_ready");
  assert.match(refusal.reason, /is not task-ready \(STALLED\)/);
});

test("the gate reads the REAL gateway: stale refuses, and the node's next call makes it assignable", async () => {
  let clock = 4_000_000;
  const server = new SovereignControlServer({ handlers: { echo: () => ({ ok: true }) },
    staleAfterMs: 5_000, now: () => clock });
  const port = await server.start();
  const token = server.issueCredential({ node_id: "w-1", role: "worker", project_id: "proj" });
  const call = () => fetch(`http://127.0.0.1:${port}/v1/tools/call`, { method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ operation: "echo", arguments: {} }) });
  try {
    await call();
    assert.equal(assignmentRefusal({ nodeId: "w-1", record: ready(), mcp: server.connectionState("w-1") }), null);
    clock += 5_001;
    const refused = assignmentRefusal({ nodeId: "w-1", record: ready(), mcp: server.connectionState("w-1") });
    assert.equal(refused.code, "mcp_unverified");
    // NOTHING was written down by that refusal — the worker record is untouched and the next call
    // from the node restores it. This is what keeps the gate from pinning a healthy idle worker.
    await call();
    assert.equal(assignmentRefusal({ nodeId: "w-1", record: ready(), mcp: server.connectionState("w-1") }), null);
  } finally { await server.stop(); }
});
