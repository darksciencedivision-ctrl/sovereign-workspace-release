"use strict";
/**
 * Phase 17C `.close` — the probe that makes a SPOKEN round trip falsifiable.
 *
 * Directive §16 track 17C requires the operator's speech to reach *"the LIVE 17A conductor session"*.
 * `.mic` delivered a real transcript into a `powershell.exe` stand-in pane and said so; this module
 * exists for the leg that closes the gap: speak → real Parakeet → the bridge → the live `claude`
 * session in pane 1 → **an answer from the model**.
 *
 * The 17A typed probe (conductor/roundtrip-probe.js) could spell its operands in words and then assert
 * the prompt contained no digit at all, so the answer's digits could not arrive as an echo. Speech
 * cannot borrow that trick: the words are spoken, and the ASR renders them however it likes
 * ("twenty-three" → "23" | "Twenty three" | "twenty-three"). Two consequences shape this module:
 *
 *   1. **The expectation is derived from the TRANSCRIPT**, not from what the fixture said — from the
 *      question the conductor was actually asked. A misheard operand then produces a different but
 *      still-correct expectation instead of a false failure, and the caller records both numbers so the
 *      divergence is visible. (What a misheard operand must NEVER do is quietly relax the check, which
 *      is why `parseHeardArithmetic` fails closed on anything it cannot read exactly.)
 *   2. **Falsifiability moves to two assertions the caller makes**: the answer is absent from the
 *      transcript (so an echo of the delivered text cannot satisfy it) and absent from the pane before
 *      delivery (so stale scrollback and the CLI's own chrome cannot either).
 *
 * Pure and deterministic under an injected `randInt` — the in-Electron receipt owns the I/O.
 */
const { spellNumber, containsAcrossWrap } = require("../conductor/roundtrip-probe");

/**
 * The operand draw band. Both ends matter:
 *   • ≥21 keeps each operand a TWO-word spoken form ("twenty-three"), which the synthesizer articulates
 *     clearly and which cannot be confused with the ordinary counting words that litter CLI chrome;
 *   • ≤49 keeps the SUM ≤ 98, i.e. inside `spellNumber`'s band too — so the answer's WORD form can be
 *     excluded from the phrase and from the transcript, not just its digits.
 * 29 × 29 draws is ample freshness for a once-per-run probe.
 */
const SPOKEN_BAND = { min: 21, max: 49 };

const UNITS = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9,
};
const TEENS = {
  ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16,
  seventeen: 17, eighteen: 18, nineteen: 19,
};
const TENS = {
  twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90,
};

const UNIT_WORDS = Object.keys(UNITS).join("|");
const TEEN_WORDS = Object.keys(TEENS).join("|");
const TENS_WORDS = Object.keys(TENS).join("|");
//: Alternation order is load-bearing: the tens+unit form must be tried BEFORE the bare tens form, or
//: "forty five" matches as 40 and leaves "five" dangling.
const NUM = `(?:\\d{1,3}|(?:${TENS_WORDS})(?:[ -](?:${UNIT_WORDS}))?|(?:${TEEN_WORDS})|(?:${UNIT_WORDS}))`;
//: Only an explicit addition operator. "and" renders lists as often as sums in speech, and guessing
//: would silently change the expected answer — the one error that could make a green receipt a lie.
const HEARD_RE = new RegExp(`(${NUM})\\s*(?:plus|\\+)\\s*(${NUM})`, "i");

function defaultRandInt(min, max) {
  return min + Math.floor(Math.random() * (max - min + 1));
}

/** A spoken/written number token (digits or 0–99 in words) → an integer, or null if unreadable. */
function readNumberToken(token) {
  const t = String(token == null ? "" : token).trim().toLowerCase();
  if (/^\d{1,3}$/.test(t)) return Number(t);
  const words = t.split(/[ -]+/).filter(Boolean);
  if (words.length === 1) {
    const w = words[0];
    if (w in UNITS) return UNITS[w];
    if (w in TEENS) return TEENS[w];
    if (w in TENS) return TENS[w];
    return null;
  }
  if (words.length === 2 && words[0] in TENS && words[1] in UNITS && UNITS[words[1]] !== 0) {
    return TENS[words[0]] + UNITS[words[1]];
  }
  return null;
}

/**
 * Draw one spoken probe.
 * @returns {{a:number,b:number,phrase:string,expectedNumber:string}} `phrase` is what gets SPOKEN.
 */
function buildSpokenProbe(randInt = defaultRandInt) {
  const a = randInt(SPOKEN_BAND.min, SPOKEN_BAND.max);
  const b = randInt(SPOKEN_BAND.min, SPOKEN_BAND.max);
  return {
    a,
    b,
    // The one minimal live exchange also challenges the supervisor-owned non-executing boundary:
    // request a harmless tool calculation. The launch-bound hook must deny the tool before execution;
    // the model may still answer from reasoning. No protected/destructive verb is present, so the
    // deterministic voice broker correctly treats this as ordinary CHAT.
    phrase: `Use a tool to calculate ${spellNumber(a)} plus ${spellNumber(b)}. `
      + "Answer with only the sum and nothing else.",
    expectedNumber: String(a + b),
  };
}

/**
 * Draw one TYPED probe (Phase 17C `.disarm`, U166) — the second prompt of a run, typed by the
 * operator after their keystroke ended the voice turn.
 *
 * Same band and same falsifiability as the spoken draw, with ONE deliberate difference: it does not
 * ask for a tool. The spoken phrase does, because a voice turn is exactly where a tool request must be
 * DENIED. By the time this one is typed the restriction is gone and tool use is ordinary — so asking
 * for one would have the CLI paint tool chrome, full of fresh standalone numbers, between the prompt
 * and the reply. Measured on this host: the first `.disarm` run's typed leg read `10` where `70` was
 * expected, with no way to tell a wrong answer from chrome. The question is whether the typed prompt
 * was ACCEPTED AND ANSWERED; nothing about it needs a tool.
 */
function buildTypedProbe(randInt = defaultRandInt) {
  const a = randInt(SPOKEN_BAND.min, SPOKEN_BAND.max);
  const b = randInt(SPOKEN_BAND.min, SPOKEN_BAND.max);
  return {
    a,
    b,
    phrase: `What is ${spellNumber(a)} plus ${spellNumber(b)}? Answer with only the sum and nothing else.`,
    expectedNumber: String(a + b),
  };
}

/**
 * Read the arithmetic the conductor was ACTUALLY asked out of the ASR transcript.
 * @returns {{a:number,b:number,expectedNumber:string,matched:string}|null} null when the transcript
 *   cannot be read exactly — fail closed, so the caller records the transcript verbatim and FAILS
 *   rather than inventing an expectation the conductor was never asked for.
 */
function parseHeardArithmetic(transcript) {
  const m = HEARD_RE.exec(String(transcript == null ? "" : transcript));
  if (!m) return null;
  const a = readNumberToken(m[1]);
  const b = readNumberToken(m[2]);
  if (a === null || b === null) return null;
  return { a, b, expectedNumber: String(a + b), matched: m[0] };
}

/**
 * The bare number as its own token, with the SAME narrow exclusions 17A established — the live CLI's
 * own chrome prints bare numbers constantly ("168 tokens", "68s", "42%", "83/100", "v2.1.681"), and
 * crediting the model for the terminal's spinner would make the receipt worthless.
 *
 * ONE deliberate divergence from `roundtrip-probe.hasStandaloneNumber`, and the tests pin it: that
 * matcher disqualifies a trailing `.` or `,` unconditionally, so it cannot see the answer in "The sum
 * is 68." — the most ordinary way a conversational model ends a sentence. Here a separator only
 * disqualifies when a DIGIT follows it, which is the case the exclusion was actually written for
 * ("0.68", "1,168"). 17A's stricter form can only ever make a receipt fail (fail-closed, and its own
 * probe demands a `SUM=` prefix), so it is left as gated.
 */
//: `/` is in here as well as in the suffix list: "83/100" must yield NEITHER number — the CLI prints
//: ratios, and the second half of one is no more a reply than the first.
const _NOT_PART_OF_A_FIGURE = "(?<![\\d.,:/])";
const _NOT_CONTINUED = "(?![\\d])(?![.,]\\d)";
const _NO_UNIT_SUFFIX = "(?!\\s*(?:tokens?|sec(?:ond)?s?\\b|s\\b|ms\\b|min\\b|%|/|:))";

function carriesDigits(text, n) {
  const re = new RegExp(`${_NOT_PART_OF_A_FIGURE}${n}${_NOT_CONTINUED}${_NO_UNIT_SUFFIX}`);
  return re.test(String(text == null ? "" : text));
}

/**
 * Does `text` carry `n` as an ANSWER — in digits or in words?
 * The word half exists because a spoken question can be answered in words, and because the phrase must
 * be checked for leaking its own answer in either form.
 */
function carriesNumber(text, n) {
  if (carriesDigits(text, String(n))) return true;
  // Outside 21..99 there is no single hyphenated word form to look for — skip rather than throw.
  if (!Number.isInteger(n) || n < 21 || n > 99) return false;
  const word = spellNumber(n);                       // "sixty-eight"
  if (containsAcrossWrap(text, word)) return true;    // hyphen present, wrapping tolerated
  return containsAcrossWrap(text, word.replace("-", " ")) && /[a-z]/i.test(String(text));
}

/** Alphanumerics only, lowercased: ANSI escapes, box borders, wrapping and punctuation all vanish. */
function alnumView(text) {
  return String(text == null ? "" : text).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

//: A standalone 2–3 digit number in rendered pane text, with the same narrow exclusions `carriesDigits`
//: uses: the live CLI's chrome prints numbers constantly ("2s", "160 tokens", "42%", "83/100") and none
//: of those is a reply.
const STANDALONE_NUMBER_RE = new RegExp(
  `${_NOT_PART_OF_A_FIGURE}(\\d{2,3})${_NOT_CONTINUED}${_NO_UNIT_SUFFIX}`, "g");

/** Every standalone number in `text`, in order of appearance. */
function standaloneNumbers(text) {
  const out = [];
  const s = String(text == null ? "" : text);
  STANDALONE_NUMBER_RE.lastIndex = 0;
  for (let m = STANDALONE_NUMBER_RE.exec(s); m; m = STANDALONE_NUMBER_RE.exec(s)) out.push(Number(m[1]));
  return out;
}

/**
 * Did the answer `n` appear in `text` AFTER the last occurrence of `anchor`?
 *
 * Two defects make this the right question rather than "does the pane contain `n`" (both found by the
 * mandatory reviews of this unit's first draft):
 *   • the live CLI's own chrome prints bare numbers in shapes the unit-suffix exclusions do not cover
 *     ("⎿ Read 69 lines", "↑69 ↓12", "69 files changed"), and the pre-delivery absence snapshot is
 *     tens of seconds stale by the time the transcript is delivered, so anything painted in that window
 *     is unguarded. A model's reply is necessarily AFTER its own prompt; chrome above it is not a reply.
 *   • the anchor is the WHOLE utterance, so it doubles as proof the whole utterance arrived. Anchoring
 *     on the arithmetic fragment alone (which sits at the front of the phrase) would let a delivery
 *     truncated after that fragment pass with a correct-looking answer.
 *
 * The ANCHOR is compared on alphanumerics so a wrapped input box, box borders and escape sequences
 * cannot hide the utterance — and cannot fabricate it either, since the letters must appear in order.
 * The REPLY is read from the whitespace-collapsed text after that anchor, because a bare number needs
 * its boundaries intact to be told apart from the CLI's chrome.
 *
 * `replied` vs `correct` vs `seen`, and why they are three things (MEASURED, not hypothetical): asked
 * "What is 37 plus 47? Answer with only the sum and nothing else.", the live Fable-5 conductor replied
 * "● 67". It read the utterance, it answered, and its arithmetic was wrong. What this receipt exists to
 * establish is that the operator's speech reached a live conductor which replied; grading the model's
 * mental arithmetic is neither the system under test nor something this build can fix, and gating on it
 * would make a criterion a coin flip. So `replied` is the fact (a standalone number of the conductor's
 * own appeared after the echoed utterance), `number` is what it said, `correct` is whether the
 * arithmetic was right, and `seen` remains the conjunction for callers that want it.
 *
 * `.close-revalidate` — THE OPERANDS ARE NOT A REPLY. The first draft justified `replied` with "an echo
 * cannot produce a number, because the utterance contains no such number". True of the SUM and false of
 * the utterance, which says "What is 31 plus 32?" — 31 and 32 are standalone 2-digit numbers in the
 * probe's own band, so a pane that merely repainted the question after the anchor (a wrap, a scroll, a
 * `/status` line) satisfied the one leg this whole track is named for. Every number the UTTERANCE
 * itself carries is now excluded from `replied`; only a number the conductor produced counts. The sum
 * is never excluded — `spokenProbeIsFalsifiable` asserts per draw that the phrase does not contain it.
 *
 * @param {string} text the rendered pane text
 * @param {string} anchor the whole utterance (also the source of the excluded numbers)
 * @param {number} n the expected sum
 * @returns {{anchored:boolean, replied:boolean, number:(number|null), correct:boolean, seen:boolean,
 *            excluded:number[]}}
 *   `anchored` false ⇒ the full utterance never echoed, and nothing else is meaningful.
 */
function answerAfterAnchor(text, anchor, n) {
  const none = { anchored: false, replied: false, number: null, correct: false, seen: false, excluded: [] };
  const hay = alnumView(text);
  const needle = alnumView(anchor);
  if (!needle) return none;
  const at = hay.lastIndexOf(needle);
  if (at < 0) return none;
  // The alnum view located the anchor; the reply is read from the SAME region of the collapsed text,
  // found by anchoring on the utterance's own tail (its last alnum run survives any repaint).
  const collapsed = String(text == null ? "" : text).replace(/\s+/g, " ");
  const anchorTail = String(anchor).replace(/\s+/g, " ").trim();
  let region = collapsed;
  const rawAt = collapsed.lastIndexOf(anchorTail);
  if (rawAt >= 0) region = collapsed.slice(rawAt + anchorTail.length);
  else {
    // The rendered text wrapped mid-utterance, so the verbatim anchor is not in the collapsed view.
    // Fall back to its last few words, which is enough to place the reply after it.
    const words = anchorTail.split(" ").filter(Boolean);
    for (let take = Math.min(4, words.length); take >= 1; take -= 1) {
      const probe = words.slice(-take).join(" ");
      const p = collapsed.lastIndexOf(probe);
      if (p >= 0) { region = collapsed.slice(p + probe.length); break; }
    }
  }
  // Numbers the utterance itself carries (its operands) are the question, not an answer — a repaint of
  // the question after the anchor must never read as the conductor replying. The expected sum is never
  // excluded: the probe is asserted not to contain it.
  const excluded = standaloneNumbers(String(anchor == null ? "" : anchor)).filter((x) => x !== n);
  // A Claude model reply is painted with its own `●` prefix. Tool/status chrome after the prompt can
  // carry fresh numbers too ("Read 69 lines", "69 files changed"); without this channel marker those
  // shapes were indistinguishable from an answer.
  const modelMarker = region.lastIndexOf("●");
  if (modelMarker < 0) {
    return { anchored: true, replied: false, number: null, correct: false, seen: false, excluded };
  }
  const replyRegion = region.slice(modelMarker + 1);
  const numbers = standaloneNumbers(replyRegion).filter((x) => x === n || !excluded.includes(x));
  const wordForm = Number.isInteger(n) && n >= 21 && n <= 99 ? alnumView(spellNumber(n)) : null;
  const spelled = Boolean(wordForm && alnumView(replyRegion).includes(wordForm));
  const correct = numbers.includes(n) || spelled;
  const number = correct ? n : (numbers.length ? numbers[numbers.length - 1] : null);
  const replied = correct || number !== null;
  return { anchored: true, replied, number, correct, seen: correct, excluded };
}

/** The probe must not carry its own answer, in digits or in words. Asserted per draw, never assumed. */
function spokenProbeIsFalsifiable(probe) {
  const n = Number((probe && probe.expectedNumber) || NaN);
  if (!Number.isInteger(n)) return false;
  return !carriesNumber(probe.phrase, n);
}

module.exports = {
  SPOKEN_BAND, buildSpokenProbe, buildTypedProbe, parseHeardArithmetic, carriesNumber, carriesDigits,
  spokenProbeIsFalsifiable, readNumberToken, alnumView, answerAfterAnchor,
};
