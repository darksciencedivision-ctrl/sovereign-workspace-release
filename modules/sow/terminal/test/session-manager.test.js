"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { SessionManager, SupervisionDenied } = require("../conpty/session-manager");

let PID = 1000;
function fakePtyFactory(spec) {
  const p = {
    pid: ++PID,
    written: [],
    killed: false,
    _dataCb: null,
    _exitCb: null,
    onData(cb) { this._dataCb = cb; },
    onExit(cb) { this._exitCb = cb; },
    write(d) { this.written.push(d); },
    resize() {},
    kill() { this.killed = true; },
    emitData(d) { this._dataCb && this._dataCb(d); },
    emitExit(code) { this._exitCb && this._exitCb({ exitCode: code }); },
  };
  fakePtyFactory.last = p;
  return p;
}

function admittingSupervisor() {
  const events = [];
  return { admit: () => ({ supervised: true }), notify: (e) => events.push(e), events };
}

let clockN = 0;
const clock = () => `t${clockN++}`;

test("constructor rejects a missing supervisor (a shell cannot run naked sessions)", () => {
  assert.throws(() => new SessionManager({ ptyFactory: fakePtyFactory }), /supervisor with admit/);
  assert.throws(() => new SessionManager({ supervisor: admittingSupervisor() }), /ptyFactory is required/);
});

test("spawn requires a nodeId binding", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  assert.throws(() => mgr.spawn({ id: "s1", spec: {} }), /no naked sessions/);
});

test("admitted spawn goes RUNNING, feeds scrollback, and surfaces data events", () => {
  const sup = admittingSupervisor();
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: sup, now: clock });
  const seen = [];
  mgr.onEvent((e) => seen.push(e.kind));
  mgr.spawn({ id: "s1", nodeId: "n1", spec: { shell: "cmd" } });
  assert.strictEqual(mgr.registry.get("s1").state, "RUNNING");
  fakePtyFactory.last.emitData("output-bytes");
  assert.strictEqual(mgr.registry.reattach("s1").toString("utf8"), "output-bytes");
  assert.ok(seen.includes("spawn"));
  assert.ok(seen.includes("data"));
  // the supervisor was notified of the lifecycle (governed, not naked)
  assert.ok(sup.events.some((e) => e.kind === "spawn"));
});

test("denied admission KILLS the PTY and marks the session REFUSED (fail-closed)", () => {
  const denying = { admit: () => ({ supervised: false, reason: "policy: node not registered" }), notify() {} };
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: denying, now: clock });
  assert.throws(() => mgr.spawn({ id: "s1", nodeId: "n1", spec: {} }), SupervisionDenied);
  assert.strictEqual(fakePtyFactory.last.killed, true);
  assert.strictEqual(typeof fakePtyFactory.last._exitCb, "function",
    "exit observation must be installed before containment can deny and kill");
  assert.strictEqual(mgr.registry.get("s1").state, "REFUSED");
  assert.strictEqual(mgr.alive().length, 0);
  assert.throws(() => mgr.forget("s1"), /has not exited/,
    "kill intent may not make the refused process replaceable");
  fakePtyFactory.last.emitExit(1);
  mgr.forget("s1");
  assert.strictEqual(mgr.registry.has("s1"), false);
});

test("a throwing supervisor is treated as denial, not as admission", () => {
  const boom = { admit: () => { throw new Error("supervisor offline"); }, notify() {} };
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: boom, now: clock });
  assert.throws(() => mgr.spawn({ id: "s1", nodeId: "n1", spec: {} }), /refused/);
  assert.strictEqual(fakePtyFactory.last.killed, true);
  assert.strictEqual(mgr.registry.get("s1").state, "REFUSED");
  assert.throws(() => mgr.forget("s1"), /has not exited/);
});

test("process exit transitions RUNNING -> EXITED with the exit code", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  fakePtyFactory.last.emitExit(3);
  assert.strictEqual(mgr.registry.get("s1").state, "EXITED");
  assert.strictEqual(mgr.registry.get("s1").exitCode, 3);
});

test("kill transitions to KILLED and calls pty.kill(); killAll leaves nothing alive", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  const p1 = fakePtyFactory.last;
  mgr.spawn({ id: "s2", nodeId: "n1", spec: {} });
  mgr.kill("s1");
  assert.strictEqual(mgr.registry.get("s1").state, "KILLED");
  assert.strictEqual(p1.killed, true);
  mgr.killAll();
  assert.strictEqual(mgr.alive().length, 0);
  assert.strictEqual(mgr.registry.get("s2").state, "KILLED");
});

test("shutdown awaits process-exit confirmation after requesting teardown", async () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  const pty = fakePtyFactory.last;
  const waiting = mgr.shutdown(100);
  assert.strictEqual(pty.killed, true);
  assert.deepStrictEqual(mgr.pendingProcessIdentities().map((row) => row.pid), [pty.pid]);
  setImmediate(() => pty.emitExit(0));
  assert.deepStrictEqual(await waiting, { complete: true, pending: [] });
});

test("shutdown reports a process whose PTY never confirms exit", async () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  const result = await mgr.shutdown(1);
  assert.strictEqual(result.complete, false);
  assert.strictEqual(result.pending.length, 1);
  fakePtyFactory.last.emitExit(1);
});

test("kill intent is distinct from confirmed process exit", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  const events = [];
  mgr.onEvent((event) => {
    if (event.id === "s1" && (event.kind === "kill" || event.kind === "exit")) events.push(event);
  });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  const pty = fakePtyFactory.last;

  mgr.kill("s1");
  assert.deepStrictEqual(events.map((event) => [event.kind, event.processExited]), [["kill", false]],
    "requesting termination must not claim that the child is already gone");

  pty.emitExit(1);
  assert.deepStrictEqual(events.map((event) => [event.kind, event.processExited]), [
    ["kill", false],
    ["exit", true],
  ], "only the PTY exit callback confirms that the process is gone");
  assert.ok(Number.isInteger(events[0].generation));
  assert.strictEqual(events[0].generation, events[1].generation);
  assert.strictEqual(events[0].pid, pty.pid);
  assert.strictEqual(events[1].pid, pty.pid);
});

test("a killed process generation cannot be forgotten or replaced until its matching PTY exit", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  const first = mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  const oldPty = fakePtyFactory.last;
  mgr.kill("s1");

  assert.throws(() => mgr.forget("s1"), /process generation .* has not exited/);
  assert.throws(() => mgr.spawn({ id: "s1", nodeId: "n2", spec: {} }), /process generation .* still active/);

  oldPty.emitExit(1);
  mgr.forget("s1");
  const replacement = mgr.spawn({ id: "s1", nodeId: "n2", spec: {} });
  const replacementPty = fakePtyFactory.last;
  assert.notStrictEqual(replacement.generation, first.generation);

  oldPty.emitExit(1);
  assert.strictEqual(mgr.registry.get("s1").state, "RUNNING");
  assert.strictEqual(mgr.registry.get("s1").generation, replacement.generation);
  assert.strictEqual(mgr.write("s1", "replacement"), true);
  assert.deepStrictEqual(replacementPty.written, ["replacement"]);
});

test("a stale process generation cannot feed data into a replacement pane", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  const oldPty = fakePtyFactory.last;
  mgr.kill("s1");
  oldPty.emitExit(1);
  mgr.forget("s1");
  mgr.spawn({ id: "s1", nodeId: "n2", spec: {} });

  oldPty.emitData("stale-output");
  assert.strictEqual(mgr.registry.reattach("s1").toString("utf8"), "");
});

test("write forwards bytes to the underlying pty", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  mgr.write("s1", "ls\r");
  assert.deepStrictEqual(fakePtyFactory.last.written, ["ls\r"]);
});

// Phase 17C `.close-revalidate`: the RETURN VALUE is a contract, not a convenience. The gate-validator
// reverted this fix (back to `?.write(data); return true;`) and all 393 + 186 tests stayed green — a
// half-fixed BLOCKING finding that nothing could see. These are what see it.
test("write reports TRUE only while a pty handle is registered for the session", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  assert.strictEqual(mgr.write("s1", "hello"), true);
});

test("write to a KILLED session reports FALSE — the record outlives the handle", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  mgr.kill("s1");
  assert.strictEqual(mgr.registry.has("s1"), true, "the registry record survives a kill");
  assert.strictEqual(mgr.write("s1", "hello"), false,
    "a write with no live handle must NOT report success — the voice path claims delivery from this");
});

test("write to an EXITED session reports FALSE", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  fakePtyFactory.last.emitExit(0);          // the process ends on its own
  assert.strictEqual(mgr.registry.has("s1"), true);
  assert.strictEqual(mgr.write("s1", "hello"), false);
});

test("write to an unknown session reports FALSE", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  assert.strictEqual(mgr.write("never-spawned", "hello"), false);
});

// Phase 17D `.close` (spec-audit F1 / validator R2): `resize` had the SAME silent-discard shape
// `write` was fixed for at 17C — it no-ops for an ended session whose registry record has not been
// forgotten, and reported nothing. The shell's answer to the renderer was built from
// `registry.has(id)` alone, so a pane whose session had exited was told `{resized:true}` while no
// ConPTY was resized. A caller that cannot tell those apart is exactly what the U73 module exists
// to stop being.
test("resize reports TRUE only when a live pty handle took the geometry", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  mgr.spawn({ id: "s1", nodeId: "n1", spec: {} });
  assert.strictEqual(mgr.resize("s1", 100, 30), true);
});

test("resize of a KILLED or EXITED session reports FALSE — the record outlives the handle", () => {
  const killed = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  killed.spawn({ id: "s1", nodeId: "n1", spec: {} });
  killed.kill("s1");
  assert.strictEqual(killed.registry.has("s1"), true, "the registry record survives a kill");
  assert.strictEqual(killed.resize("s1", 100, 30), false);

  const exited = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  exited.spawn({ id: "s2", nodeId: "n1", spec: {} });
  fakePtyFactory.last.emitExit(0);
  assert.strictEqual(exited.registry.has("s2"), true);
  assert.strictEqual(exited.resize("s2", 100, 30), false);
});

test("resize of an unknown session reports FALSE", () => {
  const mgr = new SessionManager({ ptyFactory: fakePtyFactory, supervisor: admittingSupervisor(), now: clock });
  assert.strictEqual(mgr.resize("never-spawned", 100, 30), false);
});
