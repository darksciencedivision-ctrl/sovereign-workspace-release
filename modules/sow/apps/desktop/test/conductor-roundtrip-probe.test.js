"use strict";
/**
 * Phase 17A `.roundtrip` — the falsifiability core of the type→answer receipt.
 *
 * The receipt's whole claim is "a LIVE model answered what the operator typed". The only thing that
 * separates that claim from "a terminal echoed my keystrokes" is the probe: the answer token must be
 * something the pane CANNOT contain unless a model computed it. These tests pin that property —
 * without them the receipt could pass on an echo, which is precisely the failure mode the operator's
 * black pane (F3) would otherwise hide.
 */
const test = require("node:test");
const assert = require("node:assert");

const {
  spellNumber, buildRoundTripProbe, squash, containsAcrossWrap,
  probeIsFalsifiable, answerObserved, promptEchoed,
} = require("../conductor/roundtrip-probe");

test("spellNumber writes 21..99 without a single digit", () => {
  for (let n = 21; n <= 99; n++) {
    const w = spellNumber(n);
    assert.ok(/^[a-z-]+$/.test(w), `${n} -> ${w} is not word-only`);
    assert.ok(!/\d/.test(w), `${n} -> ${w} leaked a digit`);
  }
  assert.equal(spellNumber(31), "thirty-one");
  assert.equal(spellNumber(50), "fifty");
  assert.equal(spellNumber(99), "ninety-nine");
});

test("spellNumber refuses what it cannot spell (fail closed, never a digit fallback)", () => {
  assert.throws(() => spellNumber(20));
  assert.throws(() => spellNumber(100));
  assert.throws(() => spellNumber(4.5));
});

test("the probe's answer is NEVER derivable from the prompt (the anti-echo property)", () => {
  // exhaustive over the whole draw space, not a sample: every prompt this check can ever type must
  // be free of its own answer.
  for (let a = 21; a <= 99; a++) {
    for (let b = 21; b <= 99; b++) {
      const p = buildRoundTripProbe(() => 0, { a, b });
      assert.ok(probeIsFalsifiable(p), `probe ${a}+${b} contains its own answer: ${p.prompt}`);
      assert.ok(!/\d/.test(p.prompt), `prompt for ${a}+${b} leaked a digit: ${p.prompt}`);
      assert.equal(p.expectedNumber, String(a + b));
      assert.equal(p.expectedToken, `SUM=${a + b}`);
    }
  }
});

test("buildRoundTripProbe draws from the injected randomness and stays in the spellable band", () => {
  const draws = [];
  const randInt = (min, max) => { draws.push([min, max]); return min; };
  const p = buildRoundTripProbe(randInt);
  assert.deepEqual(draws, [[21, 99], [21, 99]]);
  assert.equal(p.prompt, "Answer with only SUM=<number> and nothing else. What is twenty-one plus twenty-one?");
  assert.equal(p.expectedToken, "SUM=42");
  const q = buildRoundTripProbe(); // default randomness stays inside the band
  assert.ok(q.a >= 21 && q.a <= 99 && q.b >= 21 && q.b <= 99);
});

test("squash/containsAcrossWrap survive xterm line wrapping and re-flow", () => {
  assert.equal(squash("  SUM = 42\n"), "sum=42");
  // the answer split across two rendered rows — exactly what a narrow pane does to a token
  assert.ok(containsAcrossWrap("… tail SU\nM=42 head …", "SUM=42"));
  assert.ok(containsAcrossWrap("s u m = 4 2", "SUM=42"));
  assert.ok(!containsAcrossWrap("SUM=43", "SUM=42"));
});

test("answerObserved does not fire on the ECHO of the prompt", () => {
  const p = buildRoundTripProbe(() => 0, { a: 31, b: 52 });
  const echoOnly = `> ${p.prompt}\n(waiting)`;
  assert.equal(answerObserved(echoOnly, p).seen, false);
  assert.equal(promptEchoed(echoOnly, p), true);
});

test("answerObserved reports WHICH form the model answered in", () => {
  const p = buildRoundTripProbe(() => 0, { a: 31, b: 52 }); // 83
  const prefixed = answerObserved(`${p.prompt}\n\n⏺ SUM=83\n`, p);
  assert.equal(prefixed.seen, true);
  assert.equal(prefixed.form, "prefixed");
  const bare = answerObserved(`${p.prompt}\n\n⏺ 83\n`, p);
  assert.equal(bare.seen, true);
  assert.equal(bare.form, "bare");
  assert.equal(answerObserved(`${p.prompt}\n\n⏺ 84\n`, p).seen, false);
});

test("the BARE form never fires on a digit string that merely contains the answer", () => {
  const p = buildRoundTripProbe(() => 0, { a: 31, b: 52 }); // 83
  assert.equal(answerObserved("Claude Code v2.1.831", p).seen, false);
  assert.equal(answerObserved("183 files", p).seen, false);
  assert.equal(answerObserved("838", p).seen, false);
  assert.equal(answerObserved("cost 0.83", p).seen, false); // 0.83 — the 83 is not standalone
  assert.equal(answerObserved("row 83 of 90", p).seen, true); // a genuine standalone token
});

test("the live CLI's own chrome cannot be mistaken for the model's answer", () => {
  const p = buildRoundTripProbe(() => 0, { a: 31, b: 52 }); // 83
  // the spinner line the interactive `claude` TUI paints while it is thinking
  assert.equal(answerObserved("✻ Puttering… (83 tokens · esc to interrupt)", p).seen, false);
  assert.equal(answerObserved("✻ Baked for 83s", p).seen, false);
  assert.equal(answerObserved("context 83%", p).seen, false);
  assert.equal(answerObserved("83/100", p).seen, false);
  assert.equal(answerObserved("elapsed 83 seconds", p).seen, false);
  assert.equal(answerObserved("83 sec", p).seen, false);
  assert.equal(answerObserved("1,835 files", p).seen, false);   // part of a larger figure
  assert.equal(answerObserved("12:83", p).seen, false);         // a clock field, not an answer
  assert.equal(answerObserved("83:12", p).seen, false);
  // …but the same number as an actual reply still counts, in either form
  assert.equal(answerObserved("⏺ 83", p).seen, true);
  assert.equal(answerObserved("⏺ SUM=83 (83 tokens)", p).form, "prefixed");
});

test("promptEchoed keys on the ARITHMETIC, not on boilerplate every pane would show", () => {
  const p = buildRoundTripProbe(() => 0, { a: 31, b: 52 });
  assert.equal(promptEchoed("Answer with only SUM=<number> and nothing else.", p), false);
  assert.equal(promptEchoed("what is thirty-one plus fifty-two?", p), true);
  assert.equal(promptEchoed("what is thirty-one plus fifty-three?", p), false);
  assert.equal(promptEchoed("", p), false);
});
