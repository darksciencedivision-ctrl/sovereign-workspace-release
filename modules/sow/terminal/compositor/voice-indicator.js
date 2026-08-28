"use strict";
/**
 * Conductor voice-IN indicator render model (phase-15e.voice; OP-8 §13.5, invariants 24/25, I-V1..V3).
 *
 * The conductor pane gains a push-to-talk (PTT) mic affordance: the operator SPEAKS to the conductor
 * and the transcript enters its input on the same path as typing. The routing authority lives
 * Python-side (voice_bridge/conductor_voice.ConductorVoiceBridge over the real CommandBroker): ordinary
 * chat flows directly, a protected/destructive action proposes→approves (never executes, invariant
 * 25), a low-confidence transcript clarifies. This module is the PURE, deterministic render model for
 * that affordance + the last-utterance badge the sandboxed renderer paints. It renders nothing and
 * performs no I/O; the drawn mic control is an operator-run surface (the Phase-1 substitution pattern),
 * and the live STT + conductor write are operator-run.
 *
 * Two load-bearing honesty properties, both fail-closed:
 *   - there is NO speech-OUT control here (I-V2/D-VOICE-02): the model exposes `speechOut:false` and
 *     offers no speaker/TTS affordance — spoken answers are OWED-BY-OPERATOR-DECISION (OP-8 §13.6),
 *     never faked into the UI;
 *   - a malformed/absent outcome yields a fail-closed CLARIFY badge (`ok:false`), never a fabricated
 *     "delivered" — the UI must never imply speech reached the conductor when it did not.
 */

// The three routing outcomes the bridge can report (voice_bridge/conductor_voice.ConductorInputKind).
const KIND_LABELS = {
  chat: "Delivered to conductor",
  proposed_action: "Queued for approval",
  clarify: "Not understood — repeat",
};
const KNOWN_KINDS = Object.keys(KIND_LABELS);

function isPlainObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

/**
 * The VISIBLE STT-engine indicator (Phase 16E; directive §15 track 16E — "never silently pretend to
 * hear"). Given an engine descriptor from `conductor_voice_feed@1.0` ({ name, mock, real_available }),
 * returns what the chrome draws so the operator always knows the real state of speech recognition.
 *
 * FOUR fail-closed states (`.real` added "ready"; Phase 17C `.probe` adds "probing" — U74/F1):
 *   - REAL  (`mock:false ∧ real_available:true`): a real engine produced the transcript → label = name.
 *   - READY (`mock:true  ∧ real_available:true`): the real Parakeet stack IS installed and will
 *     transcribe live mic capture, but THIS transcript came from the mock stand-in (the headless
 *     indicator poll carries no PCM) → label = "<name> ready". Honest: not "mock engine" (the operator's
 *     OP-10 complaint) and not a claimed real transcript either.
 *   - PROBING (`probing:true`, i.e. the host has WSL but the NeMo probe has not answered): the question
 *     is OPEN → label = "probing…". This state exists because the probe legitimately costs 7–18 s on
 *     this host: before U74 an unanswered probe was rendered as "mock engine", which asserted a negative
 *     the shell had not established. An open question must look like one.
 *   - MOCK  (`real_available:false ∧ ¬probing`, or an absent/malformed descriptor): no real stack →
 *     "mock engine".
 *
 * The safe direction is preserved: a `mock:false` claim WITHOUT `real_available:true` never renders real
 * — it folds to the mock (or probing) state. `mock` is true ONLY when no real stack is available AND the
 * probe has answered; `probing` never claims an engine either, it only declines to claim the negative.
 */
function voiceEngineIndicator(engine) {
  const e = isPlainObject(engine) ? engine : {};
  const name = typeof e.name === "string" && e.name ? e.name : null;
  // the REAL engine that will transcribe live speech (carried even when a mock produced THIS stand-in
  // transcript) — so the "ready" label names Parakeet, not the mock that handled the PCM-less poll.
  const realName = typeof e.real_engine === "string" && e.real_engine ? e.real_engine : null;
  const realAvailable = e.real_available === true;
  const real = e.mock === false && realAvailable;   // a real engine produced this transcript
  const ready = e.mock !== false && realAvailable;   // real installed; this (stand-in) transcript is mock
  // an unanswered probe — never coexists with a positive answer (an answered probe is not "probing")
  const probing = e.probing === true && !realAvailable;
  const mock = !realAvailable && !probing;            // no real stack, probe ANSWERED (fail-closed)
  const label = real ? (name || realName || "Parakeet")
    : ready ? `${realName || name || "Parakeet"} ready`
      : probing ? "probing…"
        : "mock engine";
  return {
    name,
    mock,
    ready,
    real,
    probing,
    realAvailable,
    label,
    hint: probing
      ? "checking whether real Parakeet/NeMo is reachable in WSL — speech recognition state is not yet known"
      : mock
        ? "voice transcription is a MOCK engine — install NeMo/Parakeet for real speech (see docs/OPERATOR_NEMO_INSTALL.md)"
        : ready
          // Stated to exactly what the probe establishes: the NeMo ASR stack IMPORTS in the WSL venv.
          // It does not establish that a transcription will succeed — uncached weights, a broken
          // CUDA/driver pairing or insufficient VRAM all leave the import green. Saying "transcribes
          // your live speech" here asserted a capability nothing had exercised.
          ? `real Parakeet is installed and reachable in WSL (its ASR stack imports); the first live capture is what proves transcription`
          : `real STT engine: ${name || "Parakeet"}`,
  };
}

/**
 * The push-to-talk mic control the conductor chrome draws. `state` is a small status record
 * ({ capturing, available, engine }); everything defaults fail-closed. There is deliberately no
 * speaker control — `speechOut` is always false (STT-only; no TTS). The VISIBLE mock/real engine
 * indicator rides on `engine` (Phase 16E).
 */
function voiceControl(state) {
  const s = isPlainObject(state) ? state : {};
  // available defaults TRUE (voice-IN is a core 15E capability); only an explicit false disables it.
  const available = s.available !== false;
  const capturing = s.capturing === true;
  const engine = voiceEngineIndicator(s.engine);
  return {
    available,
    label: "Push to talk",
    control: "ptt",
    capturing,
    listening: available && capturing,
    hint: available ? "Hold to speak to the conductor" : "Voice input unavailable",
    speechOut: false, // I-V2/D-VOICE-02: voice input only — no speech synthesis affordance
    engine, // Phase 16E: VISIBLE mock/real STT engine indicator (never a silent pretend-to-hear)
  };
}

/**
 * The badge for the LAST routed utterance, from a `ConductorInputOutcome`-shaped payload
 * ({ kind, source, reason }) and the RESULT OF THE WRITE that carried it ({written, submitted, reason}).
 *
 * Fail-closed: a missing/unknown kind renders a CLARIFY badge with `ok:false` — never a fabricated
 * "delivered". Phase 17C `.close` adds the second argument, and it is load-bearing: until now this
 * badge — the only thing the OPERATOR reads — said "Delivered to conductor" for any CHAT verdict,
 * whatever the ConPTY write actually did. That was tolerable while the sink was a recording stand-in.
 * It is not tolerable now that the sink is a live conductor session, which can have exited, been
 * killed, or be sitting on its own prompt: a CHAT routed into a session that received nothing would
 * render as delivered, and the operator would be waiting for an answer to something never sent.
 *
 * So a CHAT badge claims delivery ONLY on `submitted === true`, and an absent/malformed write record
 * is UNCONFIRMED rather than delivered — the safe direction. The routing verdict itself is preserved
 * (`kind` stays "chat"): what the bridge decided and what the write achieved are different facts and
 * neither is allowed to rewrite the other.
 *
 * Returns { ok, kind, label, delivered, submitted, queued, needsClarification, source, reason }.
 */
function voiceOutcomeBadge(outcome, write) {
  const base = {
    ok: false, kind: "clarify", label: KIND_LABELS.clarify,
    delivered: false, queued: false, needsClarification: true, source: null, reason: "",
  };
  if (!isPlainObject(outcome)) {
    return { ...base, reason: "no voice outcome" };
  }
  const kind = typeof outcome.kind === "string" ? outcome.kind : "";
  const source = outcome.source === "voice" || outcome.source === "typed" ? outcome.source : null;
  const reason = typeof outcome.reason === "string" ? outcome.reason : "";
  if (!KNOWN_KINDS.includes(kind)) {
    // an unknown/absent kind never claims delivery — fail closed to clarify
    return { ...base, source, reason: reason || `unknown outcome kind ${kind || "(none)"}` };
  }
  if (kind !== "chat") {
    return {
      ok: true, kind, label: KIND_LABELS[kind], delivered: false, submitted: false,
      queued: kind === "proposed_action", needsClarification: kind === "clarify", source, reason,
    };
  }
  // CHAT: the routing verdict is settled; delivery is a separate fact, read off the write.
  const w = isPlainObject(write) ? write : null;
  const submitted = w ? w.submitted === true : false;
  // U180: WHOSE claim the delivery rests on. Admission is the conductor CLI presenting the armed
  // payload back to the supervisor — its own report about itself — so the badge says so rather than
  // implying this shell watched a model receive the words. An absent basis is left absent: a write
  // record that does not say is not upgraded to one that does.
  const basis = w && w.submission_basis === "vendor_reported" ? "vendor_reported" : null;
  const label = submitted
    ? (basis === "vendor_reported" ? `${KIND_LABELS.chat} (CLI reported)` : KIND_LABELS.chat)
    : !w ? "Routed — delivery unconfirmed"
      : w.written === true ? "Routed — not submitted to the conductor"
        : "Routed — not delivered to the conductor";
  return {
    ok: true,
    kind,
    label,
    delivered: submitted,
    submitted,
    basis,
    queued: false,
    needsClarification: false,
    source,
    // the write's own reason is what tells the operator WHY nothing arrived; the routing reason is
    // empty on a chat verdict, so it never competes with it.
    reason: submitted ? reason : ((w && typeof w.reason === "string" && w.reason) || reason
      || "the write result is unknown"),
  };
}

/**
 * One-line accessibility summary for the mic control + last outcome. Deterministic.
 */
function summarizeVoice(control, badge) {
  const c = isPlainObject(control) ? control : voiceControl(null);
  // the engine tag is ALWAYS surfaced (Phase 16E) — a mock engine is visible even before a first
  // utterance, and (17C) an unfinished probe reads as "probing", never as a mock verdict.
  const engineTag = !isPlainObject(c.engine) ? ""
    : c.engine.probing ? " [probing…]"
      : c.engine.mock ? " [mock engine]" : "";
  if (c.available !== true) return `voice input unavailable${engineTag}`;
  const state = c.listening ? "listening" : "ready";
  if (!isPlainObject(badge) || badge.ok !== true) return `voice ${state}${engineTag}`;
  return `voice ${state} — last: ${badge.label.toLowerCase()}${engineTag}`;
}

/**
 * The VOICE-TURN RESTRICTION indicator (Phase 17C `.disarm`, U166 / invariant 27).
 *
 * While a supervisor-owned voice turn is armed, the conductor's CLI is denied every tool call and
 * permission escalation. That is the correct behaviour (invariant 25 — voice proposes, never
 * executes) and it was completely invisible: the operator saw a live pane that had simply stopped
 * doing things. Worse, before `.disarm` it never ended, and the only way out was a chord printed
 * nowhere. So the state is drawn, and it carries its OWN way out — supplied by the supervisor
 * service that implements it, never authored here, so this badge cannot promise a recovery the
 * service does not have.
 *
 * Fail closed to SILENCE: a malformed/absent state renders nothing rather than a guessed alarm.
 */
function voiceTurnIndicator(turn) {
  const t = isPlainObject(turn) ? turn : {};
  const restricted = t.restricted === true;
  // U178 — the THIRD state. The operator's keystroke ends the turn for THEM while the answer it is
  // still generating keeps its tool denial until their next prompt. Going blank there would report a
  // live denial as over, which is the understating direction: nobody re-checks a restriction they
  // were told had ended.
  const endedDenying = !restricted && t.tools_denied === true;
  if (!restricted && !endedDenying) {
    return { show: false, restricted: false, phase: "idle", label: "", hint: "" };
  }
  const phase = endedDenying ? "ended" : t.phase === "pending" ? "pending" : "active";
  return {
    show: true,
    restricted,
    phase,
    label: phase === "pending"
      ? "voice turn pending — tool use denied"
      : phase === "ended"
        ? "voice turn ended — its answer still cannot use tools"
        : "voice turn active — tool use denied",
    hint: typeof t.recovery === "string" ? t.recovery : "",
    since: typeof t.since === "string" ? t.since : null,
  };
}

module.exports = {
  voiceControl,
  voiceEngineIndicator,
  voiceOutcomeBadge,
  summarizeVoice,
  voiceTurnIndicator,
  KIND_LABELS,
  KNOWN_KINDS,
};
