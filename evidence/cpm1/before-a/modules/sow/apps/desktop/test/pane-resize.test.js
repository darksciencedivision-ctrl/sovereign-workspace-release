"use strict";
/**
 * Phase 17D `.close` (U73) — the `pane:resize` guard, made falsifiable.
 *
 * The defect the operator's log carried on every launch: the renderer fits pane 1 — the conductor
 * PLACEHOLDER, which has no ConPTY until the governed launch admits one — and the resize handler
 * dereferenced a session that does not exist (`TypeError: Cannot read properties of null (reading
 * 'resize')`, main.js:451). Electron's IPC layer caught it, so it was non-fatal noise; but a handler
 * that throws returns nothing, the renderer's invoke REJECTS, and the shell's answer to "can this
 * pane be resized" was an exception instead of a decision.
 *
 * A guard landed in `main.js` at 16E `.wire` and was never pinned by anything: deleting it left the
 * whole repo green. These tests exist to go RED when their own rule is deleted — the rule now lives
 * in `panes/resize-intent.js` and `main.js` delegates to it, so the property is testable at all.
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  resizePane, refusalWorthLogging, NO_SESSION, BAD_DIMENSIONS, NOT_RUNNING, MAX_DIMENSION,
} = require("../panes/resize-intent");

/**
 * A SessionManager stand-in that records what it was asked to do.
 *
 * `took` is the real `SessionManager.resize` contract (17D `.close`, spec-audit F1): true only when a
 * LIVE pty handle of the matching generation accepted the geometry. A registered session whose
 * process has exited is still in the registry and returns false — the case a fake that always
 * succeeds cannot express, which is how the over-claim got in.
 */
function fakeManager({ ids = ["pane-2"], throws = null, took = true } = {}) {
  const calls = [];
  return {
    calls,
    registry: { has: (id) => ids.includes(id) },
    resize(id, cols, rows) {
      calls.push({ id, cols, rows });
      if (throws) throw throws;
      return took;
    },
  };
}

// ---- the sessionless conductor placeholder: the operator's actual startup (U73) ----------------

test("a pane with no admitted session is refused, not resized — and nothing throws", () => {
  const m = fakeManager();
  const out = resizePane(m, "pane-1", 120, 40);
  assert.deepEqual(out, { resized: false, reason: NO_SESSION });
  assert.deepEqual(m.calls, []);
});

test("a resize that arrives before supervision exists is refused, not dereferenced", () => {
  // `manager` is null until the gateway verifies; the renderer's first fit can beat it there.
  assert.deepEqual(resizePane(null, "pane-1", 120, 40), { resized: false, reason: NO_SESSION });
  assert.deepEqual(resizePane(undefined, "pane-1", 120, 40), { resized: false, reason: NO_SESSION });
  assert.deepEqual(resizePane({}, "pane-1", 120, 40), { resized: false, reason: NO_SESSION });
});

// ---- the live pane: the guard must not become a refusal of real work --------------------------

test("an admitted session is resized with the exact geometry the renderer measured", () => {
  const m = fakeManager({ ids: ["pane-2"] });
  assert.deepEqual(resizePane(m, "pane-2", 132, 43), { resized: true });
  assert.deepEqual(m.calls, [{ id: "pane-2", cols: 132, rows: 43 }]);
});

test("a session the registry still holds but whose process ended is NOT reported as resized", () => {
  // `SessionManager.resize` no-ops for an ended session whose record has not been forgotten. The
  // shell used to answer `{resized:true}` from `registry.has(id)` alone — a claim nothing performed.
  const m = fakeManager({ ids: ["pane-2"], took: false });
  assert.deepEqual(resizePane(m, "pane-2", 100, 30), { resized: false, reason: NOT_RUNNING });
  assert.deepEqual(m.calls, [{ id: "pane-2", cols: 100, rows: 30 }]);
});

// ---- the renderer is the least-trusted surface (invariant 29): its numbers are checked ----------

test("dimensions that are not positive integers are refused before the ConPTY sees them", () => {
  for (const [cols, rows] of [[0, 24], [80, 0], [-1, 24], [80, -1], [80.5, 24], [NaN, 24],
    [Infinity, 24], ["80", 24], [null, 24], [undefined, 24], [80, undefined],
    // above what a ConPTY COORD can hold: refused here, not truncated somewhere downstream
    [MAX_DIMENSION + 1, 24], [80, MAX_DIMENSION + 1], [2 ** 31 - 1, 24]]) {
    const m = fakeManager();
    const out = resizePane(m, "pane-2", cols, rows);
    assert.deepEqual(out, { resized: false, reason: BAD_DIMENSIONS },
      `expected refusal for ${String(cols)}x${String(rows)}`);
    assert.deepEqual(m.calls, [], `expected no ConPTY call for ${String(cols)}x${String(rows)}`);
  }
});

// ---- a session that dies between the check and the call ----------------------------------------

test("a ConPTY that refuses the resize is reported, not thrown — the handler still answers", () => {
  const m = fakeManager({ ids: ["pane-2"], throws: new Error("pty is gone") });
  const out = resizePane(m, "pane-2", 80, 24);
  assert.equal(out.resized, false);
  assert.match(out.reason, /pty is gone/);
  assert.deepEqual(m.calls, [{ id: "pane-2", cols: 80, rows: 24 }]);
});

test("the largest geometry a ConPTY can actually hold is still admitted", () => {
  const m = fakeManager({ ids: ["pane-2"] });
  assert.deepEqual(resizePane(m, "pane-2", MAX_DIMENSION, MAX_DIMENSION), { resized: true });
});

// ---- invariant 27: the refusals that mean something are the ones that get reported --------------

test("a live pane's refusal is worth logging; the placeholder's is the ordinary startup case", () => {
  assert.equal(refusalWorthLogging({ resized: false, reason: BAD_DIMENSIONS }), true);
  assert.equal(refusalWorthLogging({ resized: false, reason: NOT_RUNNING }), true);
  assert.equal(refusalWorthLogging({ resized: false, reason: "resize refused: pty is gone" }), true);
  assert.equal(refusalWorthLogging({ resized: false, reason: NO_SESSION }), false);
  assert.equal(refusalWorthLogging({ resized: true }), false);
  assert.equal(refusalWorthLogging(null), false);
});

test("main.js reports those refusals once per pane and reason, not on every fit", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const src = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");
  const handler = src.slice(src.indexOf('ipcMain.handle("pane:resize"'));
  const body = handler.slice(0, handler.indexOf('ipcMain.handle("pane:close"'));
  assert.match(body, /refusalWorthLogging\(answer\)/);
  assert.match(body, /resizeRefusalsLogged\.has\(key\)/, "a repeated refusal must not repeat in the log");
  assert.match(body, /log\(/);
});

// ---- main.js must actually delegate ------------------------------------------------------------
// A drift ALARM, not containment: it catches the literal re-inline (the gate-validator proved it
// goes red for one), and an inline guard written through an alias would still slip past it.

test("main.js routes `pane:resize` through this module and not through its own inline logic", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const src = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");
  const handler = src.slice(src.indexOf('ipcMain.handle("pane:resize"'));
  const body = handler.slice(0, handler.indexOf('ipcMain.handle("pane:close"'));
  assert.match(body, /resizePane\(manager, id, cols, rows\)/);
  assert.doesNotMatch(body, /manager\.resize\(/,
    "the handler must not resize directly — the decision belongs to panes/resize-intent.js");
});
