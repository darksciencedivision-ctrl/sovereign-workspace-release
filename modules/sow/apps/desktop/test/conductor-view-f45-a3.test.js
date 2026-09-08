"use strict";
/**
 * SW-JOURNAL-002-A3 item 2 (F-45): the conductor's own entries stay out of the worker view,
 * and no label ever reads "terminal #" with no number.
 *
 * Measured defect: main.js records each objective plan with status "conductor_reasoning" and
 * pane_id "conductor"; the view filter excluded only statuses starting with "view_", so the
 * conductor's own plan text was attached back to it under a header reading
 * "observed_pane_output; self_published: false" — false for text the conductor wrote itself —
 * and its rendered label read "terminal # (conductor)", a terminal number that does not exist.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const J = require("../control/workspace-journal");
const V = require("../control/conductor-view");

const profile = (n) => ({ available: true, num_ctx: n, reserved_prompt_tokens: 0,
  reserved_response_tokens: 0, chars_per_token: 1, total_max_chars: n, max_observation_chars: n });
function entry(id, extra = {}) {
  return J.prepareEntry({ node_id: "node-" + id, pane_id: "pane-" + id, model: "model-" + id,
    status: "answered", answer: "answer from " + id, source: J.SOURCE, self_published: false,
    ...extra }, "session-test", () => "2026-09-06T00:00:00Z");
}
// The exact shape main.js records: pane_id "conductor", status "conductor_reasoning".
const conductorRow = J.prepareEntry({ node_id: "conductor", pane_id: "conductor",
  model: "model-conductor", status: "conductor_reasoning",
  answer: "PLAN-ASK-EACH-WORKER-FOR-THEIR-ANSWER", source: J.SOURCE, self_published: false },
"session-test", () => "2026-09-06T00:01:00Z");
const receiptRow = J.prepareEntry({ node_id: "conductor", pane_id: "conductor",
  model: "(view delivery)", status: "view_delivered", answer: "RECEIPT-TEXT-NOT-A-WORKER-ROW",
  source: J.SOURCE, self_published: false }, "session-test", () => "2026-09-06T00:02:00Z");
const workers = [entry(2), entry(3), entry(4)];
// The forbidden shape, in both label spellings the codebase uses: "terminal #" or
// "terminal=#" with anything other than a digit after it.
const EMPTY_NUMBER = /terminal[ =]#(?!\d)/;

test("F-45: a conductor_reasoning row stays out of the worker view; worker rows are untouched", () => {
  const withRow = V.composeView("what did they all say", [...workers, conductorRow], profile(8000));
  const without = V.composeView("what did they all say", workers, profile(8000));
  assert.doesNotMatch(withRow.view, /PLAN-ASK-EACH-WORKER/);
  assert.doesNotMatch(withRow.message, /PLAN-ASK-EACH-WORKER/);
  assert.ok(!withRow.entry_ids.includes(conductorRow.event_id));
  // The workers' view is EXACTLY what it is without the conductor's row: same ids, same order.
  assert.deepEqual(withRow.entry_ids, without.entry_ids);
  assert.equal(withRow.view, without.view);
  assert.match(withRow.view, /answer from 2/);
});

test("F-45: anything stored under pane_id 'conductor' stays out, whatever its status", () => {
  const odd = J.prepareEntry({ node_id: "conductor", pane_id: "conductor", model: "m",
    status: "answered", answer: "CONDUCTOR-PANE-ANSWER", source: J.SOURCE,
    self_published: false }, "session-test", () => "2026-09-06T00:03:00Z");
  const v = V.composeView("what did they all say", [...workers, odd], profile(8000));
  assert.doesNotMatch(v.view, /CONDUCTOR-PANE-ANSWER/);
  assert.match(v.view, /answer from 2/);
});

test("F-45: the pre-existing view_* receipt filtering is unchanged, and the predicate is exported", () => {
  const v = V.composeView("what did they all say", [...workers, receiptRow], profile(8000));
  assert.doesNotMatch(v.view, /RECEIPT-TEXT/);
  assert.equal(V.viewEligible(receiptRow), false, "view_ rows stay excluded");
  assert.equal(V.viewEligible(conductorRow), false, "conductor rows stay excluded");
  assert.equal(V.viewEligible(entry(2)), true, "worker rows stay eligible");
  assert.equal(V.viewEligible(null), false);
});

test("F-45: an id that is not a numbered pane renders as itself in view labels and the notice", () => {
  const scratchRow = J.prepareEntry({ node_id: "node-9", pane_id: "scratch", model: "model-9",
    status: "answered", answer: "answer from scratch", source: J.SOURCE, self_published: false },
  "session-test", () => "2026-09-06T00:04:00Z");
  const open = [{ pane_id: "scratch", node_id: "node-9", model: "model-9", live: true }];
  const v = V.composeView("what did they all say", [scratchRow], profile(8000), "", open);
  assert.match(v.view, /terminal=scratch/, "the id renders as itself");
  assert.doesNotMatch(v.view, EMPTY_NUMBER);
  assert.doesNotMatch(v.notice, EMPTY_NUMBER);
  assert.match(v.notice, /from scratch\./, "the notice names the pane, not 'terminal # (scratch)'");
  assert.doesNotMatch(v.roster, EMPTY_NUMBER);
  assert.match(v.roster, /"scratch"/);
});

test("F-45: a full delivery never renders 'terminal #' with no number on any surface", async () => {
  const panes = [
    { pane_id: "pane-2", node_id: "node-2", model: "model-2", live: true },
    { pane_id: "conductor", node_id: "conductor", model: "model-conductor", live: true },
    { pane_id: "scratch", node_id: "node-9", model: "model-9", live: false },
  ];
  let sent;
  const r = await V.retrieveAndDeliver({ message: "what did they all say", panes,
    journal: { sessionId: "session-test", entries: async () => [...workers, conductorRow],
      observe: async () => {} },
    window: {}, budgetSource: async () => profile(8000),
    write: async (text) => { sent = text; return { written: true, submitted: true }; } });
  assert.equal(r.context.attached, true);
  for (const [name, surface] of [["sent", sent], ["view", r.context.view],
    ["notice", r.context.notice], ["roster", r.context.roster], ["message", r.context.message]]) {
    assert.ok(typeof surface === "string", name + " must exist");
    assert.doesNotMatch(surface, EMPTY_NUMBER, name + " must not carry an empty terminal number");
  }
  // Numbered panes keep the exact established form.
  assert.match(r.context.notice, /terminal #2 \(pane-2\)/);
  assert.match(r.context.view, /terminal=#2/);
  // The conductor's plan text is not in anything that was written.
  assert.doesNotMatch(sent, /PLAN-ASK-EACH-WORKER/);
});

test("F-45: the own-work digest never labels a non-numbered pane 'terminal=#' with no number", () => {
  const scratch = J.prepareEntry({ node_id: "node-9", pane_id: "scratch", model: "m",
    status: "answered", answer: "scratch answer", source: J.SOURCE, self_published: false },
  "session-test", () => "2026-09-06T00:00:00Z");
  const d = J.composeOwnDigest([scratch], { budgetChars: 4000, nodeId: "node-9" });
  assert.doesNotMatch(d.text, EMPTY_NUMBER);
  assert.match(d.text, /terminal=scratch/, "the id renders as itself");
  const numbered = J.composeOwnDigest([entry(2)], { budgetChars: 4000, nodeId: "node-2" });
  assert.match(numbered.text, /terminal=#2/, "numbered panes keep the established form");
});

test("F-45 mutation control: removing the conductor exclusion lets its rows back into the view", () => {
  const filename = require.resolve("../control/conductor-view");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = '  if (status === "conductor_reasoning" || e.pane_id === "conductor") return false;';
  assert.ok(source.includes(anchor), "the exclusion anchor must exist in the source");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor, ""), filename);
  const check = (api) => assert.doesNotMatch(
    api.composeView("what did they all say", [...workers, conductorRow], profile(8000)).view,
    /PLAN-ASK-EACH-WORKER/);
  check(V);
  assert.throws(() => check(mutant.exports),
    "without the exclusion the conductor's own row reappears — the tests above are decisive");
  assert.equal(fs.readFileSync(filename, "utf8"), source, "the control must not modify the source");
});
