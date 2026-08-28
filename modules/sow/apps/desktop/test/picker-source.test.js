"use strict";
/**
 * Per-pane model-picker SOURCE tests (Phase 16B `.source`) — the glue that turns the operator-run
 * host enumerator (`tools/live/enumerate_pane_picker.py --emit-picker`) into the picker the shell
 * renders.
 *
 * Two layers, mirroring statusbar-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + timeout + fail-closed fold deterministically, with
 *       no live host: good JSON, non-zero exit, non-JSON, malformed shape, timeout, launch error;
 *   (2) live integration — the REAL `py -3.12` enumerator is invoked and its picker is validated
 *       against the shape the renderer folds. This is the "runs the real host enumeration" leg the
 *       16B work unit requires — not a mock. Skips cleanly without py -3.12.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  PickerSourceError, fetchHostPicker, fetchPickerModel, emptyPicker, isWellFormedPicker,
  fetchHostResidency, isWellFormedResidency,
} = require("../picker/source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const GOOD_PICKER = {
  providers: [
    { provider: "claude_code", display: "Anthropic (claude CLI)", options: [
      { provider: "claude_code", adapter: "claude_code", locality: "frontier", label: "Fable 5",
        model_slug: "fable-5", verified: false, is_fallback: false, roles: ["conductor", "reasoning", "coding"],
        residency: null, available: true, unavailable_reason: null, note: "" } ] },
    { provider: "ollama_local", display: "Local (Ollama)", options: [
      { provider: "ollama_local", adapter: "ollama_local", locality: "local", label: "qwen3:8b",
        model_slug: "qwen3:8b", verified: true, is_fallback: false, roles: ["reasoning", "coding"],
        residency: "not_loaded", available: true, unavailable_reason: null, note: "" } ] },
  ],
  options: [],
  authorization: { authorized: true, providers: ["claude_code"], reason: "ok" },
  counts: { total: 2, available: 2, frontier: 1, local: 1 },
};

// A fake child process: emits the given stdout, then exits with `code`. `err` goes to stderr.
// If `neverExit` is set it stays open (to exercise the timeout path).
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
test("fetchHostPicker parses a good picker and invokes exactly --emit-picker", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_PICKER) });
  const picker = await fetchHostPicker({ spawn, cwd: REPO_ROOT });
  assert.equal(picker.counts.total, 2);
  assert.deepEqual(spawn.calls[0].args.slice(-2), ["tools/live/enumerate_pane_picker.py", "--emit-picker"]);
  assert.equal(spawn.calls[0].opts.cwd, REPO_ROOT);
});

test("fetchHostPicker rejects a non-zero exit (fail closed, surfaces stderr)", async () => {
  const spawn = fakeSpawn({ stdout: "", stderr: "boom", code: 2 });
  await assert.rejects(() => fetchHostPicker({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof PickerSourceError && /exited 2/.test(e.message) && /boom/.test(e.message));
});

test("fetchHostPicker rejects non-JSON output (never fabricates a picker)", async () => {
  const spawn = fakeSpawn({ stdout: "not json at all" });
  await assert.rejects(() => fetchHostPicker({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof PickerSourceError && /non-JSON/.test(e.message));
});

test("fetchHostPicker rejects a malformed picker shape (missing providers array)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ counts: {}, options: [] }) });
  await assert.rejects(() => fetchHostPicker({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof PickerSourceError && /malformed/.test(e.message));
});

test("fetchHostPicker times out fail-closed and kills the child", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  await assert.rejects(() => fetchHostPicker({ spawn, cwd: REPO_ROOT, timeoutMs: 60 }),
    (e) => e instanceof PickerSourceError && /timed out/.test(e.message));
});

test("fetchHostPicker rejects a spawn launch failure", async () => {
  const spawn = fakeSpawn({ throwOnSpawn: true });
  await assert.rejects(() => fetchHostPicker({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof PickerSourceError && /could not launch/.test(e.message));
});

test("fetchHostPicker rejects a child 'error' event", async () => {
  const spawn = fakeSpawn({ emitError: "spawn py ENOENT" });
  await assert.rejects(() => fetchHostPicker({ spawn, cwd: REPO_ROOT }),
    (e) => e instanceof PickerSourceError && /failed to run/.test(e.message));
});

test("fetchPickerModel DISPLAY never throws — a fault degrades to the empty fail-closed picker", async () => {
  const spawn = fakeSpawn({ stdout: "garbage" });
  const model = await fetchPickerModel({ spawn, cwd: REPO_ROOT });
  assert.equal(model.ok, false);
  assert.match(model.error, /non-JSON/);
  assert.deepEqual(model.picker.options, []);       // no fabricated options
  assert.equal(model.picker.authorization.authorized, false); // fail-closed authorization
});

test("fetchPickerModel returns ok + picker on success", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_PICKER) });
  const model = await fetchPickerModel({ spawn, cwd: REPO_ROOT });
  assert.equal(model.ok, true);
  assert.equal(model.picker.counts.total, 2);
});

test("emptyPicker + isWellFormedPicker are self-consistent (empty is well-formed but option-less)", () => {
  const ep = emptyPicker();
  assert.ok(isWellFormedPicker(ep));
  assert.equal(ep.options.length, 0);
  assert.equal(isWellFormedPicker({ providers: [] }), false); // missing options/counts
  assert.equal(isWellFormedPicker(null), false);
});

// ---- (2) live integration: the REAL enumerator ------------------------------
test("live: the real --emit-picker enumerator yields a renderer-foldable picker", { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
  const picker = await fetchHostPicker({ cwd: REPO_ROOT, timeoutMs: 60000 });
  assert.ok(isWellFormedPicker(picker), "real enumerator emitted a well-formed picker");
  // every option carries the fields the renderer reads; a greyed one carries a reason (no blank grey)
  for (const o of picker.options) {
    assert.ok(o.provider && o.label && Array.isArray(o.roles));
    if (o.available === false) assert.ok(o.unavailable_reason, "greyed option must state why");
  }
  assert.equal(picker.counts.total, picker.options.length);
});

test("fetchHostResidency parses the pinned residency contract and fails closed on drift", async () => {
  const good = { schema: "host_residency@1.0",
    budget: { vram_budget_mb: 24576, established: true, estimate: true, budget_source: "(test)" },
    snapshot: { total_vram_mb: 24576, used_vram_mb: 4000, free_vram_mb: 20576, models: [] } };
  const ok = await fetchHostResidency({ spawn: fakeSpawn({ stdout: JSON.stringify(good) }), cwd: REPO_ROOT });
  assert.equal(ok.ok, true);
  assert.equal(ok.residency.budget.vram_budget_mb, 24576);
  assert.equal(ok.residency.snapshot.used_vram_mb, 4000);

  // a null snapshot is legitimate (no planner could be built) as long as the budget is there
  const noPlanner = { schema: "host_residency@1.0",
    budget: { vram_budget_mb: null, established: false, estimate: true, budget_source: "falsified" },
    snapshot: null };
  const degraded = await fetchHostResidency({ spawn: fakeSpawn({ stdout: JSON.stringify(noPlanner) }), cwd: REPO_ROOT });
  assert.equal(degraded.ok, true);
  assert.equal(degraded.residency.budget.established, false);

  // …and every failure mode is fail-closed: NEVER throws, never yields a fabricated budget
  for (const bad of [{ stdout: "not json" }, { stdout: JSON.stringify({ schema: "other@1.0", budget: {} }) },
    { stdout: JSON.stringify({ schema: "host_residency@1.0" }) }, { code: 3 }]) {
    const res = await fetchHostResidency({ spawn: fakeSpawn(bad), cwd: REPO_ROOT });
    assert.equal(res.ok, false, `${JSON.stringify(bad)} must not be accepted`);
    assert.equal(res.residency, null);
  }
});

test("the residency contract validates the FIELDS a consumer computes with, not just the schema string", () => {
  // `host_residency@1.0` has no file in schemas/ (U104), so this predicate IS the contract. A
  // version that checked only the schema string would let the self-check derive a VRAM budget from
  // numbers nothing had validated (spec-audit MAJOR-1, 2026-07-26).
  const budget = { vram_budget_mb: 24576, established: true, estimate: true, budget_source: "x" };
  const snap = { total_vram_mb: 24576, used_vram_mb: 4000, free_vram_mb: 20576,
    models: [{ model: "a:8b", footprint_mb: 4000, status: "resident" }] };
  assert.equal(isWellFormedResidency({ schema: "host_residency@1.0", budget, snapshot: snap }), true);
  assert.equal(isWellFormedResidency({ schema: "host_residency@1.0", budget, snapshot: null }), true);
  const bad = [
    { budget, snapshot: { ...snap, used_vram_mb: null } },
    { budget, snapshot: { ...snap, used_vram_mb: "4000" } },
    { budget, snapshot: { ...snap, total_vram_mb: undefined } },
    { budget, snapshot: { ...snap, models: "none" } },
    { budget, snapshot: { ...snap, models: [{ model: "a:8b", status: "resident" }] } },
    { budget, snapshot: { ...snap, models: [{ footprint_mb: 4000, status: "resident" }] } },
    { budget, snapshot: { ...snap, models: [{ model: "a:8b", footprint_mb: 4000 }] } },
    { budget: { vram_budget_mb: 1 }, snapshot: null },
  ];
  for (const b of bad) {
    assert.equal(isWellFormedResidency({ schema: "host_residency@1.0", ...b }), false,
      `must be refused: ${JSON.stringify(b).slice(0, 90)}`);
  }
});
