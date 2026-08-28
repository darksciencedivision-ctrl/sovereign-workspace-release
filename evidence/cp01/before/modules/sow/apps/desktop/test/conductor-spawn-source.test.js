"use strict";
/**
 * CONDUCTOR governed-spawn SOURCE tests (Phase 16C `.spawn`) — the glue that turns the Python
 * governed spawn emitter (`tools/live/emit_conductor_spawn.py --emit-conductor-spawn`) into the
 * on-launch conductor-pane feed the shell renders: pane 1 is GOVERNED-BORN, `node_state` SOURCED.
 *
 * Two layers, mirroring conductor-source.test.js / picker-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + timeout + fail-closed fold deterministically: a
 *       governed spawn, a governed refusal (spawned:false + reason), non-zero exit, non-JSON,
 *       malformed shape, timeout, launch error, child 'error';
 *   (2) live integration — the REAL `py -3.12` emitter is invoked and its feed validated. On this
 *       host (config authorizes + `claude` present) it is a governed deferred spawn, torn down
 *       (D-LOOP-1); if the host lacked either it would be a refusal — both are honest, never a
 *       fabricated spawn. Skips cleanly without py -3.12.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  ConductorSpawnSourceError, fetchConductorSpawnFeed, sourceConductorSpawnFeed,
  unavailableSpawnFeed, isWellFormedSpawnFeed, CONDUCTOR_SPAWN_FEED_SCHEMA,
} = require("../conductor/spawn-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const GOOD_SPAWN = {
  schema: CONDUCTOR_SPAWN_FEED_SCHEMA,
  spawned: true,
  refused: false,
  reason: null,
  node_state: "awaiting_live_conductor",
  launched: false,
  chrome: {
    label: "CONDUCTOR", role: "conductor", pinned: true, pane_ordinal: 1, governed: true,
    interactive: true, node_state: "awaiting_live_conductor", model_label: "fable-5",
    subscription: { ref: "claude-sub", in_use: 1, allowance: 2 },
    succession: { available: true, actions: ["resume", "select", "restore"], restore_target: "fable-5" },
  },
  launch: { argv: ["claude", "--model", "fable-5"], interactive: true, one_shot: false, env_credential_scrubbed: true },
  selection_record: { selection: { model: "fable-5" }, executing: { model: null, verified: false } },
  torn_down: true,
  governor_released: true,
};

const REFUSAL = {
  schema: CONDUCTOR_SPAWN_FEED_SCHEMA,
  spawned: false,
  refused: true,
  reason: "ClaudeCliUnavailable: `claude` not detected",
  node_state: "spawn_refused",
  chrome: null,
  launch: null,
};

// A fake child process: emits the given stdout, then exits with `code`. Mirrors conductor-source.test.js.
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
test("fetchConductorSpawnFeed parses a governed spawn and invokes exactly --emit-conductor-spawn", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_SPAWN) });
  const feed = await fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(feed.spawned, true);
  assert.equal(feed.node_state, "awaiting_live_conductor");
  assert.equal(feed.chrome.role, "conductor");
  assert.deepEqual(spawn.calls[0].args.slice(-2), ["tools/live/emit_conductor_spawn.py", "--emit-conductor-spawn"]);
  assert.equal(spawn.calls[0].opts.cwd, REPO_ROOT);
});

test("fetchConductorSpawnFeed accepts a governed refusal (spawned:false + reason)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(REFUSAL) });
  const feed = await fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(feed.spawned, false);
  assert.equal(feed.refused, true);
  assert.match(feed.reason, /ClaudeCliUnavailable/);
});

test("fetchConductorSpawnFeed rejects a non-zero exit (fail closed, surfaces stderr)", async () => {
  const spawn = fakeSpawn({ stdout: "", stderr: "boom", code: 2 });
  await assert.rejects(() => fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSpawnSourceError && /exited 2/.test(e.message) && /boom/.test(e.message));
});

test("fetchConductorSpawnFeed rejects non-JSON output (never fabricates a spawn)", async () => {
  const spawn = fakeSpawn({ stdout: "not json at all" });
  await assert.rejects(() => fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSpawnSourceError && /non-JSON/.test(e.message));
});

test("fetchConductorSpawnFeed rejects a spawned feed missing chrome (malformed)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: CONDUCTOR_SPAWN_FEED_SCHEMA, spawned: true, node_state: "ready" }) });
  await assert.rejects(() => fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSpawnSourceError && /malformed/.test(e.message));
});

test("fetchConductorSpawnFeed rejects a refusal with no reason (fail closed)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: CONDUCTOR_SPAWN_FEED_SCHEMA, spawned: false, refused: true }) });
  await assert.rejects(() => fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSpawnSourceError && /malformed/.test(e.message));
});

test("fetchConductorSpawnFeed rejects a drifted schema", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ ...GOOD_SPAWN, schema: "conductor_spawn_feed@9.9" }) });
  await assert.rejects(() => fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSpawnSourceError && /malformed/.test(e.message));
});

test("fetchConductorSpawnFeed times out fail-closed and kills the child", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  await assert.rejects(() => fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT, timeoutMs: 60 }),
    (e) => e instanceof ConductorSpawnSourceError && /timed out/.test(e.message));
});

test("fetchConductorSpawnFeed rejects a spawn launch failure", async () => {
  const spawn = fakeSpawn({ throwOnSpawn: true });
  await assert.rejects(() => fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSpawnSourceError && /could not launch/.test(e.message));
});

test("fetchConductorSpawnFeed rejects a child 'error' event", async () => {
  const spawn = fakeSpawn({ emitError: "spawn py ENOENT" });
  await assert.rejects(() => fetchConductorSpawnFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSpawnSourceError && /failed to run/.test(e.message));
});

test("sourceConductorSpawnFeed DISPLAY never throws — a fault degrades to the unavailable feed", async () => {
  const spawn = fakeSpawn({ stdout: "garbage" });
  const r = await sourceConductorSpawnFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(r.ok, false);
  assert.match(r.error, /non-JSON/);
  assert.equal(r.feed.spawned, false);           // no fabricated governed birth
  assert.equal(r.feed.node_state, "unstarted");
});

test("sourceConductorSpawnFeed returns ok + feed on a governed spawn", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_SPAWN) });
  const r = await sourceConductorSpawnFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(r.ok, true);
  assert.equal(r.feed.spawned, true);
  assert.equal(r.feed.node_state, "awaiting_live_conductor");
});

test("the unavailable feed is a fail-closed non-spawn — never a fabricated governed birth", () => {
  const feed = unavailableSpawnFeed();
  assert.equal(feed.spawned, false);
  assert.equal(feed.chrome, null);
  assert.equal(feed.node_state, "unstarted");
});

test("isWellFormedSpawnFeed accepts a spawn + a refusal, rejects partials/drift/null", () => {
  assert.equal(isWellFormedSpawnFeed(GOOD_SPAWN), true);
  assert.equal(isWellFormedSpawnFeed(REFUSAL), true);
  assert.equal(isWellFormedSpawnFeed({ schema: CONDUCTOR_SPAWN_FEED_SCHEMA, spawned: true }), false); // no chrome
  assert.equal(isWellFormedSpawnFeed({ schema: CONDUCTOR_SPAWN_FEED_SCHEMA, spawned: false }), false); // no reason
  assert.equal(isWellFormedSpawnFeed({ ...GOOD_SPAWN, schema: "x" }), false);
  assert.equal(isWellFormedSpawnFeed(null), false);
});

// ---- (2) live integration: the REAL emitter ---------------------------------
test("live: the real --emit-conductor-spawn emitter yields a governed feed, torn down", { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
  const feed = await fetchConductorSpawnFeed({ cwd: REPO_ROOT, timeoutMs: 60000 });
  assert.ok(isWellFormedSpawnFeed(feed), "real emitter emitted a well-formed feed");
  assert.equal(feed.schema, CONDUCTOR_SPAWN_FEED_SCHEMA);
  if (feed.spawned) {
    // config authorizes + `claude` present ⇒ a governed DEFERRED spawn (operator-run ConPTY, §6)
    assert.equal(feed.node_state, "awaiting_live_conductor");
    assert.equal(feed.chrome.role, "conductor");
    assert.equal(feed.chrome.governed, true);
    assert.equal(feed.launch.one_shot, false);
    assert.ok(!feed.launch.argv.includes("-p"), "interactive — never the one-shot -p worker command");
    assert.equal(feed.launch.env_credential_scrubbed, true);
    // D-LOOP-1: the governed spawn released its I-X3 terminal before the tool exited
    assert.equal(feed.torn_down, true);
    assert.equal(feed.governor_released, true);
  } else {
    // honest refusal on a host missing the config or the CLI — never a fabricated spawn
    assert.equal(feed.refused, true);
    assert.ok(feed.reason && feed.reason.length > 0);
  }
});
