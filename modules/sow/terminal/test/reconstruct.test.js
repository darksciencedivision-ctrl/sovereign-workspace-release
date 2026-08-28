"use strict";
/**
 * Session-state reconstruction (pure) — rebuild last-known pane/session state from the
 * append-only lifecycle log after a shell/control-plane process restart (directive §9 track 14A).
 *
 * The append-only SessionRegistry log (invariant 12) is the authoritative record. When the shell
 * process dies, every ConPTY it owned dies with it, but the log persists what existed and its
 * last state. Reconstruction folds that log into an ordered view for the UI — and, load-bearing,
 * marks sessions that were still alive at the cut as INTERRUPTED and NOT auto-recoverable:
 * fail-closed, a naked session is never silently re-spawned (invariant 2); the operator relaunches
 * it under supervision.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { SessionRegistry } = require("../session/session-registry");
const { reconstructSessions, interruptedSessions } = require("../recovery/reconstruct");

// Build a registry, drive a lifecycle, and hand back its append-only log (what a restart reads).
function logFrom(build) {
  const reg = new SessionRegistry();
  let t = 0;
  const ts = () => `t${t++}`;
  build(reg, ts);
  return reg.eventLog();
}

test("an empty log reconstructs to nothing", () => {
  assert.deepStrictEqual(reconstructSessions([]), []);
  assert.deepStrictEqual(interruptedSessions([]), []);
});

test("a cleanly EXITED session is reconstructed as terminal history, not recoverable", () => {
  const log = logFrom((reg, ts) => {
    reg.register("s1", { nodeId: "n1", pid: 10 }, ts());
    reg.transition("s1", "RUNNING", ts(), { pid: 10 });
    reg.transition("s1", "EXITED", ts(), { exitCode: 0 });
  });
  const [s] = reconstructSessions(log);
  assert.strictEqual(s.id, "s1");
  assert.strictEqual(s.nodeId, "n1");
  assert.strictEqual(s.pid, 10);
  assert.strictEqual(s.lastState, "EXITED");
  assert.strictEqual(s.terminal, true);
  assert.strictEqual(s.disposition, "exited");
  assert.strictEqual(s.recoverable, false);
});

test("a session still RUNNING at the cut is INTERRUPTED and never auto-recoverable (fail-closed)", () => {
  const log = logFrom((reg, ts) => {
    reg.register("s1", { nodeId: "n1", pid: 10 }, ts());
    reg.transition("s1", "RUNNING", ts(), { pid: 10 });
    // no terminal event: the process died with the shell
  });
  const [s] = reconstructSessions(log);
  assert.strictEqual(s.lastState, "RUNNING");
  assert.strictEqual(s.terminal, false);
  assert.strictEqual(s.disposition, "interrupted");
  assert.strictEqual(s.recoverable, false, "no naked re-spawn — operator relaunches under supervision (invariant 2)");
  assert.strictEqual(s.needsRelaunch, true);
});

test("a session still SPAWNING at the cut is also INTERRUPTED (never admitted, still not naked)", () => {
  const log = logFrom((reg, ts) => {
    reg.register("s1", { nodeId: "n1", pid: 11 }, ts());
    // died mid-spawn, before RUNNING
  });
  const [s] = reconstructSessions(log);
  assert.strictEqual(s.lastState, "SPAWNING");
  assert.strictEqual(s.disposition, "interrupted");
  assert.strictEqual(s.needsRelaunch, true);
});

test("a REFUSED session reconstructs as refused history (governance denial), not recoverable", () => {
  const log = logFrom((reg, ts) => {
    reg.register("s1", { nodeId: "n1", pid: 12 }, ts());
    reg.transition("s1", "REFUSED", ts(), { reason: "no verified control-plane channel" });
  });
  const [s] = reconstructSessions(log);
  assert.strictEqual(s.lastState, "REFUSED");
  assert.strictEqual(s.disposition, "refused");
  assert.strictEqual(s.terminal, true);
  assert.strictEqual(s.needsRelaunch, false);
});

test("reconstruction preserves registration order and separates interrupted from history", () => {
  const log = logFrom((reg, ts) => {
    reg.register("a", { nodeId: "n1", pid: 1 }, ts());
    reg.transition("a", "RUNNING", ts(), {});
    reg.transition("a", "EXITED", ts(), { exitCode: 0 });
    reg.register("b", { nodeId: "n2", pid: 2 }, ts());
    reg.transition("b", "RUNNING", ts(), {});
    reg.register("c", { nodeId: "n3", pid: 3 }, ts());
    reg.transition("c", "KILLED", ts(), {});
  });
  const all = reconstructSessions(log);
  assert.deepStrictEqual(all.map((s) => s.id), ["a", "b", "c"]);
  const interrupted = interruptedSessions(log);
  assert.deepStrictEqual(interrupted.map((s) => s.id), ["b"], "only the still-alive session needs supervised relaunch");
});

test("reconstruction is deterministic and does not mutate the input log", () => {
  const log = logFrom((reg, ts) => {
    reg.register("a", { nodeId: "n1", pid: 1 }, ts());
    reg.transition("a", "RUNNING", ts(), {});
  });
  const before = JSON.stringify(log);
  const r1 = reconstructSessions(log);
  const r2 = reconstructSessions(log);
  assert.deepStrictEqual(r1, r2);
  assert.strictEqual(JSON.stringify(log), before, "the append-only log is read, never written");
});

test("a round-trip through a fresh registry proves cross-restart reconstruction", () => {
  // Emulate: shell #1 runs a lifecycle, its log is persisted; shell #2 boots and folds that log.
  const log = logFrom((reg, ts) => {
    reg.register("p1", { nodeId: "shell", pid: 100 }, ts());
    reg.transition("p1", "RUNNING", ts(), {});
    reg.register("p2", { nodeId: "shell", pid: 101 }, ts());
    reg.transition("p2", "RUNNING", ts(), {});
    reg.transition("p2", "EXITED", ts(), { exitCode: 0 });
  });
  const restored = reconstructSessions(JSON.parse(JSON.stringify(log))); // survives serialization
  assert.strictEqual(restored.length, 2);
  assert.strictEqual(restored.find((s) => s.id === "p1").needsRelaunch, true);
  assert.strictEqual(restored.find((s) => s.id === "p2").needsRelaunch, false);
});
