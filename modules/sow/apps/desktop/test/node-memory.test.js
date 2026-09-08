"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const Module = require("node:module");
const J = require("../control/workspace-journal");
const { characterBudget } = require("../control/conductor-view");
const { delegateToPane } = require("../control/conductor-delegation");
function setup(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "sow-node-mem-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "install"));
  const rows = [], privateRows = [];
  const store = {
    append: async e => rows.push(structuredClone(e)),
    appendPrivate: async e => privateRows.push(structuredClone(e)),
    entries: async ({ sessionId, limit }) =>
      (sessionId ? rows.filter(e => e.session_id === sessionId) : rows.toReversed()).slice(0, limit),
    privateEntries: async ({ nodeId, sessionId, limit }) =>
      privateRows.filter(e => e.node_id === nodeId && (!sessionId || e.session_id === sessionId)).slice(0, limit),
  };
  const journal = J.createWorkspaceJournal({ store, stateRoot: path.join(root, "state"),
    installRoot: path.join(root, "install"), sessionId: "session-test", now: () => "2026-09-06T00:00:00Z" });
  return { root, rows, privateRows, store, journal };
}
const workerProfile = (num_ctx) => ({ available: true, num_ctx, reserved_prompt_tokens: 1200,
  reserved_response_tokens: 2048, chars_per_token: 3, total_max_chars: 8000, max_observation_chars: 8000 });
function entry(node, extra = {}) {
  return { node_id: node, pane_id: "pane-" + node.slice(-1), model: "m", status: "answered",
    objective: "q", prompt: "p", answer: "answer from " + node, self_published: false, source: J.SOURCE, ...extra };
}
test("F-32: a delegation writes shared_project and private_node with the worker identity", async t => {
  const x = setup(t); let clock = 0;
  const result = await delegateToPane({
    journal: x.journal, now: () => clock, sleep: async ms => { clock += ms; },
    window: { mark: () => 0, read: () => ({ answerable: true, text: "worker answer", at: 1 }) },
    writePrompt: async () => ({ written: true }),
  }, { paneId: "pane-2", nodeId: "node-2", model: "test-model",
    task: { task_id: "obj-1", objective: "compare facts" }, workerProfile: workerProfile(4096),
    timeoutMs: 20, pollMs: 1, quietMs: 2 });
  assert.equal(result.answered, true);
  const shared = x.rows.find(e => e.status === "answered");
  const priv = x.privateRows.find(e => e.status === "answered");
  assert.equal(shared.self_published, false); assert.equal(shared.source, J.SOURCE);
  assert.equal(priv.node_id, "node-2"); assert.equal(priv.self_published, false);
  assert.equal(priv.source, J.SOURCE); assert.equal(priv.session_id, "session-test");
});
test("F-32: worker A's digest contains A's entries and none of B's", () => {
  const a = J.prepareEntry(entry("node-2"), "session-test", () => "2026-09-06T00:00:00Z");
  const b = J.prepareEntry(entry("node-3", { answer: "foreign-b-answer" }), "session-test", () => "2026-09-06T00:00:00Z");
  const digest = J.composeOwnDigest([a, b], { budgetChars: 4000, nodeId: "node-2" });
  assert.match(digest.text, /answer from node-2/);
  assert.doesNotMatch(digest.text, /foreign-b-answer|node-3|answer from node-3/);
  assert.match(digest.text, /self_published=false/);
  assert.match(digest.text, /observed_pane_output/);
});
test("F-32: digest fits a stub worker profile and shrinks when the profile shrinks", () => {
  const own = [J.prepareEntry(entry("node-2", { answer: "z".repeat(20000) }), "session-test",
    () => "2026-09-06T00:00:00Z")];
  const large = J.composeOwnDigest(own, { budgetChars: characterBudget(workerProfile(8192)), nodeId: "node-2" });
  const small = J.composeOwnDigest(own, { budgetChars: characterBudget(workerProfile(4096)), nodeId: "node-2" });
  assert.ok(small.text.length < large.text.length);
  assert.ok(small.text.length <= characterBudget(workerProfile(4096)));
  assert.match(small.text, /TRUNCATED/);
  assert.equal(small.truncated, true);
});
test("F-32: store failure yields a stated absence and the task still delivers", async t => {
  const x = setup(t);
  x.journal.privateEntries = async () => { throw new Error("store down"); };
  let written = ""; let clock = 0;
  const result = await delegateToPane({
    journal: x.journal, window: { mark: () => 0, read: () => ({ answerable: true, text: "ok", at: 1 }) },
    writePrompt: async (_id, body) => { written = body; return { written: true }; },
    now: () => clock, sleep: async ms => { clock += ms; },
  }, { paneId: "pane-2", nodeId: "node-2", task: { objective: "work" },
    workerProfile: workerProfile(4096), timeoutMs: 20, pollMs: 1, quietMs: 2 });
  assert.equal(result.answered, true);
  assert.match(written, /could not be retrieved/);
  assert.match(written, /Continuing without it/);
});
test("F-32: per-node markdown projects reproducibly and re-projects byte-identically", async t => {
  const x = setup(t);
  await x.journal.recordPrivate(entry("node-2"));
  await x.journal.recordPrivate(entry("node-2", { answer: "later" }));
  const { file } = await x.journal.projectNode("node-2");
  const before = fs.readFileSync(file);
  await x.journal.projectNode("node-2");
  assert.deepEqual(fs.readFileSync(file), before);
  fs.unlinkSync(file);
  await x.journal.projectNode("node-2");
  assert.deepEqual(fs.readFileSync(file), before);
  assert.match(before.toString("utf8"), /self_published: false/);
  assert.match(before.toString("utf8"), /private_node/);
});
test("F-32 mutation control: dropping the own-node filter admits another worker's entries", () => {
  const filename = require.resolve("../control/workspace-journal");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = "if (!e || e.node_id !== nodeId) continue;";
  assert.ok(source.includes(anchor));
  const mutant = new Module(filename, module); mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor, "if (!e) continue;"), filename);
  const a = J.prepareEntry(entry("node-2"), "session-test", () => "2026-09-06T00:00:00Z");
  const b = J.prepareEntry(entry("node-3", { answer: "foreign-b-answer" }), "session-test", () => "2026-09-06T00:00:00Z");
  const leaked = mutant.exports.composeOwnDigest([a, b], { budgetChars: 4000, nodeId: "node-2" });
  assert.match(leaked.text, /foreign-b-answer/);
  assert.doesNotMatch(J.composeOwnDigest([a, b], { budgetChars: 4000, nodeId: "node-2" }).text, /foreign-b-answer/);
});
