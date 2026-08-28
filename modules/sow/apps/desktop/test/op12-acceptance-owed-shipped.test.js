"use strict";
/**
 * Phase 18D — the OWED block the check SHIPS, judged by the rules the receipt is judged by.
 *
 * `op12-acceptance-verdict.test.js` tests those rules exhaustively against SYNTHETIC blocks built
 * by its own `owedBlock()` fixture. Nothing had ever asserted the real constant. The 18D
 * gate-validator (MEDIUM-3) proved what that costs: it replaced `OWED.provider_node_record` with
 *
 *     "a Sovereign node record EXISTS for both providers and the 18C legs are unblocked"
 *
 * and the python suite, the desktop suite and the terminal suite all stayed green. The rules are
 * real and correct — they simply run at receipt-EMIT time, inside Electron, so a prose edit made
 * between two in-Electron runs is unguarded. That is the D-P16-0 blind spot in miniature, and this
 * file is the cheap half of the answer: point the existing rules at the shipped object.
 *
 * Why this matters more at 18D than it did at 18C: OP-12.1 moved the U227 boundary, which made
 * every OWED marker that explained itself by "the vocabulary refuses it" stale in one commit. The
 * markers had to be edited. Editing an honesty artifact with no test on it is how a skip-with-record
 * quietly becomes a claim.
 */
const test = require("node:test");
const assert = require("node:assert");

const { REQUIRED_OWED_KEYS, owedLegsAreNamed } = require("../selfcheck/op12-acceptance-verdict");
const { OWED } = require("../selfcheck/op12-acceptance-selfcheck");

test("the OWED block the check SHIPS satisfies the rules the receipt is judged by", () => {
  const v = owedLegsAreNamed(OWED);
  assert.equal(v.ok, true, v.reasons.join(" | "));
  assert.deepEqual(Object.keys(OWED).sort(), [...REQUIRED_OWED_KEYS].sort());
});

test("no shipped OWED marker asserts the leg was performed", () => {
  // A marker may (and does) say "no record EXISTS" — a negated existence claim is the honest form.
  // What it must never do is assert the affirmative. These are the shapes an over-claim actually
  // takes when prose is edited to follow a boundary that moved.
  const OVERCLAIM = [
    /\b(?:record|node|receipt|probe|lease|pane)s?\s+(?:now\s+)?exists?\b/i,
    /\bis (?:now )?unblocked\b/i,
    /\b(?:was|were|has been|have been) (?:performed|executed|completed)\b/i,
    /\bno longer owed\b/i,
  ];
  for (const key of Object.keys(OWED)) {
    const value = OWED[key];
    for (const rx of OVERCLAIM) {
      const hit = value.match(rx);
      // "no Sovereign node RECORD exists" is the negated form and is allowed; the affirmative is
      // not. Decided on the words immediately before the match rather than on the whole marker.
      const before = hit ? value.slice(Math.max(0, hit.index - 24), hit.index).toLowerCase() : "";
      const negated = /\b(no|never|none|not|nothing)\b[^.]*$/.test(before);
      assert.ok(!hit || negated,
        "OWED." + key + " asserts a performed leg (" + rx + " matched):\n" + value);
    }
  }
});

test("every shipped OWED marker still states what is OWED, not merely what happened", () => {
  // A marker rewritten into pure narration ("the operator ruled U227 on 2026-08-01 by successor
  // schema") would pass the reference rule while telling a reader nothing is outstanding.
  const OWING = /\b(owed|never|unmet|refused|unverifiable|stays|cannot|has not|no|not)\b/i;
  for (const key of Object.keys(OWED)) {
    assert.ok(OWING.test(OWED[key]),
      "OWED." + key + " does not state anything as outstanding:\n" + OWED[key]);
  }
});
