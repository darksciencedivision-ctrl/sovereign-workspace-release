"use strict";
/**
 * Phase 19 unit 19.4 in-Electron self-check (D-P16-0 binding) — the READINESS WINDOW (U329).
 *
 * WHY IT EXISTS. The headless suite drives `control/worker-readiness.js` with a `RingBuffer` a test
 * pushed strings into, and the mutation harness proves those tests can fail. What neither can show
 * is the binding in `main.js`: that the window this shell actually classifies is the one over the
 * REAL pane buffer of a REAL ConPTY session, in the packaged runtime. D-P16-0 exists because 14A
 * shipped a shell that passed headless tests and failed at first launch.
 *
 * The legs, in the order they run:
 *
 *  A. THE MEASURED DIFFERENCE. A supervised pane prints an authentication line, then a screen's
 *     worth of ordinary output over it. The shell's production window says the pane is CLEAN; a
 *     `buffer.snapshot()` read of the same live buffer — the audited behaviour, computed here purely
 *     for contrast — says AUTH_REQUIRED. Both verdicts are recorded. If the two ever agree, this leg
 *     FAILS: it would mean the scenario did not reproduce and the receipt would be claiming a
 *     difference it did not measure.
 *  B. THE GATE IS NOT WEAKENED. A second pane whose LAST output is a trust modal still classifies
 *     WORKSPACE_TRUST_REQUIRED through the same bounded window — including a modal drawn before this
 *     check started watching, which is the common case at spawn and the case an earlier design of
 *     this window was blind to.
 *  C. EXIT CODE FIRST. `orderedProviderSignal`, in this runtime, on pane B's real screen: an exited
 *     process is decided by its code and its transcript is NOT read (the reader is a thunk, and the
 *     receipt records that it was never called). This is `frontier_provider_recon.py:44-49` restored.
 *  D. FAIL-CLOSED NONCE. The window used to promote a worker to READY answers exactly or not at all:
 *     a fabricated stream position is UNANSWERABLE, and a real mark counts this check's own token
 *     exactly twice — once written, once echoed.
 *  E. A pane with no session is UNANSWERABLE, not an empty screen that classifies clean.
 *
 * F, G, H, I — THE READINESS RUN ITSELF, which the 19.4 checkpoint recorded as owed. Legs A–E drive
 * the production WINDOW and the production ORDERING FUNCTION; they do not drive
 * `createWorkerReadiness.run()`, so the state machine around them — including the U373 remediation
 * the round-1 reviewers forced — was evidenced by the headless suite alone. These four legs run the
 * real state machine in this runtime, over real ConPTY panes, bound to the PRODUCTION U328 write
 * gate (`paneWriteRefusalFor`), the PRODUCTION write path (`writePanePrompt`), the PRODUCTION launch
 * record and the PRODUCTION operational-state writer — the same objects `main.js` hands readiness.
 *
 *  F. THE NEGATIVE CONTROL, END TO END (U373's residual, closed in 19.4-followon). Pane A's
 *     SCROLLBACK mentions an auth failure and its CURRENT screen does not. Until this unit the U328
 *     write gate read the whole 256 KB buffer, refused on that mention, and this healthy connected
 *     worker STALLED with its prompt undeliverable — the audited pin surviving as an honest stall,
 *     which earlier revisions of this leg REQUIRED and recorded as a residual. The gate now reads the
 *     same bounded window everything else does, so the leg inverts: the gate must PERMIT, the prompt
 *     must be delivered, and the run must reach READY. That is OP-13.1's stated reason for
 *     sequencing this work ahead of Path A ("U329 can pin a healthy worker as permanently blocked"),
 *     measured in the packaged runtime rather than argued.
 *  G. A CLEAN PANE IS WRITTEN TO, AND THE RUN REACHES READY on evidence this runtime measured: the
 *     gate permits, the production write path puts the readiness prompt into a real ConPTY, and the
 *     bounded nonce window counts the pane COMPOSING the reply the prompt described — two fragments
 *     joined, a string the prompt does not contain (U385). The previous version counted a token the
 *     prompt spelled out and accepted the second occurrence as an answer; on this host a resize
 *     repaints the screen and re-emits our own line, so this leg went READY on a pane that had said
 *     nothing. It is the only leg the reviewers could not have caught — the run had to be run.
 *  H. A MODAL THAT IS THE CURRENT SCREEN STILL WITHHOLDS THE WRITE, and the bounded window is what
 *     states what is wrong. Pane H's SCROLLBACK holds an auth line while its CURRENT screen is a
 *     trust modal, so the leg fails if EITHER instrument reaches back through the scrollback: the
 *     run must report WORKSPACE_TRUST_REQUIRED with `decided_by: screen_text_bounded_window`, and
 *     `AUTH_REQUIRED` — the buried line — must appear in neither the gate's answer nor the run's.
 *     Until 19.4-followon the two instruments read different regions and this leg turned on their
 *     DISAGREEMENT (the gate said AUTH_REQUIRED off the scrollback); now they read the same bounded
 *     window and the leg turns on both of them being bounded, which is the stronger claim.
 *  I. THE VERDICT HALF (U363). Pane I shows a numbered permission menu — the first of the nine
 *     realistic permission screens the 19.3 gate-validator walked straight through this gate.
 *     `classifyProviderScreen` still returns NULL for it (asserted in the leg, so the leg cannot
 *     quietly start measuring something else), and the write is refused anyway, by the affordance
 *     rule the bounded window made affordable. Zero bytes delivered, and the refusal is reported as
 *     a withheld write rather than as a provider verdict nothing measured (U373's rule, applied to
 *     the new refusal).
 *
 * WHAT IS SIMULATED IN F/G/H/I, said here and in the receipt, and said COMPLETELY — the first version
 * of this paragraph said "the two named SIMULATED" and there were more than two, which is the same
 * class of defect as everything else this unit has been fixing. The check owns: the Sovereign MCP
 * session state (`mcpState`), the provider's tool-call count (`operationCount`), the last-successful
 * MCP operation (`operationState`, which feeds `last_successful_mcp_operation` in every structured
 * failure these legs produce), both deadlines (`mcpTimeoutMs`/`responseDeadlineMs` — short, because
 * a self-check may not wait out production's 120 s/180 s, and leg F's outcome is a function of the
 * withheld deadline), and `now`/`sleep`/`log`. It also SEEDS the pane's launch record, because a
 * self-check pane was never launched through the picker, and those seeded values are literal
 * assignments rather than observed signals — the U337 class, inside the evidence instrument, which
 * is why the receipt now carries them verbatim. Everything else — window, gate, write path, launch
 * record store, operational-state writer — is the shell's own object. The claim is therefore about
 * the state machine, the gate and the window in the packaged runtime, not about a live provider,
 * which is 17B's and 18E's evidence.
 *
 * It starts no model, spends no live exchange, touches no credential, and kills every session in
 * this unit (D-LOOP-1). Every boolean is measured; a leg that cannot be measured fails the check.
 */
const fs = require("fs");
const path = require("path");
const { receiptPath } = require("./receipt-path");
const { sourceIdentity } = require("./voice-conductor-selfcheck");
const { classifyProviderScreen } = require("../control/provider-readiness");
const {
  createWorkerReadiness, orderedProviderSignal, TAIL_LINES, TAIL_BYTES,
} = require("../control/worker-readiness");

const RECEIPT_STAMP = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
const RECEIPT_UNIT = String(process.env.SOW_SELFCHECK_UNIT || "run")
  .replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 40);
const RECEIPT_PATH = receiptPath(
  `PHASE19_4_READINESS_WINDOW_SELFCHECK_${RECEIPT_UNIT}_${RECEIPT_STAMP}.json`);

/** Per-step ceilings; their sum stays under this kind's launcher bound, so a stall FAILS here with
 *  the step that stalled named rather than being killed blind (exit 124 writes no receipt). */
const SUPERVISION_MS = 30000;
const TERM_MS = 20000;
const BANNER_MS = 30000;
const OUTPUT_MS = 30000;

const BANNER = "SOVEREIGN_U329_PANE_READY";
/** Matches `classifyProviderScreen`'s provider-independent authentication rule. */
const AUTH_LINE = "you are not signed in. sign in to continue";
const TRUST_LINE = "do you trust the contents of this project";
/** Leg I's screen: the permission-menu shape the 19.3 gate-validator demonstrated this gate writing
 *  into — the first of its ten screens, and the one the register quotes. `classifyProviderScreen`
 *  knows nothing about it (the leg asserts that on the live pane, so it cannot quietly start
 *  measuring something else) and the affordance rule (`control/modal-affordance.js`) is what refuses
 *  it. Wording chosen against the classifier deliberately: "allow this tool" would have matched its
 *  MCP-permission family, because every pane here prints a banner containing the word SOVEREIGN, and
 *  the leg would then have proved nothing about the new verdict. Three separate lines, because a
 *  single long line wraps in a 65-column pane and a wrap inside "1. Yes" would fail the leg for a
 *  reason that has nothing to do with what it measures. */
const TOOL_MENU_LINES = Object.freeze([
  "Do you want to proceed?", "> 1. Yes", "  2. No",
]);
/** Enough lines to redraw past the window's line bound. Derived from `TAIL_LINES` rather than
 *  written as a literal: it WAS 120 against a bound of 24, the 19.4-followon round-1 review raised
 *  the bound to 80 (a 24-line window is smaller than the 30-row pane this shell spawns), and the
 *  headroom silently fell from 5x to 1.5x. A fixture that stops clearing its own bound stops
 *  building the scenario it is named for — the U367 class, and the round-2 spec-auditor found three
 *  more instances of it in this unit's own tests. Legs A and H both reproduce at this margin. */
const OVERWRITE_LINES = TAIL_LINES + 40;
const OVERWRITE_MARK = "SOVEREIGN_U329_OVERWRITE";
const NONCE = "SOVEREIGN_U329_NONCE";
/** Pane G answers what is submitted to it: it echoes back the readiness TOKEN alone, twice. The
 *  token rather than the whole line, deliberately — a readiness prompt is ~190 characters and wraps
 *  in a real pane, and a wrap landing inside the token would fail this leg for a reason that has
 *  nothing to do with what it measures. Two short lines cannot wrap, so what the nonce window counts
 *  is the pane genuinely answering. */
const ANSWER_MARK = "SOVEREIGN_U329_ANSWER";
/** Pane G plays a provider that OBEYS the readiness instruction (U385): it reads the two fragments
 *  out of the line submitted to it and writes them back JOINED — a string the prompt does not
 *  contain, so no echo of the prompt and no repaint that re-emits its text can produce it (the
 *  residual shape is bounded in `worker-readiness.js`'s header, [[U393]]). It goes out on a line of
 *  its own,
 *  under 50 characters, because this pane is 65 columns wide and a wrap landing inside the answer
 *  would fail the leg for a reason that has nothing to do with what it measures. The previous
 *  version wrote the token twice, which was the shape of the defect: two occurrences of a string
 *  the prompt itself carried, indistinguishable from a screen redrawing our own keystrokes. */
const ECHO_SCRIPT =
  "while ($true) { $l = Read-Host; $h = $null; $t = $null; "
  + "if ($l -match 'SOVEREIGN_READY_[0-9]+_[a-z0-9]+') { $h = $Matches[0] }; "
  + "if ($l -match 'SOVEREIGN_TAIL_[a-z0-9]+') { $t = $Matches[0] }; "
  + `if ($h -and $t) { Write-Output ($h + $t); Write-Output '${ANSWER_MARK}' } }`;

/** What a provider that obeyed the instruction replies — parsed out of the prompt the run actually
 *  delivered, exactly as pane G's script parses it. Deliberately not imported from
 *  `worker-readiness.js`: a check that asked the module what it expects and then counted that would
 *  agree with the module by construction. `null` if the instruction cannot be read, which fails the
 *  leg rather than passing it. */
const ANSWER_RE = new RegExp(
  "the fragment (SOVEREIGN_READY_[0-9]+_[a-z0-9]+) written immediately before "
  + "the fragment (SOVEREIGN_TAIL_[a-z0-9]+)");
const answerTo = (prompt) => {
  const m = ANSWER_RE.exec(String(prompt || ""));
  return m ? `${m[1]}${m[2]}` : null;
};
const occurrences = (haystack, needle) =>
  (typeof haystack === "string" && needle ? haystack.split(needle).length - 1 : null);

/** Readiness deadlines for the run legs. Short, because each is bounded by what it is waiting for:
 *  F and H wait for the gate's refusal to be confirmed across polls (250 ms each), G waits for a
 *  real pane to answer. Their sum stays well under this kind's launcher ceiling. */
const WITHHELD_DEADLINE_MS = 1500;
const ANSWER_DEADLINE_MS = 12000;
const MCP_DEADLINE_MS = 2000;

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

async function hasTerm(win, paneId) {
  return win.webContents.executeJavaScript(
    `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(paneId)})`);
}

/** The pane's RAW buffer, through the shell's own session manager — the audited read, computed only
 *  as the CONTRAST for legs A and F. No SYSTEM→pane decision reads it any more: the readiness path
 *  stopped at 19.4, and the U328 write gate stopped at 19.4-followon ([[U373]]'s residual), which is
 *  what leg F measures. It is NOT unread in this shell, and the absolute that said so was wrong for
 *  one commit: the OPERATOR→pane voice path's positive-evidence guard still reads the whole buffer
 *  (`main.js`'s `paneEmittedAll` → `voice/conductor-write.js` guard 3 → `paneAcceptsTypedText`).
 *  That direction is STRICTER, not looser — it requires evidence that a text input is showing before
 *  the operator's own utterance may be typed — so bounding it is not this unit's fix to make, and
 *  claiming it was already made is the class of defect this unit keeps finding in its own prose
 *  (round-1 spec-auditor caught the first version, round-2 the replacement). */
function wholeBuffer(manager, paneId) {
  try { return manager.registry.get(paneId).buffer.snapshot().toString("utf8"); } catch { return null; }
}

async function spawnPane(ctx, receipt, label, script, paneIds) {
  const paneId = ctx.createPaneWithSession({
    file: "powershell.exe",
    args: ["-NoLogo", "-NoProfile", "-NoExit", "-Command", `Write-Output '${BANNER}'; ${script}`],
    title: `u329-${label}`,
  });
  if (Array.isArray(paneIds)) paneIds.push(paneId);
  const termed = await waitFor(() => hasTerm(ctx.win, paneId), TERM_MS, 200);
  const banner = termed && await waitFor(
    () => String(wholeBuffer(ctx.sessionManager(), paneId) || "").includes(BANNER), BANNER_MS, 200);
  receipt.panes.push({ pane: label, pane_id: paneId, term_created: termed, banner_seen: banner });
  if (!termed) throw new Error(`renderer never created an xterm view for pane ${label}`);
  if (!banner) throw new Error(`pane ${label} never rendered its banner (no legible screen to read)`);
  return paneId;
}

/**
 * THE READINESS RUN, in this runtime, on this pane. Every binding below marked `SIMULATED` is the
 * check's; every other one is the shell's own object. The receipt carries the same list AND the
 * seeded record verbatim — a receipt whose reader cannot tell which parts were measured is the
 * failure mode 19.8 exists for, and a disclosure that undercounts itself is that failure mode
 * wearing a disclosure's clothes (round-2 review, MAJOR-1).
 *
 * Round 3 found that repair had reached the scope note and not the headline sentence a reader reads
 * first, so the two are no longer written twice: `CHECK_OWNED_BINDINGS` is the single list, the
 * sentence counts what it counts, and the seeded record is published as it is actually seeded.
 *
 * The pane is given a launch record first, because `main.js` binds `record` to the real worker
 * launcher and a self-check pane was never launched through the picker. Seeding it is how this leg
 * reaches the production record path rather than a double of it.
 */
// ONE ENTRY PER BINDING, because the sentence above is generated from this list's LENGTH and a list
// that collapses three bindings into one entry makes that sentence undercount itself — which is
// exactly U384's finding, at reduced amplitude, and the round-4 auditor found it here ([[U393]]).
// `operationCount` says what the simulation DOES: the code counts a tool call on prompt DELIVERY, so
// leg G's READY has a measured half (the answer occurrences on the real pane) and a simulated half,
// and a reader of the receipt alone could not previously tell which was which.
const CHECK_OWNED_BINDINGS = Object.freeze([
  "mcpState (the Sovereign MCP session state)",
  "operationCount (SIMULATED: the provider tool-call count, incremented on prompt DELIVERY — no MCP "
    + "server is running here, so the structured half of every promotion is this check's, not a "
    + "provider's; the answer occurrences on the real pane are the measured half)",
  "operationState (it feeds last_successful_mcp_operation in every structured failure)",
  "mcpTimeoutMs", "responseDeadlineMs", "now", "sleep", "log",
]);
const SEEDED_RECORD_FIELDS = Object.freeze({
  state: "running", exitCode: null, nodeAttested: true,
  operationalState: "STARTING", readiness: null, structuredFailure: null,
});
async function driveReadiness(ctx, receipt,
  { leg, paneId, provider, nodeId, mcpConnected, responseDeadlineMs }) {
  const launcher = ctx.workerLauncher();
  const observedProcess = ctx.sessionManager().processIdentity(paneId);
  const seeded = {
    ...SEEDED_RECORD_FIELDS, nodeId,
    pid: observedProcess && observedProcess.pid,
    sessionGeneration: observedProcess && observedProcess.generation,
    supervised: Boolean(observedProcess),
    chrome: { provider, model_slug: `${provider}-selfcheck`, node_state: "STARTING" },
  };
  launcher.updateRecord(paneId, seeded);
  // Published from the object actually seeded, by the function that seeds it, so a future leg
  // cannot add a field the receipt does not disclose. `nodeId` and `chrome` are not inert: chrome's
  // provider and model_slug become the `provider` and `model` of every structured failure these
  // legs produce (control/worker-readiness.js `failure()`), and a receipt that published only the
  // constant fields let a reader take those two for observed (round-3 audit, MAJOR-2). The process
  // pid/generation and supervised verdict above come from SessionManager.processIdentity, not a
  // seeded `true`.
  receipt.seeded_launch_record.per_pane[leg] = seeded;
  const seen = { states: [], prompts: [], operations: 0, logs: [] };
  const readiness = createWorkerReadiness({
    now: () => Date.now(),
    sleep,
    window: ctx.readinessWindow,                                   // PRODUCTION
    record: (id) => launcher.record(id),                           // PRODUCTION
    processIdentity: (id) => ctx.sessionManager().processIdentity(id), // PRODUCTION observation
    setOperationalState: (id, state, patch) => {                   // PRODUCTION
      seen.states.push(state);
      return ctx.setWorkerOperationalState(id, state, patch);
    },
    writeRefusal: (id) => ctx.paneWriteRefusalFor(id),             // PRODUCTION (the U328 gate)
    writePrompt: async (id, prompt) => {                           // PRODUCTION (the gated path)
      const written = await ctx.writePanePrompt(id, prompt);
      // SIMULATED: a real provider would answer this prompt by calling the Sovereign MCP tool it
      // names. Nothing live runs here, so the tool call is counted as made once the prompt is
      // genuinely delivered — the delivery is measured, the call is not.
      if (written) seen.operations += 1;
      seen.prompts.push({ prompt, written });
      return written;
    },
    mcpState: () => ({ state: mcpConnected ? "connected" : "disconnected" }),   // SIMULATED
    operationCount: () => seen.operations,                                      // SIMULATED
    operationState: () => ({ last: null }),                                     // SIMULATED
    mcpTimeoutMs: () => MCP_DEADLINE_MS,                                        // SIMULATED
    responseDeadlineMs: () => responseDeadlineMs,                               // SIMULATED
    log: (m) => { seen.logs.push(m); ctx.log(`[selfcheck] ${m}`); },            // SIMULATED
  });
  const result = await readiness.run(paneId);
  return { result, seen, seeded, record: launcher.record(paneId) };
}

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, readinessWindow, sessionManager,
    killSession, log } = ctx;
  const receipt = {
    check: "phase-19.4.readiness-window",
    unit: process.env.SOW_SELFCHECK_UNIT || null,
    finding: "U329 — in the packaged runtime, the readiness WINDOW, the signal ORDER and the "
      + "readiness RUN behave as the unit claims. The window is the pane's bounded tail through "
      + "RingBuffer.sliceFrom(), never buffer.snapshot(), measured against the audited whole-buffer "
      + "read on the same live pane; orderedProviderSignal consults no screen while a stronger "
      + "signal answers; and createWorkerReadiness.run() — driven here through the PRODUCTION U328 "
      + "write gate, the production write path, the production launch record and the production "
      + "operational-state writer, over real ConPTY panes — reaches READY on a healthy connected "
      + "worker whose SCROLLBACK mentions an auth failure (U373's residual, closed: the gate reads "
      + "the same bounded window and no longer withholds that worker's prompt), still withholds "
      + "every byte from a pane whose CURRENT screen is a modal — including a permission menu the "
      + "provider-state classifier does not recognise (U363's verdict half) — and reports a withheld "
      + "write as a withheld write rather than as a provider verdict. The gate is a DENYLIST, so "
      + "\"refuses a modal\" means one it recognises: three of the ten permission screens the 19.3 "
      + "review demonstrated are still written into, asserted as such in pane-writer.test.js, and "
      + `what it reads is the last ${TAIL_LINES} non-blank lines of the last ${TAIL_BYTES} bytes of `
      + "RAW stream, which is LESS than the current screen on a pane taller than that AND on a "
      + "spawn-default 30-row pane whose repaint costs more than that byte budget — a densely "
      + "coloured full-screen frame measured at 32,596 bytes by the round-2 validator (U395, both "
      + "halves). No live provider runs here "
      + "(live_exchanges: 0), so "
      + `${CHECK_OWNED_BINDINGS.length} bindings are the CHECK's rather than the shell's — `
      + `${CHECK_OWNED_BINDINGS.join("; ")} — and the launch record of every pane that a readiness `
      + "RUN is driven on is SEEDED (legs F/G/H/I; panes A and B are read by legs A–E and never "
      + "given a record). check_owned_bindings, scope_note_readiness_run and seeded_launch_record "
      + "carry the complete list; this sentence is generated from it and counts what it counts.",
    source: sourceIdentity(),
    started: new Date().toISOString(),
    electron_main_pid: process.pid,
    ok: false,
    supervision_ready: false,
    panes: [],
    legs: {},
    scope_note_screen_signal: "the panes here are powershell.exe printing text this check chose, so "
      + "no real provider screen is evidenced (U362 applies unchanged); what is measured is the "
      + "WINDOW and the ORDER, not the classifier's coverage (U363) and not a terminal emulator's "
      + "view of the visible screen (U372)",
    scope_note_readiness_run: "legs F/G/H/I drive the PRODUCTION readiness state machine bound to the "
      + "production window, U328 write gate, write path, launch record store and operational-state "
      + "writer. SIMULATED by this check, completely enumerated: the Sovereign MCP session state "
      + "(mcpState), the provider tool-call count (operationCount), the last successful MCP "
      + "operation (operationState — it feeds last_successful_mcp_operation in every structured "
      + "failure these legs produce), both deadlines (mcpTimeoutMs/responseDeadlineMs, short so a "
      + "self-check does not wait out production's 120 s/180 s — leg F's outcome is a function of "
      + "the withheld deadline), and now/sleep/log. The pane's launch record is SEEDED (values "
      + "under seeded_launch_record, per pane, including the nodeId and the chrome whose provider "
      + "and model_slug become the provider/model of every structured failure below) because a "
      + "self-check pane is not a picker launch. The pid, generation and supervised verdict come "
      + "from this runtime's SessionManager processIdentity observation; the remaining seeded "
      + "values are assignments, not observed signals. The seeded records are left in this "
      + "throwaway process's launcher registry "
      + "when the check exits",
    scope_note_leg_d: "leg D injects its keystroke through the renderer's OPERATOR input channel "
      + "(window.sovereign.input), not the gated system→pane path legs F/G/H use. It is the one "
      + "write in a check partly about the write path that does not use the write path, so it is "
      + "said here rather than left for a reader to notice: no gate is weakened or bypassed by it "
      + "(the U328 gate governs SYSTEM writes; an operator keystroke is the operator's own "
      + "authority, invariant 1), the pane is a check-spawned powershell.exe killed in this unit, "
      + "and the same channel is used by two other in-Electron self-checks for the same reason — "
      + "there is no operator at a keyboard inside an automated run. What leg D measures is the "
      + "WINDOW's exactness (a fabricated position is unanswerable, a real mark counts what "
      + "arrived), which is independent of how the bytes got there (U386(e))",
    check_owned_bindings: CHECK_OWNED_BINDINGS,
    seeded_launch_record: { constant_fields: SEEDED_RECORD_FIELDS, per_pane: {} },
    live_exchanges: 0,
    error: null,
  };
  const paneIds = [];
  try {
    if (!readinessWindow || typeof readinessWindow.read !== "function"
      || typeof readinessWindow.since !== "function") {
      throw new Error("the runtime did not expose its production readiness window");
    }
    receipt.supervision_ready = await waitFor(isSupervised, SUPERVISION_MS, 250);
    if (!receipt.supervision_ready) throw new Error("supervision never became READY");
    if (typeof createPaneWithSession !== "function") throw new Error("no supervised pane path");
    const manager = sessionManager();

    // ---- A: the buried overlay — bounded window vs the whole buffer, on the SAME live pane -------
    // The pane ends in the echo script because leg F drives a full readiness run on it: a worker
    // that is healthy has to be able to ANSWER, and a pane that cannot is a leg that proves the
    // negative control by timing out instead of by passing.
    const paneA = await spawnPane(ctx, receipt, "A",
      `Write-Output '${AUTH_LINE}'; 1..${OVERWRITE_LINES} | ForEach-Object `
      + `{ Write-Output "${OVERWRITE_MARK} $_" }; ${ECHO_SCRIPT}`, paneIds);
    const drawn = await waitFor(() => {
      const text = wholeBuffer(manager, paneA);
      return typeof text === "string" && text.includes(`${OVERWRITE_MARK} ${OVERWRITE_LINES}`);
    }, OUTPUT_MS, 200);
    const boundedA = readinessWindow.read(paneA);
    const wholeA = wholeBuffer(manager, paneA);
    const boundedVerdict = boundedA.answerable ? classifyProviderScreen("grok_build", boundedA.text) : null;
    const wholeVerdict = typeof wholeA === "string" ? classifyProviderScreen("grok_build", wholeA) : null;
    // U386(d): `boundedA.bytes` is a BYTE count off a Buffer; `wholeA.length` was a UTF-16 code-unit
    // count off a string. The panes here are ASCII so the two coincided and the reported bound was
    // right — but a field named `_bytes` that is not bytes must not be what a mechanism claim rests
    // on, so the whole buffer is now measured in the same unit and the character count is published
    // separately rather than silently standing in for it.
    const wholeBytesA = typeof wholeA === "string" ? Buffer.byteLength(wholeA, "utf8") : null;
    receipt.legs.buried_overlay_is_not_current_state = {
      output_drawn: drawn,
      bounded_window_answerable: boundedA.answerable === true,
      bounded_window_bytes: boundedA.bytes ?? null,
      whole_buffer_bytes: wholeBytesA,
      whole_buffer_chars_utf16: typeof wholeA === "string" ? wholeA.length : null,
      bounded_verdict: boundedVerdict ? boundedVerdict.terminal_state : null,
      whole_buffer_verdict: wholeVerdict ? wholeVerdict.terminal_state : null,
      // WHICH bound did the work. A pane that never emitted a tail's worth of bytes leaves the BYTE
      // bound untriggered, and a receipt reporting only "bounded ≠ whole" would read as though both
      // bounds had been exercised. Say it, so the number above is not mistaken for the mechanism.
      bound_that_applied: wholeBytesA === null
        ? null : (boundedA.bytes < wholeBytesA ? "byte_and_line" : "line_only"),
      ok: drawn === true && boundedA.answerable === true && boundedVerdict === null
        && wholeVerdict !== null && wholeVerdict.terminal_state === "AUTH_REQUIRED",
    };
    log(`[selfcheck] U329 buried overlay: bounded=${boundedVerdict && boundedVerdict.terminal_state} `
      + `whole=${wholeVerdict && wholeVerdict.terminal_state} `
      + `bytes ${boundedA.bytes}/${typeof wholeA === "string" ? wholeA.length : "?"}`);

    // ---- B: a modal that IS the current screen still classifies ----------------------------------
    const paneB = await spawnPane(ctx, receipt, "B", `Write-Output '${TRUST_LINE}'`, paneIds);
    const modalDrawn = await waitFor(() => {
      const w = readinessWindow.read(paneB);
      return w.answerable === true && /do you trust/i.test(w.text);
    }, OUTPUT_MS, 200);
    const boundedB = readinessWindow.read(paneB);
    const verdictB = boundedB.answerable ? classifyProviderScreen("grok_build", boundedB.text) : null;
    receipt.legs.current_modal_still_classifies = {
      modal_drawn: modalDrawn,
      terminal_state: verdictB ? verdictB.terminal_state : null,
      ok: modalDrawn === true && !!verdictB && verdictB.terminal_state === "WORKSPACE_TRUST_REQUIRED",
    };

    // ---- C: exit code first, and the transcript is not read --------------------------------------
    let screenReads = 0;
    const exitedSignal = orderedProviderSignal({
      provider: "grok_build", processState: "exited", exitCode: 0, mcpConnected: false,
      window: () => { screenReads += 1; return readinessWindow.read(paneB); },
    });
    const runningSignal = orderedProviderSignal({
      provider: "grok_build", processState: "running", mcpConnected: true,
      window: () => { screenReads += 1; return readinessWindow.read(paneB); },
    });
    receipt.legs.exit_code_and_structured_signals_first = {
      exited_source: exitedSignal.source, exited_exit_code: exitedSignal.exit_code,
      connected_source: runningSignal.source,
      screen_reads_while_answerable_by_stronger_signals: screenReads,
      ok: exitedSignal.source === "process_exit" && exitedSignal.exit_code === 0
        && exitedSignal.setup === null && exitedSignal.screen_consulted === false
        && runningSignal.source === "mcp_connection" && runningSignal.screen_consulted === false
        && screenReads === 0,
    };

    // ---- D: the nonce window is exact or it is nothing --------------------------------------------
    const mark = readinessWindow.mark(paneB);
    const fabricated = readinessWindow.since(paneB, mark + 1_000_000);
    const negative = readinessWindow.since(paneB, -1);
    await win.webContents.executeJavaScript(
      `window.sovereign.input(${JSON.stringify(paneB)}, ${JSON.stringify(`Write-Output '${NONCE}'\r`)})`);
    const counted = await waitFor(() => {
      const w = readinessWindow.since(paneB, mark);
      return w.answerable === true && w.text.split(NONCE).length - 1 >= 2;   // typed + printed
    }, OUTPUT_MS, 200);
    const nonceWindow = readinessWindow.since(paneB, mark);
    receipt.legs.nonce_window_is_exact_or_nothing = {
      fabricated_position_answerable: fabricated.answerable === true,
      negative_position_answerable: negative.answerable === true,
      nonce_occurrences: nonceWindow.answerable ? nonceWindow.text.split(NONCE).length - 1 : null,
      ok: fabricated.answerable === false && negative.answerable === false && counted === true,
    };

    // ---- E: a pane with no session is unanswerable, not clean -------------------------------------
    const absent = readinessWindow.read("pane-u329-never-opened");
    receipt.legs.sessionless_pane_unanswerable = {
      answerable: absent.answerable === true, reason: absent.reason || null,
      classified: absent.answerable === true
        ? Boolean(classifyProviderScreen("grok_build", absent.text)) : null,
      ok: absent.answerable === false,
    };

    // ---- F: the readiness RUN, and the gate that may only say "not yet" (U373) -------------------
    if (typeof ctx.setWorkerOperationalState !== "function" || typeof ctx.workerLauncher !== "function"
      || typeof ctx.paneWriteRefusalFor !== "function" || typeof ctx.writePanePrompt !== "function") {
      throw new Error("the runtime did not expose the production readiness bindings");
    }
    // The scenario must reproduce before the run is worth anything: the whole-buffer read of this
    // pane classifies AUTH_REQUIRED (leg A measured it), and the bounded one does not — so a gate
    // that PERMITS here is a gate reading the screen, and a gate that refuses is one reading the
    // transcript. The measurement is leg A's; the consequence is this leg's.
    const gateOnA = ctx.paneWriteRefusalFor(paneA);
    const runF = await driveReadiness(ctx, receipt, {
      leg: "F", paneId: paneA, provider: "grok_build", nodeId: "node-u329-f",
      mcpConnected: true, responseDeadlineMs: ANSWER_DEADLINE_MS,
    });
    const failureF = runF.result.failure || {};
    const deliveredF = runF.seen.prompts.filter((p) => p.written).length;
    receipt.legs.mention_in_scrollback_does_not_withhold_a_healthy_workers_prompt = {
      gate_refusal_state: gateOnA ? gateOnA.state : null,
      whole_buffer_verdict_on_this_pane: wholeVerdict ? wholeVerdict.terminal_state : null,
      run_state: runF.result.state,
      ready: runF.result.ready === true,
      stage: failureF.stage || null,
      decided_by: failureF.decided_by || null,
      prompts_delivered: deliveredF,
      operational_states: runF.seen.states,
      // grok_build owes TWO readiness turns; a run that delivered one and promoted anyway would be a
      // different defect, so the count is part of the verdict rather than a note beside it.
      readiness_responses: runF.result.readiness ? runF.result.readiness.readiness_responses : null,
      ok: gateOnA === null
        && !!wholeVerdict && wholeVerdict.terminal_state === "AUTH_REQUIRED"
        && runF.result.ready === true && runF.result.state === "READY"
        && deliveredF === 2
        && runF.result.readiness && runF.result.readiness.readiness_responses === 2,
    };
    log(`[selfcheck] U329 run F: gate=${gateOnA && gateOnA.state} state=${runF.result.state} `
      + `delivered=${deliveredF}`);

    // ---- G: a clean pane is written to, and the run reaches READY on a real answer ----------------
    const paneG = await spawnPane(ctx, receipt, "G", ECHO_SCRIPT, paneIds);
    const runG = await driveReadiness(ctx, receipt, {
      leg: "G", paneId: paneG, provider: "claude_code", nodeId: "node-u329-g",
      mcpConnected: true, responseDeadlineMs: ANSWER_DEADLINE_MS,
    });
    const nonceG = readinessWindow.since(paneG, runG.record.readiness
      && Number.isInteger(runG.record.readiness.window_mark) ? runG.record.readiness.window_mark : 0);
    // U385, measured rather than asserted: the reply the run counts is composed from the prompt's
    // two fragments and appears NOWHERE in the prompt, so an occurrence of it is this pane speaking
    // — excepting the one repaint shape bounded in `worker-readiness.js`'s header ([[U393]]), which
    // no run here has produced.
    // The head fragment's count is recorded beside it precisely because ConPTY repaints — on this
    // host a resize (`ESC[8;7;65t`) re-emits our own line, which is how the previous scheme reached
    // READY on a silent pane. Whatever that number turns out to be, it is not the answer count.
    const promptG = (runG.seen.prompts.find((p) => p.written) || {}).prompt || null;
    const expectedG = answerTo(promptG);
    const headG = expectedG && ANSWER_RE.exec(promptG) ? ANSWER_RE.exec(promptG)[1] : null;
    const textG = nonceG.answerable ? nonceG.text : null;
    receipt.legs.clean_pane_is_written_to_and_reaches_ready = {
      run_state: runG.result.state,
      ready: runG.result.ready === true,
      prompts_delivered: runG.seen.prompts.filter((p) => p.written).length,
      expected_answer_absent_from_the_prompt: expectedG ? !promptG.includes(expectedG) : null,
      answer_occurrences_on_the_real_pane: occurrences(textG, expectedG),
      prompt_echo_occurrences_on_the_real_pane: occurrences(textG, headG),
      answer_marks_on_the_real_pane: occurrences(textG, ANSWER_MARK),
      readiness_responses: runG.result.readiness ? runG.result.readiness.readiness_responses : null,
      operational_states: runG.seen.states,
      ok: runG.result.ready === true && runG.result.state === "READY"
        && runG.seen.prompts.filter((p) => p.written).length === 1
        && nonceG.answerable === true && expectedG !== null
        && !promptG.includes(expectedG)
        && occurrences(textG, expectedG) >= 1 && occurrences(textG, ANSWER_MARK) >= 1,
    };
    log(`[selfcheck] U329 run G: state=${runG.result.state} `
      + `answers=${receipt.legs.clean_pane_is_written_to_and_reaches_ready.answer_occurrences_on_the_real_pane} `
      + `echoes=${receipt.legs.clean_pane_is_written_to_and_reaches_ready.prompt_echo_occurrences_on_the_real_pane}`);

    // ---- H: a modal that IS the current screen withholds the write, and the window says why ------
    // BOTH instruments must be bounded for this leg to pass: the auth line is buried in the
    // scrollback and the trust modal is what the pane is showing, so a gate or a window that reaches
    // back through the transcript reports AUTH_REQUIRED and reddens the leg.
    const paneH = await spawnPane(ctx, receipt, "H",
      `Write-Output '${AUTH_LINE}'; 1..${OVERWRITE_LINES} | ForEach-Object `
      + `{ Write-Output "${OVERWRITE_MARK} $_" }; Write-Output '${TRUST_LINE}'`, paneIds);
    const modalIsCurrent = await waitFor(() => {
      const w = readinessWindow.read(paneH);
      return w.answerable === true && /do you trust/i.test(w.text) && !/sign in to continue/i.test(w.text);
    }, OUTPUT_MS, 200);
    const gateOnH = ctx.paneWriteRefusalFor(paneH);
    const runH = await driveReadiness(ctx, receipt, {
      leg: "H", paneId: paneH, provider: "claude_code", nodeId: "node-u329-h",
      mcpConnected: true, responseDeadlineMs: WITHHELD_DEADLINE_MS,
    });
    const failureH = runH.result.failure || {};
    receipt.legs.bounded_window_speaks_while_the_write_is_withheld = {
      scenario_reproduced: modalIsCurrent,
      gate_refusal_state: gateOnH ? gateOnH.state : null,
      run_state: runH.result.state,
      decided_by: failureH.decided_by || null,
      provider_terminal_state: failureH.provider_terminal_state || null,
      prompts_delivered: runH.seen.prompts.filter((p) => p.written).length,
      // The buried line, named so the leg's claim is checkable from the receipt alone: neither
      // instrument may report the auth text sitting 120 lines up this pane's scrollback.
      buried_auth_state_reported: (gateOnH && gateOnH.state === "AUTH_REQUIRED")
        || failureH.provider_terminal_state === "AUTH_REQUIRED",
      ok: modalIsCurrent === true && !!gateOnH && gateOnH.state === "WORKSPACE_TRUST_REQUIRED"
        && runH.result.ready === false && runH.result.state === "WORKSPACE_TRUST_REQUIRED"
        && failureH.decided_by === "screen_text_bounded_window"
        && failureH.provider_terminal_state !== "AUTH_REQUIRED"
        && runH.seen.prompts.filter((p) => p.written).length === 0,
    };
    log(`[selfcheck] U329 run H: state=${runH.result.state} decided_by=${failureH.decided_by}`);

    // ---- I: U363's verdict half — a permission screen the CLASSIFIER does not know still refuses --
    const paneI = await spawnPane(ctx, receipt, "I",
      `Write-Output '${TOOL_MENU_LINES[0]}'; Write-Output '${TOOL_MENU_LINES[1]}'; `
      + `Write-Output '${TOOL_MENU_LINES[2]}'`, paneIds);
    const menuIsCurrent = await waitFor(() => {
      const w = readinessWindow.read(paneI);
      return w.answerable === true && /do you want to proceed/i.test(w.text);
    }, OUTPUT_MS, 200);
    const windowI = readinessWindow.read(paneI);
    // The disagreement this leg turns on, measured on the live pane rather than assumed: the
    // provider-state classifier says NOTHING about this screen. If it ever learns the shape, this
    // leg starts measuring something else — so it fails rather than quietly changing meaning.
    const classifierI = windowI.answerable
      ? classifyProviderScreen("claude_code", windowI.text) : null;
    const gateOnI = ctx.paneWriteRefusalFor(paneI);
    const runI = await driveReadiness(ctx, receipt, {
      leg: "I", paneId: paneI, provider: "claude_code", nodeId: "node-u329-i",
      mcpConnected: true, responseDeadlineMs: WITHHELD_DEADLINE_MS,
    });
    const failureI = runI.result.failure || {};
    receipt.legs.unrecognised_permission_menu_is_refused = {
      scenario_reproduced: menuIsCurrent,
      classifier_verdict: classifierI ? classifierI.terminal_state : null,
      gate_refusal_terminal_state: gateOnI ? gateOnI.terminal_state : null,
      run_state: runI.result.state,
      stage: failureI.stage || null,
      decided_by: failureI.decided_by || null,
      write_withheld_terminal_state: failureI.write_withheld
        ? failureI.write_withheld.terminal_state : null,
      prompts_delivered: runI.seen.prompts.filter((p) => p.written).length,
      ok: menuIsCurrent === true && classifierI === null
        && !!gateOnI && gateOnI.terminal_state === "PANE_AWAITING_OPERATOR_DECISION"
        && runI.result.ready === false && runI.result.state === "STALLED"
        && failureI.stage === "readiness_prompt_withheld"
        && failureI.decided_by === "write_gate_withheld"
        && runI.seen.prompts.filter((p) => p.written).length === 0,
    };
    log(`[selfcheck] U329 run I: classifier=${classifierI} gate=${gateOnI && gateOnI.terminal_state} `
      + `state=${runI.result.state}`);

    receipt.ok = Object.values(receipt.legs).every((leg) => leg.ok === true);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  }
  // D-LOOP-1: this unit's sessions die in this unit.
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
  log(`[selfcheck] readiness-window ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runReadinessWindowSelfCheck: run, RECEIPT_PATH };
