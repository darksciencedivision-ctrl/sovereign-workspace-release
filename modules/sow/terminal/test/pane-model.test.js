"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { PaneModel } = require("../compositor/pane-model");

test("a new pane takes focus", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  assert.strictEqual(m.focusedId, "p1");
  m.createPane({ id: "p2" });
  assert.strictEqual(m.focusedId, "p2");
  assert.strictEqual(m.size(), 2);
});

test("a session can be attached to a placeholder pane (the conductor's live launch)", () => {
  const m = new PaneModel();
  m.createPane({ id: "pane-1", sessionId: null, title: "CONDUCTOR" });
  assert.strictEqual(m.get("pane-1").sessionId, null);
  m.attachSession("pane-1", "pane-1");
  assert.strictEqual(m.get("pane-1").sessionId, "pane-1");
  assert.throws(() => m.attachSession("nope", "s"), /unknown pane/);
  assert.throws(() => m.attachSession("pane-1", ""), /requires a sessionId/);
});

test("duplicate pane id is refused", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  assert.throws(() => m.createPane({ id: "p1" }), /duplicate pane/);
});

test("operations on an unknown pane fail closed", () => {
  const m = new PaneModel();
  for (const op of ["focus", "maximize", "minimize", "pin", "destroyPane"]) {
    assert.throws(() => m[op]("nope"), /unknown pane/);
  }
});

test("destroying the focused pane reassigns focus to the previously focused pane", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  m.createPane({ id: "p2" });
  m.createPane({ id: "p3" }); // focus p3, history [p1,p2,p3]
  m.focus("p1");              // history [p2,p3,p1]
  m.destroyPane("p1");        // focus falls back to p3 (most-recent surviving)
  assert.strictEqual(m.focusedId, "p3");
});

test("destroying the last pane leaves focus null", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  m.destroyPane("p1");
  assert.strictEqual(m.focusedId, null);
  assert.strictEqual(m.visible().length, 0);
});

test("maximize shows only the maximized pane; restore returns to the tiled set", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  m.createPane({ id: "p2" });
  m.maximize("p1");
  assert.strictEqual(m.maximizedId, "p1");
  assert.deepStrictEqual(m.visible().map((p) => p.id), ["p1"]);
  assert.strictEqual(m.focusedId, "p1");
  m.restore("p1");
  assert.strictEqual(m.maximizedId, null);
  assert.deepStrictEqual(m.visible().map((p) => p.id).sort(), ["p1", "p2"]);
});

test("minimize hides a pane from tiling and moves focus off it; session survives", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  m.createPane({ id: "p2" });
  m.focus("p1");
  m.minimize("p1");
  assert.strictEqual(m.get("p1").windowState, "minimized");
  assert.deepStrictEqual(m.visible().map((p) => p.id), ["p2"]);
  assert.deepStrictEqual(m.minimized().map((p) => p.id), ["p1"]);
  assert.strictEqual(m.focusedId, "p2");        // focus never rests on a minimized pane
  assert.strictEqual(m.size(), 2);              // pane (and its session) still exists
});

test("focusing a minimized pane un-minimizes it", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  m.createPane({ id: "p2" });
  m.minimize("p1");
  m.focus("p1");
  assert.strictEqual(m.get("p1").windowState, "normal");
  assert.strictEqual(m.focusedId, "p1");
});

test("pin / attention / activity flow through to tiling members in stable order", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  m.createPane({ id: "p2" });
  m.pin("p2");
  m.setAttention("p1", true);
  m.setActivity("p1", "awaiting_operator");
  assert.deepStrictEqual(m.tilingMembers(), [
    { id: "p1", pinned: false, attention: true, activity: "awaiting_operator" },
    { id: "p2", pinned: true, attention: false, activity: "active" },
  ]);
  m.unpin("p2");
  assert.strictEqual(m.get("p2").pinned, false);
});

test("a new pane defaults to 'active' activity", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  assert.strictEqual(m.get("p1").activity, "active");
});

test("setActivity fails closed on an unknown activity and on an unknown pane", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1" });
  assert.throws(() => m.setActivity("p1", "nonsense"), /unknown activity/);
  assert.throws(() => m.setActivity("nope", "idle"), /unknown pane/);
  assert.strictEqual(m.get("p1").activity, "active"); // unchanged after the failed set
});

test("returned pane objects are snapshots (mutating them does not affect the model)", () => {
  const m = new PaneModel();
  m.createPane({ id: "p1", title: "orig" });
  const snap = m.get("p1");
  snap.title = "hacked";
  assert.strictEqual(m.get("p1").title, "orig");
});
