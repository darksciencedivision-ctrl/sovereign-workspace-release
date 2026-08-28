"use strict";
/**
 * Subscription-concurrency status-bar GOVERNOR-SOURCE tests (Phase 16D `.statusbar`) — the glue that
 * turns the bounded `py -3.12 tools/live/emit_subscription_status.py --emit-subscription-status`
 * emitter into the readable n/2 model the shell status bar renders (closing the operator's
 * "concurrency count unavailable" finding).
 *
 * Two layers, mirroring picker-source.test.js / statusbar-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + timeout + fail-closed fold deterministically, with no
 *       live host: good feed (authorized readable 0/2), authorized:false (fail-closed unknown),
 *       non-zero exit, non-JSON, malformed shape, timeout, launch error;
 *   (2) live integration — the REAL emitter is invoked and its feed folds to a readable model.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  FEED_SCHEMA, GovernorStatusSourceError, isWellFormedFeed,
  fetchGovernorStatusFeed, fetchStatusBarModelFromGovernor,
} = require("../statusbar/governor-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const GOOD_FEED = {
  schema: FEED_SCHEMA,
  authorized: true,
  providers: ["claude_code", "openai_codex_cli"],
  allowance: 2,
  register_row: "OP-6",
  source: "(test)",
  reason: "authorized",
  status: {
    "sub-claude_code": { provider: "claude_code", allowance: 2, active: [], in_use: 0 },
    "sub-openai_codex_cli": { provider: "openai_codex_cli", allowance: 2, active: [], in_use: 0 },
  },
  live_session_tracking: { owed: true, issue: "16F", note: "0 held; ceiling" },
};

const DENIED_FEED = {
  schema: FEED_SCHEMA, authorized: false, providers: [], allowance: 0,
  register_row: null, source: "(none)", reason: "no live-operation config (enforcement-by-absence)",
  status: null, live_session_tracking: { owed: true, issue: "16F", note: "not authorized" },
};

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
test("fetchGovernorStatusFeed parses a good feed and invokes exactly --emit-subscription-status", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_FEED) });
  const feed = await fetchGovernorStatusFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(feed.schema, FEED_SCHEMA);
  assert.equal(feed.authorized, true);
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--emit-subscription-status"));
  assert.ok(args.some((a) => a.endsWith("emit_subscription_status.py")));
});

test("authorized good feed folds to a READABLE 0/2 model for both providers (not the unknown)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_FEED) });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  assert.equal(model.readable, true);          // NOT the em-dash unknown — the operator's fix
  assert.equal(model.feedAuthorized, true);
  assert.equal(model.error, undefined);
  const byProv = Object.fromEntries(model.rows.map((r) => [r.provider, r]));
  assert.equal(byProv.claude_code.label, "0/2");
  assert.equal(byProv.openai_codex_cli.label, "0/2");
  assert.equal(byProv.claude_code.state, "idle");
  assert.equal(model.summary.readable, true);
});

test("a held/active feed folds to an active count (the acquire path is real)", async () => {
  const active = JSON.parse(JSON.stringify(GOOD_FEED));
  active.status["sub-claude_code"] = { provider: "claude_code", allowance: 2, active: ["w-A"], in_use: 1 };
  const spawn = fakeSpawn({ stdout: JSON.stringify(active) });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  const claude = model.rows.find((r) => r.provider === "claude_code");
  assert.equal(claude.label, "1/2");
  assert.equal(claude.state, "active");
});

test("authorized:false feed is fail-closed UNKNOWN (em-dash), never a fabricated 0/2", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(DENIED_FEED) });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  assert.equal(model.readable, false);
  assert.equal(model.feedAuthorized, false);
  // Every row is the em-dash unknown — and its ceiling is that provider's OWN allowance (U255):
  // the OP-6 pair reads —/2, the OP-12 pair —/1. A single global 2 here would have advertised two
  // Grok terminals on a subscription the operator directive caps at one (§12/§14).
  assert.ok(model.rows.every((r) => r.state === "unknown"));
  const byProvider = Object.fromEntries(model.rows.map((r) => [r.provider, r.label]));
  assert.deepEqual(byProvider, {
    claude_code: "—/2", openai_codex_cli: "—/2", grok_build: "—/1", google_antigravity: "—/1",
  });
  assert.match(model.error, /enforcement-by-absence/);
});

test("non-zero exit → fail-closed unknown model with the error", async () => {
  const spawn = fakeSpawn({ code: 2, stderr: "boom" });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  assert.equal(model.readable, false);
  assert.match(model.error, /exited 2/);
  assert.ok(model.rows.every((r) => r.state === "unknown"));
});

test("non-JSON output → fail-closed unknown model", async () => {
  const spawn = fakeSpawn({ stdout: "not json at all" });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  assert.equal(model.readable, false);
  assert.match(model.error, /non-JSON/);
});

test("malformed feed (wrong schema) → fail-closed unknown model", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: "other@9", status: {} }) });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  assert.equal(model.readable, false);
  assert.match(model.error, /malformed feed/);
});

test("malformed feed (status is an array) → fail-closed unknown model", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: FEED_SCHEMA, status: [] }) });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  assert.equal(model.readable, false);
});

test("timeout → fail-closed unknown model", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT, timeoutMs: 30 });
  assert.equal(model.readable, false);
  assert.match(model.error, /timed out/);
});

test("spawn launch throw → fail-closed unknown model (never throws into renderer)", async () => {
  const spawn = fakeSpawn({ throwOnSpawn: true });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  assert.equal(model.readable, false);
  assert.match(model.error, /could not launch/);
});

test("child 'error' event → fail-closed unknown model", async () => {
  const spawn = fakeSpawn({ emitError: "spawn failed" });
  const model = await fetchStatusBarModelFromGovernor({ spawn, cwd: REPO_ROOT });
  assert.equal(model.readable, false);
  assert.match(model.error, /failed to run/);
});

test("fetchGovernorStatusFeed (strict) throws on a bad exit", async () => {
  const spawn = fakeSpawn({ code: 2 });
  await assert.rejects(() => fetchGovernorStatusFeed({ spawn, cwd: REPO_ROOT }), GovernorStatusSourceError);
});

test("isWellFormedFeed accepts status:null and object, rejects arrays/other schema", () => {
  assert.equal(isWellFormedFeed({ schema: FEED_SCHEMA, status: null }), true);
  assert.equal(isWellFormedFeed({ schema: FEED_SCHEMA, status: {} }), true);
  assert.equal(isWellFormedFeed({ schema: FEED_SCHEMA, status: [] }), false);
  assert.equal(isWellFormedFeed({ schema: "x@1", status: {} }), false);
  assert.equal(isWellFormedFeed(null), false);
  assert.equal(isWellFormedFeed({ schema: FEED_SCHEMA }), false); // status undefined
});

// ---- (2) live integration: the REAL emitter --------------------------------
test("LIVE: the real emitter yields a readable model folded through the pure view", { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
  const model = await fetchStatusBarModelFromGovernor({ cwd: REPO_ROOT, timeoutMs: 30000 });
  assert.equal(model.source, "emitter");
  // With config/live_operation.json present (OP-6) the host is authorized ⇒ readable 0/2; without it
  // the loader is DENIED ⇒ fail-closed unknown. Either is honest; assert the shape holds both ways.
  if (model.feedAuthorized) {
    assert.equal(model.readable, true);
    assert.ok(model.rows.some((r) => r.provider === "claude_code" && /\d+\/\d+/.test(r.label)));
    assert.ok(model.rows.some((r) => r.provider === "openai_codex_cli"));
  } else {
    assert.equal(model.readable, false);
    assert.ok(model.rows.every((r) => r.state === "unknown"));
  }
});
