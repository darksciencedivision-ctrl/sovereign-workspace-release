"use strict";
const { RingBuffer } = require("./ring-buffer");
/** Session registry: PTY lifetime is independent of any view (survival property under test).
 *  States: SPAWNING -> RUNNING -> EXITED | KILLED. Detach/reattach never touches the PTY. */
const LEGAL = { SPAWNING: ["RUNNING", "EXITED", "KILLED"], RUNNING: ["EXITED", "KILLED"], EXITED: [], KILLED: [] };
class SessionRegistry {
  constructor() { this.sessions = new Map(); }
  register(id, meta = {}) {
    if (this.sessions.has(id)) throw new Error(`duplicate session ${id}`);
    const s = { id, state: "SPAWNING", meta, buffer: new RingBuffer(), attached: false, pid: meta.pid ?? null, exitCode: null };
    this.sessions.set(id, s); return s;
  }
  transition(id, next) {
    const s = this.get(id);
    if (!LEGAL[s.state].includes(next)) throw new Error(`illegal transition ${s.state} -> ${next} (${id})`);
    s.state = next; return s;
  }
  get(id) { const s = this.sessions.get(id); if (!s) throw new Error(`unknown session ${id}`); return s; }
  feed(id, data) { this.get(id).buffer.push(data); }
  detach(id) { const s = this.get(id); s.attached = false; return s.state; }
  /** Reattach returns byte-exact scrollback; PTY state untouched. */
  reattach(id) { const s = this.get(id); s.attached = true; return s.buffer.snapshot(); }
  alive() { return [...this.sessions.values()].filter((s) => s.state === "RUNNING" || s.state === "SPAWNING"); }
  /** Teardown order: kill children first, then clear — callers assert no orphans. */
  teardownOrder() { return this.alive().map((s) => s.id); }
}
module.exports = { SessionRegistry, LEGAL };
