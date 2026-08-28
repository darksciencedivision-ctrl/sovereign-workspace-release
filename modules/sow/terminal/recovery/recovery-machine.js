"use strict";
/**
 * RecoveryMachine — the observable supervision lifecycle (product code, terminal/).
 *
 * Directive §9 track 14A requires "UI recovery after process restart": when the control-plane
 * channel drops (a gateway/control-plane restart, a transient loopback fault) the shell must
 * fail closed — tear every session down, admit nothing during the gap — and re-admit ONLY once
 * the channel is re-verified. Before this module that lived as a single latched boolean inside
 * IpcSupervisor; here it is an explicit, deterministic, fail-closed state machine so the whole
 * recovery is observable (invariant 27) and headlessly testable, independent of any live socket.
 *
 * States (fail-closed — admission is open in exactly one of them):
 *   INIT        never supervised yet (boot / never reached a verified channel) — admission SHUT
 *   SUPERVISED  channel verified this heartbeat                                — admission OPEN
 *   DEGRADED    the loss edge: channel just dropped, sessions being torn down  — admission SHUT
 *   RECOVERING  still down, actively re-probing after a loss                   — admission SHUT
 *
 * The machine holds NO clock and NO socket: it is fed one probe outcome at a time by the
 * supervisor's heartbeat (`observe(ready)`), which keeps it pure and deterministic. `epoch` is a
 * monotonic supervision generation — it bumps on every (re)establish — so the UI/inspector can
 * tell a freshly re-established channel from the original one, and downstream logic can key
 * off "new generation" rather than a bare boolean edge.
 *
 * Every transition is appended to an immutable history (invariant 12) with the injected
 * timestamp and the epoch the machine settled into, and mirrored to `onTransition` for the
 * supervisor to translate into teardown (on "lost") and re-push (on "restored").
 */

// (from-state) -> given a probe outcome, the next state. `null` next means "stay, no transition".
// The loss edge (SUPERVISED->DEGRADED) is the ONLY one that flags teardown; a re-verify from a
// down state ("restored") bumps the epoch.
const STATES = new Set(["INIT", "SUPERVISED", "DEGRADED", "RECOVERING"]);

class RecoveryMachine {
  constructor({ now = () => new Date().toISOString(), onTransition = () => {} } = {}) {
    this._now = now;
    this._onTransition = onTransition;
    this._state = "INIT";
    this._epoch = 0;          // supervision generation; 0 = never supervised
    this._history = [];       // append-only [{seq, from, to, reason, teardown?, ts, epoch}]
    this._lastReason = null;
  }

  get state() { return this._state; }
  get epoch() { return this._epoch; }
  /** The single fail-closed gate SessionManager admission consults. */
  get admissionOpen() { return this._state === "SUPERVISED"; }

  /**
   * Feed one probe outcome from the supervision heartbeat.
   * @param {boolean} ready  did the channel verify this heartbeat?
   * @returns {object|null}  the emitted transition, or null if the state did not change.
   */
  observe(ready) {
    const from = this._state;
    let to = null;
    let reason = null;
    let teardown = false;

    if (ready) {
      if (from === "INIT") { to = "SUPERVISED"; reason = "established"; }
      else if (from === "DEGRADED" || from === "RECOVERING") { to = "SUPERVISED"; reason = "restored"; }
      // SUPERVISED + ready -> stay (a healthy heartbeat; no transition)
    } else {
      if (from === "SUPERVISED") { to = "DEGRADED"; reason = "lost"; teardown = true; }
      else if (from === "DEGRADED") { to = "RECOVERING"; reason = "recovering"; }
      // INIT + not-ready -> stay (never established); RECOVERING + not-ready -> hold
    }

    if (to === null) return null;

    this._state = to;
    if (reason === "established" || reason === "restored") this._epoch += 1;
    this._lastReason = reason;

    const t = { seq: this._history.length, from, to, reason, ts: this._now(), epoch: this._epoch };
    if (teardown) t.teardown = true;
    this._history.push(t);
    try { this._onTransition(t); } catch { /* an observer must never break the machine */ }
    return { ...t };
  }

  /** Immutable copy of the append-only transition history (invariant 12). */
  history() { return this._history.map((e) => ({ ...e })); }

  /** Current lifecycle for the renderer recovery banner / inspector. */
  snapshot() {
    return { state: this._state, admissionOpen: this.admissionOpen, epoch: this._epoch, lastReason: this._lastReason };
  }
}

module.exports = { RecoveryMachine, STATES };
