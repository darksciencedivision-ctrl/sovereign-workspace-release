"use strict";
/**
 * Phase 17C `.close-revalidate` — is the conductor pane in a state that ACCEPTS TYPED TEXT?
 *
 * WHY THIS EXISTS. `.close` gated the SUBMIT KEY on an observed echo and argued that this made a
 * spoken utterance safe by construction. Both mandatory reviews of that tree found the same hole,
 * independently, and it is the one invariant 25 is about: **the gate protected the `\r` and left the
 * BODY unguarded.** The body — the operator's sentence — was written into whatever the live `claude`
 * pane happened to be showing. That CLI gates its own tool use with a numbered selection list:
 *
 *     Do you want to proceed?
 *     > 1. Yes
 *       2. Yes, and don't ask again
 *       3. No
 *
 * Digits are the affordance there, not text. The very utterance `.close`'s own receipt used — "What is
 * 31 plus 32? Answer with only the sum" — carries `3`, `1`, `3`, `2`. Typing it into an open permission
 * prompt mutates a protected-action dialog with characters the operator never aimed at it. That is
 * authority expansion by voice, whether or not the final `\r` is withheld.
 *
 * THE RULE, and it is fail-closed. Nothing is written unless this shell can point at POSITIVE evidence,
 * in the pane's OWN emitted bytes, that the pane is showing its text input. Absence of evidence is a
 * refusal, not a permission — an unknown state, an unrecognised vendor chrome, a pane that has emitted
 * nothing yet, all refuse. The operator sees the refusal and why (invariant 27); nothing is fabricated,
 * nothing is delivered.
 *
 * ORDER, not proximity. The evidence is read from the bounded ConPTY ring in order and the LAST marker
 * wins. A known permission prompt after the input box refuses; known input chrome after the dismissed
 * prompt re-opens. Unknown non-empty lines after the latest input marker also refuse, so an old marker
 * never grants permission to a new vendor modal.
 *
 * WHAT IT DOES NOT ESTABLISH, stated plainly. This is a reading of a vendor TUI's chrome, not a
 * protocol. A prompt shape this file does not know is refused when it adds later output, but a future
 * modal that exactly impersonates the known input footer remains indistinguishable. The checkpoint
 * records that vendor-shape limit; it does not call a not-yet-created issue registered. Refusals are
 * common and cheap, and every accepted marker below came from bytes this host's `claude` emitted.
 *
 * Pure and deterministic: no Electron, no I/O. The caller owns the buffer read.
 */

//: ANSI/OSC/CSI sequences a full-screen TUI repaint is made of. Stripped so the markers are matched
//: against what the pane DISPLAYS, not against cursor arithmetic. Built from escaped source rather
//: than written as literals: raw control bytes in a source file are invisible to review.
const ANSI_RE = new RegExp(
  "\\x1b\\][^\\x07\\x1b]*(?:\\x07|\\x1b\\\\)"     // OSC ... BEL | ST
    + "|\\x1b\\[[0-?]*[ -/]*[@-~]"                // CSI
    + "|\\x1b[@-Z\\\\-_]",                        // two-character escapes
  "g");
//: Remaining C0/C1 control bytes — turned into spaces, so a marker split across a repaint's control
//: codes still reads as words.
const CONTROL_RE = new RegExp("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]", "g");

/** The pane's emitted bytes as displayable text: escapes gone, runs of whitespace collapsed. */
function visibleText(emitted) {
  const s = Buffer.isBuffer(emitted) ? emitted.toString("utf8") : String(emitted == null ? "" : emitted);
  return s.replace(ANSI_RE, " ").replace(CONTROL_RE, " ").replace(/[ \t]+/g, " ");
}

//: The selection/confirmation and authority-expanding-mode patterns now live in
//: `control/modal-affordance.js`, because the SYSTEM→PANE write gate needs exactly the same ones
//: (U363, unit 19.4-followon): until that unit the operator's own voice was gated more strictly than
//: an automated write into the same pane. The lists are UNCHANGED — they moved, they were not
//: rewritten — and this file's rule around them is unchanged with them. `pane-state.test.js` is what
//: holds that: it drives every branch below through `paneAcceptsTypedText`, not through the arrays.
const {
  PROMPT_MARKERS, UNSAFE_MODE_MARKERS, lastMatchOfAny,
} = require("../control/modal-affordance");

//: The pane is showing its TEXT INPUT. Every one of these was observed in this host's live `claude`
//: pane (see the `.close` receipt's rendered excerpt): the footer hint line and the mode indicators
//: are drawn WITH the input box and repaint with it.
const INPUT_MARKERS = [
  /\bplan mode on\b/i,
  /\bmanual mode on\b/i,
];

//: STATUS NOTICES the vendor paints alongside the input box. They carry no affordance — nothing is
//: chosen by typing into them — but they ARE text after the input marker, and the fail-closed rule
//: below counted them as an unknown new state: on 2026-07-30 a live delivery was refused with
//: "unrecognized pane chrome" because the pane had added "You've used 90% of your session limit"
//: (U165). An operator whose voice input silently dies for the rest of a usage window, blaming
//: chrome, is a worse failure than the one the rule guards against — and the guard is not weakened,
//: because only THIS exact shape is removed before the remaining text is judged as before. A line
//: that also carries a confirmation affordance still matches PROMPT_MARKERS and still refuses.
const STATUS_NOTICES = [
  /\byou'?ve used \d{1,3}% of your (?:session|weekly|5-hour|hourly) limit\b(?:[^\n]*?\bresets?\b[^\n]*)?/ig,
  /\b(?:session|weekly) limit resets? (?:in )?[^\n]{0,30}/ig,
];

/** `text` with known non-affordance status notices removed, so the state rule judges the rest. */
function withoutStatusNotices(text) {
  let out = String(text || "");
  for (const re of STATUS_NOTICES) out = out.replace(new RegExp(re.source, re.flags), " ");
  return out;
}

/** The LAST match of any pattern in `text` (null = never seen). Shared with the write gate for the
 *  same reason the patterns are: two copies of one rule drift, and the copy nobody is looking at is
 *  the one that gets it wrong. The implementation moved verbatim. */
const _lastMatchOfAny = lastMatchOfAny;

/** A short, human-readable slice around `at` — for the refusal reason and the receipt, never for logic. */
function _excerpt(text, at, span = 90) {
  const from = Math.max(0, Math.min(at, text.length) - Math.floor(span / 3));
  return text.slice(from, from + span).trim();
}

/**
 * May this shell type the operator's utterance into this pane?
 *
 * @param {string|Buffer} emitted everything the pane's ConPTY has emitted (main reads the ring buffer)
 * @returns {{accepting:boolean, state:("input"|"prompt"|"unknown"), reason:string, evidence:(string|null)}}
 *   `state:"prompt"` — a confirmation/selection dialog is the most recent thing drawn: REFUSE.
 *   `state:"unknown"` — no chrome this shell recognises: REFUSE (fail closed; absence is not consent).
 *   `state:"input"` — the pane's text input is the most recent thing drawn: the body may be written.
 */
function paneAcceptsTypedText(emitted, { supervisorBoundary = false } = {}) {
  const text = visibleText(emitted);
  if (!text.trim()) {
    return { accepting: false, state: "unknown", evidence: null,
             reason: "the pane has emitted nothing this shell can read — no evidence it accepts typed text" };
  }
  const unsafeMode = _lastMatchOfAny(text, UNSAFE_MODE_MARKERS);
  const prompt = _lastMatchOfAny(text, PROMPT_MARKERS);
  const input = _lastMatchOfAny(text, INPUT_MARKERS);
  if (input && /\bmanual mode on\b/i.test(input.text) && !supervisorBoundary) {
    return { accepting: false, state: "unknown", evidence: _excerpt(text, input.index),
             reason: "manual-mode input is accepted only behind the supervisor-owned voice-turn "
               + "boundary; vendor chrome alone is not authority" };
  }
  if (unsafeMode && (!input || unsafeMode.index > input.index)) {
    return { accepting: false, state: "prompt", evidence: _excerpt(text, unsafeMode.index),
             reason: "the conductor is in an authority-expanding interaction mode — direct voice "
               + "delivery is disabled (invariant 25)" };
  }
  if (prompt && (!input || prompt.index > input.index)) {
    return { accepting: false, state: "prompt", evidence: _excerpt(text, prompt.index),
             reason: "the pane is showing a confirmation prompt — typed characters would be answering it, "
               + "so nothing was written (invariant 25: voice proposes, it never confirms)" };
  }
  if (!input) {
    return { accepting: false, state: "unknown", evidence: _excerpt(text, text.length - 1),
             reason: "the pane shows no input-box chrome this shell recognises — refused rather than "
               + "typing into an unknown state (fail closed)" };
  }
  const afterInput = withoutStatusNotices(text.slice(input.end));
  const [sameLine = "", ...laterLines] = afterInput.split(/\r?\n/);
  // Exact, observed footer hints may follow the mode marker; anything else is a new state.
  if (!/^\s*(?:[·|]\s*\?\s*for shortcuts)?(?:\s*[·|]\s*←\s*for agents)?(?:\s*●\s*(?:low|medium|high)\s*[·|]\s*\/effort)?\s*$/i.test(sameLine)) {
    return { accepting: false, state: "unknown", evidence: _excerpt(text, input.end),
             reason: "unrecognized pane chrome follows the input marker on the same line — refused "
               + "rather than treating historical input chrome as consent (fail closed)" };
  }
  if (laterLines.some((line) => line.trim())) {
    return { accepting: false, state: "unknown", evidence: _excerpt(text, input.end),
             reason: "unrecognized pane output appeared after the last input marker — historical "
               + "input chrome is not consent to type into the current state (fail closed)" };
  }
  return { accepting: true, state: "input", evidence: _excerpt(text, input.index),
           reason: "the pane's text input is the most recent chrome it drew" };
}

module.exports = { paneAcceptsTypedText, visibleText, PROMPT_MARKERS, INPUT_MARKERS };
