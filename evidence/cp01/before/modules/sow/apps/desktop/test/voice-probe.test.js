"use strict";
/**
 * Non-blocking STT-engine probe tests — Phase 17C `.probe` (U74 / OP-11 finding F1).
 *
 * The defect: the operator's shell said "mock engine" on a host where WSL Parakeet is installed and
 * verified. Python-side that was an 8 s budget against a 7–18 s import and an `lru_cache(1)` that
 * pinned the first cold miss; shell-side it was that the engine state was learned only as a side
 * effect of a capture, so raising the budget alone would have traded a lie for a stall.
 *
 * These tests pin the four properties that make the raised budget safe and the answer honest, with a
 * FAKE spawn + a FAKE clock so every branch is deterministic on any host:
 *   (1) `state()` is instant and never blocks — including WHILE a probe is in flight;
 *   (2) an unanswered probe reads `probing`/`unprobed`, never `unavailable` (the F1 distinction);
 *   (3) a NEGATIVE answer expires and is re-taken — nothing is pinned for the process lifetime;
 *   (4) every fault (timeout / non-zero exit / non-JSON / malformed / launch failure) settles as
 *       `unavailable` with the reason NAMED, and never as a claimed real engine.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const {
  VoiceProbe, VOICE_PROBE_FEED_SCHEMA, isWellFormedProbeFeed,
} = require("../voice/probe");

const AVAILABLE_FEED = {
  schema: VOICE_PROBE_FEED_SCHEMA,
  sourced: true,
  reason: "NeMo ASR imports in the WSL venv",
  engine: {
    name: "parakeet-wsl", mock: true, real_available: true, probing: false,
    nemo_state: "available", probe: { state: "available", available: true, elapsed_s: 7.02, timeout_s: 90 },
    real_engine: "parakeet-wsl", detection: { nvidia_gpu: true, wsl: true, nemo: true }, reason: "NeMo ASR imports in the WSL venv",
  },
  blocking: true, forced: false, tts: false,
};

const UNAVAILABLE_FEED = {
  schema: VOICE_PROBE_FEED_SCHEMA,
  sourced: true,
  reason: "the NeMo ASR import exited 1",
  engine: {
    name: "mock-stt", mock: true, real_available: false, probing: false,
    nemo_state: "unavailable", probe: { state: "unavailable", available: false, elapsed_s: 1.1, timeout_s: 90 },
    real_engine: null, detection: { nvidia_gpu: true, wsl: true, nemo: false }, reason: "the NeMo ASR import exited 1",
  },
  blocking: true, forced: false, tts: false,
};

// A spawn whose child exits only when `release()` is called — so "in flight" is a real, observable
// state rather than a race. `scripts` lets successive probes return different payloads.
function controllableSpawn(scripts) {
  const calls = [];
  const pending = [];
  const spawn = (cmd, args, opts) => {
    const script = scripts[Math.min(calls.length, scripts.length - 1)] || {};
    calls.push({ cmd, args, opts });
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => { child.killed = true; };
    child.killed = false;
    const fire = () => {
      if (script.throwOnSpawn) return;
      if (script.emitError) { child.emit("error", new Error(script.emitError)); return; }
      if (script.stdout) child.stdout.emit("data", Buffer.from(script.stdout));
      if (script.stderr) child.stderr.emit("data", Buffer.from(script.stderr));
      if (!script.neverExit) child.emit("exit", script.code == null ? 0 : script.code);
    };
    if (script.manual) pending.push(fire); else setImmediate(fire);
    if (script.throwOnSpawn) throw new Error("ENOENT");
    return child;
  };
  return { spawn, calls, release: () => { const f = pending.shift(); if (f) f(); } };
}

function json(obj) { return JSON.stringify(obj) + "\n"; }

function probeWith(scripts, opts = {}) {
  const s = controllableSpawn(scripts);
  const clock = { t: 1000 };
  const p = new VoiceProbe({ cwd: ".", spawn: s.spawn, now: () => clock.t, timeoutMs: 5000, ...opts });
  return { p, s, clock };
}

// ---- (2) an unanswered question renders as one — the U74/F1 distinction ---------------------------
test("before any probe, state is UNPROBED and claims NO engine — and does not claim to be probing", () => {
  // `probing` is claimed only while a child is genuinely running. Saying it here would advertise work
  // that is not happening; `ensureFresh()` is what turns this state into a real probe.
  const { p } = probeWith([{ stdout: json(AVAILABLE_FEED) }]);
  const st = p.state();
  assert.equal(st.state, "unprobed");
  assert.equal(st.probing, false);
  assert.equal(st.engine.real_available, false); // claims no engine (fail-closed)
  assert.equal(st.engine.mock, true);
  assert.equal(st.probeCount, 0);
});

// ---- THE REGRESSION BOTH REVIEWS OF THIS UNIT CAUGHT ----------------------------------------------
test("an EXPIRED answer is reported as the last established fact, never as a probe that is not running", async () => {
  // An earlier revision returned `probing:true` for ANY expired result while nothing re-armed it, so
  // 30 s after the launch probe the chrome said "probing…" forever — U74's shape (one answer decides
  // the whole run) inverted into a permanently pinned "in progress". On a host with no NeMo it also
  // ERASED the honest "mock engine" the operator needs to act on.
  const { p, clock } = probeWith([{ stdout: json(UNAVAILABLE_FEED) }], { negativeTtlMs: 1000 });
  await p.start();
  clock.t += 5000;
  const st = p.state();
  assert.equal(st.probing, false);              // nothing is running, so nothing claims to be
  assert.equal(st.stale, true);                 // …and the staleness is stated, not hidden
  assert.equal(st.state, "unavailable");        // the last thing this host actually established
  assert.match(p.state().reason, /exited 1/);
});

test("ensureFresh() re-takes a stale answer — 're-probe after failure' in the product, not just the API", async () => {
  const { p, s, clock } = probeWith(
    [{ stdout: json(UNAVAILABLE_FEED) }, { stdout: json(AVAILABLE_FEED) }],
    { negativeTtlMs: 1000 },
  );
  await p.start();
  clock.t += 5000;
  const armed = p.ensureFresh();                // the read the chrome performs
  assert.equal(s.calls.length, 2);              // a REAL probe was started by the read
  assert.equal(armed.reprobing, true);          // …and while it runs, the last answer still shows
  assert.equal(armed.state, "unavailable");
  const settled = await p.start();
  assert.equal(settled.state, "available");     // the operator who finished the install is now seen
});

test("ensureFresh() on a fresh answer does NOT spawn", async () => {
  const { p, s } = probeWith([{ stdout: json(AVAILABLE_FEED) }], { positiveTtlMs: 100000 });
  await p.start();
  p.ensureFresh();
  p.ensureFresh();
  assert.equal(s.calls.length, 1);
});

test("onSettle fires for a probe the chrome's read armed (so the badge corrects itself)", async () => {
  const seen = [];
  const { p, clock } = probeWith(
    [{ stdout: json(UNAVAILABLE_FEED) }, { stdout: json(AVAILABLE_FEED) }],
    { negativeTtlMs: 1000 },
  );
  p.onSettle((s) => seen.push(s.state));
  await p.start();
  clock.t += 5000;
  p.ensureFresh();
  await p.start();
  assert.deepEqual(seen, ["available"]);
});

// ---- the producer's "not asked yet" survives the process boundary (F1 at the seam) ------------------
test("a producer answer of 'not asked yet' is NOT recorded as an answered negative", async () => {
  // `--cached-only` and any non-blocking producer mode can legitimately answer `probing/unprobed`.
  // Folding that into `unavailable` would discard the one distinction this unit exists to preserve and
  // render it "mock engine" — F1, reintroduced at the seam between the two languages.
  const unprobedFeed = {
    ...UNAVAILABLE_FEED,
    engine: { ...UNAVAILABLE_FEED.engine, real_available: false, probing: true, nemo_state: "unprobed",
              reason: "the WSL NeMo probe has not answered yet" },
  };
  const { p, s } = probeWith([{ stdout: json(unprobedFeed) }, { stdout: json(AVAILABLE_FEED) }]);
  const st = await p.start();
  assert.equal(st.state, "unprobed");
  assert.equal(p.state().state, "unprobed");    // nothing false was cached
  p.ensureFresh();                              // …so the next read re-probes rather than settling
  assert.equal(s.calls.length, 2);
});

// ---- the env budget must not be overridden by a wired-in JS ceiling (M-1) --------------------------
test("the JS ceiling is DERIVED from SOW_NEMO_PROBE_TIMEOUT_S, never below it", () => {
  const { ceilingForEnv, DEFAULT_TIMEOUT_MS, PYTHON_PROBE_BUDGET_S, CEILING_MARGIN_MS } = require("../voice/probe");
  assert.equal(ceilingForEnv({}), DEFAULT_TIMEOUT_MS);
  assert.equal(DEFAULT_TIMEOUT_MS, PYTHON_PROBE_BUDGET_S * 1000 + CEILING_MARGIN_MS);
  // the operator's documented remedy for a slow host: Python waits 300 s, so this side must too —
  // otherwise applying the fix for U74 reproduces U74 (a killed probe badged "mock engine").
  assert.equal(ceilingForEnv({ SOW_NEMO_PROBE_TIMEOUT_S: "300" }), 330000);
  assert.ok(ceilingForEnv({ SOW_NEMO_PROBE_TIMEOUT_S: "5" }) >= DEFAULT_TIMEOUT_MS); // never below the floor
  for (const bad of ["", "  ", "abc", "0", "-3"]) {
    assert.equal(ceilingForEnv({ SOW_NEMO_PROBE_TIMEOUT_S: bad }), DEFAULT_TIMEOUT_MS);
  }
  const { captureCeilingForEnv, PYTHON_TRANSCRIBE_BUDGET_S } = require("../voice/voice-source");
  assert.equal(captureCeilingForEnv({}), PYTHON_TRANSCRIBE_BUDGET_S * 1000 + 30000);
  assert.equal(captureCeilingForEnv({ SOW_NEMO_TRANSCRIBE_TIMEOUT_S: "600" }), 630000);
});

// ---- the two languages' constants are PINNED, not merely commented as "matching" -------------------
test("the JS budget/TTL constants match the Python source they duplicate", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const py = fs.readFileSync(
    path.resolve(__dirname, "..", "..", "..", "adapters", "voice_parakeet", "wsl_parakeet.py"), "utf8",
  );
  const num = (name) => {
    const m = py.match(new RegExp(`^${name} = ([0-9.]+)`, "m"));
    assert.ok(m, `${name} not found in wsl_parakeet.py`);
    return Number(m[1]);
  };
  const { PYTHON_PROBE_BUDGET_S, DEFAULT_POSITIVE_TTL_MS, DEFAULT_NEGATIVE_TTL_MS } = require("../voice/probe");
  const { PYTHON_TRANSCRIBE_BUDGET_S } = require("../voice/voice-source");
  assert.equal(PYTHON_PROBE_BUDGET_S, num("PROBE_TIMEOUT_S"));
  assert.equal(PYTHON_TRANSCRIBE_BUDGET_S, num("TRANSCRIBE_TIMEOUT_S"));
  assert.equal(DEFAULT_POSITIVE_TTL_MS / 1000, num("PROBE_POSITIVE_TTL_S"));
  assert.equal(DEFAULT_NEGATIVE_TTL_MS / 1000, num("PROBE_NEGATIVE_TTL_S"));
  // …and the budget still satisfies the directive's floor for track 17C.
  assert.ok(num("PROBE_TIMEOUT_S") >= 60);
});

test("WHILE a probe is in flight, state() answers instantly with PROBING and does not block", () => {
  const { p, s } = probeWith([{ stdout: json(AVAILABLE_FEED), manual: true }]);
  const settled = p.start();
  const st = p.state();                        // called with the child still running
  assert.equal(st.state, "probing");
  assert.equal(st.probing, true);
  assert.equal(st.probeCount, 1);
  s.release();
  return settled.then((final) => {
    assert.equal(final.state, "available");
    assert.equal(p.state().probing, false);
  });
});

// ---- (1)+(3) the cache is a TTL, not a lifetime pin -----------------------------------------------
test("a NEGATIVE answer expires and is re-taken — the lru_cache(1) defect cannot recur", async () => {
  const { p, s, clock } = probeWith(
    [{ stdout: json(UNAVAILABLE_FEED) }, { stdout: json(AVAILABLE_FEED) }],
    { negativeTtlMs: 1000, positiveTtlMs: 100000 },
  );
  assert.equal((await p.start()).state, "unavailable");
  assert.equal(s.calls.length, 1);
  await p.start();                             // still fresh ⇒ no second spawn
  assert.equal(s.calls.length, 1);
  clock.t += 1500;                             // TTL passes
  assert.equal(p.state().stale, true);         // the answer is no longer current — and says so
  assert.equal((await p.start()).state, "available"); // …and the operator's finished install is seen
  assert.equal(s.calls.length, 2);
});

test("a POSITIVE answer is reused within its TTL (a venv does not uninstall itself mid-session)", async () => {
  const { p, s, clock } = probeWith([{ stdout: json(AVAILABLE_FEED) }], { negativeTtlMs: 1000, positiveTtlMs: 100000 });
  await p.start();
  clock.t += 50000;
  assert.equal(p.state().state, "available");
  assert.equal(p.state().stale, false);
  await p.start();
  assert.equal(s.calls.length, 1);
  clock.t += 60000;                            // past the positive TTL
  assert.equal(p.state().state, "available");  // still the last established fact…
  assert.equal(p.state().stale, true);         // …but no longer current, and it says so
});

test("refresh() re-takes the probe on demand even with a fresh cached answer", async () => {
  const { p, s } = probeWith([{ stdout: json(UNAVAILABLE_FEED) }, { stdout: json(AVAILABLE_FEED) }]);
  await p.start();
  assert.equal(s.calls.length, 1);
  const st = await p.refresh();                // the operator's retry after finishing the install
  assert.equal(st.state, "available");
  assert.equal(s.calls.length, 2);
  assert.ok(s.calls[1].args.includes("--force"));
  assert.equal(p.probeCount, 2);
});

test("concurrent starts JOIN one probe rather than spawning a storm", async () => {
  const { p, s } = probeWith([{ stdout: json(AVAILABLE_FEED), manual: true }]);
  const a = p.start();
  const b = p.start();
  const c = p.refresh();
  s.release();
  const [ra, rb, rc] = await Promise.all([a, b, c]);
  assert.equal(s.calls.length, 1);
  assert.equal(ra.state, "available");
  assert.deepEqual([rb.state, rc.state], ["available", "available"]);
});

// ---- (4) every fault is fail-closed, with the reason named ----------------------------------------
for (const [name, script, needle] of [
  ["a non-zero exit", { code: 3, stderr: "Traceback: boom" }, "exited 3"],
  ["non-JSON output", { stdout: "not json at all\n" }, "non-JSON"],
  ["a malformed feed", { stdout: json({ schema: "other@1.0", engine: {} }) }, "malformed"],
  ["a launch error", { emitError: "spawn py ENOENT" }, "failed to run"],
]) {
  test(`${name} settles as UNAVAILABLE with the reason named, never a claimed engine`, async () => {
    const { p } = probeWith([script]);
    const st = await p.start();
    assert.equal(st.state, "unavailable");
    assert.equal(st.engine.real_available, false);
    assert.equal(st.engine.mock, true);
    assert.equal(st.engine.probing, false);
    assert.match(st.reason, new RegExp(needle));
  });
}

test("a hung probe is killed at the ceiling and reported, never left in flight", async () => {
  const { p, s } = probeWith([{ neverExit: true }], { timeoutMs: 30 });
  const st = await p.start();
  assert.equal(st.state, "unavailable");
  assert.match(st.reason, /timed out after 30ms/);
  assert.equal(p.state().state, "unavailable");
  assert.equal(s.calls.length, 1);
});

test("a spawn that throws synchronously is reported, not raised into the chrome", async () => {
  const { p } = probeWith([{ throwOnSpawn: true }]);
  const st = await p.start();
  assert.equal(st.state, "unavailable");
  assert.match(st.reason, /could not launch the voice probe/);
});

// ---- the honesty rule: `available` requires Python to have said so --------------------------------
test("a sourced feed that does NOT say real_available can never become 'available'", async () => {
  const sneaky = { ...AVAILABLE_FEED, engine: { ...AVAILABLE_FEED.engine, real_available: false, mock: false } };
  const { p } = probeWith([{ stdout: json(sneaky) }]);
  const st = await p.start();
  assert.equal(st.state, "unavailable");        // `mock:false` alone never buys a real engine
  assert.equal(st.engine.mock, true);           // …and the descriptor is corrected, not carried through
});

test("an AVAILABLE probe never claims a real engine TRANSCRIBED anything", async () => {
  // The probe asks "is the real engine reachable", not "did it hear you". Reporting `mock:false` here
  // would make the chrome render the REAL state and assert a transcription that never happened — the
  // pretend-to-hear rule read in the other direction. The honest render is READY.
  const { p } = probeWith([{ stdout: json(AVAILABLE_FEED) }]);
  const st = await p.start();
  assert.equal(st.state, "available");
  assert.equal(st.engine.real_available, true);   // what the probe DID establish
  assert.equal(st.engine.mock, true);             // …and what it did not: no real transcript exists
  const { voiceEngineIndicator } = require("../../../terminal/compositor/voice-indicator");
  const ind = voiceEngineIndicator(st.engine);
  assert.equal(ind.ready, true);
  assert.equal(ind.real, false);
  assert.equal(ind.label, "parakeet-wsl ready");
});

test("an UNSOURCED feed is unavailable with the producer's own reason", async () => {
  const { p } = probeWith([{ stdout: json({ ...UNAVAILABLE_FEED, sourced: false, reason: "wsl gone" }) }]);
  const st = await p.start();
  assert.equal(st.state, "unavailable");
  assert.match(st.reason, /wsl gone/);
});

// ---- the emitter contract the shell parses --------------------------------------------------------
test("isWellFormedProbeFeed refuses a drifted producer", () => {
  assert.equal(isWellFormedProbeFeed(AVAILABLE_FEED), true);
  assert.equal(isWellFormedProbeFeed({ ...AVAILABLE_FEED, schema: "voice_probe_feed@2.0" }), false);
  assert.equal(isWellFormedProbeFeed({ schema: VOICE_PROBE_FEED_SCHEMA }), false);
  assert.equal(isWellFormedProbeFeed({ schema: VOICE_PROBE_FEED_SCHEMA, engine: [] }), false);
  assert.equal(isWellFormedProbeFeed(null), false);
});

test("the probe emitter is invoked with the engine-state-only flag (never the routing emitter)", async () => {
  const { p, s } = probeWith([{ stdout: json(AVAILABLE_FEED) }]);
  await p.start();
  const args = s.calls[0].args;
  assert.ok(args.includes("--emit-voice-probe"));
  assert.ok(!args.includes("--emit-conductor-voice"));  // a probe must not route an utterance
  assert.ok(!args.includes("--force"));                  // start() is not a forced re-probe
});

test("the LAUNCH probe's child gets a credential-scrubbed environment (U136)", async () => {
  // This is the probe that runs on every shell start, and it reaches `wsl.exe` — where `WSLENV` can
  // carry named host variables into the VM. It inherited `process.env` wholesale, so an operator who
  // launched the shell from a terminal with a provider key exported handed that key to a local child
  // and potentially across the WSL boundary. §2.2 does not stop at the governed launch paths.
  const { p, s } = probeWith([{ stdout: json(AVAILABLE_FEED) }]);
  await p.start();
  const env = s.calls[0].opts.env;
  assert.ok(env, "an env is passed explicitly — not inherited wholesale");
  assert.ok(env.PATH || env.Path, "the child can still find `py`");
  for (const k of Object.keys(env)) {
    assert.ok(!/^(ANTHROPIC_|AWS_|GOOGLE_|CLAUDE_CODE_)/i.test(k) && !/TOKEN|SECRET|API_KEY|APIKEY|PASSWORD/i.test(k),
      `${k} should have been scrubbed`);
  }
});
