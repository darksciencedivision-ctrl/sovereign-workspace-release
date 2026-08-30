"use strict";
/**
 * Phase 17D `.events` in-Electron self-check (D-P16-0 binding, per-track) — finding F2.
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer) and proves the operator's drawer
 * shows THIS session's events and nothing else. The 16D version of this file asserted the opposite:
 * it required three rows at launch (`has_plan`, `has_protected_action`, `has_clarification`,
 * `badge_at_least_3`) — a green check on exactly the defect the operator reported. What it should have
 * been asking is what this one asks.
 *
 * Flow, through the SAME preload bridge the renderer uses:
 *   1. AT LAUNCH, before anything has happened: `approvals:fetch` must come back SOURCED with a badge
 *      of ZERO and no rows — no `ap-1`/`ap-2`/`ap-3`, no demo content (the F2 assertion);
 *   2. produce a REAL event the way the product does — a fixture-audio voice capture whose transcript
 *      carries a PROTECTED verb, routed through the real bridge + the real CommandBroker (invariant 25:
 *      it is queued, never delivered, never executed);
 *   3. re-fetch: exactly ONE row, of kind `protected_action`, carrying the broker's ref, the verb the
 *      classifier derived, and the provenance of the event that produced it;
 *   4. paint it in the RENDERER and read `#appr-body` back (the emitter, main and the pixel agree);
 *   5. ROUTE a governed decide: REJECT that row → the Python authority resolves it, the shell records
 *      the event the authority minted, and a THIRD fetch shows the drawer empty again — the resolve
 *      PERSISTED (the gap 16D recorded as owed);
 *   6. and one refusal: approving a non-approvable item is refused by Python, self-authorizing nothing.
 *
 * Load-bearing and falsifiable: if the drawer reverted to a canned producer, step 1 would show three
 * rows ⇒ FAIL. If the recorded classification were trusted instead of re-derived, step 3's verb/ref
 * would not come from the broker. If the decision did not persist, step 5's badge would not return to 0.
 *
 * No live `claude`/`codex` call: the voice feed runs mock-first over the real bridge, and the drawer
 * emitters only fold a recorded file (no MCP server, no flow — D-LOOP-1 by construction).
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const RECEIPT_PATH = receiptPath("PHASE17D_APPROVALS_SELFCHECK.json");
// The scripted stand-in ref whose transcript ("spawn worker", conf 0.9) leads with a PROTECTED verb,
// so the real bridge proposes it and the real broker queues it instead of delivering it as chat. A
// stand-in, not real PCM: this check is about the DRAWER, and the real-microphone path has its own
// receipt (PHASE17C_VOICE_MIC_SELFCHECK).
const PROTECTED_AUDIO_REF = "audio:spawn-worker";

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

const rowsOf = (m) => (m && Array.isArray(m.rows) ? m.rows : []);

async function run(ctx) {
  const { win, log } = ctx;
  const startedAt = Date.now();
  const receipt = {
    schema: "phase17d_approvals_selfcheck@1.0",
    ok: false,
    electron: process.versions.electron || null,
    node: process.versions.node || null,
    platform: `${process.platform}-${process.arch}`,
    checks: {},
    at_launch: null,
    after_event: null,
    after_decision: null,
    decision: null,
    refusal: null,
    rendered_excerpt: null,
  };

  try {
    // 1. AT LAUNCH — an empty session must render an EMPTY drawer, sourced (not "unavailable").
    await waitFor(async () => {
      const m = await evalR(win, "window.sovereign.approvals()");
      return !!(m && m.sourced === true);
    }, 60000, 500);
    const atLaunch = await evalR(win, "window.sovereign.approvals()");
    receipt.at_launch = atLaunch;
    const launchRows = rowsOf(atLaunch);
    receipt.checks.launch_sourced = !!(atLaunch && atLaunch.sourced === true);
    receipt.checks.launch_source_is_session_events = !!(atLaunch && atLaunch.source === "session_events");
    receipt.checks.launch_badge_zero = !!(atLaunch && atLaunch.badgeCount === 0);
    receipt.checks.launch_no_rows = launchRows.length === 0;
    // THE F2 ASSERTION: the demonstration trio cannot be here, by id or by content.
    receipt.checks.launch_no_demo_trio = !launchRows.some(
      (r) => ["ap-1", "ap-2", "ap-3"].includes(r.id) || /roster thing|gpt-5\.5/.test(r.summary || ""));
    receipt.checks.launch_no_error = !(atLaunch && atLaunch.error);

    // 2. produce a REAL session event: a fixture voice capture carrying a PROTECTED verb. The bridge
    //    classifies it, the broker queues it, and main records the event for the drawer.
    const captured = await evalR(win,
      `window.sovereign.captureVoice(${JSON.stringify(PROTECTED_AUDIO_REF)})`);
    receipt.capture = captured ? {
      kind: captured.kind, delivered: captured.delivered_to_conductor === true,
      self_authorized: captured.selfAuthorized, engine: captured.engine ? captured.engine.name : null,
    } : null;
    // invariant 25: a protected utterance PROPOSES; it is never delivered into the conductor input.
    receipt.checks.protected_not_delivered = !!(captured && captured.delivered_to_conductor !== true);

    // 3. the drawer now holds exactly that one row — re-derived, not trusted.
    await waitFor(async () => {
      const m = await evalR(win, "window.sovereign.approvals()");
      return rowsOf(m).length > 0;
    }, 60000, 500);
    const afterEvent = await evalR(win, "window.sovereign.approvals()");
    receipt.after_event = afterEvent;
    const rows = rowsOf(afterEvent);
    const row = rows[0] || null;
    receipt.checks.one_row_after_one_event = rows.length === 1;
    receipt.checks.row_is_protected_action = !!(row && row.kind === "protected_action");
    // the verb + the broker ref are the CLASSIFIER's, produced by re-deriving the recorded transcript
    receipt.checks.row_verb_from_classifier = !!(row && row.detail && row.detail.verb === "spawn");
    receipt.checks.row_carries_broker_ref = !!(row && typeof row.ref === "string" && row.ref);
    // provenance (invariant 11): the row names the event and the channel it came from
    receipt.checks.row_carries_provenance = !!(row && row.detail
      && typeof row.detail.event_id === "string" && row.detail.event_id
      && row.detail.channel === "voice:capture");
    receipt.checks.badge_is_one = !!(afterEvent && afterEvent.badgeCount === 1);

    // 4. paint it in the RENDERER and read the painted body back.
    await evalR(win, 'document.getElementById("btn-approvals") && document.getElementById("btn-approvals").click()');
    await waitFor(async () => {
      const html = await evalR(win, 'document.getElementById("appr-body") && document.getElementById("appr-body").innerHTML');
      return typeof html === "string" && html.includes("appr-item");
    }, 60000, 500);
    const rendered = await evalR(win, 'document.getElementById("appr-body") && document.getElementById("appr-body").innerHTML');
    receipt.rendered_excerpt = typeof rendered === "string" ? rendered.slice(0, 500) : null;
    receipt.checks.rendered_shows_the_real_row = typeof rendered === "string"
      && rendered.includes("appr-item") && rendered.includes("Protected action");

    // 5. the operator DECIDES: reject it. Python resolves; main records the authority's own event; the
    //    next fetch must show it gone — the resolve persisted across the read.
    let decisionHonest = false;
    if (row && row.id) {
      const res = await evalR(win, `window.sovereign.decideApproval(${JSON.stringify(row.id)}, "reject", "not now")`);
      receipt.decision = res;
      const governed = res && res.governed;
      receipt.checks.decide_routed = !!(res && res.routed === true);
      receipt.checks.decide_self_authorized_false = !!(res && res.selfAuthorized === false);
      receipt.checks.decide_resolved_by_python = !!(governed && governed.resolved === true);
      // the authority minted the event the shell persisted — the shell authored no decision record
      receipt.checks.decision_event_minted_by_authority = !!(governed && governed.decision_event
        && governed.decision_event.kind === "decision");
      const afterDecision = await evalR(win, "window.sovereign.approvals()");
      receipt.after_decision = afterDecision;
      receipt.checks.decision_persisted_empty_drawer = !!(afterDecision
        && afterDecision.sourced === true && afterDecision.badgeCount === 0
        && rowsOf(afterDecision).length === 0);
      decisionHonest = receipt.checks.decide_routed && receipt.checks.decide_self_authorized_false
        && receipt.checks.decide_resolved_by_python && receipt.checks.decision_persisted_empty_drawer;
    } else {
      receipt.checks.decide_skipped_no_row = true;
    }

    // 6. and the governed REFUSAL still refuses: a decided item cannot be decided again (invariant 16
    //    machinery, no override path), and the shell reports the refusal rather than a resolution.
    if (row && row.id) {
      const again = await evalR(win, `window.sovereign.decideApproval(${JSON.stringify(row.id)}, "approve", "")`);
      receipt.refusal = again;
      const g = again && again.governed;
      receipt.checks.re_decide_governed_refused = !!(g && g.resolved === false && g.refused === true);
    }

    receipt.checks.no_demo_items_flag = !!(afterEvent && afterEvent.demoItems === false);

    receipt.side_effects_owed = "17E (an approved item's downstream effect — broker execute / "
      + "ObjectiveIntake assign — is not fired from the decide path)";

    receipt.ok = Object.entries(receipt.checks)
      .filter(([k]) => !k.startsWith("decide_skipped"))
      .every(([, v]) => v === true);
    receipt.checks_passed = Object.values(receipt.checks).filter((v) => v === true).length;
    receipt.checks_total = Object.keys(receipt.checks).length;
    // recorded so the launcher's ceiling is set from a measurement rather than a guess
    receipt.duration_ms = Date.now() - startedAt;
  } catch (e) {
    receipt.error = `${e && e.name}: ${e && e.message}`;
    if (log) log(`[selfcheck:approvals] crashed: ${e && e.message}`);
  }

  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    if (log) log(`[selfcheck:approvals] could not write receipt: ${e && e.message}`);
  }
  if (log) log(`[selfcheck:approvals] ok=${receipt.ok} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runApprovalsSelfCheck: run, RECEIPT_PATH };
