"use strict";
/**
 * Recovery state machine (pure) — the observable supervision lifecycle across a
 * control-plane/process restart (directive §9 track 14A: "UI recovery after process restart").
 *
 * The shell must fail closed during the gap (no naked sessions), tear sessions down on loss,
 * and re-admit ONLY on a re-verified channel. This machine formalizes what was an implicit
 * boolean into an explicit, testable, observable state chain (invariant 27) with a monotonic
 * supervision "epoch" so the UI can tell a freshly re-established channel from the original.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { RecoveryMachine } = require("../recovery/recovery-machine");

let clock = 0;
const now = () => `t${clock++}`;
const mk = (opts = {}) => new RecoveryMachine({ now, ...opts });

test("starts INIT — fail-closed: never supervised, admission shut, epoch 0", () => {
  const m = mk();
  assert.strictEqual(m.state, "INIT");
  assert.strictEqual(m.admissionOpen, false);
  assert.strictEqual(m.epoch, 0);
});

test("first verified probe establishes supervision and opens admission (epoch -> 1)", () => {
  const m = mk();
  const t = m.observe(true);
  assert.strictEqual(m.state, "SUPERVISED");
  assert.strictEqual(m.admissionOpen, true);
  assert.strictEqual(m.epoch, 1);
  assert.strictEqual(t.reason, "established");
});

test("a failed probe before ever supervising stays INIT (admission never opens)", () => {
  const m = mk();
  assert.strictEqual(m.observe(false), null);
  assert.strictEqual(m.state, "INIT");
  assert.strictEqual(m.admissionOpen, false);
  assert.strictEqual(m.epoch, 0);
});

test("healthy heartbeats while SUPERVISED emit no transition (idempotent ok)", () => {
  const m = mk();
  m.observe(true);
  assert.strictEqual(m.observe(true), null);
  assert.strictEqual(m.observe(true), null);
  assert.strictEqual(m.state, "SUPERVISED");
  assert.strictEqual(m.epoch, 1);
});

test("losing the channel goes DEGRADED, shuts admission, and flags teardown exactly once", () => {
  const m = mk();
  m.observe(true);
  const t = m.observe(false);
  assert.strictEqual(m.state, "DEGRADED");
  assert.strictEqual(m.admissionOpen, false, "no session may be admitted during the gap");
  assert.strictEqual(t.reason, "lost");
  assert.strictEqual(t.teardown, true, "sessions must be torn down on the loss edge");
});

test("staying down moves DEGRADED -> RECOVERING and then holds (admission stays shut)", () => {
  const m = mk();
  m.observe(true);
  m.observe(false); // -> DEGRADED
  const t = m.observe(false); // -> RECOVERING
  assert.strictEqual(m.state, "RECOVERING");
  assert.strictEqual(t.reason, "recovering");
  assert.strictEqual(t.teardown, undefined, "teardown fires only on the loss edge, not on retries");
  const t2 = m.observe(false); // hold
  assert.strictEqual(t2, null);
  assert.strictEqual(m.state, "RECOVERING");
  assert.strictEqual(m.admissionOpen, false);
});

test("re-verifying the channel restores supervision and bumps the epoch (re-admit only now)", () => {
  const m = mk();
  m.observe(true); // epoch 1
  m.observe(false); // DEGRADED
  m.observe(false); // RECOVERING
  const t = m.observe(true); // restored
  assert.strictEqual(m.state, "SUPERVISED");
  assert.strictEqual(m.admissionOpen, true);
  assert.strictEqual(m.epoch, 2, "a re-established channel is a new supervision generation");
  assert.strictEqual(t.reason, "restored");
  assert.strictEqual(t.epoch, 2);
});

test("restore straight from DEGRADED (a one-tick outage) still re-admits and bumps epoch", () => {
  const m = mk();
  m.observe(true);
  m.observe(false); // DEGRADED
  const t = m.observe(true); // restored directly
  assert.strictEqual(m.state, "SUPERVISED");
  assert.strictEqual(m.epoch, 2);
  assert.strictEqual(t.reason, "restored");
});

test("a full flap cycle is recorded append-only with timestamps and epochs", () => {
  const m = mk();
  m.observe(true);  // established
  m.observe(false); // lost
  m.observe(false); // recovering
  m.observe(true);  // restored
  const h = m.history();
  assert.deepStrictEqual(h.map((e) => e.reason), ["established", "lost", "recovering", "restored"]);
  assert.deepStrictEqual(h.map((e) => e.seq), [0, 1, 2, 3]);
  assert.deepStrictEqual(h.map((e) => e.to), ["SUPERVISED", "DEGRADED", "RECOVERING", "SUPERVISED"]);
  // every transition carries the injected timestamp and the epoch it left the machine in
  assert.ok(h.every((e) => typeof e.ts === "string"));
  assert.deepStrictEqual(h.map((e) => e.epoch), [1, 1, 1, 2]);
});

test("history() is a copy — the append-only record cannot be mutated by a caller", () => {
  const m = mk();
  m.observe(true);
  const h = m.history();
  h.push({ reason: "forged" });
  h[0].reason = "tampered";
  const again = m.history();
  assert.strictEqual(again.length, 1);
  assert.strictEqual(again[0].reason, "established");
});

test("onTransition fires for each state change with the transition object (observability)", () => {
  const seen = [];
  const m = mk({ onTransition: (t) => seen.push(t.reason) });
  m.observe(true);
  m.observe(true);  // no change -> no callback
  m.observe(false);
  m.observe(true);
  assert.deepStrictEqual(seen, ["established", "lost", "restored"]);
});

test("snapshot() exposes the current lifecycle for the renderer banner", () => {
  const m = mk();
  m.observe(true);
  m.observe(false);
  const s = m.snapshot();
  assert.strictEqual(s.state, "DEGRADED");
  assert.strictEqual(s.admissionOpen, false);
  assert.strictEqual(s.epoch, 1);
  assert.strictEqual(s.lastReason, "lost");
});
