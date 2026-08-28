"use strict";
/**
 * phase-15e.objective — approval-queue drawer render model (pure/deterministic).
 * Mirrors the inspector-model tests: fold snapshots, fail closed on malformed input, never
 * fabricate or trust an inflated badge count, never drop an unknown-kind row.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  buildApprovalDrawer,
  summarizeApprovalDrawer,
  kindLabel,
} = require("../compositor/approval-drawer");

function snapshot(pending, extra = {}) {
  return { schema: "approval_drawer@1.0", badge_count: pending.length, pending, ...extra };
}

test("folds a snapshot into ordered rows with a derived badge count", () => {
  const view = buildApprovalDrawer(snapshot([
    { item_id: "ap-2", seq: 2, kind: "protected_action", summary: "terminate node-7", origin: "typed", approvable: true, ref: "q-1" },
    { item_id: "ap-1", seq: 1, kind: "plan", summary: "Plan for X", origin: "conductor", approvable: true },
  ]));
  assert.equal(view.ok, true);
  assert.equal(view.badgeCount, 2);
  assert.deepEqual(view.rows.map((r) => r.id), ["ap-1", "ap-2"]); // sorted by seq
  assert.equal(view.rows[0].kindLabel, "Plan");
  assert.equal(view.rows[1].kindLabel, "Protected action");
  assert.equal(view.kindCounts.plan, 1);
  assert.equal(view.kindCounts.protected_action, 1);
});

test("fail closed on a malformed / absent snapshot — empty, ok:false, no fabricated count", () => {
  for (const bad of [null, undefined, 42, "x", []]) {
    const view = buildApprovalDrawer(bad);
    assert.equal(view.ok, false);
    assert.equal(view.badgeCount, 0);
    assert.equal(view.empty, true);
    assert.ok(view.error);
  }
});

test("recomputes the badge from rows — an inflated payload badge_count is ignored", () => {
  const view = buildApprovalDrawer(snapshot(
    [{ item_id: "ap-1", seq: 1, kind: "plan", summary: "p", origin: "conductor", approvable: true }],
    { badge_count: 99 },
  ));
  assert.equal(view.badgeCount, 1); // NOT 99
});

test("an unknown-kind row is surfaced, not dropped", () => {
  const view = buildApprovalDrawer(snapshot([
    { item_id: "ap-1", seq: 1, kind: "brand_new_kind", summary: "?", origin: "conductor", approvable: false },
  ]));
  assert.equal(view.rows.length, 1);
  assert.equal(view.rows[0].kindLabel, "Unknown");
  assert.equal(view.rows[0].known, false);
  assert.equal(view.kindCounts.unknown, 1);
});

test("a row without an id is dropped (cannot be acted on) but others survive", () => {
  const view = buildApprovalDrawer(snapshot([
    { seq: 1, kind: "plan", summary: "no id" },
    { item_id: "ap-2", seq: 2, kind: "plan", summary: "ok", origin: "conductor", approvable: true },
  ]));
  assert.equal(view.rows.length, 1);
  assert.equal(view.rows[0].id, "ap-2");
});

test("approvable defaults to false when the flag is absent/ambiguous (no stray Approve affordance)", () => {
  const view = buildApprovalDrawer(snapshot([
    { item_id: "ap-1", seq: 1, kind: "plan", summary: "p", origin: "conductor" },
    { item_id: "ap-2", seq: 2, kind: "plan", summary: "p", origin: "conductor", approvable: "yes" },
  ]));
  assert.equal(view.rows[0].approvable, false);
  assert.equal(view.rows[1].approvable, false); // only strict true counts
});

test("summarize is deterministic and honest about availability", () => {
  assert.equal(summarizeApprovalDrawer(null), "approvals unavailable");
  assert.equal(summarizeApprovalDrawer({ ok: false }), "approvals unavailable");
  const empty = buildApprovalDrawer(snapshot([]));
  assert.equal(summarizeApprovalDrawer(empty), "no pending approvals");
  const two = buildApprovalDrawer(snapshot([
    { item_id: "ap-1", seq: 1, kind: "plan", summary: "p", origin: "conductor", approvable: true },
    { item_id: "ap-2", seq: 2, kind: "clarification", summary: "c", origin: "voice", approvable: false },
  ]));
  assert.equal(summarizeApprovalDrawer(two), "2 pending (1 plan · 1 clarification)");
});

test("kindLabel maps known kinds and falls back to Unknown", () => {
  assert.equal(kindLabel("plan"), "Plan");
  assert.equal(kindLabel("protected_action"), "Protected action");
  assert.equal(kindLabel("nope"), "Unknown");
});
