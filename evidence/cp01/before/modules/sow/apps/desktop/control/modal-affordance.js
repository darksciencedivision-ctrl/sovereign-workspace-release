"use strict";
/**
 * IS THE PANE SHOWING SOMETHING A KEYSTROKE WOULD ANSWER? (U363, Phase 19 unit 19.4-followon.)
 *
 * WHY THIS FILE EXISTS AT ALL. The patterns below are not new. They have gated the OPERATOR's voice
 * since Phase 17C, in `voice/pane-state.js`, and they moved here unchanged. Be exact about their
 * provenance, because the file they came from is: `pane-state.js` claims observation for its ACCEPTED
 * (input-chrome) markers only, and these are its REFUSAL markers — shapes it declined to over-claim.
 * Some are drawn from this host's live provider panes (the numbered "Do you want to proceed?"
 * selection, the "press enter to continue" overlay, the two mode banners); others (`[y/N]`, "do you
 * want to create/run", "press enter to accept") are the same family written out, and no receipt in
 * `docs/evidence/` evidences those three on a live pane.
 *
 * Meanwhile the SYSTEM→PANE gate (`control/pane-writer.js`) knew only six provider-STATE phrases, so
 * the 19.3 gate-validator walked nine of ten realistic permission screens straight through it. The
 * operator's voice was gated more strictly than an automated write into the same pane. This module is
 * the shared definition that ends that asymmetry: one list, two callers, and moving it here changes
 * nothing about what the voice path does with it. The round-2 gate-validator re-established that
 * independently — 1,620,000 generated screens through the old and new `paneAcceptsTypedText`, 0
 * behavioural differences. One byte-level non-identity, recorded rather than glossed: the two arrays
 * are `Object.freeze`d here and were not there ([[U404]]).
 *
 * WHAT A MATCH MEANS, precisely. A match is evidence that typed characters would be CHOOSING
 * something — it is not a provider state, not an error, and not a claim about what the provider
 * needs. `pane-writer.js` turns it into "not yet"; `worker-readiness.js` never turns it into a
 * worker's condition (U373). Callers pass the pane's CURRENT screen, bounded — on a whole-buffer
 * read these patterns would pin a pane the moment a model quoted one of them (which is exactly why
 * 19.3 declined to add them, and why the bounded window had to come first).
 *
 * WHAT IT IS NOT. A denylist, still: an unrecognised vendor modal is not matched and is written
 * into. `paneAcceptsTypedText` in `voice/pane-state.js` is the stronger, positive-evidence shape,
 * and it can be that strict because it only ever addresses the conductor pane, whose input chrome
 * this shell has actually observed. Pure and deterministic: no I/O, no Electron.
 */

//: A SELECTION/CONFIRMATION prompt is open — typed characters are choices, not text. Deliberately
//: specific: a bare "1." would fire on any numbered list a model prints in an ordinary answer, and a
//: gate that refuses everything teaches its operator to ignore it.
const PROMPT_MARKERS = Object.freeze([
  /do you want to (proceed|make this edit|create|run|continue)/i,
  /yes,? and don'?t ask again/i,
  /[❯>]\s*[1-9]\.\s*(yes|no)\b/i,
  /\b[1-9]\.\s*yes\b[\s\S]{0,80}?\b[1-9]\.\s*no\b/i,
  /\(y\/n\)/i,
  /\[y\/n\]/i,
  /press\s+(?:enter|return)\s+to\s+(?:confirm|continue|accept)/i,
]);

//: The vendor has been put into a mode where it stops asking. Not a prompt — the ABSENCE of one —
//: and D-P18-13/U317 is the ruling that a provider's own accept-mode is not operator approval, so a
//: pane in one is a pane this shell does not type into either.
const UNSAFE_MODE_MARKERS = Object.freeze([
  /\bbypass permissions on\b/i,
  /\baccept edits on\b/i,
]);

/** The LAST match of any pattern in `text`, or null. ORDER, not proximity: a caller comparing this
 *  against input chrome needs to know which was drawn most recently, so the scan is exhaustive
 *  rather than first-hit. */
function lastMatchOfAny(text, patterns) {
  let last = null;
  for (const re of patterns) {
    const g = new RegExp(re.source, re.flags.includes("g") ? re.flags : `${re.flags}g`);
    for (let m = g.exec(text); m; m = g.exec(text)) {
      if (!last || m.index > last.index) {
        last = { index: m.index, end: m.index + m[0].length, text: m[0] };
      }
      if (g.lastIndex === m.index) g.lastIndex += 1;   // zero-width guard
    }
  }
  return last;
}

/**
 * The affordance on this screen, or null. `{ kind: "prompt" | "unsafe_mode", text, index }` — the
 * matched text is carried so a refusal can say what it saw (invariant 27: a guard that refuses
 * without naming its reason is a guard the operator cannot check).
 */
function modalAffordance(screen) {
  const text = String(screen == null ? "" : screen);
  if (!text.trim()) return null;         // an empty screen shows no affordance; see the header
  const unsafe = lastMatchOfAny(text, UNSAFE_MODE_MARKERS);
  const prompt = lastMatchOfAny(text, PROMPT_MARKERS);
  const winner = !unsafe ? prompt : (!prompt || unsafe.index > prompt.index ? unsafe : prompt);
  if (!winner) return null;
  return {
    kind: winner === unsafe ? "unsafe_mode" : "prompt",
    // ONE LINE, ALWAYS. This excerpt is PROVIDER-CONTROLLED text and it travels: into the refusal's
    // `reason`, into the shell log, into the conductor's operator-visible chrome, into structured
    // failures. The two-line numbered-menu pattern matches ACROSS a newline, so an unsanitised
    // excerpt lets a model's own output forge a second log line (the round-1 spec-auditor of
    // 19.4-followon). Collapsing whitespace costs nothing a reader needs — invariant 27 asks that
    // the reason be legible, not that it be verbatim.
    text: winner.text.replace(/\s+/g, " ").trim().slice(0, 120),
    index: winner.index,
  };
}

module.exports = { PROMPT_MARKERS, UNSAFE_MODE_MARKERS, lastMatchOfAny, modalAffordance };
