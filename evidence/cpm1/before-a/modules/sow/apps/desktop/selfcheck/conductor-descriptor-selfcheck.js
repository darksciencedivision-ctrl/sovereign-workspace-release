"use strict";
/**
 * Phase 19 unit 19.6 in-Electron self-check (D-P16-0 binding) — THE DESCRIPTOR, not the name.
 *
 * WHY IT EXISTS. The audited shell failed conductor readiness unless the descriptor carried
 * `openai_codex_cli`/`gpt-5.6-sol` ([[U331]]), and three further runtime decisions were inline
 * vendor comparisons ([[U386]](c), [[U393]] MINOR-1). The headless suite now drives the modules
 * that replace them. What it cannot show is the binding in the packaged runtime: that THIS shell,
 * launched on THIS host, admits the descriptor it actually resolved, and that the write path and
 * the classifier consult declared traits over a real ConPTY. D-P16-0 exists because 14A shipped a
 * shell that passed headless tests and failed at first launch.
 *
 * The legs, in the order they run:
 *
 *  A. THE HOST'S OWN DESCRIPTOR IS ADMITTED. `conductorDescriptorOf()` — the descriptor this shell
 *     sourced from the Python registry over the conductor feed, whatever it is on this host — is
 *     put through the production `conductorAdmission`. It must be ADMITTED, and the receipt records
 *     the provider, the model and the `selection_source` verbatim. On a clone with no live-operation
 *     switch that descriptor is `claude_code`/`fable-5` with `recorded_default_selection`, which is
 *     the exact case the audited shell failed permanently with a message that read like a config
 *     error. If the shell resolved no descriptor at all, the leg records that and does not pass:
 *     an absent descriptor is a real finding, not a skip.
 *  B. THE READINESS LAYER ADMITS DECLARED CONDUCTOR DESCRIPTOR SHAPES. Five descriptors — one per
 *     shipped provider, plus a local one — are admitted by the same production module in
 *     this runtime; under the pin exactly one of the five could ever have been ready.
 *     WHAT THIS LEG DOES NOT SAY, because the first version of it did (gate-validator MAJOR-1,
 *     19.6): it does NOT say conductor succession onto those five backends is REACHABLE. Two layers
 *     upstream bound the set and neither is this one — `control_plane/conductor/registry.py` mints
 *     only its registered pairs (codex/gpt-5.6-sol, claude/fable-5, claude/opus-4.8), and
 *     `conductor/launch-source.js` refuses a ticket whose provider has no verified containment
 *     profile, which today is every provider except those two. That refusal is a fail-closed
 *     containment rule (invariant 29), not a vendor pin, and removing it would admit an unverified
 *     permission boundary. The claim this leg supports is exactly: the readiness layer no longer
 *     refuses on the name.
 *  C. FAIL CLOSED, STILL. No descriptor, no provider, no model, an unregistered one and a
 *     not-conductor-capable one are each refused with `FAILED`, and no refusal reason names a
 *     vendor — a refusal that names a vendor is the pin returning as a message.
 *  D. THE CLASSIFIER, ON A REAL PANE. One supervised pane prints Grok's usage-limit line. Read
 *     through the shell's PRODUCTION bounded window: classified `USAGE_LIMIT` for `grok_build`, and
 *     NULL for a provider this build has never declared — the scoped rule fires for its provider and
 *     leaks to no other. The same pane's universal workspace-trust line classifies for BOTH, because
 *     authentication and trust are states of the governed session, not of a vendor's TUI.
 *  E. THE SUBMIT KEY, MEASURED IN BYTES HANDED TO A REAL ConPTY. Two panes, one prompt each,
 *     through `createPaneWriter` bound to this shell's real session manager and real bounded
 *     window: the pane whose provider declares `submit_confirm_enter` is handed TWO carriage
 *     returns (the confirm Enter and the submit), the pane whose provider is undeclared is handed
 *     ONE — recorded at the boundary where the writer calls the session manager, and only when the
 *     manager ACCEPTED the write. Each pane's body is separately observed EXECUTING, so the bytes
 *     are shown to have reached a live shell and not merely a function. The pane-side prompt count
 *     is recorded as an observation and is deliberately NOT the criterion: across runs of this
 *     check it read 0, 1 and 2 for the same single submitted line, because a repaint redraws a
 *     prompt and a slow render hides one, and a leg that turned on that number would be measuring
 *     the renderer's timing.
 *
 * WHAT IS CHECK-OWNED, said here and in the receipt. Leg E builds its own `createPaneWriter` with a
 * check-owned `providerFor` (the shell's real resolver answers from pane CHROME, and a self-check
 * pane was never launched through the picker, so it has none) and a check-owned logger. Everything
 * else in that leg is the shell's: the bounded window, the modal gate, the session manager's write.
 * Leg D's `provider` argument is likewise the check's — the production resolver is exercised for
 * what it answers on these panes and the answer is recorded, not asserted, because a chromeless pane
 * has no provider to resolve. Legs A–C use the production module and the shell's real descriptor.
 *
 * It starts no model, spends no live exchange, touches no credential, and kills every session it
 * creates inside this unit (D-LOOP-1). Every boolean is measured; a leg that cannot be measured
 * fails the check.
 */
const fs = require("fs");
const path = require("path");
const { receiptPath } = require("./receipt-path");
const { sourceIdentity } = require("./voice-conductor-selfcheck");
const { conductorAdmission } = require("../control/conductor-admission");
const { classifyProviderScreen } = require("../control/provider-readiness");
const { traitsFor, declaredProviderIds } = require("../control/provider-traits");
const { createPaneWriter, paneScreenFromWindow } = require("../control/pane-writer");

const RECEIPT_STAMP = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
const RECEIPT_UNIT = String(process.env.SOW_SELFCHECK_UNIT || "run")
  .replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 40);
const RECEIPT_PATH = receiptPath(
  `PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_${RECEIPT_UNIT}_${RECEIPT_STAMP}.json`);

/** Per-step ceilings; their sum stays under this kind's launcher bound, so a stall FAILS here with
 *  the step that stalled named rather than being killed blind (exit 124 writes no receipt). */
const SUPERVISION_MS = 30000;
const TERM_MS = 20000;
const BANNER_MS = 30000;
const OUTPUT_MS = 30000;

const BANNER = "SOVEREIGN_U331_PANE_READY";
const PROMPT_TOKEN = "SOVEREIGN_U331_PROMPT>";
/** Grok's declared usage-limit rule, and NOTHING a universal rule or a modal affordance matches. */
const GROK_LIMIT_LINE = "you have exceeded your usage limit, try again later";
/** A universal rule: not a vendor's TUI but a state of the governed session. */
const TRUST_LINE = "do you trust the contents of this project";
/** A provider this build has never declared. Deliberately not a real product: the point is what a
 *  shell does with a provider it has no knowledge of. */
const UNDECLARED = "selfcheck_undeclared_cli";
/** The declared provider whose trait makes it submit twice. Read from the table rather than
 *  written here, so this leg cannot drift from what the runtime declares. */
const CONFIRMING = declaredProviderIds().find((id) => traitsFor(id).submit_confirm_enter) || null;

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

/** How many lines this pane has submitted, by its own prompt token. `null` when the screen cannot
 *  be read at all — never 0, which would read as "no submissions" (fail closed on ambiguity). */
async function submitCount(win, paneId) {
  const text = await paneText(win, paneId);
  if (typeof text !== "string") return null;
  return text.split(PROMPT_TOKEN).length - 1;
}

async function hasTerm(win, paneId) {
  return win.webContents.executeJavaScript(
    `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(paneId)})`);
}

async function spawnPane(ctx, receipt, label, paneIds) {
  const paneId = ctx.createPaneWithSession({
    file: "powershell.exe",
    args: ["-NoLogo", "-NoProfile", "-NoExit", "-Command",
      `function prompt { '${PROMPT_TOKEN} ' }; Write-Output '${BANNER}'`],
    title: `u331-${label}`,
  });
  if (Array.isArray(paneIds)) paneIds.push(paneId);
  const termed = await waitFor(async () => hasTerm(ctx.win, paneId), TERM_MS, 200);
  const banner = termed && await seesNeedle(ctx.win, paneId, BANNER, BANNER_MS);
  receipt.panes.push({ pane: label, pane_id: paneId, term_created: termed, banner_seen: banner });
  if (!termed) throw new Error(`renderer never created an xterm view for pane ${label}`);
  if (!banner) throw new Error(`pane ${label} never rendered its banner (no legible screen to read)`);
  return paneId;
}

/** The OPERATOR's input bridge — used to paint a screen, never the system write path under test. */
async function operatorTypes(win, paneId, data) {
  try {
    await win.webContents.executeJavaScript(
      `window.sovereign.input(${JSON.stringify(paneId)}, ${JSON.stringify(data)})`);
    return true;
  } catch { return false; }
}

const vendorish = ["codex", "openai", "gpt-5", "claude", "fable", "anthropic", "grok", "gemini",
  "antigravity", "ollama"];

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, conductorDescriptorOf, paneProviderFor,
    readinessWindow, sessionManager, killSession, log } = ctx;
  const receipt = {
    check: "phase-19.6.conductor-descriptor",
    unit: process.env.SOW_SELFCHECK_UNIT || null,
    finding: "U331/U386(c)/U393 MINOR-1 — in the packaged runtime, conductor readiness admits the "
      + "descriptor THIS shell resolved (whatever provider that is) and refuses only on descriptor "
      + "properties; the classifier applies universal rules to every provider and a scoped rule to "
      + "its own; and the submit-key behaviour is read from declared traits, measured in bytes on a "
      + "real ConPTY. It evidences the DECISION PATHS, not any live provider: no model is started "
      + "and no live exchange is spent.",
    source: sourceIdentity(),
    started: new Date().toISOString(),
    electron_main_pid: process.pid,
    ok: false,
    supervision_ready: false,
    declared_providers: declaredProviderIds(),
    panes: [],
    legs: {},
    // Corrected at 19.6 round 1 (gate-validator MEDIUM-4): the first version claimed leg E records
    // what the production resolver answers on its panes — it does not, leg D records that, once —
    // and it omitted the two millisecond overrides, which matter because U364's echo-settle bound is
    // timing-sensitive.
    check_owned_bindings: [
      "leg E's providerFor (a self-check pane has no chrome, so the production resolver has "
      + "nothing to answer from; what the production resolver answers is recorded in leg D, for "
      + "leg D's pane, as production_resolver_answered)",
      "leg E's pasteSettleMs (200 ms) and submitConfirmMs (200 ms), substituted for production's "
      + "PROVIDER_PASTE_SETTLE_MS / CODEX_SUBMIT_CONFIRM_MS so the check does not sit out the real "
      + "settle windows — U364's bound is timing-sensitive and this leg does not measure it",
      "leg E's conductorTarget and workerPaneFor, both () => null: writePrompt does not consult "
      + "them, so they are inert here, but they are check-owned inputs to a production factory",
      "leg E's log sink",
      "leg D's provider argument (the classifier takes a provider id; these panes have none)",
      "the pane programs themselves — powershell.exe printing text this check chose, so no real "
      + "provider screen is evidenced here (U362)",
    ],
    live_exchanges_is_a_literal: "this check makes no provider call at all, so the zero below is "
      + "asserted by construction rather than counted from a spend ledger",
    live_exchanges: 0,
    error: null,
  };
  const paneIds = [];
  try {
    receipt.supervision_ready = await waitFor(isSupervised, SUPERVISION_MS, 250);
    if (!receipt.supervision_ready) throw new Error("supervision never became READY");
    if (typeof createPaneWithSession !== "function") throw new Error("no supervised pane path");
    if (typeof conductorDescriptorOf !== "function") {
      throw new Error("the runtime did not expose the conductor descriptor it resolved");
    }

    // ---- A: this host's own descriptor, through the production admission ------------------------
    const hostDescriptor = conductorDescriptorOf();
    const hostVerdict = conductorAdmission(hostDescriptor);
    receipt.legs.host_descriptor_admitted = {
      descriptor_present: !!hostDescriptor,
      provider_id: hostVerdict.ok ? hostVerdict.provider_id : null,
      model_id: hostVerdict.ok ? hostVerdict.model_id : null,
      selection_source: hostVerdict.ok ? hostVerdict.selection_source : null,
      readiness_turns: hostVerdict.ok ? hostVerdict.readiness_turns : null,
      decided_by: hostVerdict.ok ? hostVerdict.decided_by : null,
      refusal_reason: hostVerdict.ok ? null : hostVerdict.reason,
      ok: hostVerdict.ok === true,
    };
    log(`[selfcheck] U331 host descriptor: ${JSON.stringify(receipt.legs.host_descriptor_admitted)}`);

    // ---- B: readiness consumes declared descriptor capability, independent of provider name -----
    const successionCandidates = [
      { provider_id: "claude_code", model_id: "fable-5" },
      { provider_id: "openai_codex_cli", model_id: "gpt-5.6-sol" },
      { provider_id: "grok_build", model_id: "grok-code" },
      { provider_id: "google_antigravity", model_id: "gemini-3-pro" },
      { provider_id: "ollama_local", model_id: "qwen3:8b" },
    ].map((d) => {
      const v = conductorAdmission({ role: "conductor", registered: true,
        conductor_capable: true, readiness_turns: d.provider_id === "grok_build" ? 2 : 1, ...d });
      return { ...d, admitted: v.ok === true, readiness_turns: v.ok ? v.readiness_turns : null,
        reason: v.ok ? null : v.reason };
    });
    receipt.legs.readiness_admits_declared_descriptor_shapes = {
      candidates: successionCandidates,
      admitted_count: successionCandidates.filter((c) => c.admitted).length,
      scope: "READINESS ADMISSION ONLY. This leg does not establish that a conductor can be "
        + "LAUNCHED on these five backends: control_plane/conductor/registry.py mints only its "
        + "registered pairs, and conductor/launch-source.js verifies the boundary profile carried "
        + "by a ticket (a fail-closed containment rule, invariant 29). Phase 15D succession is "
        + "bounded by those layers, not by this one.",
      ok: successionCandidates.every((c) => c.admitted),
    };

    // ---- C: fail closed, and no refusal names a vendor ------------------------------------------
    const base = { role: "conductor", provider_id: "claude_code", model_id: "fable-5" };
    const refusals = [
      { case: "no descriptor", verdict: conductorAdmission(null) },
      { case: "no provider", verdict: conductorAdmission({ ...base, provider_id: "" }) },
      { case: "no model", verdict: conductorAdmission({ ...base, model_id: "" }) },
      { case: "unregistered", verdict: conductorAdmission({ ...base, registered: false }) },
      { case: "not conductor-capable",
        verdict: conductorAdmission({ ...base, conductor_capable: false }) },
      { case: "another role", verdict: conductorAdmission({ ...base, role: "worker" }) },
    ].map((r) => ({
      case: r.case, ok: r.verdict.ok === true, state: r.verdict.state || null,
      reason: r.verdict.reason || null,
      names_a_vendor: typeof r.verdict.reason === "string"
        && vendorish.some((v) => r.verdict.reason.toLowerCase().includes(v)),
    }));
    receipt.legs.fail_closed_without_naming_a_vendor = {
      refusals,
      ok: refusals.every((r) => r.ok === false && r.state === "FAILED" && !r.names_a_vendor),
    };

    // ---- D: the classifier over the PRODUCTION bounded window of a real pane --------------------
    const paneD = await spawnPane(ctx, receipt, "D", paneIds);
    const limitPainted = await operatorTypes(win, paneD, `Write-Output '${GROK_LIMIT_LINE}'\r`)
      && await seesNeedle(win, paneD, GROK_LIMIT_LINE, OUTPUT_MS);
    const limitWindow = readinessWindow.read(paneD);
    const limitText = limitWindow && limitWindow.answerable ? limitWindow.text : null;
    const scopedForGrok = limitText === null ? null : classifyProviderScreen("grok_build", limitText);
    const scopedForOther = limitText === null ? null : classifyProviderScreen(UNDECLARED, limitText);
    const trustPainted = await operatorTypes(win, paneD, `Write-Output '${TRUST_LINE}'\r`)
      && await seesNeedle(win, paneD, TRUST_LINE, OUTPUT_MS);
    const trustWindow = readinessWindow.read(paneD);
    const trustText = trustWindow && trustWindow.answerable ? trustWindow.text : null;
    const universalForOther = trustText === null ? null : classifyProviderScreen(UNDECLARED, trustText);
    const universalForGrok = trustText === null ? null : classifyProviderScreen("grok_build", trustText);
    receipt.legs.scoped_rule_does_not_leak = {
      window_readable: limitText !== null && trustText !== null,
      limit_line_painted: limitPainted, trust_line_painted: trustPainted,
      production_resolver_answered: paneProviderFor ? paneProviderFor(paneD) || null : null,
      grok_on_grok_line: scopedForGrok ? scopedForGrok.terminal_state : null,
      undeclared_on_grok_line: scopedForOther ? scopedForOther.terminal_state : null,
      undeclared_on_universal_line: universalForOther ? universalForOther.terminal_state : null,
      grok_on_universal_line: universalForGrok ? universalForGrok.terminal_state : null,
      ok: limitPainted && trustPainted && limitText !== null && trustText !== null
        && !!scopedForGrok && scopedForGrok.terminal_state === "USAGE_LIMIT"
        && scopedForOther === null
        && !!universalForOther && universalForOther.terminal_state === "WORKSPACE_TRUST_REQUIRED"
        && !!universalForGrok && universalForGrok.terminal_state === "WORKSPACE_TRUST_REQUIRED",
    };
    log("[selfcheck] U393 classification: "
      + `grok=${scopedForGrok && scopedForGrok.terminal_state} `
      + `undeclared=${scopedForOther && scopedForOther.terminal_state}`);

    // ---- E: the submit key, in bytes, on real ConPTYs -------------------------------------------
    if (!CONFIRMING) throw new Error("no declared provider carries submit_confirm_enter");
    const manager = typeof sessionManager === "function" ? sessionManager() : null;
    if (!manager) throw new Error("the runtime did not expose its session manager");
    const paneE1 = await spawnPane(ctx, receipt, "E-confirming", paneIds);
    const paneE2 = await spawnPane(ctx, receipt, "E-undeclared", paneIds);
    const providerByPane = { [paneE1]: CONFIRMING, [paneE2]: UNDECLARED };
    // What the SESSION MANAGER was actually handed, per pane, in order — recorded at the boundary
    // between the writer and the real ConPTY. This is the leg's criterion because the pane-side
    // count is not trustworthy on its own: across three runs of this check the undeclared pane's
    // prompt-token delta read 0, 1 and 2 for the SAME one submitted line, because a repaint can
    // redraw a prompt and a slow render can hide one. That number is still recorded below, as an
    // observation with its noise stated, and the body reaching each pane is still measured.
    const handed = { [paneE1]: [], [paneE2]: [] };
    const writer = createPaneWriter({
      paneScreen: paneScreenFromWindow(readinessWindow),
      providerFor: (id) => providerByPane[id] || null,
      write: (id, data) => {
        const accepted = manager.write(id, data);
        if (handed[id] && accepted !== false) handed[id].push(data);
        return accepted;
      },
      sleep,
      pasteSettleMs: () => 200,
      submitConfirmMs: () => 200,
      log: (m) => log(`[selfcheck] ${m}`),
      conductorTarget: () => null,
      workerPaneFor: () => null,
    });
    const before1 = await submitCount(win, paneE1);
    const before2 = await submitCount(win, paneE2);
    const w1 = await writer.writePrompt(paneE1, "Write-Output 'SOVEREIGN_U331_E1'");
    const w2 = await writer.writePrompt(paneE2, "Write-Output 'SOVEREIGN_U331_E2'");
    const executed1 = await seesNeedle(win, paneE1, "SOVEREIGN_U331_E1", OUTPUT_MS);
    const executed2 = await seesNeedle(win, paneE2, "SOVEREIGN_U331_E2", OUTPUT_MS);
    // Both panes are then watched past the point where the confirming one has finished, so a
    // difference in the observation below is not a difference in patience.
    await sleep(3000);
    const after1 = await submitCount(win, paneE1);
    const after2 = await submitCount(win, paneE2);
    const enters1 = handed[paneE1].filter((d) => d === "\r").length;
    const enters2 = handed[paneE2].filter((d) => d === "\r").length;
    receipt.legs.submit_key_follows_the_declared_trait = {
      confirming_provider: CONFIRMING,
      undeclared_provider: UNDECLARED,
      confirming_written: w1 && w1.written === true,
      undeclared_written: w2 && w2.written === true,
      confirming_bytes_handed_to_conpty: handed[paneE1],
      undeclared_bytes_handed_to_conpty: handed[paneE2],
      confirming_submit_keys: enters1, undeclared_submit_keys: enters2,
      confirming_body_executed_in_pane: executed1,
      undeclared_body_executed_in_pane: executed2,
      declared_confirm_enter: traitsFor(CONFIRMING).submit_confirm_enter,
      undeclared_confirm_enter: traitsFor(UNDECLARED).submit_confirm_enter,
      observed_prompt_delta: {
        confirming: Number.isInteger(after1) && Number.isInteger(before1) ? after1 - before1 : null,
        undeclared: Number.isInteger(after2) && Number.isInteger(before2) ? after2 - before2 : null,
        note: "pane-side observation only, NOT a criterion: the same one submitted line has read 0, "
          + "1 and 2 across runs of this check, because a repaint redraws a prompt and a slow "
          + "render hides one",
      },
      ok: w1 && w1.written === true && w2 && w2.written === true
        && enters1 === 2 && enters2 === 1 && executed1 === true && executed2 === true,
    };
    log(`[selfcheck] U393 submit keys handed to ConPTY: ${CONFIRMING}=${enters1} `
      + `${UNDECLARED}=${enters2}`);

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
  log(`[selfcheck] conductor-descriptor ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runConductorDescriptorSelfCheck: run, RECEIPT_PATH };
