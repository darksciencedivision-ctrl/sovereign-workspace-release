"use strict";
/** Per-session scrollback ring buffer (default 200 KB). Byte-exact replay on reattach. */
class RingBuffer {
  constructor(capacity = 200 * 1024) { this.capacity = capacity; this.chunks = []; this.size = 0; }
  push(data) {
    const buf = Buffer.isBuffer(data) ? data : Buffer.from(data, "utf8");
    this.chunks.push(buf); this.size += buf.length;
    while (this.size > this.capacity && this.chunks.length > 1) this.size -= this.chunks.shift().length;
    if (this.size > this.capacity) { // single oversized chunk: trim head
      const only = this.chunks[0]; this.chunks[0] = only.subarray(only.length - this.capacity); this.size = this.capacity;
    }
  }
  snapshot() { return Buffer.concat(this.chunks, this.size); }
}
module.exports = { RingBuffer };
