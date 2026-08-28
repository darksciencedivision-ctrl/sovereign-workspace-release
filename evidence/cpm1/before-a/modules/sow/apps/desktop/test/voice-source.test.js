"use strict";
/**
 * Conductor voice-IN source tests (Phase 16E `.engine`) — the glue that turns the bounded
 * `py -3.12 tools/live/emit_conductor_voice.py` emitter into the voice feed the shell renders (closing
 * the READ half of U67).
 *
 * Two layers, mirroring approvals-drawer-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + timeout + fail-closed fold deterministically, with no
 *       live host: good chat feed, malformed shape, wrong schema, non-zero exit, non-JSON, timeout,
 *       launch error; and that --audio-ref is forwarded only when given;
 *   (2) live integration — the REAL emitter delivers a chat outcome with a VISIBLE mock engine and no TTS.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const {
  CONDUCTOR_VOICE_FEED_SCHEMA, VoiceSourceError,
  isWellFormedVoiceFeed, unavailableVoiceFeed,
  fetchConductorVoiceFeed, sourceConductorVoiceFeed,
} = require("../voice/voice-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const GOOD_CHAT_FEED = {
  schema: CONDUCTOR_VOICE_FEED_SCHEMA,
  sourced: true,
  engine: { name: "mock-stt", mock: true, real_available: false, detection: { nvidia_gpu: true, wsl: true, nemo: false }, reason: "mock" },
  outcome: { kind: "chat", source: "voice", text: "show status", confidence: 0.95, reason: "", queue_item_id: null },
  delivered: true,
  delivered_text: "show status",
  queued: false,
  needs_clarification: false,
  deliveries: [{ text: "show status", source: "voice", semantic_key: "show status" }],
  tts: false,
  transcribe_then_discard: true,
  audio_ref: "audio:show-status",
  live_capture_owed: { owed: true, issue: "16F", note: "owed" },
  torn_down: true,
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

// ---- (1) unit: the voice read-source ----------------------------------------
test("fetchConductorVoiceFeed parses a good chat feed and invokes --emit-conductor-voice", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_CHAT_FEED) });
  const feed = await fetchConductorVoiceFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(feed.schema, CONDUCTOR_VOICE_FEED_SCHEMA);
  assert.equal(feed.delivered, true);
  assert.equal(feed.delivered_text, "show status");
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--emit-conductor-voice"));
  assert.ok(args.some((a) => a.endsWith("emit_conductor_voice.py")));
});

test("sourceConductorVoiceFeed returns {ok:true, feed} on a good chat feed", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_CHAT_FEED) });
  const res = await sourceConductorVoiceFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, true);
  assert.equal(res.feed.engine.mock, true); // the VISIBLE mock engine reaches the shell
  assert.equal(res.feed.tts, false);        // no TTS ever
});

test("--audio-ref is forwarded only when provided", async () => {
  const withRef = fakeSpawn({ stdout: JSON.stringify(GOOD_CHAT_FEED) });
  await fetchConductorVoiceFeed({ spawn: withRef, cwd: REPO_ROOT, audioRef: "audio:terminate-node-b" });
  assert.ok(withRef.calls[0].args.includes("--audio-ref") && withRef.calls[0].args.includes("audio:terminate-node-b"));

  const noRef = fakeSpawn({ stdout: JSON.stringify(GOOD_CHAT_FEED) });
  await fetchConductorVoiceFeed({ spawn: noRef, cwd: REPO_ROOT });
  assert.ok(!noRef.calls[0].args.includes("--audio-ref"));
});

// ---- Phase 17C `.mic`: the real-capture arguments ---------------------------
test("realCapture forwards --real-capture and seeds the emitter with the shell's probe answer", async () => {
  // The emitter is a one-shot process whose probe cache is always cold (U134). Without the seed a real
  // capture either re-probes for 7–22 s on top of the transcription, or (non-blocking) sees `unprobed`
  // and routes the operator's actual speech to the MOCK — U74 at the process seam.
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_CHAT_FEED) });
  await fetchConductorVoiceFeed({
    spawn, cwd: REPO_ROOT, audioRef: "D:\\repo\\.voice-captures\\capture-1.wav", realCapture: true,
    engineState: { state: "available", reason: "NeMo ASR imports in the WSL venv", elapsedMs: 21516 },
  });
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--real-capture"));
  assert.equal(args[args.indexOf("--engine-state") + 1], "available");
  assert.equal(args[args.indexOf("--engine-elapsed-s") + 1], "21.516");
  assert.match(args[args.indexOf("--engine-reason") + 1], /NeMo ASR imports/);
});

test("a non-positive engine state is NOT forwarded — the emitter re-probes rather than trust it", async () => {
  // fail-closed direction: a negative must never be able to suppress the real engine across the seam.
  for (const state of ["unavailable", "unprobed", "probing", undefined]) {
    const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_CHAT_FEED) });
    await fetchConductorVoiceFeed({ spawn, cwd: REPO_ROOT, audioRef: "x.wav", realCapture: true, engineState: state ? { state } : undefined });
    const args = spawn.calls[0].args;
    assert.ok(args.includes("--real-capture"), `${state}: still a real capture`);
    assert.ok(!args.includes("--engine-state"), `${state}: not seeded`);
  }
});

test("the stand-in path never gains --real-capture", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_CHAT_FEED) });
  await fetchConductorVoiceFeed({ spawn, cwd: REPO_ROOT, audioRef: "audio:show-status" });
  assert.ok(!spawn.calls[0].args.includes("--real-capture"));
  assert.ok(!spawn.calls[0].args.includes("--engine-state"));
});

test("a real capture's fail-closed feed does NOT echo the recorded-audio path", async () => {
  // the only path where the ref names a real file of the operator's speech; an error surface that
  // echoed it would tell every reader of the feed where that audio sat.
  const spawn = fakeSpawn({ code: 2, stderr: "boom" });
  const res = await sourceConductorVoiceFeed({
    spawn, cwd: REPO_ROOT, audioRef: "D:\\repo\\.voice-captures\\capture-1.wav", realCapture: true,
  });
  assert.equal(res.ok, false);
  assert.equal(res.feed.audio_ref, null);
  assert.equal(JSON.stringify(res.feed).includes("capture-1.wav"), false);
});

test("the emitter child gets a CREDENTIAL-SCRUBBED environment (U136)", async () => {
  // this child reaches `wsl.exe`, where WSLENV can carry named host variables into the VM. §2.2 does
  // not stop at the governed launch paths.
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_CHAT_FEED) });
  await fetchConductorVoiceFeed({ spawn, cwd: REPO_ROOT });
  const env = spawn.calls[0].opts.env;
  assert.ok(env, "an env is passed explicitly — not inherited wholesale");
  assert.ok(env.PATH || env.Path, "the child can still find `py`");
  for (const k of Object.keys(env)) {
    assert.ok(!/^(ANTHROPIC_|AWS_|GOOGLE_|CLAUDE_CODE_)/i.test(k) && !/TOKEN|SECRET|API_KEY|APIKEY|PASSWORD/i.test(k),
      `${k} should have been scrubbed`);
  }
});

test("non-zero exit → {ok:false} with the fail-closed unavailable feed (never throws)", async () => {
  const spawn = fakeSpawn({ code: 2, stderr: "boom" });
  const res = await sourceConductorVoiceFeed({ spawn, cwd: REPO_ROOT, audioRef: "audio:x" });
  assert.equal(res.ok, false);
  assert.match(res.error, /exited 2/);
  assert.equal(res.feed.sourced, false);
  assert.equal(res.feed.delivered, false);           // never a fabricated delivery
  assert.equal(res.feed.outcome.kind, "clarify");    // a fault reads as "repeat"
  assert.equal(res.feed.engine.mock, true);          // never a claimed real engine
  assert.equal(res.feed.audio_ref, "audio:x");       // the attempted ref is preserved honestly
});

test("non-JSON output → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ stdout: "not json" });
  const res = await sourceConductorVoiceFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
  assert.match(res.error, /non-JSON/);
});

test("malformed feed (no outcome object) → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: CONDUCTOR_VOICE_FEED_SCHEMA, delivered: true }) });
  const res = await sourceConductorVoiceFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
  assert.match(res.error, /malformed/);
});

test("wrong schema → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: "other@9", outcome: { kind: "chat" }, delivered: true }) });
  const res = await sourceConductorVoiceFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
});

test("timeout → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  const res = await sourceConductorVoiceFeed({ spawn, cwd: REPO_ROOT, timeoutMs: 30 });
  assert.equal(res.ok, false);
  assert.match(res.error, /timed out/);
});

test("spawn launch throw → {ok:false} fail-closed (never throws into renderer)", async () => {
  const spawn = fakeSpawn({ throwOnSpawn: true });
  const res = await sourceConductorVoiceFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
  assert.match(res.error, /could not launch/);
});

test("fetchConductorVoiceFeed (strict) throws VoiceSourceError on a bad exit", async () => {
  const spawn = fakeSpawn({ code: 2 });
  await assert.rejects(() => fetchConductorVoiceFeed({ spawn, cwd: REPO_ROOT }), VoiceSourceError);
});

// ---- well-formedness + fail-closed shape ------------------------------------
test("isWellFormedVoiceFeed accepts an outcome+delivered feed, rejects others", () => {
  assert.equal(isWellFormedVoiceFeed(GOOD_CHAT_FEED), true);
  assert.equal(isWellFormedVoiceFeed({ schema: CONDUCTOR_VOICE_FEED_SCHEMA, delivered: true }), false);
  assert.equal(isWellFormedVoiceFeed({ schema: CONDUCTOR_VOICE_FEED_SCHEMA, outcome: { kind: "chat" } }), false); // no boolean delivered
  assert.equal(isWellFormedVoiceFeed({ schema: "x@1", outcome: { kind: "chat" }, delivered: true }), false);
  assert.equal(isWellFormedVoiceFeed(null), false);
});

test("unavailableVoiceFeed is an honest clarify, never a delivery", () => {
  const f = unavailableVoiceFeed("boom", "audio:y");
  assert.equal(f.sourced, false);
  assert.equal(f.reason, "boom");
  assert.equal(f.delivered, false);
  assert.equal(f.delivered_text, null);
  assert.equal(f.outcome.kind, "clarify");
  assert.equal(f.engine.mock, true);
  assert.equal(f.tts, false);
  assert.equal(f.audio_ref, "audio:y");
  assert.equal(f.live_capture_owed.issue, "16F");
});

// ---- (2) live integration: the REAL emitter ---------------------------------
test("LIVE: the real voice emitter delivers a chat outcome with a VISIBLE mock engine and no TTS",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    const res = await sourceConductorVoiceFeed({ cwd: REPO_ROOT, timeoutMs: 60000, audioRef: "audio:show-status" });
    assert.equal(res.ok, true);
    assert.equal(res.feed.sourced, true);
    assert.equal(res.feed.outcome.kind, "chat");
    assert.equal(res.feed.delivered, true);
    assert.equal(res.feed.delivered_text, "show status");
    assert.equal(res.feed.engine.mock, true);   // never a claimed real engine on this host
    assert.equal(res.feed.tts, false);          // I-V2/D-VOICE-02
    assert.equal(res.feed.torn_down, true);
  });

test("LIVE: a destructive utterance is QUEUED, never delivered (invariant 25)",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    const res = await sourceConductorVoiceFeed({ cwd: REPO_ROOT, timeoutMs: 60000, audioRef: "audio:terminate-node-b" });
    assert.equal(res.ok, true);
    assert.equal(res.feed.outcome.kind, "proposed_action");
    assert.equal(res.feed.queued, true);
    assert.equal(res.feed.delivered, false);
    assert.equal(res.feed.delivered_text, null);
    assert.ok(res.feed.outcome.queue_item_id);
  });
