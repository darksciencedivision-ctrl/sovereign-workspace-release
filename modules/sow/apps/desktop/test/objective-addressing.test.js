"use strict";
/**
 * SW-CONDUCTOR-001 Phase 1 — delegation addressing.
 *
 * The defect: `selectObjectiveRecipients` never saw the objective text, so "terminal 2, redo
 * yours as a list" was delivered byte-identically to every live worker, and a worker that is not
 * terminal 2 had no way to know that — so it guessed. The repair: the objective's third parameter
 * (additive, broadcast default), addressing through conductor-view's `resolveTerminalRefs` (the
 * SAME parser the read path uses — no second parser), notices carried to the operator on the
 * skipped rows main.js already returns, and a one-line delivery-position statement in the prompt
 * so every recipient can tell a broadcast from a message meant for it alone.
 *
 * The operator's F-36 ruling is untouched and is guarded by its own protected file
 * (test/broadcast-delegation.test.js, green and unedited beside this one): an objective naming no
 * terminal reaches EVERY live worker, exactly as before.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const {
  selectObjectiveRecipients, selectObjectiveRecipientsFor, delegationPrompt, audienceFor,
  delegateToPane,
} = require("../control/conductor-delegation");

/** Three live worker panes, the F-36 fixture shape (camelCase records, as worker-spawn mints). */
function LIVE() {
  return [
    { nodeId: "n-a", paneId: "pane-2", chrome: { role: "reasoning" } },
    { nodeId: "n-b", paneId: "pane-3", chrome: { role: "coding" } },
    { nodeId: "n-c", paneId: "pane-4", chrome: { role: "reasoning" } },
  ];
}

/** A delegateToPane io with no journal, in the shape the record-once tests drive. */
function fakeIO(replyFor) {
  let clock = 0;
  let writtenBody = null;
  const io = {
    now: () => clock,
    sleep: async (ms) => { clock += ms; },
    log: () => {},
    window: { mark: () => 0, read: () => ({ answerable: true, text: replyFor(writtenBody), at: 1 }) },
    writePrompt: async (_paneId, body) => { writtenBody = body; return { written: true }; },
  };
  return { io, writtenBody: () => writtenBody };
}

test("SW-CONDUCTOR-001: an objective naming no terminal reaches every live worker, exactly as today", () => {
  const live = LIVE();
  const sel = selectObjectiveRecipientsFor(live, live, "summarize the release risks");
  assert.deepEqual(sel.recipients.map((r) => r.pane_id), ["pane-2", "pane-3", "pane-4"]);
  assert.deepStrictEqual(sel.recipients, selectObjectiveRecipients(live, live).recipients,
    "a naming-nothing objective selects precisely what the two-argument F-36 form selects");
  assert.deepStrictEqual(sel.skipped, []);
  assert.deepStrictEqual(sel.notices, []);
});

test("SW-CONDUCTOR-001: 'terminal 2, redo yours as a list' reaches pane-2 alone", () => {
  const live = LIVE();
  const sel = selectObjectiveRecipientsFor(live, live, "terminal 2, redo yours as a list");
  assert.equal(sel.recipients.length, 1);
  assert.equal(sel.recipients[0].pane_id, "pane-2");
  assert.equal(sel.recipients[0].node_id, "n-a");
  assert.equal(sel.recipients[0].pane_number, "2");
  assert.deepStrictEqual(sel.skipped, []);
  assert.deepStrictEqual(sel.notices, []);
});

test("SW-CONDUCTOR-001: addressing resolves the production pane-id shape too (worker-pane-N)", () => {
  const live = [
    { nodeId: "n-a", paneId: "worker-pane-2", chrome: { role: "reasoning" } },
    { nodeId: "n-b", paneId: "worker-pane-3", chrome: { role: "coding" } },
  ];
  const sel = selectObjectiveRecipientsFor(live, live, "worker-pane-3, restate your answer as bullets");
  assert.equal(sel.recipients.length, 1);
  assert.equal(sel.recipients[0].pane_id, "worker-pane-3");
});

test("SW-CONDUCTOR-001: resolveTerminalRefs's grammar is the addressing grammar — no second parser", () => {
  const live = LIVE();
  // Ordinals the parser HAS: "third pane" / "2nd terminal" resolve by pane NUMBER.
  const third = selectObjectiveRecipientsFor(live, live, "the third pane, redo yours");
  assert.deepEqual(third.recipients.map((r) => r.pane_id), ["pane-3"],
    "'the third pane' is terminal #3, per resolveTerminalRefs — the pane whose number is 3");
  const second = selectObjectiveRecipientsFor(live, live, "2nd terminal, restate as a list");
  assert.deepEqual(second.recipients.map((r) => r.pane_id), ["pane-2"]);
  // A phrase the parser does NOT match attempts no addressing, and the F-36 broadcast stands.
  // (The loop document's "the third one" bullet is conditional on resolveTerminalRefs semantics;
  // its ordinal regex requires "third terminal|pane", so "the third one" names no terminal.)
  const one = selectObjectiveRecipientsFor(live, live, "the third one, redo yours");
  assert.deepEqual(one.recipients.map((r) => r.pane_id), ["pane-2", "pane-3", "pane-4"]);
  assert.deepStrictEqual(one.notices, []);
  assert.equal(audienceFor("the third one, redo yours", "pane-4").addressed, false);
});

test("SW-CONDUCTOR-001: a named terminal that is not open delivers to NOBODY and says so — never a broadcast", () => {
  const live = LIVE();
  const sel = selectObjectiveRecipientsFor(live, live, "terminal 9, restate the answer");
  assert.deepStrictEqual(sel.recipients, [], "three live panes exist; a miss must not reach them");
  assert.ok(sel.notices.some((n) => /no terminal 9 is open/.test(n)), JSON.stringify(sel.notices));
  assert.ok(sel.notices.some((n) => /delivered to no one/.test(n)), JSON.stringify(sel.notices));
  // The notices ride skipped rows — the channel main.js already folds into the delegations it
  // returns, so the operator sees them without a main.js change beyond the objective argument.
  assert.ok(sel.skipped.some((row) => /no terminal 9 is open/.test(row.reason)
    && row.delivered === false && row.answered === false));
  assert.ok(sel.skipped.some((row) => /delivered to no one/.test(row.reason)));
});

test("SW-CONDUCTOR-001: a named terminal that is not live is reported, and the named live one still receives", () => {
  const live = [{ nodeId: "n-a", paneId: "pane-2", chrome: { role: "reasoning" } }];
  const registered = [live[0],
    { nodeId: "n-b", paneId: "pane-3", state: "exited" },
    { nodeId: "n-c", paneId: "pane-4", state: "exited" }];
  const sel = selectObjectiveRecipientsFor(live, registered, "terminals #2 and #3, redo yours");
  assert.deepEqual(sel.recipients.map((r) => r.pane_id), ["pane-2"]);
  assert.ok(sel.notices.some((n) => /terminal 3 is not live/.test(n)), JSON.stringify(sel.notices));
  const row = sel.skipped.find((r) => /terminal 3 is not live/.test(r.reason));
  assert.ok(row, "the not-live notice rides a skipped row");
  assert.equal(row.node_id, "n-b", "the row names the record the notice is about");
  assert.equal(row.pane_id, "pane-3");
  assert.equal(row.delivered, false);
  // The unaddressed registered record (pane-4) gets no row: it was never a candidate.
  assert.equal(sel.skipped.filter((r) => r.pane_id === "pane-4").length, 0);
  // Parser grammar, documented: a bare "and 3" carries no # and no terminal/pane word, so
  // "terminals 2 and 3" resolves ONLY 2 — and even then nothing broadcasts to 3 or 4.
  const bare = selectObjectiveRecipientsFor(live, registered, "terminals 2 and 3, redo yours");
  assert.deepEqual(bare.recipients.map((r) => r.pane_id), ["pane-2"]);
  assert.deepStrictEqual(bare.notices, []);
});

test("SW-CONDUCTOR-001: the prompt a sole addressee receives differs from the prompt a broadcast recipient receives", () => {
  const live = LIVE();
  selectObjectiveRecipientsFor(live, live, "count the open risks");
  selectObjectiveRecipientsFor(live, live, "terminal 3, count the open risks");
  const audBroadcast = audienceFor("count the open risks", "pane-3");
  const audSole = audienceFor("terminal 3, count the open risks", "pane-3");
  assert.equal(audBroadcast.addressed, false);
  assert.equal(audBroadcast.recipient_count, 3);
  assert.equal(audSole.addressed, true);
  assert.equal(audSole.recipient_count, 1);
  // The SAME task, so the only possible difference is the delivery-position line.
  const task = { task_id: "t-position", objective: "count the open risks" };
  const promptBroadcast = delegationPrompt(task, audBroadcast);
  const promptSole = delegationPrompt(task, audSole);
  assert.notEqual(promptSole, promptBroadcast);
  assert.ok(promptSole.includes("Delivery: addressed to terminal #3 alone"), promptSole);
  assert.ok(promptBroadcast.includes("Delivery: broadcast"), promptBroadcast);
  assert.ok(promptBroadcast.includes("(3 recipients); you are terminal #3"), promptBroadcast);
  // The position line never re-introduces tool vocabulary a local REPL does not have.
  for (const p of [promptBroadcast, promptSole]) {
    assert.ok(!/publish_candidate|publish_progress|send_message/.test(p), p);
    assert.match(p, /Answer directly and completely in this terminal/);
  }
});

test("SW-CONDUCTOR-001: two-argument calls behave exactly as today and leave no state behind", () => {
  const live = [
    { nodeId: "n-a", paneId: "pane-2", chrome: { role: "reasoning" } },
    { nodeId: "n-b", paneId: "pane-3", chrome: { role: "coding" } },
  ];
  const registered = [live[0], live[1], { nodeId: "n-idle", paneId: "pane-9", state: "exited" }];
  const two = selectObjectiveRecipients(live, registered);
  // Today's exact selection: every live pane a recipient; the registered-not-live node skipped
  // with its reason. deepStrictEqual pins the whole row shape, pane_number included.
  assert.deepStrictEqual(two.recipients, [
    { node_id: "n-a", pane_id: "pane-2", role: "reasoning", pane_number: "2" },
    { node_id: "n-b", pane_id: "pane-3", role: "coding", pane_number: "3" },
  ]);
  assert.deepStrictEqual(two.skipped, [
    { node_id: "n-idle", pane_id: "pane-9", delivered: false, answered: false,
      reason: "no live pane is registered for this assignment", pane_number: "9" },
  ]);
  assert.deepStrictEqual(two.notices, []);
  const emptyText = selectObjectiveRecipientsFor(live, registered, "");
  assert.deepStrictEqual(emptyText.recipients, two.recipients);
  assert.deepStrictEqual(emptyText.skipped, two.skipped);
  // No audience was recorded for an unselected objective, so the prompt is the pre-addressing one.
  const legacy = delegationPrompt({ task_id: "t-legacy", objective: "an objective never selected here" });
  assert.ok(!legacy.includes("Delivery:"), legacy);
  assert.match(legacy, /SOVEREIGN TASK t-legacy/);
  assert.equal(audienceFor("an objective never selected here", "pane-2"), null);
});

test("SW-CONDUCTOR-001: the position line rides the real delegation write — addressed and broadcast", async () => {
  const live = LIVE();
  const addressedText = "terminal 4, restate your answer as a list";
  const sel = selectObjectiveRecipientsFor(live, live, addressedText);
  assert.equal(sel.recipients.length, 1);
  const addressed = fakeIO((body) => (body || "") + "\r\nADDRESSED-WORKER-ANSWER");
  const r1 = await delegateToPane(addressed.io, {
    paneId: sel.recipients[0].pane_id, nodeId: sel.recipients[0].node_id,
    task: { task_id: "t-e2e-a", objective: addressedText, expected_output: "a list" },
    timeoutMs: 500, pollMs: 1, quietMs: 2,
  });
  assert.equal(r1.answered, true);
  assert.match(r1.candidate.content, /ADDRESSED-WORKER-ANSWER/);
  // flattenBody collapses the prompt's newlines to spaces at the write boundary; the line itself
  // carries no newline, so it survives as one substring.
  assert.ok(addressed.writtenBody().includes("Delivery: addressed to terminal #4 alone"),
    addressed.writtenBody());
  assert.ok(addressed.writtenBody().includes("SOVEREIGN TASK t-e2e-a"));

  const broadcastText = "summarize the deployment order";
  const bsel = selectObjectiveRecipientsFor(live, live, broadcastText);
  assert.equal(bsel.recipients.length, 3);
  const broadcast = fakeIO((body) => (body || "") + "\r\nBROADCAST-WORKER-ANSWER");
  const r2 = await delegateToPane(broadcast.io, {
    paneId: "pane-3", nodeId: "n-b",
    task: { task_id: "t-e2e-b", objective: broadcastText, expected_output: "a summary" },
    timeoutMs: 500, pollMs: 1, quietMs: 2,
  });
  assert.equal(r2.answered, true);
  assert.ok(broadcast.writtenBody().includes("(3 recipients); you are terminal #3"),
    broadcast.writtenBody());
});

test("SW-CONDUCTOR-001: a pane outside the audience gets no position line", () => {
  const live = LIVE();
  selectObjectiveRecipientsFor(live, live, "terminal 2, only you answer this one");
  assert.equal(audienceFor("terminal 2, only you answer this one", "pane-3"), null,
    "pane-3 did not receive this objective; nothing may claim it did");
  const prompt = delegationPrompt({ task_id: "t-out", objective: "terminal 2, only you answer this one" },
    audienceFor("terminal 2, only you answer this one", "pane-3"));
  assert.ok(!prompt.includes("Delivery:"), prompt);
});

test("SW-CONDUCTOR-001 mutation control: a named-terminal miss falling back to broadcast fails the zero-recipients test", () => {
  const filename = require.resolve("../control/conductor-delegation");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = "  const addressed = recipients.filter((r) => named.has(r.pane_id) || named.has(r.node_id));";
  assert.ok(source.includes(anchor), "the addressing-filter anchor must exist in the source");
  assert.equal(source.split(anchor).length - 1, 1, "the anchor must be unique");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor,
    "  let addressed = recipients.filter((r) => named.has(r.pane_id) || named.has(r.node_id));\n"
    + "  if (!addressed.length) addressed = recipients;"), filename);
  const live = LIVE();
  const real = selectObjectiveRecipientsFor(live, live, "terminal 9, restate the answer");
  assert.equal(real.recipients.length, 0);
  const leaked = mutant.exports.selectObjectiveRecipientsFor(live, live, "terminal 9, restate the answer");
  assert.equal(leaked.recipients.length, 3,
    "with the broadcast fallback restored, the miss reaches every live pane — the zero-recipients "
    + "assertion above is exactly what catches it");
  assert.equal(fs.readFileSync(filename, "utf8"), source, "the source on disk is untouched");
});

test("SW-CONDUCTOR-001: the receipt map is capped — the oldest objective evicts first", () => {
  const live = LIVE();
  const first = "eviction probe zero — names no terminal";
  selectObjectiveRecipientsFor(live, live, first);
  assert.ok(audienceFor(first, "pane-2"), "the receipt exists before eviction");
  for (let i = 1; i <= 40; i += 1) {
    selectObjectiveRecipientsFor(live, live, `eviction probe ${i} — names no terminal`);
  }
  assert.equal(audienceFor(first, "pane-2"), null, "the oldest receipt evicted");
  assert.ok(audienceFor("eviction probe 40 — names no terminal", "pane-2"), "the newest did not");
});
