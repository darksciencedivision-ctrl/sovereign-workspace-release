"use strict";
/**
 * Phase 19 unit 19.3 in-Electron self-check (D-P16-0 binding) — the SYSTEM→PANE write gate (U328).
 *
 * WHY IT EXISTS. The headless suite drives `control/pane-writer.js` with injected doubles and the
 * mutation harness proves those tests can fail. Neither runs inside the packaged runtime, and
 * D-P16-0 exists because 14A shipped a shell that passed headless tests and failed at first launch.
 * What this check adds is the wiring nobody can fake in a unit test: main.js's REAL bindings — the
 * live `SessionManager` screen reader, the real pane chrome/conductor provider resolver, the real
 * `manager.write` — driven against a REAL ConPTY session in the REAL renderer.
 *
 * The legs, in the order they run:
 *
 *  A1. a clean supervised pane takes a system write: `paneWriteRefusalFor` returns null, the
 *      production `writePanePrompt` returns true, and the body is OBSERVED executing in the pane —
 *      so the refactor did not merely stop refusing, it still delivers the body AND the submit key.
 *  A2. that same pane is then driven to a trust-modal screen through the OPERATOR's own input path
 *      (`window.sovereign.input`, not ours — the classification must be independent of the write
 *      path it gates). The refusal now names WORKSPACE_TRUST_REQUIRED, the production write returns
 *      false, the withheld body is NEVER observed on the screen, and — the assertion the 19.3 review
 *      required, because the first version did not make it — NO SUBMIT KEY REACHES THE PTY EITHER.
 *      The dangerous byte is the carriage return, not the body: a defect that withholds the body and
 *      still emits a bare `\r` answers the numbered menu while leaving no needle to find. The pane's
 *      prompt function is pinned to a unique token at spawn, so every submitted line adds exactly one
 *      occurrence and a stray Enter is COUNTABLE. The absence window ends with a positive control
 *      (a needle already on the screen is re-read), because `paneText` answers null when the renderer
 *      bridge dies, and "I could not look" must not read as "nothing happened".
 *  B.  a SECOND fresh pane proves the own-echo exclusion in the runtime: a system write whose BODY
 *      contains modal-shaped text ("yes, proceed") is delivered, because a pane echoing our own
 *      prompt back at us may not withhold that prompt's submit key. Without the exclusion this leg
 *      hangs the body in the input box forever.
 *  C.  a pane id with no session is UNREADABLE, not empty — an unopened pane classifies clean on an
 *      empty string, which would be the fail-OPEN reading of "nothing is on the screen".
 *
 * It starts no model, spends no live exchange, touches no credential, and kills both sessions in
 * this unit (D-LOOP-1). Every boolean is measured; a leg that cannot be measured fails the check.
 */
const fs = require("fs");
const path = require("path");
const { receiptPath } = require("./receipt-path");
const { sourceIdentity } = require("./voice-conductor-selfcheck");

const RECEIPT_STAMP = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
const RECEIPT_UNIT = String(process.env.SOW_SELFCHECK_UNIT || "run")
  .replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 40);
const RECEIPT_PATH = receiptPath(
  `PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_${RECEIPT_UNIT}_${RECEIPT_STAMP}.json`);

/** Per-step ceilings. Their sum stays under this kind's launcher bound, so a stall FAILS here with
 *  the step that stalled named, rather than being killed blind (exit 124 writes no receipt). */
const SUPERVISION_MS = 30000;
const TERM_MS = 20000;
const BANNER_MS = 30000;
const ECHO_MS = 20000;
/** How long the withheld body is watched for. It is an ABSENCE, so this is a bound on patience, not
 *  on a signal: the delivered legs above measure how long delivery actually takes (well under it). */
const ABSENCE_MS = 6000;

const BANNER = "SOVEREIGN_U328_PANE_READY";
/** The pane's prompt, pinned to a token nothing else prints: one occurrence per submitted line, so
 *  a carriage return that reached the PTY is counted rather than inferred. */
const PROMPT_TOKEN = "SOVEREIGN_U328_PROMPT>";
const DELIVERED = "SOVEREIGN_U328_DELIVERED";
const WITHHELD = "SOVEREIGN_U328_WITHHELD";
const ECHO_BODY_DELIVERED = "SOVEREIGN_U328_ECHOBODY";
/** Matches `classifyProviderScreen`'s provider-independent workspace-trust rule. */
const TRUST_LINE = "do you trust the contents of this project";
const TRUST_BODY_FRAGMENT = "yes, proceed";

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

async function paneText(win, paneId) {
  const expr = `window.__sovereignSelfCheck && window.__sovereignSelfCheck.paneText(${JSON.stringify(paneId)})`;
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

async function seesNeedle(win, paneId, needle, timeoutMs) {
  return waitFor(async () => {
    const text = await paneText(win, paneId);
    return typeof text === "string" && text.toLowerCase().includes(needle.toLowerCase());
  }, timeoutMs, 200);
}

/** The OPERATOR's input bridge — deliberately NOT the system write path this check is gating. */
async function operatorTypes(win, paneId, data) {
  try {
    await win.webContents.executeJavaScript(
      `window.sovereign.input(${JSON.stringify(paneId)}, ${JSON.stringify(data)})`);
    return true;
  } catch { return false; }
}

/** How many lines this pane has submitted, by its own prompt token. `null` when the screen cannot be
 *  read at all — never 0, which would read as "no submissions" (fail closed on ambiguity). */
async function submitCount(win, paneId) {
  const text = await paneText(win, paneId);
  if (typeof text !== "string") return null;
  return text.split(PROMPT_TOKEN).length - 1;
}

async function spawnPane(ctx, receipt, label, paneIds) {
  const paneId = ctx.createPaneWithSession({
    file: "powershell.exe",
    args: ["-NoLogo", "-NoProfile", "-NoExit", "-Command",
      `function prompt { '${PROMPT_TOKEN} ' }; Write-Output '${BANNER}'`],
    title: `u328-${label}`,
  });
  // The pane id is recorded BEFORE the assertions below, so a pane that spawns and then fails to
  // banner is still torn down by the caller (D-LOOP-1); the earlier version pushed it after.
  if (Array.isArray(paneIds)) paneIds.push(paneId);
  const termed = await waitFor(async () => win_hasTerm(ctx.win, paneId), TERM_MS, 200);
  const banner = termed && await seesNeedle(ctx.win, paneId, BANNER, BANNER_MS);
  receipt.panes.push({ pane: label, pane_id: paneId, term_created: termed, banner_seen: banner });
  if (!termed) throw new Error(`renderer never created an xterm view for pane ${label}`);
  if (!banner) throw new Error(`pane ${label} never rendered its banner (no legible screen to gate)`);
  return paneId;
}

async function win_hasTerm(win, paneId) {
  return win.webContents.executeJavaScript(
    `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(paneId)})`);
}

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, writePanePrompt, paneWriteRefusalFor,
    killSession, log } = ctx;
  const receipt = {
    check: "phase-19.3.system-pane-write",
    unit: process.env.SOW_SELFCHECK_UNIT || null,
    // Say exactly what the legs below establish. The earlier wording ("nothing this shell sends may
    // answer a trust/permission modal") was an absolute the code falsifies — `classifyProviderScreen`
    // is a denylist and allows every screen it does not recognise (U363) — and a receipt outlives the
    // prose around it, so it may not be the artifact that overstates.
    finding: "U328 — no system→pane write reaches the PTY unclassified, and none answers a modal "
      + "classifyProviderScreen RECOGNISES or a confirmation/selection affordance modalAffordance "
      + "recognises (19.4-followon widened the verdict), as the screen stood at the last read before "
      + "each keystroke (invariant 1, D-P18-13). Screens NEITHER recognises are still written into: "
      + "U363, narrowed and open.",
    source: sourceIdentity(),
    started: new Date().toISOString(),
    electron_main_pid: process.pid,
    ok: false,
    supervision_ready: false,
    panes: [],
    legs: {},
    scope_note_screen_signal: "the gate's signal is the shell's ONE bounded window — the last 80 "
      + "non-blank lines of the last 16 KB of raw stream, the same object readiness classifies "
      + "through (U373's residual, closed in 19.4-followon) — judged by the DENYLIST provider-state "
      + "classifier AND, since that unit, the modal-affordance families; so it no longer inherits "
      + "U329's whole-buffer weakness, it does inherit the bounded window's own residual (U395: a "
      + "pane taller than 80 non-blank lines, or a repaint costing more than 16 KB, crops the live "
      + "screen) and U363's fail-open default is narrowed but not closed (7 of the 19.3 validator's "
      + "10 permission screens refuse; 3 are recorded residual); this check measures the gate and "
      + "its wiring, never the classifier's coverage — the panes it drives are powershell.exe "
      + "printing text this check chose, so no real provider screen is evidenced here (U362)",
    live_exchanges: 0,
    error: null,
  };
  const paneIds = [];
  try {
    if (typeof writePanePrompt !== "function" || typeof paneWriteRefusalFor !== "function") {
      throw new Error("the runtime did not expose its production system→pane write path");
    }
    receipt.supervision_ready = await waitFor(isSupervised, SUPERVISION_MS, 250);
    if (!receipt.supervision_ready) throw new Error("supervision never became READY");
    if (typeof createPaneWithSession !== "function") throw new Error("no supervised pane path");

    // ---- A1: a clean pane takes a system write, body AND submit key ------------------------------
    const paneA = await spawnPane(ctx, receipt, "A", paneIds);
    const cleanRefusal = paneWriteRefusalFor(paneA);
    const cleanWritten = await writePanePrompt(paneA, `Write-Output '${DELIVERED}'`);
    const cleanObserved = await seesNeedle(win, paneA, DELIVERED, ECHO_MS);
    receipt.legs.clean_pane_write = {
      refusal: cleanRefusal, written: cleanWritten === true, body_observed_executing: cleanObserved,
      ok: cleanRefusal === null && cleanWritten === true && cleanObserved,
    };
    log(`[selfcheck] U328 clean write: written=${cleanWritten} observed=${cleanObserved}`);

    // ---- A2: the same pane on a modal screen refuses, and the bytes really do not go out ---------
    const modalTyped = await operatorTypes(win, paneA, `Write-Output '${TRUST_LINE}'\r`);
    const modalOnScreen = modalTyped && await seesNeedle(win, paneA, TRUST_LINE, ECHO_MS);
    const modalRefusal = paneWriteRefusalFor(paneA);
    // the pane's own count of submitted lines, taken immediately before the refused write
    const submitsBefore = await submitCount(win, paneA);
    const modalWritten = await writePanePrompt(paneA, `Write-Output '${WITHHELD}'`);
    // an ABSENCE: the withheld body must never appear on the screen it was refused for
    const withheldSeen = await seesNeedle(win, paneA, WITHHELD, ABSENCE_MS);
    // …and no Enter either. The body is the visible half; the carriage return is the half that
    // answers a numbered menu, and it leaves no needle — only a new prompt.
    const submitsAfter = await submitCount(win, paneA);
    // the window's own positive control: `paneText` answers null when the renderer bridge dies,
    // which would make every absence above vacuously true
    const bridgeAlive = await seesNeedle(win, paneA, BANNER, 2000);
    const straySubmit = !(Number.isInteger(submitsBefore) && Number.isInteger(submitsAfter))
      || submitsAfter !== submitsBefore;
    receipt.legs.modal_pane_refused = {
      modal_screen_via_operator_input: modalOnScreen,
      refusal: modalRefusal,
      terminal_state: modalRefusal ? modalRefusal.terminal_state : null,
      written: modalWritten === true,
      withheld_body_observed: withheldSeen,
      submits_before: submitsBefore,
      submits_after: submitsAfter,
      stray_submit_observed: straySubmit,
      bridge_alive_after_window: bridgeAlive,
      ok: modalOnScreen && !!modalRefusal
        && modalRefusal.terminal_state === "WORKSPACE_TRUST_REQUIRED"
        && modalWritten === false && withheldSeen === false
        && straySubmit === false && bridgeAlive === true,
    };
    log(`[selfcheck] U328 modal write: refused=${modalRefusal && modalRefusal.terminal_state} `
      + `written=${modalWritten} body_seen=${withheldSeen} `
      + `submits ${submitsBefore}→${submitsAfter} bridge_alive=${bridgeAlive}`);

    // ---- B: our own echo may not classify against us --------------------------------------------
    const paneB = await spawnPane(ctx, receipt, "B", paneIds);
    const echoBefore = paneWriteRefusalFor(paneB);
    const echoWritten = await writePanePrompt(
      paneB, `Write-Output '${TRUST_BODY_FRAGMENT} ${ECHO_BODY_DELIVERED}'`);
    const echoObserved = await seesNeedle(win, paneB, ECHO_BODY_DELIVERED, ECHO_MS);
    receipt.legs.own_echo_not_self_refusing = {
      refusal_before: echoBefore, body_contains_modal_text: TRUST_BODY_FRAGMENT,
      written: echoWritten === true, body_observed_executing: echoObserved,
      ok: echoBefore === null && echoWritten === true && echoObserved,
    };
    log(`[selfcheck] U328 own-echo body: written=${echoWritten} observed=${echoObserved}`);

    // ---- C: a pane with no session is UNREADABLE, not clean -------------------------------------
    const absentId = "pane-u328-never-opened";
    const absentRefusal = paneWriteRefusalFor(absentId);
    const absentWritten = await writePanePrompt(absentId, `Write-Output '${WITHHELD}'`);
    receipt.legs.sessionless_pane_unreadable = {
      refusal: absentRefusal,
      terminal_state: absentRefusal ? absentRefusal.terminal_state : null,
      written: absentWritten === true,
      ok: !!absentRefusal && absentRefusal.terminal_state === "PANE_SCREEN_UNREADABLE"
        && absentWritten === false,
    };

    receipt.ok = Object.values(receipt.legs).every((leg) => leg.ok === true);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  }
  // D-LOOP-1: this unit's sessions die in this unit. The launcher's teardown is the backstop, not
  // the plan — a check that leaves a ConPTY for someone else to reap has left an orphan.
  receipt.sessions_killed_in_unit = [];
  for (const id of paneIds) {
    try { killSession(id); receipt.sessions_killed_in_unit.push(id); } catch { /* already terminal */ }
  }
  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] system-pane-write ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runSystemPaneWriteSelfCheck: run, RECEIPT_PATH };
