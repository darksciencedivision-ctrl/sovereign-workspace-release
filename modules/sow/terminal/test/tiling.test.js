"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const {
  classify, nearSquare, gridGeometry, planLayout, membershipKey, LayoutScheduler, DEFAULT_MAX_VISIBLE,
} = require("../compositor/tiling");
const { PaneModel } = require("../compositor/pane-model");

// helper: a tiling member with sane defaults
const M = (id, over = {}) => ({ id, pinned: false, attention: false, activity: "active", ...over });

// ---- classification (priority classes P0..P4) -------------------------------
test("classify maps pinned+activity to priority classes P0..P4", () => {
  assert.equal(classify(M("a", { pinned: true })), "P0");
  assert.equal(classify(M("b", { activity: "awaiting_operator" })), "P1");
  assert.equal(classify(M("c", { activity: "active" })), "P2");
  assert.equal(classify(M("d", { activity: "background" })), "P3");
  assert.equal(classify(M("e", { activity: "idle" })), "P4");
});

test("pinned overrides activity — an operator-pinned pane is always P0", () => {
  assert.equal(classify(M("a", { pinned: true, activity: "idle" })), "P0");
  assert.equal(classify(M("a", { pinned: true, activity: "background" })), "P0");
});

test("classify fails closed on an unknown activity", () => {
  assert.throws(() => classify(M("a", { activity: "nonsense" })), /unknown pane activity/);
});

// ---- near-square grid (parity with the spike invariants) --------------------
test("near-square grid for n=1..12: fits n and is near-square", () => {
  for (let n = 1; n <= 12; n++) {
    const g = nearSquare(n);
    assert.ok(g.cols * g.rows >= n, `n=${n} fits`);
    assert.ok(g.cols - g.rows <= 1, `n=${n} near-square`);
  }
  assert.deepEqual(nearSquare(6), { cols: 3, rows: 2 });
  assert.deepEqual(nearSquare(8), { cols: 3, rows: 3 });
  assert.deepEqual(nearSquare(0), { cols: 0, rows: 0 });
});

// ---- double cells for P0/P1 -------------------------------------------------
test("P0 and P1 panes get double (span-2) cells and lead the grid", () => {
  const plan = planLayout([
    M("a"),                                   // P2
    M("b", { pinned: true }),                 // P0
    M("c", { activity: "awaiting_operator" }),// P1
  ]);
  // order: P0, P1, then P2
  assert.deepEqual(plan.grid.cells.map((c) => c.id), ["b", "c", "a"]);
  assert.equal(plan.grid.cells[0].span, 2); // b (P0)
  assert.equal(plan.grid.cells[1].span, 2); // c (P1)
  assert.equal(plan.grid.cells[2].span, 1); // a (P2)
});

test("a single pane never gets a double cell", () => {
  const plan = planLayout([M("only", { pinned: true })]);
  assert.equal(plan.grid.cells.length, 1);
  assert.equal(plan.grid.cells[0].span, 1);
});

// ---- visible-set cap + status-card rail -------------------------------------
test("P2 beyond maxVisible collapses to status cards; grid holds the budget", () => {
  const members = Array.from({ length: 9 }, (_, i) => M(`p${i}`)); // 9 active (P2)
  const plan = planLayout(members, { maxVisible: 6 });
  assert.equal(plan.grid.cells.length, 6, "tiled set capped at maxVisible");
  assert.equal(plan.cards.length, 3, "overflow collapses to cards");
  assert.deepEqual(plan.cards.map((c) => c.id), ["p6", "p7", "p8"]);
  assert.ok(plan.cards.every((c) => c.priority === "P2"), "overflow cards keep their class");
});

test("P3/P4 always collapse to cards regardless of budget", () => {
  const plan = planLayout([
    M("a"),                          // P2 -> tiled
    M("b", { activity: "background" }), // P3 -> card
    M("c", { activity: "idle" }),       // P4 -> card
  ], { maxVisible: 6 });
  assert.deepEqual(plan.grid.cells.map((c) => c.id), ["a"]);
  assert.deepEqual(plan.cards.map((c) => c.id), ["b", "c"]);
});

test("cards are ordered P2-overflow first, then background/idle", () => {
  const members = [
    ...Array.from({ length: 7 }, (_, i) => M(`act${i}`)), // 7 P2 (one overflows at mv=6)
    M("bg", { activity: "background" }),
    M("idle", { activity: "idle" }),
  ];
  const plan = planLayout(members, { maxVisible: 6 });
  assert.deepEqual(plan.cards.map((c) => c.id), ["act6", "bg", "idle"]);
});

test("default maxVisible is 6", () => {
  assert.equal(DEFAULT_MAX_VISIBLE, 6);
  const members = Array.from({ length: 8 }, (_, i) => M(`p${i}`));
  assert.equal(planLayout(members).grid.cells.length, 6);
});

test("maxVisible is operator-tunable", () => {
  const members = Array.from({ length: 5 }, (_, i) => M(`p${i}`));
  assert.equal(planLayout(members, { maxVisible: 2 }).grid.cells.length, 2);
  assert.equal(planLayout(members, { maxVisible: 2 }).cards.length, 3);
});

test("maxVisible fails closed on non-positive-integer values", () => {
  for (const bad of [0, -1, 2.5, "6", true, NaN]) {
    assert.throws(() => planLayout([M("a")], { maxVisible: bad }), /maxVisible must be a positive integer/);
  }
});

test("maxVisible null/undefined fall back to the default (unset, not invalid)", () => {
  assert.equal(planLayout([M("a")], { maxVisible: null }).maxVisible, DEFAULT_MAX_VISIBLE);
  assert.equal(planLayout([M("a")], {}).maxVisible, DEFAULT_MAX_VISIBLE);
});

// ---- HARD RULE: P1 (awaiting-operator) can never be auto-collapsed ----------
test("P1 panes are never collapsed to cards even when they exceed maxVisible", () => {
  // 8 panes ALL awaiting operator, budget of 6 — every one must stay tiled (hard rule).
  const members = Array.from({ length: 8 }, (_, i) => M(`ask${i}`, { activity: "awaiting_operator" }));
  const plan = planLayout(members, { maxVisible: 6 });
  assert.equal(plan.grid.cells.length, 8, "all P1 tiled");
  assert.equal(plan.cards.length, 0, "no P1 ever collapses");
  assert.ok(plan.grid.cells.every((c) => c.priority === "P1"));
});

test("P0+P1 reservation squeezes P2 out first; P1 still never collapses", () => {
  const members = [
    M("pin", { pinned: true }),                       // P0
    ...Array.from({ length: 5 }, (_, i) => M(`ask${i}`, { activity: "awaiting_operator" })), // 5 P1
    M("act", { activity: "active" }),                 // P2 -> no budget left (1+5=6), collapses
  ];
  const plan = planLayout(members, { maxVisible: 6 });
  assert.deepEqual(plan.grid.cells.map((c) => c.id).sort(), ["ask0", "ask1", "ask2", "ask3", "ask4", "pin"].sort());
  assert.deepEqual(plan.cards.map((c) => c.id), ["act"]);
  assert.ok(!plan.cards.some((c) => c.priority === "P1" || c.priority === "P0"), "no P0/P1 in rail");
});

// ---- membership key (relayout gate) -----------------------------------------
test("membershipKey is stable under chrome-only changes (attention)", () => {
  const before = [M("a"), M("b")];
  const k1 = membershipKey(before);
  const after = [M("a", { attention: true }), M("b")]; // attention pulse only
  assert.equal(membershipKey(after), k1, "attention must not force a relayout");
});

test("membershipKey changes when priority (activity/pin) changes", () => {
  const base = [M("a"), M("b")];
  const k1 = membershipKey(base);
  assert.notEqual(membershipKey([M("a", { pinned: true }), M("b")]), k1);
  assert.notEqual(membershipKey([M("a", { activity: "idle" }), M("b")]), k1);
});

test("membershipKey changes when maxVisible changes", () => {
  const members = Array.from({ length: 8 }, (_, i) => M(`p${i}`));
  assert.notEqual(membershipKey(members, { maxVisible: 6 }), membershipKey(members, { maxVisible: 4 }));
});

// ---- debounced, membership-gated scheduler ----------------------------------
// deterministic fake timer: records the pending callback; fire() runs it.
function fakeTimer() {
  let nextId = 1, live = new Map(), lastMs = null;
  return {
    api: {
      set: (fn, ms) => { const id = nextId++; live.set(id, fn); lastMs = ms; return id; },
      clear: (id) => { live.delete(id); },
    },
    fire: () => { // fire the single most-recent still-live timer
      const entries = [...live.entries()];
      if (!entries.length) return false;
      const [id, fn] = entries[entries.length - 1];
      live.delete(id);
      fn();
      return true;
    },
    liveCount: () => live.size,
    lastMs: () => lastMs,
  };
}

test("scheduler debounces at 250 ms by default and honors an override", () => {
  const t = fakeTimer();
  const s = new LayoutScheduler({ timer: t.api, onLayout: () => {} });
  s.update([M("a")]);
  assert.equal(t.lastMs(), 250, "Plan §10.2 default debounce is 250 ms");
  const t2 = fakeTimer();
  new LayoutScheduler({ timer: t2.api, debounceMs: 90, onLayout: () => {} }).update([M("a")]);
  assert.equal(t2.lastMs(), 90, "debounce window is configurable");
});

test("scheduler fires one debounced relayout on a membership change", () => {
  const t = fakeTimer();
  const layouts = [];
  const s = new LayoutScheduler({ timer: t.api, onLayout: (p) => layouts.push(p) });
  assert.equal(s.update([M("a")]), true, "membership change scheduled");
  assert.equal(layouts.length, 0, "not fired until debounce elapses");
  t.fire();
  assert.equal(layouts.length, 1, "exactly one relayout");
  assert.deepEqual(layouts[0].grid.cells.map((c) => c.id), ["a"]);
});

test("scheduler ignores chrome-only updates (no relayout scheduled)", () => {
  const t = fakeTimer();
  const layouts = [];
  const s = new LayoutScheduler({ timer: t.api, onLayout: (p) => layouts.push(p) });
  s.update([M("a"), M("b")]);
  t.fire();
  assert.equal(layouts.length, 1);
  // chrome-only change: attention flip -> same membership key -> no new schedule
  assert.equal(s.update([M("a", { attention: true }), M("b")]), false);
  assert.equal(t.liveCount(), 0, "nothing pending");
  assert.equal(layouts.length, 1, "no extra relayout");
});

test("rapid membership changes coalesce into a single relayout with the latest state", () => {
  const t = fakeTimer();
  const layouts = [];
  const s = new LayoutScheduler({ timer: t.api, onLayout: (p) => layouts.push(p) });
  s.update([M("a")]);
  s.update([M("a"), M("b")]);
  s.update([M("a"), M("b"), M("c")]); // three membership changes within the window
  assert.equal(t.liveCount(), 1, "only one pending timer (prior ones cleared)");
  t.fire();
  assert.equal(layouts.length, 1, "coalesced to one relayout");
  assert.deepEqual(layouts[0].grid.cells.map((c) => c.id), ["a", "b", "c"], "latest state wins");
});

test("scheduler.dispose cancels a pending relayout", () => {
  const t = fakeTimer();
  const layouts = [];
  const s = new LayoutScheduler({ timer: t.api, onLayout: (p) => layouts.push(p) });
  s.update([M("a")]);
  s.dispose();
  assert.equal(t.liveCount(), 0);
  assert.equal(t.fire(), false);
  assert.equal(layouts.length, 0);
});

test("scheduler requires an onLayout callback (fail closed)", () => {
  assert.throws(() => new LayoutScheduler({}), /requires an onLayout/);
});

// ---- integration: consumes real PaneModel.tilingMembers() -------------------
test("planLayout consumes PaneModel.tilingMembers() end-to-end", () => {
  const pm = new PaneModel();
  pm.createPane({ id: "p1" });
  pm.createPane({ id: "p2" });
  pm.createPane({ id: "p3" });
  pm.pin("p2");                       // P0
  pm.setActivity("p3", "idle");       // P4 -> card
  const plan = planLayout(pm.tilingMembers(), { maxVisible: 6 });
  assert.deepEqual(plan.grid.cells.map((c) => c.id), ["p2", "p1"]); // P0 then P2; p3 collapsed
  assert.equal(plan.grid.cells[0].span, 2, "pinned p2 double cell");
  assert.deepEqual(plan.cards.map((c) => c.id), ["p3"]);
});
