"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { SeqChecker } = require("../lib/seq-check");

test("contiguous stream: zero gaps", () => {
  const c = new SeqChecker();
  c.feed("SEQ:1:x\nSEQ:2:x\nSEQ:3:x\n");
  assert.deepEqual(c.report().gaps, 0);
  assert.equal(c.report().received, 3);
});
test("gap counted exactly", () => {
  const c = new SeqChecker();
  c.feed("SEQ:1:x\nSEQ:5:x\n"); // 2,3,4 missing
  assert.equal(c.report().gaps, 3);
});
test("chunk-boundary split lines are not lost or double-counted", () => {
  const c = new SeqChecker();
  c.feed("SEQ:1:x\nSE"); c.feed("Q:2:x\nSEQ:3"); c.feed(":x\n");
  const r = c.report();
  assert.equal(r.received, 3); assert.equal(r.gaps, 0);
});
test("duplicates and restarts distinguished from gaps", () => {
  const c = new SeqChecker();
  c.feed("SEQ:10:x\nSEQ:10:x\nSEQ:1:x\nSEQ:2:x\n");
  const r = c.report();
  assert.equal(r.dupes, 1); assert.equal(r.restarts, 1); assert.equal(r.gaps, 0);
});
test("CRLF (ConPTY) handled", () => {
  const c = new SeqChecker();
  c.feed("SEQ:1:x\r\nSEQ:2:x\r\n");
  assert.equal(c.report().received, 2);
});
