"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  PROVIDER_STATES, classifyProviderScreen, occurrenceCount, structuredProviderFailure,
} = require("../control/provider-readiness");

test("Grok overlays and setup screens can never be READY", () => {
  const r = classifyProviderScreen("grok_build", "What's New — Connectors available. Press Enter to continue");
  assert.equal(r.state, "PROVIDER_SETUP_REQUIRED");
  assert.equal(r.terminal_state, "AWAITING_PROVIDER_SETUP");
  assert.ok(PROVIDER_STATES.includes(r.state));
});

test("Grok quota exhaustion is an exact setup state, never a generic readiness timeout", () => {
  const r = classifyProviderScreen("grok_build",
    "You've reached your free Grok Build usage limit for now. Get SuperGrok or try again later.");
  assert.equal(r.state, "PROVIDER_SETUP_REQUIRED");
  assert.equal(r.terminal_state, "USAGE_LIMIT");
});

test("Gemini Plan UI and unresolved Sovereign permission are distinguished", () => {
  assert.equal(classifyProviderScreen("google_antigravity", "Review plan · Gemini 3.6 Flash").state,
    "PROVIDER_SETUP_REQUIRED");
  assert.equal(classifyProviderScreen("google_antigravity", "Permission required: allow Sovereign MCP tool").state,
    "MCP_PERMISSION_REQUIRED");
});

test("a first echoed token cannot satisfy a two-occurrence response boundary", () => {
  assert.equal(occurrenceCount("prompt READY_X", "READY_X"), 1);
  assert.equal(occurrenceCount("prompt READY_X\nanswer READY_X", "READY_X"), 2);
});

test("worker timeouts carry every required structured failure field", () => {
  const f = structuredProviderFailure({ provider: "grok_build", model: "grok-4.5", nodeId: "g1",
    taskId: "t1", stage: "second_readiness_response", leaseState: "active", processState: "running" });
  for (const key of ["provider", "model", "node_id", "task_id", "stage",
    "last_successful_mcp_operation", "last_progress_timestamp", "provider_terminal_state",
    "lease_state", "process_state", "retry_eligibility"]) assert.ok(Object.hasOwn(f, key), key);
});
