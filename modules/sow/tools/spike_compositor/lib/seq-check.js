"use strict";
/** Sequence-gap detector for the 1 MB/s streamer. Any gap = dropped output (kill criterion). */
class SeqChecker {
  constructor() { this.last = null; this.gaps = 0; this.dupes = 0; this.restarts = 0; this.received = 0; this._tail = ""; }
  /** Feed raw terminal data; extracts SEQ:<n>: lines across chunk boundaries. */
  feed(chunk) {
    const text = this._tail + chunk;
    const lines = text.split(/\r?\n/);
    this._tail = lines.pop() ?? "";
    for (const line of lines) {
      const m = /SEQ:(\d+):/.exec(line);
      if (!m) continue;
      const n = Number(m[1]);
      this.received++;
      if (this.last === null) { this.last = n; continue; }
      if (n === this.last + 1) this.last = n;
      else if (n <= this.last) { if (n === this.last) this.dupes++; else this.restarts++; this.last = n; }
      else { this.gaps += n - this.last - 1; this.last = n; }
    }
  }
  report() { return { received: this.received, gaps: this.gaps, dupes: this.dupes, restarts: this.restarts, last: this.last }; }
}
module.exports = { SeqChecker };
