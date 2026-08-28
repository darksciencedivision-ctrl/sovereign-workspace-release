"use strict";
/**
 * Phase 16B in-Electron per-pane model-picker self-check (D-P16-0 binding, per-track).
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer) and proves the exact thing the
 * operator reported missing (OP-10 finding 2 — "no per-pane model selector visible"): the picker
 * opens, the LIVE host enumeration renders as selectable options, and a selection dispatches the
 * governed pane_node_spawn intent (previewing the pane's model badge). It writes a machine-readable
 * receipt so the gate closes on runtime evidence, not headless-only tests.
 *
 * Flow:
 *   1. wait for supervision READY (so a real supervised target pane can be spawned — no naked
 *      session, invariant 2);
 *   2. spawn a supervised worker pane to be the picker TARGET;
 *   3. open the picker targeting that pane; assert the LIVE enumeration rendered (options, groups,
 *      readable authorization, and — honesty — every greyed option carries a reason);
 *   4. dispatch a selection of the first AVAILABLE option through the SAME governed intent a click
 *      fires; assert it is recorded and the pane's model badge previews the selection;
 *   5. dispatch a KNOWN-BAD selection (conductor role via the worker picker, or a greyed option) and
 *      assert it is REFUSED fail-closed — the guard is load-bearing in the wired UI, not just tests;
 *   6. write the receipt. The caller tears down (no orphan PTY/gateway) and exits with pass/fail.
 *
 * Every boolean in the receipt is measured against the real renderer; nothing is fabricated. Where
 * the host has no available option (e.g. no Ollama and live-DENIED), the selection leg is recorded
 * as not-run WITH the reason and the render+refusal proof still stands (honest degrade).
 */
const fs = require("fs");
const path = require("path");

// The 16B GATE artifact by default. A later phase re-running this check as a regression must set
// SHELL_SELFCHECK_RECEIPT_DIR: 18B `.picker` overwrote this file in place and the receipt stopped
// describing the 16B run (append-only, directive §2.6 — MEDIUM-2).
const { receiptPath } = require("./receipt-path");

const RECEIPT_PATH = receiptPath("PHASE16B_SELFCHECK.json");

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

// Evaluate an expression in the renderer, awaiting a returned promise. Returns null on failure.
async function evalR(win, expr) {
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, log } = ctx;
  const receipt = {
    check: "phase-16b.picker",
    started: new Date().toISOString(),
    ok: false,
    supervision_ready: false,
    target_pane_id: null,
    picker_opened: false,
    picker_ok: false,
    option_count: 0,
    group_count: 0,
    available_count: 0,
    authorization_readable: false,
    authorization_authorized: null,
    greyed_all_have_reason: true,
    rendered_option_els: 0,
    selection_run: false,
    selection_recorded: false,
    selected_label: null,
    selected_role: null,
    badge_shown: false,
    badge_text: null,
    refusal_proved: false,
    refusal_reason: null,
    error: null,
  };
  try {
    // 1. supervision READY (governed spawn path — a naked session is impossible by design)
    receipt.supervision_ready = await waitFor(isSupervised, 25000, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY (control-plane/IPC gateway did not verify within 25s)");
    }

    // 2. a supervised worker pane to target with the picker
    const paneId = createPaneWithSession({ file: "powershell.exe", args: ["-NoLogo", "-NoProfile", "-NoExit"], title: "picker-target" });
    receipt.target_pane_id = paneId;
    // the renderer must have created the xterm view for the target pane (layout plan)
    await waitFor(async () => evalR(win, `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(paneId)})`), 15000, 200);

    // 3. open the picker targeting the pane and wait for the LIVE enumeration to render
    await evalR(win, `window.__sovereignSelfCheck.openPicker(${JSON.stringify(paneId)})`);
    receipt.picker_opened = await waitFor(
      async () => { const s = await evalR(win, "window.__sovereignSelfCheck.pickerSummary()"); return !!(s && s.ok); },
      30000, 300
    );
    const summary = await evalR(win, "window.__sovereignSelfCheck.pickerSummary()") || {};
    const rendered = await evalR(win, "window.__sovereignSelfCheck.pickerRendered()") || {};
    receipt.picker_ok = !!summary.ok;
    receipt.option_count = summary.total || 0;
    receipt.group_count = rendered.groupEls || 0;
    receipt.available_count = summary.available || 0;
    receipt.authorization_readable = !!summary.authReadable;
    receipt.authorization_authorized = summary.authAuthorized;
    receipt.greyed_all_have_reason = summary.greyedWithReason !== false;
    receipt.rendered_option_els = rendered.optionEls || 0;
    if (!receipt.picker_ok) throw new Error("picker never rendered a live enumeration (ok:false or empty)");
    if (receipt.rendered_option_els <= 0) throw new Error("picker rendered zero option rows into the drawer");
    if (!receipt.authorization_readable) throw new Error("picker authorization block not readable");
    if (!receipt.greyed_all_have_reason) throw new Error("a greyed option rendered without a reason (dishonest grey)");
    log(`[selfcheck] picker rendered ${receipt.option_count} options (${receipt.available_count} available) in ${receipt.group_count} groups`);

    // 4. dispatch the first AVAILABLE option through the governed intent; expect a recorded selection
    //    + a previewed pane badge. If nothing is available on this host, record that honestly.
    if (summary.firstAvailable >= 0) {
      receipt.selection_run = true;
      // Select with the WORKER role "reasoning" (offered by every provider's options) — the default
      // role of an Anthropic option is "conductor", which the worker picker deliberately refuses
      // (that path is proven separately in step 5). Here we prove an ordinary governed worker spawn.
      const res = await evalR(win, `window.__sovereignSelfCheck.selectOption(${summary.firstAvailable}, "reasoning")`);
      receipt.selection_recorded = !!(res && res.recorded);
      receipt.selected_label = res && res.chrome ? res.chrome.model_label : null;
      receipt.selected_role = res && res.chrome ? res.chrome.role : null;
      await sleep(150);
      const badge = await evalR(win, `window.__sovereignSelfCheck.paneBadgeText(${JSON.stringify(paneId)})`);
      receipt.badge_shown = !!(badge && badge.shown);
      receipt.badge_text = badge ? badge.text : null;
      if (!receipt.selection_recorded) throw new Error("an available selection was not recorded by the governed intent");
      if (!receipt.badge_shown) throw new Error("the pane model badge did not preview the selection");
      log(`[selfcheck] selection recorded + badge previewed: ${receipt.badge_text}`);
    } else {
      receipt.selection_run = false;
      receipt.selection_note = "no available option enumerated on this host (Ollama absent + live-DENIED) — render+refusal proof stands";
      log(`[selfcheck] no available option on this host — selection leg recorded as not-run (honest)`);
    }

    // 5. KNOWN-BAD selection must be REFUSED fail-closed in the wired UI. Prefer a conductor-role
    //    selection through the worker picker (host-independent refusal); if no option offers the
    //    conductor role, a greyed option's selection is the refusal instead.
    if (summary.firstConductor >= 0) {
      const bad = await evalR(win, `window.__sovereignSelfCheck.selectOption(${summary.firstConductor}, "conductor")`);
      receipt.refusal_proved = !!(bad && bad.recorded === false && bad.error);
      receipt.refusal_reason = bad ? bad.error : null;
    }
    if (!receipt.refusal_proved) {
      // fallback: try to select a greyed option (if any) — it must be refused as unavailable
      const gi = await evalR(win, `(function(){const o=(window.__sovereignSelfCheck.pickerModel().picker.options||[]);return o.findIndex(x=>!x.available);})()`);
      if (typeof gi === "number" && gi >= 0) {
        const bad2 = await evalR(win, `window.__sovereignSelfCheck.selectOption(${gi})`);
        receipt.refusal_proved = !!(bad2 && bad2.recorded === false && bad2.error);
        receipt.refusal_reason = bad2 ? bad2.error : null;
      }
    }
    if (!receipt.refusal_proved) throw new Error("could not prove a fail-closed refusal (no conductor-capable or greyed option to refuse)");
    log(`[selfcheck] fail-closed refusal proved: ${receipt.refusal_reason}`);

    // PASS: the picker renders the live enumeration honestly, a selection routes through the governed
    // intent + previews the badge (where any option is available), and a bad selection is refused.
    const selectionOk = summary.firstAvailable < 0 ? true : (receipt.selection_recorded && receipt.badge_shown);
    receipt.ok = receipt.picker_ok && receipt.rendered_option_els > 0
      && receipt.authorization_readable && receipt.greyed_all_have_reason
      && selectionOk && receipt.refusal_proved;
  } catch (e) {
    receipt.error = String((e && e.message) || e);
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
  log(`[selfcheck] picker ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runPickerSelfCheck: run, RECEIPT_PATH };
