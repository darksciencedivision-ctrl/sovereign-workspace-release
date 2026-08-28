"use strict";
/**
 * Phase 17A `.roundtrip` — the probe that makes a type→answer receipt falsifiable.
 *
 * A terminal echoes. A model answers. A receipt that cannot tell those apart proves nothing, so the
 * probe is built so its answer CANNOT appear in the pane unless something computed it:
 *
 *   • the operands are SPELLED IN WORDS — the prompt contains no digit at all, so the answer's digits
 *     cannot arrive as an echo of the keystrokes;
 *   • the answer is drawn fresh per run, so no canned reply and no earlier scrollback can satisfy it;
 *   • the caller additionally asserts the token is ABSENT from the pane before submitting (a banner
 *     that happens to contain the number re-rolls the draw rather than passing for free).
 *
 * Everything here is pure and deterministic under an injected `randInt` — the in-Electron self-check
 * owns the I/O, the tests own this.
 */

const UNITS = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
const TENS = { 2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety" };

/** 21..99 in words. Throws outside that band rather than falling back to digits (fail closed). */
function spellNumber(n) {
  if (!Number.isInteger(n) || n < 21 || n > 99) {
    throw new RangeError(`spellNumber: ${n} is outside the digit-free band 21..99`);
  }
  const tens = TENS[Math.floor(n / 10)];
  const unit = UNITS[n % 10];
  return unit ? `${tens}-${unit}` : tens;
}

function defaultRandInt(min, max) {
  return min + Math.floor(Math.random() * (max - min + 1));
}

/**
 * Build one round-trip probe. `fixed` is for tests only — production always draws.
 * @returns {{a:number,b:number,prompt:string,expectedNumber:string,expectedToken:string,echoKey:string}}
 */
function buildRoundTripProbe(randInt = defaultRandInt, fixed = null) {
  const a = fixed ? fixed.a : randInt(21, 99);
  const b = fixed ? fixed.b : randInt(21, 99);
  const question = `What is ${spellNumber(a)} plus ${spellNumber(b)}?`;
  return {
    a, b,
    // Short by design: one prompt, one answer, minimal tokens (§16 live-budget discipline).
    prompt: `Answer with only SUM=<number> and nothing else. ${question}`,
    expectedNumber: String(a + b),
    expectedToken: `SUM=${a + b}`,
    echoKey: question,
  };
}

/** Whitespace- and case-insensitive view of rendered text: xterm wrapping cannot hide a token. */
function squash(text) {
  return String(text == null ? "" : text).replace(/\s+/g, "").toLowerCase();
}

function containsAcrossWrap(text, needle) {
  const n = squash(needle);
  return n.length > 0 && squash(text).includes(n);
}

/** The probe must not carry its own answer — asserted per draw, never assumed. */
function probeIsFalsifiable(probe) {
  return !containsAcrossWrap(probe.prompt, probe.expectedToken)
    && !/\d/.test(probe.prompt)
    && !hasStandaloneNumber(probe.prompt, probe.expectedNumber);
}

/**
 * The bare number as its own token in the RAW text (not the squashed view): `83` must not match
 * `v2.1.831`, `183`, `838` or `0.83`. Squashing is right for the prefixed form (`SUM=` anchors it)
 * and wrong for a bare two/three-digit number, which needs its boundaries intact.
 *
 * The live CLI's own chrome ALSO prints bare numbers — "(160 tokens · esc to interrupt)", "Baked for
 * 83s", "42%", "83/100", "83 seconds". A draw that collided with one of those would credit the model
 * for the terminal's spinner, so a number carrying a unit is not an answer, and a number that is
 * part of a larger figure ("1,135", "12:83") is not standalone. These are NARROW exclusions: a
 * genuine bare reply like "row 83 of 90" still counts.
 */
const _UNIT_SUFFIX = "(?!\\s*(?:tokens?|sec(?:ond)?s?\\b|s\\b|ms\\b|min\\b|%|/|:))";
const _NOT_PART_OF_A_FIGURE = "(?<![\\d.,:])";

function hasStandaloneNumber(text, number) {
  const re = new RegExp(`${_NOT_PART_OF_A_FIGURE}${number}(?![\\d.,])${_UNIT_SUFFIX}`);
  return re.test(String(text == null ? "" : text));
}

/**
 * Did the pane show the model's ANSWER (as opposed to the echo of the question)?
 * @returns {{seen:boolean, form:"prefixed"|"bare"|null}}
 */
function answerObserved(text, probe) {
  if (containsAcrossWrap(text, probe.expectedToken)) return { seen: true, form: "prefixed" };
  if (hasStandaloneNumber(text, probe.expectedNumber)) return { seen: true, form: "bare" };
  return { seen: false, form: null };
}

/** Did the keystrokes reach the session's input at all? Keyed on the arithmetic, not boilerplate. */
function promptEchoed(text, probe) {
  return containsAcrossWrap(text, probe.echoKey);
}

module.exports = {
  spellNumber, buildRoundTripProbe, squash, containsAcrossWrap,
  probeIsFalsifiable, answerObserved, promptEchoed, hasStandaloneNumber,
};
