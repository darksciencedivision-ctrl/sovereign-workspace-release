"use strict";
/**
 * CONDUCTOR selection SOURCE tests (Phase 16C `.selection`) — the glue that turns the authoritative
 * Python emitter (`tools/live/emit_conductor_selection.py --emit-conductor-selection`) into the
 * badge/succession feed the shell renders, closing U65 (no hand-maintained literal to drift).
 *
 * Two layers, mirroring picker-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + timeout + fail-closed fold deterministically: good
 *       JSON, non-zero exit, non-JSON, malformed shape, timeout, launch error; and that the
 *       fail-closed feed renders "(unknown selection)" through the SAME pure badge the renderer uses;
 *   (2) live integration — the REAL `py -3.12` emitter is invoked and its feed validated against the
 *       shape the renderer folds, and asserted to carry the operator selection (fable-5). Not a mock.
 *       Skips cleanly without py -3.12.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  ConductorSourceError, fetchConductorFeed, fetchConductorSelectionFeed,
  unknownSelectionFeed, isWellFormedFeed, CONDUCTOR_SELECTION_FEED_SCHEMA,
} = require("../conductor/source");
const { conductorBadge, conductorSuccessionControl } = require("../../../terminal/compositor/conductor-pane");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const GOOD_FEED = {
  schema: CONDUCTOR_SELECTION_FEED_SCHEMA,
  selection_record: {
    selection: { model: "fable-5", reason: "operator_selected", since: "2026-07-19T00:00:00+00:00" },
    executing: { model: null, verified: false, is_fallback: false },
    label_mismatch: false,
  },
  succession: {
    available: true, control: "resume_select", actions: ["resume", "select", "restore"],
    restore_target: "fable-5",
  },
};

// A fake child process: emits the given stdout, then exits with `code`. Mirrors picker-source.test.js.
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
test("fetchConductorFeed parses a good feed and invokes exactly --emit-conductor-selection", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_FEED) });
  const feed = await fetchConductorFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(feed.selection_record.selection.model, "fable-5");
  assert.deepEqual(spawn.calls[0].args.slice(-2), ["tools/live/emit_conductor_selection.py", "--emit-conductor-selection"]);
  assert.equal(spawn.calls[0].opts.cwd, REPO_ROOT);
});

test("fetchConductorFeed rejects a non-zero exit (fail closed, surfaces stderr)", async () => {
  const spawn = fakeSpawn({ stdout: "", stderr: "boom", code: 2 });
  await assert.rejects(() => fetchConductorFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSourceError && /exited 2/.test(e.message) && /boom/.test(e.message));
});

test("fetchConductorFeed rejects non-JSON output (never fabricates a selection)", async () => {
  const spawn = fakeSpawn({ stdout: "not json at all" });
  await assert.rejects(() => fetchConductorFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSourceError && /non-JSON/.test(e.message));
});

test("fetchConductorFeed rejects a malformed feed shape (missing selection_record)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: CONDUCTOR_SELECTION_FEED_SCHEMA, succession: {} }) });
  await assert.rejects(() => fetchConductorFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSourceError && /malformed/.test(e.message));
});

test("fetchConductorFeed rejects a feed missing succession (fail closed)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: CONDUCTOR_SELECTION_FEED_SCHEMA, selection_record: GOOD_FEED.selection_record }) });
  await assert.rejects(() => fetchConductorFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSourceError && /malformed/.test(e.message));
});

test("fetchConductorFeed times out fail-closed and kills the child", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  await assert.rejects(() => fetchConductorFeed({ spawn, cwd: REPO_ROOT, timeoutMs: 60 }),
    (e) => e instanceof ConductorSourceError && /timed out/.test(e.message));
});

test("fetchConductorFeed rejects a spawn launch failure", async () => {
  const spawn = fakeSpawn({ throwOnSpawn: true });
  await assert.rejects(() => fetchConductorFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSourceError && /could not launch/.test(e.message));
});

test("fetchConductorFeed rejects a child 'error' event", async () => {
  const spawn = fakeSpawn({ emitError: "spawn py ENOENT" });
  await assert.rejects(() => fetchConductorFeed({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof ConductorSourceError && /failed to run/.test(e.message));
});

test("fetchConductorSelectionFeed DISPLAY never throws — a fault degrades to the unknown feed", async () => {
  const spawn = fakeSpawn({ stdout: "garbage" });
  const model = await fetchConductorSelectionFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(model.ok, false);
  assert.match(model.error, /non-JSON/);
  assert.equal(model.feed.selection_record.selection.model, null); // no fabricated model
});

test("fetchConductorSelectionFeed returns ok + feed on success", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_FEED) });
  const model = await fetchConductorSelectionFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(model.ok, true);
  assert.equal(model.feed.selection_record.selection.model, "fable-5");
});

test("the fail-closed unknown feed renders '(unknown selection)' — never a fabricated model", () => {
  const feed = unknownSelectionFeed();
  assert.ok(isWellFormedFeed(feed) === false || feed.succession === null); // succession is null ⇒ not 'well-formed from the emitter'
  const badge = conductorBadge(feed.selection_record);
  assert.equal(badge.model, "(unknown selection)");
  assert.equal(badge.verified, false);
  const succ = conductorSuccessionControl(feed.succession);
  assert.equal(succ.available, false); // Resume→Select shown unavailable on a fail-closed feed
});

test("a good feed renders the sourced model through the same pure badge the renderer uses", () => {
  const badge = conductorBadge(GOOD_FEED.selection_record);
  assert.equal(badge.model, "fable-5");
  assert.equal(badge.verified, false); // unverified until a live reply (invariant 3)
  const succ = conductorSuccessionControl(GOOD_FEED.succession);
  assert.equal(succ.available, true);
  assert.equal(succ.restoreTarget, "fable-5");
});

test("isWellFormedFeed accepts the emitter shape, rejects partials/null", () => {
  assert.equal(isWellFormedFeed(GOOD_FEED), true);
  assert.equal(isWellFormedFeed({ selection_record: GOOD_FEED.selection_record }), false); // no succession
  assert.equal(isWellFormedFeed({ succession: {} }), false); // no selection_record
  assert.equal(isWellFormedFeed(null), false);
});

// ---- (2) live integration: the REAL emitter ---------------------------------
test("live: the real --emit-conductor-selection emitter yields the operator selection feed", { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
  const feed = await fetchConductorFeed({ cwd: REPO_ROOT, timeoutMs: 60000 });
  assert.ok(isWellFormedFeed(feed), "real emitter emitted a well-formed feed");
  assert.equal(feed.schema, CONDUCTOR_SELECTION_FEED_SCHEMA);
  // 19.6, gate-validator MAJOR-2: these three assertions used to be the literals
  // `gpt-5.6-sol` / `ChatGPT 5.6 Sol` / `openai_codex_cli`, which is what the emitter yields ON THIS
  // HOST — because this host carries the operator's gitignored `config/live_operation.json`. On a
  // clone the registry resolves the RECORDED default (claude_code/fable-5) and this test went RED,
  // so `962 passed` was a host-conditional number and nothing said so. That clone case is the exact
  // case U331 exists for. What the emitter owes is now asserted as a PROPERTY: the selection is one
  // of the registry's registered conductor-capable pairs, and the descriptor, the selection record
  // and the badge all agree about which one. A drifting emitter still fails; a different host no
  // longer does.
  const REGISTERED = [
    { provider_id: "openai_codex_cli", model_id: "gpt-5.6-sol", display_name: "ChatGPT 5.6 Sol" },
    { provider_id: "claude_code", model_id: "fable-5", display_name: "Claude Fable 5" },
    { provider_id: "claude_code", model_id: "opus-4.8", display_name: "Claude Opus 4.8" },
  ];
  const d = feed.conductor_descriptor;
  // LOCAL-01 F-3 (ENTRY 018): the conductor seat is AGNOSTIC, so the registered set is no longer
  // three frontier literals — it is those PLUS one row per local model the operator's 8B ceiling
  // admits on this host. Those rows cannot be written down here: which models exist is a property
  // of the operator's disk, which is exactly the host-conditional trap this block was rewritten to
  // escape. So a local pair is admitted by its SHAPE (locality local, display name = the `ollama
  // list` tag the registry uses, no subscription), and the internal-agreement assertions below are
  // unchanged and still do the real work. A drifting emitter still fails.
  const isLocal = d.locality === "local";
  const registered = isLocal
    ? { provider_id: d.provider_id, model_id: d.model_id, display_name: d.model_id }
    : REGISTERED.find((r) => r.provider_id === d.provider_id && r.model_id === d.model_id);
  assert.ok(registered, `emitted conductor ${d.provider_id}/${d.model_id} is not a registered pair`);
  if (isLocal) {
    assert.equal(d.provider_id, "ollama_local");
    assert.equal(d.subscription_ref, "", "a local conductor holds no subscription (invariant 19)");
  }
  assert.equal(d.display_name, registered.display_name);
  assert.equal(d.role, "conductor");
  assert.equal(d.conductor_capable, true);
  assert.equal(feed.selection_record.selection.model, d.model_id);
  assert.equal(feed.selection_record.executing.model, null);      // nothing executed pre-launch (inv 3)
  assert.equal(feed.selection_record.executing.verified, false);
  assert.equal(feed.succession.available, true);
  // the badge the renderer draws from the REAL feed carries the sourced model, not a placeholder
  assert.equal(conductorBadge(feed.selection_record).model, d.model_id);
});
