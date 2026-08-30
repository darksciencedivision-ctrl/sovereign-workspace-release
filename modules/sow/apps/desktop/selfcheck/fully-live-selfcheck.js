"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * Phase 17E — THE FULLY-LIVE ASSEMBLED RECEIPT (D-P16-0 binding, high-stakes gate).
 *
 * Every earlier receipt in this phase proved ONE leg in its own runtime: 17A that pane 1 can hold a
 * live conductor and answer a typed prompt; 17B that a picker click starts a real governed worker and
 * that a LIVE worker can execute a dispatched task; 17C that real speech reaches the same live
 * session; 17D that the approval drawer shows only what this session did. Each ran alone. The
 * operator's stated DEFINITION OF DONE is not a list of separate runs — it is ONE shell in which all
 * of it is true at once, so this check composes them in a single Electron process:
 *
 *   supervision READY
 *     → the governed LIVE conductor launch in pane 1 (production path, full live-gate chain)
 *     → real PCM → real WSL Parakeet → the bridge → THAT session → the conductor's answer   [DONE b*]
 *     → a spoken PROTECTED verb queues instead of delivering, and the approval drawer shows
 *       that event and nothing else, decided through the governed authority                  [DONE e]
 *     → the operator's keystroke ends the voice turn and a TYPED prompt is answered by the
 *       same live session                                                                    [DONE a]
 *     → a picker selection launches a LIVE local worker (`qwen3:8b`) in its own pane          [DONE c]
 *     → a governed dispatch in which a LIVE worker publishes a CANDIDATE over MCP, the real
 *       gate engine accepts it and the conductor synthesizes an acceptance packet             [DONE d]
 *     → both live frontier terminals counted against ONE subscription's allowance (I-X3 = 2)
 *     → everything this check started is torn down before it returns (D-LOOP-1).
 *
 * WHAT IT DOES NOT CLAIM is as load-bearing as what it does, and lives in `receipt.owed` rather than
 * in prose: the physical microphone and the operator's own keyboard are the operator's first use
 * (§16 — the loop never blocks on the operator); U69's OS-level keydown remains unexplained; the
 * live conductor CLI does not itself CHOOSE to dispatch (the governed dispatch is invoked by the
 * shell — the U58 residual); no TTS exists (I-V2/D-VOICE-02); cloud Kimi/Qwen need a new provider
 * authorization. `fully-live-verdict.js` refuses a receipt whose OWED block drops any of them.
 *
 * LIVE SCOPE (§16 "live exchanges MINIMAL"): ONE conductor session, ONE spoken exchange, ONE typed
 * exchange, ONE live worker exchange inside the dispatch, one local model session that is sent no
 * prompt at all. The lease ledger is SCRATCH throughout, so this check can never adopt or release the
 * operator's own terminal — and because the dispatch emitter is a child of this process, its live
 * worker takes its terminal from that SAME scratch ledger, which is what makes the I-X3 leg mean
 * anything.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");
const { spawn } = require("child_process");

const { decodeWav } = require("../voice/wav");
const { childEnv } = require("../voice/env-scrub");
const { fetchLeaseStatus } = require("../conductor/launch-source");
const { fetchPickerModel, fetchHostResidency } = require("../picker/source");
const {
  buildSpokenProbe, buildTypedProbe, parseHeardArithmetic, carriesNumber, spokenProbeIsFalsifiable,
  answerAfterAnchor,
} = require("../voice/spoken-probe");
const { sourceIdentity, committedTreeCheckName } = require("./voice-conductor-selfcheck");
const {
  liveDispatchIsHonest, approvalDrawerIsRealSessionEvents, demoIdsPresent, owedMarkersAreComplete,
  twoTerminalsOnOneAllowance, composeVerdict,
} = require("./fully-live-verdict");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const RECEIPT_PATH = receiptPath("PHASE17E_FULLY_LIVE_SELFCHECK.json");
const FIXTURE_WAV = path.resolve(REPO_ROOT, "tools", "live", "_voice_fixture_fully_live.wav");
const CAPTURE_DIR = path.resolve(__dirname, "..", ".voice-captures");
const SCRATCH_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", `selfcheck-17e-${process.pid}.json`);
// The operator's own ledger (node_runtime/supervisor/terminal_lease.DEFAULT_LEDGER_PATH). This check
// never writes to it — 17B gated that as `real_ledger_unchanged` and the composition had dropped the
// rule (spec-audit F2), so it is measured here by digest, before and after.
const DURABLE_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", "terminal_leases.json");

/** A digest of a file that may not exist. `absent` is a legitimate state, not an error. */
function digestOf(file) {
  try {
    return require("crypto").createHash("sha256").update(fs.readFileSync(file)).digest("hex");
  } catch (e) {
    return (e && e.code === "ENOENT") ? "absent" : `unreadable:${(e && e.code) || "?"}`;
  }
}

// Per-step ceilings, each named in the failure it produces, so a stall reports WHICH step stalled
// instead of being killed blind by the launcher.
const SUPERVISION_MS = 30000;
const TUI_READY_MS = 45000;
const PROBE_SETTLE_MS = 180000;
const FIXTURE_MS = 120000;
const TRANSCRIBE_MS = 420000;
const ECHO_MS = 30000;
const ANSWER_MS = 180000;
const DRAWER_MS = 60000;
const PICKER_MS = 90000;
const PANE_OUTPUT_MS = 120000;
const DISPATCH_MS = 900000;
const KILL_MS = 20000;
const RELEASE_MS = 60000;

// See worker-launch/worker-spawn for why the VRAM budget is COMPUTED from the host's own residency
// snapshot rather than being a flat constant: a fixed figure lands on whichever admission branch the
// daemon's current state happens to produce, and a leg that exercises a different gate than its name
// claims is evidence for the wrong thing. Here the intent is explicit — the LOCAL option must be
// admissible so the picker leg tests the SPAWN, not the residency planner (which 17B `.ticket` owns).
const PINNED_VRAM_FLOOR_MB = 24576;
const PINNED_VRAM_HEADROOM_MB = 1024;
const PROBE_VRAM_BUDGET_MB = "1048576";

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

async function typeInto(win, paneId, data) {
  return evalR(win,
    `window.__sovereignSelfCheck && window.__sovereignSelfCheck.typeInto(`
      + `${JSON.stringify(paneId)}, ${JSON.stringify(data)})`);
}

/**
 * Type a whole prompt into a live pane the way the operator does — and SUBMIT it only once the pane
 * has echoed it back (17C's measured rule: a body and a bare `\r` in one write does not reach the
 * live CLI as a submitted message, and an unconditional `\r` answers whatever prompt is on screen).
 */
async function typeAndSubmit(win, paneId, body, isEchoed, echoMs) {
  const written = (await typeInto(win, paneId, body)) === true;
  if (!written) return { written: false, echoed: false, submitted: false };
  const echoed = await waitFor(async () => isEchoed((await paneText(win, paneId)) || ""), echoMs, 250);
  if (!echoed) return { written, echoed: false, submitted: false };
  const submitted = (await typeInto(win, paneId, "\r")) === true;
  return { written, echoed, submitted };
}

/** Files sitting in the capture directory — the filesystem's own answer about invariant 26. */
function captureFiles() {
  try { return fs.readdirSync(CAPTURE_DIR).filter((n) => n.endsWith(".wav")); } catch { return []; }
}

/**
 * The interactive CLI is ready for input when it has painted the governed workspace it opened AND
 * stopped repainting. (Same rule 17A `.roundtrip` established and 17C `.close` reuses; kept local so
 * this unit cannot regress either gated check's evidence path.)
 */
async function waitForTuiQuiescence(win, paneId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  let stableSince = null;
  while (Date.now() < deadline) {
    const text = await paneText(win, paneId);
    const painted = typeof text === "string"
      && text.replace(/\s+/g, "").includes(REPO_ROOT.replace(/\s+/g, ""));
    if (painted && text === last) {
      if (stableSince === null) stableSince = Date.now();
      if (Date.now() - stableSince >= 2000) return { ready: true, text };
    } else {
      stableSince = null;
    }
    last = text;
    await sleep(400);
  }
  return { ready: false, text: last };
}

/**
 * Author the fixture WAV with the OS speech synthesizer (TEST INPUT ONLY — the product has no TTS;
 * `tools/live/make_voice_fixture.py` enforces that the synthesizer can only ever reach a FILE).
 */
function makeFixture(phrase, log) {
  return new Promise((resolve) => {
    if (!process.env.SHELL_SELFCHECK) {
      resolve({ ok: false, error: "refusing to synthesize outside a self-check run (I-V2/D-VOICE-02)" });
      return;
    }
    const { env } = childEnv({}, process.env);   // U136: even a local diagnostic child gets a scrubbed env
    const child = spawn(defaultPython(), [...defaultPythonArgs(), "tools/live/make_voice_fixture.py", FIXTURE_WAV, phrase],
      { cwd: REPO_ROOT, env });
    let out = "";
    let err = "";
    const to = setTimeout(() => {
      try { child.kill(); } catch { /* gone */ }
      resolve({ ok: false, error: "fixture synthesis timed out" });
    }, FIXTURE_MS);
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
      if (log) log(`[selfcheck:fully-live] fixture ${rec.wav_bytes} bytes / ${rec.seconds}s @ ${rec.sample_rate}Hz`);
      resolve({ ok: true, fixture: rec });
    });
  });
}

/** An available picker option matching a predicate, PREFERRING a named model — never fabricated. */
function pickOption(options, predicate, preferred) {
  const available = (options || []).filter((o) => o && o.available && predicate(o));
  return available.find((o) => o.model_slug === preferred) || available[0] || null;
}

/** The OWED block — every leg this run cannot evidence, named with the reference that tracks it. */
function owedBlock() {
  return {
    spoken_microphone: "the physical microphone cannot be driven by an automated check — directive "
      + "§16 puts the spoken-mic half in the operator's own first use, and the loop never blocks on "
      + "the operator (§1). Everything below MicRecorder.stop() is the production path and IS measured here.",
    physical_key_delivery: "U69 — 17D drove 28 TRUSTED keydowns into the focused xterm helper "
      + "textarea with no terminal data resulting, while the textarea's own text-input path plus a "
      + "delivered Return DID echo through to the PTY. No mechanism was isolated; the operator's own "
      + "keyboard is the remaining witness. The typed legs here use the renderer's real "
      + "onData → pane:input → SessionManager.write path.",
    conductor_initiated_dispatch: "U58 residual — the governed dispatch proven here is INVOKED by "
      + "the shell (the same emitter the conductor chrome sources), not chosen by the live conductor "
      + "CLI itself over MCP. The live worker, its CANDIDATE, the gate and the synthesis are real; "
      + "'the conductor decided to delegate' is not what this leg shows.",
    speech_out_tts: "I-V2 / D-VOICE-02 — the product has no TTS and this run asserts tts:false. A "
      + "spoken ANSWER would be an operator reversal of a frozen invariant (would-be OP-9-TTS), "
      + "recorded as OWED-BY-OPERATOR-DECISION, never built silently.",
    cloud_kimi_qwen: "OP-10 track 16B — Kimi K3 and Qwen 3.8 are offered only as cloud endpoints on "
      + "this host; enabling them needs a new operator provider authorization. The LOCAL leg here "
      + "runs the host's real `qwen3:8b`, enumerated from the daemon, never fabricated.",
    diagnostic_ledger_scope: "U111 — this run's two live frontier terminals are recorded in a "
      + "DIAGNOSTIC (scratch) ledger, so the check can never adopt or release a terminal the "
      + "operator's own shell holds. Until this unit that also meant the enforcing governor counted "
      + "ZERO for the window, and an operator shell at its own allowance could have brought the true "
      + "total to 4. A diagnostic ledger now COUNTS the durable one as a read-only baseline in every "
      + "admission decision (`concurrency.baseline_in_use` records what it saw). The residual is the "
      + "gap between reading that baseline and writing our own record: a terminal the operator's "
      + "shell acquires inside that window is not in our count. And the overlay is ONE-WAY by "
      + "construction (U215): a durable ledger has no baseline path, so the operator's own shell "
      + "never counts THIS run's leases at any time — for the whole run an operator shell could take "
      + "its full allowance and the true total would be 4. What this unit fixed is that the CHECK can "
      + "no longer be the party that overshoots; the operator-shell direction is unchanged.",
    vendor_session_store_retention: "U146 — `audio_was_transcribed_then_discarded` is true of OUR "
      + "capture store: the PCM is deleted and `.voice-captures` is empty afterwards. The delivered "
      + "TRANSCRIPT, however, becomes durable text in the vendor CLI's own session store, outside "
      + "this workspace and outside any retention this system controls. 17C's receipt disclosed this "
      + "and the composition had dropped it. Speaking to the shell does leave something behind; it "
      + "is not the audio.",
  };
}

async function run(ctx) {
  const {
    win, isSupervised, conductorState, launchConductorSession, conductorLaunchState, sessionManager,
    killSession, voiceState, exerciseOperatorTypedKeyDisarm, spawnFromSelection, workerLaunchState,
    runGovernedDispatch, log,
  } = ctx;

  const receipt = {
    schema: "phase17e_fully_live_selfcheck@1.0",
    check: "phase-17e.compose",
    started: new Date().toISOString(),
    source: sourceIdentity(),
    ok: false,
    electron_main_pid: process.pid,
    ledger_scope: "scratch",
    ledger_path: SCRATCH_LEDGER,
    // [a] the live conductor session in pane 1
    conductor: {
      pane_id: null, launched: false, launch_state: null, launch_reason: null, argv: null,
      session_id: null, session_pid: null, session_state: null, model_label: null, model_slug: null,
      model_is_fallback: null, chrome_live: null, subscription_ref: null, tui_ready: false,
    },
    // [b*] the spoken half, fixture-driven
    voice: {
      probe_settled: false, phrase: null, expected: null, fixture: null, transcribe_ms: null,
      transcript: null, engine: null, heard_expected: null, asr_matched_the_spoken_operands: null,
      echo_seen: false, answer_seen: false, answer_number: null, answer_matched: null,
      answer_latency_ms: null, capture_files_after: null, audio_existed_during: false,
      excerpt: null,
    },
    // [e] the approval drawer, from this session's own events
    approvals: {
      launch_source: null, launch_badge_count: null, before_badge_count: null, rows: 0,
      row_ids: [], event_count: null, row_provenance: null, demo_ids_present: null,
      protected_capture: null, decide: null, after_badge_count: null,
      re_decide: null, drawer_verdict: null,
    },
    // [a] the typed half, after the operator's keystroke ends the voice turn
    typed: {
      disarm: null, prompt: null, expected: null, write: null, answer_seen: false,
      answer_number: null, answer_matched: null, excerpt: null,
    },
    // [c] the LIVE local worker a picker selection started
    worker: {
      picker_sourced: false, option_count: null, option: null, host_used_vram_mb: null,
      budget_pinned_mb: null, pane_id: null, launched: false,
      reason: null, argv: null, node_id: null, session_state: null, session_pid: null,
      chrome_node_state: null, chrome_governed: null, subscription_governed: null,
      pane_output_seen: false, excerpt: null,
    },
    // [d] the LIVE governed dispatch
    dispatch: {
      ok: false, elapsed_ms: null, legs: null, worker_evidence: null, accepted_count: null,
      acceptance_verdict: null, operator_disposition: null, synthesized_by: null,
      synthesized_by_note: null, live_run: null, torn_down: null, verdict: null,
      // WHY, when the answer is "nothing was accepted". `accepted_count: 0` is reached two ways —
      // the vendor CLI faulted before anything was published (a `node_refusals` row, in the node's
      // own words), or the artifact WAS published and the real STAGE gate refused it (`gate_summary`
      // 0-of-1). The first re-run of this composition dropped all three fields and the red leg could
      // not be diagnosed from the receipt at all.
      failed_count: null, node_refusals: null, gate_summary: null, worker_legs: null,
      // WHICH BRIEF was in force. `676362b` changed what the live worker is told (the STAGE criteria),
      // and the receipt could not show which text produced the artifact the gate judged — so the one
      // change most likely to move a leg's colour was invisible to a receipt-only reader
      // (gate-validator m4). The feed carries the objective; it is recorded verbatim.
      objective: null,
    },
    // I-X3, read across the process boundary while both live terminals are held. `scope` and
    // `baseline_in_use` are U111's answer: a diagnostic ledger counts the operator's durable
    // terminals too, so this is the enforcing count and not a scratch file's private opinion.
    concurrency: { allowance: null, scope: null, in_use_after_conductor: null,
      max_in_use_observed: null, baseline_in_use: null, samples: [], verdict: null },
    // the diagnostic ledger's own hygiene — 17B gated both of these and the composition dropped them
    ledger: { scratch_path: SCRATCH_LEDGER, durable_path: null, durable_digest_before: null,
      durable_digest_after: null, durable_unchanged: null, scratch_removed: null },
    // D-LOOP-1
    teardown: { conductor_killed: false, worker_killed: false, lease_released: false,
      in_use_after_release: null, sessions_alive_after: null },
    owed: owedBlock(),
    checks: {},
    failed_checks: [],
    error: null,
  };
  receipt.checks[committedTreeCheckName] = Boolean(
    receipt.source.commit && receipt.source.tracked_product_tree_clean
    && receipt.source.unexpected_untracked_product_files.length === 0);

  const priorLedger = process.env.SOW_TERMINAL_LEASE_LEDGER;
  const priorBudget = process.env.SOW_VRAM_BUDGET_MB;
  receipt.ledger.durable_path = DURABLE_LEDGER;
  receipt.ledger.durable_digest_before = digestOf(DURABLE_LEDGER);
  process.env.SOW_TERMINAL_LEASE_LEDGER = SCRATCH_LEDGER;  // inherited by every `py` child below
  let conductorPane = null;
  let workerPane = null;
  try {
    // ---- 1. admission — nothing is born without a verified channel (invariant 2) -----------------
    receipt.checks.supervision_ready = await waitFor(isSupervised, SUPERVISION_MS, 250);
    if (!receipt.checks.supervision_ready) throw new Error("supervision never became READY (no session may be born)");
    conductorPane = conductorState().paneId;
    receipt.conductor.pane_id = conductorPane;
    if (!conductorPane) throw new Error("no conductor pane exists to compose around");

    // ---- 2. [DONE a, first half] THE GOVERNED LIVE CONDUCTOR LAUNCH -----------------------------
    //     The production path: live_operation switch → provider-live → OP-9 terms → `claude`
    //     presence → durable I-X3 lease. Identical to on-launch and to the pane-1 control.
    const launch = await launchConductorSession({ reason: "in-Electron fully-live assembled check (17E)" });
    const st = conductorLaunchState();
    receipt.conductor.launched = launch.launched === true;
    receipt.conductor.launch_state = st.state;
    receipt.conductor.launch_reason = st.reason || (launch && launch.reason) || null;
    receipt.conductor.argv = Array.isArray(st.argv) ? st.argv.slice() : null;
    receipt.conductor.session_id = st.sessionId || null;
    receipt.conductor.session_pid = st.pid || null;
    receipt.conductor.subscription_ref = st.subscriptionRef || null;
    const slugAt = Array.isArray(receipt.conductor.argv) ? receipt.conductor.argv.indexOf("--model") : -1;
    receipt.conductor.model_slug = slugAt >= 0 ? receipt.conductor.argv[slugAt + 1] || null : null;
    receipt.conductor.model_label = (st.modelProbe && st.modelProbe.label) || null;
    // `model_available` is TRI-state (true / false / null = unprobed), and folding it into a boolean
    // made "the host CLI accepted the operator's slug" and "nobody asked" the same record
    // (spec-audit F7). Both are kept: the boolean for continuity, the state for honesty (invariant 3).
    receipt.conductor.model_is_fallback = (st.modelProbe && st.modelProbe.model_available === false) || false;
    receipt.conductor.model_probe_state = !st.modelProbe ? "no_probe_record"
      : st.modelProbe.model_available === true ? "available"
        : st.modelProbe.model_available === false ? "fallback" : "unprobed";
    // The run may ASK for the operator's selected model only where the probe confirmed the CLI takes
    // it; on a fallback or unprobed host the honest outcome is a session launched without `--model`
    // and a receipt that says so — never a slug asserted on silence (invariant 3).
    receipt.checks.the_conductor_model_slug_is_only_asserted_where_the_probe_confirmed_it =
      receipt.conductor.model_probe_state === "available"
        ? receipt.conductor.model_slug !== null && receipt.conductor.model_is_fallback === false
        : receipt.conductor.model_slug === null;
    receipt.checks.live_conductor_launched_through_the_governed_path = receipt.conductor.launched;
    if (!receipt.conductor.launched) {
      throw new Error(`the governed live launch did not run: ${receipt.conductor.launch_reason || "unknown"}`);
    }
    const mgr = sessionManager();
    receipt.conductor.session_state = mgr && mgr.registry.has(conductorPane)
      ? mgr.registry.get(conductorPane).state : null;
    receipt.checks.live_conductor_session_running = receipt.conductor.session_state === "RUNNING";
    if (!receipt.checks.live_conductor_session_running) {
      throw new Error(`the conductor session is ${receipt.conductor.session_state}, not RUNNING`);
    }
    receipt.conductor.chrome_live = conductorState().live === true;
    receipt.checks.chrome_reports_pane1_live = receipt.conductor.chrome_live;
    // the durable terminal, read across the process boundary (never this process's own opinion)
    const leaseAfterConductor = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
    const entry = ((leaseAfterConductor.ok && leaseAfterConductor.status
      && leaseAfterConductor.status.subscriptions) || {})[receipt.conductor.subscription_ref] || null;
    receipt.concurrency.in_use_after_conductor = entry ? entry.in_use : null;
    receipt.concurrency.allowance = leaseAfterConductor.ok && leaseAfterConductor.status
      ? leaseAfterConductor.status.allowance : null;
    // U111: the count is the DIAGNOSTIC ledger's, which now also counts the operator's durable
    // holders. `baseline_in_use` is what it saw of them — 0 on a host with no other shell running,
    // and the reason the total below is the enforcing number rather than a scratch file's opinion.
    receipt.concurrency.scope = entry ? (entry.scope || null) : null;
    receipt.concurrency.baseline_in_use = entry ? (entry.baseline_in_use ?? null) : null;
    receipt.checks.the_ix3_count_is_the_governing_one = receipt.concurrency.scope === "diagnostic"
      && Number.isFinite(receipt.concurrency.baseline_in_use);
    receipt.checks.conductor_holds_exactly_one_governed_terminal =
      Boolean(receipt.conductor.subscription_ref) && receipt.concurrency.in_use_after_conductor === 1;

    const tui = await waitForTuiQuiescence(win, conductorPane, TUI_READY_MS);
    receipt.conductor.tui_ready = tui.ready;
    receipt.checks.live_conductor_ready_for_input = tui.ready;
    if (!tui.ready) throw new Error("the live conductor session never settled into a ready, quiescent view");

    // ---- 3. [DONE b, fixture half] SPEECH → THAT SESSION → ITS ANSWER ---------------------------
    receipt.voice.probe_settled = await waitFor(() => {
      const s = voiceState && voiceState();
      return !!(s && s.probe && s.probe.state === "available");
    }, PROBE_SETTLE_MS, 500);
    receipt.checks.real_stt_engine_probe_settled_before_capture = receipt.voice.probe_settled;

    let probe = null;
    const paneBeforeVoice = (await paneText(win, conductorPane)) || tui.text || "";
    for (let roll = 0; roll < 5; roll++) {
      probe = buildSpokenProbe();
      if (!carriesNumber(paneBeforeVoice, Number(probe.expectedNumber)) && spokenProbeIsFalsifiable(probe)) break;
      probe = null;    // this draw's answer is already on screen — it would pass for free
    }
    if (!probe) throw new Error("could not draw a spoken probe whose answer is absent from the pane");
    receipt.voice.phrase = probe.phrase;
    receipt.voice.expected = probe.expectedNumber;

    const fx = await makeFixture(probe.phrase, log);
    receipt.voice.fixture = fx.ok ? fx.fixture : { error: fx.error };
    if (!fx.ok) throw new Error(fx.error);
    const wavBytes = fs.readFileSync(FIXTURE_WAV);
    const decoded = decodeWav(new Uint8Array(wavBytes));

    const filesBefore = captureFiles();
    let sawFile = false;
    const watcher = setInterval(() => {
      if (captureFiles().length > filesBefore.length) sawFile = true;
    }, 150);
    let cap = null;
    try {
      const expr = `window.__sovereignSelfCheck.captureVoicePcm(${JSON.stringify(Array.from(wavBytes))}, ${decoded.sampleRate})`;
      const started = Date.now();
      cap = await Promise.race([evalR(win, expr), sleep(TRANSCRIBE_MS).then(() => null)]);
      receipt.voice.transcribe_ms = Date.now() - started;
    } finally {
      clearInterval(watcher);
    }
    if (!cap) throw new Error(`the capture never resolved within ${TRANSCRIBE_MS / 1000}s`);
    const engine = cap.engine || {};
    const meta = cap.capture || {};
    receipt.voice.transcript = cap.delivered_text;
    receipt.voice.engine = { name: engine.name, mock: engine.mock, real_available: engine.real_available };
    receipt.voice.audio_existed_during = sawFile;
    receipt.voice.capture_files_after = captureFiles();
    receipt.checks.real_parakeet_transcribed_real_pcm = engine.mock === false
      && engine.real_available === true && String(engine.name || "").includes("parakeet")
      && meta.real_pcm === true && meta.bytes === wavBytes.length;
    receipt.checks.audio_was_transcribed_then_discarded = sawFile
      && receipt.voice.capture_files_after.length === filesBefore.length && meta.discarded === true;
    // Named for what they MEASURE, not for the property they are evidence about (spec-audit M2 at
    // 17E `.close`). Both fields are hard-coded literals — `deliver.js` writes `tts:false`, `main.js`
    // writes `selfAuthorized:false` — so neither check can go red under any input, and calling them
    // `no_tts_on_any_path` / `shell_self_authorized_nothing` was the same defect as D3/U216 in the
    // opposite direction. The INVARIANTS are enforced elsewhere and adversarially: the disarm-authority
    // mutation harness catches a reachable `System.Speech`, `selfcheck-guards.test.js` refuses one,
    // and `test_conductor_voice.py` asserts the bridge exposes no synthesize/speak/tts surface.
    receipt.checks.the_capture_result_asserts_no_tts = cap.tts === false;
    receipt.checks.the_capture_result_asserts_no_self_authorization = cap.selfAuthorized === false;
    receipt.checks.transcript_delivered_into_the_live_conductor =
      cap.delivered_to_conductor === true && !!cap.outcome && cap.outcome.kind === "chat"
      && !!cap.write && cap.write.submitted === true;

    const heard = parseHeardArithmetic(receipt.voice.transcript);
    if (!heard) throw new Error(`the transcript carried no readable arithmetic: ${JSON.stringify(receipt.voice.transcript)}`);
    receipt.voice.heard_expected = heard.expectedNumber;
    receipt.voice.asr_matched_the_spoken_operands = heard.expectedNumber === probe.expectedNumber;
    const spokenExpected = Number(heard.expectedNumber);
    // falsifiability, both halves: an echo cannot produce the answer, and the pane did not already hold it
    receipt.checks.spoken_answer_absent_from_the_transcript_and_the_pane =
      !carriesNumber(receipt.voice.transcript, spokenExpected)
      && !carriesNumber(paneBeforeVoice, spokenExpected);

    const spokenSubmittedAt = Date.now();
    receipt.voice.echo_seen = await waitFor(async () => {
      const t = await paneText(win, conductorPane);
      return answerAfterAnchor(t, receipt.voice.transcript, spokenExpected).anchored;
    }, ECHO_MS, 400);
    receipt.checks.whole_utterance_echoed_in_the_live_pane = receipt.voice.echo_seen;
    let spokenObserved = { replied: false, number: null, correct: false };
    receipt.voice.answer_seen = await waitFor(async () => {
      spokenObserved = answerAfterAnchor(await paneText(win, conductorPane), receipt.voice.transcript, spokenExpected);
      return spokenObserved.replied;
    }, ANSWER_MS, 1000);
    receipt.voice.answer_number = spokenObserved.number;
    receipt.voice.answer_matched = spokenObserved.correct;   // RECORDED, never gating (17C's rule)
    receipt.voice.answer_latency_ms = receipt.voice.answer_seen ? Date.now() - spokenSubmittedAt : null;
    const afterSpoken = await paneText(win, conductorPane);
    receipt.voice.excerpt = typeof afterSpoken === "string"
      ? (afterSpoken.replace(/\s+/g, " ").trim().slice(-1200) || null) : null;
    receipt.checks.the_live_conductor_answered_the_spoken_prompt = receipt.voice.answer_seen;
    if (!receipt.voice.answer_seen) {
      throw new Error(`the live conductor never replied to the utterance within ${ANSWER_MS / 1000}s `
        + `(expected ${spokenExpected})`);
    }
    log(`[selfcheck:fully-live] LIVE spoken round trip: heard "${heard.matched}" → replied `
      + `${receipt.voice.answer_number} (expected ${spokenExpected}, correct=${spokenObserved.correct}) `
      + `in ${receipt.voice.answer_latency_ms}ms`);

    // ---- 4. [DONE e] THE APPROVAL DRAWER SHOWS ONLY WHAT THIS SESSION DID -----------------------
    //     A spoken PROTECTED verb: the bridge proposes and the broker QUEUES it (invariant 25 — never
    //     delivered, never executed), which is the real session event the drawer must then show. It
    //     costs no live exchange precisely because nothing is delivered.
    await waitFor(async () => {
      const m = await evalR(win, "window.sovereign.approvals()");
      return !!(m && m.sourced === true);
    }, DRAWER_MS, 500);
    const launchDrawer = await evalR(win, "window.sovereign.approvals()") || {};
    receipt.approvals.launch_source = launchDrawer.source || null;
    receipt.approvals.launch_badge_count = launchDrawer.badgeCount || 0;
    receipt.approvals.before_badge_count = receipt.approvals.launch_badge_count;
    // The 17D F2 property, asserted in the assembled run: nothing is pending that this run did not do.
    receipt.checks.approval_drawer_was_empty_until_this_run_caused_something =
      launchDrawer.source === "session_events" && (launchDrawer.badgeCount || 0) === 0;
    const paneBeforeProtected = await paneText(win, conductorPane);
    // The utterance is a scripted stand-in ref, NOT real PCM: a protected verb must be refused
    // before anything is delivered, and proving that needs no microphone and no live exchange. The
    // engine that produced the transcript is recorded (17D did; this composition had dropped it —
    // gate-validator D2 / spec-audit F3), because a receipt whose `voice.engine` says `mock:false`
    // must not let a reader assume the same of every leg in it.
    const prot = await evalR(win, 'window.__sovereignSelfCheck.captureVoice("audio:terminate-node-b")');
    receipt.approvals.protected_capture = prot && {
      queued: prot.queued, delivered: prot.delivered,
      delivered_to_conductor: prot.delivered_to_conductor,
      kind: prot.outcome && prot.outcome.kind,
      engine: prot.engine || null,
      real_pcm: !!(prot.capture && prot.capture.real_pcm),
    };
    // …and the stand-in is named as one. A leg that silently used the mock engine while the receipt
    // claimed a real one is the failure this whole track exists to prevent.
    receipt.checks.the_protected_verb_leg_names_the_engine_that_produced_it = !!(
      receipt.approvals.protected_capture
      && receipt.approvals.protected_capture.engine
      && typeof receipt.approvals.protected_capture.engine.mock === "boolean"
      && receipt.approvals.protected_capture.real_pcm === false);
    receipt.checks.protected_verb_queued_not_delivered = !!(prot && prot.queued === true
      && prot.delivered === false && prot.delivered_to_conductor === false
      && prot.outcome && prot.outcome.kind === "proposed_action");
    // …and the LIVE pane received nothing — measured against the pane's own text, not against a flag
    // the code sets about itself. The still-anchored clause stops an empty/missing pane from passing.
    const paneAfterProtected = await paneText(win, conductorPane);
    receipt.checks.protected_verb_reached_no_live_pane =
      typeof paneBeforeProtected === "string" && typeof paneAfterProtected === "string"
      && answerAfterAnchor(paneAfterProtected, receipt.voice.transcript, spokenExpected).anchored
      && !/terminate/i.test(String(paneAfterProtected));

    await waitFor(async () => {
      const m = await evalR(win, "window.sovereign.approvals()");
      return Array.isArray(m && m.rows) && m.rows.length > 0;
    }, DRAWER_MS, 500);
    const drawer = await evalR(win, "window.sovereign.approvals()") || {};
    const rows = Array.isArray(drawer.rows) ? drawer.rows : [];
    receipt.approvals.rows = rows.length;
    receipt.approvals.row_ids = rows.map((r) => r && r.id).filter(Boolean);
    receipt.approvals.event_count = drawer.eventCount;
    receipt.approvals.row_provenance = (rows.find((r) => r && r.kind === "protected_action") || {}).detail || null;
    // RECORDED, not gating, and the reason is in fully-live-verdict.js: the event-sourced queue mints
    // `ap-1` for its first real row, so the demonstration trio's ids are not distinguishing and no
    // id-based test can tell the two apart (U213). Provenance is what decides the leg.
    receipt.approvals.demo_ids_present = demoIdsPresent(drawer);
    const drawerVerdict = approvalDrawerIsRealSessionEvents(drawer, { expectedChannel: "voice:capture" });
    receipt.approvals.drawer_verdict = drawerVerdict;
    receipt.checks.approval_drawer_shows_only_real_session_events = drawerVerdict.ok;
    const queued = rows.find((r) => r && r.kind === "protected_action");
    if (queued && queued.id) {
      // REJECT it through the governed authority: the shell self-authorizes nothing, the resolve
      // PERSISTS, and the same item cannot be decided twice (invariant 16 — no override path).
      const res = await evalR(win, `window.sovereign.decideApproval(${JSON.stringify(queued.id)}, "reject", "")`);
      receipt.approvals.decide = res && { routed: res.routed, selfAuthorized: res.selfAuthorized,
        resolved: res.governed && res.governed.resolved };
      const after = await evalR(win, "window.sovereign.approvals()") || {};
      receipt.approvals.after_badge_count = after.badgeCount || 0;
      const again = await evalR(win, `window.sovereign.decideApproval(${JSON.stringify(queued.id)}, "approve", "")`);
      receipt.approvals.re_decide = again && again.governed
        ? { resolved: again.governed.resolved, refused: again.governed.refused } : null;
    }
    receipt.checks.the_queued_event_was_decided_through_the_governed_authority = !!(
      receipt.approvals.decide && receipt.approvals.decide.routed === true
      && receipt.approvals.decide.selfAuthorized === false
      && receipt.approvals.decide.resolved === true
      && receipt.approvals.after_badge_count === 0
      && receipt.approvals.re_decide && receipt.approvals.re_decide.resolved === false
      && receipt.approvals.re_decide.refused === true);

    // ---- 5. [DONE a, second half] THE OPERATOR TAKES THE KEYBOARD BACK, AND TYPES ---------------
    const disarm = exerciseOperatorTypedKeyDisarm();
    receipt.typed.disarm = disarm;
    receipt.checks.operator_keystroke_ended_the_voice_turn = !!(disarm && disarm.disarmed
      && disarm.disarmed.source === "electron_main_before_input_event"
      && disarm.turn && disarm.turn.restricted === false
      && disarm.handled === false && disarm.consumed === false);
    await waitForTuiQuiescence(win, conductorPane, TUI_READY_MS);
    let typedProbe = null;
    const paneBeforeTyped = (await paneText(win, conductorPane)) || "";
    for (let roll = 0; roll < 5; roll++) {
      typedProbe = buildTypedProbe();
      if (!carriesNumber(paneBeforeTyped, Number(typedProbe.expectedNumber))
        && spokenProbeIsFalsifiable(typedProbe)) break;
      typedProbe = null;
    }
    if (!typedProbe) throw new Error("could not draw a typed probe whose answer is absent from the pane");
    receipt.typed.prompt = typedProbe.phrase;
    receipt.typed.expected = typedProbe.expectedNumber;
    const typedExpected = Number(typedProbe.expectedNumber);
    receipt.typed.write = await typeAndSubmit(win, conductorPane, typedProbe.phrase,
      (text) => answerAfterAnchor(text, typedProbe.phrase, typedExpected).anchored, ECHO_MS);
    receipt.checks.typed_prompt_reached_the_same_live_session = !!(receipt.typed.write
      && receipt.typed.write.written && receipt.typed.write.echoed && receipt.typed.write.submitted);
    let typedObserved = { replied: false, number: null, correct: false };
    receipt.typed.answer_seen = await waitFor(async () => {
      typedObserved = answerAfterAnchor(await paneText(win, conductorPane), typedProbe.phrase, typedExpected);
      return typedObserved.replied;
    }, ANSWER_MS, 1000);
    receipt.typed.answer_number = typedObserved.number;
    receipt.typed.answer_matched = typedObserved.correct;   // recorded, not gating
    const afterTyped = await paneText(win, conductorPane);
    receipt.typed.excerpt = typeof afterTyped === "string"
      ? (afterTyped.replace(/\s+/g, " ").trim().slice(-1200) || null) : null;
    receipt.checks.the_same_live_conductor_answered_the_typed_prompt = receipt.typed.answer_seen;
    if (!receipt.typed.answer_seen) {
      throw new Error(`the live conductor never answered the TYPED prompt within ${ANSWER_MS / 1000}s`);
    }
    log(`[selfcheck:fully-live] LIVE typed round trip: replied ${receipt.typed.answer_number} `
      + `(expected ${typedExpected}, correct=${typedObserved.correct})`);

    // ---- 6. [DONE c] A PICKER SELECTION LAUNCHES A LIVE LOCAL WORKER ----------------------------
    // The host's residency, read under a budget nothing can refuse, so the pinned budget below is
    // arithmetic on this host's real numbers rather than a guess (see the constants).
    process.env.SOW_VRAM_BUDGET_MB = PROBE_VRAM_BUDGET_MB;
    const residency = await fetchHostResidency({ cwd: REPO_ROOT, timeoutMs: PICKER_MS });
    const snapshot = (residency.residency && residency.residency.snapshot) || null;
    if (!residency.ok || !snapshot || !Number.isFinite(snapshot.used_vram_mb)) {
      throw new Error(`could not read this host's residency snapshot: ${residency.error || "no snapshot"}`);
    }
    receipt.worker.host_used_vram_mb = snapshot.used_vram_mb;
    const biggest = (snapshot.models || []).reduce(
      (m, e) => (Number.isFinite(e.footprint_mb) && e.footprint_mb > m ? e.footprint_mb : m), 0);
    receipt.worker.budget_pinned_mb = String(Math.max(
      PINNED_VRAM_FLOOR_MB, snapshot.used_vram_mb + biggest + PINNED_VRAM_HEADROOM_MB));
    // Disclosed in the RECEIPT, not only in the code above it (spec-audit F4 — 17B `.spawn` records
    // the same thing as `scope_note_substitutions`): this number is a pinned admission budget so the
    // LOCAL option is admissible and the leg tests the SPAWN. It is arithmetic on the host's real
    // residency snapshot; it is NOT this GPU's capacity, and the residency planner's own gate is
    // 17B `.ticket`'s leg, not this one.
    receipt.worker.budget_source = "env SOW_VRAM_BUDGET_MB, pinned by this check from the host's "
      + `real residency snapshot (used ${snapshot.used_vram_mb} MB + largest footprint ${biggest} MB `
      + `+ ${PINNED_VRAM_HEADROOM_MB} MB headroom, floor ${PINNED_VRAM_FLOOR_MB} MB) — NOT this `
      + "host's GPU capacity, and never verified against it";
    process.env.SOW_VRAM_BUDGET_MB = receipt.worker.budget_pinned_mb;
    const pickerRes = await fetchPickerModel({ cwd: REPO_ROOT, timeoutMs: PICKER_MS });
    receipt.worker.picker_sourced = pickerRes.ok === true;
    const options = (pickerRes.picker && pickerRes.picker.options) || [];
    receipt.worker.option_count = options.length;
    if (!receipt.worker.picker_sourced) throw new Error(`host picker enumeration failed: ${pickerRes.error}`);
    // LOCAL deliberately: a frontier worker pane would take the operator's SECOND governed terminal,
    // and the live dispatch below needs it. The frontier picker spawn is 17B `.spawn`'s gated leg.
    const localOpt = pickOption(options, (o) => o.locality === "local"
      && (o.roles || []).includes("reasoning"), "qwen3:8b");
    receipt.worker.option = localOpt && { label: localOpt.label, model_slug: localOpt.model_slug,
      locality: localOpt.locality, adapter: localOpt.adapter };
    if (!localOpt) throw new Error("the host picker offered no available LOCAL reasoning model to launch");
    const spawnRes = await spawnFromSelection({
      option: localOpt, role: "reasoning", mode: "attended", targetPaneId: null,
    });
    workerPane = spawnRes.target || null;
    receipt.worker.pane_id = workerPane;
    receipt.worker.launched = spawnRes.launched === true;
    receipt.worker.reason = spawnRes.reason || null;
    receipt.worker.argv = spawnRes.argv ? spawnRes.argv.slice() : null;
    receipt.worker.node_id = spawnRes.nodeId || null;
    receipt.worker.chrome_node_state = (spawnRes.chrome || {}).node_state || null;
    receipt.worker.chrome_governed = (spawnRes.chrome || {}).governed === true;
    if (!receipt.worker.launched) {
      throw new Error(`the governed LOCAL worker launch did not run: ${receipt.worker.reason || "unknown"}`);
    }
    const wrec = workerLaunchState(workerPane);
    receipt.worker.subscription_governed = wrec.subscriptionGoverned;
    const wsession = sessionManager() && sessionManager().registry.has(workerPane)
      ? sessionManager().registry.get(workerPane) : null;
    receipt.worker.session_state = wsession ? wsession.state : null;
    receipt.worker.session_pid = wsession ? (wsession.pid || null) : null;
    receipt.worker.pane_output_seen = await waitFor(async () => {
      const t = await paneText(win, workerPane);
      return typeof t === "string" && t.trim().length > 0;
    }, PANE_OUTPUT_MS, 500);
    const wtext = await paneText(win, workerPane);
    receipt.worker.excerpt = typeof wtext === "string"
      ? wtext.replace(/\s+/g, " ").trim().slice(0, 300) : null;
    receipt.checks.picker_selection_started_a_live_local_worker_pane =
      receipt.worker.launched && receipt.worker.session_state === "RUNNING"
      && receipt.worker.pane_output_seen && receipt.worker.chrome_node_state === "running"
      && receipt.worker.chrome_governed === true
      && receipt.worker.node_id === `worker-${workerPane}`;
    // invariant 19: a LOCAL pane holds no subscription terminal — the frontier allowance stays free
    // for the live dispatch worker below, which is what makes the I-X3 leg readable.
    receipt.checks.the_local_worker_held_no_subscription_terminal =
      receipt.worker.subscription_governed === false;
    if (!receipt.checks.picker_selection_started_a_live_local_worker_pane) {
      throw new Error(`the picker-selected LOCAL worker did not come up live: `
        + `${JSON.stringify({ state: receipt.worker.session_state, output: receipt.worker.pane_output_seen })}`);
    }
    log(`[selfcheck:fully-live] picker selection launched ${receipt.worker.option.label} in ${workerPane}`);

    // ---- 7. [DONE d] A GOVERNED DISPATCH IN WHICH A LIVE WORKER DID THE WORK --------------------
    //     Same emitter the conductor chrome sources at launch, asked for `--live-workers` this once.
    //     It is a CHILD of this process, so its worker takes its durable terminal from the SAME
    //     scratch ledger the conductor's session took one from — which is the only reason the I-X3
    //     sample below can say anything.
    const dispatchStarted = Date.now();
    const dispatchPromise = runGovernedDispatch({ liveWorkers: true, timeoutMs: DISPATCH_MS });
    let sampling = true;
    const sampler = (async () => {
      while (sampling) {
        try {
          const s = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 30000 });
          const e = ((s.ok && s.status && s.status.subscriptions) || {})[receipt.conductor.subscription_ref] || null;
          if (e && Number.isFinite(e.in_use)) receipt.concurrency.samples.push(e.in_use);
        } catch { /* a sample this check could not read is simply not a sample */ }
        await sleep(5000);
      }
    })();
    let dispatchRes = null;
    try {
      dispatchRes = await dispatchPromise;
    } finally {
      sampling = false;
      await sampler;
    }
    receipt.dispatch.elapsed_ms = Date.now() - dispatchStarted;
    const feed = (dispatchRes && dispatchRes.feed) || null;
    receipt.dispatch.ok = dispatchRes ? dispatchRes.ok === true : false;
    if (feed) {
      receipt.dispatch.legs = feed.legs || null;
      receipt.dispatch.worker_evidence = feed.worker_evidence || null;
      receipt.dispatch.accepted_count = feed.accepted_count;
      receipt.dispatch.acceptance_verdict = feed.acceptance_verdict || null;
      receipt.dispatch.operator_disposition = feed.operator_disposition || null;
      receipt.dispatch.synthesized_by = feed.synthesized_by || null;
      // `synthesized_by` is a hard-coded adapter literal — `live_succession` says so itself: it reads
      // "conductor_fable5" for EVERY ConductorAdapter, live or mock, so it never discriminates
      // (gate-validator D3). The discriminating field is `legs.conductor`, and it says `mock` here:
      // the conductor SIDE of this dispatch is the prototype adapter. The live half of the leg is the
      // WORKER — its checkpoint is what `liveDispatchIsHonest` reads.
      receipt.dispatch.synthesized_by_note = `legs.conductor=${JSON.stringify((feed.legs || {}).conductor)}`
        + " — `synthesized_by` is a fixed adapter literal, NOT evidence about which backend folded "
        + "the accepted set. A reader beside a live Fable-5 pane must not read it as Fable 5.";
      // The emitter dates and bounds its own live call so a receipt stands on its own (an earlier
      // validator's R1); this composition had dropped it (gate-validator D5).
      receipt.dispatch.live_run = feed.live_run || null;
      receipt.dispatch.torn_down = feed.torn_down;
      // The failure fields, recorded whether or not this run needed them: a receipt that only keeps
      // them on the red path cannot show a reader that the green one had nothing to report.
      receipt.dispatch.failed_count = Number.isFinite(feed.failed_count) ? feed.failed_count : null;
      receipt.dispatch.node_refusals = Array.isArray(feed.node_refusals) ? feed.node_refusals : null;
      receipt.dispatch.gate_summary = feed.gate_summary || null;
      receipt.dispatch.worker_legs = feed.worker_legs || null;
      receipt.dispatch.objective = typeof feed.objective === "string" ? feed.objective : null;
    }
    const dispatchVerdict = liveDispatchIsHonest(feed);
    receipt.dispatch.verdict = dispatchVerdict;
    receipt.checks.a_live_worker_published_a_candidate_that_the_gate_accepted_and_the_conductor_synthesized =
      receipt.dispatch.ok && dispatchVerdict.ok;
    receipt.concurrency.max_in_use_observed = receipt.concurrency.samples.length
      ? Math.max(...receipt.concurrency.samples) : null;
    // I-X3, measured rather than asserted: two live frontier terminals — the operator's conductor
    // session and the dispatch's worker — were counted against ONE subscription's allowance, read
    // from the ledger by a separate process while both were held. The policy constant is NOT
    // asserted here (spec-audit F13 — a config that narrows the allowance to 1 is legitimate); the
    // rule lives in fully-live-verdict.js and says what the leg actually claims.
    const concurrencyVerdict = twoTerminalsOnOneAllowance(receipt.concurrency);
    receipt.concurrency.verdict = concurrencyVerdict;
    receipt.checks.both_live_frontier_terminals_counted_against_one_allowance = concurrencyVerdict.ok;
    if (!receipt.checks.a_live_worker_published_a_candidate_that_the_gate_accepted_and_the_conductor_synthesized) {
      throw new Error(`the live governed dispatch is not honest evidence: `
        + `${(dispatchVerdict.reasons || []).join("; ") || (dispatchRes && dispatchRes.error) || "no feed"}`);
    }
    log(`[selfcheck:fully-live] LIVE dispatch in ${Math.round(receipt.dispatch.elapsed_ms / 1000)}s: `
      + `${dispatchVerdict.live_nodes.join(", ")} → ${receipt.dispatch.accepted_count} accepted `
      + `(${receipt.dispatch.acceptance_verdict}), synthesized by ${receipt.dispatch.synthesized_by}`);

    // ---- 8. the OWED block names every leg this run could not evidence --------------------------
    // Named for what it MEASURES (spec-audit F5): the list is authored, so this rule enforces that
    // every leg we know is unevidenced is named with a reference a reader can look up. It cannot
    // discover a leg nobody wrote down — that is what the gate's two reviewers are for.
    const owedVerdict = owedMarkersAreComplete(receipt.owed);
    receipt.owed_verdict = owedVerdict;
    receipt.checks.every_known_unevidenced_leg_is_named_with_its_reference = owedVerdict.ok;
  } catch (e) {
    receipt.error = String((e && e.message) || e);
    if (log) log(`[selfcheck:fully-live] ${receipt.error}`);
  } finally {
    // ---- D-LOOP-1: nothing this check started outlives it ---------------------------------------
    try {
      const mgr = sessionManager();
      for (const [pane, key] of [[workerPane, "worker_killed"], [conductorPane, "conductor_killed"]]) {
        if (!pane) continue;
        if (mgr && mgr.registry.has(pane)) killSession(pane);
        receipt.teardown[key] = await waitFor(() => {
          const m = sessionManager();
          if (!m || !m.registry.has(pane)) return true;
          return !m.registry.alive().map((s) => s.id).includes(pane);
        }, KILL_MS, 250);
      }
      receipt.teardown.lease_released = await waitFor(async () => {
        const ref = conductorLaunchState().subscriptionRef || receipt.conductor.subscription_ref;
        if (!ref) { receipt.teardown.in_use_after_release = null; return false; }
        const s = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
        if (!s.ok || !s.status) { receipt.teardown.in_use_after_release = null; return false; }
        // an ABSENT entry after a readable status is a legitimate zero (the ledger drops a
        // subscription once its last lease is handed back); an unreadable status is null, not zero.
        const e2 = (s.status.subscriptions || {})[ref] || null;
        receipt.teardown.in_use_after_release = e2 ? e2.in_use : 0;
        return receipt.teardown.in_use_after_release === 0;
      }, RELEASE_MS, 1000);
      const m = sessionManager();
      receipt.teardown.sessions_alive_after = m ? m.registry.alive().map((s) => s.id) : null;
    } catch (e) {
      receipt.error = receipt.error || `teardown failed: ${String((e && e.message) || e)}`;
    }
    receipt.checks.every_live_session_this_check_started_was_torn_down =
      (!conductorPane || receipt.teardown.conductor_killed)
      && (!workerPane || receipt.teardown.worker_killed)
      && Array.isArray(receipt.teardown.sessions_alive_after)
      && receipt.teardown.sessions_alive_after.length === 0;
    receipt.checks.both_governed_terminals_were_handed_back =
      receipt.teardown.lease_released && receipt.teardown.in_use_after_release === 0;
    if (priorLedger === undefined) delete process.env.SOW_TERMINAL_LEASE_LEDGER;
    else process.env.SOW_TERMINAL_LEASE_LEDGER = priorLedger;
    if (priorBudget === undefined) delete process.env.SOW_VRAM_BUDGET_MB;
    else process.env.SOW_VRAM_BUDGET_MB = priorBudget;
    // 17B gated both of these and this composition had dropped them (spec-audit F2): a removal whose
    // result is never read is not a teardown, and "the check never touched the operator's ledger" is
    // a claim, not an assumption. Both are conjuncts of ok, as they were in `.spawn`.
    try { fs.rmSync(SCRATCH_LEDGER, { force: true }); } catch { /* reported below, not swallowed */ }
    receipt.ledger.scratch_removed = !fs.existsSync(SCRATCH_LEDGER);
    receipt.ledger.durable_digest_after = digestOf(DURABLE_LEDGER);
    receipt.ledger.durable_unchanged =
      receipt.ledger.durable_digest_after === receipt.ledger.durable_digest_before;
    receipt.checks.the_operator_own_lease_ledger_was_never_written_to = receipt.ledger.durable_unchanged;
    receipt.checks.the_diagnostic_ledger_was_removed = receipt.ledger.scratch_removed === true;
    // transcribe-then-discard applies to the fixture too — no speech is left on disk.
    try { fs.unlinkSync(FIXTURE_WAV); } catch { /* already gone */ }
  }

  const verdict = composeVerdict(receipt.checks);
  receipt.failed_checks = verdict.failed;
  receipt.ok = receipt.error === null && verdict.ok;
  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node, chrome: process.versions.chrome,
    platform: process.platform, arch: process.arch,
  };
  receipt.substitutions = [
    {
      of: "the physical microphone",
      why: "operator hardware cannot be driven by an automated check — directive §16 puts the "
        + "spoken-mic half in the operator's first use, and the loop never blocks on the operator (§1)",
      what_ran_instead: "the fixture WAV's samples are injected at exactly the point MicRecorder.stop() "
        + "hands its encoded bytes to S.captureVoice; everything below that is the unmodified "
        + "production path — IPC payload, CaptureStore validation + write, real-engine selection, WSL "
        + "Parakeet transcription, bridge routing, the delivery into pane 1's LIVE ConPTY, the "
        + "guaranteed discard. The fixture is OS-synthesized TEST INPUT (the 16E carve-out); the "
        + "product has no TTS (I-V2/D-VOICE-02)",
    },
    {
      of: "OS key delivery for the typed prompt and for the operator's disarming keystroke",
      why: "an automated check cannot press a physical key, and U69 records that trusted keydowns "
        + "into the focused xterm produced no terminal data on this host with no mechanism isolated",
      what_ran_instead: "typed text reaches the session through the renderer's real "
        + "term.input → pane:input → SessionManager.write path (the production path), and the disarm "
        + "drives main's production before-input-event handler with a synthesized keyDown — the same "
        + "handler an operator keystroke enters, with the same decision behind it",
    },
    {
      of: "the operator's own objective, for the governed dispatch",
      why: "the live conductor CLI does not itself choose to delegate over MCP (the U58 residual, "
        + "named in receipt.owed) — the dispatch is invoked by the shell with the emitter's own "
        + "pinned objective, exactly as the conductor chrome sources its mock-first one at launch",
      what_ran_instead: "the SAME emitter, asked for `--live-workers` once: a real live "
        + "`claude_code` worker node, a real CANDIDATE published over a loopback MCP server, the real "
        + "gate engine, and the conductor's own synthesis into an acceptance packet whose "
        + "operator_disposition stays `pending`. Its leg label is derived from a VERIFIED executing "
        + "checkpoint (U45), not from the fact that a call was attempted",
    },
    {
      of: "real speech, for the PROTECTED-VERB half of the approval leg",
      why: "a protected verb must be refused before anything is delivered, and proving that needs "
        + "no microphone and no live exchange — the leg is about the broker's refusal and the "
        + "drawer's provenance, not about transcription",
      what_ran_instead: "a scripted `audio:` stand-in ref, which carries no PCM and is therefore "
        + "routed through the VISIBLE mock engine (`approvals.protected_capture.engine.mock` is "
        + "true, `real_pcm` false — recorded, because this receipt's `voice.engine` block says "
        + "mock:false about the SPOKEN leg and a reader must not carry that across). Everything "
        + "after the transcript is the production path: the real router, the real broker, the real "
        + "append-only event record and the real Python fold",
    },
    {
      of: "the host's real GPU capacity, for the picker leg's admission budget",
      why: "the LOCAL option has to be admissible for the leg to test the SPAWN; the residency "
        + "planner's own admission gate is 17B `.ticket`'s leg, and a leg that exercises a "
        + "different gate than its name claims is evidence for the wrong thing",
      what_ran_instead: "`SOW_VRAM_BUDGET_MB` pinned to arithmetic on the host's REAL residency "
        + "snapshot (recorded verbatim in `worker.budget_source`, with `host_used_vram_mb` as read "
        + "from the live daemon). The enumeration itself is the host's own (`worker.option_count` "
        + "is what the daemon offered, never fabricated) and the model this leg starts is a real "
        + "local one the picker listed",
    },
    {
      of: "a FRONTIER worker pane from the picker",
      why: "I-X3 allows two terminals on this subscription and the live dispatch worker needs the "
        + "second one; a frontier picker spawn would have taken it and made the dispatch refuse",
      what_ran_instead: "the picker leg launches the host's real LOCAL `qwen3:8b` (which holds no "
        + "subscription terminal, invariant 19). The frontier picker spawn is 17B `.spawn`'s own "
        + "gated leg — docs/evidence/receipts/PHASE17B_SPAWN_SELFCHECK.json",
    },
  ];
  receipt.substitution = receipt.substitutions.map((s) => `${s.of}: ${s.what_ran_instead}`).join(" · ");
  receipt.scope_note = "WHAT THIS RECEIPT IS: one Electron process in which the operator's stated "
    + "DEFINITION OF DONE holds at once — a live conductor in pane 1 that answers both a spoken and a "
    + "typed prompt, a picker selection that starts a live local worker, a governed dispatch whose "
    + "worker really executed, and an approval drawer carrying only this session's own event. Each "
    + "leg was proven alone by an earlier gated receipt; the claim here is the COMPOSITION, and "
    + "nothing else in this file should be read as a stronger version of those earlier claims. "
    + "WHAT IT DOES NOT CLAIM, in `receipt.owed` rather than buried here: a human spoke into a "
    + "microphone; the operator's own OS keystrokes reach a pane (U69, still unexplained); the live "
    + "conductor CLI decided to delegate (the dispatch is shell-invoked — the U58 residual); the "
    + "product can speak (I-V2 stands, tts:false is asserted); cloud Kimi/Qwen exist here. "
    + "MODEL ARITHMETIC IS RECORDED AND DOES NOT GATE, for 17C's measured reason: the gating fact is "
    + "that the conductor REPLIED with a standalone number of its own after the whole prompt echoed "
    + "and the prompt contains none — `answer_matched` says whether that number was right. "
    + "THE I-X3 LEG is the one thing here that no earlier receipt could show: two live frontier "
    + "terminals — pane 1's conductor and the dispatch's worker — held at once and counted against "
    + "ONE subscription's allowance, sampled by a separate process while both were live. It is "
    + "readable only because the dispatch emitter is a child of this process and inherits the "
    + "DIAGNOSTIC (scratch) ledger. That redirection cuts BOTH ways and this unit stopped stating "
    + "only the flattering half (U111, spec-audit F1): it is what stops this check from ever "
    + "adopting or releasing a terminal the operator's own shell holds, AND it is why the enforcing "
    + "governor counted zero for the window — an operator shell already at its allowance could have "
    + "brought the true total to 4. A diagnostic ledger now COUNTS the durable one as a read-only "
    + "baseline in every admission decision; `concurrency.scope` and `concurrency.baseline_in_use` "
    + "record that this run's count was the governing one. SAY THE RESIDUAL PLAINLY (U215, spec-audit "
    + "M5 — the earlier draft put the 4-terminal scenario in the past tense, which was the flattering "
    + "half again): the overlay is ONE-WAY. A durable ledger carries no baseline path, so the "
    + "operator's own shell never counts THIS run's leases at any moment of the run — not merely "
    + "inside a read-to-write window. What changed is that the CHECK can no longer be the party that "
    + "overshoots. "
    + "WHOSE CONDUCTOR SYNTHESIZED the dispatch: `legs.conductor` says `mock`. `synthesized_by` "
    + "reads `conductor_fable5` for every ConductorAdapter ever built — a fixed literal, not a "
    + "measurement (gate-validator D3, `dispatch.synthesized_by_note`). The LIVE half of that leg is "
    + "the WORKER, whose executed/spent/VERIFIED checkpoint is what the verdict reads. "
    + "WHAT THE APPROVAL LEG READS, and why it is not the row's id: the first run of this receipt "
    + "refused a genuine session event because the event-sourced queue mints `ap-1` for its FIRST "
    + "real row — the same id the deterministic demonstration trio's first item uses. So the ids are "
    + "not distinguishing in either direction (U213), `demo_ids_present` records the collision, and "
    + "the leg is decided on PROVENANCE instead: the drawer was folded from a recorded event, and the "
    + "queued row names the event id, the channel that recorded it (`voice:capture`) and that "
    + "channel's feed schema — none of which a canned item has any way to carry. What that leg's "
    + "\"ONLY\" is worth, stated: this run causes ONE event, so the quantifier is exercised over one "
    + "row of one kind (gate-validator m3). The rule reads every row and the multi-row reproduction "
    + "of the iteration-100 defect lives in `fully-live-verdict.test.js`, not here; and provenance is "
    + "a SHAPE check — a canned row carrying a fabricated event id and a real channel would pass it. "
    + "What actually keeps the demonstration trio out of the product path is that "
    + "`tests/support/demo_approval_queue.py` is unreachable from it, and that "
    + "`session_approvals` re-derives every row's classification and fails closed on disagreement.";

  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    if (log) log(`[selfcheck:fully-live] could not write receipt: ${e && e.message}`);
  }
  if (log) {
    log(`[selfcheck:fully-live] ${receipt.ok ? "PASS" : `FAIL (${receipt.failed_checks.join(", ") || receipt.error})`} → ${RECEIPT_PATH}`);
  }
  return receipt;
}

module.exports = { runFullyLiveSelfCheck: run, RECEIPT_PATH, FIXTURE_WAV };
