"use strict";
/**
 * CONDUCTOR model-probe SOURCE tests (Phase 17A `.roundtrip`).
 *
 * The shell must never launch the live conductor with a `--model` slug the host CLI rejects — that
 * is exactly what produced a running session which answered every prompt with "There's an issue with
 * the selected model (fable-5)". These tests pin the read-side contract:
 *
 *   (1) unit — a FAKE spawn proves the parse + fail-closed fold: an accepted slug, a recorded
 *       CLI-default fallback, a governed refusal, a shape drift, a non-zero exit, a timeout, and a
 *       spawn error. EVERY failure path must resolve to `unprobed` (model_available null), because
 *       "could not probe" must never silently strip the operator's selected model;
 *   (2) live integration — the REAL `py -3.12` emitter is invoked in `--ledger-only` mode (offline,
 *       spends nothing) and its payload validated. Skips without py.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  MODEL_PROBE_SCHEMA, PROBE_EMITTER, sourceConductorModelProbe, isWellFormedProbe, unprobed,
  describeProbe, modelProbeStrategy, unprobedDescriptorResult,
} = require("../conductor/model-probe-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const ACCEPTED = {
  schema: MODEL_PROBE_SCHEMA,
  ok: true,
  refused: false,
  reason: null,
  label: "fable-5",
  source: "probed",
  spent_live_call: true,
  resolution: { label: "fable-5", model: "claude-fable-5", model_available: true, source: "probe-ledger" },
  record: { accepted_slug: "claude-fable-5", checkpoint: "claude-fable-5-20260701", conclusive: true },
};

const FALLBACK = {
  ...ACCEPTED,
  resolution: { label: "fable-5", model: null, model_available: false, source: "probe-ledger" },
  record: { accepted_slug: null, checkpoint: null, conclusive: true, is_fallback: true },
};

const REFUSED = {
  schema: MODEL_PROBE_SCHEMA,
  ok: false,
  refused: true,
  reason: "SubscriptionLimitExceeded: allowance 2 already in use",
  label: "fable-5",
  source: "refused",
  spent_live_call: false,
  resolution: { label: "fable-5", model: null, model_available: null, source: "unprobed" },
  record: null,
};

function fakeSpawn({ stdout = "", stderr = "", code = 0, neverExit = false, throwOnSpawn = false,
  emitError = null } = {}) {
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

// ---- (1) unit: fake spawn ---------------------------------------------------
test("an accepted slug is parsed and reported as available", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(ACCEPTED) });
  const res = await sourceConductorModelProbe({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, true);
  assert.equal(res.probe.resolution.model, "claude-fable-5");
  assert.equal(res.probe.resolution.model_available, true);
  assert.deepEqual(spawn.calls[0].args.slice(-2), [PROBE_EMITTER, "--emit-model-probe"]);
  assert.match(describeProbe(res.probe), /ACCEPTED/);
});

test("a conclusive fallback is reported as unavailable — and SAYS so", async () => {
  const res = await sourceConductorModelProbe({ spawn: fakeSpawn({ stdout: JSON.stringify(FALLBACK) }), cwd: REPO_ROOT });
  assert.equal(res.probe.resolution.model, null);
  assert.equal(res.probe.resolution.model_available, false);
  assert.match(describeProbe(res.probe), /CLI default and RECORDING the fallback/);
});

test("flags are passed through (label / reprobe / ledger-only)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(ACCEPTED) });
  await sourceConductorModelProbe({ spawn, cwd: REPO_ROOT, label: "opus-4.8", reprobe: true, ledgerOnly: true });
  assert.deepEqual(spawn.calls[0].args.slice(-6),
    [PROBE_EMITTER, "--emit-model-probe", "--label", "opus-4.8", "--reprobe", "--ledger-only"]);
});

test("a governed refusal is surfaced as-is and leaves the launch unprobed", async () => {
  const res = await sourceConductorModelProbe({ spawn: fakeSpawn({ stdout: JSON.stringify(REFUSED) }), cwd: REPO_ROOT });
  assert.equal(res.ok, true);              // a well-formed payload was parsed…
  assert.equal(res.probe.refused, true);   // …and it is a refusal
  assert.equal(res.probe.resolution.model_available, null);
  assert.match(describeProbe(res.probe), /UNPROBED/);
});

test("EVERY failure path resolves to unprobed — never to unavailable", async () => {
  const drift = { ...ACCEPTED, schema: "conductor_model_probe@9.9" };
  const badResolution = { ...ACCEPTED, resolution: { model: "x", model_available: "yes", source: "s" } };
  const cases = [
    ["shape drift", fakeSpawn({ stdout: JSON.stringify(drift) })],
    ["bad resolution", fakeSpawn({ stdout: JSON.stringify(badResolution) })],
    ["non-JSON", fakeSpawn({ stdout: "not json" })],
    ["non-zero exit", fakeSpawn({ code: 2, stderr: "usage" })],
    ["spawn throws", fakeSpawn({ throwOnSpawn: true })],
    ["spawn error", fakeSpawn({ emitError: "EPERM" })],
  ];
  for (const [what, spawn] of cases) {
    const res = await sourceConductorModelProbe({ spawn, cwd: REPO_ROOT });
    assert.equal(res.ok, false, what);
    assert.equal(res.probe.resolution.model_available, null, what);
    assert.equal(res.probe.resolution.source, "unprobed", what);
    assert.equal(res.probe.resolution.model, null, what);
  }
});

test("a hung emitter times out into the unprobed shape", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  const res = await sourceConductorModelProbe({ spawn, cwd: REPO_ROOT, timeoutMs: 30 });
  assert.equal(res.ok, false);
  assert.match(res.error, /timed out/);
  assert.equal(res.probe.resolution.model_available, null);
});

test("isWellFormedProbe rejects the tri-state being widened", () => {
  assert.equal(isWellFormedProbe(ACCEPTED), true);
  assert.equal(isWellFormedProbe({ ...ACCEPTED, resolution: { model: "", model_available: true, source: "s" } }), false);
  assert.equal(isWellFormedProbe({ ...ACCEPTED, resolution: { model: null, model_available: 1, source: "s" } }), false);
  assert.equal(isWellFormedProbe({ ...ACCEPTED, ok: "true" }), false);
  assert.equal(isWellFormedProbe(null), false);
  assert.equal(unprobed("why").resolution.model_available, null);
});

test("a registered descriptor is not fabricated into proof that its model is available", () => {
  assert.equal(modelProbeStrategy({ adapter_id: "claude_code" }), "host_probe");
  for (const adapter_id of ["openai_codex_cli", "grok_build", "unknown"]) {
    const res = unprobedDescriptorResult({ adapter_id, display_name: adapter_id });
    assert.equal(modelProbeStrategy({ adapter_id }), "unprobed");
    assert.equal(res.ok, false);
    assert.equal(res.probe.resolution.model_available, null);
    assert.match(res.probe.reason, /no host model probe/);
  }
});

// ---- (2) live integration: the real emitter, offline mode -------------------
test("the REAL emitter answers --ledger-only without spending anything", { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
  const res = await sourceConductorModelProbe({ cwd: REPO_ROOT, ledgerOnly: true, timeoutMs: 60000 });
  assert.equal(res.ok, true, res.error || "");
  assert.equal(res.probe.schema, MODEL_PROBE_SCHEMA);
  assert.equal(res.probe.spent_live_call, false);
  // Either the host has a recorded verdict, or it has none — both are honest; a widened tri-state
  // is not.
  assert.ok([true, false, null].includes(res.probe.resolution.model_available));
});
