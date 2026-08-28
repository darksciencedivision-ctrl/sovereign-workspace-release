"use strict";
/**
 * Phase 16D `.statusbar` in-Electron self-check (D-P16-0 binding, per-track).
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer) and proves the operator's
 * "concurrency count unavailable (fail-closed)" finding is FIXED: the status bar now sources a REAL,
 * readable n/allowance count from the governed emitter (statusbar:fetch → governor-source →
 * tools/live/emit_subscription_status.py), not the em-dash unknown the EchoControlSurface gateway
 * forced. It writes a machine-readable receipt so the gate closes on runtime evidence, not
 * headless-only tests.
 *
 * Flow:
 *   1. read the status-bar model through the SAME preload bridge the renderer uses
 *      (`window.sovereign.statusBar()` → statusbar:fetch): assert it was SOURCED from the emitter
 *      (`source:"emitter"`) — the load-bearing proof the governed subprocess ran, not a JS literal;
 *   2. on the authorized host (config/live_operation.json present, OP-6): assert `readable:true`,
 *      a real n/allowance row for BOTH live providers (claude_code + openai_codex_cli), and no
 *      fabricated count — an honest 0/2 (no live frontier terminal held by the shell; live drive is
 *      operator-run/16F). If the host is UNauthorized, assert the honest fail-closed unknown instead;
 *   3. read the RENDERED `#statusbar` DOM: assert the authorized path paints the provider chips with
 *      the count and does NOT paint the "concurrency count unavailable" warn — so the emitter, the
 *      main handler, and the pixel all agree;
 *   4. write the receipt. The caller tears down (no orphan PTY/gateway, D-LOOP-1) and exits pass/fail.
 *
 * Load-bearing: if the wiring reverted to the IPC-only path, the shell's EchoControlSurface gateway
 * would answer no `subscription_status` op ⇒ `readable:false` ⇒ this FAILS on the authorized host.
 *
 * This self-check makes NO live `claude`/`codex` call — the emitter only reads the authorization gate
 * and builds an in-memory governor (§2.2/§2.4).
 */
const fs = require("fs");
const path = require("path");

// The 16D GATE artifact by default; a regression re-run must redirect it with
// SHELL_SELFCHECK_RECEIPT_DIR (see receipt-path.js — directive §2.6, MEDIUM-2).
const { receiptPath } = require("./receipt-path");

const RECEIPT_PATH = receiptPath("PHASE16D_STATUSBAR_SELFCHECK.json");

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
  const { win, log } = ctx;
  const receipt = {
    schema: "phase16d_statusbar_selfcheck@1.0",
    ok: false,
    electron: process.versions.electron || null,
    node: process.versions.node || null,
    platform: `${process.platform}-${process.arch}`,
    checks: {},
    model: null,
    rendered_excerpt: null,
  };

  try {
    // 1. Source the status-bar model through the real preload bridge (statusbar:fetch). Poll until the
    //    bounded emitter subprocess has returned a model (source:"emitter"): the load-bearing proof.
    await waitFor(async () => {
      const m = await evalR(win, "window.sovereign.statusBar()");
      return !!(m && m.source === "emitter");
    }, 40000, 300);

    const model = await evalR(win, "window.sovereign.statusBar()");
    receipt.model = model;
    const sourced = !!(model && model.source === "emitter");
    receipt.checks.model_sourced_from_emitter = sourced;

    const authorized = !!(model && model.feedAuthorized);
    receipt.checks.feed_authorized = authorized;

    // 2. Assert the count per the authorization branch (both branches are honest).
    let countHonest = false;
    if (authorized) {
      const rows = (model && Array.isArray(model.rows)) ? model.rows : [];
      const byProv = Object.fromEntries(rows.map((r) => [r.provider, r]));
      const claude = byProv.claude_code;
      const codex = byProv.openai_codex_cli;
      const bothPresent = !!claude && !!codex;
      const realLabels = bothPresent && /^\d+\/\d+$/.test(claude.label) && /^\d+\/\d+$/.test(codex.label);
      receipt.checks.readable = model.readable === true;
      receipt.checks.both_live_providers_present = bothPresent;
      receipt.checks.real_n_over_allowance_labels = realLabels;
      receipt.checks.no_error = !model.error;
      receipt.count = bothPresent ? { claude_code: claude.label, openai_codex_cli: codex.label } : null;
      countHonest = model.readable === true && realLabels && !model.error;
    } else {
      // Unauthorized host (no config): the honest fail-closed unknown, NOT a fabricated 0/2.
      const rows = (model && Array.isArray(model.rows)) ? model.rows : [];
      const allUnknown = rows.length > 0 && rows.every((r) => r.state === "unknown" && /—\/\d+/.test(r.label));
      receipt.checks.readable = model.readable === false;
      receipt.checks.failclosed_unknown_no_fabricated_count = allUnknown;
      receipt.checks.reason_present = !!(model && model.error);
      countHonest = model.readable === false && allUnknown;
    }

    // 3. Read the RENDERED status bar DOM and assert the pixel agrees.
    // Give the renderer a beat to paint the freshest model, then read #statusbar.
    await sleep(300);
    const rendered = await evalR(win, 'document.getElementById("statusbar") && document.getElementById("statusbar").innerHTML');
    receipt.rendered_excerpt = typeof rendered === "string" ? rendered.slice(0, 400) : null;
    const hasUnavailableWarn = typeof rendered === "string" && rendered.includes("concurrency count unavailable");
    if (authorized) {
      const paintedCount = typeof rendered === "string"
        && rendered.includes("sb-count")
        && /\d+\/\d+/.test(rendered)
        && rendered.includes("subscriptions");
      receipt.checks.rendered_shows_count = paintedCount;
      receipt.checks.rendered_no_unavailable_warn = !hasUnavailableWarn;
    } else {
      // honest fail-closed: the warn is CORRECT here (nothing authorized to count)
      receipt.checks.rendered_shows_unavailable_warn = hasUnavailableWarn;
    }

    // honest owed note carried into the receipt for the reader (dynamic per-session tracking → 16F)
    receipt.live_session_tracking_owed = "16F (in_use tracks 0 held-by-shell now; dynamic per-session count owed)";

    const renderOk = authorized
      ? (receipt.checks.rendered_shows_count && receipt.checks.rendered_no_unavailable_warn)
      : receipt.checks.rendered_shows_unavailable_warn;

    receipt.ok = sourced && countHonest && renderOk;
  } catch (e) {
    receipt.error = `${e && e.name}: ${e && e.message}`;
    if (log) log(`[selfcheck:statusbar] crashed: ${e && e.message}`);
  }

  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    if (log) log(`[selfcheck:statusbar] could not write receipt: ${e && e.message}`);
  }
  if (log) log(`[selfcheck:statusbar] ok=${receipt.ok} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runStatusBarSelfCheck: run, RECEIPT_PATH };
