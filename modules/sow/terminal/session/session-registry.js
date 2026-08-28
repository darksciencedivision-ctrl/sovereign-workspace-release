"use strict";
/**
 * Session registry (product code, terminal/).
 *
 * A "session" is a supervised PTY process; a "pane" is a view over it. The registry owns the
 * session lifetime, which is INDEPENDENT of any view (invariant 27; proven under test by the
 * spike's survival property, now product): detach/reattach never touches the PTY.
 *
 * State machine (deterministic, fail-closed — invariant, Directive §4):
 *   SPAWNING -> RUNNING -> EXITED | KILLED
 *   SPAWNING -> REFUSED            (supervision denied admission: a naked session is killed,
 *                                   never run — invariant 2 "no raw model / naked session")
 * Illegal transitions raise rather than silently correct (no last-write-wins, invariant 13).
 *
 * Lifecycle events append to an immutable event log. Within the RETAINED WINDOW the log is
 * append-only and ordered (invariant 12); retention itself is BOUNDED since W-63 - the last
 * `maxLogEvents` events (default 1024), plus the register and latest event of every LIVE
 * session, so cross-restart reconstruction still surfaces an interrupted session fail-closed.
 * Terminal/forgotten sessions' history outside the window evicts FIFO; per-event persistence
 * cost is therefore bounded and no longer a function of total history.
 */
const { RingBuffer } = require("./ring-buffer");

const LEGAL = {
  SPAWNING: ["RUNNING", "EXITED", "KILLED", "REFUSED"],
  RUNNING: ["EXITED", "KILLED"],
  EXITED: [],
  KILLED: [],
  REFUSED: [],
};

const TERMINAL = new Set(["EXITED", "KILLED", "REFUSED"]);

class SessionRegistry {
  constructor({ scrollbackBytes = 256 * 1024, maxLogEvents = 1024 } = {}) {
    this.sessions = new Map();
    this._log = []; // retained lifecycle events {seq, ts, id, kind, from, to, detail} - see _trimLog
    this._seq = 0;
    this._scrollbackBytes = scrollbackBytes;
    this._maxLogEvents = Math.max(1, maxLogEvents);
  }

  /** ts is injected (never Date.now() here) so the log is deterministic and testable. */
  register(id, meta = {}, ts = null) {
    if (this.sessions.has(id)) throw new Error(`duplicate session ${id}`);
    if (!meta.nodeId) throw new Error(`session ${id} has no node binding — refusing (invariant 2)`);
    const s = {
      id, state: "SPAWNING", meta,
      nodeId: meta.nodeId, pid: meta.pid ?? null, generation: meta.generation ?? null, exitCode: null,
      buffer: new RingBuffer(this._scrollbackBytes), attached: false,
    };
    this.sessions.set(id, s);
    this._append(id, "register", null, "SPAWNING",
      { nodeId: s.nodeId, pid: s.pid, generation: s.generation }, ts);
    return s;
  }

  transition(id, next, ts = null, detail = {}) {
    const s = this.get(id);
    if (!LEGAL[s.state].includes(next)) {
      throw new Error(`illegal transition ${s.state} -> ${next} (${id})`);
    }
    const from = s.state;
    s.state = next;
    this._append(id, "transition", from, next, detail, ts);
    return s;
  }

  get(id) {
    const s = this.sessions.get(id);
    if (!s) throw new Error(`unknown session ${id}`);
    return s;
  }

  has(id) { return this.sessions.has(id); }

  feed(id, data) { this.get(id).buffer.push(data); }

  /** Detaching a view leaves the PTY untouched; returns the current session state. */
  detach(id) { const s = this.get(id); s.attached = false; return s.state; }

  /** Reattach returns byte-exact scrollback; the PTY is never restarted. */
  reattach(id) { const s = this.get(id); s.attached = true; return s.buffer.snapshot(); }

  alive() {
    return [...this.sessions.values()].filter((s) => s.state === "RUNNING" || s.state === "SPAWNING");
  }

  /** Teardown order for a clean, orphan-free shutdown: currently-alive sessions. */
  teardownOrder() { return this.alive().map((s) => s.id); }

  isTerminal(id) { return TERMINAL.has(this.get(id).state); }

  /**
   * Drop a TERMINAL session's record so its id (a pane id) can host a new session — the conductor
   * pane relaunching after its session exited (Phase 17A `.pty`). Refuses while the session is
   * alive: forgetting a running session would orphan a supervised process. The append-only
   * lifecycle log is NOT touched (invariant 12) — history keeps the session that ended.
   */
  forget(id) {
    if (!this.isTerminal(id)) throw new Error(`refusing to forget a live session ${id}`);
    this.sessions.delete(id);
    return this;
  }

  /** Immutable snapshot of the RETAINED lifecycle log (for supervision / recovery). Bounded:
   *  the window plus every live session's register/latest - see the module header (W-63). */
  eventLog() { return this._log.map((e) => ({ ...e })); }

  _append(id, kind, from, to, detail, ts) {
    // deep-clone detail so the append-only log cannot be mutated through a caller's
    // retained reference (invariant 12, immutable history — the record is truly frozen).
    const frozenDetail = detail == null ? detail : structuredClone(detail);
    this._log.push({ seq: this._seq++, ts, id, kind, from, to, detail: frozenDetail });
    this._trimLog();
  }

  /**
   * W-63: keep the log bounded. Once it reaches twice the window, rebuild once: keep the most
   * recent `maxLogEvents` events, plus each LIVE session's register and latest event so an
   * interrupted-at-cut session stays fully reconstructable with its node binding (fail-closed,
   * invariant 2 posture). Dead/forgotten sessions' older events evict FIFO. One batch pass per
   * rebuild keeps amortized append cost O(1) — never a per-event pass over total history.
   */
  _trimLog() {
    if (this._log.length < this._maxLogEvents * 2) return;
    const live = new Set();
    for (const s of this.sessions.values()) {
      if (!TERMINAL.has(s.state)) live.add(s.id);
    }
    const tail = this._log.slice(-this._maxLogEvents);
    const seenSeq = new Set(tail.map((e) => e.seq));
    const pinned = [];
    if (live.size > 0) {
      const latestById = new Map();
      for (const e of this._log) {
        if (!live.has(e.id)) continue;
        if (e.kind === "register" && !seenSeq.has(e.seq)) { pinned.push(e); seenSeq.add(e.seq); }
        latestById.set(e.id, e);
      }
      for (const e of latestById.values()) {
        if (!seenSeq.has(e.seq)) { pinned.push(e); seenSeq.add(e.seq); }
      }
    }
    this._log = pinned.concat(tail).sort((a, b) => a.seq - b.seq);
  }
}

module.exports = { SessionRegistry, LEGAL, TERMINAL };
