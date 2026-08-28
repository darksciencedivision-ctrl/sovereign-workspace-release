"use strict";
/**
 * ConPTY session manager (product code, terminal/).
 *
 * Owns the PTY <-> registry <-> supervisor wiring for the desktop shell. The single most
 * important property, directive §9 track 14A: **ConPTY sessions are supervised by the real
 * Node Runtime — no naked sessions**. This manager enforces that mechanically:
 *
 *   1. a spawn with no node binding is refused before any process starts;
 *   2. after the PTY starts, the manager asks the supervisor to ADMIT it (in production the
 *      supervisor reports the pid to the Node Runtime, which assigns it to a Windows Job
 *      Object — containment.py — and records it in the control plane);
 *   3. if admission is denied or errors, the PTY is KILLED immediately and the session goes
 *      to REFUSED. A process that cannot be contained never keeps running (fail-closed,
 *      invariant 2 / invariant 29, Directive §4).
 *
 * The PTY implementation is injected (`ptyFactory`) so this is fully unit-testable headlessly;
 * apps/desktop/main.js injects node-pty (ConPTY on Windows). Nothing here is Electron-specific.
 */
const { SessionRegistry } = require("../session/session-registry");

class SupervisionDenied extends Error {}

class SessionManager {
  /**
   * @param {object}   opts
   * @param {Function} opts.ptyFactory  (spec) => IPty-like { pid, onData(cb), onExit(cb), write(d), resize(c,r), kill() }
   * @param {object}   opts.supervisor  { admit({id,nodeId,pid}) => {supervised, reason?}, notify(event) }
   * @param {SessionRegistry} [opts.registry]
   * @param {Function} [opts.now]       () => ISO timestamp (injected for deterministic logs)
   */
  constructor({ ptyFactory, supervisor, registry = new SessionRegistry(), now = () => new Date().toISOString() }) {
    if (typeof ptyFactory !== "function") throw new Error("ptyFactory is required");
    if (!supervisor || typeof supervisor.admit !== "function") {
      throw new Error("a supervisor with admit() is required — a shell cannot run naked sessions");
    }
    this._ptyFactory = ptyFactory;
    this._supervisor = supervisor;
    this.registry = registry;
    this._now = now;
    this._ptys = new Map(); // id -> {pty, generation, pid}; pane id alone is never process identity
    this._generation = 0;
    this._listeners = new Set(); // (event) => void  view/render sinks
  }

  onEvent(fn) { this._listeners.add(fn); return () => this._listeners.delete(fn); }

  _emit(event) {
    for (const fn of this._listeners) {
      try { fn(event); } catch { /* a view sink must never break the manager */ }
    }
    try { this._supervisor.notify?.(event); } catch { /* supervision notify is best-effort after admission */ }
  }

  /**
   * Spawn a supervised session. Throws SupervisionDenied (after killing the PTY) if the
   * supervisor refuses admission. Returns the session record on success.
   */
  spawn({ id, nodeId, spec }) {
    if (!id) throw new Error("spawn requires an id");
    if (!nodeId) throw new Error("spawn requires a nodeId — no naked sessions (invariant 2)");
    const priorHandle = this._ptys.get(id);
    if (priorHandle) {
      throw new Error(`session ${id} process generation ${priorHandle.generation} still active `
        + `(pid ${priorHandle.pid}) — replacement refused until matching PTY exit`);
    }
    if (this.registry.has(id)) throw new Error(`duplicate session ${id}`);

    const p = this._ptyFactory(spec || {});
    const generation = ++this._generation;
    const handle = { pty: p, generation, pid: p.pid };
    const ts0 = this._now();
    this.registry.register(id, { ...(spec || {}), nodeId, pid: p.pid, generation }, ts0);
    this._ptys.set(id, handle);

    // Install observation BEFORE admission. A denial still created an OS process, and kill() is only
    // intent; without this callback the denied process could be forgotten/replaced while still alive.
    p.onData((data) => {
      if (this._ptys.get(id) !== handle) return; // delayed output from an older pane generation
      const current = this.registry.has(id) ? this.registry.get(id) : null;
      if (!current || current.generation !== generation || current.state !== "RUNNING") return;
      this.registry.feed(id, data);
      this._emit({ kind: "data", id, data, pid: p.pid, generation });
    });
    p.onExit((info) => {
      const code = info && typeof info === "object" ? info.exitCode : info;
      const isCurrentHandle = this._ptys.get(id) === handle;
      const s = this.registry.has(id) ? this.registry.get(id) : null;
      const isCurrentRecord = Boolean(s && s.generation === generation);
      if (isCurrentRecord && (s.state === "RUNNING" || s.state === "SPAWNING")) {
        this.registry.transition(id, "EXITED", this._now(), { exitCode: code });
        s.exitCode = code;
      }
      if (isCurrentHandle) this._ptys.delete(id);
      this._emit({
        kind: "exit", id, pid: p.pid, generation, exitCode: code, processExited: true,
        matchedCurrentSession: isCurrentHandle && isCurrentRecord,
      });
    });

    let admission;
    try {
      admission = this._supervisor.admit({ id, nodeId, pid: p.pid });
    } catch (e) {
      admission = { supervised: false, reason: `supervisor error: ${e.message}` };
    }
    if (!admission || admission.supervised !== true) {
      // Fail closed: mark REFUSED, then signal the just-started process. Retain its exact handle until
      // the already-installed onExit callback confirms death; REFUSED means "not admitted", not
      // "process no longer exists".
      this.registry.transition(id, "REFUSED", this._now(),
        { reason: admission ? admission.reason : "no verdict" });
      this._emit({
        kind: "refused", id, nodeId, pid: p.pid, generation,
        reason: admission ? admission.reason : "no verdict",
      });
      try { p.kill(); } catch { /* already dead */ }
      const error = new SupervisionDenied(
        `session ${id} refused: ${admission ? admission.reason : "no supervisor verdict"}`);
      error.sessionIdentity = { pid: p.pid, generation };
      error.processExitPending = this._ptys.get(id) === handle;
      throw error;
    }

    this.registry.transition(id, "RUNNING", this._now(), { pid: p.pid });
    this._emit({ kind: "spawn", id, nodeId, pid: p.pid, generation });

    return this.registry.get(id);
  }

  /**
   * Write to a session's ConPTY. Returns whether a LIVE pty handle received the bytes.
   *
   * Phase 17C `.close`: the return value is load-bearing and used to be absent. `onExit` deletes the
   * handle (above) while the registry record survives until someone `forget()`s it, so a write to an
   * EXITED/KILLED session used to vanish into the optional chain and report nothing — and the voice
   * delivery path, which guards on `registry.has(id)`, then reported the operator's utterance as
   * "delivered to the conductor" when no process existed to receive it.
   *
   * `.close-revalidate` — what "LIVE" means here, exactly, because the previous sentence over-claimed
   * (spec-audit MINOR-10): true means a pty handle for this id was still registered and accepted the
   * bytes. Between a process dying and `onExit` firing, that handle exists and this returns true. It is
   * a HANDLE-level fact, not a proof of receipt; the voice path does not rely on it alone — a delivery
   * is only claimed after the pane echoes the bytes back (voice/conductor-write.js).
   */
  write(id, data) {
    const handle = this._ptys.get(id);
    const session = this.registry.has(id) ? this.registry.get(id) : null;
    if (!handle || !session || session.state !== "RUNNING"
        || session.generation !== handle.generation) return false;
    handle.pty.write(data);
    return true;
  }

  /**
   * Resize a session's ConPTY. Returns whether a LIVE pty handle took the geometry.
   *
   * Phase 17D `.close` (spec-audit F1): the return value used to be absent, and it is the same
   * silent-discard shape `write` was fixed for at 17C. The registry record outlives the process, so
   * an ended session still answers `registry.has(id)` — and the shell's `pane:resize` handler, which
   * decided from exactly that, reported `{resized:true}` for a pane where nothing was resized. As
   * with `write`, true is a HANDLE-level fact: a handle of this generation existed and accepted the
   * call.
   */
  resize(id, cols, rows) {
    const handle = this._ptys.get(id);
    const session = this.registry.has(id) ? this.registry.get(id) : null;
    if (!handle || !session || session.state !== "RUNNING"
        || session.generation !== handle.generation) return false;
    handle.pty.resize(cols, rows);
    return true;
  }

  /** Operator/gov-initiated kill. Transitions to KILLED (distinct from a process EXIT). */
  kill(id) {
    const handle = this._ptys.get(id);
    if (!handle) return;
    const p = handle.pty;
    this.registry.transition(id, "KILLED", this._now(), {});
    // A signal is not evidence that the process is gone. Only onExit confirms it.
    this._emit({
      kind: "kill", id, pid: handle.pid, generation: handle.generation, processExited: false,
    });
    try { p.kill(); } catch { /* already dead */ }
  }

  /**
   * Forget an ended registry record only after node-pty confirmed that exact process generation
   * exited. A KILLED state is signal intent, not proof; retaining the handle prevents pane reuse from
   * turning a delayed old callback into authority over a replacement.
   */
  forget(id) {
    const handle = this._ptys.get(id);
    if (handle) {
      throw new Error(`session ${id} process generation ${handle.generation} has not exited `
        + `(pid ${handle.pid})`);
    }
    this.registry.forget(id);
    return this;
  }

  /** Exact identity of a process whose PTY has not confirmed exit, or null. */
  processIdentity(id) {
    const handle = this._ptys.get(id);
    return handle ? { pid: handle.pid, generation: handle.generation } : null;
  }

  /** Clean, orphan-free teardown: kill every still-alive session (children-first via registry order). */
  killAll() {
    for (const id of this.registry.teardownOrder()) {
      try { this.kill(id); } catch { /* already terminal */ }
    }
  }

  pendingProcessIdentities() {
    return [...this._ptys.entries()].map(([id, handle]) => ({
      id, pid: handle.pid, generation: handle.generation,
    }));
  }

  /**
   * Request termination and wait for node-pty to confirm every tracked process exit.
   * A kill signal is not completion; self-checks use this boundary before their pipe owner exits.
   */
  async shutdown(timeoutMs = 15000) {
    this.killAll();
    if (this._ptys.size === 0) return { complete: true, pending: [] };
    await new Promise((resolve) => {
      let settled = false;
      let timer = null;
      const finish = () => {
        if (settled) return;
        settled = true;
        if (timer) clearTimeout(timer);
        off();
        resolve();
      };
      const off = this.onEvent((event) => {
        if (event.kind === "exit" && this._ptys.size === 0) finish();
      });
      timer = setTimeout(finish, timeoutMs);
      if (this._ptys.size === 0) finish();
    });
    const pending = this.pendingProcessIdentities();
    return { complete: pending.length === 0, pending };
  }

  alive() { return this.registry.alive().map((s) => s.id); }
}

module.exports = { SessionManager, SupervisionDenied };
