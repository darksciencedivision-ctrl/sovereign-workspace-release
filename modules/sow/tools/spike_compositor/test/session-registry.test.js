"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { SessionRegistry } = require("../lib/session-registry");

test("legal lifecycle only", () => {
  const r = new SessionRegistry();
  r.register("s1"); r.transition("s1", "RUNNING"); r.transition("s1", "EXITED");
  assert.throws(() => r.transition("s1", "RUNNING"), /illegal transition/);
});
test("duplicate registration refused", () => {
  const r = new SessionRegistry();
  r.register("s1");
  assert.throws(() => r.register("s1"), /duplicate/);
});
test("detach/reattach replays byte-exact scrollback and never mutates state", () => {
  const r = new SessionRegistry();
  r.register("s1"); r.transition("s1", "RUNNING");
  r.feed("s1", "line1\n"); 
  const stateBefore = r.get("s1").state;
  r.detach("s1");
  r.feed("s1", "line2\n"); // session keeps producing while detached
  const replay = r.reattach("s1").toString();
  assert.equal(replay, "line1\nline2\n");
  assert.equal(r.get("s1").state, stateBefore);
});
test("teardown order covers exactly the live sessions (no orphans)", () => {
  const r = new SessionRegistry();
  r.register("a"); r.transition("a", "RUNNING");
  r.register("b"); r.transition("b", "RUNNING"); r.transition("b", "KILLED");
  r.register("c");
  assert.deepEqual(r.teardownOrder().sort(), ["a", "c"]);
});
