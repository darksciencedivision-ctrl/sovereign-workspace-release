"use strict";
/**
 * Phase 17C `.close` in-Electron receipt (D-P16-0 binding, per-track) — the leg the whole track is
 * named for: **the operator's speech reaches the LIVE conductor session and the conductor answers.**
 *
 * WHY THIS EXISTS, precisely. `.probe` stopped the badge lying about the engine (U74). `.mic` pushed
 * real captured PCM through the shipped path into real WSL Parakeet and proved a routed CHAT transcript
 * lands in an admitted pane's ConPTY (U137) — and said, in its own receipt, what it could not claim:
 * directive §16 track 17C requires *"→ the LIVE 17A conductor session"*, and `.mic`'s delivery pane was
 * a `powershell.exe` stand-in whose conductor pane was still `awaiting_live_conductor`. A shell echoes
 * anything written to it; that receipt therefore could not distinguish "the transcript was delivered"
 * from "a conductor received it". This check closes exactly that gap, end to end, in one run:
 *
 *   supervision READY → the GOVERNED live launch of the real interactive `claude` in pane 1 (the same
 *   production path 17A gated) → a spoken fixture → the shipped capture path (CaptureStore → real WSL
 *   Parakeet → the Python bridge's CHAT verdict) → the production delivery into **pane 1's live ConPTY**
 *   → **the model's own answer**, read back out of the xterm buffer.
 *
 * TELLING AN ECHO FROM AN ANSWER (voice/spoken-probe.js). The pane will contain the transcript, because
 * the live CLI echoes its input. So the probe is arithmetic whose answer cannot be an echo, and the
 * expected answer is derived from **the transcript** — the question the conductor was actually asked —
 * not from what the fixture said, because an ASR is free to hear "twenty-three" as "23" or as
 * "twenty-two". Four assertions keep it falsifiable and they fail independently:
 *   • the answer is absent from the pane BEFORE the delivery (a fresh draw, re-rolled if not);
 *   • the answer is absent from the TRANSCRIPT (so the echo cannot satisfy it);
 *   • the WHOLE utterance must echo — the anchor is the entire transcript, not the arithmetic fragment
 *     at the front of it, so a delivery truncated after that fragment cannot pass with a correct-looking
 *     answer (the hole the gate-validator found in this check's first draft);
 *   • the answer is searched ONLY in what the pane painted AFTER that echo, because the live CLI's own
 *     chrome prints bare numbers ("⎿ Read 69 lines", "↑69 ↓12") and a reply is necessarily after its
 *     own prompt. Echo and answer remain separate checks: a dead model cannot pass on a live terminal,
 *     and a live model cannot cover for an utterance that never arrived.
 *
 * THE SUBSTITUTION, unchanged from `.mic` and stated again because it is the only one (directive §6):
 * a physical microphone cannot be driven by an automated check — *"the spoken-mic half is operator first
 * use"*. The fixture WAV's bytes are injected at exactly the point `MicRecorder.stop()` hands its
 * encoding to `S.captureVoice({pcm, sampleRate})`; everything from there on is production code. The
 * fixture is OS-synthesized TEST INPUT (the 16E carve-out, restated); the product still has no TTS and
 * this check asserts `tts:false`.
 *
 * LIVE SCOPE (§16 "live exchanges MINIMAL"): ONE live session, ONE utterance, ONE answer of a few
 * tokens, then the session is killed and the durable I-X3 terminal handed back (D-LOOP-1). The lease
 * ledger is SCRATCH throughout, so this check can never adopt or release the operator's own terminal.
 *
 * `.disarm` (U166) ADDS ONE MORE LIVE EXCHANGE, and it is the point of that sub-step. Every run of
 * this check until now made its single voice turn the LAST act before teardown — so nothing followed
 * it that the restriction could block, and the receipt passed 41/41 while an admitted voice turn
 * never disarmed: after the first utterance the operator's own typed prompts were blocked and every
 * tool call denied for the rest of the session. The missing leg is therefore now here: the operator's
 * keystroke ends the turn (through main's own before-input-event handler) and a SECOND, TYPED prompt
 * is accepted and answered by the SAME live conductor session — §13 item 2, typed AND spoken.
 *
 * `.receipt` (U177) ADDS THE RUNTIME CROSS-CHANNEL ASSERTION, and it is here because this is the only
 * place an ADMITTED turn exists. The static guard pins which call sites may end a turn; it cannot see
 * a callee reached through a getter or a Proxy trap, or a reference stored on one channel and invoked
 * from another, and its own header says so. So section 11b drives EVERY renderer IPC channel while the
 * operator's spoken turn is admitted and then asks the supervisor — from its own state, not from the
 * absence of an audit row — whether it still holds that turn, and re-dispatches a real PreToolUse to
 * show the restriction is still ENFORCED rather than merely recorded. It buys no model tokens; it is
 * not free of effect, and the first version proved why — it spawns one supervised scratch session
 * (closed within the sweep), and it writes bytes into the live session, which is why those bytes are
 * now a kill-line control character and nothing that could become the operator's next prompt.
 */
const fs = require("fs");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const { decodeWav } = require("../voice/wav");
const { childEnv } = require("../voice/env-scrub");
const { dispatchHookEvent } = require("../voice/turn-boundary-probe");
const { fetchLeaseStatus } = require("../conductor/launch-source");
const { turnSurvivedChannelSweep } = require("../voice/turn-survival");
const { registeredIpcChannels, ipcRegistrationCounts, SWEEP_PROBE } = require("../renderer/channel-sweep");
const {
  buildSpokenProbe, buildTypedProbe, parseHeardArithmetic, carriesNumber, spokenProbeIsFalsifiable,
  answerAfterAnchor,
} = require("../voice/spoken-probe");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const RECEIPT_PATH = path.resolve(REPO_ROOT, "docs", "evidence", "receipts", "PHASE17C_CLOSE_SELFCHECK.json");
const FIXTURE_WAV = path.resolve(REPO_ROOT, "tools", "live", "_voice_fixture_close.wav");
const CAPTURE_DIR = path.resolve(__dirname, "..", ".voice-captures");
const SCRATCH_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", `selfcheck-17cc-${process.pid}.json`);
// The session id this check's OWN hook dispatches carry, so the audit can tell a measured denial
// apart from one the vendor's own process caused (U164) — the two are different claims.
const SUPERVISOR_PROBE_SESSION = "sovereign-selfcheck-hook-probe";
// The only provenances that may appear on a row which CLEARED the voice restriction: the two
// operator signals Electron main observes on the OS input path, plus the node-pty exit it observes
// for itself. Anything else on such a row means the vendor process got its authority back by saying
// so — including bytes on the pane:input channel, which xterm.js also emits for terminal replies the
// pane's own process can elicit.
const MAIN_OWNED_RELEASE_SOURCES = [
  "electron_main_before_input_event",
  "electron_main_operator_chord",
  "node_pty_exit",
];

// Per-step ceilings, each named in the failure it produces, so a stall reports WHICH step stalled
// instead of being killed blind by the launcher.
const SUPERVISION_MS = 30000;
const TUI_READY_MS = 45000;
const PROBE_SETTLE_MS = 180000;
const FIXTURE_MS = 120000;
const TRANSCRIBE_MS = 420000;
const ECHO_MS = 30000;
const ANSWER_MS = 180000;
const KILL_MS = 15000;
const RELEASE_MS = 45000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function exactProcessExitResetObserved(audit, expected) {
  return Array.isArray(audit) && audit.some((row) => row.event === "voice_turn_reset"
    && row.source === "node_pty_exit"
    && row.process_exited === true
    && row.pane_id === expected.paneId
    && row.session_id === expected.sessionId
    && row.pid === expected.pid
    && row.generation === expected.generation);
}

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

/** What the OPERATOR can see about the voice-turn restriction, read from the painted chrome. */
async function turnBadge(win, paneId) {
  await evalR(win, "window.__sovereignSelfCheck && window.__sovereignSelfCheck.refreshVoiceChrome()");
  return evalR(win,
    `window.__sovereignSelfCheck && window.__sovereignSelfCheck.voiceTurnBadge(${JSON.stringify(paneId)})`);
}

/**
 * Type a whole prompt into a live pane the way the operator does — and SUBMIT it only after the pane
 * has echoed it back. Same rule the voice delivery follows and for the same measured reason: a body
 * and a bare `\r` in one write does not reach the live CLI as a submitted message, and an
 * unconditional `\r` answers whatever prompt the pane happens to be showing.
 */
async function typeAndSubmit(win, paneId, body, isEchoed, echoMs) {
  const written = (await typeInto(win, paneId, body)) === true;
  if (!written) return { written: false, echoed: false, submitted: false };
  // wrap-tolerant, by the same matcher the spoken utterance uses: a full-screen TUI re-renders its
  // input box with escape sequences and may break one sentence across lines.
  const echoed = await waitFor(async () => isEchoed((await paneText(win, paneId)) || ""), echoMs, 250);
  if (!echoed) return { written, echoed: false, submitted: false };
  const submitted = (await typeInto(win, paneId, "\r")) === true;
  return { written, echoed, submitted };
}

/** Files sitting in the capture directory — the filesystem's own answer about invariant 26. */
function captureFiles() {
  try { return fs.readdirSync(CAPTURE_DIR).filter((n) => n.endsWith(".wav")); } catch { return []; }
}

function boundaryAudit(readAudit) {
  try {
    const rows = readAudit();
    return Array.isArray(rows) ? rows.map((row) => ({ ...row })) : [];
  } catch {
    return [];
  }
}

function sourceIdentity() {
  const commit = spawnSync("git", ["rev-parse", "HEAD"], {
    cwd: REPO_ROOT, encoding: "utf8", timeout: 10000,
  });
  const productPaths = [
    "apps/desktop", "terminal", "tools/live", "node_runtime", "adapters",
    "voice_bridge", "control_plane",
  ];
  const diff = spawnSync("git", ["diff", "--quiet", "HEAD", "--", ...productPaths], {
    cwd: REPO_ROOT, encoding: "utf8", timeout: 10000,
  });
  const others = spawnSync("git", ["ls-files", "--others", "--exclude-standard", "--", ...productPaths], {
    cwd: REPO_ROOT, encoding: "utf8", timeout: 10000,
  });
  // No carve-outs. `apps/desktop/package-lock.json` was the only one and it has been TRACKED since
  // 3d57eeb, so the exclusion had stopped excluding anything while the receipt still advertised it —
  // a field describing a hole that no longer exists (gate-validator R-5).
  const disclosedExclusions = [];
  const untracked = others.status === 0
    ? others.stdout.split(/\r?\n/).filter(Boolean).map((p) => p.replace(/\\/g, "/"))
    : [];
  const unexpectedUntracked = untracked.filter((p) => !disclosedExclusions.includes(p));
  return {
    commit: commit.status === 0 ? commit.stdout.trim() : null,
    tracked_product_tree_clean: diff.status === 0,
    disclosed_untracked_product_exclusions: disclosedExclusions,
    unexpected_untracked_product_files: unexpectedUntracked,
    product_paths: productPaths,
  };
}

const committedTreeCheckName =
  "receipt_matches_committed_tracked_product_tree_with_disclosed_exclusions";

/**
 * The interactive CLI is ready for input when it has painted the governed workspace it opened AND
 * stopped repainting. Quiescence is what makes the delivered transcript land in the input box rather
 * than into a half-drawn frame. (Same rule 17A `.roundtrip` established; kept local rather than
 * refactored out of that gated check, so this unit cannot regress 17A's evidence path.)
 */
async function waitForTuiQuiescence(win, paneId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  let stableSince = null;
  while (Date.now() < deadline) {
    const text = await paneText(win, paneId);
    const painted = typeof text === "string" && text.replace(/\s+/g, "").includes(REPO_ROOT.replace(/\s+/g, ""));
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
    // The packaged main process `require`s this module unconditionally, so the OS synthesizer is
    // reachable from the shipped app — under `SHELL_SELFCHECK` only. Asserted here rather than assumed
    // (spec-audit MINOR-8): I-V2 says the product never speaks, and "no caller does this by accident"
    // is not an enforcement.
    if (!process.env.SHELL_SELFCHECK) {
      resolve({ ok: false, error: "refusing to synthesize outside a self-check run (I-V2/D-VOICE-02)" });
      return;
    }
    const { env } = childEnv({}, process.env);   // U136: even a local diagnostic child gets a scrubbed env
    const child = spawn("py", ["-3.12", "tools/live/make_voice_fixture.py", FIXTURE_WAV, phrase],
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
      if (log) log(`[selfcheck:voice-conductor] fixture ${rec.wav_bytes} bytes / ${rec.seconds}s @ ${rec.sample_rate}Hz`);
      resolve({ ok: true, fixture: rec });
    });
  });
}

async function run(ctx) {
  const { win, isSupervised, conductorState, launchConductorSession, conductorLaunchState,
    sessionManager, killSession, voiceState, voiceAuthorityAudit, voiceAuthorityState,
    voiceAuthorityChildEnv, exerciseOperatorResumeGesture, exerciseOperatorTypedKeyDisarm,
    armVoiceTurnForExitCheck, log } = ctx;
  const receipt = {
    // @1.1 at `.disarm`: two legs were renamed to what they measure and the turn-release/typed-prompt
    // legs were added, so a consumer must not read this as a `@1.0` receipt.
    // @1.2 at `.disarm-authority` (U178): `chrome_stops_claiming_a_restriction_that_ended` is gone —
    // it asserted a blank badge where a denial is still running — replaced by
    // `chrome_shows_the_turn_ended_with_its_answer_still_denied` plus the new
    // `ended_voice_turn_still_denies_its_own_answers_tools` dispatch.
    // @1.3 at `.receipt` (U177): the runtime cross-channel assertion — every renderer IPC channel is
    // driven while the operator's turn is ADMITTED, and four new legs say what survived it.
    // @1.4, same sub-step, after both reviewers read the @1.3 run: a fifth leg
    // (`channel_sweep_wrote_no_prompt_text_into_the_live_conductor`), an admission predicate inside
    // the coverage leg, a registration-shape refusal in the coverage counters, and a drop-counter
    // window in the survival verdict. A consumer must not read this as @1.3.
    schema: "phase17c_close_selfcheck@1.4",
    check: "phase-17c.receipt",
    started: new Date().toISOString(),
    source: sourceIdentity(),
    ok: false,
    ledger_scope: "scratch",
    ledger_path: SCRATCH_LEDGER,
    electron_main_pid: process.pid,
    // the LIVE conductor session (the production 17A path — not a stand-in pane)
    supervision_ready: false,
    pane_id: null,
    launched: false,
    launch_state: null,
    launch_reason: null,
    argv: null,
    session_id: null,
    session_pid: null,
    session_generation: null,
    session_state: null,
    conductor_live: null,
    model_label: null,
    model_slug: null,
    model_probe_source: null,
    model_is_fallback: null,
    authority_boundary: null,
    authority_audit: [],
    // the MEASURED tool denial (U164) and what the vendor itself did
    pinned_hook_command: null,
    tool_denial_probe: null,
    tool_denial_unauthenticated: null,
    vendor_tool_attempt_observed: null,
    // U177 — the runtime cross-channel assertion
    channel_sweep: null,
    channel_sweep_coverage: null,
    channel_sweep_scratch_pane: null,
    channel_sweep_left_probe_text_in_the_pane: null,
    turn_state_before_channel_sweep: null,
    turn_survived_channel_sweep: null,
    tool_denial_after_channel_sweep: null,
    operator_recovery: null,
    lease_id: null,
    lease_in_use: null,
    lease_allowance: null,
    tui_ready: false,
    typed_equivalence_probe: "typed-path-equivalence",
    typed_via_renderer: false,
    typed_probe_echoed: false,
    typed_probe_cancelled: false,
    // the spoken probe
    spoken_phrase: null,
    spoken_operands: null,
    spoken_expected: null,
    probe_rerolls: 0,
    fixture: null,
    // the capture (production path)
    probe_at_capture: null,
    transcribe_ms: null,
    transcript: null,
    engine_used: null,
    capture_meta: null,
    heard: null,
    heard_expected: null,
    asr_matched_the_spoken_operands: null,
    // the delivery into the LIVE session
    write: null,
    owed_record: null,
    protected_capture: null,
    subscription_ref: null,
    echo_seen: false,
    answer_seen: false,
    answer_number: null,
    answer_matched_the_arithmetic: null,
    answer_latency_ms: null,
    answer_excerpt: null,
    // invariant 26 / U133
    capture_files_during: null,
    capture_files_after: null,
    capturing_during: null,
    capturing_after: null,
    // D-LOOP-1
    session_killed: false,
    lease_released: false,
    in_use_after_release: null,
    checks: {},
    failed_checks: [],
    error: null,
  };
  receipt.checks[committedTreeCheckName] = Boolean(
    receipt.source.commit && receipt.source.tracked_product_tree_clean
    && receipt.source.unexpected_untracked_product_files.length === 0);

  const priorLedger = process.env.SOW_TERMINAL_LEASE_LEDGER;
  process.env.SOW_TERMINAL_LEASE_LEDGER = SCRATCH_LEDGER;
  let paneId = null;
  try {
    // 1. supervision READY — a session is only ever born on a verified channel (invariant 2)
    receipt.supervision_ready = await waitFor(isSupervised, SUPERVISION_MS, 250);
    receipt.checks.supervision_ready = receipt.supervision_ready;
    if (!receipt.supervision_ready) throw new Error("supervision never became READY (no session may be born)");
    paneId = conductorState().paneId;
    receipt.pane_id = paneId;
    if (!paneId) throw new Error("no conductor pane exists to speak to");

    // 2. THE GOVERNED LIVE LAUNCH — the production path (live_operation switch → provider-live → OP-9
    //    terms → `claude` presence → durable I-X3 lease), identical to on-launch and to the pane-1
    //    control. This is what makes the delivery below a delivery to a CONDUCTOR rather than to a shell.
    const res = await launchConductorSession({ reason: "in-Electron self-check (17C .close)" });
    const st = conductorLaunchState();
    receipt.launched = res.launched === true;
    receipt.launch_state = st.state;
    receipt.launch_reason = st.reason || (res && res.reason) || null;
    receipt.argv = Array.isArray(st.argv) ? st.argv.slice() : null;
    receipt.session_id = st.sessionId || null;
    receipt.session_pid = st.pid || null;
    receipt.session_generation = st.sessionGeneration || null;
    receipt.lease_id = st.leaseId || null;
    const slugAt = Array.isArray(receipt.argv) ? receipt.argv.indexOf("--model") : -1;
    receipt.model_slug = slugAt >= 0 ? receipt.argv[slugAt + 1] || null : null;
    receipt.model_label = (st.modelProbe && st.modelProbe.label) || null;
    receipt.model_probe_source = (st.modelProbe && st.modelProbe.source) || null;
    receipt.model_is_fallback = (st.modelProbe && st.modelProbe.model_available === false) || false;
    receipt.authority_boundary = st.authorityBoundary || null;
    receipt.checks.live_conductor_launched = receipt.launched;
    receipt.checks.supervisor_voice_boundary_bound = !!(receipt.authority_boundary
      && receipt.authority_boundary.schema === "voice_turn_boundary@1.0"
      && receipt.authority_boundary.supervisor_owned === true
      && receipt.authority_boundary.non_executing_voice_turns === true
      && receipt.authority_boundary.enforced_by_supervisor_process === true
      && receipt.authority_boundary.broker_schema === "supervisor_voice_turn_authority@1.0"
      && Array.isArray(receipt.argv) && receipt.argv.includes("--settings"));
    if (!receipt.launched) throw new Error(`the governed live launch did not run: ${receipt.launch_reason || "unknown"}`);
    receipt.operator_recovery = exerciseOperatorResumeGesture();
    receipt.checks.main_owned_operator_recovery = Boolean(receipt.operator_recovery
      && receipt.operator_recovery.handled === true
      && receipt.operator_recovery.consumed === true
      && receipt.operator_recovery.reset
      && receipt.operator_recovery.reset.source === "electron_main_operator_chord");
    const mgr = sessionManager();
    receipt.session_state = mgr && mgr.registry.has(paneId) ? mgr.registry.get(paneId).state : null;
    receipt.checks.live_session_running = receipt.session_state === "RUNNING";
    if (!receipt.checks.live_session_running) throw new Error(`the conductor session is ${receipt.session_state}, not RUNNING`);
    // the shell's OWN observable claim about pane 1 — what the operator's chrome reads
    receipt.conductor_live = conductorState().live === true;
    receipt.checks.chrome_reports_pane1_live = receipt.conductor_live;
    receipt.subscription_ref = st.subscriptionRef || null;
    const leaseStatus = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
    const entry = ((leaseStatus.ok && leaseStatus.status && leaseStatus.status.subscriptions) || {})[st.subscriptionRef] || null;
    receipt.lease_in_use = entry ? entry.in_use : null;
    receipt.lease_allowance = leaseStatus.ok && leaseStatus.status ? leaseStatus.status.allowance : null;
    // The live session consumed exactly one of the operator's governed terminals, READ back across the
    // process boundary. Load-bearing for the teardown leg below, which used to pass vacuously when the
    // subscription ref was missing (validator D-5): no ref ⇒ no entry ⇒ `in_use` defaulted to 0 ⇒ "the
    // terminal was handed back" without any lease having been read at all.
    receipt.checks.durable_terminal_taken = Boolean(st.subscriptionRef) && receipt.lease_in_use === 1;

    // 3. let the live CLI finish painting and settle before anything is delivered into it
    const tui = await waitForTuiQuiescence(win, paneId, TUI_READY_MS);
    receipt.tui_ready = tui.ready;
    receipt.checks.live_session_ready_for_input = receipt.tui_ready;
    if (!receipt.tui_ready) throw new Error("the live conductor session never settled into a ready, quiescent view");

    // 4. CURRENT-TREE PHYSICAL TYPED PATH (U149): type into xterm through the renderer's real
    //    onData→pane:input→SessionManager.write path, observe the bytes in the same pane, then Ctrl-C
    //    before Enter so this costs no model exchange. Voice below reaches the same SessionManager
    //    write boundary, with the additional supervisor non-executing marker required by invariant 25.
    receipt.typed_via_renderer = (await typeInto(
      win, paneId, receipt.typed_equivalence_probe)) === true;
    receipt.typed_probe_echoed = receipt.typed_via_renderer && await waitFor(async () => {
      const text = await paneText(win, paneId);
      return typeof text === "string" && text.includes(receipt.typed_equivalence_probe);
    }, ECHO_MS, 250);
    receipt.typed_probe_cancelled = (await typeInto(win, paneId, "\x03")) === true;
    receipt.checks.physical_typed_path_reaches_same_conductor_input =
      receipt.typed_via_renderer && receipt.typed_probe_echoed && receipt.typed_probe_cancelled;
    if (!receipt.checks.physical_typed_path_reaches_same_conductor_input) {
      throw new Error("the current-tree renderer typed path did not reach and clear the conductor input");
    }
    await waitForTuiQuiescence(win, paneId, TUI_READY_MS);

    // 5. the STT engine answer the shell has already established (U134) — so the capture below pays for
    //    no second WSL NeMo import. Bounded; recorded unmet rather than skipped if it never settles.
    receipt.probe_settled = await waitFor(() => {
      const s = voiceState && voiceState();
      return !!(s && s.probe && s.probe.state === "available");
    }, PROBE_SETTLE_MS, 500);
    receipt.probe_at_capture = voiceState ? voiceState().probe : null;
    receipt.checks.probe_settled_before_capture = receipt.probe_settled;

    // 6. draw a spoken probe whose answer the pane cannot already contain
    let probe = null;
    const before = (await paneText(win, paneId)) || tui.text || "";
    for (let roll = 0; roll < 5; roll++) {
      probe = buildSpokenProbe();
      receipt.probe_rerolls = roll;
      if (!carriesNumber(before, Number(probe.expectedNumber))) break;
      probe = null;  // this draw's answer is already on screen — it would pass for free
    }
    if (!probe) throw new Error("could not draw an answer absent from the pane in 5 attempts");
    receipt.spoken_phrase = probe.phrase;
    receipt.spoken_operands = { a: probe.a, b: probe.b };
    receipt.spoken_expected = probe.expectedNumber;
    receipt.checks.spoken_probe_falsifiable = spokenProbeIsFalsifiable(probe);
    if (!receipt.checks.spoken_probe_falsifiable) throw new Error("the drawn phrase carries its own answer — the receipt would prove nothing");

    // 7. SPEAK IT: synthesize the utterance, then push its bytes through the shipped capture path.
    const fx = await makeFixture(probe.phrase, log);
    receipt.fixture = fx.ok ? fx.fixture : { error: fx.error };
    if (!fx.ok) throw new Error(fx.error);
    const wavBytes = fs.readFileSync(FIXTURE_WAV);
    const decoded = decodeWav(new Uint8Array(wavBytes));
    receipt.fixture.decoded = { sampleRate: decoded.sampleRate, samples: decoded.samples,
                                seconds: Math.round(decoded.seconds * 1000) / 1000 };

    const filesBefore = captureFiles();
    let sawFile = false;
    let sawCapturing = false;
    const watcher = setInterval(() => {
      if (captureFiles().length > filesBefore.length) sawFile = true;
      try { const s = voiceState && voiceState(); if (s && s.control && s.control.capturing === true) sawCapturing = true; } catch { /* transient */ }
    }, 150);
    let cap = null;
    try {
      const expr = `window.__sovereignSelfCheck.captureVoicePcm(${JSON.stringify(Array.from(wavBytes))}, ${decoded.sampleRate})`;
      const started = Date.now();
      cap = await Promise.race([evalR(win, expr), sleep(TRANSCRIBE_MS).then(() => null)]);
      receipt.transcribe_ms = Date.now() - started;
    } finally {
      clearInterval(watcher);
    }
    if (!cap) throw new Error(`the capture never resolved within ${TRANSCRIBE_MS / 1000}s`);
    receipt.capture_files_during = sawFile;
    receipt.capture_files_after = captureFiles();
    receipt.capturing_during = sawCapturing;
    const sAfter = voiceState ? voiceState() : null;
    receipt.capturing_after = !!(sAfter && sAfter.control && sAfter.control.capturing);

    const engine = cap.engine || {};
    const meta = cap.capture || {};
    receipt.transcript = cap.delivered_text;
    receipt.engine_used = { name: engine.name, mock: engine.mock, real_available: engine.real_available };
    receipt.capture_meta = meta;
    receipt.write = cap.write || null;
    log(`[selfcheck:voice-conductor] engine=${engine.name} mock=${engine.mock} `
      + `transcript=${JSON.stringify(cap.delivered_text)} write=${JSON.stringify(cap.write)}`);

    // the capture legs (the same facts `.mic` measured, re-measured here because this run's transcript
    // is the thing being delivered — a receipt that assumed them would be citing another run)
    receipt.checks.capture_sourced = cap.sourced === true;
    receipt.checks.capture_carried_real_pcm = meta.real_pcm === true && meta.bytes === wavBytes.length;
    receipt.checks.real_engine_transcribed = engine.mock === false && engine.real_available === true
      && String(engine.name || "").includes("parakeet");
    receipt.checks.routed_as_chat = cap.delivered === true && !!cap.outcome && cap.outcome.kind === "chat";
    receipt.checks.audio_existed_during_transcription = sawFile;
    receipt.checks.audio_discarded_after = receipt.capture_files_after.length === filesBefore.length
      && meta.discarded === true;
    receipt.checks.capturing_visible_during = sawCapturing;
    receipt.checks.capturing_cleared_after = receipt.capturing_after === false;
    receipt.checks.no_tts = cap.tts === false;
    receipt.checks.self_authorized_false = cap.selfAuthorized === false;

    // 7. THE DELIVERY — into the LIVE conductor session, by the production path. `delivered_to_conductor`
    //    is main's own report that BOTH writes landed (body + echo-confirmed submit key); the pane
    //    assertions below are what make it more than a claim.
    receipt.checks.delivered_into_live_conductor = cap.delivered_to_conductor === true;
    receipt.checks.submit_key_delivered = !!(cap.write && cap.write.submitted === true);
    // The submit key waited on an OBSERVATION, not a timer: main saw the pane echo the utterance back
    // in its own ConPTY output before pressing Enter. Recorded because it is the barrier that stops a
    // bare `\r` answering the live CLI's own permission prompt (invariant 25).
    receipt.checks.submit_key_was_echo_confirmed = !!(cap.write && cap.write.echo
      && cap.write.echo.total > 0 && cap.write.echo.matched > 0);
    receipt.checks.delivery_carried_nonexecuting_boundary = !!(cap.write
      && cap.write.authority_boundary
      && cap.write.authority_boundary.schema === "voice_turn_boundary@1.0"
      && cap.write.authority_boundary.non_executing_voice_turns === true
      && cap.write.authority_boundary.enforced_by_supervisor_process === true
      && cap.write.authority_boundary.broker_schema === "supervisor_voice_turn_authority@1.0");
    // The OWED record must NAME the live write and its evidence — not merely carry a string field
    // (validator MINOR-9: `typeof === "string"` passes for "").
    const owed = (cap.live_capture_owed || {});
    receipt.owed_record = owed;
    receipt.checks.owed_record_names_the_live_write =
      typeof owed.live_conductor_write === "string"
      && owed.live_conductor_write.includes("PHASE17C_CLOSE_SELFCHECK.json")
      && owed.live_conductor_write.includes("supervisor-owned")
      && owed.live_conductor_write.includes("non-executing");
    // …and must not have quietly declared the ROUTING paid: the confidence gate is uncalibrated on the
    // real engine (U140) and protected-action classification is a deterministic full-utterance lexicon
    // rather than semantic intent recognition (U144, narrowed). An OWED that
    // understates is the dangerous direction (spec-audit MAJOR-6).
    receipt.checks.owed_record_names_the_routing_limits =
      typeof owed.routing_limits === "string"
      && owed.routing_limits.includes("U140") && owed.routing_limits.includes("U144")
      && owed.routing_limits.includes("WHOLE utterance")
      && owed.routing_limits.includes("arbitrary semantic paraphrases")
      && owed.routing_limits.includes("supervisor-owned")
      && owed.routing_limits.includes("non-executing");

    // 8. WHAT THE CONDUCTOR WAS ACTUALLY ASKED. The expectation comes from the transcript, so a
    //    misheard operand yields a different-but-correct expectation instead of a false failure — and
    //    the divergence is recorded rather than smoothed over.
    const heard = parseHeardArithmetic(receipt.transcript);
    receipt.heard = heard;
    receipt.checks.transcript_carried_the_question = !!heard;
    if (!heard) throw new Error(`the transcript carried no readable arithmetic: ${JSON.stringify(receipt.transcript)}`);
    receipt.heard_expected = heard.expectedNumber;
    receipt.asr_matched_the_spoken_operands = heard.expectedNumber === probe.expectedNumber;
    const expected = Number(heard.expectedNumber);
    // falsifiability, both halves, against the ACTUAL expectation
    receipt.checks.answer_absent_from_transcript = !carriesNumber(receipt.transcript, expected);
    receipt.checks.answer_absent_before_delivery = !carriesNumber(before, expected);

    // 9. the ECHO — the WHOLE utterance reached the live session, not just the part carrying the
    //    arithmetic. `heard.matched` sits at the FRONT of the phrase, so anchoring on it would let a
    //    delivery truncated after it pass with a correct-looking answer (validator D-2). The delivery
    //    itself already happened inside the capture, so this measures from the capture's return.
    const submittedAt = Date.now();
    receipt.checks.whole_transcript_echoed_in_pane = await waitFor(async () => {
      const t = await paneText(win, paneId);
      return answerAfterAnchor(t, receipt.transcript, expected).anchored;
    }, ECHO_MS, 400);
    receipt.echo_seen = receipt.checks.whole_transcript_echoed_in_pane;

    // 10. THE ANSWER — the conductor's own reply, searched ONLY in what the pane painted AFTER the
    //     echoed utterance. The CLI's own chrome prints bare numbers ("⎿ Read 69 lines", "↑69 ↓12")
    //     that the unit-suffix exclusions do not cover, and the pre-delivery absence snapshot is tens
    //     of seconds stale by now (validator D-3). A reply is necessarily after its own prompt.
    //     `replied` is the fact this receipt needs: a standalone number appeared after the echoed
    //     utterance, and the utterance contains none — so an echo cannot produce it. Whether the
    //     arithmetic was RIGHT is recorded separately and does not gate. That is not a softened bar, it
    //     is the correct one: measured on this host, asked "What is 37 plus 47?", the live Fable-5
    //     conductor replied "● 67". It read the utterance and answered; its mental arithmetic was wrong.
    //     Grading the model is not what track 17C is for, and gating on it makes the criterion a coin flip.
    let observed = { anchored: false, replied: false, number: null, correct: false };
    const got = await waitFor(async () => {
      observed = answerAfterAnchor(await paneText(win, paneId), receipt.transcript, expected);
      return observed.replied;
    }, ANSWER_MS, 1000);
    receipt.answer_seen = got;
    receipt.answer_number = observed.number;
    receipt.answer_matched_the_arithmetic = observed.correct;
    // Measured from the capture's return (the delivery happened inside it), not from after the echo
    // wait — which understated the submit→answer interval by however long the echo took (MINOR-10).
    receipt.answer_latency_ms = got ? Date.now() - submittedAt : null;
    receipt.checks.live_conductor_answered = got;
    // The single prompt explicitly asked for a harmless tool calculation. The supervisor-owned
    // service must arm before processing. Vendor lifecycle is OBSERVATION ONLY: even StopFailure
    // cannot disarm a restriction (the gate-validator reproduced that bypass).
    await waitFor(() => {
      const events = boundaryAudit(voiceAuthorityAudit).map((row) => row.event);
      return events.includes("voice_turn_armed") && events.includes("vendor_lifecycle_observed");
    }, 15000, 250);
    receipt.authority_audit = boundaryAudit(voiceAuthorityAudit);
    receipt.checks.voice_turn_armed_before_model =
      receipt.authority_audit.map((row) => row.event).includes("voice_turn_armed");
    // WHETHER THE MODEL ITSELF REACHED FOR A TOOL — recorded, never gating. The prompt asks for a
    // tool calculation, but a model that answers `65` from its own head has not disobeyed anything,
    // and 2026-07-30 produced both outcomes on the same prompt. See below for what IS measured.
    receipt.vendor_tool_attempt_observed = receipt.authority_audit.some(
      (row) => row.event === "tool_denied" && row.session_id
        && row.session_id !== SUPERVISOR_PROBE_SESSION);
    // …so the denial itself is MEASURED instead of hoped for (U164): the exact pinned hook command,
    // run by this host's real hook dispatcher, carrying a real PreToolUse payload, against the same
    // authenticated loopback service, WHILE the operator's live voice turn is still armed.
    const liveTurn = receipt.authority_audit.findLast((row) => row.event === "voice_turn_armed");
    const ticketBoundary = conductorLaunchState().ticketAuthorityBoundary || null;
    receipt.pinned_hook_command = ticketBoundary && ticketBoundary.hook_command;
    const pinnedInput = {
      hook_event_name: "PreToolUse", tool_name: "Bash",
      tool_input: { command: "echo the supervisor must refuse this" },
      session_id: SUPERVISOR_PROBE_SESSION,
    };
    // The capability the supervised child holds. If the service is not listening there is nothing to
    // dispatch AT, and that is a failed leg rather than a thrown check.
    let probeEnv = null;
    try { probeEnv = voiceAuthorityChildEnv(childEnv({}, process.env).env); }
    catch (e) { receipt.tool_denial_probe_env_error = String((e && e.message) || e); }
    const denial = receipt.pinned_hook_command && probeEnv
      ? await dispatchHookEvent({ command: receipt.pinned_hook_command, input: pinnedInput, env: probeEnv })
      : { decision: null, reason: "no pinned hook command or no listening authority" };
    receipt.tool_denial_probe = { shell: denial.shell || null, exit_code: denial.exit_code,
      decision: denial.decision, reason: denial.reason, error: denial.error || null,
      stderr: (denial.stderr || "").trim().slice(0, 300) || null };
    const deniedRow = boundaryAudit(voiceAuthorityAudit).findLast(
      (row) => row.event === "tool_denied" && row.session_id === SUPERVISOR_PROBE_SESSION);
    // NAMED FOR WHAT IT MEASURES (U164/R1): this is the SUPERVISOR's decision on a real PreToolUse
    // payload carried by the exact pinned hook command, while a real voice turn is armed. It does not
    // observe a vendor tool call being stopped before it ran — `vendor_tool_attempt_observed` records
    // separately whether the model reached for a tool at all, and whether the CLI HONOURS the deny it
    // is handed rests on the vendor's hook contract plus the OS containment still owed as U25. The old
    // name, `voice_tool_call_denied_before_execution`, promised all three.
    receipt.checks.supervisor_denied_a_tool_call_through_the_pinned_hook_while_armed = denial.decision === "deny"
      && /voice turns are non-executing/i.test(String(denial.reason || ""))
      && !!deniedRow && !!liveTurn && deniedRow.turn_id === liveTurn.turn_id;
    // FALSIFIABILITY, and the thing that makes the leg above mean what it says: the SAME dispatch
    // with a corrupted capability token must still deny — but with the fail-closed transport reason,
    // not the supervisor's. A run where the service was unreachable would produce that second reason
    // for BOTH, so the two together separate "the supervisor decided" from "nothing answered".
    const forged = receipt.pinned_hook_command && probeEnv
      ? await dispatchHookEvent({ command: receipt.pinned_hook_command, input: pinnedInput,
        env: { ...probeEnv, SOW_VOICE_AUTH_TOKEN: "0".repeat(64) } })
      : { decision: null, reason: null };
    receipt.tool_denial_unauthenticated = { decision: forged.decision, reason: forged.reason };
    receipt.checks.tool_denial_came_from_the_supervisor_not_the_fallback =
      forged.decision === "deny" && /authority unavailable/i.test(String(forged.reason || ""))
      && !/voice turns are non-executing/i.test(String(forged.reason || ""));
    const authorityState = voiceAuthorityState();
    // re-read: the dispatches above append their own rows, and the lifecycle claim is about THIS run
    receipt.authority_audit = boundaryAudit(voiceAuthorityAudit);
    receipt.checks.voice_restriction_survived_vendor_lifecycle =
      receipt.authority_audit.map((row) => row.event).includes("vendor_lifecycle_observed")
      && !!(authorityState && authorityState.active);
    const after = await paneText(win, paneId);
    // The pane is running the VENDOR CLI, not a shell that happens to share the cwd: `waitForTuiQuiescence`
    // only requires the workspace path, which a shell would also print (validator D-7).
    receipt.checks.pane_ran_the_vendor_cli = typeof after === "string"
      && /claude\s*code/i.test(after.replace(/\s+/g, " "));
    // Generous, because this is the only durable record of what the live pane actually showed. The
    // first falsification run (the pre-`.close` single-chunk write) left a 300-character tail that was
    // pure CLI chrome — enough to prove the answer was absent, not enough to say what happened
    // instead. A receipt that cannot answer "then what DID it do?" wastes the live session it spent.
    receipt.answer_excerpt = typeof after === "string" ? (after.replace(/\s+/g, " ").trim().slice(-1500) || null) : null;
    // 11. INVARIANT 25, AGAINST THE LIVE PANE. `.mic` proved a protected spoken verb queues instead of
    //     delivering — but into a `powershell.exe` stand-in. That leg's MEANING changed when the
    //     destination became a session that can act, so re-measuring it here is not redundant
    //     (spec-audit MAJOR-7); it costs zero live tokens, because nothing is delivered. The stand-in
    //     `audio:` ref is used deliberately: the routing authority must be identical whatever produced
    //     the transcript, and a protected verb must not need a microphone to be proven.
    const paneBeforeProtected = await paneText(win, paneId);
    const prot = await evalR(win, 'window.__sovereignSelfCheck.captureVoice("audio:terminate-node-b")');
    receipt.protected_capture = prot && { queued: prot.queued, delivered: prot.delivered,
                                          delivered_to_conductor: prot.delivered_to_conductor,
                                          kind: prot.outcome && prot.outcome.kind,
                                          write: prot.write };
    receipt.checks.protected_verb_queued_not_delivered = !!(prot && prot.queued === true
      && prot.delivered === false && prot.delivered_to_conductor === false
      && prot.outcome && prot.outcome.kind === "proposed_action");
    // …and the live pane received NOTHING: no body, no submit key. Measured against the pane's own
    // text, not against the flag the code sets about itself. The transcript-still-present clause is
    // there so a leg that reads an empty/missing pane cannot pass by finding nothing.
    const paneAfterProtected = await paneText(win, paneId);
    const spokenVerbLanded = /terminate/i.test(String(paneAfterProtected || ""));
    const readingTheRightPane = typeof paneBeforeProtected === "string"
      && typeof paneAfterProtected === "string"
      && answerAfterAnchor(paneAfterProtected, receipt.transcript, expected).anchored;
    receipt.checks.protected_verb_reached_no_live_pane = readingTheRightPane && !spokenVerbLanded;
    if (!got) throw new Error(`the live conductor never replied to the utterance within ${ANSWER_MS / 1000}s `
      + `(expected ${expected}; nothing standalone appeared after the echoed prompt)`);
    log(`[selfcheck:voice-conductor] LIVE spoken round trip: heard "${heard.matched}" → replied `
      + `${receipt.answer_number} (expected ${expected}, correct=${observed.correct}) in ${receipt.answer_latency_ms}ms`);

    // 12. THE TURN ENDS — AND THE OPERATOR GETS THEIR KEYBOARD BACK (Phase 17C `.disarm`, U166).
    //
    //     This is the leg whose ABSENCE hid the defect. Every earlier run's single voice turn was the
    //     last act before teardown, so nothing followed it that the restriction could block — and the
    //     restriction had no end at all: `_active` cleared only on the observed OS-process exit. After
    //     the first utterance of a session the operator's own typed prompts were blocked and every
    //     tool call denied for the rest of it, which is the opposite of directive §13 item 2.
    //
    // 11b. U177 — THE DYNAMIC CROSS-CHANNEL RELEASE, asserted at RUNTIME because no source reading can
    //      see it. `voice-disarm-wiring.test.js` closed every static form: no `ipcMain.handle` body,
    //      and nothing reachable by name from one, calls a release or names the authority service. What
    //      it cannot see — and says so — is a callee reached through a getter or a Proxy trap, or a
    //      reference stored on one channel and invoked from another. So: with the operator's voice turn
    //      ADMITTED, drive EVERY intent the renderer can send to main, then ask the supervisor whether
    //      it still holds that turn. The sweep is fail-closed on coverage (an intent it does not name,
    //      or a channel it could not drive, fails it), and its arguments are governed no-ops — the
    //      destructive pane intents are aimed at a scratch pane it creates and closes, never at pane 1.
    const auditBeforeSweep = boundaryAudit(voiceAuthorityAudit);
    const stateBeforeSweep = voiceAuthorityState();
    // The leg is named "…while a turn was ADMITTED", so admission is asserted here rather than left
    // to the reader to reconstruct from audit timestamps (validator MINOR-6).
    receipt.turn_state_before_channel_sweep = (stateBeforeSweep && stateBeforeSweep.turn) || null;
    const admittedBeforeSweep = Boolean(liveTurn && stateBeforeSweep && stateBeforeSweep.active
      && stateBeforeSweep.active.turn_id === liveTurn.turn_id
      && stateBeforeSweep.turn && stateBeforeSweep.turn.phase === "active");
    const paneBeforeSweep = (await paneText(win, paneId)) || "";
    const sweep = await evalR(win,
      `window.__sovereignSelfCheck && window.__sovereignSelfCheck.driveEveryRendererChannel(`
        + `{conductorPaneId: ${JSON.stringify(paneId)}})`);
    receipt.channel_sweep = sweep;
    // Only rows that were actually INVOKED count as driven — a row is a claim about an attempt, and
    // publishing an un-invoked channel in `driven` would misreport coverage even where the leg's own
    // conjunction saves it (validator MINOR-8).
    const drivenChannels = new Set(((sweep && sweep.channels) || [])
      .filter((row) => row && row.invoked === true).map((row) => row.channel));
    const mainSrc = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");
    const registered = registeredIpcChannels(mainSrc);
    const counts = ipcRegistrationCounts(mainSrc);
    // The renderer sweep is closed against the BRIDGE; this closes it against MAIN, at runtime, from
    // the shipped source. A channel main registers that the sweep never drove is precisely where a
    // dynamic release would sit, and a receipt that did not notice would still be green. The counters
    // are the refusal: this parser reads one registration shape, so a source containing any OTHER
    // shape — any registration this parser cannot name — makes the coverage claim
    // unavailable rather than optimistic (validator RESERVATION-4). A channel name held in a constant
    // or a one-way `ipcMain.on` therefore fails this leg instead of quietly escaping the sweep.
    receipt.channel_sweep_coverage = {
      registered_in_main: registered,
      registration_counts: counts,
      driven: [...drivenChannels].sort(),
      undriven: registered.filter((c) => !drivenChannels.has(c)),
    };
    receipt.checks.every_renderer_channel_was_driven_while_a_turn_was_admitted = Boolean(
      sweep && sweep.ok === true && registered.length > 15 && admittedBeforeSweep
      && counts.parsed === counts.handle_total && counts.one_way_total === 0
      && receipt.channel_sweep_coverage.undriven.length === 0
      && ((sweep.channels || []).length === drivenChannels.size));
    // …and the supervisor still holds the SAME admitted turn, read from its own state rather than
    // inferred from the absence of an audit row (a release that writes no row at all is the class
    // U176 was). `liveTurn` is the `voice_turn_armed` row for the operator's spoken turn.
    const auditAfterSweep = boundaryAudit(voiceAuthorityAudit);
    const stateAfterSweep = voiceAuthorityState();
    const survival = turnSurvivedChannelSweep({
      turnId: liveTurn && liveTurn.turn_id,
      before: auditBeforeSweep,
      after: auditAfterSweep,
      stateAfter: stateAfterSweep,
      // the bounded ring's own drop counter, both sides: an audit that dropped rows across the sweep
      // is a window that cannot be trusted to hold every release written during it
      droppedBefore: stateBeforeSweep && stateBeforeSweep.audit_dropped,
      droppedAfter: stateAfterSweep && stateAfterSweep.audit_dropped,
      sweep,
    });
    receipt.turn_survived_channel_sweep = survival;
    receipt.checks.no_renderer_channel_released_the_admitted_voice_turn = survival.survived === true;
    // …and the sweep left nothing of its own sitting in the live CLI's input box. The first version
    // typed its probe STRING here and the next typed prompt was submitted with it attached — a prompt
    // the operator never composed (validator RESERVATION-3 / spec-audit F1). The conductor payload is
    // control bytes now, and this is the leg that keeps it that way.
    const paneAfterSweep = (await paneText(win, paneId)) || "";
    receipt.channel_sweep_left_probe_text_in_the_pane = paneAfterSweep.includes(SWEEP_PROBE);
    receipt.checks.channel_sweep_wrote_no_prompt_text_into_the_live_conductor =
      paneBeforeSweep.length > 0 && !paneAfterSweep.includes(SWEEP_PROBE);
    // …and the restriction is not merely RECORDED as held, it is still ENFORCED: the same pinned hook
    // command, the same real dispatcher, a real PreToolUse — after every channel has been driven.
    const toolAfterSweep = receipt.pinned_hook_command && probeEnv
      ? await dispatchHookEvent({ command: receipt.pinned_hook_command, env: probeEnv,
          input: { hook_event_name: "PreToolUse", session_id: SUPERVISOR_PROBE_SESSION,
                   tool_name: "SovereignChannelSweepProbe" } })
      : { decision: null, reason: "no pinned hook command or no listening authority" };
    receipt.tool_denial_after_channel_sweep = { decision: toolAfterSweep.decision,
      reason: (toolAfterSweep.reason || "").slice(0, 200) || null };
    const sweepDeniedRow = boundaryAudit(voiceAuthorityAudit).findLast(
      (row) => row.event === "tool_denied" && row.session_id === SUPERVISOR_PROBE_SESSION);
    receipt.checks.the_restriction_was_still_enforced_after_the_channel_sweep =
      toolAfterSweep.decision === "deny"
      && /voice turns are non-executing/i.test(String(toolAfterSweep.reason || ""))
      && !!sweepDeniedRow && !!liveTurn && sweepDeniedRow.turn_id === liveTurn.turn_id;
    // D-LOOP-1, in miniature: the sweep spawns one scratch pane to aim the destructive intents at and
    // closes it itself. Nothing it created may outlive it.
    const scratchId = (sweep && sweep.scratch_pane_id) || null;
    receipt.channel_sweep_scratch_pane = scratchId;
    receipt.checks.channel_sweep_left_no_session_behind = Boolean(scratchId) && await waitFor(() => {
      const mgr2 = sessionManager();
      if (!mgr2) return false;
      const alive = mgr2.registry.alive().map((s) => s.id);
      return !alive.includes(scratchId) && alive.includes(paneId);
    }, KILL_MS, 250);
    // the live pane was re-tiled and written to; let it settle before anything else is measured
    await waitForTuiQuiescence(win, paneId, TUI_READY_MS);

    //     Measured in four steps, and the first two cost no tokens because they are the SAME dispatch
    //     either side of the disarm — which is what makes the pair mean something: an unmarked
    //     `UserPromptSubmit` (what the operator's own typing produces) is BLOCKED while the turn is
    //     armed and ADMITTED once it is not. If the disarm did nothing, leg 2 stays blocked; if the
    //     restriction were never real, leg 1 is already admitted. Measured AFTER the sweep above, so
    //     it doubles as the enforcement half of that assertion.
    const typedPrompt = {
      hook_event_name: "UserPromptSubmit",
      session_id: SUPERVISOR_PROBE_SESSION,
      prompt: "the operator is typing into pane 1",
    };
    const dispatchTyped = async () => (receipt.pinned_hook_command && probeEnv
      ? dispatchHookEvent({ command: receipt.pinned_hook_command, input: typedPrompt, env: probeEnv })
      : { decision: null, exit_code: null, stdout: "", reason: "no pinned hook command or no listening authority" });
    const armedTyped = await dispatchTyped();
    receipt.typed_prompt_while_armed = { decision: armedTyped.decision, exit_code: armedTyped.exit_code,
      reason: (armedTyped.reason || "").slice(0, 200) || null };
    receipt.checks.typed_prompt_is_blocked_while_the_voice_turn_is_armed = armedTyped.decision === "block";

    //     …and the operator can SEE the restriction that is doing it (invariant 27). Read off the
    //     PAINTED chrome, not the model behind it: a state that exists only in a receipt is not visible.
    receipt.turn_badge_while_armed = await turnBadge(win, paneId);
    receipt.checks.armed_turn_is_visible_in_the_operator_chrome = !!(receipt.turn_badge_while_armed
      && receipt.turn_badge_while_armed.hidden === false
      && /voice turn/i.test(receipt.turn_badge_while_armed.text || "")
      && /tool/i.test(receipt.turn_badge_while_armed.text || "")
      // …and the way out is discoverable, which the Ctrl+Shift+Escape chord alone was not: it appeared
      // in no chrome, no string and no operator document (spec-audit M2).
      && /typ(e|ing)/i.test(receipt.turn_badge_while_armed.title || "")
      && /Ctrl\+Shift\+Escape/.test(receipt.turn_badge_while_armed.title || "")
      // …and the tooltip must not scope the bound narrower than the code does (spec-audit M-4):
      // ANY key in this window ends the turn, which is the residual U170 records.
      && /anywhere in this window/i.test(receipt.turn_badge_while_armed.title || ""));

    //     THE DISARM ITSELF, through the production `before-input-event` handler with an ordinary key —
    //     the signal Electron main measures for itself. A vendor lifecycle event cannot produce it (the
    //     child is not in the window's input path), and a deadline was rejected as the alternative:
    //     handing authority back for the passage of time is something a child need only WAIT OUT.
    const disarm = exerciseOperatorTypedKeyDisarm();
    receipt.operator_typed_disarm = disarm;
    receipt.checks.operator_keystroke_disarmed_the_voice_turn = !!(disarm && disarm.disarmed
      && disarm.disarmed.event === "voice_turn_disarmed"
      && disarm.disarmed.source === "electron_main_before_input_event"
      && disarm.disarmed.phase === "active"
      && disarm.turn && disarm.turn.restricted === false
      // an ordinary keystroke is NOT consumed by main — it still reaches the pane being typed into
      && disarm.handled === false && disarm.consumed === false);
    //     …and the audit records the KIND of key, never the key: an append-only trail of the operator's
    //     keystrokes that reaches committed receipts is a keylogger.
    receipt.checks.disarm_audit_records_no_keystroke_content = !!(disarm && disarm.disarmed
      && disarm.disarmed.key_kind === "printable"
      && !Object.prototype.hasOwnProperty.call(disarm.disarmed, "key"));
    //     …and what the chrome says NOW. `.disarm` asserted the badge went away entirely, which was
    //     right for the state the code then had and wrong for the state it has: the operator's
    //     keystroke ends the turn for THEM while the answer it is still generating keeps its tool
    //     denial until their next prompt (U178). A blank badge there would report a live denial as
    //     over — the understating direction, and nobody re-checks a restriction they were told ended.
    receipt.turn_badge_after_disarm = await turnBadge(win, paneId);
    receipt.checks.chrome_shows_the_turn_ended_with_its_answer_still_denied =
      !!(receipt.turn_badge_after_disarm
        && receipt.turn_badge_after_disarm.hidden === false
        && /ended/i.test(receipt.turn_badge_after_disarm.text || "")
        && /tool/i.test(receipt.turn_badge_after_disarm.text || "")
        && /next prompt/i.test(receipt.turn_badge_after_disarm.title || ""));

    //     THE U178 PROPERTY ITSELF, and it costs no live exchange: a PreToolUse dispatched through
    //     the pinned hook command in the window between the operator's keystroke and their next
    //     prompt. Before this fix the deny path simply stopped running — the spoken turn's own answer
    //     could execute tools the moment the operator touched the keyboard (I-V3 / invariant 25).
    const toolAfterDisarm = receipt.pinned_hook_command && probeEnv
      ? await dispatchHookEvent({ command: receipt.pinned_hook_command, env: probeEnv,
          input: { hook_event_name: "PreToolUse", session_id: SUPERVISOR_PROBE_SESSION,
                   tool_name: "SovereignEndedTurnProbe" } })
      : { decision: null, exit_code: null, reason: "no pinned hook command or no listening authority" };
    receipt.tool_call_after_disarm = { decision: toolAfterDisarm.decision,
      exit_code: toolAfterDisarm.exit_code,
      reason: (toolAfterDisarm.reason || "").slice(0, 200) || null };
    receipt.checks.ended_voice_turn_still_denies_its_own_answers_tools =
      toolAfterDisarm.decision === "deny";

    const releasedTyped = await dispatchTyped();
    receipt.typed_prompt_after_disarm = { decision: releasedTyped.decision, exit_code: releasedTyped.exit_code,
      stdout: (releasedTyped.stdout || "").trim().slice(0, 200) || null };
    // "admitted" is the ABSENCE of a decision on a clean exit — and it cannot be produced by a failed
    // dispatch, because every fail-closed path returns a `block` for this event.
    receipt.checks.typed_prompt_is_admitted_once_the_operator_disarms =
      releasedTyped.exit_code === 0 && releasedTyped.decision === null
      && (releasedTyped.stdout || "").trim() === "";

    //     THE LIVE HALF: a second prompt, physically typed into the SAME session through the renderer's
    //     real onData→pane:input→SessionManager.write path, answered by the same live conductor. One
    //     more live exchange than a `.close` run, and the exit criterion this sub-step exists for
    //     (§13 item 2: typed AND spoken input reach the same live conductor session).
    let typedProbe = null;
    const paneBeforeTyped = (await paneText(win, paneId)) || "";
    for (let roll = 0; roll < 5; roll++) {
      typedProbe = buildTypedProbe();
      receipt.typed_probe_rerolls = roll;
      if (!carriesNumber(paneBeforeTyped, Number(typedProbe.expectedNumber))
        && spokenProbeIsFalsifiable(typedProbe)) break;
      typedProbe = null;
    }
    if (!typedProbe) throw new Error("could not draw a typed probe whose answer is absent from the pane");
    receipt.typed_second_prompt = typedProbe.phrase;
    receipt.typed_second_expected = typedProbe.expectedNumber;
    receipt.checks.second_typed_prompt_is_falsifiable =
      !carriesNumber(paneBeforeTyped, Number(typedProbe.expectedNumber))
      && spokenProbeIsFalsifiable(typedProbe);
    const typedExpected = Number(typedProbe.expectedNumber);
    const typedWrite = await typeAndSubmit(win, paneId, typedProbe.phrase,
      (text) => answerAfterAnchor(text, typedProbe.phrase, typedExpected).anchored, ECHO_MS);
    receipt.typed_second_write = typedWrite;
    receipt.checks.second_typed_prompt_reached_the_live_session =
      typedWrite.written && typedWrite.echoed && typedWrite.submitted;
    let typedObserved = { anchored: false, replied: false, number: null, correct: false };
    const typedGot = await waitFor(async () => {
      typedObserved = answerAfterAnchor(await paneText(win, paneId), typedProbe.phrase, typedExpected);
      return typedObserved.replied;
    }, ANSWER_MS, 1000);
    receipt.typed_second_answer_number = typedObserved.number;
    receipt.typed_second_answer_matched_the_arithmetic = typedObserved.correct;
    // What the pane ACTUALLY showed, for the same reason the spoken leg keeps one: the first `.disarm`
    // run recorded a typed answer of `10` where `70` was expected and left nothing to read, so the
    // receipt could not say whether the model was wrong or the chrome was being counted. A receipt
    // that cannot answer "then what DID it do?" wastes the live exchange it spent.
    const paneAfterTyped = await paneText(win, paneId);
    receipt.typed_second_answer_excerpt = typeof paneAfterTyped === "string"
      ? (paneAfterTyped.replace(/\s+/g, " ").trim().slice(-1200) || null) : null;
    // Same bar as the spoken leg, for the same reason: the GATING fact is that the conductor replied
    // with a standalone number of its own after the whole prompt echoed (the prompt contains none);
    // whether its arithmetic was right is recorded and does not gate.
    receipt.checks.second_typed_prompt_answered_in_the_same_live_session = typedGot;
    if (!typedGot) {
      throw new Error(`the live conductor never answered the SECOND, TYPED prompt within ${ANSWER_MS / 1000}s `
        + "— an admitted voice turn that never disarms is exactly the defect this leg exists to catch (U166)");
    }
    log(`[selfcheck:voice-conductor] LIVE typed round trip after the disarm: replied `
      + `${receipt.typed_second_answer_number} (expected ${typedExpected}, `
      + `correct=${typedObserved.correct})`);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
    if (log) log(`[selfcheck:voice-conductor] ${receipt.error}`);
  } finally {
    // D-LOOP-1 — neither the live session nor its durable terminal outlives this check.
    try {
      if (paneId && sessionManager() && sessionManager().registry.has(paneId)) {
        // Phase 17C `.disarm`: the OTHER release path — a turn that is still live when the supervised
        // process dies — needs something live to release. After the operator's keystroke ended the
        // real one (which is the point of this sub-step), there is nothing left, so the check arms a
        // supervisor-side turn of its own. NOTHING IS WRITTEN to the session and no live exchange is
        // spent: `arm()` only creates the pending payload. Disclosed as a substitution in
        // `receipt.substitutions`, and the leg below still demands the EXACT pane/session/pid/
        // generation from the observed node-pty exit — a persuasive reason cannot satisfy it.
        try {
          receipt.exit_release_turn = armVoiceTurnForExitCheck
            ? (armVoiceTurnForExitCheck() || {}).turn_id || null
            : null;
        } catch (e) { receipt.exit_release_turn_error = String((e && e.message) || e); }
        killSession(paneId);
        receipt.session_killed = await waitFor(() => {
          if (!receipt.session_pid) return true;
          try { process.kill(receipt.session_pid, 0); return false; } catch { return true; }
        }, KILL_MS, 250);
      }
      receipt.lease_released = await waitFor(async () => {
        // A ref this check never learned, or an entry the ledger does not carry, is NOT a released
        // terminal — it is an unreadable count (validator D-5). Fail closed on both.
        const ref = conductorLaunchState().subscriptionRef || receipt.subscription_ref;
        if (!ref) { receipt.in_use_after_release = null; return false; }
        const afterStatus = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
        if (!afterStatus.ok || !afterStatus.status) { receipt.in_use_after_release = null; return false; }
        // An ABSENT entry after a readable status is a legitimate zero — the ledger drops a subscription
        // once its last lease is handed back. What is not legitimate, and was the hole D-5 named, is a
        // ref this check never learned or a status it could not read: those are `null`, not zero.
        const e2 = (afterStatus.status.subscriptions || {})[ref] || null;
        receipt.in_use_after_release = e2 ? e2.in_use : 0;
        return receipt.in_use_after_release === 0;
      }, RELEASE_MS, 1000);
    } catch (e) {
      receipt.error = receipt.error || `teardown failed: ${String((e && e.message) || e)}`;
    }
    receipt.checks.live_session_torn_down = receipt.session_killed;
    receipt.checks.durable_terminal_handed_back = receipt.lease_released && receipt.in_use_after_release === 0;
    if (priorLedger === undefined) delete process.env.SOW_TERMINAL_LEASE_LEDGER;
    else process.env.SOW_TERMINAL_LEASE_LEDGER = priorLedger;
    receipt.authority_audit = boundaryAudit(voiceAuthorityAudit);
    // A turn that is STILL LIVE when the supervised process dies is released by the observed
    // node-pty exit, with the exact pane/session/pid/generation — a persuasive reason cannot satisfy
    // this. (Renamed at `.disarm`: it used to say "only after … process exit", which was the U166
    // defect stated as a virtue. The process exit is one of the two release paths, not the only one.)
    // Named for the turn it actually released (validator R-4): substitution 6 arms a PENDING turn
    // moments before the kill, because the operator's keystroke ended the admitted one — which is
    // this sub-step's whole point. The mechanism under test is identical for either phase, and the
    // audit row now records which it was, so the receipt can be read without taking the name's word.
    const exitReset = receipt.authority_audit.findLast((row) => row.event === "voice_turn_reset");
    receipt.exit_release_turn_phase = (exitReset && exitReset.phase) || null;
    receipt.checks.the_turn_live_at_process_exit_is_released_by_that_exact_process_exit =
      exactProcessExitResetObserved(receipt.authority_audit, {
        paneId: receipt.pane_id,
        sessionId: receipt.session_id,
        pid: receipt.session_pid,
        generation: receipt.session_generation,
      });
    // …and NOTHING ELSE ever released one: every row that cleared the restriction in this run carries
    // a provenance Electron main measured for itself, and the vendor's own lifecycle events are
    // present in the audit as observations that cleared nothing (the forged-SessionEnd bypass, fixed
    // at iteration 88, stays closed).
    const releases = receipt.authority_audit.filter(
      (row) => row.event === "voice_turn_disarmed" || row.event === "voice_turn_reset");
    receipt.turn_releases = releases.map((row) => ({ event: row.event, source: row.source || null }));
    receipt.checks.every_release_carried_a_main_owned_provenance = releases.length > 0
      && releases.every((row) => MAIN_OWNED_RELEASE_SOURCES.includes(row.source))
      && receipt.authority_audit.some((row) => row.event === "vendor_lifecycle_observed");
    try { fs.rmSync(SCRATCH_LEDGER, { force: true }); } catch { /* nothing to remove */ }
    // transcribe-then-discard applies to the fixture too — no speech is left on disk.
    try { fs.unlinkSync(FIXTURE_WAV); } catch { /* already gone */ }
  }

  const c = receipt.checks;
  receipt.failed_checks = Object.entries(c).filter(([, v]) => !v).map(([k]) => k);
  receipt.ok = receipt.error === null && Object.keys(c).length > 0 && receipt.failed_checks.length === 0;
  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node, chrome: process.versions.chrome,
    platform: process.platform, arch: process.arch,
  };
  // EVERY substitution, enumerated (directive §6; spec-audit M1 — the previous run called the
  // microphone "the only one" while three more were disclosed in prose further down and not labelled).
  receipt.substitutions = [
    {
      of: "the physical microphone",
      why: "operator hardware cannot be driven by an automated check — directive §16 track 17C puts "
        + "the spoken-mic half in the operator's first use, and the loop never blocks on the operator",
      what_ran_instead: "the fixture WAV's samples are injected at exactly the point MicRecorder.stop() "
        + "hands its encoded bytes to S.captureVoice; everything below that is the unmodified production "
        + "path — IPC payload, CaptureStore validation + write, real-engine selection, WSL Parakeet "
        + "transcription, bridge routing, the delivery into pane 1's LIVE ConPTY, the guaranteed discard. "
        + "The fixture is OS-synthesized TEST INPUT (the 16E carve-out); the product has no TTS "
        + "(I-V2/D-VOICE-02)",
    },
    {
      of: "OS key delivery for the typed path and for the operator's disarming keystroke",
      why: "an automated check cannot press a physical key",
      what_ran_instead: "typed text reaches the session through the renderer's real "
        + "term.input → pane:input → SessionManager.write path (the production path), and the disarm "
        + "drives main's production before-input-event handler with a synthesized keyDown — the same "
        + "handler an operator keystroke enters, with the same decision behind it",
    },
    {
      of: "the operator-recovery chord gesture",
      why: "same — a synthesized input event, not an observed keystroke",
      what_ran_instead: "handleOperatorResumeInput is called with the exact Ctrl+Shift+Escape event shape",
    },
    {
      of: "a vendor-originated tool call",
      why: "whether the live model reaches for a tool during one answer is its own choice — on "
        + "2026-07-30 the same prompt produced both outcomes, so gating on it makes the criterion a "
        + "coin flip (`vendor_tool_attempt_observed` records what it did)",
      what_ran_instead: "a real PreToolUse payload with this check's own session id, dispatched through "
        + "the EXACT pinned hook command by this host's real hook dispatcher, against the same "
        + "authenticated loopback service, while the operator's live voice turn was armed",
    },
    {
      of: "the operator's own typed prompt, for the blocked/admitted PAIR either side of the disarm",
      why: "the pair has to be the SAME dispatch before and after, and it must cost no tokens — a "
        + "live prompt that is blocked by the supervisor never reaches the model, so there is nothing "
        + "to observe in the pane and nothing to compare it with",
      what_ran_instead: "an unmarked UserPromptSubmit carrying this check's own session id "
        + "(sovereign-selfcheck-hook-probe), dispatched through the EXACT pinned hook command by this "
        + "host's real dispatcher against the same authenticated loopback service — the same shape as "
        + "the tool-denial substitution above. It measures the SUPERVISOR's decision on a typed "
        + "prompt, not the live session's own prompt. The LIVE half of that claim is the second typed "
        + "prompt below, which the operator's real path submitted and the model answered",
    },
    {
      of: "the operator clicking every control in the shell while a voice turn is admitted (U177)",
      why: "the property is about the CHANNELS, not the widgets: a dynamic release — a callee reached "
        + "through a getter or a Proxy trap, or a reference stored on one channel and invoked from "
        + "another — is reached by the intent, and several intents (a second conductor launch, an "
        + "approval decision) have no control an operator could click in this state",
      what_ran_instead: "every intent the preload bridge exposes is invoked from the renderer through "
        + "that same bridge, while the operator's spoken turn is ADMITTED — closed against BOTH sides "
        + "(a bridge method the sweep does not name, or a channel main registers that it never drove, "
        + "fails the leg; a registration shape the parser cannot read fails it too). The arguments are "
        + "governed and NON-DESTRUCTIVE, which is not the same as no-ops and was overstated as such in "
        + "the previous run: the protected verb queues a real proposal, the approval decision routes to "
        + "the governed Python resolve, the succession request writes a log line. Each is a governed "
        + "write the shell attributes to the operator — acceptable only because this path exists solely "
        + "under SHELL_SELFCHECK, whose recovery store is isolated (main.js RECOVERY_DIR), so it never "
        + "touches an operator session's queue or layout. The destructive pane intents are aimed at a "
        + "scratch pane the sweep creates and closes; only non-destructive ones touch pane 1, and "
        + "`pane:input` deliberately does — with CONTROL BYTES ONLY, because the previous run's probe "
        + "STRING survived its own clear and was submitted as part of the operator's next prompt",
    },
    {
      of: "a live voice turn at process-exit time",
      why: "the operator's keystroke ended the real one — which is the whole point of this sub-step — so "
        + "the other release path had nothing left to release",
      what_ran_instead: "the check arms a supervisor-side turn immediately before the kill. NOTHING is "
        + "written to the session and no live exchange is spent; the leg still demands the exact "
        + "pane/session/pid/generation from the observed node-pty exit",
    },
  ];
  receipt.substitution = receipt.substitutions.map((s) => `${s.of}: ${s.what_ran_instead}`).join(" · ");
  receipt.scope_note = "THREE legs pin CONTRACT FIELDS rather than the facts they are named for, and "
    + "should not be read as proving them: `no_tts` and `self_authorized_false` read values hardcoded in "
    + "voice/deliver.js and main.js (the substantive evidence for I-V2 is that no synthesis exists in any "
    + "product path, and for invariant 1 that decideDelivery only ever forwards the bridge's verdict), and "
    + "the owed-record legs read text, not behaviour. "
    + "ONE live session, ONE spoken exchange and — new at `.disarm` — ONE typed exchange, because the "
    + "criterion this sub-step exists for is that the operator's TYPED prompt is accepted and answered "
    + "in the SAME session after a voice turn (§13 item 2; U166). Two exchanges is the minimum that can "
    + "show it. WHAT THE DISARM DOES AND DOES NOT CLAIM: the voice restriction is bounded by the "
    + "OPERATOR — everything the CLI does between an admitted spoken prompt and the operator's next "
    + "keyboard action is non-executing, and taking the keyboard back ends that window. It is NOT "
    + "bounded by the vendor's own notion of its turn ending (unforgeable is the requirement, and the "
    + "child holds the transport bearer), nor by a deadline (a child need only wait one out). The "
    + "residual is stated rather than buried: a keystroke the operator aims elsewhere in the shell also "
    + "ends the window, so a tool call the model makes after that point is governed by the ordinary "
    + "typed path rather than by the voice restriction (U170). WHAT THE U177 SWEEP CLAIMS AND WHAT IT "
    + "DOES NOT: every IPC channel this shell registers — as this receipt's own parser can NAME them, "
    + "which it refuses to claim unless the count of registrations it named equals the total it can "
    + "see and no one-way `ipcMain.on` exists — was invoked from the renderer, through the real preload "
    + "bridge, while the operator's spoken turn was ADMITTED (asserted from the authority's state "
    + "before the sweep, not inferred), and the supervisor still held that exact turn afterwards and "
    + "still denied a real PreToolUse for it. Each channel was driven ONCE, with governed "
    + "non-destructive arguments — NOT no-ops: several of them record (a queued proposal, a routed "
    + "approval decision, a succession log line), which is acceptable only because this path exists "
    + "solely under SHELL_SELFCHECK with an isolated recovery store, never in an operator session. So "
    + "a dynamic release (a getter, a Proxy trap, a reference stored on one channel and invoked from "
    + "another) that fires only under argument values this sweep does not supply is not excluded by "
    + "it. The static guard covers that shape wherever a callee can be named, whatever its arguments; "
    + "what neither reaches is the intersection, recorded as U190 rather than implied away. WHAT THE "
    + "SWEEP DID TO THE LIVE SESSION, because the previous run of this receipt got it wrong and said "
    + "otherwise: its conductor-pane write is a kill-line control byte and nothing else. The version "
    + "before it typed a probe STRING and claimed a trailing ETX cleared it; the live CLI took the ETX "
    + "as an interrupt, kept the text, and the next typed prompt reached the model with that text "
    + "attached — a prompt the operator never composed. That receipt's `typed_second_prompt` did not "
    + "say so. This run asserts the probe text is absent from the pane after the sweep. The "
    + "`--model` slug is the one the host CLI was OBSERVED to accept (the governed probe resolved the "
    + "operator's selection LABEL to it; an unresolvable label launches on the CLI default with "
    + "`model_is_fallback` set — never a silent substitution). The expected answer is derived from the "
    + "TRANSCRIPT, i.e. from the question the conductor was actually asked, and "
    + "`asr_matched_the_spoken_operands` records whether the ASR heard the fixture exactly; the answer "
    + "is asserted absent from both the transcript and the pane before delivery, and is read only from "
    + "what the pane painted AFTER the whole utterance echoed and after the model's own `●` marker — so "
    + "neither an echo nor stale scrollback can satisfy it. WHAT THAT DOES NOT EXCLUDE, measured rather "
    + "than assumed: TOOL CHROME painted after that marker carries fresh standalone numbers, and this "
    + "unit's first receipt was green with a typed answer of 10 against an expected 70 for exactly that "
    + "reason. The typed probe no longer asks for a tool; the SPOKEN one still does (that request is what "
    + "a voice turn must deny), so on a run where the model reaches for a tool the same shape is live for "
    + "the spoken leg — `vendor_tool_attempt_observed` records whether it did. The GATING fact is that the conductor REPLIED with a "
    + "number of its own; `answer_matched_the_arithmetic` records whether that number was right and does "
    + "NOT gate: measured on this host, the live Fable-5 backend answered '37 plus 47' with 67, and "
    + "grading the model's mental arithmetic would make this criterion a coin flip on something track "
    + "17C is not about. WHAT THIS DOES NOT CLAIM: that a human speaking into a "
    + "microphone was transcribed (operator first use); that the ASR is confidence-calibrated (U140 — "
    + "recognition-derived confidence cannot distinguish a confidently WRONG transcription from a "
    + "correct one); that the deterministic full-utterance protected-verb lexicon can infer arbitrary "
    + "semantic paraphrases outside its explicit synonyms/inflections (U144, narrowed — polite prefixes "
    + "such as 'please delete' are now brokered); kernel containment beyond what 17A `.pty` "
    + "recorded (OS job objects remain owed — U25). The voice-turn permission profile IS now bound. "
    + "ITS DENIAL IS MEASURED, NOT INFERRED (U164): a real PreToolUse payload was dispatched through "
    + "the EXACT pinned hook command, by this host's real hook dispatcher, against the same "
    + "authenticated loopback service, while the operator's live voice turn was armed — and the same "
    + "dispatch with a corrupted capability token fell back to the transport's own deny, which is what "
    + "separates 'the supervisor decided' from 'nothing answered'. WHAT THAT DOES NOT SAY: that the "
    + "vendor CLI HONOURS the deny it is handed. This run's model answered from its own head without "
    + "reaching for a tool (`vendor_tool_attempt_observed` records that), so no vendor-side refusal was "
    + "observed here; the earlier U162 run, whose hook could not be parsed at all, showed the CLI "
    + "surfacing its own approval prompt rather than executing silently. Vendor honouring rests on the "
    + "vendor's hook contract plus the OS-level containment still owed as U25. Gating on whether a "
    + "live model happens to call a tool would make this criterion a coin flip on the model's mood — "
    + "on 2026-07-30 the same prompt produced both outcomes. "
    + "ALSO NOT CLAIMED, "
    + "and true here for the first time: the delivered utterance becomes durable text in the vendor "
    + "CLI's own session store, outside this workspace and outside `.voice-captures` — invariant 26 "
    + "governs the AUDIO, which is discarded, and this is the same exposure typing already has, but the "
    + "spoken half of it starts with this receipt (U146). The live session and its durable I-X3 terminal "
    + "are torn down here; the OPERATOR's own conductor session persists by design.";
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    if (log) log(`[selfcheck:voice-conductor] could not write receipt: ${e && e.message}`);
  }
  if (log) log(`[selfcheck:voice-conductor] ${receipt.ok ? "PASS" : `FAIL (${receipt.failed_checks.join(", ") || receipt.error})`} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = {
  runVoiceConductorSelfCheck: run,
  exactProcessExitResetObserved,
  sourceIdentity,
  committedTreeCheckName,
  RECEIPT_PATH,
  FIXTURE_WAV,
};
