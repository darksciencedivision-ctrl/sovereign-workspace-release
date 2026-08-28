"use strict";
/**
 * Phase 17E — the LIVE-worker option on the conductor dispatch source.
 *
 * `tools/live/emit_conductor_dispatch.py --live-workers` (17B `.legs`) spawns ONE governed live
 * `claude_code` worker that publishes a CANDIDATE over MCP, passes the real gate engine and is folded
 * into the conductor's acceptance packet. Until now nothing in the shell could ask for it, so the
 * assembled composition had no way to compose the live leg with the rest of the run in ONE runtime.
 *
 * The flag is deliberately NOT free: it spends the operator's subscription. So these tests pin both
 * halves — it reaches the emitter when the caller asks for it, and NOTHING on the shell's ordinary
 * launch path asks for it. The second half is the load-bearing one: a launch-time live dispatch would
 * spend a live exchange every time the operator opens the app.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { EventEmitter } = require("node:events");

const {
  fetchConductorDispatchFeed, CONDUCTOR_DISPATCH_FEED_SCHEMA,
} = require("../conductor/dispatch-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

const LIVE_FEED = {
  schema: CONDUCTOR_DISPATCH_FEED_SCHEMA,
  dispatched: true,
  by_descriptor: true,
  accepted_count: 1,
  acceptance_verdict: "PASS",
  assignments: [{ node_id: "worker-claude-live", task_id: "t-1" }],
  legs: { conductor: "mock", workers: "live" },
  live_workers_owed: { owed: false, issue: "U58" },
  torn_down: true,
};

function fakeSpawn({ stdout = "", code = 0 } = {}) {
  const calls = [];
  const spawn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => { child.killed = true; };
    setImmediate(() => {
      if (stdout) child.stdout.emit("data", Buffer.from(stdout));
      child.emit("exit", code);
    });
    return child;
  };
  spawn.calls = calls;
  return spawn;
}

test("by default the emitter is invoked with NO live flag (an app launch spends nothing)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ ...LIVE_FEED, legs: { conductor: "mock", workers: "mock" } }) });
  await fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT });
  assert.ok(!spawn.calls[0].args.includes("--live-workers"),
    `default invocation asked for live workers: ${spawn.calls[0].args.join(" ")}`);
});

test("liveWorkers:true appends --live-workers after the emit flag", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(LIVE_FEED) });
  const feed = await fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT, liveWorkers: true });
  assert.deepEqual(spawn.calls[0].args.slice(-3),
    ["tools/live/emit_conductor_dispatch.py", "--emit-conductor-dispatch", "--live-workers"]);
  assert.equal(feed.legs.workers, "live");
});

test("liveWorkers:false is the same invocation as omitting it (no accidental truthiness)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ ...LIVE_FEED, legs: { conductor: "mock", workers: "mock" } }) });
  await fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT, liveWorkers: false });
  assert.ok(!spawn.calls[0].args.includes("--live-workers"));
});

test("a live dispatch gets a bound wide enough for a real model call, and the caller can still pin one", async () => {
  // 17B `.legs` measured 277 s end-to-end on this host. The mock default (40 s) would kill every live
  // run before it returned — reported as a fail-closed "feed unavailable", i.e. as a shell fault that
  // had not happened.
  const spawn = fakeSpawn({ stdout: JSON.stringify(LIVE_FEED) });
  const feed = await fetchConductorDispatchFeed({ spawn, cwd: REPO_ROOT, liveWorkers: true });
  assert.equal(feed.dispatched, true);
  // the bound itself is not observable through a resolved call, so it is asserted at the source: the
  // live default must exceed the measured live run, and the mock default must not have moved.
  const src = fs.readFileSync(path.join(__dirname, "..", "conductor", "dispatch-source.js"), "utf8");
  const mockDefault = /opts\.timeoutMs\s*\|\|\s*\(liveWorkers\s*\?\s*(\d+)\s*:\s*(\d+)\)/.exec(src);
  assert.ok(mockDefault, "the dispatch source no longer picks its default timeout by liveWorkers");
  assert.ok(Number(mockDefault[1]) >= 600000, `live default ${mockDefault[1]}ms is below the measured 277 s run`);
  assert.equal(Number(mockDefault[2]), 40000, "the MOCK default timeout moved");
});

test("main.js never asks for live workers on the launch path", () => {
  // The guard that matters. A shell that sourced a live dispatch at launch would spend one governed
  // live exchange every single time the operator opened the app — and it would do it before anyone
  // had asked for anything.
  const main = fs.readFileSync(path.join(__dirname, "..", "main.js"), "utf8");
  // Anchor on the self-check DISPATCHER, which appears exactly once. The first
  // `if (process.env.SHELL_SELFCHECK)` in the file is the renderer console-logging block a few
  // hundred lines earlier (spec-audit F6): boundary-ing there put the PRODUCT conductor auto-launch
  // inside `inBlock`, so a `liveWorkers: true` added to the auto-launch — the exact scenario this
  // test exists for — would have passed. The boundary is asserted to contain that launch path.
  const anchor = 'const kind = process.env.SHELL_SELFCHECK === "picker"';
  const blockAt = main.indexOf(anchor);
  assert.ok(blockAt > 0, "main.js no longer has a SHELL_SELFCHECK dispatcher to scope the flag to");
  assert.equal(main.indexOf(anchor), main.lastIndexOf(anchor), "the anchor is no longer unique");
  const beforeBlock = main.slice(0, blockAt);
  const inBlock = main.slice(blockAt);
  assert.ok(/SOW_CONDUCTOR_AUTOLAUNCH/.test(beforeBlock),
    "the boundary no longer contains the product conductor auto-launch — it would not catch a "
    + "live dispatch added THERE, which is the launch path that matters");
  assert.ok(/sourceConductorDispatchFeed\(/.test(beforeBlock),
    "main.js no longer sources a conductor dispatch feed on the launch path at all");
  assert.ok(!/liveWorkers/.test(beforeBlock),
    "main.js names liveWorkers on the launch path — an app launch would spend a live exchange");
  // …and the guard is not vacuous: the flag IS reachable, from inside the self-check block only.
  assert.ok(/liveWorkers/.test(inBlock),
    "nothing in main.js can ask for a live dispatch — this guard would pass on any file");
});
