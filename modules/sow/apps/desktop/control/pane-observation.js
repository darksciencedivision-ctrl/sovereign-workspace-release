"use strict";
/**
 * What a worker pane is showing, prepared for a CONDUCTOR to read. EPC-03 Layer 4.
 *
 * The operator's framing was that the conductor should see what he sees:
 *
 *     "the conductor is absolutely supposed to be talking to those models and communicating
 *      with them, injecting their prompts, telling them what to do"
 *
 * Talking to them requires reading them, and until now nothing on the conductor's side could.
 * The bounded reader already existed - `createScreenWindow` over `RingBuffer.sliceFrom()` - but
 * its only consumers were a readiness classifier and a write gate, both of which match the text
 * against regexes inside this process and throw it away.
 *
 * THREE THINGS THIS ADDS, AND WHY EACH IS HERE RATHER THAN IN THE READER:
 *
 * 1. REDACTION (L4-2). The window's text has never been redacted, because it never left the
 *    process. A conductor prompt is a different destination: prompts are logged, cached, and
 *    carried into evidence artifacts on disk. `redactPaneText` arrives with the change of
 *    destination rather than after it. It is a net, not a proof, and this module reports what it
 *    removed rather than certifying that nothing remains.
 *
 * 2. A CHARACTER BOUND on top of the reader's byte and line bounds (L4-4). The reader bounds what
 *    a CLASSIFIER needs to see. A conductor's context window is a different and much harder
 *    constraint: four panes of 16 KB tails is 64 KB of text, and an 8B model's usable context is
 *    not that. The authoritative budget is derived from measured hardware on the Python side
 *    (`control_plane.orchestration.pane_observation`); this end takes it as a parameter so there
 *    is exactly one derivation and the shell never carries a second copy of it.
 *
 * 3. AN HONEST SHAPE. The record says whether it is answerable, how much was dropped and why. It
 *    carries NO leg field and no execution claim, by exactly the reasoning `pane_presence`
 *    records: knowing what a pane is SHOWING is not knowing that it DID anything. A worker leg
 *    remains derivable only from evidence, through `_assert_legs_honest`, which is untouched.
 *
 * The window instance is INJECTED rather than constructed here. `main.js` builds one
 * `createScreenWindow` and hands the same object to every consumer; `system-pane-write-wiring`
 * already pins that, because a second window can drift from the first and then two instruments
 * disagree about what a pane showed.
 */
const { redactPaneText } = require("../../../terminal/observe/pane-redaction");

const OBSERVATION_SCHEMA = "pane_observation@1.0";

/** A conservative default for a caller that has not sourced the derived budget. Deliberately
 *  small: under-reading a pane costs the conductor context, over-reading costs it its whole
 *  context window, and only one of those is recoverable within a turn. */
const DEFAULT_MAX_CHARS = 2000;

const UNANSWERABLE = Object.freeze({
  answerable: false, text: "", chars: 0, truncated: false, redactions: 0, kinds: [],
});

/**
 * Observe ONE pane. `window` is the shared `createScreenWindow` object.
 *
 * Returns a `pane_observation@1.0` record. Never throws: this runs on the conductor's path and a
 * pane that cannot be read must produce an honest unanswerable record, not an exception that
 * takes the dispatch with it.
 */
function observePane(window, paneId, { maxChars = DEFAULT_MAX_CHARS, maxLines, notBefore } = {}) {
  const base = { schema: OBSERVATION_SCHEMA, pane_id: String(paneId || "") };
  if (!window || typeof window.read !== "function") {
    return { ...base, ...UNANSWERABLE, reason: "no pane screen window is available" };
  }
  let read = null;
  try {
    const options = {};
    if (Number.isFinite(maxLines)) options.maxLines = maxLines;
    if (Number.isInteger(notBefore)) options.notBefore = notBefore;
    read = window.read(paneId, options);
  } catch (err) {
    return { ...base, ...UNANSWERABLE, reason: `pane screen read failed: ${err && err.message}` };
  }
  if (!read || read.answerable !== true) {
    return {
      ...base, ...UNANSWERABLE,
      reason: (read && read.reason) || "the pane screen window is not answerable",
    };
  }

  const redacted = redactPaneText(read.text);
  // Bound AFTER redacting, never before. Truncating first could split a secret across the
  // boundary and leave the surviving half unmatched by every rule - the classic way a redactor
  // is defeated by a length limit nobody thought of as part of the security path.
  const limit = Number.isFinite(maxChars) && maxChars > 0 ? Math.floor(maxChars) : DEFAULT_MAX_CHARS;
  const full = redacted.text;
  const truncated = full.length > limit;
  // Keep the TAIL. What a pane is showing now is at the bottom; the top of a long window is
  // scrollback the conductor did not ask for.
  const text = truncated ? full.slice(full.length - limit) : full;

  return {
    ...base,
    answerable: true,
    text,
    chars: text.length,
    truncated,
    dropped_chars: truncated ? full.length - limit : 0,
    bytes_read: Number.isFinite(read.bytes) ? read.bytes : null,
    from: Number.isInteger(read.from) ? read.from : null,
    at: Number.isInteger(read.at) ? read.at : null,
    redactions: redacted.redactions,
    redaction_kinds: redacted.kinds,
    redaction_failed: redacted.failed || null,
    note: "What the pane is SHOWING, redacted and bounded. Not a claim that it ran anything.",
  };
}

/**
 * Observe several panes under ONE shared character budget.
 *
 * The budget is shared because the constraint is shared: the conductor has one context window,
 * not one per pane. Dividing it evenly is the honest default - a scheme that gave the loudest
 * pane the most room would let one runaway worker crowd the others out of the conductor's view,
 * which is precisely the failure mode a conductor exists to notice.
 */
function observePanes(window, paneIds, { totalMaxChars = DEFAULT_MAX_CHARS, maxLines } = {}) {
  const ids = Array.isArray(paneIds) ? paneIds.filter((id) => typeof id === "string" && id) : [];
  if (!ids.length) return [];
  const total = Number.isFinite(totalMaxChars) && totalMaxChars > 0
    ? Math.floor(totalMaxChars) : DEFAULT_MAX_CHARS;
  const each = Math.max(200, Math.floor(total / ids.length));
  return ids.map((id) => observePane(window, id, { maxChars: each, maxLines }));
}

module.exports = { OBSERVATION_SCHEMA, DEFAULT_MAX_CHARS, observePane, observePanes };
