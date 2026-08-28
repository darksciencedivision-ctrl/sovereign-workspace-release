"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { RingBuffer } = require("../session/ring-buffer");

test("byte-exact replay of pushed data", () => {
  const rb = new RingBuffer(1024);
  rb.push("hello ");
  rb.push(Buffer.from("world"));
  assert.strictEqual(rb.snapshot().toString("utf8"), "hello world");
});

test("empty pushes are no-ops", () => {
  const rb = new RingBuffer(16);
  rb.push("");
  rb.push(Buffer.alloc(0));
  assert.strictEqual(rb.size, 0);
  assert.strictEqual(rb.snapshot().length, 0);
});

test("oldest chunks evicted when over capacity", () => {
  const rb = new RingBuffer(10);
  rb.push("aaaaa"); // 5
  rb.push("bbbbb"); // 10 -> at cap
  rb.push("ccccc"); // 15 -> evict first chunk
  assert.strictEqual(rb.snapshot().toString("utf8"), "bbbbbccccc");
  assert.ok(rb.size <= rb.capacity);
});

test("single oversized chunk is trimmed to trailing capacity bytes", () => {
  const rb = new RingBuffer(4);
  rb.push("abcdefgh");
  assert.strictEqual(rb.snapshot().toString("utf8"), "efgh");
  assert.strictEqual(rb.size, 4);
});

test("capacity must be positive", () => {
  assert.throws(() => new RingBuffer(0), /capacity must be > 0/);
  assert.throws(() => new RingBuffer(-1), /capacity must be > 0/);
});

test("clear resets the buffer", () => {
  const rb = new RingBuffer(64);
  rb.push("data");
  rb.clear();
  assert.strictEqual(rb.snapshot().length, 0);
});

// ---- Phase 17C `.close-revalidate`: the stream position + the fail-closed window ----
// Both mandatory reviews found the same BLOCKING defect: the voice submit gate bounded its echo
// search with `snapshot().length`, an index into a buffer whose origin moves. These pin the
// replacement — the position is monotonic, and a window that cannot be answered EXACTLY is null.

test("totalWritten counts every byte ever emitted, including trimmed ones", () => {
  const rb = new RingBuffer(10);
  rb.push("aaaaa");
  rb.push("bbbbb");
  rb.push("ccccc");
  assert.strictEqual(rb.totalWritten, 15);
  assert.strictEqual(rb.size, 10);
  assert.strictEqual(rb.dropped, 5);
});

test("sliceFrom returns exactly the bytes appended after a position", () => {
  const rb = new RingBuffer(1024);
  rb.push("banner\r\n");
  const at = rb.totalWritten;
  rb.push("what is 31 plus 32");
  assert.strictEqual(rb.sliceFrom(at).toString("utf8"), "what is 31 plus 32");
  assert.strictEqual(rb.sliceFrom(rb.totalWritten).length, 0); // nothing new yet — not "everything"
});

test("sliceFrom is null once the appended region has been trimmed — never a wider window", () => {
  const rb = new RingBuffer(10);
  rb.push("what is 3"); // the utterance the caller wants confirmed
  const at = rb.totalWritten - 9;
  rb.push("xxxxxxxxxx"); // one eviction: the region the caller asked about is gone
  assert.strictEqual(rb.sliceFrom(at), null);
  // the older bytes are genuinely no longer available — the caller must fail closed, not fall back
  assert.ok(!rb.snapshot().toString("utf8").includes("what is 3"));
});

test("sliceFrom rejects positions ahead of the stream and malformed ones", () => {
  const rb = new RingBuffer(64);
  rb.push("abc");
  assert.strictEqual(rb.sliceFrom(4), null);
  assert.strictEqual(rb.sliceFrom(-1), null);
  assert.strictEqual(rb.sliceFrom(1.5), null);
  assert.strictEqual(rb.sliceFrom(null), null);
});

test("clear() does not rewind the stream: earlier positions fail closed, later ones stay exact", () => {
  const rb = new RingBuffer(64);
  rb.push("hello");
  const before = 2;                       // inside the bytes clear() is about to throw away
  const at = rb.totalWritten;             // the position clear() leaves as the new origin
  rb.clear();
  rb.push("hello");                       // the same bytes again, in a fresh screen
  assert.strictEqual(rb.sliceFrom(before), null, "a discarded region is never answered with newer bytes");
  assert.strictEqual(rb.sliceFrom(at).toString("utf8"), "hello");
});

test("an oversized single chunk still accounts for what it dropped", () => {
  const rb = new RingBuffer(4);
  const at = rb.totalWritten;
  rb.push("abcdefgh");
  assert.strictEqual(rb.totalWritten, 8);
  assert.strictEqual(rb.dropped, 4);
  assert.strictEqual(rb.sliceFrom(at), null);
  assert.strictEqual(rb.sliceFrom(4).toString("utf8"), "efgh");
});
