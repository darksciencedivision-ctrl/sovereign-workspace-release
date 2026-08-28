"use strict";
/**
 * IpcSupervisor — the shell's binding to the real control plane over authenticated IPC.
 *
 * This is what makes a ConPTY session "supervised by the real Node Runtime — no naked
 * sessions" (directive §9 track 14A). SessionManager asks admit() synchronously before it
 * lets any PTY keep running; this supervisor latches a single fact: does the shell CURRENTLY
 * hold a live, authenticated, integrity-verified channel to the control plane?
 *
 *   - initial + periodic health control_events feed a RecoveryMachine (a heartbeat);
 *   - admit() returns {supervised: machine.admissionOpen}: no session survives without a
 *     currently-verified channel;
 *   - if the channel drops, the machine goes DEGRADED AND onSupervisionLost() fires so the
 *     manager tears every session down — a shell that has lost its governor runs nothing
 *     (fail-closed, directive §9 "UI recovery after process restart");
 *   - each heartbeat re-probes; when the channel is re-verified the machine goes back to
 *     SUPERVISED (a new supervision epoch) and onSupervisionRestored() fires so the shell
 *     re-admits and the UI recovers — re-admission happens ONLY on that re-verified channel;
 *   - notify() forwards each lifecycle event to the control plane (best-effort, post-admission)
 *     so the orchestra is visible (invariant 27) and the lifecycle is centrally recorded.
 *
 * The recovery lifecycle itself is the pure, headlessly-tested RecoveryMachine; this class is
 * only its live driver (the socket heartbeat) and the bridge to teardown/re-push side effects.
 *
 * HONEST LIMITATION (recorded, Phase-14A follow-up): OS-level containment — assigning the
 * PTY pid to the Node Runtime's Windows Job Object (node_runtime/supervisor/containment.py) —
 * is NOT yet wired from this Node process; that pid→job handoff needs the IPC surface to grow
 * a write op (blocked on the U25 per-node credential broker). Today the shell enforces the
 * GOVERNANCE gate (authenticated channel required, lifecycle reported, kill-on-loss); the
 * kernel-level kill-on-close containment remains the Node Runtime's, exercised in Phase 3/10.
 */
const { RecoveryMachine } = require("../../terminal/recovery/recovery-machine");
const { IpcBusy } = require("./ipc/client");

/**
 * How many consecutive BUSY beats may be skipped before the channel is scored as lost anyway.
 * A busy channel is evidence of life, not of loss (see `IpcBusy`) — but "busy forever" must not
 * become a way to hold admission open on a dead channel, so the skip is bounded. Three beats at
 * the 5 s heartbeat is 15 s, comfortably past the 10 s request timeout that always settles a real
 * in-flight request.
 */
const MAX_BUSY_SKIPS = 3;

class IpcSupervisor {
  constructor({ client, onSupervisionLost = () => {}, onSupervisionRestored = () => {}, heartbeatMs = 5000, log = () => {} }) {
    this._client = client;
    this._onLost = onSupervisionLost;
    this._onRestored = onSupervisionRestored;
    this._heartbeatMs = heartbeatMs;
    this._log = log;
    this._timer = null;
    // The recovery lifecycle is delegated to the pure machine; the supervisor only feeds it
    // probe outcomes and translates its transitions into teardown / re-push side effects.
    this._machine = new RecoveryMachine({
      onTransition: (t) => {
        if (t.reason === "lost") {
          this._log("supervision LOST — tearing down all sessions (fail-closed)");
          try { this._onLost(); } catch { /* teardown must not throw out of the probe */ }
        } else if (t.reason === "restored") {
          this._log(`supervision RESTORED (epoch ${t.epoch}) — channel re-verified, re-admitting`);
          try { this._onRestored(t); } catch { /* recovery re-push must not throw out of the probe */ }
        }
      },
    });
  }

  /** True iff the shell CURRENTLY holds a verified channel (admission open). */
  get ready() { return this._machine.admissionOpen; }

  /** Observable recovery lifecycle for the renderer banner / logs. */
  supervisionState() { return this._machine.snapshot(); }

  async start() {
    await this._probe();
    this._timer = setInterval(() => { this._probe().catch(() => {}); }, this._heartbeatMs);
    if (this._timer.unref) this._timer.unref();
    return this.ready;
  }

  async _probe() {
    let ready = false;
    try {
      const res = await this._client.controlEvent({ op: "health" });
      ready = res && res.ok === true;
      this._busySkips = 0;
    } catch (e) {
      // A BUSY channel is a NON-observation, not a negative one (Phase 17A `.roundtrip`): the
      // sequential channel is shared with `notify()`'s session-event reports, so a heartbeat can
      // collide with one. Scoring that collision as "lost" tore down every session — including the
      // operator's live conductor — on a race that proves the channel is alive. Skip the beat and
      // re-probe on the next one, bounded so "busy forever" cannot hold admission open on a dead
      // channel. Every other fault is still an immediate, fail-closed loss.
      if (e instanceof IpcBusy && (this._busySkips = (this._busySkips || 0) + 1) <= MAX_BUSY_SKIPS) {
        this._log(`supervision probe skipped — ${e.message} (beat ${this._busySkips}/${MAX_BUSY_SKIPS}, `
          + "channel demonstrably alive; not scored as a loss)");
        return;
      }
      ready = false;
      this._log(`supervision probe failed: ${e.constructor.name}: ${e.message}`);
    }
    // The machine owns the lost/restored edges and fires the callbacks above; feeding it is all
    // the driver does. A re-verified channel after a drop re-opens admission on a NEW epoch.
    this._machine.observe(ready);
  }

  /** Synchronous admission verdict read by SessionManager.spawn (current heartbeat state). */
  admit({ id, nodeId, pid }) {
    if (!this._machine.admissionOpen) return { supervised: false, reason: "no verified control-plane channel" };
    return { supervised: true, reason: `admitted node ${nodeId} pid ${pid} for session ${id}` };
  }

  /** Best-effort lifecycle report to the control plane (post-admission). */
  notify(event) {
    if (!this._client) return;
    // fire-and-forget; a report failure must not disturb the session it describes
    Promise.resolve()
      .then(() => this._client.controlEvent({ op: "session_event", event }))
      .catch(() => {});
  }

  stop() {
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
  }
}

module.exports = { IpcSupervisor, MAX_BUSY_SKIPS };
