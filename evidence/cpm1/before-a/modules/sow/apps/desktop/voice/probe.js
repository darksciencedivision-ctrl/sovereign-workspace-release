"use strict";
/**
 * Non-blocking STT-engine probe — Phase 17C `.probe` (directive §16 track 17C; closes U74 / OP-11
 * finding F1).
 *
 * THE DEFECT THIS CLOSES. The operator's shell badged **"mock engine"** on a host where WSL Parakeet is
 * installed and verified. Two causes, both Python-side and both now fixed
 * (adapters/voice_parakeet/wsl_parakeet.py): an 8 s probe budget against a NeMo ASR import measured at
 * 7–18 s on this host, and an `lru_cache(maxsize=1)` that pinned the first (cold, failed) answer for the
 * life of the process. But a third cause is architectural and lives HERE: the engine state was only ever
 * learned as a side effect of a CAPTURE. Raising the budget to 90 s without moving the probe off the
 * chrome's path would trade a lie for a stall.
 *
 * So this module owns the probe as its own asynchronous fact:
 *   - `state()` is SYNCHRONOUS and instant, always. It answers with what is known NOW — `unprobed`,
 *     `probing`, `available`, or `unavailable` — and never waits on WSL.
 *   - `start()` kicks a probe in the background (idempotent: a probe already in flight is joined, not
 *     duplicated). `refresh()` forces a fresh one — the "re-probe on demand" path (a talk press, an
 *     operator retry after finishing the install).
 *   - a NEGATIVE answer is NOT sticky: `state()` lets it expire after `negativeTtlMs`, so the shell
 *     re-probes instead of pinning one cold miss for the session. A POSITIVE answer is held for
 *     `positiveTtlMs` (a venv does not uninstall itself mid-session).
 *
 * HONESTY (invariant 3; directive §16 track 17C — never silently pretend to hear). `probing` and
 * `unprobed` are distinct from `unavailable` and MUST render as such: the renderer's engine indicator
 * has four states for exactly this reason. `available` is set ONLY from a `sourced:true` feed whose
 * `engine.real_available` is true — a fault, a timeout, a non-zero exit, or a malformed payload all
 * yield `unavailable` with the reason NAMED, never a claimed real engine, and never a thrown error into
 * the always-visible chrome.
 *
 * NO TTS (I-V2/D-VOICE-02): the probe reports a recognition engine only; `tts` is carried false.
 * Injectable (`spawn`, `now`) so every branch is unit-tested with a fake process and a fake clock —
 * apps/desktop/test/voice-probe.test.js.
 */
const { spawn: realSpawn } = require("child_process");
const { scrubCredentialEnv } = require("./env-scrub");

const VOICE_PROBE_FEED_SCHEMA = "voice_probe_feed@1.0";

// The four states the shell can be in about speech recognition. `unprobed` and `probing` exist so an
// unanswered question is never rendered as a negative answer (U74/F1).
const UNPROBED = "unprobed";
const PROBING = "probing";
const AVAILABLE = "available";
const UNAVAILABLE = "unavailable";

// The Python-side default budget (adapters/voice_parakeet/wsl_parakeet.PROBE_TIMEOUT_S). Duplicated
// here on purpose — this process cannot import Python — and PINNED to it by a test
// (apps/desktop/test/voice-probe.test.js reads the constant out of the Python source), so the two
// cannot drift apart silently.
const PYTHON_PROBE_BUDGET_S = 90;
// How much longer than the Python budget this side waits before giving up: interpreter start, WSL VM
// start, and JSON round-trip. A ceiling BELOW the Python budget would kill an honest slow probe and
// report "unavailable" for a merely-cold host — U74 reintroduced from the JS side.
const CEILING_MARGIN_MS = 30000;
const DEFAULT_TIMEOUT_MS = PYTHON_PROBE_BUDGET_S * 1000 + CEILING_MARGIN_MS;
const DEFAULT_POSITIVE_TTL_MS = 900000; // 15 min — pinned to PROBE_POSITIVE_TTL_S by test
const DEFAULT_NEGATIVE_TTL_MS = 30000;  // 30 s — pinned to PROBE_NEGATIVE_TTL_S by test

/**
 * The ceiling this side must honour, given the budget PYTHON will actually use.
 *
 * `SOW_NEMO_PROBE_TIMEOUT_S` is the documented remedy for a slow host — it is the lever this unit's own
 * self-check pulls. Read only Python-side, it becomes a trap: Python waits 300 s, this side kills the
 * child at its wired-in ceiling, the fault folds to `unavailable`, and the badge says "mock engine" on a
 * host where Parakeet is installed. That is U74, reproduced by applying the fix for U74. So the ceiling
 * is DERIVED from the same env var, and can only ever exceed the budget in force.
 */
function ceilingForEnv(env = process.env, floorMs = DEFAULT_TIMEOUT_MS) {
  const raw = env && env.SOW_NEMO_PROBE_TIMEOUT_S;
  const budgetS = raw == null || String(raw).trim() === "" ? NaN : Number(raw);
  const budgetMs = Number.isFinite(budgetS) && budgetS > 0 ? budgetS * 1000 : PYTHON_PROBE_BUDGET_S * 1000;
  return Math.max(floorMs, budgetMs + CEILING_MARGIN_MS);
}

// A payload is a usable probe feed only if it carries the pinned schema and an `engine` object. A
// drifted producer cannot pass (the same rule voice-source.js applies to the capture feed).
function isWellFormedProbeFeed(f) {
  if (!f || typeof f !== "object" || f.schema !== VOICE_PROBE_FEED_SCHEMA) return false;
  const e = f.engine;
  return !!e && typeof e === "object" && !Array.isArray(e);
}

// The fail-closed engine descriptor: a VISIBLE mock, never a claimed real engine.
function unavailableEngine(reason) {
  return {
    name: "unknown",
    mock: true,
    real_available: false,
    probing: false,
    nemo_state: UNAVAILABLE,
    probe: null,
    real_engine: null,
    detection: {},
    reason,
  };
}

class VoiceProbe {
  /**
   * @param {object} opts {cwd, spawn?, python?, pythonArgs?, timeoutMs?, positiveTtlMs?,
   *                       negativeTtlMs?, now?, log?}
   */
  constructor(opts = {}) {
    this.cwd = opts.cwd;
    this._spawn = opts.spawn || realSpawn;
    this.python = opts.python || "py";
    this.pythonArgs = opts.pythonArgs || ["-3.12"];
    this.timeoutMs = Number.isFinite(opts.timeoutMs) && opts.timeoutMs > 0
      ? opts.timeoutMs
      : ceilingForEnv(opts.env || process.env);
    this.positiveTtlMs = Number.isFinite(opts.positiveTtlMs) ? opts.positiveTtlMs : DEFAULT_POSITIVE_TTL_MS;
    this.negativeTtlMs = Number.isFinite(opts.negativeTtlMs) ? opts.negativeTtlMs : DEFAULT_NEGATIVE_TTL_MS;
    this._env = opts.childEnv || null;   // test seam; production uses the credential scrub (U136)
    this._now = opts.now || (() => Date.now());
    this._log = opts.log || (() => {});
    this._result = null;   // {state, engine, reason, at, elapsedMs}
    this._inFlight = null; // the Promise of the probe currently running, if any
    this._startedAt = null;
    this._probes = 0;      // how many real probes this shell has taken (receipt evidence)
  }

  /** How many real probes have been STARTED — the measurement that falsifies "cached for the app's life". */
  get probeCount() { return this._probes; }

  /** Has the last result outlived its TTL? A negative expires fast so it is never sticky (U74). */
  _expired() {
    if (!this._result) return true;
    const ttl = this._result.state === AVAILABLE ? this.positiveTtlMs : this.negativeTtlMs;
    return this._now() - this._result.at >= ttl;
  }

  /**
   * SYNCHRONOUS and instant — the always-visible chrome's read. Never spawns, never awaits, never throws.
   *
   * THE THREE ANSWERS, and why there is no fourth. `probing` is claimed ONLY while a child is genuinely
   * running: an earlier revision of this file returned `probing:true` for any expired result, which is
   * how the reviews of this unit found it asserting an activity nothing was performing — U74's own shape
   * (one answer decides the whole run) inverted into a permanently pinned "in progress". A result that
   * has outlived its TTL is still the last thing this host actually established, so it is reported AS
   * that, marked `stale`, while `ensureFresh()` re-takes it. Only a host that has never been probed
   * AND has no probe running is `unprobed`.
   *
   * @returns {{state, engine, reason, probing, stale, elapsedMs, since, probeCount}}
   */
  state() {
    if (this._inFlight) {
      // Nothing has been established yet: the first probe of the process is genuinely an open question.
      // A RE-probe over a known answer keeps showing that answer (below) rather than flickering.
      if (!this._result) {
        return {
          state: PROBING,
          engine: { ...unavailableEngine("probing the WSL NeMo stack…"), probing: true, nemo_state: UNPROBED },
          reason: "probing the WSL NeMo stack…",
          probing: true,
          stale: false,
          elapsedMs: this._startedAt == null ? 0 : this._now() - this._startedAt,
          since: this._startedAt,
          probeCount: this._probes,
        };
      }
      return { ...this._result, probing: false, stale: true, reprobing: true, probeCount: this._probes };
    }
    if (!this._result) {
      // Never probed and nothing running. This is NOT "probing" — saying so would advertise work that
      // is not happening. `ensureFresh()` is what turns this state into a real probe.
      return {
        state: UNPROBED,
        engine: { ...unavailableEngine("the STT engine has not been probed yet"), probing: false, nemo_state: UNPROBED },
        reason: "the STT engine has not been probed yet",
        probing: false,
        stale: false,
        elapsedMs: 0,
        since: null,
        probeCount: this._probes,
      };
    }
    // An expired answer is still the last ESTABLISHED fact — report it, flagged stale, never as a
    // question the shell is not currently asking.
    return { ...this._result, probing: false, stale: this._expired(), probeCount: this._probes };
  }

  /**
   * The read the chrome should use: `state()`, plus the guarantee that a probe is UNDERWAY whenever the
   * answer is missing or stale. This is what makes "probing…" true whenever it is shown, and it is what
   * delivers directive §16 track 17C's *"re-probe on demand and after failure"* in the product rather
   * than only in the API — a negative expires after 30 s and the next repaint re-takes it, so an
   * operator who finishes the NeMo install does not have to restart the shell.
   *
   * Fire-and-forget: the returned STATE is synchronous; the probe (if one was started) settles later
   * and the caller is expected to push the updated state then.
   */
  ensureFresh() {
    if (!this._inFlight && (!this._result || this._expired())) {
      const p = this._run(false);
      if (this._onSettle) p.then((s) => { try { this._onSettle(s); } catch { /* never throw from a push */ } });
    }
    return this.state();
  }

  /** Register the callback fired when a probe started by `ensureFresh()` settles (the chrome push). */
  onSettle(cb) { this._onSettle = cb; }

  /** Start a probe if none is in flight and the last answer is stale; returns the settled state. */
  start() {
    if (this._inFlight) return this._inFlight;
    if (this._result && !this._expired()) return Promise.resolve(this.state());
    return this._run(false);
  }

  /**
   * D-LOOP-1: abandon any in-flight probe at teardown. The child is killed; note honestly that on
   * Windows killing `py.exe` does NOT reap the `wsl.exe` grandchild it spawned, so a NeMo import
   * already running inside the WSL VM finishes on its own (bounded by the Python budget). Recorded
   * rather than claimed away.
   */
  dispose() {
    const child = this._child;
    this._child = null;
    try { if (child) child.kill(); } catch { /* already gone */ }
    return { killed: Boolean(child), wsl_grandchild_note: "wsl.exe grandchild is not tree-killed on Windows; it exits on its own within the probe budget" };
  }

  /** Force a fresh probe NOW, ignoring any cached answer (the on-demand / after-failure path). */
  refresh() {
    if (this._inFlight) return this._inFlight;
    return this._run(true);
  }

  _run(force) {
    this._probes += 1;
    this._startedAt = this._now();
    const args = ["tools/live/emit_conductor_voice.py", "--emit-voice-probe"];
    if (force) args.push("--force");
    this._inFlight = this._spawnOnce(args)
      .then((feed) => this._settle(feed, null))
      .catch((err) => this._settle(null, err))
      .then((state) => { this._inFlight = null; return state; });
    return this._inFlight;
  }

  // Record the outcome. `available` requires a sourced feed that positively says so — anything else,
  // including a fault, is `unavailable` with its reason named (fail-closed, never a claimed engine).
  _settle(feed, err) {
    const at = this._now();
    const elapsedMs = at - this._startedAt;
    // The producer can legitimately answer "not asked yet" (`--cached-only`, or any non-blocking mode).
    // Recording that as an answered NEGATIVE would discard the one distinction this whole unit exists
    // to preserve and render it "mock engine" — F1, reintroduced at the process boundary. It is stored
    // as nothing at all, so the next read re-probes.
    if (!err && feed && feed.sourced === true && feed.engine
        && feed.engine.real_available !== true
        && (feed.engine.probing === true || feed.engine.nemo_state === UNPROBED)) {
      this._result = null;
      this._log(`[voice:probe] producer has not answered yet (${(feed.engine.reason || "unprobed")}) — not recorded`);
      return { state: UNPROBED, engine: feed.engine, reason: String(feed.engine.reason || "not probed yet"),
               probing: false, stale: false, elapsedMs, probeCount: this._probes };
    }
    if (err || !feed || feed.sourced !== true) {
      const reason = err ? `${err.name || "Error"}: ${err.message}` : (feed && feed.reason) || "voice probe unavailable";
      this._result = { state: UNAVAILABLE, engine: unavailableEngine(reason), reason, at, elapsedMs };
    } else {
      const engine = feed.engine || {};
      const available = engine.real_available === true;
      const reason = String(engine.reason || feed.reason || "");
      this._result = {
        state: available ? AVAILABLE : UNAVAILABLE,
        // `mock` answers "did a MOCK engine produce the transcript?" — and a probe produces NO
        // transcript at all, so the answer is always yes-by-default here: nothing real has spoken. It
        // is `real_available` that carries what the probe actually learned. Pinning `mock:true` is what
        // makes the chrome render the READY state ("parakeet-wsl ready") rather than the REAL state
        // ("parakeet-wsl"), which would assert a real transcription that never happened — the same
        // pretend-to-hear the visible-mock rule exists to prevent, just in the other direction.
        engine: { ...engine, mock: true, probing: false },
        reason,
        at,
        elapsedMs,
      };
    }
    this._log(`[voice:probe] ${this._result.state} in ${elapsedMs}ms — ${this._result.reason}`);
    return { ...this._result, probing: false, probeCount: this._probes };
  }

  // Bounded one-shot emitter run. Rejects on launch error / timeout / non-zero exit / non-JSON /
  // malformed shape; the caller folds every rejection into the fail-closed `unavailable` state.
  _spawnOnce(args) {
    return new Promise((resolve, reject) => {
      let child;
      try {
        // U136: the LAUNCH probe — the one that runs on every shell start — reaches `wsl.exe`, where
        // `WSLENV` can carry named host variables into the VM. It inherited `process.env` wholesale,
        // so an operator who launched the shell from a terminal with a provider key exported handed
        // that key to a local child and potentially across the WSL boundary. §2.2 does not stop at the
        // governed launch paths. Injectable so a test can pin the scrub without a real host.
        child = this._spawn(this.python, [...this.pythonArgs, ...args],
          { cwd: this.cwd, env: this._env || scrubCredentialEnv().env });
        this._child = child;   // held so `dispose()` can abandon an in-flight probe at teardown
      } catch (e) {
        reject(new Error(`could not launch the voice probe: ${e.message}`));
        return;
      }
      let out = "";
      let errOut = "";
      let settled = false;
      const finish = (fn, arg) => {
        if (settled) return;
        settled = true;
        clearTimeout(to);
        try { child.kill(); } catch { /* already gone */ }
        if (this._child === child) this._child = null;
        fn(arg);
      };
      const to = setTimeout(
        () => finish(reject, new Error(`voice probe timed out after ${this.timeoutMs}ms`)),
        this.timeoutMs,
      );
      if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
      if (child.stderr) child.stderr.on("data", (d) => { errOut += d.toString(); });
      child.on("error", (e) => finish(reject, new Error(`voice probe failed to run: ${e.message}`)));
      child.on("exit", (code) => {
        if (code !== 0) {
          finish(reject, new Error(`voice probe exited ${code}${errOut ? `: ${errOut.trim().slice(0, 200)}` : ""}`));
          return;
        }
        let parsed;
        try { parsed = JSON.parse(out); }
        catch (e) { finish(reject, new Error(`voice probe emitted non-JSON: ${e.message}`)); return; }
        if (!isWellFormedProbeFeed(parsed)) { finish(reject, new Error("voice probe emitted a malformed feed")); return; }
        finish(resolve, parsed);
      });
    });
  }
}

module.exports = {
  VoiceProbe,
  VOICE_PROBE_FEED_SCHEMA,
  isWellFormedProbeFeed,
  unavailableEngine,
  ceilingForEnv,
  UNPROBED, PROBING, AVAILABLE, UNAVAILABLE,
  DEFAULT_TIMEOUT_MS, DEFAULT_POSITIVE_TTL_MS, DEFAULT_NEGATIVE_TTL_MS,
  PYTHON_PROBE_BUDGET_S, CEILING_MARGIN_MS,
};
