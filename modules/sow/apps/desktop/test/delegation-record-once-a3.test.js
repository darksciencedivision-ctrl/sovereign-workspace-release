"use strict";
/**
 * SW-JOURNAL-002-A3 item 6 (F-46e): each fact is recorded ONCE.
 *
 *   delegation_requested — the objective and the task id (base fields on every row). NOT the
 *                          prompt: at that moment no prompt has been written, so a copy of it
 *                          on this row claims a fact that has not happened yet.
 *   prompt_written       — the prompt. This row exists precisely to say what was written.
 *   answered             — the answer.
 *
 * Measured defect: one delegation stored the same prompt text three times (delegation_requested,
 * prompt_written, answered), burning journal bytes and leaving "what did we actually write, and
 * when" ambiguous — three rows could disagree after any partial failure. A refused write keeps
 * its prompt copy: for a refusal, write_refused IS the record of what was attempted.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const Module = require("node:module");
const J = require("../control/workspace-journal");
const D = require("../control/conductor-delegation");

function setup(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "sow-once-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "install"));
  const rows = [];
  const store = { append: async (e) => rows.push(structuredClone(e)),
    entries: async ({ sessionId, limit }) =>
      (sessionId ? rows.filter(e => e.session_id === sessionId) : rows.toReversed()).slice(0, limit) };
  const journal = J.createWorkspaceJournal({ store, stateRoot: path.join(root, "state"),
    installRoot: path.join(root, "install"), sessionId: "session-test",
    now: () => "2026-09-06T00:00:00Z" });
  return { rows, journal };
}
function delegationIO(x, paneTextFor, writeResult) {
  let clock = 0, writtenBody = null;
  const io = { journal: x.journal, now: () => clock, sleep: async (ms) => { clock += ms; },
    log: () => {},
    window: { mark: () => 0, read: () => ({ answerable: true, text: paneTextFor(writtenBody), at: 1 }) },
    writePrompt: async (paneId, body) => { writtenBody = body;
      return writeResult || { written: true }; } };
  return { io, writtenBody: () => writtenBody };
}
const options = { paneId: "pane-2", nodeId: "node-2", model: "test-model",
  task: { task_id: "t-once", objective: "report the sum" },
  timeoutMs: 200, pollMs: 1, quietMs: 2, maxChars: 4000 };
const promptCopies = (rows) => rows.filter(e => String(e.prompt || "").includes("SOVEREIGN TASK"));

async function runAnswered(api, t) {
  const x = setup(t);
  const { io, writtenBody } = delegationIO(x, (body) => body + "\nPLAIN-WORKER-ANSWER");
  const result = await api.delegateToPane(io, options);
  return { x, result, body: writtenBody() };
}

test("F-46e: objective on delegation_requested, prompt on prompt_written, answer on answered", async (t) => {
  const x = setup(t);
  const { io, writtenBody } = delegationIO(x, (body) => body + "\nPLAIN-WORKER-ANSWER");
  const result = await D.delegateToPane(io, options);
  assert.equal(result.answered, true);
  const body = writtenBody();
  assert.ok(body.includes("SOVEREIGN TASK t-once"), "the fixture wrote the real prompt");
  assert.deepEqual(x.rows.map(e => e.status),
    ["delegation_requested", "prompt_written", "answered"]);
  const [requested, written, answered] = x.rows;
  // delegation_requested: the objective and task id — facts that exist before the write.
  assert.equal(requested.prompt, "");
  assert.equal(requested.objective, "report the sum");
  assert.equal(requested.task_id, "t-once");
  assert.equal(requested.answer, "");
  // prompt_written: the prompt, exactly as written.
  assert.equal(written.prompt, body);
  assert.equal(written.answer, "");
  // answered: the answer.
  assert.equal(answered.prompt, "");
  assert.equal(answered.answer, "PLAIN-WORKER-ANSWER");
  assert.equal(answered.objective, "report the sum");
  assert.equal(answered.task_id, "t-once");
  assert.doesNotMatch(answered.answer, /SOVEREIGN TASK/);
  // The prompt text exists in EXACTLY ONE stored field of the whole delegation.
  assert.equal(promptCopies(x.rows).length, 1);
  assert.equal(promptCopies(x.rows)[0].status, "prompt_written");
  for (const e of x.rows) {
    assert.equal(e.self_published, false);
    assert.equal(e.source, J.SOURCE);
  }
});

test("F-46e: a refused write keeps its prompt copy — it is the only record of the attempt", async (t) => {
  const x = setup(t);
  const { io, writtenBody } = delegationIO(x, () => "",
    { written: false, refused: { reason: "permission modal OPEN" } });
  const result = await D.delegateToPane(io, options);
  assert.equal(result.delivered, false);
  assert.equal(result.refused.reason, "permission modal OPEN");
  const statuses = x.rows.map(e => e.status);
  assert.deepEqual(statuses, ["delegation_requested", "write_refused", "write_refused"]);
  assert.equal(x.rows[0].prompt, "", "the request row still precedes any write");
  assert.equal(x.rows[1].prompt, writtenBody(), "the refusal records what was attempted");
  assert.equal(x.rows[1].reason, "permission modal OPEN");
  assert.equal(x.rows[2].prompt, "");
  assert.equal(promptCopies(x.rows).length, 1);
});

test("F-46e mutation control: a prompt copy on delegation_requested is caught by the once-rule", async (t) => {
  const filename = require.resolve("../control/conductor-delegation");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = 'await record({ status: "delegation_requested", prompt: "" });';
  assert.ok(source.includes(anchor), "the request-row anchor must exist in the source");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor,
    'await record({ status: "delegation_requested", prompt: flattenBody(delegationPrompt(task)) });'),
    filename);
  const check = async (api) => {
    const { x } = await runAnswered(api, t);
    assert.equal(promptCopies(x.rows).length, 1,
      "the prompt must be stored exactly once per delegation");
  };
  await check(D);
  await assert.rejects(() => check(mutant.exports),
    "with the copy restored the prompt is stored twice — the once-rule above is decisive");
  assert.equal(fs.readFileSync(filename, "utf8"), source);
});

test("F-46e mutation control: a prompt copy on the answered row is caught by the once-rule", async (t) => {
  const filename = require.resolve("../control/conductor-delegation");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = '    prompt: "",\n    answer: result.candidate ? result.candidate.content : "",';
  assert.ok(source.includes(anchor), "the answered-row anchor must exist in the source");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor,
    '    prompt: flattenBody(delegationPrompt(task)),\n    answer: result.candidate ? result.candidate.content : "",'),
    filename);
  const check = async (api) => {
    const { x } = await runAnswered(api, t);
    assert.equal(promptCopies(x.rows).length, 1,
      "the prompt must be stored exactly once per delegation");
  };
  await check(D);
  await assert.rejects(() => check(mutant.exports),
    "with the copy restored the prompt is stored twice — the once-rule above is decisive");
  assert.equal(fs.readFileSync(filename, "utf8"), source);
});
