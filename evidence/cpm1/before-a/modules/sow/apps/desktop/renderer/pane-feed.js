"use strict";
/**
 * PaneFeed — race-free ordering of a pane's terminal output across (dispose → re-attach).
 *
 * Phase 16A fix. THE defect this closes: a pane's xterm VIEW is (re)created lazily by the
 * §10.2 layout plan, which arrives on a debounced channel — AFTER the supervised PTY has
 * already printed its banner. The old renderer wrote live `pane:data` straight to the term
 * and DROPPED anything that arrived before the term existed (`if (rec) rec.term.write`), and
 * it never replayed the session's byte-exact scrollback on (re)attach even though the code
 * claimed "re-expansion reattaches losslessly". Net: blank panes, no banner (operator report,
 * OP-10). The scrollback already exists byte-exact in the main-process SessionRegistry
 * (RingBuffer, invariant 27); this helper stitches it to the live stream with NO gap and NO
 * duplication, using a per-session monotonic data sequence number.
 *
 * Contract (all writes flow through this, deterministic — no clock, no I/O):
 *   - main tags every `pane:data` chunk with a per-session monotonically increasing `seq`.
 *   - main's `pane:scrollback` returns {text, seq}: the byte-exact snapshot AND the seq of the
 *     last chunk INCLUDED in that snapshot (atomic on the single-threaded main loop).
 *   - while a term is (re)attaching, live chunks are BUFFERED here (not written).
 *   - attach(text, baseSeq) returns the ordered writes: scrollback first, then only the
 *     buffered chunks with seq > baseSeq (chunks <= baseSeq are already in the snapshot ⇒ no
 *     duplication), in seq order (no reordering). After attach the feed is ready and live
 *     chunks pass straight through.
 *
 * The seq comparison is the load-bearing invariant: it makes the snapshot boundary exact, so
 * a chunk can never be both replayed (in scrollback) and re-written (from the live buffer),
 * and no chunk between "snapshot taken" and "term ready" is lost.
 *
 * Wrapped in an IIFE so the class name is NOT a global lexical binding: the renderer loads this as
 * a classic <script>, and a bare top-level `class PaneFeed` would collide with renderer.js's
 * `const PaneFeed` (both share the global lexical scope) — a SyntaxError that aborts renderer.js.
 * Only `window.PaneFeed` (browser) / `module.exports` (Node test) are exported.
 */
(function () {
class PaneFeed {
  constructor() {
    this._ready = false;
    this._pending = []; // {seq, data} buffered while (re)attaching
  }

  get ready() {
    return this._ready;
  }

  /**
   * A live `pane:data` chunk arrived. Returns the string to write to the term NOW, or null if
   * it was buffered (feed not yet attached). `seq` is the per-session chunk sequence from main.
   */
  live(seq, data) {
    if (this._ready) return data;
    this._pending.push({ seq, data });
    return null;
  }

  /**
   * Scrollback resolved: `text` is the byte-exact snapshot, `baseSeq` the seq of the last chunk
   * included in it. Returns the ordered list of strings to write (scrollback, then buffered
   * chunks newer than the snapshot) and marks the feed ready. Idempotent-safe: a second attach
   * after ready is a no-op returning [].
   */
  attach(text, baseSeq) {
    if (this._ready) return [];
    const base = Number.isFinite(baseSeq) ? baseSeq : -1;
    const writes = [];
    if (text) writes.push(text);
    const fresh = this._pending
      .filter((p) => p.seq > base)
      .sort((a, b) => a.seq - b.seq);
    for (const p of fresh) writes.push(p.data);
    this._pending = [];
    this._ready = true;
    return writes;
  }

  /** Number of chunks currently buffered (diagnostic / test observability). */
  get pendingCount() {
    return this._pending.length;
  }
}

// UMD: usable both by the Node test suite (require) and the sandboxed renderer (window global,
// loaded via <script> — the renderer has no Node integration, TB-2 / invariant 29).
if (typeof module !== "undefined" && module.exports) module.exports = { PaneFeed };
if (typeof window !== "undefined") window.PaneFeed = PaneFeed;
})();
