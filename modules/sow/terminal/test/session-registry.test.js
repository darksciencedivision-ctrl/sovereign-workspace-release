"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { SessionRegistry } = require("../session/session-registry");

const reg = () => new SessionRegistry();

test("register requires a node binding (no naked sessions)", () => {
  assert.throws(() => reg().register("s1", {}), /no node binding/);
});

test("register then legal lifecycle SPAWNING -> RUNNING -> EXITED", () => {
  const r = reg();
  const s = r.register("s1", { nodeId: "n1", pid: 100 }, "t0");
  assert.strictEqual(s.state, "SPAWNING");
  r.transition("s1", "RUNNING", "t1");
  r.transition("s1", "EXITED", "t2", { exitCode: 0 });
  assert.strictEqual(r.get("s1").state, "EXITED");
  assert.ok(r.isTerminal("s1"));
});

test("duplicate register is refused", () => {
  const r = reg();
  r.register("s1", { nodeId: "n1" });
  assert.throws(() => r.register("s1", { nodeId: "n1" }), /duplicate session/);
});

test("illegal transition raises rather than silently correcting", () => {
  const r = reg();
  r.register("s1", { nodeId: "n1" });
  r.transition("s1", "RUNNING");
  r.transition("s1", "EXITED");
  assert.throws(() => r.transition("s1", "RUNNING"), /illegal transition EXITED -> RUNNING/);
});

test("REFUSED is reachable from SPAWNING and is terminal", () => {
  const r = reg();
  r.register("s1", { nodeId: "n1" });
  r.transition("s1", "REFUSED", null, { reason: "not admitted" });
  assert.strictEqual(r.get("s1").state, "REFUSED");
  assert.throws(() => r.transition("s1", "RUNNING"), /illegal transition/);
});

test("detach/reattach returns byte-exact scrollback, PTY state untouched", () => {
  const r = reg();
  r.register("s1", { nodeId: "n1" });
  r.transition("s1", "RUNNING");
  r.feed("s1", "line-1\n");
  r.feed("s1", Buffer.from("line-2\n"));
  assert.strictEqual(r.detach("s1"), "RUNNING");
  assert.strictEqual(r.get("s1").attached, false);
  const replay = r.reattach("s1");
  assert.strictEqual(replay.toString("utf8"), "line-1\nline-2\n");
  assert.strictEqual(r.get("s1").attached, true);
  assert.strictEqual(r.get("s1").state, "RUNNING"); // reattach never restarts the PTY
});

test("event log is append-only, ordered, and records every transition", () => {
  const r = reg();
  r.register("s1", { nodeId: "n1", pid: 5 }, "t0");
  r.transition("s1", "RUNNING", "t1");
  r.transition("s1", "KILLED", "t2");
  const log = r.eventLog();
  assert.deepStrictEqual(log.map((e) => e.seq), [0, 1, 2]);
  assert.deepStrictEqual(log.map((e) => e.to), ["SPAWNING", "RUNNING", "KILLED"]);
  // returned log is a copy: mutating it does not affect the registry's record
  log.push({ seq: 99 });
  assert.strictEqual(r.eventLog().length, 3);
});

test("alive() and teardownOrder() reflect only live sessions", () => {
  const r = reg();
  r.register("a", { nodeId: "n" }); r.transition("a", "RUNNING");
  r.register("b", { nodeId: "n" }); r.transition("b", "RUNNING"); r.transition("b", "EXITED");
  r.register("c", { nodeId: "n" }); // SPAWNING counts as alive
  assert.deepStrictEqual(r.alive().map((s) => s.id).sort(), ["a", "c"]);
  assert.deepStrictEqual(r.teardownOrder().sort(), ["a", "c"]);
});

test("a TERMINAL session can be forgotten so its pane id is reusable; a live one cannot", () => {
  const r = new SessionRegistry();
  r.register("pane-1", { nodeId: "n" }, "t0");
  r.transition("pane-1", "RUNNING", "t1", {});
  assert.throws(() => r.forget("pane-1"), /refusing to forget a live session/);
  r.transition("pane-1", "EXITED", "t2", {});
  r.forget("pane-1");
  assert.equal(r.has("pane-1"), false);
  // the append-only lifecycle log keeps the session that ended (invariant 12)
  const log = r.eventLog();
  assert.ok(log.some((e) => e.id === "pane-1" && e.to === "EXITED"));
  // the id is reusable for the relaunched session
  r.register("pane-1", { nodeId: "n" }, "t3");
  assert.equal(r.has("pane-1"), true);
});

// ---- W-63: the lifecycle log must be BOUNDED, and a live session must survive eviction ----

const churn = (r, n, prefix) => {
  for (let i = 0; i < n; i++) {
    const id = prefix + i;
    r.register(id, { nodeId: "n-" + id, pid: 1000 + i });
    r.transition(id, "RUNNING");
    r.transition(id, "EXITED", null, { exitCode: 0 });
    r.forget(id);
  }
};

test("W-63 NEGATIVE: the retained log is bounded and dead sessions' history evicts", () => {
  const r = new SessionRegistry({ maxLogEvents: 8 });
  churn(r, 40, "pane-");
  const kept = r.eventLog();
  assert.ok(kept.length <= 8, "retained " + kept.length + " rows for a window of 8");
  assert.equal(kept.some((e) => e.id === "pane-0"), false,
    "the oldest forgotten session's events must have been evicted");
});

test("W-63 CONTROL: a live session survives eviction with register and latest state", () => {
  const r = new SessionRegistry({ maxLogEvents: 8 });
  r.register("long-lived", { nodeId: "nX", pid: 7 }, "t0");
  r.transition("long-lived", "RUNNING", "t1");
  churn(r, 40, "other-");
  const rows = r.eventLog().filter((e) => e.id === "long-lived").map((e) => e.kind);
  assert.deepEqual(rows, ["register", "transition"],
    "an interrupted-at-cut session must stay reconstructable: register + latest, always retained");
  const last = r.eventLog().filter((e) => e.id === "long-lived").pop();
  assert.equal(last.to, "RUNNING");
});
