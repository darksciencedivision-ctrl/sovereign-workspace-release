"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createOperationalState, summarizeDispatch } = require("../control/operational-state");

const worker = (patch = {}) => ({
  nodeId: "node-1", paneId: "pane-1", sessionId: "session-1", pid: 42,
  cwd: "C:/repo", state: "running", operationalState: "READY", nodeAttested: true,
  supervised: true, leaseId: "lease-1", subscriptionRef: "sub-1",
  chrome: { provider: "grok_build", model_slug: "grok-4.5" },
  ...patch,
});

function harness(patch = {}) {
  const records = patch.records || [worker()];
  const mcp = patch.mcp || { state: "connected", fresh: true, last_seen: "now", last_seen_age_ms: 0 };
  return createOperationalState({
    repoRoot: "C:/repo",
    workerRecords: () => records,
    chromeFor: patch.chromeFor || (() => null),
    mcpState: () => mcp,
    sessionEstablished: (state) => ["connected", "stale"].includes(state.state),
    normalizedProvider: (value) => ({ grok: "grok_build" }[value] || value || null),
    conductorLaunch: () => patch.conductorLaunch || { state: "stopped" },
    conductorDescriptor: () => patch.conductorDescriptor || null,
    conductorPaneId: () => "pane-conductor",
  });
}

test("worker projection prefers current pane-owned assignment chrome", () => {
  const state = harness({ chromeFor: () => ({
    provider: "grok_build", model_slug: "grok-4.5", task_status: "IN_PROGRESS",
  }) });
  const status = state.operationalNodeStatus(state.liveWorkerRecords()[0]);
  assert.equal(status.task_status, "IN_PROGRESS");
  assert.equal(status.ready, true);
});

test("established-but-stale MCP remains session-ready while freshness stays explicit", () => {
  const state = harness({ mcp: { state: "stale", fresh: false, last_seen_age_ms: 999 } });
  const status = state.operationalNodeStatus(state.liveWorkerRecords()[0]);
  assert.equal(status.ready, true);
  assert.equal(status.mcp_fresh, false);
});

test("the dispatch sentence and structured legs expose every MCP-unverified READY worker", () => {
  const result = summarizeDispatch([
    { node_id: "n1", pane_id: "p1", ready: true, mcp_fresh: false, mcp_state: "stale" },
    { node_id: "n2", pane_id: "p2", ready: true, mcp_fresh: true, mcp_state: "connected",
      task_status: "IN_PROGRESS" },
  ]);
  assert.match(result.text, /2 READY \(1 MCP-unverified\)/);
  assert.match(result.text, /1 assigned/);
  assert.equal(result.mcp_unverified, 1);
  assert.deepEqual(result.legs.map((leg) => leg.mcp_fresh), [false, true]);
});

test("worker lookup accepts node identity and normalized provider without returning ended records", () => {
  const state = harness({ records: [worker(), worker({ nodeId: "ended", state: "exited" })] });
  assert.equal(state.workerRecordFor({ node_id: "node-1" }).paneId, "pane-1");
  assert.equal(state.workerRecordFor({ provider: "grok" }).nodeId, "node-1");
  assert.equal(state.workerRecordFor({ node_id: "ended" }), null);
});

test("conductor projection uses admitted descriptor and observed MCP state", () => {
  const state = harness({
    conductorLaunch: { state: "running", operationalState: "READY", nodeId: "cond", pid: 7,
      sessionId: "sc", leaseId: "lc", subscriptionRef: "sub" },
    conductorDescriptor: { provider_id: "google_antigravity", model_id: "gemini" },
  });
  const status = state.operationalConductorStatus();
  assert.equal(status.ready, true);
  assert.equal(status.provider_id, "google_antigravity");
  assert.equal(status.mcp_fresh, true);
});
