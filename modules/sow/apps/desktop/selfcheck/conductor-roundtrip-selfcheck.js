"use strict";
/**
 * Phase 17A `.roundtrip` in-Electron self-check (D-P16-0 binding, per-track).
 *
 * `.pty` proved the shell RUNS the real interactive `claude` conductor session inside pane 1's ConPTY.
 * It deliberately sent nothing. This is the leg the operator actually cares about — directive §16
 * definition-of-done (a): **type to pane 1, get a live answer** — and it is the last thing that can
 * separate "a session is running" from "the conductor talks back".
 *
 * The keystrokes take the OPERATOR'S path, not a shortcut: `term.input()` on the renderer's live xterm
 * fires the same `onData` a physical key does → `pane:input` IPC → `SessionManager.write` → the ConPTY.
 * Nothing here writes to a pty handle directly, and the check owns no authority the renderer lacks.
 *
 * Falsifiability (the whole point — see conductor/roundtrip-probe.js):
 *   • the prompt is arithmetic with the operands SPELLED IN WORDS, so it contains no digit and the
 *     answer cannot arrive as an echo of what was typed;
 *   • the operands are drawn fresh per run — no canned reply satisfies it;
 *   • the answer token is asserted ABSENT from the pane before submitting (a banner that already
 *     contains the number re-rolls the draw instead of passing for free);
 *   • the echo and the answer are separate assertions: keystrokes-arrived and model-answered fail
 *     independently, so a dead model cannot pass on a live terminal.
 *
 * LIVE SCOPE (§16 "live exchanges MINIMAL"): exactly ONE prompt and ONE answer, ~20 tokens, then the
 * session is killed and the durable I-X3 terminal handed back (D-LOOP-1). SCRATCH lease ledger
 * throughout, so the check can never adopt or release the operator's own conductor terminal.
 *
 * THE MODEL PROBE (the defect the first run of this check exposed). The first `.roundtrip` run failed
 * honestly: the session was live, the keystrokes arrived, and the CLI answered "There's an issue with
 * the selected model (fable-5). It may not exist or you may not have access to it." The launch path
 * now resolves the accepted slug first (`conductor/model-probe-source` → the governed Python probe),
 * so this check exercises that production path and RECORDS what it resolved — an accepted slug, or a
 * recorded CLI-default fallback, never a silent substitution. The probe LEDGER is deliberately the
 * host's real one (not scratch, unlike the lease ledger): it caches an observation about this host's
 * CLI, so sharing it costs the operator nothing and spares a live call on every run, while the lease
 * ledger stays scratch because it is authority over the operator's own terminals.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const { fetchLeaseStatus } = require("../conductor/launch-source");
const { buildRoundTripProbe, probeIsFalsifiable, answerObserved, promptEchoed } = require("../conductor/roundtrip-probe");

const RECEIPT_PATH = receiptPath("PHASE17A_ROUNDTRIP_SELFCHECK.json");
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SCRATCH_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", `selfcheck-17art-${process.pid}.json`);

// Per-step ceilings. Their sum — plus the launch step's own model-probe budget (≤200 s, and ~0 once
// the host verdict is cached) — stays under the launcher's hard timeout for this kind, so a stall
// FAILS the receipt here with the step that stalled NAMED, rather than being killed blind.
const SUPERVISION_MS = 30000;
const TUI_READY_MS = 45000;
const ECHO_MS = 20000;
const ANSWER_MS = 150000;
const KILL_MS = 15000;
const RELEASE_MS = 45000;

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

/** The rendered xterm buffer for a pane (read-only renderer observability hook). */
async function paneText(win, paneId) {
  const expr = `window.__sovereignSelfCheck && window.__sovereignSelfCheck.paneText(${JSON.stringify(paneId)})`;
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

/** Type through the REAL renderer input wiring (term.onData → pane:input → manager.write → PTY). */
async function typeInto(win, paneId, data) {
  const expr = `window.__sovereignSelfCheck.typeInto(${JSON.stringify(paneId)}, ${JSON.stringify(data)})`;
  try { return await win.webContents.executeJavaScript(expr); } catch { return false; }
}

/**
 * The interactive CLI is ready for input when it has painted its banner (the governed workspace it
 * opened) AND stopped repainting. Quiescence is what makes the subsequent keystrokes land in the
 * input box rather than into a half-drawn frame.
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

async function run(ctx) {
  const { win, isSupervised, conductorState, launchConductorSession, conductorLaunchState,
    sessionManager, killSession, log } = ctx;
  const receipt = {
    check: "phase-17a.roundtrip",
    started: new Date().toISOString(),
    ok: false,
    ledger_scope: "scratch",
    ledger_path: SCRATCH_LEDGER,
    electron_main_pid: process.pid,
    // the governed live session (same production path .pty gated)
    supervision_ready: false,
    pane_id: null,
    launched: false,
    launch_state: null,
    launch_reason: null,
    argv: null,
    session_id: null,
    session_pid: null,
    session_state: null,
    lease_id: null,
    lease_in_use: null,
    lease_allowance: null,
    // WHICH model the governed launch actually asked for, and on what evidence (never silent)
    model_label: null,
    model_slug: null,
    model_probe_source: null,
    model_is_fallback: null,
    // the probe
    tui_ready: false,
    probe_prompt: null,
    probe_expected_token: null,
    probe_falsifiable: false,
    probe_rerolls: 0,
    answer_absent_before_submit: false,
    // the typed half (the operator's own path)
    input_path: "renderer xterm term.onData → pane:input IPC → SessionManager.write → ConPTY",
    typed_via_renderer: false,
    prompt_echoed: false,
    submitted: false,
    // the live half
    answer_seen: false,
    answer_form: null,
    answer_latency_ms: null,
    answer_excerpt: null,
    // D-LOOP-1
    session_killed: false,
    lease_released: false,
    in_use_after_release: null,
    error: null,
  };

  const priorLedger = process.env.SOW_TERMINAL_LEASE_LEDGER;
  process.env.SOW_TERMINAL_LEASE_LEDGER = SCRATCH_LEDGER;
  let sessionId = null;
  let paneId = null;
  try {
    // 1. supervision READY — a session is only ever born on a verified channel (invariant 2)
    receipt.supervision_ready = await waitFor(isSupervised, SUPERVISION_MS, 250);
    if (!receipt.supervision_ready) throw new Error("supervision never became READY (no session may be born)");
    paneId = conductorState().paneId;
    receipt.pane_id = paneId;
    if (!paneId) throw new Error("no conductor pane exists to talk to");

    // 2. THE PRODUCTION LAUNCH PATH (identical to on-launch and to the pane-1 control)
    const res = await launchConductorSession({ reason: "in-Electron self-check (17A .roundtrip)" });
    const st = conductorLaunchState();
    sessionId = st.sessionId;
    receipt.launched = res.launched === true;
    receipt.launch_state = st.state;
    receipt.launch_reason = st.reason || (res && res.reason) || null;
    receipt.session_id = sessionId;
    receipt.argv = Array.isArray(st.argv) ? st.argv.slice() : null;
    receipt.session_pid = st.pid || null;
    receipt.lease_id = st.leaseId || null;
    // The slug is READ back off the authorized argv (what the session was really given), and its
    // provenance from the ticket's own probe block — not from what this check hoped for.
    const slugAt = Array.isArray(receipt.argv) ? receipt.argv.indexOf("--model") : -1;
    receipt.model_slug = slugAt >= 0 ? receipt.argv[slugAt + 1] || null : null;
    receipt.model_label = (st.modelProbe && st.modelProbe.label) || null;
    receipt.model_probe_source = (st.modelProbe && st.modelProbe.source) || null;
    receipt.model_is_fallback = (st.modelProbe && st.modelProbe.model_available === false) || false;
    if (!receipt.launched) throw new Error(`the governed live launch did not run: ${receipt.launch_reason || "unknown"}`);
    const mgr = sessionManager();
    receipt.session_state = mgr && mgr.registry.has(paneId) ? mgr.registry.get(paneId).state : null;
    if (receipt.session_state !== "RUNNING") throw new Error(`the conductor session is ${receipt.session_state}, not RUNNING`);
    const leaseStatus = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
    const entry = ((leaseStatus.ok && leaseStatus.status && leaseStatus.status.subscriptions) || {})[st.subscriptionRef] || null;
    receipt.lease_in_use = entry ? entry.in_use : null;
    receipt.lease_allowance = leaseStatus.ok && leaseStatus.status ? leaseStatus.status.allowance : null;

    // 3. wait for the live CLI to finish painting and settle
    const tui = await waitForTuiQuiescence(win, paneId, TUI_READY_MS);
    receipt.tui_ready = tui.ready;
    if (!receipt.tui_ready) throw new Error("the live conductor session never settled into a ready, quiescent view");

    // 4. draw a probe whose answer the pane cannot already contain
    let probe = null;
    let before = tui.text || "";
    for (let roll = 0; roll < 5; roll++) {
      probe = buildRoundTripProbe();
      receipt.probe_rerolls = roll;
      if (!answerObserved(before, probe).seen) break;
      probe = null; // this draw's answer is already on screen — it would pass for free
    }
    if (!probe) throw new Error("could not draw an answer token absent from the pane in 5 attempts");
    receipt.probe_prompt = probe.prompt;
    receipt.probe_expected_token = probe.expectedToken;
    receipt.probe_falsifiable = probeIsFalsifiable(probe);
    receipt.answer_absent_before_submit = !answerObserved(before, probe).seen;
    if (!receipt.probe_falsifiable) throw new Error("the drawn probe carries its own answer — the receipt would prove nothing");

    // 5. TYPE IT — the operator's own path. Text first, then Enter, so the echo (keystrokes arrived)
    //    and the answer (a model replied) are two independent observations.
    await win.webContents.executeJavaScript(`window.__sovereignSelfCheck.focusPane(${JSON.stringify(paneId)})`);
    receipt.typed_via_renderer = (await typeInto(win, paneId, probe.prompt)) === true;
    if (!receipt.typed_via_renderer) throw new Error("the renderer has no live terminal for pane 1 — keystrokes have nowhere to go");
    receipt.prompt_echoed = await waitFor(async () => promptEchoed(await paneText(win, paneId), probe), ECHO_MS, 400);
    if (!receipt.prompt_echoed) throw new Error("what was typed never appeared in the pane — keystrokes are not reaching the live session");
    const submittedAt = Date.now();
    receipt.submitted = (await typeInto(win, paneId, "\r")) === true;
    if (!receipt.submitted) throw new Error("the submit keystroke could not be delivered");

    // 6. THE LIVE ANSWER
    let observed = { seen: false, form: null };
    const got = await waitFor(async () => {
      observed = answerObserved(await paneText(win, paneId), probe);
      return observed.seen;
    }, ANSWER_MS, 1000);
    receipt.answer_seen = got && observed.seen;
    receipt.answer_form = observed.form;
    receipt.answer_latency_ms = got ? Date.now() - submittedAt : null;
    const after = await paneText(win, paneId);
    const tail = typeof after === "string" ? after.replace(/\s+/g, " ").trim() : "";
    receipt.answer_excerpt = tail.slice(-300) || null;
    if (!receipt.answer_seen) {
      throw new Error(`the live conductor never answered within ${ANSWER_MS / 1000}s `
        + `(expected ${probe.expectedToken}) — typing still gets no answer`);
    }
    log(`[selfcheck] LIVE round trip: typed "${probe.prompt}" → ${probe.expectedToken} `
      + `(${receipt.answer_form}) in ${receipt.answer_latency_ms}ms`);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  } finally {
    // 7. D-LOOP-1 — neither the live session nor its terminal outlives this check.
    try {
      if (paneId && sessionManager() && sessionManager().registry.has(paneId)) {
        killSession(paneId);
        receipt.session_killed = await waitFor(() => {
          if (!receipt.session_pid) return true;
          try { process.kill(receipt.session_pid, 0); return false; } catch { return true; }
        }, KILL_MS, 250);
      }
      receipt.lease_released = await waitFor(async () => {
        const afterStatus = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
        // An UNREADABLE count is not a released terminal.
        if (!afterStatus.ok || !afterStatus.status) { receipt.in_use_after_release = null; return false; }
        const e2 = (afterStatus.status.subscriptions || {})[conductorLaunchState().subscriptionRef || ""] || null;
        receipt.in_use_after_release = e2 ? e2.in_use : 0;
        return receipt.in_use_after_release === 0;
      }, RELEASE_MS, 1000);
    } catch (e) {
      receipt.error = receipt.error || `teardown failed: ${String((e && e.message) || e)}`;
    }
    if (priorLedger === undefined) delete process.env.SOW_TERMINAL_LEASE_LEDGER;
    else process.env.SOW_TERMINAL_LEASE_LEDGER = priorLedger;
    try { fs.rmSync(SCRATCH_LEDGER, { force: true }); } catch { /* nothing to remove */ }
  }

  receipt.ok = receipt.error === null
    && receipt.supervision_ready && receipt.launched && receipt.session_state === "RUNNING"
    && receipt.tui_ready && receipt.probe_falsifiable && receipt.answer_absent_before_submit
    && receipt.typed_via_renderer && receipt.prompt_echoed && receipt.submitted
    && receipt.answer_seen
    && receipt.session_killed && receipt.lease_released && receipt.in_use_after_release === 0;

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  receipt.scope_note = "The `--model` slug is the one the host CLI was OBSERVED to accept: the "
    + "governed probe (tools/live/probe_conductor_model.py) resolved the operator's selection LABEL "
    + "to it with a live call, and an unresolvable label would launch on the CLI default with "
    + "`model_is_fallback` set — never a silent substitution. "
    + "ONE minimal live exchange (§16 live-budget discipline): a single arithmetic "
    + "prompt typed through the RENDERER's own input path into the governed interactive `claude` "
    + "session running in pane 1's ConPTY, and the model's answer read back out of the xterm buffer. "
    + "The operands are spelled in words so the prompt contains no digit, the draw is fresh per run, "
    + "and the answer token is asserted absent from the pane before submitting — an echo, a canned "
    + "reply or stale scrollback cannot satisfy `answer_seen`. What this does NOT claim: any worker "
    + "leg (17B/U58/U70), voice input (17C), tool use, or that the answer was correct beyond the "
    + "arithmetic token. Containment is as `.pty` recorded it (supervised admission, governed "
    + "identity, workspace binding, credential env scrub; permission-profile binding and OS job "
    + "objects still owed — U78/U25). The session and its durable I-X3 terminal are torn down here; "
    + "the OPERATOR's own conductor session persists by design.";
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] conductor-roundtrip ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runConductorRoundTripSelfCheck: run, RECEIPT_PATH };
