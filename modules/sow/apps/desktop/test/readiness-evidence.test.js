"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  processSupervisionObserved, observedReadinessEvidence,
} = require("../control/readiness-evidence");

const record = { supervised: true, pid: 41, sessionGeneration: 3 };

test("process supervision is an exact SessionManager identity observation, not a success literal", () => {
  assert.equal(processSupervisionObserved(record, { pid: 41, generation: 3 }), true);
  assert.equal(processSupervisionObserved(record, { pid: 42, generation: 3 }), false);
  assert.equal(processSupervisionObserved(record, { pid: 41, generation: 4 }), false);
  assert.equal(processSupervisionObserved({ ...record, supervised: false },
    { pid: 41, generation: 3 }), false);
  assert.equal(processSupervisionObserved(record, null), false);
});

test("readiness exposes observations and omits claims this runtime cannot measure", () => {
  const observed = observedReadinessEvidence({
    record,
    processIdentity: { pid: 41, generation: 3 },
    mcpState: { state: "connected" },
    nodeRegistered: true,
  });
  assert.deepEqual(observed, {
    process_supervised: true, node_registered: true, mcp_connected: true,
  });
  for (const unobserved of [
    "provider_authenticated", "workspace_accepted", "mcp_discovered",
    "identity_validated", "permission_resolved",
  ]) assert.equal(unobserved in observed, false, `${unobserved} must be absent`);
});

test("a stale session is established but is not reported connected", () => {
  const observed = observedReadinessEvidence({
    record,
    processIdentity: { pid: 41, generation: 3 },
    mcpState: { state: "stale" },
    nodeRegistered: false,
  });
  assert.equal(observed.mcp_connected, false);
  assert.equal(observed.node_registered, false);
});

test("an unavailable observer produces an absent field rather than a fabricated false", () => {
  const observed = observedReadinessEvidence({ record, processIdentity: undefined });
  assert.equal("process_supervised" in observed, false);
  assert.equal("mcp_connected" in observed, false);
  assert.equal("node_registered" in observed, false);
});
