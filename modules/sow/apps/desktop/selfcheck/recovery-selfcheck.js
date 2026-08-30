"use strict";
/**
 * Phase 16D `.recovery` in-Electron self-check (D-P16-0 binding, per-track) — closes U68.
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer) and proves the thing U68 owed:
 * the recovery SNAPSHOT now carries per-pane worker CHROME, so after a full shell-process restart a
 * worker pane repaints its EXACT model badge instead of coming back blank. Before this fix worker
 * panes snapshotted as model null (only the conductor carried governed chrome), so a restart lost
 * every worker's model badge.
 *
 * Flow (all against the REAL renderer + REAL picker + REAL RecoveryStore on disk):
 *   1. wait for supervision READY (governed spawn path — no naked session, invariant 2);
 *   2. spawn a supervised worker pane and record a governed picker selection targeting it (the SAME
 *      governed intent a click fires) → the pane's model badge previews the selection AND main
 *      records the chrome server-side + persists the layout snapshot;
 *   3. DURABLE half (the real U68 gap): read the persisted layout.json back off disk and assert the
 *      worker entry carries the chrome (model badge label) — honestly governed:false (a recorded
 *      selection, never a live-node claim);
 *   4. FOLD half: reconstruct the conductor-first layout (the production restart fold) and assert the
 *      recovered worker carries the chrome AND is still reattach:false / not admitted (invariant 2 —
 *      carrying a badge never auto-attaches a live session);
 *   5. VISIBLE half (load-bearing): simulate a fresh renderer — drop the in-memory picker badges
 *      (resetBadges) so the badge goes blank, then push shell:recovery through the production path
 *      (sendRecovery) and assert the renderer REBUILDS the model badge from the reconstructed chrome.
 *   6. write the receipt. The caller tears down (no orphan PTY/gateway, D-LOOP-1) and exits pass/fail.
 *
 * Load-bearing: if the U68 wiring reverted (paneMeta returns no chrome for workers ⇒ the snapshot
 * carries chrome:null), step 3 fails (no model_label on disk), step 4's recovered chrome is null, and
 * step 5's badge never repaints ⇒ this self-check FAILS. Empirically falsifiable.
 *
 * This self-check makes NO live `claude`/`codex` call — it records a governed SELECTION only; the
 * live governed worker spawn stays owed to 16F/U70 (§2.2/§2.4). Recovery state is isolated to
 * .recovery/selfcheck/ (main sets RECOVERY_DIR under SHELL_SELFCHECK), so the real store is untouched.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const RECEIPT_PATH = receiptPath("PHASE16D_RECOVERY_SELFCHECK.json");

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

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, loadLayoutSnapshot, reconstructLayout, sendRecovery, log } = ctx;
  const receipt = {
    schema: "phase16d_recovery_selfcheck@1.0",
    ok: false,
    electron: process.versions.electron || null,
    node: process.versions.node || null,
    platform: `${process.platform}-${process.arch}`,
    checks: {},
    target_pane_id: null,
    selected_label: null,
    snapshot_chrome: null,
    recovered_chrome: null,
    badge_before_reset: null,
    badge_after_reset: null,
    badge_after_recovery: null,
  };

  try {
    // 1. supervision READY (a naked session is impossible by design — invariant 2).
    receipt.checks.supervision_ready = await waitFor(isSupervised, 25000, 250);
    if (!receipt.checks.supervision_ready) throw new Error("supervision never became READY within 25s");

    // 2. a supervised worker pane + a governed picker selection targeting it.
    const paneId = createPaneWithSession({ file: "powershell.exe", args: ["-NoLogo", "-NoProfile", "-NoExit"], title: "recovery-target" });
    receipt.target_pane_id = paneId;
    await waitFor(async () => evalR(win, `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(paneId)})`), 15000, 200);

    await evalR(win, `window.__sovereignSelfCheck.openPicker(${JSON.stringify(paneId)})`);
    await waitFor(async () => { const s = await evalR(win, "window.__sovereignSelfCheck.pickerSummary()"); return !!(s && s.ok); }, 30000, 300);
    const summary = await evalR(win, "window.__sovereignSelfCheck.pickerSummary()") || {};
    if (!(summary.firstAvailable >= 0)) {
      // Honest degrade: with no available option we cannot record a governed selection to recover.
      receipt.checks.selection_available = false;
      receipt.note = "no available picker option on this host — the U68 chrome round-trip is proven headlessly (layout-reconstruct.test.js); the visible leg needs an available option";
      throw new Error("no available picker option to record a governed selection (visible U68 leg needs one)");
    }
    receipt.checks.selection_available = true;
    // Worker role "reasoning" (offered by every provider's options; the conductor role is refused by
    // the worker picker — proven in the 16B check). This records the governed selection + chrome.
    const spawn = await evalR(win, `window.__sovereignSelfCheck.selectOption(${summary.firstAvailable}, "reasoning")`);
    receipt.checks.selection_recorded = !!(spawn && spawn.recorded);
    receipt.selected_label = spawn && spawn.chrome ? spawn.chrome.model_label : null;
    if (!receipt.checks.selection_recorded || !receipt.selected_label) throw new Error("the governed selection was not recorded with a model label");
    await sleep(150);
    const badgeBefore = await evalR(win, `window.__sovereignSelfCheck.paneBadgeText(${JSON.stringify(paneId)})`);
    receipt.badge_before_reset = badgeBefore;
    receipt.checks.badge_previewed = !!(badgeBefore && badgeBefore.shown && String(badgeBefore.text).includes(receipt.selected_label));
    if (!receipt.checks.badge_previewed) throw new Error("the pane model badge did not preview the recorded selection");

    // 3. DURABLE half — the persisted layout.json (off disk) carries the worker chrome (U68 gap).
    const snap = loadLayoutSnapshot();
    const snapWorker = snap && Array.isArray(snap.panes) ? snap.panes.find((p) => p.paneId === paneId) : null;
    receipt.snapshot_chrome = snapWorker ? snapWorker.chrome : null;
    receipt.checks.snapshot_carries_chrome = !!(receipt.snapshot_chrome && receipt.snapshot_chrome.model_label === receipt.selected_label);
    // honesty: a RECORDED selection, never a live-node claim.
    receipt.checks.snapshot_chrome_not_governed = !!(receipt.snapshot_chrome && receipt.snapshot_chrome.governed === false);
    if (!receipt.checks.snapshot_carries_chrome) throw new Error("the persisted snapshot did NOT carry the worker's model chrome (U68 not closed)");

    // 4. FOLD half — the production restart fold carries the chrome, still fail-closed (invariant 2).
    const layout = reconstructLayout();
    const recWorker = layout && Array.isArray(layout.panes) ? layout.panes.find((p) => p.paneId === paneId) : null;
    receipt.recovered_chrome = recWorker ? recWorker.chrome : null;
    receipt.checks.recovered_carries_chrome = !!(receipt.recovered_chrome && receipt.recovered_chrome.model_label === receipt.selected_label);
    receipt.checks.recovered_not_reattached = !!(recWorker && recWorker.reattach === false && recWorker.admitted === false);
    if (!receipt.checks.recovered_carries_chrome) throw new Error("the reconstructed layout did NOT carry the worker's model chrome");
    if (!receipt.checks.recovered_not_reattached) throw new Error("a recovered worker was auto-attached/admitted (invariant 2 breach)");

    // 5. VISIBLE half (load-bearing) — simulate a fresh renderer: drop in-memory badges, prove the
    //    badge went blank, then push shell:recovery through the PRODUCTION path and prove the renderer
    //    REBUILDS the badge from the reconstructed chrome (not from this session's memory).
    await evalR(win, "window.__sovereignSelfCheck.resetBadges()");
    await sleep(50);
    const badgeAfterReset = await evalR(win, `window.__sovereignSelfCheck.paneBadgeText(${JSON.stringify(paneId)})`);
    receipt.badge_after_reset = badgeAfterReset;
    receipt.checks.badge_cleared_on_reset = !!(badgeAfterReset && badgeAfterReset.shown === false);

    sendRecovery(); // production restart push (reconstruct → shell:recovery), same as boot
    const repainted = await waitFor(async () => {
      const b = await evalR(win, `window.__sovereignSelfCheck.paneBadgeText(${JSON.stringify(paneId)})`);
      return !!(b && b.shown && String(b.text).includes(receipt.selected_label));
    }, 10000, 200);
    receipt.badge_after_recovery = await evalR(win, `window.__sovereignSelfCheck.paneBadgeText(${JSON.stringify(paneId)})`);
    receipt.checks.badge_restored_from_recovery = repainted;
    if (!repainted) throw new Error("the model badge was NOT rebuilt from the reconstructed chrome after recovery");

    receipt.owed_note = "16F/U70: the live governed worker SPAWN from a selection is still owed; this proves the RECORDED selection + its badge survive a restart (read/record half).";
    receipt.ok = receipt.checks.snapshot_carries_chrome && receipt.checks.snapshot_chrome_not_governed
      && receipt.checks.recovered_carries_chrome && receipt.checks.recovered_not_reattached
      && receipt.checks.badge_cleared_on_reset && receipt.checks.badge_restored_from_recovery;
  } catch (e) {
    receipt.error = `${e && e.name}: ${e && e.message}`;
    if (log) log(`[selfcheck:recovery] crashed: ${e && e.message}`);
  }

  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    if (log) log(`[selfcheck:recovery] could not write receipt: ${e && e.message}`);
  }
  if (log) log(`[selfcheck:recovery] ok=${receipt.ok} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runRecoverySelfCheck: run, RECEIPT_PATH };
