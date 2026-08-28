"use strict";
/**
 * The U177 verdict: did the ADMITTED voice turn survive having every renderer IPC channel driven at it?
 *
 * Separated from the self-check that uses it for one reason — a verdict that only ever runs inside a
 * live in-Electron receipt is a verdict nobody can falsify. Here each way of being wrong is its own
 * failing case in `test/channel-sweep.test.js`.
 *
 * It answers "survived" only when ALL of these hold, and says which one did not:
 *
 *  1. the sweep actually drove every channel (`ok`, every row `invoked`) — a verdict about a sweep
 *     that skipped a channel is a verdict about nothing, and the skipped one is exactly where a
 *     dynamic release would sit;
 *  2. no release row appeared in the audit DURING the sweep. `voice_turn_disarmed` and
 *     `voice_turn_reset` are answers to facts Electron main observes for itself (the OS input path,
 *     the node-pty exit) — a renderer channel cannot witness either, so ANY of them here is a
 *     failure, whichever turn it names. `voice_turn_cancelled` is the one exception, and it is
 *     narrower than "some other turn": the cancelled turn must have been MINTED during this same
 *     sweep (its `voice_turn_pending` row is in the window too). That is the audited exception in
 *     CHANNEL_MAY_REACH_RELEASE — `voice:capture` voiding a turn it minted and nobody else has seen.
 *     A cancel of a turn that predates the sweep is a release like any other, and the first version
 *     of this predicate let every one of them through (spec-audit F4). Cancelling the ADMITTED turn
 *     is a failure whatever else is true;
 *
 *     The WINDOW itself is fail-closed. The audit is a bounded ring that drops its oldest rows, so
 *     "the tail past the pre-sweep snapshot" is only the truth while nothing was dropped between the
 *     two reads — at the cap, `after.length === before.length`, the window is empty and criterion 2
 *     would examine nothing and pass. The ring's own drop counter is therefore required on both
 *     sides and must be unchanged; the party that can flood that ring is the least-trusted one
 *     (U182), so a missing or moved counter is a refusal, not a detail (validator MINOR-7 /
 *     spec-audit F3);
 *  3. the service still holds THIS turn, active, restricting the session — read from the authority's
 *     own state, not inferred from the absence of a row, because a release that wrote no row at all
 *     is the class U176 was.
 */

const RELEASE_EVENTS = ["voice_turn_disarmed", "voice_turn_reset", "voice_turn_cancelled"];

function turnSurvivedChannelSweep({
  turnId, before, after, stateAfter, sweep, droppedBefore, droppedAfter,
} = {}) {
  const reasons = [];
  const id = String(turnId || "");
  if (!id) reasons.push("no admitted turn id was given — a verdict about no turn is not a verdict");

  if (!sweep || sweep.ok !== true) {
    reasons.push(`the channel sweep did not complete cleanly (uncovered: `
      + `${JSON.stringify((sweep && sweep.uncovered) || null)}, missing: `
      + `${JSON.stringify((sweep && sweep.missing) || null)})`);
  }
  const rows = (sweep && Array.isArray(sweep.channels) ? sweep.channels : []);
  const notDriven = rows.filter((r) => r.invoked !== true).map((r) => r.channel || r.method);
  if (!sweep || rows.length === 0) reasons.push("the sweep drove no channels at all");
  else if (notDriven.length) reasons.push(`these channels were never driven: ${notDriven.join(", ")}`);

  const beforeRows = Array.isArray(before) ? before : [];
  const afterRows = Array.isArray(after) ? after : [];
  // The window is the tail past the pre-sweep snapshot — which is the truth only if the bounded ring
  // dropped nothing between the two reads. Both counts are required and must match; anything else
  // means the window cannot be computed, and an uncomputable window is a refusal.
  if (!Number.isFinite(droppedBefore) || !Number.isFinite(droppedAfter)) {
    reasons.push("the audit ring's drop counter was not read on both sides of the sweep, so the "
      + "window cannot be trusted to contain every row written during it");
  } else if (droppedBefore !== droppedAfter) {
    reasons.push(`the audit ring dropped ${droppedAfter - droppedBefore} row(s) during the sweep — `
      + "a release row may have fallen out of the window");
  }
  if (afterRows.length < beforeRows.length) {
    reasons.push("the audit shrank across the sweep — the window is not the tail of an append-only trail");
  }
  const during = afterRows.slice(beforeRows.length);
  // Turns MINTED inside the window: the only ones `voice:capture` may cancel here (see the header).
  const mintedDuringSweep = new Set(during
    .filter((row) => row && row.event === "voice_turn_pending" && row.turn_id)
    .map((row) => String(row.turn_id)));
  for (const row of during) {
    if (!RELEASE_EVENTS.includes(row && row.event)) continue;
    const rowTurn = String((row && row.turn_id) || "");
    if (row.event === "voice_turn_cancelled" && rowTurn !== id && mintedDuringSweep.has(rowTurn)) {
      continue;   // voice:capture voiding a turn it minted in this same window, before admission
    }
    reasons.push(`${row.event} was recorded while the renderer channels were being driven `
      + `(turn ${row.turn_id || "?"}, source ${row.source || "none"}) — no renderer channel may end a turn`);
  }

  const state = stateAfter || {};
  const turn = state.turn || {};
  if (!state.active || String(state.active.turn_id || "") !== id) {
    reasons.push(`the supervisor no longer holds turn ${id || "(none)"} as active `
      + `(active: ${JSON.stringify((state.active && state.active.turn_id) || null)})`);
  }
  if (turn.restricted !== true || turn.phase !== "active" || String(turn.turn_id || "") !== id) {
    reasons.push(`the operator-facing turn state is no longer this turn, active and restricting `
      + `(${JSON.stringify({ restricted: turn.restricted, phase: turn.phase, turn_id: turn.turn_id })})`);
  }

  return { survived: reasons.length === 0, reasons, released_during_sweep: during.filter(
    (row) => RELEASE_EVENTS.includes(row && row.event)).map((row) => ({ event: row.event, turn_id: row.turn_id || null, source: row.source || null })) };
}

module.exports = { turnSurvivedChannelSweep, RELEASE_EVENTS };
