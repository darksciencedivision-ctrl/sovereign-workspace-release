"use strict";
/**
 * CONDUCTOR governed-DISPATCH SOURCE tests (Phase 16C `.dispatch`) — the glue that turns the Python
 * governed dispatch emitter (`tools/live/emit_conductor_dispatch.py --emit-conductor-dispatch`) into
 * the on-launch conductor dispatch line the shell renders: the govern-born conductor DISPATCHED work
 * to worker nodes over MCP (decompose → assign BY DESCRIPTOR → CANDIDATE → gates → synthesis), folded
 * into `conductor_dispatch_feed@1.0`, MOCK-first — no live call.
 *
 * Two layers, mirroring conductor-spawn-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + timeout + fail-closed fold deterministically: a
 *       governed dispatch, a governed non-dispatch (dispatched:false + reason), non-zero exit,
 *       non-JSON, malformed shape, timeout, launch error, child 'error';
 *   (2) live integration — the REAL `py -3.12` emitter is invoked and its feed validated. On this
 *       host it runs the mock-first governed dispatch and folds it; the legs are mock/mock and the
 *       live worker leg is recorded OWED (U58). Skips cleanly without py -3.12.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  ConductorDispatchSourceError, fetchConductorDispatchFeed, sourceConductorDispatchFeed,
  unavailableDispatchFeed, isWellFormedDispatchFeed, CONDUCTOR_DISPATCH_FEED_SCHEMA,
} = require("../conductor/dispatch-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const GOOD_DISPATCH = {
  schema: CONDUCTOR_DISPATCH_FEED_SCHEMA,
  dispatched: true,
  reason: null,
  objective: "Design the offline conductor roster",
  assignments: [
    { task: "t-1", node: "worker-A", rationale: "resolved 'reasoning' to worker-A by descriptor (2 eligible)" },
    { task: "t-3", node: "worker-B", rationale: "resolved 'review' to worker-B by descriptor (2 eligible)" },
  ],
  assigned_count: 2,
  by_descriptor: true,
  queued_count: 1,
  failed_count: 0,
  accepted_count: 2,
  acceptance_packet: "m-abc123",
  acceptance_verdict: "PASS",
  operator_disposition: "pending",
  legs: { conductor: "mock", workers: "mock" },
  gate_summary: { plan: "PASS", stage_pass: 2, stage_total: 2, acceptance: "PASS" },
  synthesized_by: "conductor_fable5",
  live_workers_owed: { owed: true, issue: "U58", note: "owed to 16F" },
  ts: "2026-07-24T00:00:00+00:00",
  torn_down: true,
};

const NON_DISPATCH = {
  schema: CONDUCTOR_DISPATCH_FEED_SCHEMA,
  dispatched: false,
  reason: "plan gate 'FAIL' — no plan, nothing dispatched",
  assignments: [],
  legs: { conductor: "skipped", workers: "skipped" },
};

// A fake child process: emits the given stdout, then exits with `code`. Mirrors conductor-spawn-source.test.js.
function fakeSpawn({ stdout = "", stderr = "", code = 0, neverExit = false, throwOnSpawn = false, emitError = null } = {}) {
  const calls = [];
  const spawn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    if (throwOnSpawn) throw new Error("ENOENT");
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => { child.killed = true; };
    child.killed = false;
    setImmediate(() => {
      if (emitError) { child.emit("error", new Error(emitError)); return; }
      if (stdout) child.stdout.emit("data", Buffer.from(stdout));
      if (stderr) child.stderr.emit("data", Buffer.from(stderr));
      if (!neverExit) child.emit("exit", code);
    });
    return child;
  };
  spawn.calls = calls;
  return spawn;
}

// ---- (1) unit: fake spawn ----------------------------------------------------
test("fetchConductorDispatchFeed parses a governed dispatch and invokes exactly --emit-conductor-dispatch", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_DISPATCH) });
  const feed = await fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(feed.dispatched, true);
  assert.equal(feed.by_descriptor, true);
  assert.equal(feed.accepted_count, 2);
  assert.deepEqual(feed.legs, { conductor: "mock", workers: "mock" });
  assert.equal(feed.live_workers_owed.issue, "U58");
  assert.deepEqual(spawn.calls[0].args.slice(-2), ["tools/live/emit_conductor_dispatch.py", "--emit-conductor-dispatch"]);
  assert.equal(spawn.calls[0].opts.cwd, REPO_ROOT);
});

test("fetchConductorDispatchFeed accepts a governed non-dispatch (dispatched:false + reason)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(NON_DISPATCH) });
  const feed = await fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(feed.dispatched, false);
  assert.match(feed.reason, /plan gate/);
});

test("fetchConductorDispatchFeed rejects a non-zero exit (fail closed, surfaces stderr)", async () => {
  const spawn = fakeSpawn({ stdout: "", stderr: "boom", code: 2 });
  await assert.rejects(() => fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorDispatchSourceError && /exited 2/.test(e.message) && /boom/.test(e.message));
});

test("fetchConductorDispatchFeed rejects non-JSON output (never fabricates a dispatch)", async () => {
  const spawn = fakeSpawn({ stdout: "not json at all" });
  await assert.rejects(() => fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorDispatchSourceError && /non-JSON/.test(e.message));
});

test("fetchConductorDispatchFeed rejects a dispatched feed with no assignments (malformed)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ ...GOOD_DISPATCH, assignments: [] }) });
  await assert.rejects(() => fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorDispatchSourceError && /malformed/.test(e.message));
});

test("fetchConductorDispatchFeed rejects a non-dispatch with no reason (fail closed)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: CONDUCTOR_DISPATCH_FEED_SCHEMA, dispatched: false }) });
  await assert.rejects(() => fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorDispatchSourceError && /malformed/.test(e.message));
});

test("fetchConductorDispatchFeed rejects a drifted schema", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ ...GOOD_DISPATCH, schema: "conductor_dispatch_feed@9.9" }) });
  await assert.rejects(() => fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorDispatchSourceError && /malformed/.test(e.message));
});

test("fetchConductorDispatchFeed times out fail-closed and kills the child", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  await assert.rejects(() => fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT, timeoutMs: 60 }),
    (e) => e instanceof ConductorDispatchSourceError && /timed out/.test(e.message));
});

test("fetchConductorDispatchFeed rejects a spawn launch failure", async () => {
  const spawn = fakeSpawn({ throwOnSpawn: true });
  await assert.rejects(() => fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorDispatchSourceError && /could not launch/.test(e.message));
});

test("fetchConductorDispatchFeed rejects a child 'error' event", async () => {
  const spawn = fakeSpawn({ emitError: "spawn py ENOENT" });
  await assert.rejects(() => fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorDispatchSourceError && /failed to run/.test(e.message));
});

test("sourceConductorDispatchFeed DISPLAY never throws — a fault degrades to the unavailable feed", async () => {
  const spawn = fakeSpawn({ stdout: "garbage" });
  const r = await sourceConductorDispatchFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(r.ok, false);
  assert.match(r.error, /non-JSON/);
  assert.equal(r.feed.dispatched, false);        // no fabricated dispatch
  assert.equal(r.feed.assignments.length, 0);
  assert.equal(r.feed.live_workers_owed.issue, "U58"); // U58 still surfaced
});

test("sourceConductorDispatchFeed returns ok + feed on a governed dispatch", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_DISPATCH) });
  const r = await sourceConductorDispatchFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(r.ok, true);
  assert.equal(r.feed.dispatched, true);
  assert.equal(r.feed.accepted_count, 2);
});

test("the unavailable feed is a fail-closed non-dispatch — never a fabricated dispatch", () => {
  const feed = unavailableDispatchFeed();
  assert.equal(feed.dispatched, false);
  assert.equal(feed.assignments.length, 0);
  assert.deepEqual(feed.legs, { conductor: "skipped", workers: "skipped" });
  assert.equal(feed.live_workers_owed.issue, "U58");
});

test("isWellFormedDispatchFeed accepts a dispatch + a non-dispatch, rejects partials/drift/null", () => {
  assert.equal(isWellFormedDispatchFeed(GOOD_DISPATCH), true);
  assert.equal(isWellFormedDispatchFeed(NON_DISPATCH), true);
  assert.equal(isWellFormedDispatchFeed({ schema: CONDUCTOR_DISPATCH_FEED_SCHEMA, dispatched: true, assignments: [] }), false); // no assignments
  assert.equal(isWellFormedDispatchFeed({ schema: CONDUCTOR_DISPATCH_FEED_SCHEMA, dispatched: false }), false); // no reason
  assert.equal(isWellFormedDispatchFeed({ ...GOOD_DISPATCH, schema: "x" }), false);
  assert.equal(isWellFormedDispatchFeed(null), false);
});

// ---- (2) live integration: the REAL emitter ---------------------------------
test("live: the real --emit-conductor-dispatch emitter yields a mock-first governed dispatch, U58 owed, torn down",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    const feed = await fetchConductorDispatchFeed({ cwd: REPO_ROOT, timeoutMs: 90000 });
    assert.ok(isWellFormedDispatchFeed(feed), "real emitter emitted a well-formed feed");
    assert.equal(feed.schema, CONDUCTOR_DISPATCH_FEED_SCHEMA);
    assert.equal(feed.dispatched, true, "the mock-first governed dispatch runs on this host");
    assert.equal(feed.by_descriptor, true, "routing is BY DESCRIPTOR (invariant 4)");
    assert.ok(feed.accepted_count >= 1, "at least one artifact was gate-accepted");
    assert.equal(feed.acceptance_verdict, "PASS");
    // MOCK-FIRST HONESTY: never a claimed live worker/conductor leg
    assert.deepEqual(feed.legs, { conductor: "mock", workers: "mock" });
    assert.equal(feed.operator_disposition, "pending"); // gate promotion ≠ operator acceptance (inv 1)
    assert.equal(feed.live_workers_owed.owed, true);
    assert.equal(feed.live_workers_owed.issue, "U58");
    assert.equal(feed.torn_down, true);                 // D-LOOP-1
  });
