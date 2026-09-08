"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const J = require("../control/workspace-journal");
const { clearSession } = require("../control/journal-runtime");
function setup(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "sow-clear-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "install"));
  const rows = [];
  const store = {
    append: async e => rows.push(structuredClone(e)),
    entries: async ({ sessionId, limit }) =>
      (sessionId ? rows.filter(e => e.session_id === sessionId) : rows).slice(0, limit),
  };
  const journal = J.createWorkspaceJournal({ store, stateRoot: path.join(root, "state"),
    installRoot: path.join(root, "install"), sessionId: "session-old", now: () => "2026-09-06T00:00:00Z" });
  return { root, rows, journal };
}
const entry = () => ({ node_id: "node-2", pane_id: "pane-2", model: "m", status: "answered",
  objective: "q", prompt: "p", answer: "kept", self_published: false, source: J.SOURCE });
test("F-35: Clear starts a new session id; entries before and after carry different ones", async t => {
  const x = setup(t);
  const before = (await x.journal.record(entry())).entry;
  const result = await clearSession({ confirm: true, teardownPane: async () => {}, paneIds: ["pane-2"],
    journal: x.journal });
  const after = (await x.journal.record(entry())).entry;
  assert.notEqual(result.session_id, result.previous_session_id);
  assert.equal(before.session_id, "session-old");
  assert.notEqual(after.session_id, before.session_id);
  assert.equal(result.deleted, false);
});
test("F-35: the journal is byte-identical across a Clear — nothing deleted", async t => {
  const x = setup(t);
  const { projection } = await x.journal.record(entry());
  const before = fs.readFileSync(projection.file);
  await clearSession({ confirm: true, teardownPane: async () => {}, paneIds: ["pane-2"], journal: x.journal });
  assert.deepEqual(fs.readFileSync(projection.file), before);
  assert.equal(x.rows.length, 1);
});
test("F-35: prior entries remain readable after Clear", async t => {
  const x = setup(t);
  await x.journal.record(entry());
  const prior = x.rows.slice();
  await clearSession({ confirm: true, teardownPane: async () => {}, paneIds: [], journal: x.journal });
  assert.equal(x.rows.length, 1);
  assert.equal(x.rows[0].answer, "kept");
  assert.deepEqual(x.rows, prior);
});
test("F-35: a pane that refuses teardown is named and the result reports partial completion", async t => {
  const x = setup(t);
  const result = await clearSession({
    confirm: true,
    teardownPane: async id => { if (id === "pane-3") throw new Error("still running"); },
    paneIds: ["pane-2", "pane-3"], journal: x.journal,
  });
  assert.equal(result.complete, false);
  assert.equal(result.deleted, false);
  assert.ok(result.results.some(r => r.pane_id === "pane-3" && r.ok === false && /still running/.test(r.reason)));
  assert.ok(result.results.some(r => r.pane_id === "pane-2" && r.ok === true));
});
test("F-35: confirmation is required; declining it changes nothing", async t => {
  const x = setup(t);
  await x.journal.record(entry());
  let torn = 0;
  const result = await clearSession({ confirm: false, teardownPane: async () => { torn++; },
    paneIds: ["pane-2"], journal: x.journal });
  assert.equal(result.changed, false);
  assert.equal(torn, 0);
  assert.equal(x.journal.sessionId, "session-old");
  assert.equal(x.rows.length, 1);
});
test("F-35 mutation control: removing confirmation, or making Clear delete an entry, each fail a test", async t => {
  const x = setup(t);
  await x.journal.record(entry());
  const declined = await clearSession({ confirm: false, teardownPane: async () => {},
    paneIds: ["pane-2"], journal: x.journal });
  assert.equal(declined.changed, false);
  const file = (await x.journal.project()).file;
  const before = fs.readFileSync(file);
  await clearSession({ confirm: true, teardownPane: async () => {}, paneIds: [], journal: x.journal });
  assert.deepEqual(fs.readFileSync(file), before);
});
test("F-35 source pins: Clear confirms, uses existing close, collapses transcript and refits", () => {
  const renderer = fs.readFileSync(path.resolve(__dirname, "../renderer/renderer.js"), "utf8");
  const html = fs.readFileSync(path.resolve(__dirname, "../renderer/index.html"), "utf8");
  assert.match(html, /id="btn-clear"/);
  assert.match(renderer, /window\.confirm\(/);
  assert.match(renderer, /if \(ok !== true\) return/);
  assert.match(renderer, /await S\.close\(id\)/);
  assert.match(renderer, /S\.runObjective\(\{ options: \{ new_session: true \} \}\)/);
  assert.match(renderer, /setTranscriptCollapsed\(true\)/);
  assert.match(renderer, /refitConductorTerminals\(\)/);
});
