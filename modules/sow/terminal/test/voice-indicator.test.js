"use strict";
/**
 * phase-15e.voice — conductor voice-IN indicator render model (pure/deterministic).
 * Mirrors the approval-drawer/inspector tests: fail closed on malformed input, never fabricate a
 * "delivered", and never offer a speech-OUT affordance (I-V2/D-VOICE-02: STT-only, no TTS).
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  voiceControl,
  voiceEngineIndicator,
  voiceOutcomeBadge,
  summarizeVoice,
  voiceTurnIndicator,
  KIND_LABELS,
} = require("../compositor/voice-indicator");

// -- the push-to-talk control ------------------------------------------------------------------

test("ptt control defaults available and not listening, with NO speech-out", () => {
  const c = voiceControl(null);
  assert.equal(c.available, true);
  assert.equal(c.control, "ptt");
  assert.equal(c.listening, false);
  assert.equal(c.speechOut, false); // STT-only — no TTS affordance ever
});

test("ptt control reflects capturing as listening", () => {
  const c = voiceControl({ capturing: true });
  assert.equal(c.listening, true);
  assert.equal(c.label, "Push to talk");
});

test("ptt control fails closed to unavailable on an explicit false", () => {
  const c = voiceControl({ available: false, capturing: true });
  assert.equal(c.available, false);
  assert.equal(c.listening, false); // never listening when unavailable
  assert.match(c.hint, /unavailable/);
});

test("the control object exposes no speaker/tts affordance", () => {
  const c = voiceControl({});
  for (const k of Object.keys(c)) {
    assert.ok(!/tts|speak|speaker|synth|say/i.test(k), `unexpected speech-out key ${k}`);
  }
});

// -- the last-utterance outcome badge ----------------------------------------------------------

test("a chat outcome renders delivered when the write actually landed", () => {
  const b = voiceOutcomeBadge({ kind: "chat", source: "voice" }, { written: true, submitted: true });
  assert.equal(b.ok, true);
  assert.equal(b.delivered, true);
  assert.equal(b.queued, false);
  assert.equal(b.needsClarification, false);
  assert.equal(b.label, KIND_LABELS.chat);
  assert.equal(b.source, "voice");
  assert.equal(b.submitted, true);
});

test("the delivered badge names whose claim the delivery rests on (U180)", () => {
  // Admission is the conductor CLI presenting the armed payload back — its claim about itself. The
  // badge is the only thing the operator reads, so it carries the basis rather than implying that
  // this shell watched a model receive the words.
  const b = voiceOutcomeBadge({ kind: "chat", source: "voice" },
    { written: true, submitted: true, submission_basis: "vendor_reported" });
  assert.equal(b.delivered, true);
  assert.equal(b.basis, "vendor_reported");
  assert.match(b.label, /reported/i);
  // …and a write record with no basis at all does not get to imply one
  const bare = voiceOutcomeBadge({ kind: "chat", source: "voice" }, { written: true, submitted: true });
  assert.equal(bare.basis, null);
});

// Phase 17C `.close` — the badge is what the OPERATOR reads, and until now it was built from the
// ROUTING verdict alone: "Delivered to conductor" appeared whenever the bridge said CHAT, whatever the
// PTY write did. With the sink a live conductor session that can exit, be killed, or sit on its own
// prompt, that is the badge affirmatively lying about the one thing the operator cannot otherwise see.
test("a chat outcome whose body landed but was never SUBMITTED does not claim delivery", () => {
  const b = voiceOutcomeBadge({ kind: "chat", source: "voice" },
    { written: true, submitted: false, reason: "the conductor pane never echoed the utterance" });
  assert.equal(b.ok, true);
  assert.equal(b.kind, "chat");            // the routing verdict is preserved — it was chat
  assert.equal(b.delivered, false);        // …but nothing was delivered
  assert.equal(b.submitted, false);
  assert.match(b.label, /not submitted/i);
  assert.match(b.reason, /never echoed/);
});

test("a chat outcome whose write never landed at all says so", () => {
  const b = voiceOutcomeBadge({ kind: "chat", source: "voice" },
    { written: false, submitted: false, reason: "conductor session not admitted (owed 16F)" });
  assert.equal(b.delivered, false);
  assert.match(b.label, /not delivered/i);
});

test("a chat outcome with NO write record fails closed to unconfirmed, never to delivered", () => {
  for (const w of [null, undefined, 42, "written"]) {
    const b = voiceOutcomeBadge({ kind: "chat", source: "voice" }, w);
    assert.equal(b.delivered, false, `write=${JSON.stringify(w)} must not claim delivery`);
    assert.match(b.label, /unconfirmed/i);
  }
});

test("a proposed_action outcome renders queued, not delivered", () => {
  const b = voiceOutcomeBadge({ kind: "proposed_action", source: "voice", reason: "destructive verb" });
  assert.equal(b.ok, true);
  assert.equal(b.queued, true);
  assert.equal(b.delivered, false); // a queued action never claims delivery into the conversation
  assert.equal(b.reason, "destructive verb");
});

test("a clarify outcome asks for a repeat", () => {
  const b = voiceOutcomeBadge({ kind: "clarify", source: "voice" });
  assert.equal(b.ok, true);
  assert.equal(b.needsClarification, true);
  assert.equal(b.delivered, false);
});

test("a malformed outcome fails closed to clarify, never delivered", () => {
  for (const bad of [null, undefined, 42, "chat", { kind: "bogus" }, {}]) {
    const b = voiceOutcomeBadge(bad);
    assert.equal(b.ok, false);
    assert.equal(b.delivered, false); // never fabricate "delivered"
    assert.equal(b.needsClarification, true);
    assert.equal(b.kind, "clarify");
  }
});

test("an unknown source is dropped to null, not trusted", () => {
  const b = voiceOutcomeBadge({ kind: "chat", source: "spoofed" });
  assert.equal(b.source, null);
});

// -- summary -----------------------------------------------------------------------------------

test("summary reflects listening state and last outcome", () => {
  const control = voiceControl({ capturing: true });
  const badge = voiceOutcomeBadge({ kind: "chat", source: "voice" }, { written: true, submitted: true });
  assert.match(summarizeVoice(control, badge), /voice listening — last: delivered to conductor/);
});

test("summary is honest when voice is unavailable", () => {
  // Phase 16E: the mock-engine tag is surfaced even when unavailable (never a silent pretend-to-hear).
  assert.equal(summarizeVoice(voiceControl({ available: false }), null), "voice input unavailable [mock engine]");
});

test("summary degrades to ready with no valid badge", () => {
  assert.equal(summarizeVoice(voiceControl({}), null), "voice ready [mock engine]");
});

// -- the VISIBLE STT-engine indicator (Phase 16E .engine) --------------------------------------

test("engine indicator fails closed to a VISIBLE mock engine on an absent/malformed descriptor", () => {
  for (const bad of [null, undefined, 42, "mock", []]) {
    const e = voiceEngineIndicator(bad);
    assert.equal(e.mock, true);
    assert.equal(e.real, false);
    assert.equal(e.label, "mock engine");
    assert.match(e.hint, /OPERATOR_NEMO_INSTALL/);
  }
});

test("a mock engine descriptor renders a visible mock engine", () => {
  const e = voiceEngineIndicator({ name: "mock-stt", mock: true, real_available: false });
  assert.equal(e.mock, true);
  assert.equal(e.real, false);
  assert.equal(e.label, "mock engine");
});

test("a real engine renders as real ONLY when mock:false AND real_available:true", () => {
  const e = voiceEngineIndicator({ name: "parakeet-tdt", mock: false, real_available: true });
  assert.equal(e.real, true);
  assert.equal(e.mock, false);
  assert.equal(e.ready, false);
  assert.equal(e.label, "parakeet-tdt");
  assert.match(e.hint, /real STT engine/);
});

test("Phase 16E .real: real stack installed but a stand-in transcript renders READY, not 'mock engine'", () => {
  // mock:true (this transcript is the stand-in mock) AND real_available:true ⇒ the real Parakeet is
  // installed and will transcribe live speech. The indicator must say so ("<name> ready") — NOT keep
  // showing "mock engine" (the operator's OP-10 complaint) and NOT claim a real transcript happened.
  const e = voiceEngineIndicator({ name: "parakeet-wsl", mock: true, real_available: true });
  assert.equal(e.ready, true);
  assert.equal(e.real, false);
  assert.equal(e.mock, false); // NOT a "mock engine" — the real stack IS available
  assert.equal(e.realAvailable, true);
  assert.equal(e.label, "parakeet-wsl ready");
  // Phase 17C `.probe`: the hint is stated to what the probe ESTABLISHES (the ASR stack imports), not
  // to what it does not (that a transcription will succeed) — uncached weights or a broken CUDA pairing
  // leave the import green and transcription dead.
  assert.match(e.hint, /reachable in WSL/);
  assert.doesNotMatch(e.hint, /transcribes your live speech/);
  assert.doesNotMatch(e.label, /mock engine/);
});

test("READY falls back to a Parakeet label when the descriptor omits a name", () => {
  const e = voiceEngineIndicator({ mock: true, real_available: true });
  assert.equal(e.ready, true);
  assert.equal(e.label, "Parakeet ready");
});

test("READY names the REAL engine (real_engine) even when a mock produced the stand-in transcript", () => {
  // the real-feed shape: the mock transcribed the PCM-less poll (name mock-stt) but the real Parakeet
  // stack is what will handle live speech — the badge must name it, not the mock.
  const e = voiceEngineIndicator({ name: "mock-stt", real_engine: "parakeet-wsl", mock: true, real_available: true });
  assert.equal(e.ready, true);
  assert.equal(e.label, "parakeet-wsl ready");
});

test("a mock:false claim WITHOUT host detection still folds to mock (never claims real)", () => {
  // the safe direction: a producer must not be able to claim 'real' without real_available:true
  const e = voiceEngineIndicator({ name: "sketchy", mock: false, real_available: false });
  assert.equal(e.real, false);
  assert.equal(e.mock, true);
  assert.equal(e.label, "mock engine");
});

test("voiceControl surfaces the engine indicator", () => {
  const c = voiceControl({ engine: { name: "mock-stt", mock: true, real_available: false } });
  assert.equal(c.engine.mock, true);
  assert.equal(c.engine.label, "mock engine");
});

// ---- Phase 17C `.probe` (U74 / OP-11 finding F1): the fourth state ---------------------------------
test("Phase 17C .probe: an UNANSWERED probe renders 'probing…', never 'mock engine'", () => {
  // The operator's host HAS Parakeet. The probe legitimately costs 7–18 s, and before 17C the chrome
  // rendered that open question as the answer "mock engine" — a negative the shell had not established.
  const e = voiceEngineIndicator({ name: "mock-stt", real_engine: "parakeet-wsl", mock: true,
                                   real_available: false, probing: true, nemo_state: "unprobed" });
  assert.equal(e.probing, true);
  assert.equal(e.mock, false);              // it is NOT asserting "no real engine"
  assert.equal(e.real, false);              // …and it is NOT claiming one either
  assert.equal(e.ready, false);
  assert.equal(e.label, "probing…");
  assert.doesNotMatch(e.label, /mock engine/);
  assert.match(e.hint, /not yet known/);
});

test("an ANSWERED negative still renders the visible mock engine", () => {
  const e = voiceEngineIndicator({ name: "mock-stt", mock: true, real_available: false,
                                   probing: false, nemo_state: "unavailable" });
  assert.equal(e.probing, false);
  assert.equal(e.mock, true);
  assert.equal(e.label, "mock engine");
});

test("a positive answer beats a stale `probing` flag — the states are mutually exclusive", () => {
  // a descriptor that claims BOTH must resolve to the answered one; "probing" may only ever mean
  // "no answer yet", so it can never suppress a real availability the probe already established.
  const e = voiceEngineIndicator({ name: "parakeet-wsl", mock: true, real_available: true, probing: true });
  assert.equal(e.probing, false);
  assert.equal(e.ready, true);
  assert.equal(e.label, "parakeet-wsl ready");
});

test("the accessibility summary says [probing…] while the question is open", () => {
  const c = voiceControl({ engine: { name: "mock-stt", mock: true, real_available: false, probing: true } });
  assert.equal(c.engine.label, "probing…");
  assert.equal(summarizeVoice(c, null), "voice ready [probing…]");
  assert.doesNotMatch(summarizeVoice(c, null), /mock engine/);
});

// -- the voice-turn restriction indicator (Phase 17C `.disarm`, U166 / invariant 27) -------------
// The supervisor denies the CLI's tool use for the length of a voice turn. That state was invisible
// AND permanent, so an operator whose typing stopped reaching pane 1 had nothing to read, and the
// only way back was an undocumented chord.

test("an idle session shows no restriction at all", () => {
  const i = voiceTurnIndicator({ schema: "supervisor_voice_turn_state@1.0", restricted: false, phase: "idle" });
  assert.equal(i.show, false);
  assert.equal(i.restricted, false);
  assert.equal(i.label, "");
});

test("an admitted voice turn is visible, says what is restricted, and names its way out", () => {
  const i = voiceTurnIndicator({
    schema: "supervisor_voice_turn_state@1.0",
    restricted: true, phase: "active", turn_id: "abc", session_id: "s1",
    since: "2026-07-30T00:00:00.000Z",
    recovery: "type in the conductor pane — your next keystroke ends the voice turn; "
      + "or press Ctrl+Shift+Escape to end it without typing",
  });
  assert.equal(i.show, true);
  assert.equal(i.restricted, true);
  assert.match(i.label, /voice turn/i);
  assert.match(i.label, /tool/i);
  assert.match(i.hint, /type/i);
  assert.match(i.hint, /Ctrl\+Shift\+Escape/);
});

test("a pending turn is restricted too, and says so as pending rather than active", () => {
  const i = voiceTurnIndicator({ restricted: true, phase: "pending", recovery: "type in the pane" });
  assert.equal(i.show, true);
  assert.match(i.label, /pending/i);
});

test("a turn the operator ended still shows, because its answer still cannot use tools (U178)", () => {
  // The keystroke gives the operator their keyboard back and leaves the in-flight answer denied. A
  // chrome that went blank there would understate a live denial — the more dangerous direction,
  // because nobody re-checks a restriction reported as over (invariant 27).
  const i = voiceTurnIndicator({
    schema: "supervisor_voice_turn_state@1.0",
    restricted: false, phase: "ended", turn_id: "abc", tools_denied: true, denying_turn_id: "abc",
    ended_at: "2026-07-31T00:00:00.000Z",
    recovery: "you ended the voice turn and your keyboard is yours again — the answer it is still "
      + "producing cannot use tools until you send your next prompt",
  });
  assert.equal(i.show, true);
  assert.equal(i.phase, "ended");
  // it must NOT claim the operator is still restricted — that is what their keystroke ended
  assert.equal(i.restricted, false);
  assert.match(i.label, /ended/i);
  assert.match(i.label, /tool/i);
  assert.match(i.hint, /next prompt/i);
});

test("an ended turn with nothing left denying renders nothing", () => {
  const i = voiceTurnIndicator({ restricted: false, phase: "ended", tools_denied: false });
  assert.equal(i.show, false);
});

test("a malformed or absent turn state renders NOTHING rather than a guess", () => {
  for (const bad of [null, undefined, "restricted", 7, {}, { restricted: "yes" }]) {
    const i = voiceTurnIndicator(bad);
    assert.equal(i.show, false, JSON.stringify(bad));
    assert.equal(i.label, "");
  }
});

test("the indicator never invents a recovery the supervisor does not implement", () => {
  const i = voiceTurnIndicator({ restricted: true, phase: "active" });
  assert.equal(i.show, true);
  assert.equal(i.hint, "");
});

test("voiceControl still exposes no speaker/tts affordance even with an engine", () => {
  const c = voiceControl({ engine: { name: "parakeet-tdt", mock: false, real_available: true } });
  for (const k of Object.keys(c)) {
    assert.ok(!/tts|speak|speaker|synth|say/i.test(k), `unexpected speech-out key ${k}`);
  }
  assert.equal(c.engine.real, true);
});
