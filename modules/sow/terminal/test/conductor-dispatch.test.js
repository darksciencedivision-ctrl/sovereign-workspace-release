"use strict";
/**
 * Conductor DISPATCH chrome tests (Phase 16C `.dispatch`) — the pure render model for pane 1's
 * dispatch line. Proves it draws the summary from the sourced feed and NEVER fabricates or dresses a
 * mock dispatch as live: the legs are stated verbatim and the OWED live-worker leg (U58) is always
 * surfaced; an unavailable/undispatched feed renders an honest "unavailable".
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { conductorDispatchSummary, DISPATCH_LABEL } = require("../compositor/conductor-dispatch");

const GOOD = {
  schema: "conductor_dispatch_feed@1.0",
  dispatched: true,
  objective: "obj",
  assignments: [{ task: "t-1", node: "worker-A", rationale: "by descriptor" }],
  assigned_count: 2,
  by_descriptor: true,
  queued_count: 1,
  accepted_count: 2,
  acceptance_verdict: "PASS",
  acceptance_packet: "m-abc",
  legs: { conductor: "mock", workers: "mock" },
  live_workers_owed: { owed: true, issue: "U58" },
};

test("a governed dispatch renders assignments-by-descriptor, accepted, legs verbatim, and OWED", () => {
  const s = conductorDispatchSummary(GOOD);
  assert.equal(s.dispatched, true);
  assert.equal(s.assigned, 2);
  assert.equal(s.accepted, 2);
  assert.equal(s.queued, 1);
  assert.equal(s.byDescriptor, true);
  assert.equal(s.conductorLeg, "mock");
  assert.equal(s.workersLeg, "mock");
  assert.equal(s.owed, true);
  assert.match(s.text, new RegExp(`^${DISPATCH_LABEL}`));
  assert.match(s.text, /2 worker\(s\) by descriptor/);
  assert.match(s.text, /2 gate-accepted/);
  assert.match(s.text, /1 queued/);
  assert.match(s.text, /legs mock\/mock/);
  assert.match(s.text, /live workers OWED \(U58\)/);
});

test("the legs are stated verbatim — a mock dispatch is NEVER dressed as live", () => {
  const s = conductorDispatchSummary(GOOD);
  assert.ok(!/live\//.test(s.text), "the summary must not claim a live leg for a mock dispatch");
  assert.equal(s.conductorLeg, "mock");
  assert.equal(s.workersLeg, "mock");
});

test("an undispatched feed renders an honest 'unavailable' with the reason + OWED, no fabrication", () => {
  const s = conductorDispatchSummary({ dispatched: false, reason: "plan gate FAIL", live_workers_owed: { owed: true } });
  assert.equal(s.dispatched, false);
  assert.equal(s.reason, "plan gate FAIL");
  assert.match(s.text, /unavailable/);
  assert.match(s.text, /OWED/);
});

test("a null/missing feed fails closed to unavailable (never throws)", () => {
  const s = conductorDispatchSummary(null);
  assert.equal(s.dispatched, false);
  assert.match(s.text, /unavailable/);
});

test("missing counts coerce to 0, not NaN (fail-closed numeric fold)", () => {
  const s = conductorDispatchSummary({ dispatched: true, assignments: [{}], by_descriptor: false,
    legs: { conductor: "mock", workers: "mock" }, live_workers_owed: { owed: true } });
  assert.equal(s.assigned, 0);
  assert.equal(s.accepted, 0);
  assert.ok(!/NaN/.test(s.text));
});
