"use strict";
/**
 * Phase 17C `.close` — the SPOKEN round-trip probe (unit tests, written before the module).
 *
 * `.mic` proved the operator's own PCM reaches the real WSL Parakeet engine and that a CHAT transcript
 * is written into an admitted pane's ConPTY. What it could NOT claim is directive §16's actual words for
 * track 17C — *"→ the LIVE 17A conductor session"*: its delivery pane was a `powershell.exe` stand-in.
 * `.close` delivers into the genuinely live `claude` session and waits for the conductor's ANSWER, which
 * needs a probe that can tell an ECHO of the transcript apart from a MODEL's reply.
 *
 * The hard part is that speech is not typing. 17A could spell its operands in words and assert the
 * prompt contained no digit at all; here the words are spoken and an ASR renders them however it likes
 * ("twenty-three" → "23", "Twenty three", "twenty-three"). So the expected answer is derived from THE
 * TRANSCRIPT — what the conductor was actually asked — not from what the fixture said. A misheard
 * operand then yields a different-but-correct expectation instead of a false failure, and the receipt
 * records both so the divergence is visible rather than smoothed over.
 *
 * Falsifiability is preserved by two assertions this module supports: the answer must be absent from the
 * transcript itself (so the pane cannot satisfy it by echoing what was delivered), and the caller
 * asserts it absent from the pane before delivery.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const {
  buildSpokenProbe, buildTypedProbe, parseHeardArithmetic, carriesNumber, spokenProbeIsFalsifiable,
  SPOKEN_BAND, answerAfterAnchor,
} = require("../voice/spoken-probe");

// `.disarm` (U166): the SECOND prompt of a run is TYPED, after the operator's keystroke ended the
// voice turn — so tool use is no longer denied. Asking that prompt to "use a tool" would invite the
// CLI to paint tool chrome full of fresh numbers between the prompt and the reply, which is exactly
// the shape `answerAfterAnchor`'s exclusions cannot fully cover. It asks for the sum and nothing else.

test("the typed probe asks for no tool, carries no digits, and never carries its own answer", () => {
  const p = buildTypedProbe(() => 23);
  assert.equal(p.expectedNumber, "46");
  assert.doesNotMatch(p.phrase, /\d/);
  assert.doesNotMatch(p.phrase, /tool/i);
  assert.match(p.phrase, /plus/);
  for (let i = 0; i < 200; i++) {
    assert.equal(spokenProbeIsFalsifiable(buildTypedProbe()), true);
  }
});

test("the drawn phrase is speakable: digit-free, spelled operands, one question", () => {
  const p = buildSpokenProbe(() => 23);
  assert.match(p.phrase, /twenty-three/);
  assert.ok(!/\d/.test(p.phrase), "a spoken phrase must contain no digit — the synthesizer says words");
  assert.strictEqual(p.expectedNumber, "46");
  assert.strictEqual(p.a, 23);
  assert.strictEqual(p.b, 23);
});

test("both operands and the sum stay inside the spellable band", () => {
  const draws = [];
  const randInt = (min, max) => { draws.push([min, max]); return max; };
  const p = buildSpokenProbe(randInt);
  assert.deepStrictEqual(draws, [[SPOKEN_BAND.min, SPOKEN_BAND.max], [SPOKEN_BAND.min, SPOKEN_BAND.max]]);
  assert.ok(p.a + p.b <= 99, "the sum must be spellable so its WORD form can be excluded too");
  assert.ok(SPOKEN_BAND.min >= 21, "below 21 the operands are single words and collide with ordinary speech");
});

test("the phrase carries neither the answer's digits nor its word form", () => {
  const p = buildSpokenProbe(() => 24); // 48 — "forty-eight"
  assert.strictEqual(p.expectedNumber, "48");
  assert.ok(spokenProbeIsFalsifiable(p), "a phrase containing its own answer would prove nothing");
});

test("a phrase that leaks its own answer is rejected", () => {
  const leaky = { phrase: "What is twenty-four plus twenty-four? The answer is forty-eight.", expectedNumber: "48" };
  assert.strictEqual(spokenProbeIsFalsifiable(leaky), false);
  const digits = { phrase: "What is twenty-four plus twenty-four? Reply 48.", expectedNumber: "48" };
  assert.strictEqual(spokenProbeIsFalsifiable(digits), false);
});

test("the generated probe contains no gated verb anywhere — the bridge routes it as CHAT", () => {
  // voice_bridge/spoken_verbs.split_spoken_command scans every word; PROTECTED/DESTRUCTIVE ones
  // (spawn/make/create/start/stop/delete/grant/approve…) would be PROPOSED to the approval queue and
  // never delivered (invariant 25) — the delivery leg would then be unreachable through no fault of
  // the shell. "Use a tool" deliberately challenges the per-turn tool-deny boundary without using
  // a broker-gated verb.
  const p = buildSpokenProbe(() => 30);
  assert.match(p.phrase.trim().toLowerCase(), /^use a tool /);
});

test("the heard arithmetic parses when the ASR writes digits", () => {
  const h = parseHeardArithmetic("What is 23 plus 45? Answer with only the sum and nothing else.");
  assert.strictEqual(h.a, 23);
  assert.strictEqual(h.b, 45);
  assert.strictEqual(h.expectedNumber, "68");
});

test("…and when it writes words, hyphenated or not, in any case", () => {
  for (const t of ["What is twenty-three plus forty-five?", "what is Twenty Three plus Forty Five?",
    "What is twenty-three plus 45?"]) {
    const h = parseHeardArithmetic(t);
    assert.ok(h, `no parse for ${JSON.stringify(t)}`);
    assert.strictEqual(h.expectedNumber, "68", `wrong sum for ${JSON.stringify(t)}`);
  }
});

test("teens and bare units parse too — the ASR is not obliged to stay in the drawn band", () => {
  assert.strictEqual(parseHeardArithmetic("what is nineteen plus seven").expectedNumber, "26");
  assert.strictEqual(parseHeardArithmetic("what is ninety plus nine").expectedNumber, "99");
});

test("a '+' sign is accepted; a vague connective is NOT", () => {
  assert.strictEqual(parseHeardArithmetic("what is 23 + 45?").expectedNumber, "68");
  // "and" is how speech renders lists as well as sums; guessing would silently change the expected
  // answer, so it fails closed and the receipt records the unparsed transcript verbatim.
  assert.strictEqual(parseHeardArithmetic("what is 23 and 45?"), null);
});

test("a transcript with no arithmetic yields null, never a guess", () => {
  assert.strictEqual(parseHeardArithmetic("the conductor should summarize the build status"), null);
  assert.strictEqual(parseHeardArithmetic(""), null);
  assert.strictEqual(parseHeardArithmetic(null), null);
});

test("the matched span is reported, so a receipt can show WHAT was parsed", () => {
  const h = parseHeardArithmetic("Um, what is 23 plus 45? Answer with only the sum.");
  assert.match(h.matched, /23\s*plus\s*45/i);
});

test("carriesNumber sees both the digits and the word form of a number", () => {
  assert.strictEqual(carriesNumber("the sum is 68", 68), true);
  assert.strictEqual(carriesNumber("the sum is sixty-eight", 68), true);
  assert.strictEqual(carriesNumber("the sum is sixty eight", 68), true);
  assert.strictEqual(carriesNumber("SUM=68", 68), true);
});

test("carriesNumber does not fire on a number that is part of a larger figure", () => {
  // The live CLI's own chrome prints bare numbers constantly; crediting the model for "168 tokens"
  // would make the receipt worthless.
  assert.strictEqual(carriesNumber("v2.1.681 built", 68), false);
  assert.strictEqual(carriesNumber("168 tokens", 68), false);
  assert.strictEqual(carriesNumber("68 tokens · esc to interrupt", 68), false);
  assert.strictEqual(carriesNumber("baked for 68s", 68), false);
  assert.strictEqual(carriesNumber("", 68), false);
});

test("carriesNumber skips the word form outside the spellable band rather than throwing", () => {
  assert.strictEqual(carriesNumber("the total is 142", 142), true);
  assert.strictEqual(carriesNumber("nothing here", 142), false);
});

// -- the answer must appear AFTER the delivered utterance ---------------------------------------
// The gate-validator demonstrated (R2/D-3) that `carriesNumber` fires on real Claude Code chrome:
// "⎿ Read 69 lines", "⧉ 69 lines selected", "↑69 ↓12", "69 files changed" all contain the drawn sum in
// a shape the unit-suffix exclusions do not cover. The pre-delivery absence snapshot is also ~35 s
// stale by the time the transcript is delivered, so anything the CLI paints in that window is
// unguarded. Anchoring the search to the text AFTER the last echo of the utterance closes both: the
// model's reply is necessarily after its own prompt, and the anchor doubles as the proof that the WHOLE
// utterance arrived — not just the arithmetic fragment at the front of it.

test("the answer is seen only after the last echo of the utterance", () => {
  const pane = "❯ What is 37 plus 32? Answer with only the sum and nothing else.\n● 69\n✻ Crunched for 2s";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum and nothing else.", 69);
  assert.strictEqual(r.anchored, true);
  assert.strictEqual(r.seen, true);
});

test("chrome carrying the sum BEFORE the utterance does not count as an answer", () => {
  const pane = "⎿ Read 69 lines\n↑69 ↓12\n❯ What is 37 plus 32? Answer with only the sum and nothing else.";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum and nothing else.", 69);
  assert.strictEqual(r.anchored, true);
  assert.strictEqual(r.seen, false, "everything carrying 69 is above the prompt — the model has not replied");
});

test("a PARTIAL echo does not anchor: a truncated delivery cannot pass", () => {
  // The exact hole the validator found: `heard.matched` ("37 plus 32") is at the FRONT of the phrase,
  // so a delivery truncated after it would still echo, and the sum alone would satisfy the answer leg.
  const pane = "❯ What is 37 plus 32?\n● 69";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum and nothing else.", 69);
  assert.strictEqual(r.anchored, false);
  assert.strictEqual(r.seen, false);
});

test("the anchor survives a wrapped input box and interleaved chrome", () => {
  // xterm wraps the input line and the TUI paints borders around it; the comparison is on
  // alphanumerics, so neither can hide the utterance or fabricate it.
  const pane = "│ What is 37 plus 32? Answer with only the │\n│ sum and nothing else.                    │\n● 69";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum and nothing else.", 69);
  assert.strictEqual(r.anchored, true);
  assert.strictEqual(r.seen, true);
});

test("the answer may be spelled in words after the anchor", () => {
  const pane = "❯ What is 37 plus 32?\n● The sum is sixty-nine.";
  const r = answerAfterAnchor(pane, "What is 37 plus 32?", 69);
  assert.strictEqual(r.seen, true);
});

// `.close-revalidate` (spec-audit MAJOR-5): the OPERANDS are the question, not a reply. `replied` was
// "any standalone 2–3 digit number after the anchor", and the utterance carries two of them in the
// probe's own band — so a pane that merely repainted the question satisfied the leg the track is
// named for.
test("a repaint of the question after the anchor is NOT a reply", () => {
  const pane = "❯ What is 37 plus 32? Answer with only the sum and nothing else.\n"
    + "❯ What is 37 plus 32? Answer with only the sum and nothing else.\n⏸ manual mode on";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum and nothing else.", 69);
  assert.strictEqual(r.anchored, true);
  assert.strictEqual(r.replied, false, "37 and 32 are the operator's own words coming back");
  assert.strictEqual(r.number, null);
  assert.deepStrictEqual(r.excluded.sort((a, b) => a - b), [32, 37]);
});

test("a stalled reply that only restates the operands is not a reply either", () => {
  const pane = "❯ What is 37 plus 32? Answer with only the sum and nothing else.\n● 37 + 32 =";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum and nothing else.", 69);
  assert.strictEqual(r.replied, false);
  assert.strictEqual(r.correct, false);
});

test("a WRONG number of the conductor's own still counts as a reply (measured: it answered 67)", () => {
  const pane = "❯ What is 37 plus 32? Answer with only the sum and nothing else.\n● 67";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum and nothing else.", 69);
  assert.strictEqual(r.replied, true);
  assert.strictEqual(r.number, 67);
  assert.strictEqual(r.correct, false, "correctness is recorded, never gated");
});

test("the sum is never excluded even if the exclusion list would cover it", () => {
  const pane = "❯ What is 37 plus 32? Answer with only the sum and nothing else.\n● 37 + 32 = 69";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum and nothing else.", 69);
  assert.strictEqual(r.correct, true);
  assert.strictEqual(r.seen, true);
});

test("answerAfterAnchor fails closed on junk input", () => {
  assert.strictEqual(answerAfterAnchor(null, "x", 5).anchored, false);
  assert.strictEqual(answerAfterAnchor(null, "x", 5).seen, false);
  assert.strictEqual(answerAfterAnchor("text", "", 5).anchored, false);
});

// -- a WRONG answer is still an answer ----------------------------------------------------------
// Measured on this host: asked "What is 37 plus 47? Answer with only the sum and nothing else.", the
// live Fable-5 conductor replied "● 67". The arithmetic is wrong. The receipt's job is to establish that
// the operator's SPEECH reached a live conductor and the conductor REPLIED — not to grade the model's
// mental arithmetic, which is neither the system under test nor something this build can fix. Conflating
// the two makes the gate flaky on a live model, which is how a green criterion turns into a coin flip.
// Falsifiability is preserved by the two properties that matter: the number must appear AFTER the whole
// echoed utterance, and the utterance itself contains no such number — so an echo cannot produce one.

test("a number after the anchor is reported even when the arithmetic is wrong", () => {
  const pane = "❯ What is 37 plus 47? Answer with only the sum and nothing else.\n● 67\n✻ Sautéed for 3s";
  const r = answerAfterAnchor(pane, "What is 37 plus 47? Answer with only the sum and nothing else.", 84);
  assert.strictEqual(r.anchored, true);
  assert.strictEqual(r.replied, true, "the conductor did reply");
  assert.strictEqual(r.number, 67);
  assert.strictEqual(r.correct, false);
  assert.strictEqual(r.seen, false, "`seen` stays reserved for the arithmetic being right");
});

test("the correct answer is reported as correct", () => {
  const pane = "❯ What is 37 plus 32? Answer with only the sum.\n● 69\n✻ Crunched for 2s";
  const r = answerAfterAnchor(pane, "What is 37 plus 32? Answer with only the sum.", 69);
  assert.strictEqual(r.replied, true);
  assert.strictEqual(r.correct, true);
  assert.strictEqual(r.seen, true);
  assert.strictEqual(r.number, 69);
});

test("the CLI's own chrome is not a reply", () => {
  for (const tail of ["✻ Crunched for 2s", "(160 tokens · esc to interrupt)", "42%", "83/100",
    "⏸ manual mode on · ? for shortcuts", "──────────"]) {
    const pane = `❯ say something\n${tail}`;
    const r = answerAfterAnchor(pane, "say something", 84);
    assert.strictEqual(r.anchored, true, tail);
    assert.strictEqual(r.replied, false, `chrome must not count as a reply: ${tail}`);
  }
});

test("CLI chrome AFTER the anchor is still not a reply, even when it carries a fresh number", () => {
  const anchor = "What is 37 plus 32? Answer with only the sum.";
  for (const tail of ["⎿ Read 69 lines", "69 files changed", "↑69 ↓12", "Page 69 of 100"]) {
    const r = answerAfterAnchor(`❯ ${anchor}\n${tail}`, anchor, 69);
    assert.strictEqual(r.anchored, true, tail);
    assert.strictEqual(r.replied, false, `chrome must not become a model reply: ${tail}`);
  }
});

test("when the model restates the question, the LAST standalone number is taken as its answer", () => {
  const pane = "❯ What is 37 plus 47?\n● 37 + 47 = 84";
  const r = answerAfterAnchor(pane, "What is 37 plus 47?", 84);
  assert.strictEqual(r.correct, true);
  assert.strictEqual(r.number, 84);
});
