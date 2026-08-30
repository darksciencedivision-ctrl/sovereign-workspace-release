"use strict";
/**
 * Phase 16E in-Electron voice-IN self-check (D-P16-0 binding, per-track). `.wire` proved the WRITE half
 * (talk button → bridge → conductor input); `.real` extends it to prove the running shell now surfaces
 * the WSL-probed real-engine state HONESTLY.
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer + real ConPTY) and proves: the talk
 * button ROUTES a captured utterance through the REAL Python ConductorVoiceBridge (voice:capture →
 * voice-source → emit_conductor_voice); the engine indicator is HONEST about the host — on a real-stack
 * host it renders "<engine> ready" (NOT "mock engine": the operator's OP-10 complaint) while still
 * reporting the stand-in transcript as the mock's (no fabricated real transcript), and on a host without
 * the stack it renders the visible "mock engine"; a CHAT transcript is WRITTEN into a conductor pane's
 * input over the SAME manager.write path typing uses — reaching a real PTY. Writes a machine-readable
 * receipt so the gate closes on runtime evidence, not headless-only tests.
 *
 * Flow (every boolean is measured; nothing is fabricated):
 *   1. wait for supervision READY (governed spawn; no naked session — invariant 2);
 *   2. CAPTURE a SAFE-verb utterance through the real talk-button path
 *      (`window.__sovereignSelfCheck.captureVoice("audio:show-status")`): assert it was SOURCED
 *      (`sourced:true`) from the engine-selected feed, routed as CHAT (`delivered:true`) with a real
 *      transcript, the engine is a VISIBLE mock (`engine.mock:true` — never a silent pretend-to-hear),
 *      and `selfAuthorized:false` (the shell forwarded the bridge's verdict, it decided nothing);
 *   3. assert the RENDERER painted the engine indicator ("mock engine") + the "Delivered to conductor"
 *      outcome into pane-1's `.cvoice` chrome (feed, main, and pixel agree);
 *   4. the WRITE: deliver the captured transcript into a REAL admitted supervised pane (a freshly
 *      spawned PTY standing in for the live conductor session, which is operator-run/16F) via the SAME
 *      production delivery function the handler uses (`ctx.deliverConductorChat`), then assert the text
 *      echoes into that pane's xterm buffer — proving talk → bridge → CHAT → an admitted pane's PTY;
 *   5. the HONESTY negatives: a PROTECTED/DESTRUCTIVE utterance ("audio:terminate-node-b") is QUEUED for
 *      approval and NEVER delivered (`queued:true`, `delivered:false`, `delivered_to_conductor:false` —
 *      invariant 25); and the production conductor pane (no admitted live session) reports the write as
 *      OWED to 16F rather than a fabricated delivery;
 *   6. write the receipt. The caller tears down (no orphan PTY/gateway — D-LOOP-1) and exits pass/fail.
 *
 * Load-bearing: if the wiring reverted to the old record-only `voice:propose`, `sourced`/`delivered`
 * would be absent and the `.cvoice` chrome would stay blank ⇒ this FAILS. Empirically falsifiable by the
 * validator moving the emitter aside (⇒ sourced:false ⇒ FAIL). NO live `claude`/`codex` call — the
 * voice feed runs the bridge mock-first (§2.2/§2.4). NO TTS (I-V2/D-VOICE-02) — the result carries none.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const RECEIPT_PATH = receiptPath("PHASE16E_REAL_SELFCHECK.json");

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

// Read a pane's rendered xterm buffer (read-only observability hook the renderer exposes).
async function paneText(win, paneId) {
  const expr = `window.__sovereignSelfCheck && window.__sovereignSelfCheck.paneText(${JSON.stringify(paneId)})`;
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, conductorState, deliverConductorChat, log } = ctx;
  const receipt = {
    schema: "phase16e_real_selfcheck@1.0",
    check: "phase-16e.real",
    started: new Date().toISOString(),
    ok: false,
    supervision_ready: false,
    conductor_pane_id: null,
    capture: null,
    protected_capture: null,
    checks: {},
    voice_badge_text: null,
    write_pane_id: null,
    error: null,
  };

  try {
    // 1. supervision READY (governed spawn path; a naked session is impossible by design)
    receipt.supervision_ready = await waitFor(isSupervised, 25000, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY (control-plane/IPC gateway did not verify within 25s)");
    }
    const cs = conductorState ? conductorState() : null;
    const conductorPaneId = cs && cs.paneId;
    receipt.conductor_pane_id = conductorPaneId || null;

    // 2. CAPTURE a SAFE-verb utterance through the REAL talk-button path (drives voice:capture → the
    //    Python ConductorVoiceBridge). The mock maps "audio:show-status" → "show status", a SAFE verb ⇒
    //    the bridge routes it as ordinary CHAT. Poll: the feed spins a broker/queue, so allow startup.
    await waitFor(async () => {
      const r = await evalR(win, 'window.__sovereignSelfCheck.captureVoice("audio:show-status")');
      return !!(r && r.sourced === true);
    }, 60000, 750);
    const cap = await evalR(win, 'window.__sovereignSelfCheck.captureVoice("audio:show-status")');
    receipt.capture = cap;
    receipt.checks.capture_sourced = !!(cap && cap.sourced === true);                 // load-bearing: the emitter ran
    receipt.checks.capture_is_chat = !!(cap && cap.delivered === true && cap.outcome && cap.outcome.kind === "chat");
    receipt.checks.capture_has_transcript = !!(cap && typeof cap.delivered_text === "string" && cap.delivered_text.trim());
    // Phase 16E `.real`: the engine descriptor is HONEST about the host. real_available reflects the
    // WSL NeMo probe; on this host it should agree with the detection conjunction. The stand-in
    // transcript is ALWAYS the mock's (engine.mock:true) — a real engine is never used for a PCM-less
    // ref, so there is never a fabricated real transcript (never a silent pretend-to-hear).
    const eng = (cap && cap.engine) || {};
    const det = eng.detection || {};
    const realAvailable = eng.real_available === true;
    receipt.engine_real_available = realAvailable;
    receipt.checks.engine_detection_honest =
      realAvailable === !!(det.nvidia_gpu && det.wsl && det.nemo);       // real_available ⇔ full stack probed
    receipt.checks.no_fabricated_real_transcript = eng.mock === true;    // stand-in ⇒ mock produced it, always
    receipt.self_authorized_false_note = "shell forwarded; Python decided";
    receipt.checks.self_authorized_false = !!(cap && cap.selfAuthorized === false);    // shell forwarded; Python decided
    receipt.checks.no_tts = !!(cap && cap.tts === false);                              // I-V2/D-VOICE-02
    // the production conductor pane has no admitted live session ⇒ the write is honestly OWED to 16F,
    // never fabricated as delivered (the live interactive conductor drive is operator-run).
    receipt.checks.conductor_write_owed_honest = !!(cap && cap.delivered_to_conductor === false && /OWED to 16F/.test(cap.note || ""));

    // 3. the RENDERER painted the HONEST engine indicator + the CHAT outcome into pane-1's .cvoice.
    //    On a real-stack host the tag reads "<engine> ready" (never "mock engine"); otherwise "mock
    //    engine". Either way it must be present alongside the "Delivered to conductor" outcome.
    // Phase 17C `.probe` (U74): the badge is drawn from the CHROME's engine descriptor, which since
    // 17C is the PROBE's maintained answer — a different (and better-founded) fact than this capture's
    // own engine. The capture routes a PCM-less stand-in, so its `real_available` now reflects a
    // non-blocking read rather than a fresh probe, and comparing the badge against it would assert
    // "mock engine" on a host where the probe has established the real engine IS reachable. Read the
    // expectation from what the badge is actually drawn from.
    const chromeEngine = (cap && cap.chromeEngine) || eng;
    const chromeRealAvailable = chromeEngine.real_available === true;
    receipt.chrome_engine_real_available = chromeRealAvailable;
    const engineTagRe = chromeRealAvailable ? /ready|parakeet/i : /mock engine|probing/i;
    // Phase 17C `.close` (spec-audit MAJOR-4): the outcome half of this badge no longer comes from the
    // routing verdict alone. THIS scenario has no admitted conductor session — the write is honestly
    // OWED — so the badge that used to read "Delivered to conductor" now reads "Routed — not delivered
    // to the conductor", and that is the fix, not a regression: claiming delivery for an utterance no
    // session received is exactly what the operator must never be shown. The expectation is therefore
    // derived from the WRITE the shell actually performed, so this leg pins the honesty in either state.
    const wroteToConductor = !!(cap && cap.delivered_to_conductor === true);
    const outcomeRe = wroteToConductor ? /Delivered to conductor/i : /not delivered to the conductor/i;
    const badgeOk = await waitFor(async () => {
      const b = await evalR(win, `window.__sovereignSelfCheck.voiceBadgeText(${JSON.stringify(conductorPaneId)})`);
      return !!(b && typeof b.text === "string" && engineTagRe.test(b.text) && outcomeRe.test(b.text));
    }, 15000, 300);
    const badge = await evalR(win, `window.__sovereignSelfCheck.voiceBadgeText(${JSON.stringify(conductorPaneId)})`);
    receipt.voice_badge_text = badge && badge.text;
    receipt.badge_expectation = { delivered_to_conductor: wroteToConductor, pattern: String(outcomeRe) };
    const badgeText = (badge && badge.text) || "";
    receipt.checks.rendered_engine_indicator = badgeOk && engineTagRe.test(badgeText);
    // the operator's OP-10 complaint fix: on a real-stack host the badge must NOT say "mock engine"
    receipt.checks.badge_not_mislabelled_mock = chromeRealAvailable ? !/mock engine/i.test(badgeText) : true;
    receipt.checks.rendered_outcome = badgeOk && outcomeRe.test(badgeText);
    // …and it must never claim delivery while the write says otherwise (the defect itself).
    receipt.checks.badge_never_claims_undelivered_as_delivered =
      wroteToConductor || !/(^|[^t])Delivered to conductor/i.test(badgeText);

    // 4. the WRITE: deliver the captured transcript into a REAL admitted supervised pane via the SAME
    //    production delivery function the handler uses, and assert it echoes into that pane's PTY buffer.
    const testPane = createPaneWithSession({
      file: "powershell.exe",
      args: ["-NoLogo", "-NoProfile", "-NoExit"],
      title: "voice-selfcheck",
    });
    receipt.write_pane_id = testPane;
    // the pane's xterm view must exist before we can read its buffer
    await waitFor(async () => evalR(win, `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(testPane)})`), 15000, 200);
    const transcript = (cap && cap.delivered_text) || "show status";
    // real production write, pointed at the admitted pane. AWAITED since 17C `.close`: the body and the
    // submit key are now two writes with a settle gap (the destination is an interactive TUI, not a
    // line-reading shell), so the delivery only reports `written` once both have gone out.
    const wr = await deliverConductorChat(`${transcript}`, testPane);
    receipt.checks.write_reported_written = !!(wr && wr.written === true);
    const echoed = await waitFor(async () => {
      const t = await paneText(win, testPane);
      return typeof t === "string" && t.includes(transcript);
    }, 15000, 250);
    receipt.checks.write_echoed_into_pty = echoed;
    log(`[selfcheck:voice] transcript "${transcript}" write=${wr && wr.written} echoed=${echoed}`);

    // 5. HONESTY negative — a PROTECTED/DESTRUCTIVE utterance is QUEUED, never delivered (invariant 25)
    const prot = await evalR(win, 'window.__sovereignSelfCheck.captureVoice("audio:terminate-node-b")');
    receipt.protected_capture = prot;
    receipt.checks.protected_queued = !!(prot && prot.queued === true && prot.outcome && prot.outcome.kind === "proposed_action");
    receipt.checks.protected_not_delivered = !!(prot && prot.delivered === false && prot.delivered_to_conductor === false);

    const c = receipt.checks;
    receipt.ok = c.capture_sourced && c.capture_is_chat && c.capture_has_transcript
      && c.engine_detection_honest && c.no_fabricated_real_transcript && c.badge_not_mislabelled_mock
      && c.self_authorized_false && c.no_tts && c.conductor_write_owed_honest
      && c.rendered_engine_indicator && c.rendered_outcome && c.badge_never_claims_undelivered_as_delivered
      && c.write_reported_written && c.write_echoed_into_pty
      && c.protected_queued && c.protected_not_delivered;

    receipt.live_capture_owed = "16F (routing + engine selection + conductor-input write are real; real mic PCM capture + the admitted live interactive conductor ConPTY session are operator-run; the real WSL Parakeet transcription itself is proven on this host by tools/live/real_parakeet_smoke.py)";
  } catch (e) {
    receipt.error = String((e && e.message) || e);
    if (log) log(`[selfcheck:voice] crashed: ${e && e.message}`);
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
    if (log) log(`[selfcheck:voice] could not write receipt: ${e && e.message}`);
  }
  if (log) log(`[selfcheck:voice] ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runVoiceSelfCheck: run, RECEIPT_PATH };
