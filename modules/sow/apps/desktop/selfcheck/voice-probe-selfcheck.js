"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * Phase 17C `.probe` in-Electron self-check (D-P16-0 binding, per-track) — U74 / OP-11 finding F1.
 *
 * WHAT THE OPERATOR SAW, AND WHY A HEADLESS TEST CANNOT CLOSE IT. The shipped shell badged the voice
 * engine **"mock engine"** on a host where WSL Parakeet is installed and verified (the real
 * transcription receipt PHASE16E_REAL_PARAKEET_SMOKE.json is from THIS host). The unit tests all
 * passed, because each half was individually right: the probe returned false, and the indicator
 * faithfully rendered false as "mock engine". The defect only exists in the composition — an 8 s budget
 * against a 7–18 s NeMo ASR import, one cold miss cached for the app's life, and an engine state that
 * was only ever learned as a side effect of a capture. So the fix has to be measured in the RUNNING
 * shell, against this host's real WSL.
 *
 * What this check measures (every boolean is observed; nothing is asserted from the source):
 *   1. supervision READY (governed spawn path; no naked session — invariant 2);
 *   2. **the probe does not block the chrome.** The shell starts it at first paint; `voice:state`
 *      answers WHILE it is in flight, in milliseconds, and the answer is `probing` — never the
 *      "mock engine" verdict, and never a stall. The elapsed time of that call is recorded;
 *   3. **the renderer paints the open question as open**: pane 1's `.cvoice` chrome reads "probing…"
 *      (not "mock engine") while the probe runs — the operator's actual eye-level evidence;
 *   4. **the probe answers, and the badge flips itself with no operator action**: the settled state and
 *      its measured elapsed time are recorded, and the renderer's chrome is re-read to prove main's
 *      push reached it. On a host with the real stack the label becomes "<engine> ready"; on a host
 *      without it, the honest "mock engine" — the check asserts AGREEMENT with the host, not a value;
 *   5. **nothing is pinned**: a forced re-probe actually re-probes (the probe counter advances), which
 *      is the direct falsification of the `lru_cache(maxsize=1)` half of U74;
 *   6. **the answer is fail-closed**: `real_available` equals the detection conjunction the probe
 *      reported, and a `probing` state never coexists with a claimed engine.
 *
 * Load-bearing: restore the 8 s budget or the lifetime cache and leg 4 reports `unavailable` on this
 * host (the badge goes back to "mock engine") ⇒ FAIL. Make `voice:state` await the probe and leg 2's
 * measured latency blows its ceiling ⇒ FAIL. NO live `claude`/`codex` call and no credential (§2.2/
 * §2.4): the probe runs `wsl.exe` locally. NO TTS (I-V2/D-VOICE-02) — nothing here speaks.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");
const { spawn } = require("child_process");
const { childEnv } = require("../voice/env-scrub");

const RECEIPT_PATH = receiptPath("PHASE17C_VOICE_PROBE_SELFCHECK.json");

// The chrome read must be fast enough that a blocking implementation cannot hide inside it. The probe's
// own budget is 90 s; a `voice:state` that awaited it would take seconds, not milliseconds.
const NONBLOCKING_CEILING_MS = 1500;
// The probe's ceiling from this check's point of view: the Python budget (90 s) + interpreter start +
// headroom. Past this the check FAILS with the step named rather than being killed blind.
const PROBE_SETTLE_CEILING_MS = 150000;

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

/**
 * An INDEPENDENT reference measurement of this host's real stack, taken through a route that does not
 * depend on the budget under test: the probe emitter with an explicit, generous `SOW_NEMO_PROBE_TIMEOUT_S`
 * env override.
 *
 * Why it exists: without it, every "the badge agrees with the host" leg here is self-referential — the
 * badge is drawn FROM the probe's answer, so a probe that wrongly says "unavailable" produces a
 * perfectly consistent "mock engine" badge and the check passes while the operator is being lied to.
 * That is exactly the shape U74 shipped in. This gives the check a second, independent opinion about
 * the same host, and it doubles as the end-to-end proof that the `SOW_*` overrides are honoured in the
 * running product path (directive §16 track 17C).
 *
 * Fail-closed: any fault returns `{ok:false, reason}` and the comparison leg is recorded as unmet — the
 * reference can never manufacture agreement.
 */
function referenceProbe(repoRoot, budgetS = 300, timeoutMs = 330000) {
  return new Promise((resolve) => {
    let child;
    try {
      // U136: this child reaches `wsl.exe`, and `WSLENV` can carry named host variables INTO the WSL
      // VM. Forwarding `{...process.env}` verbatim was an explicit widening in a unit that crosses that
      // boundary, while the repo already had the scrub rule for exactly this. §2.2 does not stop at the
      // governed launch paths, so a diagnostic child gets the same treatment.
      child = spawn(defaultPython(), [...defaultPythonArgs(), "tools/live/emit_conductor_voice.py", "--emit-voice-probe", "--force"], {
        cwd: repoRoot,
        env: childEnv({ SOW_NEMO_PROBE_TIMEOUT_S: String(budgetS) }, process.env).env,
      });
    } catch (e) {
      resolve({ ok: false, reason: `could not launch the reference probe: ${e.message}` });
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (v) => { if (settled) return; settled = true; clearTimeout(to); try { child.kill(); } catch { /* gone */ } resolve(v); };
    const to = setTimeout(() => finish({ ok: false, reason: `reference probe timed out after ${timeoutMs}ms` }), timeoutMs);
    child.stdout.on("data", (d) => { out += d.toString(); });
    child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish({ ok: false, reason: `reference probe failed to run: ${e.message}` }));
    child.on("exit", (code) => {
      if (code !== 0) { finish({ ok: false, reason: `reference probe exited ${code}: ${err.trim().slice(0, 200)}` }); return; }
      try {
        const feed = JSON.parse(out);
        const engine = feed.engine || {};
        finish({
          ok: feed.sourced === true,
          budget_s: budgetS,
          real_available: engine.real_available === true,
          nemo_state: engine.nemo_state || null,
          elapsed_s: engine.probe ? engine.probe.elapsed_s : null,
          timeout_s_in_force: engine.probe ? engine.probe.timeout_s : null,
          mock: engine.mock,          // must be TRUE even when available: a probe transcribes nothing
          tts: feed.tts,              // I-V2/D-VOICE-02, read from the producer rather than assumed
          reason: String(engine.reason || feed.reason || ""),
        });
      } catch (e) { finish({ ok: false, reason: `reference probe emitted non-JSON: ${e.message}` }); }
    });
  });
}

async function run(ctx) {
  const { win, isSupervised, conductorState, voiceState, voiceProbe, log } = ctx;
  const receipt = {
    schema: "phase17c_voice_probe_selfcheck@1.0",
    check: "phase-17c.probe",
    issue: "U74 (OP-11 finding F1) — the voice badge said 'mock engine' on a host with real Parakeet",
    started: new Date().toISOString(),
    ok: false,
    supervision_ready: false,
    conductor_pane_id: null,
    inflight: null,          // what `voice:state` said WHILE the probe was running, and how fast
    settled: null,           // the probe's own answer + measured elapsed time
    forced: null,            // the re-probe that falsifies the lifetime cache
    badge: { while_probing: null, after_settle: null },
    reference: null,         // the independent measurement of the same host (see referenceProbe)
    rearm: null,             // the expiry/re-arm behaviour, driven against the real VoiceProbe
    host: null,
    checks: {},
    error: null,
  };

  try {
    // 1. supervision READY
    receipt.supervision_ready = await waitFor(isSupervised, 25000, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY (control-plane/IPC gateway did not verify within 25s)");
    }
    const cs = conductorState ? conductorState() : null;
    const conductorPaneId = cs && cs.paneId;
    receipt.conductor_pane_id = conductorPaneId || null;

    // 2. THE NON-BLOCKING PROPERTY. The shell kicked the probe at first paint; read the state while it
    //    is still in flight and MEASURE how long that read took. A `voice:state` that awaited the probe
    //    would sit here for seconds — that is the regression this ceiling detects.
    const probe = voiceProbe();
    const t0 = Date.now();
    const inflightState = voiceState();
    const readMs = Date.now() - t0;
    const inflightEngine = (inflightState && inflightState.control && inflightState.control.engine) || {};
    receipt.inflight = {
      read_ms: readMs,
      ceiling_ms: NONBLOCKING_CEILING_MS,
      probe_state: inflightState && inflightState.probe ? inflightState.probe.state : null,
      engine_label: inflightEngine.label || null,
      probing: inflightEngine.probing === true,
      probes_started: inflightState && inflightState.probe ? inflightState.probe.probes : null,
    };
    receipt.checks.state_read_is_nonblocking = readMs < NONBLOCKING_CEILING_MS;
    // The probe may already have answered on a very warm host — that is a legitimate outcome, not a
    // failure, so this leg asserts the honest disjunction: either it is OPEN and says "probing…", or it
    // has ANSWERED. What it may never be is unanswered-and-labelled-"mock engine".
    const openAndHonest = receipt.inflight.probing === true && /probing/.test(inflightEngine.label || "");
    const alreadyAnswered = receipt.inflight.probe_state === "available" || receipt.inflight.probe_state === "unavailable";
    receipt.checks.unanswered_probe_is_never_labelled_mock = openAndHonest || alreadyAnswered;
    receipt.checks.probe_started_at_launch = (receipt.inflight.probes_started || 0) >= 1;

    // 3. the RENDERER painted the open question as open (the operator's eye-level evidence).
    if (conductorPaneId) {
      const b = await evalR(win, `window.__sovereignSelfCheck.voiceBadgeText(${JSON.stringify(conductorPaneId)})`);
      receipt.badge.while_probing = b && b.text;
      const text = (b && b.text) || "";
      receipt.checks.chrome_shows_the_open_question =
        alreadyAnswered ? true : (/probing/i.test(text) && !/mock engine/i.test(text));
    } else {
      receipt.checks.chrome_shows_the_open_question = false;
      log("[selfcheck:voice-probe] no conductor pane id — cannot read the chrome");
    }

    // 4. THE ANSWER. Wait for the probe to settle within its ceiling and record what it measured.
    const settleStart = Date.now();
    const settled = await Promise.race([
      probe.start(),
      sleep(PROBE_SETTLE_CEILING_MS).then(() => null),
    ]);
    if (!settled) throw new Error(`the STT probe did not settle within ${PROBE_SETTLE_CEILING_MS}ms`);
    receipt.settled = {
      state: settled.state,
      reason: settled.reason,
      probe_elapsed_ms: settled.elapsedMs,
      wait_ms: Date.now() - settleStart,
      probes: settled.probeCount,
      engine: settled.engine,
    };
    receipt.checks.probe_answered = settled.state === "available" || settled.state === "unavailable";
    receipt.checks.probe_within_budget = settled.elapsedMs < PROBE_SETTLE_CEILING_MS;

    // …and the badge flipped ITSELF: main pushes `shell:voice`, so the chrome must now agree with the
    // answer WITHOUT the operator clicking anything. On a real-stack host that is "<engine> ready".
    const realHost = settled.state === "available";
    // On a real-stack host with no capture yet the honest label is "<engine> ready" — reachable, and
    // nothing transcribed. Anything else (a bare engine name, or "mock engine") is a wrong claim.
    const settledRe = realHost ? /ready/i : /mock engine/i;
    const flipped = conductorPaneId
      ? await waitFor(async () => {
        const b = await evalR(win, `window.__sovereignSelfCheck.voiceBadgeText(${JSON.stringify(conductorPaneId)})`);
        return !!(b && typeof b.text === "string" && settledRe.test(b.text) && !/probing/i.test(b.text));
      }, 15000, 250)
      : false;
    const after = conductorPaneId
      ? await evalR(win, `window.__sovereignSelfCheck.voiceBadgeText(${JSON.stringify(conductorPaneId)})`)
      : null;
    receipt.badge.after_settle = after && after.text;
    receipt.checks.badge_flipped_without_operator_action = flipped;
    // the U74 headline, stated as the operator would: on a host where the real stack IS reachable, the
    // badge must not say "mock engine". On a host where it is not, "mock engine" is the honest answer.
    receipt.checks.badge_agrees_with_the_host = realHost
      ? !/mock engine/i.test((after && after.text) || "")
      : /mock engine/i.test((after && after.text) || "");
    // …and it must not over-correct: no capture has run, so a reachable engine renders READY. A bare
    // engine name would assert that the real engine transcribed something, which nothing has.
    receipt.checks.badge_claims_no_transcript_before_a_capture = realHost
      ? /ready/i.test((after && after.text) || "")
      : true;

    // 5. NOTHING IS PINNED. A forced re-probe must actually take a new probe — the falsification of the
    //    `lru_cache(maxsize=1)` half of U74, which made the answer un-retakeable for the app's life.
    const before = probe.probeCount;
    const forced = await probe.refresh();
    receipt.forced = { probes_before: before, probes_after: forced.probeCount, state: forced.state,
                       elapsed_ms: forced.elapsedMs };
    receipt.checks.reprobe_on_demand_actually_reprobes = forced.probeCount > before;
    receipt.checks.reprobe_agrees_with_the_first = forced.state === settled.state;

    // 5b. THE INDEPENDENT OPINION. Everything above compares the badge to the probe's own answer, which
    //     is precisely the circle U74 shipped inside: a wrong "unavailable" draws a perfectly
    //     consistent "mock engine". Take a second measurement of the SAME host through a route that
    //     cannot inherit the budget under test (an explicit SOW_NEMO_PROBE_TIMEOUT_S override), and
    //     require the shell's own verdict to match it.
    const reference = await referenceProbe(ctx.repoRoot);
    receipt.reference = reference;
    // STATED LIMIT, so this leg is not read as more than it is: the reference is independent of the
    // BUDGET under test and of nothing else. It runs the same `probe_nemo` with the same PROBE_IMPORT
    // through the same config, differing only in `SOW_NEMO_PROBE_TIMEOUT_S`. A wrong probe QUESTION —
    // the other half of the original defect, where `import nemo` was a 0.04 s namespace import that
    // said nothing about ASR — would be reproduced identically by both and this leg would pass. What
    // establishes that a passing probe implies transcription is a real capture, which is `.mic`; the
    // nearest existing evidence is docs/evidence/receipts/PHASE16E_REAL_PARAKEET_SMOKE.json.
    receipt.reference_scope = "independent of the probe BUDGET only (same probe question, same config, "
      + "different SOW_NEMO_PROBE_TIMEOUT_S); it cannot falsify a wrong probe question, and no leg here "
      + "establishes that a green probe implies a successful transcription — that is `.mic`.";
    receipt.checks.reference_probe_sourced = reference.ok === true;
    receipt.checks.shell_verdict_matches_the_reference =
      reference.ok === true && reference.real_available === (settled.state === "available");
    // …and the override reached the spawn (the same fact, from the budget the probe recorded).
    receipt.checks.env_override_honoured_end_to_end =
      reference.ok === true && reference.timeout_s_in_force === reference.budget_s;
    // …and the PRODUCER itself refuses to claim a transcript. This is the contract-level form of the
    // "no fabricated real transcript" rule: before, only the JS consumer corrected `mock`, which put
    // the honesty one new consumer away from an operator-visible false claim.
    receipt.checks.producer_never_claims_a_transcript = reference.ok === true && reference.mock === true;

    // 5c. THE RE-ARM PROPERTY. `state()` may claim `probing` only while a child is genuinely running,
    //     and an expired answer must be RE-TAKEN rather than pinned. Both reviews of this unit found an
    //     earlier revision advertising "probing…" forever with nothing probing — U74's own shape (one
    //     answer decides the whole run) inverted. Drive it against the real object with a tiny TTL.
    const { VoiceProbe } = require("../voice/probe");
    let clock = 5_000_000;
    const rearm = new VoiceProbe({ cwd: ctx.repoRoot, log, now: () => clock,
                                   negativeTtlMs: 1000, positiveTtlMs: 1000 });
    const first = await rearm.start();
    clock += 5000;                                   // both TTLs expire
    const stale = rearm.state();
    const armed = rearm.ensureFresh();               // the read the chrome performs
    receipt.rearm = {
      first_state: first.state, first_probes: first.probeCount,
      stale_state: stale.state, stale_probing: stale.probing === true, stale_flag: stale.stale === true,
      armed_probes: armed.probeCount, armed_reprobing: armed.reprobing === true,
    };
    // an expired answer is reported as the last ESTABLISHED fact, flagged stale — never as "probing"
    receipt.checks.expired_answer_is_not_advertised_as_probing =
      stale.probing === false && stale.stale === true && stale.state === first.state;
    // …and reading it ACTUALLY re-takes the probe (the operator who just finished the install)
    receipt.checks.stale_read_rearms_a_real_probe = armed.probeCount > first.probeCount;
    await rearm.start();          // let the re-armed probe settle so nothing is left in flight
    rearm.dispose();              // D-LOOP-1: this check leaves no child behind

    // 6. fail-closed honesty of the answer itself.
    const det = (settled.engine && settled.engine.detection) || {};
    receipt.host = { detection: det, nemo_state: settled.engine && settled.engine.nemo_state,
                     probe: settled.engine && settled.engine.probe };
    receipt.checks.real_available_equals_detection =
      (settled.engine.real_available === true) === !!(det.nvidia_gpu && det.wsl && det.nemo);
    receipt.checks.probing_never_claims_an_engine =
      !(settled.engine.probing === true && settled.engine.real_available === true);
    // I-V2/D-VOICE-02. Read from the PRODUCER's own payload (the reference feed's `tts`), not only from
    // the shell's hard-coded `speechOut:false` — a constant checked against itself proves nothing.
    receipt.checks.no_tts = voiceState().speechOut === false && reference.tts === false;

    const c = receipt.checks;
    receipt.ok = c.state_read_is_nonblocking && c.unanswered_probe_is_never_labelled_mock
      && c.probe_started_at_launch && c.chrome_shows_the_open_question
      && c.probe_answered && c.probe_within_budget
      && c.badge_flipped_without_operator_action && c.badge_agrees_with_the_host
      && c.badge_claims_no_transcript_before_a_capture
      && c.reprobe_on_demand_actually_reprobes && c.reprobe_agrees_with_the_first
      && c.reference_probe_sourced && c.shell_verdict_matches_the_reference
      && c.env_override_honoured_end_to_end && c.producer_never_claims_a_transcript
      && c.expired_answer_is_not_advertised_as_probing && c.stale_read_rearms_a_real_probe
      && c.real_available_equals_detection && c.probing_never_claims_an_engine && c.no_tts;

    receipt.scope_note = "This check measures the ENGINE-STATE half of 17C (U74): what the shell knows "
      + "about speech recognition and what it shows the operator. Real microphone PCM capture into the "
      + "live conductor session is the `.mic` sub-step; the spoken-mic leg itself is validated by the "
      + "operator's first use (directive §16 track 17C). No audio was captured or transcribed here.";
  } catch (e) {
    receipt.error = String((e && e.message) || e);
    if (log) log(`[selfcheck:voice-probe] crashed: ${e && e.message}`);
  }

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron,
    node: process.versions.node,
    chrome: process.versions.chrome,
    platform: process.platform,
    arch: process.arch,
  };
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    if (log) log(`[selfcheck:voice-probe] could not write receipt: ${e && e.message}`);
  }
  if (log) log(`[selfcheck:voice-probe] ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runVoiceProbeSelfCheck: run, RECEIPT_PATH, NONBLOCKING_CEILING_MS, PROBE_SETTLE_CEILING_MS };
