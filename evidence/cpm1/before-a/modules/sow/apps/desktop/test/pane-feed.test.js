"use strict";
/**
 * PaneFeed unit tests (Phase 16A) — the race-free scrollback/live merge that fixes the blank-pane
 * defect. Covers the load-bearing seq-boundary invariant: no gap, no duplication, correct order.
 */
const test = require("node:test");
const assert = require("node:assert");
const { PaneFeed } = require("../renderer/pane-feed.js");

test("live chunks before attach are buffered, not written", () => {
  const f = new PaneFeed();
  assert.strictEqual(f.ready, false);
  assert.strictEqual(f.live(0, "a"), null);
  assert.strictEqual(f.live(1, "b"), null);
  assert.strictEqual(f.pendingCount, 2);
});

test("attach replays scrollback first, then only chunks newer than the snapshot boundary", () => {
  const f = new PaneFeed();
  // chunks 0,1 arrived and were folded into scrollback (baseSeq=1); chunk 2 arrived after.
  f.live(0, "banner\r\n"); // already in the snapshot
  f.live(1, "prompt> ");   // already in the snapshot
  f.live(2, "live-after"); // NOT in the snapshot
  const writes = f.attach("banner\r\nprompt> ", 1);
  assert.deepStrictEqual(writes, ["banner\r\nprompt> ", "live-after"]);
  assert.strictEqual(f.ready, true);
  assert.strictEqual(f.pendingCount, 0);
});

test("no duplication: a chunk at exactly baseSeq is treated as already-in-snapshot", () => {
  const f = new PaneFeed();
  f.live(5, "X");
  const writes = f.attach("...X", 5); // boundary chunk 5 is included in scrollback
  assert.deepStrictEqual(writes, ["...X"]); // NOT ["...X", "X"]
});

test("buffered chunks are flushed in seq order regardless of arrival order", () => {
  const f = new PaneFeed();
  f.live(3, "c");
  f.live(1, "a"); // out-of-order arrival
  f.live(2, "b");
  const writes = f.attach("", 0);
  assert.deepStrictEqual(writes, ["a", "b", "c"]);
});

test("after attach, live chunks pass straight through (ready)", () => {
  const f = new PaneFeed();
  f.attach("scroll", -1);
  assert.strictEqual(f.ready, true);
  assert.strictEqual(f.live(10, "next"), "next"); // written immediately
});

test("empty scrollback yields no leading write", () => {
  const f = new PaneFeed();
  f.live(0, "z");
  const writes = f.attach("", -1);
  assert.deepStrictEqual(writes, ["z"]);
});

test("attach with no session (missing scrollback) still flushes buffered live chunks", () => {
  // main returns {text:"", seq:-1} when the pane has no registered session (e.g. a pane whose
  // session only just spawned); the feed must still flush what it buffered.
  const f = new PaneFeed();
  f.live(0, "hello");
  const writes = f.attach("", -1);
  assert.deepStrictEqual(writes, ["hello"]);
});

test("second attach after ready is a no-op", () => {
  const f = new PaneFeed();
  f.attach("a", -1);
  const again = f.attach("b", 100);
  assert.deepStrictEqual(again, []);
});
