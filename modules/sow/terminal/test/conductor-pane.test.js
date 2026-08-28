"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const {
  CONDUCTOR_LABEL,
  SUCCESSION_LABEL,
  conductorBadge,
  conductorSuccessionControl,
  conductorPaneSpec,
} = require("../compositor/conductor-pane");
const { PaneModel } = require("../compositor/pane-model");

// a conductor selection record as the Python `ConductorBinding.as_record()` produces it
const REC = (over = {}) => ({
  selection: { model: "fable-5", reason: "operator_selected", since: "2026-07-19T00:00:00+00:00" },
  executing: { model: null, verified: false, is_fallback: false, ...over.executing },
  ...over,
});

// ---- badge honesty (invariant 3) --------------------------------------------
test("badge shows the SELECTION label, unverified until a live reply", () => {
  const b = conductorBadge(REC());
  assert.equal(b.label, "CONDUCTOR");
  assert.equal(b.model, "fable-5");
  assert.equal(b.verified, false);
  assert.equal(b.executing, null); // nothing ran ⇒ no checkpoint id
  assert.equal(b.mode, "attended");
  assert.equal(b.pinned, true);
  assert.equal(b.paneOrdinal, 1);
});

test("badge surfaces a verified executing checkpoint when the record reports one", () => {
  const b = conductorBadge(REC({ executing: { model: "claude-fable-5-20260101", verified: true } }));
  assert.equal(b.verified, true);
  assert.equal(b.executing, "claude-fable-5-20260101");
});

test("badge fails closed to (unknown selection) — never fabricates a model", () => {
  assert.equal(conductorBadge({}).model, "(unknown selection)");
  assert.equal(conductorBadge({ selection: { model: "   " } }).model, "(unknown selection)");
  assert.equal(conductorBadge(null).verified, false);
});

test("badge marks the recorded CLI-default fallback", () => {
  const b = conductorBadge(REC({ executing: { is_fallback: true, model: null, verified: false } }));
  assert.equal(b.isFallback, true);
});

// ---- succession control -----------------------------------------------------
test("succession control is Resume→Select and reachable when available", () => {
  const c = conductorSuccessionControl({
    available: true, control: "resume_select",
    actions: ["resume", "select", "restore"], restore_target: "fable-5",
  });
  assert.equal(c.available, true);
  assert.equal(c.label, SUCCESSION_LABEL);
  assert.deepEqual(c.actions, ["resume", "select", "restore"]);
  assert.equal(c.restoreTarget, "fable-5");
});

test("succession control fails closed to unavailable on a missing/untrusted affordance", () => {
  assert.equal(conductorSuccessionControl(null).available, false);
  assert.equal(conductorSuccessionControl({ available: false }).available, false);
  assert.equal(conductorSuccessionControl({}).label, SUCCESSION_LABEL);
});

// ---- pane-1 conductor-first spec --------------------------------------------
const CHROME = (over = {}) => ({
  role: "conductor", pane_ordinal: 1, pinned: true, mode: "attended", interactive: true,
  governed: true, node_state: "ready", model_label: "fable-5", model_verified: false,
  is_fallback: false, subscription: { ref: "claude-sub", in_use: 1, allowance: 2 },
  succession: { available: true, actions: ["resume", "select", "restore"], restore_target: "fable-5" },
  ...over,
});

test("conductorPaneSpec produces a pinned pane-1 CONDUCTOR spec", () => {
  const s = conductorPaneSpec(CHROME());
  assert.equal(s.ordinal, 1);
  assert.equal(s.pinned, true);
  assert.equal(s.label, "CONDUCTOR");
  assert.equal(s.role, "conductor");
  assert.equal(s.mode, "attended");
  assert.equal(s.interactive, true);
  assert.equal(s.governed, true);
  assert.equal(s.badge.model, "fable-5");
  assert.equal(s.badge.verified, false);
  assert.equal(s.succession.available, true);
  assert.deepEqual(s.subscription, { ref: "claude-sub", in_use: 1, allowance: 2 });
});

test("conductorPaneSpec refuses a non-conductor chrome — never brand a worker CONDUCTOR", () => {
  assert.throws(() => conductorPaneSpec(CHROME({ role: "reasoning" })), /conductor-role/);
  assert.throws(() => conductorPaneSpec(null), /conductor-role/);
});

test("conductorPaneSpec surfaces an honest awaiting state before a live launch", () => {
  const s = conductorPaneSpec(CHROME({ node_state: "awaiting_live_conductor" }));
  assert.equal(s.nodeState, "awaiting_live_conductor");
});

// ---- integration with PaneModel: pinned pane-1 stays visible (tiling P0) ------
test("a pinned conductor pane-1 is never auto-collapsed out of the visible set", () => {
  const panes = new PaneModel();
  panes.createPane({ id: "pane-conductor", title: "CONDUCTOR" });
  panes.pin("pane-conductor");
  for (let i = 0; i < 8; i++) panes.createPane({ id: `w${i}`, title: `worker ${i}` });
  const members = panes.tilingMembers();
  const conductor = members.find((m) => m.id === "pane-conductor");
  assert.ok(conductor, "conductor pane present in tiling members");
  assert.equal(conductor.pinned, true); // pinned ⇒ P0 ⇒ always tiled (never auto-collapsed)
});
