"use strict";
/**
 * EPC-03 L3-5 (UI) — the DISPATCH line names the panes the node registry knows.
 *
 * Measured before this: the line read `DISPATCH · 2 worker(s) by descriptor · ...` while
 * `worker-A` and `worker-B` were a hardcoded tuple in `conductor_dispatch.py` and the operator's
 * actual panes appeared nowhere on the surface. The count was true about the dispatch and silent
 * about reality, which is the harder kind of wrong to notice.
 *
 * The line must gain presence WITHOUT gaining an execution claim. `panes_live` says panes are up;
 * the legs and the OWED marker remain the only things that speak to what ran.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { conductorDispatchSummary } = require("../compositor/conductor-dispatch");

const BASE = {
  schema: "conductor_dispatch_feed@1.0",
  dispatched: true,
  assigned_count: 2,
  by_descriptor: true,
  accepted_count: 2,
  acceptance_verdict: "PASS",
  legs: { conductor: "mock", workers: "mock" },
  live_workers_owed: { owed: true, issue: "U58" },
};

function withPresence(presence) {
  return { ...BASE, pane_presence: presence };
}

test("live registered panes are named on the line the operator reads", () => {
  const s = conductorDispatchSummary(withPresence({
    panes_present: [{ node_id: "pane-1", live: true }, { node_id: "pane-2", live: true }],
    panes_live: ["pane-1", "pane-2"],
    dispatched_to: ["pane-1", "pane-2"],
    dispatched_to_live_panes: true,
  }));
  assert.match(s.text, /2\/2 pane\(s\) live \(dispatched\)/);
  assert.equal(s.panesLive, 2);
  assert.equal(s.panesPresent, 2);
  assert.equal(s.dispatchedToLivePanes, true);
});

test("a registered pane that is not live is counted as known but not live", () => {
  const s = conductorDispatchSummary(withPresence({
    panes_present: [{ node_id: "pane-1", live: true }, { node_id: "pane-2", live: false }],
    panes_live: ["pane-1"],
    dispatched_to: ["worker-A"],
    dispatched_to_live_panes: false,
  }));
  assert.match(s.text, /1\/2 pane\(s\) live/);
  assert.ok(!/dispatched\)/.test(s.text),
    "a dispatch to ids outside panes_live must not be marked as addressing them");
});

test("a host with no registered pane says so rather than omitting the clause", () => {
  const s = conductorDispatchSummary(withPresence({
    panes_present: [], panes_live: [], dispatched_to: ["worker-A", "worker-B"],
    dispatched_to_live_panes: false,
  }));
  assert.match(s.text, /no registered panes/);
  assert.equal(s.panesLive, 0);
});

test("presence never becomes an execution claim", () => {
  const s = conductorDispatchSummary(withPresence({
    panes_present: [{ node_id: "pane-1", live: true }],
    panes_live: ["pane-1"], dispatched_to: ["pane-1"], dispatched_to_live_panes: true,
  }));
  // The legs and the OWED marker are what say whether anything RAN, and both are untouched.
  assert.equal(s.conductorLeg, "mock");
  assert.equal(s.workersLeg, "mock");
  assert.match(s.text, /legs mock\/mock/);
  assert.match(s.text, /live workers OWED \(U58\)/);
});

test("an unavailable dispatch still reports whether any pane is up", () => {
  const s = conductorDispatchSummary({
    dispatched: false, reason: "plan gate blocked",
    live_workers_owed: { owed: true, issue: "U58" },
    pane_presence: { panes_present: [{ node_id: "pane-1" }], panes_live: ["pane-1"],
                     dispatched_to: [], dispatched_to_live_panes: false },
  });
  assert.match(s.text, /unavailable/);
  assert.match(s.text, /1\/1 pane\(s\) live/);
});

test("a feed with no presence field renders exactly as it did before", () => {
  // The 1.0 feed is still valid input. An older producer must not make the line say something
  // false about the registry, so the clause is absent rather than guessed at zero.
  const s = conductorDispatchSummary(BASE);
  assert.ok(!/pane\(s\) live/.test(s.text), s.text);
  assert.ok(!/no registered panes/.test(s.text), s.text);
  assert.equal(s.panesLive, 0);
});

test("a malformed presence block never throws and never invents a count", () => {
  for (const bad of [{ pane_presence: null }, { pane_presence: 7 },
                     { pane_presence: { panes_live: "two" } }]) {
    const s = conductorDispatchSummary({ ...BASE, ...bad });
    assert.equal(typeof s.text, "string");
    assert.ok(!/pane\(s\) live/.test(s.text), s.text);
  }
});
