"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { RingBuffer } = require("../lib/ring-buffer");

test("byte-exact replay under capacity", () => {
  const b = new RingBuffer(1024);
  b.push("hello "); b.push(Buffer.from("world"));
  assert.equal(b.snapshot().toString(), "hello world");
});
test("overflow trims oldest, keeps newest, never exceeds capacity", () => {
  const b = new RingBuffer(10);
  b.push("aaaaa"); b.push("bbbbb"); b.push("cc");
  const s = b.snapshot().toString();
  assert.ok(s.length <= 10);
  assert.ok(s.endsWith("cc"));
  assert.ok(!s.includes("aaaaa"));
});
test("single oversized chunk keeps its tail", () => {
  const b = new RingBuffer(4);
  b.push("abcdefgh");
  assert.equal(b.snapshot().toString(), "efgh");
});
