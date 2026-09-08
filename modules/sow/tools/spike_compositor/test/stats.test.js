"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { latencyStats, percentile } = require("../lib/stats");

test("percentiles on known distribution", () => {
  const s = latencyStats([...Array(100).keys()].map((i) => i + 1)); // 1..100
  assert.equal(s.p50, 50); assert.equal(s.p95, 95); assert.equal(s.p99, 99);
  assert.equal(s.min, 1); assert.equal(s.max, 100); assert.equal(s.n, 100);
});
test("small-N does not overflow", () => {
  const s = latencyStats([7]);
  assert.equal(s.p95, 7); assert.equal(s.p50, 7); assert.equal(s.n, 1);
});
test("empty + timeouts are explicit, never silent", () => {
  const s = latencyStats([], 5);
  assert.equal(s.n, 0); assert.equal(s.timeouts, 5); assert.equal(s.p95, null);
});
test("percentile never reads past the array", () => {
  assert.equal(percentile([1, 2], 99), 2);
});
