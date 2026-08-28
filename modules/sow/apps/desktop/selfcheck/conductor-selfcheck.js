"use strict";
/**
 * Phase 16C in-Electron conductor-selection self-check (D-P16-0 binding, per-track).
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer) and proves the exact U65 fix:
 * pane-1's CONDUCTOR badge is SOURCED from the authoritative Python emitter
 * (tools/live/emit_conductor_selection --emit-conductor-selection) and rendered VERBATIM — not read
 * from a hand-maintained literal that could drift from the operator's selection authority. It writes
 * a machine-readable receipt so the gate closes on runtime evidence, not headless-only tests.
 *
 * Flow:
 *   1. wait for the renderer to have received the conductor state + rendered pane 1's CONDUCTOR badge;
 *   2. read the MAIN-side feed (ctx.conductorFeed): assert a real subprocess feed was parsed
 *      (ok:true, the pinned schema) — this is the load-bearing proof the badge came from Python;
 *   3. read the MAIN-side conductor state (ctx.conductorState): assert selectionSourced:true and the
 *      badge model matches the sourced selection;
 *   4. read the RENDERED .cbadge text off the conductor pane and assert it carries that same model —
 *      so the Python authority, the main state, and the pixel all agree (no drift, invariant 3);
 *   5. assert the Resume→Select succession control is present (sourced, not a literal);
 *   6. write the receipt. The caller tears down (no orphan PTY/gateway, D-LOOP-1) and exits pass/fail.
 *
 * Load-bearing: if the wiring reverted to a local literal, ctx.conductorFeed().ok would be false (no
 * subprocess parsed) and conductorState().selectionSourced would be false — this check would FAIL.
 * The renderer-vs-feed model equality proves the drift U65 flagged cannot occur.
 *
 * No supervision is required: the conductor pane is a governed PLACEHOLDER (sessionId null, no naked
 * session — invariant 2) created conductor-first on launch; the badge renders regardless of the
 * control-plane channel.
 */
const fs = require("fs");
const path = require("path");

const RECEIPT_PATH = path.resolve(
  __dirname, "..", "..", "..", "docs", "evidence", "receipts", "PHASE16C_SELFCHECK.json"
);
const FEED_SCHEMA = "conductor_selection_feed@1.0";

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
  const { win, conductorState, conductorFeed, log } = ctx;
  const receipt = {
    check: "phase-16c.selection",
    started: new Date().toISOString(),
    ok: false,
    // main-side: was the badge SOURCED from the authoritative Python emitter?
    feed_ok: false,
    feed_schema: null,
    feed_error: null,
    selection_sourced: false,
    main_badge_model: null,
    feed_selection_model: null,
    // renderer-side: what actually rendered into pane 1's CONDUCTOR badge
    conductor_pane_id: null,
    badge_rendered: false,
    badge_text: null,
    rendered_model_matches_feed: false,
    succession_available: false,
    error: null,
  };
  try {
    // 2. MAIN-side feed — the load-bearing proof the badge came from a real subprocess, not a literal.
    const feed = (typeof conductorFeed === "function" ? conductorFeed() : null) || {};
    receipt.feed_ok = feed.ok === true;
    receipt.feed_schema = feed.feed && feed.feed.schema ? feed.feed.schema : null;
    receipt.feed_error = feed.error || null;
    const sel = feed.feed && feed.feed.selection_record && feed.feed.selection_record.selection;
    receipt.feed_selection_model = sel ? sel.model : null;
    if (!receipt.feed_ok) throw new Error(`conductor selection feed was not sourced from Python (ok:false): ${receipt.feed_error || "unknown"}`);
    if (receipt.feed_schema !== FEED_SCHEMA) throw new Error(`sourced feed carries an unexpected schema: ${receipt.feed_schema}`);

    // 3. MAIN-side conductor state — selectionSourced + the badge model it will send the renderer.
    const st = (typeof conductorState === "function" ? conductorState() : null) || {};
    receipt.selection_sourced = st.selectionSourced === true;
    receipt.main_badge_model = st.badge ? st.badge.model : null;
    receipt.conductor_pane_id = st.paneId || null;
    if (!receipt.selection_sourced) throw new Error("conductorState().selectionSourced is not true — badge is not sourced from Python");
    if (!receipt.conductor_pane_id) throw new Error("no conductor pane was created (conductor-first pane 1 missing)");
    if (receipt.main_badge_model !== receipt.feed_selection_model) {
      throw new Error(`main badge model ${JSON.stringify(receipt.main_badge_model)} != sourced feed model ${JSON.stringify(receipt.feed_selection_model)}`);
    }

    // 1./4. RENDERER-side: wait for the badge to render, then read it off the real DOM.
    const paneId = receipt.conductor_pane_id;
    receipt.badge_rendered = await waitFor(async () => {
      const b = await evalR(win, `window.__sovereignSelfCheck.conductorBadgeText(${JSON.stringify(paneId)})`);
      return !!(b && b.isConductor && typeof b.text === "string" && b.text.indexOf("CONDUCTOR") >= 0);
    }, 20000, 200);
    const badge = await evalR(win, `window.__sovereignSelfCheck.conductorBadgeText(${JSON.stringify(paneId)})`);
    receipt.badge_text = badge ? badge.text : null;
    if (!receipt.badge_rendered || !receipt.badge_text) throw new Error("the CONDUCTOR badge never rendered into pane 1's chrome");
    // the rendered pixel must carry the SAME model the Python authority holds (no drift, invariant 3)
    receipt.rendered_model_matches_feed = typeof receipt.feed_selection_model === "string"
      && receipt.feed_selection_model.length > 0
      && receipt.badge_text.indexOf(receipt.feed_selection_model) >= 0;
    if (!receipt.rendered_model_matches_feed) {
      throw new Error(`rendered badge ${JSON.stringify(receipt.badge_text)} does not carry the sourced model ${JSON.stringify(receipt.feed_selection_model)}`);
    }

    // 5. the Resume→Select succession control is present (sourced from the affordance, not a literal).
    const rState = await evalR(win, "window.__sovereignSelfCheck.conductorState()") || {};
    receipt.succession_available = !!(rState.succession && rState.succession.available === true);
    if (!receipt.succession_available) throw new Error("the Resume→Select succession control is not available in the sourced conductor state");

    log(`[selfcheck] conductor badge SOURCED from Python: model=${receipt.feed_selection_model} · rendered='${receipt.badge_text}'`);
    receipt.ok = receipt.feed_ok && receipt.selection_sourced && receipt.badge_rendered
      && receipt.rendered_model_matches_feed && receipt.succession_available;
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
  log(`[selfcheck] conductor ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runConductorSelfCheck: run, RECEIPT_PATH };
