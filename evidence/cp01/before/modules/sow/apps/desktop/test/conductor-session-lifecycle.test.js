"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  advanceConductorSessionLifecycle,
} = require("../voice/conductor-session-lifecycle");

const running = {
  state: "running",
  sessionId: "conductor-session",
  sessionGeneration: 7,
  pid: 31337,
  leaseId: "lease-1",
  reason: null,
};

test("a kill request keeps the conductor restricted and its lease held until PTY exit", () => {
  const result = advanceConductorSessionLifecycle(running, {
    kind: "kill",
    id: "pane-1",
    generation: 7,
    pid: 31337,
    processExited: false,
  }, "pane-1", "2026-07-28T00:00:00.000Z");

  assert.equal(result.action, "await_process_exit");
  assert.equal(result.releaseAuthority, false);
  assert.equal(result.releaseLease, false);
  assert.equal(result.launch.state, "terminating");
  assert.equal(result.launch.leaseId, "lease-1");
});

test("only confirmed PTY exit releases voice authority and the durable lease", () => {
  const terminating = advanceConductorSessionLifecycle(running, {
    kind: "kill",
    id: "pane-1",
    generation: 7,
    pid: 31337,
    processExited: false,
  }, "pane-1", "2026-07-28T00:00:00.000Z").launch;

  const result = advanceConductorSessionLifecycle(terminating, {
    kind: "exit",
    id: "pane-1",
    generation: 7,
    pid: 31337,
    processExited: true,
    exitCode: 1,
  }, "pane-1", "2026-07-28T00:00:01.000Z");

  assert.equal(result.action, "process_exited");
  assert.equal(result.releaseAuthority, true);
  assert.equal(result.releaseLease, true);
  assert.equal(result.launch.state, "release_pending");
  assert.equal(result.launch.leaseId, "lease-1",
    "a transient release failure must remain retryable while Electron still owns the ledger row");
  assert.equal(result.launch.processExited, true);
  assert.equal(result.launch.exitCode, 1);
});

test("an unconfirmed exit-shaped event fails closed", () => {
  const result = advanceConductorSessionLifecycle(running, {
    kind: "exit",
    id: "pane-1",
    generation: 7,
    pid: 31337,
    processExited: false,
    exitCode: 0,
  }, "pane-1", "2026-07-28T00:00:01.000Z");

  assert.equal(result.action, "ignore");
  assert.equal(result.releaseAuthority, false);
  assert.equal(result.releaseLease, false);
  assert.equal(result.launch.state, "running");
});

test("an exit for an older pane generation cannot release replacement authority or lease", () => {
  const result = advanceConductorSessionLifecycle(running, {
    kind: "exit",
    id: "pane-1",
    generation: 6,
    pid: 30000,
    processExited: true,
    exitCode: 0,
  }, "pane-1", "2026-07-28T00:00:01.000Z");

  assert.equal(result.action, "ignore");
  assert.equal(result.releaseAuthority, false);
  assert.equal(result.releaseLease, false);
  assert.equal(result.launch.state, "running");
  assert.equal(result.launch.leaseId, "lease-1");
});

test("an exit with the right pane and generation but wrong pid fails closed", () => {
  const result = advanceConductorSessionLifecycle(running, {
    kind: "exit",
    id: "pane-1",
    generation: 7,
    pid: 99999,
    processExited: true,
    exitCode: 0,
  }, "pane-1", "2026-07-28T00:00:01.000Z");

  assert.equal(result.action, "ignore");
  assert.equal(result.releaseAuthority, false);
  assert.equal(result.releaseLease, false);
});
