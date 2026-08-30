"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * Phase 17C `.mic` in-Electron receipt (D-P16-0 binding, per-track) — real captured PCM through the
 * SHIPPED capture path, on this host, inside the packaged Electron runtime.
 *
 * WHAT IT PROVES, and why each leg is here.
 *
 * `.probe` closed U74 (the badge stopped lying about the engine) but left **U137** open and said so:
 * the probe establishes exactly one fact — the NeMo ASR stack IMPORTS in the WSL venv — and nothing in
 * the shell had ever exercised `ASRModel.from_pretrained`. Uncached weights, a broken CUDA/driver
 * pairing or insufficient VRAM all leave that import green while transcription is dead, so the operator
 * could be badged "parakeet-wsl ready" and have their first real utterance fail. This check closes that
 * gap the only way it can be closed: by transcribing real audio through the production path and
 * comparing the result to what was actually said.
 *
 * THE ONE SUBSTITUTION, stated plainly (directive §6). A physical microphone cannot be driven by an
 * automated check, and the directive says so — *"the spoken-mic half is operator first use"*. So the
 * fixture WAV's samples are injected at EXACTLY the point `MicRecorder.stop()` hands its encoded bytes
 * over (`S.captureVoice({pcm, sampleRate})`). Everything downstream is the unmodified production path:
 * the IPC payload shape, main's `CaptureStore` validation and write, the real-engine selection, the WSL
 * Parakeet transcription, the bridge's chat-vs-propose-vs-clarify routing, the delivery into an admitted
 * pane's ConPTY, and the guaranteed discard. The fixture itself is produced by the OS speech
 * synthesizer as a TEST INPUT — the same carve-out recorded at 16E `.real`; the product still has no
 * TTS and this check asserts `tts:false` on every result.
 *
 * The legs, each measured, nothing fabricated:
 *   1. supervision READY (governed spawn; no naked session — invariant 2);
 *   2. the mic is WIRED in the running renderer (recorder + encoder + button present) — a regression
 *      that dropped the <script> tag would leave the button routing stand-ins forever, silently;
 *   3. the RENDERER's own encoder produces a container the decoder accepts (the shipped encode path,
 *      not main's copy of it);
 *   4. **U137**: real PCM → REAL engine (`mock:false`, `parakeet-wsl`) → a transcript that RECOGNISES
 *      the spoken phrase. A green probe now demonstrably implies a successful transcription;
 *   5. **invariant 26**: the WAV existed during transcription and is GONE after — asserted against the
 *      filesystem, not against a flag the code set about itself;
 *   6. **U133**: `capturing` is true DURING the capture and false after — the operator can tell a slow
 *      WSL round trip from a hung shell;
 *   7. the WRITE: the transcript reaches a real admitted pane's PTY over the production delivery
 *      function — the same command path as typing (OP-8 §13.5);
 *   8. the HONESTY negatives: a protected spoken verb is QUEUED not delivered (invariant 25); a
 *      malformed PCM payload from the least-trusted surface is REFUSED with no file written and no
 *      fabricated delivery (invariant 29); and no TTS anywhere (I-V2/D-VOICE-02).
 *
 * FALSIFIABLE, by design: point the fixture at silence and leg 4 fails; delete the discard and leg 5
 * fails; revert `capturing` to the hard-coded `false` and leg 6 fails. Each is a one-line mutation the
 * validator can reproduce.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");
const { spawn } = require("child_process");
const { decodeWav } = require("../voice/wav");
const { childEnv } = require("../voice/env-scrub");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const RECEIPT_PATH = receiptPath("PHASE17C_MIC_SELFCHECK.json");
const FIXTURE_WAV = path.resolve(REPO_ROOT, "tools", "live", "_voice_fixture_selfcheck.wav");
const CAPTURE_DIR = path.resolve(__dirname, "..", ".voice-captures");

//: What the fixture says. Chosen to be ordinary conversational CHAT — no protected verb — so the
//: bridge routes it as chat and the delivery leg is reachable. The recognition check is word-level and
//: case-insensitive: ASR legitimately re-punctuates and re-cases ("Testing 1234" for "testing one two
//: three four" at 16E), so demanding an exact string would fail on a WORKING engine.
const PHRASE = "the conductor should summarize the build status";
const PHRASE_WORDS = ["conductor", "build", "status"];

//: A cold `ASRModel.from_pretrained` on this host is tens of seconds; the Python budget is 180 s and the
//: JS ceiling derives from it. This is the receipt's own wait on top, with room for a cold model load.
const TRANSCRIBE_WAIT_MS = 420000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(pred, timeoutMs, stepMs) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    let ok = false;
    try { ok = await pred(); } catch { ok = false; }
    if (ok) return true;
    if (Date.now() >= deadline) return false;
    await sleep(stepMs);
  }
}

async function evalR(win, expr) {
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

async function paneText(win, paneId) {
  return evalR(win, `window.__sovereignSelfCheck && window.__sovereignSelfCheck.paneText(${JSON.stringify(paneId)})`);
}

/** Files currently sitting in the capture directory — the filesystem's own answer about invariant 26. */
function captureFiles() {
  try { return fs.readdirSync(CAPTURE_DIR).filter((n) => n.endsWith(".wav")); } catch { return []; }
}

/**
 * Author the fixture WAV with the OS speech synthesizer (TEST INPUT ONLY — the product has no TTS;
 * see the module header and `tools/live/make_voice_fixture.py`). Bounded; a fault is reported, never
 * worked around with a fabricated file.
 */
function makeFixture(log) {
  return new Promise((resolve) => {
    // U185: the guard the OTHER caller has, in the caller that did not. The packaged main process
    // `require`s this module unconditionally, so the OS synthesizer is reachable from the shipped app
    // — under `SHELL_SELFCHECK` only. I-V2/D-VOICE-02 says the product never speaks, and "no caller
    // does this by accident" is not an enforcement. The evidence report attributed this refusal to
    // `tools/live/make_voice_fixture.py`, which has none; it lived in one of two entry points.
    if (!process.env.SHELL_SELFCHECK) {
      resolve({ ok: false, error: "refusing to synthesize outside a self-check run (I-V2/D-VOICE-02)" });
      return;
    }
    // U136: even a local diagnostic child gets a credential-scrubbed environment.
    const { env } = childEnv({}, process.env);
    const child = spawn(defaultPython(), [...defaultPythonArgs(), "tools/live/make_voice_fixture.py", FIXTURE_WAV, PHRASE],
      { cwd: REPO_ROOT, env });
    let out = "";
    let err = "";
    const to = setTimeout(() => { try { child.kill(); } catch { /* gone */ } resolve({ ok: false, error: "fixture synthesis timed out" }); }, 120000);
    child.stdout.on("data", (d) => { out += d.toString(); });
    child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => { clearTimeout(to); resolve({ ok: false, error: `fixture generator failed to run: ${e.message}` }); });
    child.on("exit", (code) => {
      clearTimeout(to);
      let rec = null;
      try { rec = JSON.parse(out.trim().split(/\r?\n/).pop() || "null"); } catch { /* below */ }
      if (code !== 0 || !rec || rec.ok !== true) {
        resolve({ ok: false, error: `fixture generator exited ${code}: ${(rec && rec.error) || err.trim().slice(0, 200)}` });
        return;
      }
      if (log) log(`[selfcheck:voice-mic] fixture ${rec.wav_bytes} bytes / ${rec.seconds}s @ ${rec.sample_rate}Hz`);
      resolve({ ok: true, fixture: rec });
    });
  });
}

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, conductorState, deliverConductorChat, voiceState, log } = ctx;
  const receipt = {
    schema: "phase17c_mic_selfcheck@1.0",
    check: "phase-17c.mic",
    started: new Date().toISOString(),
    ok: false,
    supervision_ready: false,
    mic_wired: null,
    renderer_encode: null,
    fixture: null,
    capture: null,
    transcript: null,
    protected_capture: null,
    refusal: null,
    capture_files_during: null,
    capture_files_after: null,
    capturing_during: null,
    capturing_after: null,
    write_pane_id: null,
    checks: {},
    substitution: "the physical microphone is operator hardware and cannot be driven by an automated check "
      + "(directive §16 track 17C: the spoken-mic half is operator first use). The fixture WAV's samples are "
      + "injected at exactly the point MicRecorder.stop() hands its encoded bytes to S.captureVoice; every "
      + "step below that — IPC payload, CaptureStore validation + write, real-engine selection, the WSL "
      + "Parakeet transcription, bridge routing and guaranteed discard — is the unmodified production "
      + "path. This receipt also proves a transcript cannot be redirected into a stand-in command shell; "
      + "the live-conductor delivery is measured separately by PHASE17C_CLOSE_SELFCHECK.json. The fixture "
      + "is OS-synthesized TEST INPUT; the product has no TTS (I-V2/D-VOICE-02).",
    error: null,
  };

  try {
    // 1. supervision READY — no naked session (invariant 2)
    receipt.supervision_ready = await waitFor(isSupervised, 25000, 250);
    if (!receipt.supervision_ready) throw new Error("supervision never became READY within 25s");
    const cs = conductorState ? conductorState() : null;
    const conductorPaneId = (cs && cs.paneId) || null;

    // 2. the microphone path is WIRED in the RUNNING renderer (not merely present on disk)
    receipt.mic_wired = await evalR(win, "window.__sovereignSelfCheck.micWired()");
    receipt.checks.mic_recorder_wired = !!(receipt.mic_wired && receipt.mic_wired.recorder);
    receipt.checks.mic_encoder_wired = !!(receipt.mic_wired && receipt.mic_wired.encoder);
    receipt.checks.ptt_button_present = !!(receipt.mic_wired && receipt.mic_wired.button);

    // 3. the RENDERER's own encoder produces a container that decodes back to what went in
    const samples = Array.from({ length: 1600 }, (_, i) => 0.4 * Math.sin((2 * Math.PI * 440 * i) / 48000));
    const enc = await evalR(win, `window.__sovereignSelfCheck.encodeCapturePcm(${JSON.stringify(samples)}, 48000)`);
    receipt.renderer_encode = enc && { samples: enc.samples, sampleRate: enc.sampleRate, seconds: enc.seconds, bytes: enc.bytes.length };
    let rendererEncodeOk = false;
    try {
      const decoded = decodeWav(Uint8Array.from(enc.bytes));
      rendererEncodeOk = decoded.sampleRate === 16000 && decoded.channels === 1 && decoded.samples === enc.samples;
    } catch (e) { receipt.renderer_encode_error = String(e.message); }
    receipt.checks.renderer_encode_transcribable = rendererEncodeOk;

    // 4. the fixture: real spoken audio to push through the real path
    const fx = await makeFixture(log);
    receipt.fixture = fx.ok ? fx.fixture : { error: fx.error };
    if (!fx.ok) throw new Error(fx.error);
    const wavBytes = fs.readFileSync(FIXTURE_WAV);
    const decodedFixture = decodeWav(new Uint8Array(wavBytes));
    receipt.fixture.decoded = { sampleRate: decodedFixture.sampleRate, samples: decodedFixture.samples, seconds: Math.round(decodedFixture.seconds * 1000) / 1000 };

    // 5. Wait for the LAUNCH probe to settle before capturing. This is not politeness — it is the real
    //    operator sequence (the probe starts at first paint and settles in ~22 s; a talk press comes
    //    later), and it is the only way this receipt exercises **U134**: the seed that carries the
    //    shell's established answer across the process seam so a capture does not pay a second WSL
    //    import. Bounded; if it never settles the seed leg is recorded unmet rather than skipped.
    receipt.probe_settled = await waitFor(() => {
      const st = voiceState && voiceState();
      return !!(st && st.probe && st.probe.state === "available");
    }, 180000, 500);
    const probeState = voiceState ? voiceState().probe : null;
    receipt.probe_at_capture = probeState;
    receipt.checks.probe_settled_before_capture = receipt.probe_settled;

    // 6. THE CAPTURE. Watch the capture directory and the `capturing` flag WHILE it runs — both are
    //    facts about the running shell that cannot be read after the fact.
    const before = captureFiles();
    let sawFile = false;
    let sawCapturing = false;
    const watcher = setInterval(() => {
      if (captureFiles().length > before.length) sawFile = true;
      try { const st = voiceState && voiceState(); if (st && st.control && st.control.capturing === true) sawCapturing = true; } catch { /* transient */ }
    }, 150);
    let cap = null;
    try {
      const expr = `window.__sovereignSelfCheck.captureVoicePcm(${JSON.stringify(Array.from(wavBytes))}, ${decodedFixture.sampleRate})`;
      const started = Date.now();
      cap = await Promise.race([
        evalR(win, expr),
        sleep(TRANSCRIBE_WAIT_MS).then(() => null),
      ]);
      receipt.transcribe_ms = Date.now() - started;
    } finally {
      clearInterval(watcher);
    }
    receipt.capture = cap;
    receipt.capture_files_during = sawFile;
    receipt.capture_files_after = captureFiles();
    receipt.capturing_during = sawCapturing;
    const stAfter = voiceState ? voiceState() : null;
    receipt.capturing_after = !!(stAfter && stAfter.control && stAfter.control.capturing);

    const engine = (cap && cap.engine) || {};
    const meta = (cap && cap.capture) || {};
    receipt.transcript = cap && cap.delivered_text;
    receipt.engine_used = { name: engine.name, mock: engine.mock, real_available: engine.real_available };

    receipt.checks.capture_sourced = !!(cap && cap.sourced === true);
    receipt.checks.capture_carried_real_pcm = meta.real_pcm === true && meta.bytes === wavBytes.length;
    // U134: the shell's established answer crossed the process seam, so this capture paid for NO second
    // WSL NeMo import. Without it a real capture either re-probes (7–22 s on top of a transcription the
    // operator is already waiting through) or, non-blocking, sees `unprobed` and routes real speech to
    // the MOCK — U74's failure re-staged at the boundary.
    receipt.checks.engine_answer_seeded_across_the_seam = meta.engine_state_seeded === true;
    // U137 — the whole point: the REAL engine, not the mock stand-in, handled real PCM.
    receipt.checks.real_engine_transcribed = engine.mock === false && engine.real_available === true
      && String(engine.name || "").includes("parakeet");
    const text = String((cap && cap.delivered_text) || "").toLowerCase();
    receipt.checks.transcript_recognised_the_phrase = PHRASE_WORDS.every((w) => text.includes(w));
    receipt.checks.routed_as_chat = !!(cap && cap.delivered === true && cap.outcome && cap.outcome.kind === "chat");
    // invariant 26 — measured against the filesystem, not against a flag the code set about itself
    receipt.checks.audio_existed_during_transcription = sawFile;
    receipt.checks.audio_discarded_after = receipt.capture_files_after.length === before.length && meta.discarded === true;
    // U133 — the operator can distinguish a slow WSL round trip from a hung shell
    receipt.checks.capturing_visible_during = sawCapturing;
    receipt.checks.capturing_cleared_after = receipt.capturing_after === false;
    receipt.checks.no_tts = !!(cap && cap.tts === false);
    receipt.checks.self_authorized_false = !!(cap && cap.selfAuthorized === false);
    // the OWED record must stop claiming real capture is owed once real capture has happened
    receipt.checks.owed_record_honest = !!(cap && cap.live_capture_owed && cap.live_capture_owed.issue === "17C.mic");
    log(`[selfcheck:voice-mic] engine=${engine.name} mock=${engine.mock} transcript=${JSON.stringify(cap && cap.delivered_text)}`);

    // 6. TARGET HONESTY: the transcript must NOT be redirectable into a merely-admitted shell.
    //    The live-conductor positive is the `.close` receipt; this regression receipt owns the negative.
    const testPane = createPaneWithSession({
      file: "powershell.exe", args: ["-NoLogo", "-NoProfile", "-NoExit"], title: "voice-mic-selfcheck",
    });
    receipt.write_pane_id = testPane;
    await waitFor(async () => evalR(win, `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(testPane)})`), 15000, 200);
    const transcript = (cap && cap.delivered_text) || "";
    const wr = transcript ? await deliverConductorChat(transcript) : { written: false, reason: "no transcript" };
    receipt.write = wr;
    receipt.checks.off_conductor_write_refused = wr.written !== true && wr.submitted !== true;
    const leaked = await waitFor(async () => {
      const t = await paneText(win, testPane);
      return typeof t === "string" && t.toLowerCase().includes("conductor should");
    }, 4000, 250);
    receipt.checks.off_conductor_pane_received_nothing = leaked === false;
    receipt.live_delivery_evidence = "docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json";

    // 7. HONESTY NEGATIVE A — a protected spoken verb is QUEUED, never delivered (invariant 25).
    //    Uses the stand-in path deliberately: the routing authority must be identical whatever produced
    //    the transcript, and a protected verb must not need a microphone to be proven.
    const prot = await evalR(win, 'window.__sovereignSelfCheck.captureVoice("audio:terminate-node-b")');
    receipt.protected_capture = prot;
    receipt.checks.protected_queued_not_delivered = !!(prot && prot.queued === true
      && prot.delivered === false && prot.delivered_to_conductor === false);

    // 8. HONESTY NEGATIVE B — the least-trusted surface sends junk (invariant 29). It must be REFUSED
    //    with no file written and no fabricated delivery — never a silent fall-back to the mock, which
    //    on a path where the operator really spoke would be a pretend-to-hear.
    const filesBeforeJunk = captureFiles().length;
    const junk = Array.from({ length: 2000 }, () => 7);
    const refusal = await evalR(win, `window.__sovereignSelfCheck.captureVoicePcm(${JSON.stringify(junk)}, 16000)`);
    receipt.refusal = refusal;
    receipt.checks.junk_pcm_refused = !!(refusal && refusal.sourced === false
      && refusal.delivered_to_conductor === false && /not a RIFF|refused/i.test(String(refusal.error || refusal.note || "")));
    receipt.checks.junk_pcm_wrote_no_file = captureFiles().length === filesBeforeJunk;

    // 9. HONESTY NEGATIVE C — the talk button must never route anything but the operator's own speech.
    //    An earlier revision of `wirePushToTalk` fell back to the scripted stand-in whenever capture
    //    failed or never began, which meant a stray `pointerup` (released over the button after
    //    dragging a divider) or a synthetic `click` resolved to DEFAULT_AUDIO_REF → MockSTT →
    //    "show status" → a CHAT verdict → a real write into the conductor's ConPTY. Both mandatory
    //    reviews found it; it is the sharpest defect this unit could ship, so it gets a receipt leg.
    //    On this host there is no microphone, so even a full press-and-hold must route NOTHING.
    const badgeBefore = await evalR(win, "JSON.stringify((window.__sovereignSelfCheck.voiceModel()||{}).badge||null)");
    const stray = await evalR(win, `window.__sovereignSelfCheck.fireTalkEvents(${JSON.stringify(conductorPaneId)}, ["pointerup","click"])`);
    receipt.stray_events = stray;
    const heldNoMic = await evalR(win, `window.__sovereignSelfCheck.fireTalkEvents(${JSON.stringify(conductorPaneId)}, ["pointerdown","pointerup"])`);
    receipt.held_without_mic = heldNoMic;
    const badgeAfter = await evalR(win, "JSON.stringify((window.__sovereignSelfCheck.voiceModel()||{}).badge||null)");
    receipt.checks.stray_release_routes_nothing = !!(stray && stray.before === stray.after);
    receipt.checks.press_without_a_mic_routes_nothing = !!(heldNoMic && heldNoMic.before === heldNoMic.after);
    receipt.checks.talk_button_never_fabricates = badgeBefore === badgeAfter;
    // …and the device is not left HOT. `getUserMedia` is asynchronous, so a quick tap resolves the
    // release handler first; without an explicit re-check the device opened behind it and stayed open,
    // with the chrome reading "listening…" and no press holding it. The button's own label is the
    // observable: after a completed tap it must have returned to rest.
    receipt.talk_label_after_tap = heldNoMic && heldNoMic.label;
    receipt.checks.device_not_left_hot_after_a_tap = !/listening/i.test(String((heldNoMic && heldNoMic.label) || ""));

    const c = receipt.checks;
    receipt.ok = Object.keys(c).length > 0 && Object.values(c).every(Boolean);
    receipt.failed_checks = Object.entries(c).filter(([, v]) => !v).map(([k]) => k);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
    if (log) log(`[selfcheck:voice-mic] crashed: ${receipt.error}`);
  } finally {
    // transcribe-then-discard applies to the FIXTURE too — this check does not leave speech on disk.
    try { fs.unlinkSync(FIXTURE_WAV); } catch { /* already gone */ }
  }

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node, chrome: process.versions.chrome,
    platform: process.platform, arch: process.arch,
  };
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    if (log) log(`[selfcheck:voice-mic] could not write receipt: ${e && e.message}`);
  }
  if (log) log(`[selfcheck:voice-mic] ${receipt.ok ? "PASS" : `FAIL (${(receipt.failed_checks || []).join(", ") || receipt.error})`} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runVoiceMicSelfCheck: run, RECEIPT_PATH, PHRASE, FIXTURE_WAV };
