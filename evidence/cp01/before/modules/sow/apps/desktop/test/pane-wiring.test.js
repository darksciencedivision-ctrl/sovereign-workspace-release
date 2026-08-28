"use strict";
/**
 * Phase 17B `.spawn-revalidate` — the worker-pane wiring rules that NOTHING could see.
 *
 * Every test here exists because a rule was fixed in `main.js`, reported FIXED, and left the whole
 * repo green when reverted (spec-audit MAJOR-2 / validator MINOR-2, 2026-07-26). Each one is written
 * to go RED when its own rule is deleted — that is the property being bought, not coverage.
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  endedWorkerChrome, createGovernedPaneSpawn, refuseSelection,
} = require("../picker/pane-wiring");

// ---- endedWorkerChrome: a dead pane stops claiming a live governed node -----------------------

const RUNNING_CHROME = Object.freeze({
  provider: "anthropic", adapter: "claude_code", locality: "frontier",
  model_label: "Fable 5", model_slug: "fable-5", model_verified: true,
  role: "reasoning", mode: "autonomous",
  node_state: "running", governed: true, pid: 4242, session_generation: 7,
  subscription: { allowance: 2, in_use: 1 }, residency: null,
});

test("a session that EXITED leaves a chrome that no longer claims a live governed node", () => {
  const ended = endedWorkerChrome(RUNNING_CHROME, {
    kind: "exit", processExited: true, pid: 4242, generation: 7, exitCode: 0,
  });
  assert.equal(ended.node_state, "session_exited");
  assert.equal(ended.governed, false);
  assert.equal(ended.pid, null);
  assert.match(ended.launch_reason, /session exited \(0\)/);
});

test("a KILL intent says terminating and stays governed until matching PTY exit", () => {
  const terminating = endedWorkerChrome(RUNNING_CHROME, {
    kind: "kill", processExited: false, pid: 4242, generation: 7,
  });
  assert.equal(terminating.node_state, "session_terminating");
  assert.equal(terminating.governed, true);
  assert.equal(terminating.pid, 4242);
  assert.equal(terminating.launch_reason, "session termination requested");

  const ended = endedWorkerChrome(terminating, {
    kind: "exit", processExited: true, pid: 4242, generation: 7, exitCode: 1,
  });
  assert.equal(ended.node_state, "session_exited");
  assert.equal(ended.governed, false);
  assert.equal(ended.pid, null);
});

test("the MODEL BADGE survives — the operator picked it and it is what the pane last ran", () => {
  const ended = endedWorkerChrome(RUNNING_CHROME, {
    kind: "exit", processExited: true, pid: 4242, generation: 7, exitCode: 3,
  });
  assert.equal(ended.model_label, "Fable 5");
  assert.equal(ended.model_slug, "fable-5");
  assert.equal(ended.role, "reasoning");
  assert.deepEqual(ended.subscription, { allowance: 2, in_use: 1 });
});

test("a chrome that never claimed a running session is NOT rewritten (no invented ending)", () => {
  const exit = { kind: "exit", processExited: true, pid: 4242, generation: 7 };
  assert.equal(endedWorkerChrome({ ...RUNNING_CHROME, node_state: "launch_refused" }, exit), null);
  assert.equal(endedWorkerChrome({ ...RUNNING_CHROME, node_state: "session_exited" }, exit), null);
  assert.equal(endedWorkerChrome(null, exit), null);
  assert.equal(endedWorkerChrome(undefined, exit), null);
});

test("a stale exit for an older process cannot darken a replacement pane", () => {
  assert.equal(endedWorkerChrome(RUNNING_CHROME, {
    kind: "exit", processExited: true, pid: 4000, generation: 6, exitCode: 0,
  }), null);
  assert.equal(endedWorkerChrome(RUNNING_CHROME, {
    kind: "exit", processExited: true, pid: 4242, generation: 6, exitCode: 0,
  }), null);
});

test("the input chrome is not mutated — the correction is a new object", () => {
  const live = { ...RUNNING_CHROME };
  endedWorkerChrome(live, {
    kind: "kill", processExited: false, pid: 4242, generation: 7,
  });
  assert.equal(live.node_state, "running");
  assert.equal(live.governed, true);
});

// ---- createGovernedPaneSpawn: a throw means NOTHING was born ----------------------------------

function fakeShell(overrides = {}) {
  const calls = { spawned: [], killed: [], persisted: 0, pushed: 0, laid: 0, logs: [] };
  const registry = { get: (id) => ({ id, pid: 9001, generation: 4 }) };
  const manager = {
    registry,
    spawn: (a) => { calls.spawned.push(a); return { id: a.id, pid: 9001, generation: 4 }; },
    kill: (id) => { calls.killed.push(id); },
    processIdentity: () => ({ pid: 9001, generation: 4 }),
  };
  const panes = {
    panes: new Map(),
    createPane: ({ id }) => { panes.panes.set(id, { id }); },
    attachSession: () => {},
  };
  const deps = {
    manager, panes,
    persistLayoutSnapshot: () => { calls.persisted += 1; },
    pushState: () => { calls.pushed += 1; },
    emitLayoutNow: () => { calls.laid += 1; },
    log: (l) => calls.logs.push(l),
    ...overrides,
  };
  return { calls, deps, manager, panes };
}

test("a governed spawn returns the session's exact pid and generation and wires the pane", () => {
  const { calls, deps } = fakeShell();
  const spawn = createGovernedPaneSpawn(deps);
  const identity = spawn({ paneId: "pane-2", nodeId: "worker-pane-2", spec: { file: "ollama.exe", title: "qwen" } });
  assert.deepEqual(identity, { pid: 9001, generation: 4 });
  assert.equal(calls.spawned.length, 1);
  assert.equal(calls.spawned[0].nodeId, "worker-pane-2");
  assert.equal(calls.killed.length, 0);
  assert.equal(calls.persisted, 1);
  assert.equal(calls.laid, 1);
});

test("a post-spawn wiring failure KILLS the session it just started, then rethrows", () => {
  // The whole point: the launcher reads a throw as "nothing was born" and hands the durable I-X3
  // terminal back. Without the rollback a live `claude` keeps running on a terminal nobody counts.
  const { calls, deps, panes } = fakeShell();
  panes.attachSession = () => { throw new Error("pane model rejected the attach"); };
  const spawn = createGovernedPaneSpawn(deps);
  let error = null;
  try {
    spawn({ paneId: "pane-3", nodeId: "worker-pane-3", spec: {} });
  } catch (e) {
    error = e;
  }
  assert.match(error.message, /pane model rejected the attach/);
  assert.deepEqual(error.sessionIdentity, { pid: 9001, generation: 4 });
  assert.equal(error.processExitPending, true);
  assert.deepEqual(calls.killed, ["pane-3"]);
  assert.equal(calls.spawned.length, 1);
  assert.match(calls.logs.join("\n"), /session killed, launch rolled back/);
});

test("EVERY post-spawn step is inside the rollback — persist, push, relayout and the pid read", () => {
  // One test per step, because a rollback that covers three of five steps is the same defect with a
  // smaller blast radius: each of these runs AFTER the process is alive.
  for (const step of ["createPane", "persistLayoutSnapshot", "pushState", "emitLayoutNow", "registryGet"]) {
    const { calls, deps, panes, manager } = fakeShell();
    if (step === "createPane") panes.createPane = () => { throw new Error(`${step} failed`); };
    else if (step === "registryGet") manager.registry.get = () => { throw new Error(`${step} failed`); };
    else deps[step] = () => { throw new Error(`${step} failed`); };
    const spawn = createGovernedPaneSpawn(deps);
    assert.throws(() => spawn({ paneId: "pane-4", nodeId: "worker-pane-4", spec: {} }),
      new RegExp(`${step} failed`), `${step} did not propagate`);
    assert.deepEqual(calls.killed, ["pane-4"], `${step} threw without rolling the session back`);
  }
});

test("a rollback whose own kill throws still reports the ORIGINAL fault (never a launch)", () => {
  const { deps, panes, manager } = fakeShell();
  panes.attachSession = () => { throw new Error("attach failed"); };
  manager.kill = () => { throw new Error("kill failed too"); };
  const spawn = createGovernedPaneSpawn(deps);
  assert.throws(() => spawn({ paneId: "pane-5", nodeId: "worker-pane-5", spec: {} }), /attach failed/);
});

test("a spawn REFUSED by supervision never reaches the pane model (no empty pane left behind)", () => {
  const { calls, deps, manager, panes } = fakeShell();
  manager.spawn = () => { throw new Error("SupervisionDenied: channel not verified"); };
  const spawn = createGovernedPaneSpawn(deps);
  assert.throws(() => spawn({ paneId: "pane-6", nodeId: "worker-pane-6", spec: {} }), /SupervisionDenied/);
  assert.equal(panes.panes.size, 0);
  assert.equal(calls.killed.length, 0);   // nothing was born, so there is nothing to roll back
});

test("the factory fails closed without the real manager/pane model (invariant 2)", () => {
  assert.throws(() => createGovernedPaneSpawn({}), /supervised spawn is the only way/);
  assert.throws(() => createGovernedPaneSpawn({ manager: {} }), /supervised spawn is the only way/);
});

// ---- refuseSelection: the conductor pane is not a worker pane ---------------------------------

const OPT = Object.freeze({
  provider: "anthropic", adapter: "claude_code", label: "Fable 5", model_slug: "fable-5",
  available: true, roles: ["reasoning", "coding"],
});
const SEL = (over = {}) => ({ option: OPT, role: "reasoning", mode: "attended", ...over });

// W-37 made `hostOptions` REQUIRED and fail-closed, so every call below now supplies the host
// enumeration the real caller (`main.js` `spawnFromSelection`) supplies. Each test's intent is
// unchanged — the conductor-pane rule, the mode rule, the role rule — they simply now corroborate
// against a host that offers the option, instead of against the caller's own claim about it.
const HOST = Object.freeze([OPT]);
const AT = (over = {}) => ({ hostOptions: HOST, ...over });

test("a worker model is REFUSED into the conductor pane, by pane id and not by a CSS rule", () => {
  const why = refuseSelection(SEL({ targetPaneId: "pane-1" }), AT({ conductorPaneId: "pane-1" }));
  assert.match(why, /pane-1 is the CONDUCTOR pane/);
  assert.match(why, /Resume→Select/);
});

test("…and the same selection into any OTHER pane passes the guard", () => {
  assert.equal(refuseSelection(SEL({ targetPaneId: "pane-2" }), AT({ conductorPaneId: "pane-1" })), null);
});

test("the conductor-pane guard does not fire when the shell has no conductor pane yet", () => {
  assert.equal(refuseSelection(SEL({ targetPaneId: "pane-1" }), AT({ conductorPaneId: null })), null);
  assert.equal(refuseSelection(SEL({ targetPaneId: "pane-1" }), AT()), null);
});

test("the front-line refusals still hold: no option, greyed, bad mode, unoffered role, conductor role", () => {
  assert.match(refuseSelection({ role: "reasoning", mode: "attended" }, AT()), /carries no picker option/);
  // The greyed case is now judged on the HOST's copy, which is the point of W-37: the caller cannot
  // grey-in an option the host greyed out.
  const greyed = { ...OPT, available: false, unavailable_reason: "not resident" };
  assert.match(refuseSelection(SEL({ option: greyed }), { hostOptions: [greyed] }),
    /unavailable \(not resident\)/);
  assert.match(refuseSelection(SEL({ mode: "sideways" }), AT()), /unknown pane mode/);
  assert.match(refuseSelection(SEL({ role: "voice" }), AT()), /not offered by/);
  const conductorOnly = { ...OPT, roles: ["conductor"] };
  assert.match(refuseSelection(SEL({ role: "conductor", option: conductorOnly }),
    { hostOptions: [conductorOnly] }),
  /conductor role is spawned by the dedicated conductor-first path/);
});
