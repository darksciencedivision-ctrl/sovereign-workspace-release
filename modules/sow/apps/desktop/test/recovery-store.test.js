"use strict";
/**
 * RecoveryStore — durable persistence of the append-only session lifecycle log so a RESTARTED
 * shell process can reconstruct what existed (directive §9 track 14A). fs is injected, so this
 * is proven headlessly with an in-memory fake — no real disk, no Electron.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { RecoveryStore } = require("../recovery-store");
const { SessionRegistry } = require("../../../terminal/session/session-registry");

// Minimal in-memory fs shim exposing only what RecoveryStore uses.
function fakeFs() {
  const files = new Map();
  return {
    files,
    existsSync: (p) => files.has(p),
    mkdirSync: () => {},
    readFileSync: (p) => { if (!files.has(p)) { const e = new Error("ENOENT"); e.code = "ENOENT"; throw e; } return files.get(p); },
    writeFileSync: (p, data) => { files.set(p, data); },
  };
}

test("loadInterrupted() on a missing file returns [] (clean first boot, fail-closed)", () => {
  const store = new RecoveryStore({ file: "/x/log.json", fs: fakeFs() });
  assert.deepStrictEqual(store.loadInterrupted(), []);
});

test("persist then loadInterrupted round-trips a still-alive session as needing relaunch", () => {
  const fs = fakeFs();
  const store = new RecoveryStore({ file: "/x/log.json", fs });
  const reg = new SessionRegistry();
  let t = 0; const ts = () => `t${t++}`;
  reg.register("p1", { nodeId: "shell", pid: 100 }, ts());
  reg.transition("p1", "RUNNING", ts(), {});
  reg.register("p2", { nodeId: "shell", pid: 101 }, ts());
  reg.transition("p2", "RUNNING", ts(), {});
  reg.transition("p2", "EXITED", ts(), { exitCode: 0 });
  store.persist(reg.eventLog());

  // a fresh store over the SAME fake disk == a restarted shell reading the persisted log
  const restarted = new RecoveryStore({ file: "/x/log.json", fs });
  const interrupted = restarted.loadInterrupted();
  assert.deepStrictEqual(interrupted.map((s) => s.id), ["p1"]);
  assert.strictEqual(interrupted[0].disposition, "interrupted");
  assert.strictEqual(interrupted[0].recoverable, false);
});

test("persist is atomic when the fs supports rename — temp write then rename over the target", () => {
  const fs = fakeFs();
  const renames = [];
  fs.renameSync = (from, to) => { renames.push([from, to]); fs.files.set(to, fs.files.get(from)); fs.files.delete(from); };
  const store = new RecoveryStore({ file: "/x/log.json", fs });
  store.persist([{ seq: 0, id: "a", kind: "register", to: "SPAWNING", detail: { nodeId: "n" } }]);
  assert.deepStrictEqual(renames, [["/x/log.json.tmp", "/x/log.json"]], "must write temp then rename");
  assert.ok(fs.files.has("/x/log.json"), "target exists after the atomic rename");
  assert.ok(!fs.files.has("/x/log.json.tmp"), "temp is gone after rename");
});

test("a corrupt recovery file fails closed — loadInterrupted returns [], never throws", () => {
  const fs = fakeFs();
  fs.writeFileSync("/x/log.json", "{ not json");
  const store = new RecoveryStore({ file: "/x/log.json", fs });
  assert.deepStrictEqual(store.loadInterrupted(), []);
});

test("persist writes a versioned envelope so the format is self-describing", () => {
  const fs = fakeFs();
  const store = new RecoveryStore({ file: "/x/log.json", fs });
  store.persist([{ seq: 0, id: "a", kind: "register", to: "SPAWNING", detail: { nodeId: "n" } }]);
  const written = JSON.parse(fs.files.get("/x/log.json"));
  assert.strictEqual(written.version, 1);
  assert.ok(Array.isArray(written.log));
});

// -- Phase 15E `.recovery`: conductor-first LAYOUT snapshot --------------------

test("the layout snapshot is stored in a sibling layout.json, not the session log", () => {
  const fs = fakeFs();
  const store = new RecoveryStore({ file: "/x/session-log.json", fs });
  store.persistLayout({ version: 1, conductor: { paneId: "pane-1" }, panes: [] });
  assert.ok(fs.files.has("/x/layout.json"), "layout snapshot goes to the sibling file");
  assert.ok(!fs.files.has("/x/session-log.json"), "the session log is untouched by a layout persist");
});

test("persistLayout then loadLayout round-trips the conductor-first snapshot across a restart", () => {
  const fs = fakeFs();
  const store = new RecoveryStore({ file: "/x/session-log.json", fs });
  const snap = { version: 1, conductor: { paneId: "pane-1", pinned: true }, panes: [{ paneId: "pane-2", sessionId: "pane-2" }] };
  store.persistLayout(snap);
  const restarted = new RecoveryStore({ file: "/x/session-log.json", fs });
  assert.deepStrictEqual(restarted.loadLayout(), snap);
});

test("persistLayout then loadLayout round-trips per-pane worker CHROME across a restart (U68)", () => {
  const fs = fakeFs();
  const store = new RecoveryStore({ file: "/x/session-log.json", fs });
  const snap = {
    version: 1,
    conductor: { paneId: "pane-1", pinned: true, model: "fable-5", sessionId: null },
    panes: [{
      paneId: "pane-2", ordinal: 2, role: "reasoning", mode: "autonomous", model: "opus-4.8",
      sessionId: "pane-2",
      chrome: { model_label: "opus-4.8", model_slug: "claude-opus-4-8", locality: "frontier",
        node_state: "selected_awaiting_governed_spawn", governed: false, subscription: { allowance: 2, in_use: null } },
    }],
  };
  store.persistLayout(snap);
  const restarted = new RecoveryStore({ file: "/x/session-log.json", fs });
  const back = restarted.loadLayout();
  assert.strictEqual(back.panes[0].chrome.model_label, "opus-4.8", "the worker's model badge survives the disk round-trip");
  assert.strictEqual(back.panes[0].chrome.governed, false, "and never gains a live-node claim on the way");
});

test("loadLayout on a missing or corrupt snapshot fails closed to null (conductor-only reconstruction)", () => {
  const fs = fakeFs();
  const store = new RecoveryStore({ file: "/x/session-log.json", fs });
  assert.strictEqual(store.loadLayout(), null, "missing ⇒ null");
  fs.writeFileSync("/x/layout.json", "{ not json");
  assert.strictEqual(store.loadLayout(), null, "corrupt ⇒ null, never throws");
});
