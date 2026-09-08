"use strict";
/**
 * SW-JOURNAL-002-A3 item 5 (F-46d): a view receipt records WHAT HAPPENED — the ids of the
 * entries the view carried, their counts, the panes they came from, the size of the view,
 * whether it was truncated, the state, and the operator-facing notice — and never the view
 * text itself.
 *
 * Measured defect: one turn's three view_* receipts stored ~30.9k answer characters, 77% of
 * all stored answer bytes, each a verbatim copy of a view that is fully reconstructible from
 * the entry ids the receipt already named. The receipt must answer "what did the conductor
 * receive on that turn"; a second copy of the payload answers nothing and doubles the store.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const J = require("../control/workspace-journal");
const V = require("../control/conductor-view");

const MARKER = "UNIQUE-VIEW-MARKER-XYZ";
const MESSAGE = "show me the workers";
const PANES = [{ pane_id: "pane-2", node_id: "node-2", model: "model-2", live: true }];
const profile = (n) => ({ available: true, num_ctx: n, reserved_prompt_tokens: 0,
  reserved_response_tokens: 0, chars_per_token: 1, total_max_chars: n, max_observation_chars: n });
// Long answers make truncation certain at the small budget below, whatever the label costs.
const entry = (id) => J.prepareEntry({ node_id: "node-" + id, pane_id: "pane-" + id,
  model: "model-" + id, status: "answered", answer: MARKER + " answer from " + id + " "
    + "x".repeat(600), source: J.SOURCE, self_published: false },
  "session-test", () => "2026-09-06T00:00:00Z");
const workers = [entry(2), entry(3), entry(4)];

async function deliver(api = V, { budget, write } = {}) {
  const receipts = [];
  const result = await api.retrieveAndDeliver({ message: MESSAGE, panes: PANES,
    journal: { sessionId: "session-test", entries: async () => workers,
      record: async (e) => receipts.push(e), observe: async () => {} },
    window: {}, budgetSource: async () => profile(budget),
    write: write || (async () => ({ written: true, submitted: true })) });
  return { receipts, result };
}

test("F-46d: receipts record ids, counts, truncation and notice — never the view text", async () => {
  const { receipts, result } = await deliver(V, { budget: 4000 });
  assert.deepEqual(receipts.map(r => r.status), ["view_prepared", "view_delivered"]);
  assert.equal(result.context.attached, true);
  assert.equal(result.context.truncated, false);
  assert.equal(result.context.entry_ids.length, 3);
  assert.match(result.context.view, new RegExp(MARKER), "the view itself carries the payload");
  for (const r of receipts) {
    const parsed = JSON.parse(r.answer); // a receipt is structured fact, not prose
    assert.deepEqual(parsed.entry_ids, result.context.entry_ids);
    assert.equal(parsed.entries, result.context.entry_ids.length);
    assert.deepEqual(parsed.panes, result.context.pane_ids);
    assert.equal(parsed.view_chars, result.context.view.length);
    assert.equal(parsed.truncated, false);
    assert.equal(parsed.state, result.context.state);
    assert.equal(parsed.notice, result.context.notice);
    assert.doesNotMatch(r.answer, new RegExp(MARKER), "the view text is never copied in");
    assert.ok(r.answer.length < result.context.view.length,
      "the receipt is smaller than the payload it describes");
    assert.equal(r.prompt, MESSAGE, "the operator message stays on the receipt");
    assert.equal(r.self_published, false);
    assert.equal(r.source, J.SOURCE);
    assert.equal(r.node_id, "conductor");
    assert.equal(r.pane_id, "conductor");
  }
});

test("F-46d: a truncated view is declared truncated in the receipt, still without the text", async () => {
  const { receipts, result } = await deliver(V, { budget: 1000 });
  assert.equal(result.context.attached, true);
  assert.equal(result.context.truncated, true);
  const delivered = receipts.find(r => r.status === "view_delivered");
  assert.ok(delivered, "a truncated view is still delivered and receipted");
  const parsed = JSON.parse(delivered.answer);
  assert.equal(parsed.truncated, true);
  assert.equal(parsed.view_chars, result.context.view.length);
  assert.match(parsed.notice, /TRUNCATED/);
  assert.ok(parsed.entries < workers.length, "the receipt says how much made it in");
  assert.doesNotMatch(delivered.answer, new RegExp(MARKER));
});

test("F-46d: a refused delivery receipt keeps the same shape and its reason", async () => {
  const { receipts, result } = await deliver(V, { budget: 4000,
    write: async () => ({ written: false, reason: "the pane write gate refused this prompt" }) });
  assert.deepEqual(receipts.map(r => r.status), ["view_prepared", "view_refused"]);
  const refused = receipts[1];
  assert.equal(refused.reason, "the pane write gate refused this prompt");
  const parsed = JSON.parse(refused.answer);
  assert.deepEqual(parsed.entry_ids, result.context.entry_ids);
  assert.equal(parsed.truncated, result.context.truncated === true);
  assert.doesNotMatch(refused.answer, new RegExp(MARKER));
  // The refusal notice is appended to the context AFTER the receipt is taken; the receipt
  // carries the notice as it stood when the delivery was refused.
  assert.equal(result.context.state, "delivery_refused");
  assert.match(result.context.notice, /No worker view delivered/);
});

test("F-46d mutation control: restoring the view copy puts the payload back in receipts", async () => {
  const filename = require.resolve("../control/conductor-view");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = "status, prompt: message, answer: receipt, reason, self_published: false, source: SOURCE,";
  assert.ok(source.includes(anchor), "the receipt anchor must exist in the source");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor,
    "status, prompt: message, answer: context.view, reason, self_published: false, source: SOURCE,"),
    filename);
  const check = async (api) => {
    const { receipts } = await deliver(api, { budget: 4000 });
    assert.equal(receipts.length, 2);
    for (const r of receipts)
      assert.doesNotMatch(r.answer, new RegExp(MARKER),
        "a receipt must never carry the view text");
  };
  await check(V);
  await assert.rejects(() => check(mutant.exports),
    "with the view copy restored the payload reappears — the tests above are decisive");
  assert.equal(fs.readFileSync(filename, "utf8"), source, "the control must not modify the source");
});
