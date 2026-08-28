"use strict";
/**
 * Phase 17C `.close` — the echo confirmation that gates the submit key.
 *
 * These tests exist because the first version of that gate was a substring test and it FAILED on a live
 * run whose pane demonstrably rendered the utterance in full: a ConPTY repaint of a full-screen TUI
 * splits the line with cursor moves, borders, padding and status text. The rule has to tolerate that
 * noise without tolerating a truncated or altered utterance — because what depends on it is whether a
 * bare `\r` is sent into a live agentic session (invariant 25: it must never answer that session's own
 * permission prompt, and a prompt does not echo typed text).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { echoedInOrder, segmentsOf, alnumOnly } = require("../voice/echo-confirm");

const BODY = "What is 37 plus 32? Answer with only the sum and nothing else.";

test("a clean contiguous echo is confirmed", () => {
  const r = echoedInOrder(`[2K❯ ${BODY}[0m`, BODY);
  assert.strictEqual(r.echoed, true);
  assert.strictEqual(r.matchedSegments, r.totalSegments);
});

test("a repaint that SPLITS the utterance with interleaved chrome is still confirmed", () => {
  // The observed failure mode: the pane rendered the whole sentence, but the emitted bytes carried it
  // in pieces separated by borders, cursor moves and the status line.
  const emitted = "[H╭────────╮[K│ ❯ What is 37 plus"
    + "[12;1H────────────────[K⏸ manual mode on"
    + "[3;5H 32? Answer with only[K"
    + "│ the sum and nothing else. │[K? for shortcuts";
  const r = echoedInOrder(emitted, BODY);
  assert.strictEqual(r.echoed, true, `only matched ${r.matchedSegments}/${r.totalSegments}`);
});

test("a wrapped input box does not defeat it", () => {
  const emitted = "│ What is 37 plus 32? Answer with only the │\n│ sum and nothing else.  │";
  assert.strictEqual(echoedInOrder(emitted, BODY).echoed, true);
});

test("a HEAD-ONLY echo is accepted — and reports the ratio, because that is the honest limit", () => {
  // Measured on this host: the live TUI's repaint stream carries the head of a freshly-written utterance
  // and not the tail (2/5) while the screen shows the whole sentence. A gate demanding more refuses a
  // delivery the pane accepted — so the rule is "this utterance's text came back", and the fact that it
  // cannot also prove byte-integrity is reported (`ratio`) rather than hidden behind a boolean.
  const r = echoedInOrder("❯ What is 37 plus 32? Answer", BODY);
  assert.strictEqual(r.echoed, true);
  assert.strictEqual(r.matchedSegments, 2);
  assert.ok(r.ratio < 1, "a partial echo must not read as a complete one");
  assert.ok(r.firstMissingSegment, "…and must say which run went missing");
});

test("ONE segment is not enough for a multi-segment utterance", () => {
  const r = echoedInOrder("❯ What is 37 plus", BODY);
  assert.strictEqual(r.echoed, false);
  assert.strictEqual(r.matchedSegments, 1);
});

test("a single-segment utterance must match its one segment", () => {
  assert.strictEqual(echoedInOrder("❯ yes please", "yes please").echoed, true);
  assert.strictEqual(echoedInOrder("❯ yes pl", "yes please").echoed, false);
});

test("a pane that echoed NOTHING is refused with zero segments matched", () => {
  // What an open permission prompt looks like: it ignores the typed body entirely.
  const prompt = "Do you want to proceed?\n❯ 1. Yes\n  2. Yes, and don't ask again\n  3. No";
  const r = echoedInOrder(prompt, BODY);
  assert.strictEqual(r.echoed, false);
  assert.strictEqual(r.matchedSegments, 0);
});

test("a DIFFERENT utterance in the pane is refused", () => {
  const other = "❯ Summarize the build status for me please, in one line.";
  const r = echoedInOrder(other, BODY);
  assert.strictEqual(r.echoed, false);
  assert.ok(r.ratio < 0.6);
});

test("reordering is tolerated by design; a single stray run is not enough", () => {
  // A repaint may emit screen LINES out of order, so the rule counts runs found in order rather than
  // demanding a strict sequence over the whole utterance.
  const segs = segmentsOf(BODY);
  const oneDisplaced = [segs[2], segs[0], segs[1], ...segs.slice(3)].join("|");
  assert.strictEqual(echoedInOrder(oneDisplaced, BODY).echoed, true);
  assert.strictEqual(echoedInOrder(segs[3], BODY).echoed, false);
});

test("an empty utterance can never be confirmed", () => {
  for (const b of ["", "   ", "?!.", null, undefined]) {
    const r = echoedInOrder("anything at all", b);
    assert.strictEqual(r.echoed, false, `body=${JSON.stringify(b)}`);
    assert.strictEqual(r.totalSegments, 0);
  }
});

test("segments are consecutive and reconstruct the alnum view exactly", () => {
  assert.strictEqual(segmentsOf(BODY).join(""), alnumOnly(BODY));
  assert.ok(segmentsOf(BODY).slice(0, -1).every((s) => s.length === 10));
});

test("the same utterance twice needs a NEW echo — the caller searches only what was appended", () => {
  // The caller passes the appended region, not the whole scrollback; this test pins the contract that
  // makes that sufficient: an echo present only in the earlier region is invisible here.
  const earlier = `❯ ${BODY}`;
  const appended = "";
  assert.strictEqual(echoedInOrder(appended, BODY).echoed, false);
  assert.strictEqual(echoedInOrder(earlier, BODY).echoed, true);
});
