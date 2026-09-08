"use strict";
/** SW-JOURNAL-002-A2 WO-4/WO-5: an UNMEASURABLE budget must not swallow the operator's message.
 *
 * The defect: when characterBudget() could not MEASURE a budget, composeView returned
 * refused:true and retrieveAndDeliver never called write — the operator typed to the conductor
 * and the message was never sent at all. A conductor answering without context is far better
 * than a conductor you cannot talk to. After WO-4 an unmeasured turn DELIVERS the operator's own
 * message with no roster and no view, says so in the notice, and reports state
 * "budget_unmeasurable"; WO-5 gives that state its own collapsed-line summary in the renderer.
 *
 * Withholding stays correct — and is pinned below — where a budget WAS measured and genuinely
 * cannot fit the complete roster: that is the TRUNCATED refusal, which keeps refused:true.
 *
 * No test here needs a GPU, a daemon, or a real pane: the budget profile is a stub in the shape
 * journal-store.py's budget() emits, and renderer.js is exercised the way
 * conductor-context-surface.test.js exercises it — the real source region, run in a vm.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const V = require("../control/conductor-view");

// A MEASURED budget too small for the complete roster — the refusal that must stay a refusal.
const tiny = { available: true, num_ctx: 40, reserved_prompt_tokens: 0,
  reserved_response_tokens: 0, chars_per_token: 1, total_max_chars: 40, max_observation_chars: 40 };
// An UNMEASURABLE budget: characterBudget() answers null for any profile that is not available.
const unmeasured = { available: false };

const OPERATOR_MESSAGE = "hello conductor, what is the state of the work?";

async function deliver(profile, message = OPERATOR_MESSAGE) {
  const writes = [];
  const r = await V.retrieveAndDeliver({ message, budgetSource: async () => profile,
    journal: { entries: async () => [] },
    write: async text => { writes.push(text); return { written: true, submitted: true }; } });
  return { r, writes };
}

test("WO-4: an unmeasured budget DELIVERS the operator's own message to the writer", async () => {
  const { r, writes } = await deliver(unmeasured);
  assert.equal(writes.length, 1, "the writer must be called exactly once — this is the whole point");
  assert.equal(writes[0], OPERATOR_MESSAGE, "the writer receives the operator's own message, unaltered");
  assert.equal(r.written, true);
});

test("WO-4: an unmeasured-budget turn is not refused and reports state budget_unmeasurable", async () => {
  const { r } = await deliver(unmeasured);
  assert.notEqual(r.context.refused, true, "no refusal: the caller must deliver");
  assert.equal(r.context.state, "budget_unmeasurable");
  assert.equal(r.context.attached, false, "delivery without a view is still not an attached view");
});

test("WO-4: a MEASURED budget too small for the complete roster still withholds the turn", async () => {
  const { r, writes } = await deliver(tiny);
  assert.equal(writes.length, 0, "the writer must NOT be called when the measured budget cannot fit the roster");
  assert.equal(r.context.refused, true);
  assert.equal(r.written, false);
  assert.match(r.reason, /TRUNCATED/);
});

test("WO-4: the unmeasured notice and the withheld notice are different strings", async () => {
  const sent = await deliver(unmeasured);
  const withheld = await deliver(tiny);
  assert.notEqual(sent.r.context.notice, withheld.r.context.notice,
    "a failed measurement and a real budget that cannot fit must not report the same way");
});

test("WO-4: an unmeasured-budget result claims no pane count anywhere", async () => {
  const { r, writes } = await deliver(unmeasured);
  assert.equal(r.context.roster_attached, false);
  assert.deepEqual(r.context.pane_ids, []);
  assert.doesNotMatch(writes[0], /No worker panes are open/, "no roster rode along with the message");
  assert.doesNotMatch(r.context.notice, /\d+\s*(?:pane|terminal)/i, "the notice states no count");
  assert.doesNotMatch(r.context.notice, /No worker panes are open/);
});

test("WO-5: workspaceViewSummary gives budget_unmeasurable its own collapsed line", async () => {
  // The REAL renderer source, extracted the way conductor-context-surface.test.js does it.
  const rendererPath = path.resolve(__dirname, "../renderer/renderer.js");
  const source = fs.readFileSync(rendererPath, "utf8");
  const line = '  if (state === "budget_unmeasurable") return "Sent \u00B7 no context (budget unmeasured)";';
  assert.equal(source.split(line).length - 1, 1, "the summary line exists exactly once");
  assert.ok(source.indexOf(line) < source.indexOf('  if (state === "attached")'),
    "and sits before the attached branch it must be distinguished from");
  const a = source.indexOf("function workspaceViewNotice(turn)");
  const b = source.indexOf("(function wireConductorBar()", a);
  assert.ok(a >= 0 && b > a, "workspaceViewSummary region");
  const box = {};
  vm.createContext(box);
  vm.runInContext(source.slice(a, b), box);
  const summary = vm.runInContext("workspaceViewSummary", box);
  const turnOf = context => ({ utc: "2026-09-06T00:00:00Z", dir: "out",
    text: OPERATOR_MESSAGE, workspace_view: context });
  const sent = await deliver(unmeasured);
  const withheld = await deliver(tiny);
  const unmeasuredLine = summary(turnOf(sent.r.context));
  const withheldLine = summary(turnOf(withheld.r.context));
  assert.equal(unmeasuredLine, "Sent \u00B7 no context (budget unmeasured)");
  assert.equal(withheldLine, "No view \u00B7 /workspace");
  assert.notEqual(unmeasuredLine, withheldLine,
    "the collapsed line must distinguish a sent-without-context turn from a withheld one");
});
