"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * Conductor voice-IN read-source — Phase 16E `.engine` (closes the READ half of U67).
 *
 * The shell's talk button must route captured operator speech through the REAL `ConductorVoiceBridge`
 * and render the outcome (delivered chat / queued protected action / clarify) with a VISIBLE mock-engine
 * indicator. Phase 15E shipped the routing authority + the pure render model, but the shell's
 * `voice:propose` only RECORDED a push-to-talk hold — no engine, no transcript, nothing routed (U67).
 * This module closes the read half the SAME way the 16B picker and the 16C/16D feeds closed theirs — a
 * BOUNDED one-shot `py -3.12` read-source, NOT the WS-IPC channel:
 *   - `sourceConductorVoiceFeed` invokes `tools/live/emit_conductor_voice.py --emit-conductor-voice`,
 *     which routes ONE captured utterance (an `--audio-ref` stand-in) through the real bridge over a
 *     real broker (mock-first, no `claude`/`codex` process) and prints its outcome folded into
 *     `conductor_voice_feed@1.0`. Main folds `feed` through the pure `voice-indicator` view the JS
 *     tests already cover.
 *
 * SUBSTITUTION (directive §6, recorded): a bounded subprocess emitter, not the authenticated IPC
 * surface — swapping the shell's EchoControlSurface gateway would displace the supervisor's liveness
 * path (a first-launch regression class D-P16-0 warns against). Identical to `.statusbar`/`.approvals`.
 *
 * FAIL-CLOSED, by contract (invariant 3 / invariant 20 spirit): a timeout, a non-zero exit, non-JSON
 * output, or a malformed shape yields the UNAVAILABLE feed (`sourced:false`, a CLARIFY outcome, a
 * VISIBLE mock engine) — the shell renders an honest "voice unavailable", never a fabricated "delivered
 * to the conductor". This module never throws into the always-visible chrome.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process, with
 * zero dependence on a live host (apps/desktop/test/voice-source.test.js). Read-only glue: no model
 * call, no credential, no network here — the feed it sources is itself mock-first. NO TTS is carried
 * through (`feed.tts` is always false; I-V2/D-VOICE-02).
 *
 * NOTE (Phase 16E scope): this source is headlessly tested here; the shell WIRING (`voice:propose`
 * calling this, and delivering a CHAT transcript into the conductor ConPTY) + the in-Electron
 * self-check are the `.wire` sub-step. This file is not yet imported by the running shell.
 */
const { spawn: realSpawn } = require("child_process");
const { scrubCredentialEnv } = require("./env-scrub");

class VoiceSourceError extends Error {}

const CONDUCTOR_VOICE_FEED_SCHEMA = "conductor_voice_feed@1.0";

// The U67/16F record every feed carries — real mic capture + the live conductor ConPTY write are owed.
const LIVE_CAPTURE_OWED = Object.freeze({
  owed: true,
  issue: "16F",
  note: "the routing is real and the transcript is engine-selected; real mic capture + the live conductor ConPTY write are operator-run, owed to 16F.",
});

// A VISIBLE mock engine on the fail-closed path — never a claimed real engine (never pretend-to-hear).
function unavailableEngine() {
  return { name: "unknown", mock: true, real_available: false, detection: {}, reason: "engine unavailable (fail-closed)" };
}

// The unavailable voice feed — the fail-closed shape. NEVER a fabricated "delivered" (invariant 3):
// sourced:false, a CLARIFY outcome, a visible mock engine, the honest reason, no TTS.
function unavailableVoiceFeed(reason = "conductor voice feed unavailable", audioRef = null) {
  return {
    schema: CONDUCTOR_VOICE_FEED_SCHEMA,
    sourced: false,
    reason,
    engine: unavailableEngine(),
    outcome: { kind: "clarify", source: null, text: "", confidence: null, reason, queue_item_id: null },
    delivered: false,
    delivered_text: null,
    queued: false,
    needs_clarification: true,
    deliveries: [],
    tts: false,
    transcribe_then_discard: true,
    audio_ref: audioRef,
    live_capture_owed: { ...LIVE_CAPTURE_OWED },
    torn_down: true,
  };
}

// The Python default for a WSL transcription (wsl_parakeet.TRANSCRIBE_TIMEOUT_S), duplicated here
// because this process cannot import Python, and pinned to it by a test.
const PYTHON_TRANSCRIBE_BUDGET_S = 180;
// Bridge/broker construction + interpreter start + JSON round-trip on top of whatever Python waits for.
const CAPTURE_MARGIN_MS = 30000;

/**
 * The capture ceiling, derived from the budget PYTHON will honour. `SOW_NEMO_TRANSCRIBE_TIMEOUT_S` is
 * an operator lever; if this side ignored it, raising the Python budget on a slow host would simply
 * move the kill from Python to JS and the operator would still see a failure — with a worse reason.
 */
function captureCeilingForEnv(env = process.env) {
  const raw = env && env.SOW_NEMO_TRANSCRIBE_TIMEOUT_S;
  const s = raw == null || String(raw).trim() === "" ? NaN : Number(raw);
  const budgetMs = Number.isFinite(s) && s > 0 ? s * 1000 : PYTHON_TRANSCRIBE_BUDGET_S * 1000;
  return budgetMs + CAPTURE_MARGIN_MS;
}

// A payload is a usable voice feed only if it carries the pinned schema, an `outcome` object with a
// string `kind`, and a boolean `delivered`. Anything else is refused (a drifted producer cannot pass).
function isWellFormedVoiceFeed(f) {
  if (!f || typeof f !== "object" || f.schema !== CONDUCTOR_VOICE_FEED_SCHEMA) return false;
  const o = f.outcome;
  return !!o && typeof o === "object" && !Array.isArray(o) && typeof o.kind === "string"
    && typeof f.delivered === "boolean";
}

// Bounded-subprocess runner: spawn the emitter once, collect stdout, resolve the parsed feed or reject
// with VoiceSourceError on timeout / non-zero exit / non-JSON / malformed shape.
function runEmitter({ spawn, python, pythonArgs, cwd, timeoutMs, args, wellFormed, label, env }) {
  return new Promise((resolve, reject) => {
    let child;
    try {
      // U136: a diagnostic child gets a CREDENTIAL-SCRUBBED environment by default. This one reaches
      // `wsl.exe`, where `WSLENV` can carry named host variables into the VM — §2.2 does not stop at
      // the governed launch paths. `env` is injectable so a test can pin the scrub without a real host.
      child = spawn(python, [...pythonArgs, ...args], { cwd, env: env || scrubCredentialEnv().env });
    } catch (e) {
      reject(new VoiceSourceError(`could not launch the ${label} emitter: ${e.message}`));
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (fn, arg) => { if (settled) return; settled = true; clearTimeout(to); try { child.kill(); } catch { /* gone */ } fn(arg); };
    const to = setTimeout(
      () => finish(reject, new VoiceSourceError(`${label} emit timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish(reject, new VoiceSourceError(`${label} emitter failed to run: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new VoiceSourceError(`${label} emitter exited ${code}${err ? `: ${err.trim().slice(0, 200)}` : ""}`));
        return;
      }
      let parsed;
      try { parsed = JSON.parse(out); }
      catch (e) { finish(reject, new VoiceSourceError(`${label} emitter emitted non-JSON: ${e.message}`)); return; }
      if (!wellFormed(parsed)) {
        finish(reject, new VoiceSourceError(`${label} emitter emitted a malformed feed`));
        return;
      }
      finish(resolve, parsed);
    });
  });
}

/**
 * Run `--emit-conductor-voice [--audio-ref <ref>]` once and return the parsed feed. STRICT: throws
 * VoiceSourceError on timeout / non-zero exit / non-JSON / malformed shape.
 * @param {object} opts {spawn?, python?, pythonArgs?, cwd, timeoutMs?, audioRef?}
 * @returns {Promise<object>} the voice feed dict
 */
function fetchConductorVoiceFeed(opts = {}) {
  const args = ["tools/live/emit_conductor_voice.py", "--emit-conductor-voice"];
  if (typeof opts.audioRef === "string" && opts.audioRef.trim()) args.push("--audio-ref", opts.audioRef);
  // Phase 17C `.mic`: `realCapture` says the ref is a real WAV of the operator's speech, so the emitter
  // must select the REAL engine (`for_capture`) instead of the PCM-less stand-in's mock. `engineState`
  // hands over the answer the shell's `VoiceProbe` already paid for — the emitter is a one-shot process
  // whose own probe cache is always cold (U134), so without this a real capture would either re-probe
  // for 7–22 s on top of the transcription or route real speech to the MOCK. Only a POSITIVE is passed;
  // it seeds a cache, it cannot fabricate a transcript (the WSL round trip still fails closed).
  if (opts.realCapture === true) {
    args.push("--real-capture");
    const st = opts.engineState;
    if (st && st.state === "available") {
      args.push("--engine-state", "available");
      if (st.reason) args.push("--engine-reason", String(st.reason).slice(0, 400));
      if (Number.isFinite(st.elapsedMs)) args.push("--engine-elapsed-s", String(Math.max(0, st.elapsedMs) / 1000));
    }
  }
  return runEmitter({
    spawn: opts.spawn || realSpawn,
    python: opts.python || defaultPython(),
    pythonArgs: opts.pythonArgs || defaultPythonArgs(),
    cwd: opts.cwd,
    env: opts.childEnv,
    // Bounded, and DERIVED from the budgets Python will actually honour rather than wired in: the
    // bridge builds a broker + queue and, on a real capture, runs a WSL transcription under
    // `SOW_NEMO_TRANSCRIBE_TIMEOUT_S` (default 180 s). A ceiling below that sum kills an in-budget
    // Python transcription and the operator reads it as "voice broken" — the same shape as U74, one
    // layer up. (Phase 17C `.probe` also removed the probe from this path entirely: the emitter reads
    // the engine state non-blocking, so a talk press no longer pays for a WSL NeMo import.)
    timeoutMs: opts.timeoutMs || captureCeilingForEnv(opts.env || process.env),
    args,
    wellFormed: isWellFormedVoiceFeed,
    label: "conductor-voice",
  });
}

/**
 * DISPLAY contract: NEVER throws. Returns {ok:true, feed} on a well-formed voice feed, else
 * {ok:false, error, feed: unavailableVoiceFeed()} so main always has a shape to fold — fail-closed,
 * no fabricated delivery.
 */
async function sourceConductorVoiceFeed(opts = {}) {
  // A real capture's ref is a FILESYSTEM PATH to the operator's recorded speech. It is deliberately
  // NOT carried into the fail-closed feed's `audio_ref` (below) on that path — an error surface that
  // echoed the path would leak where recorded audio sat, on the one code path where the file is real.
  const audioRef = opts.realCapture === true ? null : (typeof opts.audioRef === "string" ? opts.audioRef : null);
  try {
    const feed = await fetchConductorVoiceFeed(opts);
    return { ok: true, feed };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}`, feed: unavailableVoiceFeed(`${e.name || "Error"}: ${e.message}`, audioRef) };
  }
}

module.exports = {
  VoiceSourceError,
  captureCeilingForEnv,
  PYTHON_TRANSCRIBE_BUDGET_S,
  CONDUCTOR_VOICE_FEED_SCHEMA,
  LIVE_CAPTURE_OWED,
  unavailableVoiceFeed,
  isWellFormedVoiceFeed,
  fetchConductorVoiceFeed,
  sourceConductorVoiceFeed,
};
