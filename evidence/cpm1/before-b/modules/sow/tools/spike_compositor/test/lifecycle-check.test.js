"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { lifecycleCheck } = require("../lib/lifecycle-check");

const ev = (kind, id) => ({ ts: "t", kind, detail: { id } });

test("all sessions accounted for -> ok", () => {
  const events = [ev("spawn", "a"), ev("spawn", "b"), ev("exit", "a"), ev("kill", "b")];
  const sessions = [{ id: "a", state: "EXITED" }, { id: "b", state: "KILLED" }];
  const r = lifecycleCheck(events, sessions);
  assert.equal(r.ok, true);
  assert.equal(r.checked, 2);
});

test("missing spawn event flagged", () => {
  const r = lifecycleCheck([ev("exit", "a")], [{ id: "a", state: "EXITED" }]);
  assert.equal(r.ok, false);
  assert.deepEqual(r.missing[0], { id: "a", problem: "no spawn event" });
});

test("still RUNNING after teardown flagged", () => {
  const r = lifecycleCheck([ev("spawn", "a")], [{ id: "a", state: "RUNNING" }]);
  assert.equal(r.ok, false);
  assert.match(r.missing[0].problem, /still RUNNING/);
});

test("KILLED without kill event flagged; kill-on-quit accepted", () => {
  const bad = lifecycleCheck([ev("spawn", "a")], [{ id: "a", state: "KILLED" }]);
  assert.equal(bad.ok, false);
  const good = lifecycleCheck([ev("spawn", "a"), ev("kill-on-quit", "a")], [{ id: "a", state: "KILLED" }]);
  assert.equal(good.ok, true);
});

test("KILLED whose process exited (exit event) also accepted", () => {
  const r = lifecycleCheck([ev("spawn", "a"), ev("exit", "a")], [{ id: "a", state: "KILLED" }]);
  assert.equal(r.ok, true);
});
