"use strict";
/**
 * Per-session scrollback ring buffer (product code, terminal/).
 *
 * Byte-exact replay on reattach is the property that makes a pane a VIEW over a session
 * rather than the session itself: detaching a view and reattaching it must reproduce the
 * exact bytes the PTY emitted, so the PTY's lifetime is independent of any window (Plan
 * §10, invariant 27 "the orchestra is visible" — a pane can always be re-shown losslessly).
 *
 * Bounded (default 256 KB) so a runaway stream cannot grow memory without limit; the oldest
 * bytes are dropped first, matching a terminal scrollback.
 *
 * Phase 17C `.close-revalidate`: the buffer also keeps a MONOTONIC stream position
 * (`totalWritten` — every byte the PTY ever emitted, whether or not it is still held). Both
 * mandatory reviews found the same BLOCKING defect in the voice submit gate built on top of a
 * `snapshot().length` offset: that offset is an index into a buffer whose ORIGIN MOVES, so one
 * front-chunk eviction silently turned "what the pane emitted after my write" into "the whole
 * scrollback" — and an earlier echo of the same sentence could then authorise a keystroke into a
 * live model session. `sliceFrom()` is the fail-closed replacement: it answers with the appended
 * region or with NULL, and never with a wider window than it was asked for.
 */
class RingBuffer {
  constructor(capacity = 256 * 1024) {
    if (!(capacity > 0)) throw new Error("ring buffer capacity must be > 0");
    this.capacity = capacity;
    this.chunks = [];
    this.size = 0;
    //: Every byte ever pushed. Never decreases, never resets — a position taken from it stays
    //: comparable across trims and across `clear()`.
    this.totalWritten = 0;
  }

  /** How many of the emitted bytes are no longer held (trimmed from the front, or cleared). */
  get dropped() {
    return this.totalWritten - this.size;
  }

  /**
   * The bytes emitted since stream position `from`, or NULL when that cannot be answered exactly:
   * `from` predates what is still held (the region was trimmed) or points past the stream (a stale
   * or fabricated position). A caller asking "did the pane echo what I just wrote" must be able to
   * tell "it did not" from "I can no longer see" — returning a wider window conflates them, and
   * that is exactly how the submit gate came to be satisfiable by an older echo.
   */
  sliceFrom(from) {
    if (!Number.isInteger(from) || from < 0) return null;
    if (from > this.totalWritten) return null;      // ahead of the stream — not answerable
    if (from < this.dropped) return null;           // trimmed away — not answerable
    return this.snapshot().subarray(from - this.dropped);
  }

  push(data) {
    const buf = Buffer.isBuffer(data) ? data : Buffer.from(data, "utf8");
    if (buf.length === 0) return;
    this.chunks.push(buf);
    this.size += buf.length;
    this.totalWritten += buf.length;
    while (this.size > this.capacity && this.chunks.length > 1) {
      this.size -= this.chunks.shift().length;
    }
    if (this.size > this.capacity) {
      // a single oversized chunk: keep only the trailing `capacity` bytes
      const only = this.chunks[0];
      this.chunks[0] = only.subarray(only.length - this.capacity);
      this.size = this.capacity;
    }
  }

  snapshot() {
    return Buffer.concat(this.chunks, this.size);
  }

  /**
   * Drop the held bytes. `totalWritten` is deliberately NOT reset: a position taken before a clear
   * must fail closed afterwards (`sliceFrom` sees `from < dropped`), never silently re-point into a
   * fresh stream.
   */
  clear() {
    this.chunks = [];
    this.size = 0;
  }
}

module.exports = { RingBuffer };
