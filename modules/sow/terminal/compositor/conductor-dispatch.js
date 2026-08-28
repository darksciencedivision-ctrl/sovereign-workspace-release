"use strict";
/**
 * Conductor DISPATCH chrome (product code, terminal/). Phase 16C `.dispatch` (directive §15 track 16C;
 * OP-8 §13.4).
 *
 * Pure/deterministic render model for the conductor pane's dispatch line — no time, no I/O, no Node.
 * The govern-born conductor dispatches work to worker nodes over MCP and synthesizes their gated
 * results; the Python `control_plane.orchestration.conductor_dispatch` folds one governed dispatch run
 * into a `conductor_dispatch_feed@1.0` record and the shell sources it (dispatch-source.js). This module
 * only shapes what the sandboxed renderer draws from that record.
 *
 * HONESTY (invariant 3 / directive §6): it NEVER dresses a mock dispatch as live — the summary states
 * the legs verbatim (`conductor=mock · workers=mock`) and always surfaces the OWED live-worker leg
 * (U58). A missing/undispatched feed renders an explicit "dispatch unavailable"/reason, never a
 * fabricated assignment.
 */
const DISPATCH_LABEL = "DISPATCH";

function _int(n) {
  return typeof n === "number" && Number.isFinite(n) ? n : 0;
}

/**
 * The conductor dispatch summary drawn from a dispatch feed (`conductor_dispatch_feed@1.0`).
 * Fail-closed: a feed that is not `dispatched` renders `dispatched:false` with the feed's reason.
 * The `owed` flag is always surfaced (the live-worker leg is owed regardless — U58).
 */
function conductorDispatchSummary(feed) {
  const f = feed || {};
  const owed = !!(f.live_workers_owed && f.live_workers_owed.owed);
  const legs = f.legs || {};
  const conductorLeg = typeof legs.conductor === "string" ? legs.conductor : "unknown";
  const workersLeg = typeof legs.workers === "string" ? legs.workers : "unknown";
  if (f.dispatched !== true) {
    return {
      label: DISPATCH_LABEL,
      dispatched: false,
      owed,
      reason: (typeof f.reason === "string" && f.reason) ? f.reason : "dispatch unavailable",
      text: `${DISPATCH_LABEL} · unavailable${owed ? " · live workers OWED (U58)" : ""}`,
    };
  }
  const assigned = _int(f.assigned_count);
  const accepted = _int(f.accepted_count);
  const queued = _int(f.queued_count);
  const byDescriptor = f.by_descriptor === true;
  // The one line the operator reads: how many workers the conductor dispatched to (by descriptor),
  // how many artifacts the GATE accepted (qualified "gate-accepted" so it is never read as OPERATOR
  // acceptance — invariant 1; gate promotion is not an operator decision), the legs verbatim, and the
  // owed live-worker leg.
  const text = `${DISPATCH_LABEL} · ${assigned} worker(s)${byDescriptor ? " by descriptor" : ""}`
    + ` · ${accepted} gate-accepted${queued ? ` · ${queued} queued` : ""}`
    + ` · legs ${conductorLeg}/${workersLeg}`
    + (owed ? " · live workers OWED (U58)" : "");
  return {
    label: DISPATCH_LABEL,
    dispatched: true,
    owed,
    assigned,
    accepted,
    queued,
    byDescriptor,
    conductorLeg,
    workersLeg,
    acceptanceVerdict: typeof f.acceptance_verdict === "string" ? f.acceptance_verdict : null,
    acceptancePacket: typeof f.acceptance_packet === "string" ? f.acceptance_packet : null,
    text,
  };
}

module.exports = { DISPATCH_LABEL, conductorDispatchSummary };
