"use strict";
/**
 * Phase 17D `.close` (U73) — what the shell does when a pane says it changed size.
 *
 * The renderer measures a pane and reports its geometry. That report is an INTENT, not an
 * instruction: the pane it names may have no admitted session (pane 1 is the conductor placeholder
 * until the governed launch admits one — invariant 2), supervision may not exist yet (`manager` is
 * null until the gateway verifies), and the numbers come from the least-trusted surface in the
 * system (invariant 29). Every one of those is a DECISION the main process makes and answers with;
 * none of them is an exception.
 *
 * Before this module the decision was three dereferences in an IPC handler, and the operator's log
 * carried the result on every single launch (U73):
 *
 *   Error occurred in handler for 'pane:resize': TypeError: Cannot read properties of null (reading 'resize')
 *
 * Electron caught it, so nothing crashed — but a thrown handler answers the renderer with a REJECTED
 * invoke, which is not an answer, and "did the shell refuse this, or did it break?" had no observable
 * difference. It is a decision now, and it says which one it made.
 *
 * It grants nothing and starts nothing: the only authority in reach is a resize of a session the
 * SessionManager already admitted.
 */

/** No session to resize: no supervision yet, or a pane the registry does not hold (the placeholder). */
const NO_SESSION = "no admitted session";
/** The renderer reported a geometry a ConPTY cannot be given (invariant 29 — it is not trusted). */
const BAD_DIMENSIONS = "invalid dimensions";
/**
 * The registry holds this pane's session, but no live ConPTY handle took the geometry — the process
 * ended and its record has not been forgotten yet. Reporting success here is the over-claim the
 * SessionManager's own `resize` return value exists to prevent (spec-audit F1).
 */
const NOT_RUNNING = "session not running";
/**
 * A ConPTY console screen buffer is addressed by `COORD`, whose fields are 16-bit signed. Anything
 * above this is not a large terminal, it is a number the renderer made up, and it is refused here
 * rather than truncated or allocated for somewhere below.
 */
const MAX_DIMENSION = 32767;

/** A ConPTY takes positive whole columns and rows, within what a COORD can hold. */
function isDimension(n) {
  return Number.isInteger(n) && n > 0 && n <= MAX_DIMENSION;
}

/**
 * Decide and, if admitted, perform a pane resize.
 *
 * @param {object|null} manager  the SessionManager, or null before supervision exists
 * @param {string} id            the pane/session id the renderer measured
 * @param {number} cols
 * @param {number} rows
 * @returns {{resized: boolean, reason?: string}} always an answer — this never throws
 */
function resizePane(manager, id, cols, rows) {
  if (!manager || !manager.registry || typeof manager.registry.has !== "function"
      || !manager.registry.has(id)) {
    return { resized: false, reason: NO_SESSION };
  }
  if (!isDimension(cols) || !isDimension(rows)) return { resized: false, reason: BAD_DIMENSIONS };
  let took = false;
  try {
    took = manager.resize(id, cols, rows);
  } catch (e) {
    // The session can die between the registry check and the write. That is a refusal with a
    // reason, not a handler fault: the caller gets told, the shell stays up.
    return { resized: false, reason: `resize refused: ${(e && e.message) || e}` };
  }
  // Holding a registry record is not holding a process: only the SessionManager knows whether a live
  // handle took this, and its answer is the one that gets reported (spec-audit F1).
  if (took !== true) return { resized: false, reason: NOT_RUNNING };
  return { resized: true };
}

/**
 * Is this answer a refusal the operator's log should carry (invariant 27)?
 *
 * A resize aimed at a pane with no admitted session is the ordinary startup case — the renderer fits
 * the CONDUCTOR placeholder on every launch — and logging it would drown the log it is supposed to
 * inform. Every OTHER refusal is a live pane not getting what it asked for, which is a fault, and
 * silence was the old behaviour's real defect: a thrown handler at least printed something.
 */
function refusalWorthLogging(answer) {
  return Boolean(answer && answer.resized === false && answer.reason && answer.reason !== NO_SESSION);
}

module.exports = {
  resizePane, refusalWorthLogging, NO_SESSION, BAD_DIMENSIONS, NOT_RUNNING, MAX_DIMENSION,
};
