"use strict";
/**
 * Session-state reconstruction (product code, terminal/).
 *
 * Folds the SessionRegistry lifecycle log (invariant 12 within its bounded retention window,
 * W-63; every LIVE session's register and latest event are always retained) — the authoritative
 * record of recent supervised PTYs and their state transitions — into the ordered view the shell rebuilds
 * after a control-plane/process restart (directive §9 track 14A, "UI recovery after process
 * restart"). The log is the persisted truth; the live PTYs are gone (they die with the shell),
 * so reconstruction reports what EXISTED and its last state, and classifies each session for
 * recovery.
 *
 * The load-bearing rule: a session that was still alive (SPAWNING/RUNNING) at the cut is marked
 * INTERRUPTED and `recoverable: false` / `needsRelaunch: true`. Fail-closed, invariant 2 — the
 * shell NEVER silently re-spawns a naked session on boot; it surfaces the interrupted session so
 * the operator relaunches it through the supervised admission path (a fresh, re-verified channel).
 * Terminal sessions (EXITED/KILLED/REFUSED) reconstruct as history only.
 *
 * Pure and deterministic: it reads the log, never writes it, and takes no clock or I/O.
 */

// last-known state -> {disposition, needsRelaunch}. Alive-at-the-cut states are interrupted.
const DISPOSITION = {
  SPAWNING: { disposition: "interrupted", needsRelaunch: true },
  RUNNING: { disposition: "interrupted", needsRelaunch: true },
  EXITED: { disposition: "exited", needsRelaunch: false },
  KILLED: { disposition: "killed", needsRelaunch: false },
  REFUSED: { disposition: "refused", needsRelaunch: false },
};
const TERMINAL = new Set(["EXITED", "KILLED", "REFUSED"]);

/**
 * @param {Array<{seq,ts,id,kind,from,to,detail}>} eventLog  SessionRegistry.eventLog() output
 * @returns {Array<object>} one record per session, in registration order.
 */
function reconstructSessions(eventLog) {
  const byId = new Map(); // id -> accumulator (first-seen order preserved by Map insertion)
  for (const e of eventLog || []) {
    if (!e || !e.id) continue;
    let acc = byId.get(e.id);
    if (!acc) {
      acc = { id: e.id, nodeId: null, pid: null, lastState: "SPAWNING" };
      byId.set(e.id, acc);
    }
    if (e.kind === "register") {
      if (e.detail && e.detail.nodeId != null) acc.nodeId = e.detail.nodeId;
      if (e.detail && e.detail.pid != null) acc.pid = e.detail.pid;
      acc.lastState = e.to || "SPAWNING";
    } else if (e.kind === "transition") {
      if (e.to) acc.lastState = e.to;
      if (e.detail && e.detail.pid != null) acc.pid = e.detail.pid;
    }
  }

  const out = [];
  for (const acc of byId.values()) {
    const d = DISPOSITION[acc.lastState] || { disposition: "unknown", needsRelaunch: false };
    out.push({
      id: acc.id,
      nodeId: acc.nodeId,
      pid: acc.pid,
      lastState: acc.lastState,
      terminal: TERMINAL.has(acc.lastState),
      disposition: d.disposition,
      // fail-closed: only ever false here — a naked session is never auto-recovered (invariant 2).
      recoverable: false,
      needsRelaunch: d.needsRelaunch,
    });
  }
  return out;
}

/** The sessions a restart must surface for supervised relaunch (alive at the cut). */
function interruptedSessions(eventLog) {
  return reconstructSessions(eventLog).filter((s) => s.needsRelaunch);
}

module.exports = { reconstructSessions, interruptedSessions };
