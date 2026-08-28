"use strict";
/**
 * Conductor voice-IN delivery decision — Phase 16E `.wire` (closes the WRITE half of U67).
 *
 * `.engine` shipped the read half (voice-source.js sources `conductor_voice_feed@1.0` from the REAL
 * ConductorVoiceBridge). `.wire` connects the shell talk button to that feed and DELIVERS a CHAT
 * transcript into the conductor pane's input — "the same command path as typing" (OP-8 §13.2/§13.5).
 *
 * This module is the PURE, deterministic delivery decision + result fold (no Electron, no I/O), so the
 * routing→delivery contract is unit-tested with zero dependence on a live shell. The load-bearing
 * honesty rule, fail-closed:
 *   - a transcript is DELIVERED into the conductor input ONLY when the Python bridge routed it as CHAT
 *     (`sourced ∧ delivered ∧ kind==="chat"` with non-empty text). The shell NEVER re-classifies; a
 *     PROTECTED/DESTRUCTIVE action comes back `queued` (surfaced in the approval drawer, never delivered
 *     — invariant 25) and a low-confidence transcript comes back `needs_clarification` (never delivered).
 *   - the shell self-authorizes NOTHING (invariant 1): it forwards the bridge's decision, it does not
 *     make one. `written` in the result reflects what the PTY write actually did, never a fabricated
 *     "delivered".
 */

// A non-empty trimmed string, else null. Delivery text must be real transcript, never "" or whitespace.
function _text(v) {
  return typeof v === "string" && v.trim() ? v : null;
}

/**
 * Decide whether a voice feed's transcript should be written into the conductor input.
 * @param {object} feed a `conductor_voice_feed@1.0` dict (or the fail-closed unavailable shape)
 * @returns {{shouldDeliver:boolean, text:(string|null), reason:string}}
 *   shouldDeliver true ONLY for a sourced CHAT outcome with real text; otherwise false + a reason
 *   naming why (queued protected action / needs clarification / unavailable / no text).
 */
function decideDelivery(feed) {
  if (!feed || typeof feed !== "object") {
    return { shouldDeliver: false, text: null, reason: "no voice feed (fail-closed)" };
  }
  if (feed.sourced !== true) {
    return { shouldDeliver: false, text: null, reason: `voice unavailable: ${feed.reason || "not sourced"}` };
  }
  const outcome = feed.outcome && typeof feed.outcome === "object" ? feed.outcome : {};
  if (outcome.kind === "proposed_action" || feed.queued === true) {
    // invariant 25: a protected/destructive spoken action is PROPOSED (queued for approval), never
    // delivered into the conductor and never executed. It surfaces in the approval drawer.
    return { shouldDeliver: false, text: null, reason: "protected/destructive action — queued for approval (never delivered)" };
  }
  if (outcome.kind === "clarify" || feed.needs_clarification === true) {
    return { shouldDeliver: false, text: null, reason: outcome.reason || "not understood — repeat (never delivered)" };
  }
  if (feed.delivered !== true || outcome.kind !== "chat") {
    return { shouldDeliver: false, text: null, reason: "no chat outcome to deliver" };
  }
  // the delivered text is ONLY ever what the bridge routed (delivered_text), never re-derived here.
  const text = _text(feed.delivered_text) || _text(outcome.text);
  if (!text) {
    return { shouldDeliver: false, text: null, reason: "chat outcome carried no transcript text (fail-closed)" };
  }
  return { shouldDeliver: true, text, reason: "chat — deliver to conductor input" };
}

/**
 * Fold the sourced feed + the actual write result into the structured object the renderer draws.
 * PURE. `write` describes what the conductor-input PTY write did ({written:boolean, reason?}); when no
 * delivery was attempted it is `{written:false, reason}` from `decideDelivery`. Nothing is fabricated:
 * `delivered_to_conductor` is true ONLY when a CHAT transcript was actually written to an admitted
 * conductor session (never when the session is absent — that is honestly OWED to 16F).
 * @returns {{sourced, engine, outcome, delivered, delivered_text, queued, needs_clarification,
 *            delivered_to_conductor, write, note, live_capture_owed, tts}}
 */
function buildCaptureResult(feed, write) {
  const f = feed && typeof feed === "object" ? feed : {};
  const w = write && typeof write === "object" ? write : { written: false, reason: "no write attempted" };
  // Phase 17C `.close`: the conductor input is a real interactive TUI now, so a delivery is TWO writes
  // — the transcript body and the submit key. Both are required. A body sitting unsent in the input box
  // is the one failure the operator cannot see: the text is on screen, so it looks delivered, and the
  // conductor never received it. `delivered_to_conductor` therefore needs `submitted` as well, and a
  // write object that does not report one has not submitted (fail closed, never lenient by absence).
  const wrote = w.written === true && w.submitted === true;
  return {
    sourced: f.sourced === true,
    engine: f.engine || { name: "unknown", mock: true, real_available: false },
    outcome: f.outcome || { kind: "clarify", source: null, text: "", confidence: null, reason: "no outcome" },
    delivered: f.delivered === true,                 // the bridge's routing verdict (CHAT)
    delivered_text: typeof f.delivered_text === "string" ? f.delivered_text : null,
    queued: f.queued === true,                        // protected/destructive → approval drawer
    needs_clarification: f.needs_clarification === true,
    delivered_to_conductor: wrote,                    // both writes actually landed (never fabricated)
    // `written` reports the BODY, `submitted` the submit key — separately, so a half-delivery is
    // visible rather than folded into one optimistic boolean.
    write: { written: w.written === true, submitted: w.submitted === true,
             // whether interior newlines were collapsed to keep one utterance one prompt (17C `.close`)
             flattened: w.flattened === true,
             // how much of the utterance the pane echoed back — the observation the submit key waits on
             echo: w.echo && typeof w.echo === "object" ? { ...w.echo } : null,
             // `.close-revalidate`: WHY it was safe to type at all — the pane-state precondition's
             // verdict (input / prompt / unknown), and whether an earlier unsubmitted utterance
             // blocked this one. Both are refusals the operator must be able to read, not just
             // fields main knows about.
             pane_state: w.pane_state && typeof w.pane_state === "object" ? { ...w.pane_state } : null,
             residue: w.residue && typeof w.residue === "object" ? { ...w.residue } : null,
             // Phase 17C `.disarm` (U171): what the supervisor still held for this turn after the
             // submit key — `admitted` / `pending` / `ended` / `unavailable`. This fold is an explicit
             // whitelist, so a field it does not name is dropped silently: `delivered_to_conductor`
             // stayed honest without it (it keys off `submitted`), but the receipt and the Inspector
             // could not see WHY a delivery failed, which is the half the operator needs.
             turn_fate: typeof w.turn_fate === "string" ? w.turn_fate : null,
             // The launch-ticket-pinned boundary that governed this write. Preserve the delivery
             // module's measured claim through the UI fold so receipts do not have to infer it from
             // the separately displayed launch ticket.
             authority_boundary: w.authority_boundary && typeof w.authority_boundary === "object"
               ? { ...w.authority_boundary } : null,
             reason: w.reason || (wrote ? "written to conductor input" : "not written") },
    tts: false,                                       // I-V2/D-VOICE-02: STT-only, no synthesis
    note: wrote
      ? "chat transcript written into the conductor input (same command path as typing)"
      : (w.written === true
        ? `transcript body reached the conductor input but was NOT submitted (${w.reason || "no submit key"})`
        : (f.delivered === true
          ? "chat routed by the bridge, but this capture has no confirmed governed-conductor submission"
          : (w.reason || "no chat outcome to deliver"))),
    live_capture_owed: f.live_capture_owed || { owed: true, issue: "17C.capture-evidence" },
  };
}

module.exports = { decideDelivery, buildCaptureResult };
