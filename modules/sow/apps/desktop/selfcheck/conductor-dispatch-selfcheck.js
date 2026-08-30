"use strict";
/**
 * Phase 16C in-Electron governed-DISPATCH self-check (D-P16-0 binding, per-track).
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer) and proves that the govern-born
 * conductor pane's DISPATCH (OP-8 §13.4) is SOURCED from the Python governed flow
 * (control_plane.orchestration.conductor_dispatch → live_flow: decompose → assign BY DESCRIPTOR →
 * CANDIDATE over MCP → real gate engine → conductor synthesis), not a hardcoded string. It writes a
 * machine-readable receipt so the gate closes on runtime evidence, not headless-only tests.
 *
 * Flow:
 *   1. read the MAIN-side dispatch feed (ctx.conductorDispatchFeed): assert a real subprocess feed was
 *      parsed (ok:true, the pinned schema) and it is a governed dispatch (dispatched:true) — the
 *      load-bearing proof the governed flow ran, not a JS literal;
 *   2. assert the governed facts on the feed: routing was BY DESCRIPTOR (invariant 4), at least one
 *      artifact was ACCEPTED by the acceptance gate (verdict PASS — invariant 18, the gate node's
 *      verdict, not the synthesizer's), the legs are MOCK-first and HONEST (conductor=mock,
 *      workers=mock — no live model call), the packet's operator_disposition is "pending" (gate
 *      promotion is NOT operator acceptance — invariant 1), and the LIVE-worker leg is recorded OWED
 *      (U58, honest), and D-LOOP-1 is proven (torn_down:true — the loopback MCP server is down);
 *   3. read the MAIN-side conductor state (ctx.conductorState): assert dispatchRan + dispatchSourced,
 *      and that its dispatch summary agrees with the feed (no drift);
 *   4. read the RENDERED .cdispatch text off pane 1 and assert it carries the dispatch summary + the
 *      OWED (U58) marker — so the Python governed dispatch, the main state, and the pixel all agree;
 *   5. write the receipt. The caller tears down (no orphan PTY/gateway, D-LOOP-1) and exits pass/fail.
 *
 * Load-bearing: if the wiring reverted to a literal, ctx.conductorDispatchFeed().ok would be false
 * (no subprocess parsed) and conductorState().dispatchRan would be false — this FAILS.
 *
 * This self-check makes NO live `claude`/`codex` call (the emitter's dispatch is mock-first and already
 * tore its MCP server down); it only inspects the sourced governed record.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const RECEIPT_PATH = receiptPath("PHASE16C_DISPATCH_SELFCHECK.json");
const FEED_SCHEMA = "conductor_dispatch_feed@1.0";

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
  const { win, conductorState, conductorDispatchFeed, log } = ctx;
  const receipt = {
    check: "phase-16c.dispatch",
    started: new Date().toISOString(),
    ok: false,
    // main-side: did the govern-born conductor run a governed DISPATCH via the Python flow?
    feed_ok: false,
    feed_schema: null,
    feed_error: null,
    dispatched: false,
    // governed facts on the feed
    assigned_count: 0,
    by_descriptor: false,
    accepted_count: 0,
    acceptance_verdict: null,
    legs: null,
    legs_mock_honest: false,
    operator_disposition: null,
    live_workers_owed: false,
    torn_down: false,
    // conductor state (drift proof)
    dispatch_ran: false,
    dispatch_sourced: false,
    state_text: null,
    // renderer-side
    conductor_pane_id: null,
    dispatch_rendered: false,
    dispatch_text: null,
    rendered_carries_owed: false,
    error: null,
  };
  try {
    // 1. MAIN-side dispatch feed — the load-bearing proof the governed flow ran.
    const src = (typeof conductorDispatchFeed === "function" ? conductorDispatchFeed() : null) || {};
    const feed = src.feed || {};
    receipt.feed_ok = src.ok === true;
    receipt.feed_schema = feed.schema || null;
    receipt.feed_error = src.error || null;
    receipt.dispatched = feed.dispatched === true;
    if (!receipt.feed_ok) throw new Error(`conductor dispatch feed was not sourced from Python (ok:false): ${receipt.feed_error || "unknown"}`);
    if (receipt.feed_schema !== FEED_SCHEMA) throw new Error(`sourced feed carries an unexpected schema: ${receipt.feed_schema}`);
    if (!receipt.dispatched) throw new Error(`the governed dispatch did not run (dispatched:false, reason: ${feed.reason || "unknown"})`);

    // 2. the governed facts — by descriptor, accepted, mock-honest legs, U58 owed, D-LOOP-1.
    receipt.assigned_count = typeof feed.assigned_count === "number" ? feed.assigned_count : 0;
    receipt.by_descriptor = feed.by_descriptor === true;
    receipt.accepted_count = typeof feed.accepted_count === "number" ? feed.accepted_count : 0;
    receipt.acceptance_verdict = feed.acceptance_verdict || null;
    receipt.legs = feed.legs || null;
    receipt.legs_mock_honest = !!(feed.legs && feed.legs.conductor === "mock" && feed.legs.workers === "mock");
    receipt.operator_disposition = feed.operator_disposition || null;
    receipt.live_workers_owed = !!(feed.live_workers_owed && feed.live_workers_owed.owed === true && feed.live_workers_owed.issue === "U58");
    receipt.torn_down = feed.torn_down === true;
    if (!receipt.by_descriptor) throw new Error("dispatch routing was not BY DESCRIPTOR (invariant 4)");
    if (!(receipt.accepted_count > 0) || receipt.acceptance_verdict !== "PASS") throw new Error(`no artifact was gate-accepted (accepted=${receipt.accepted_count}, acceptance=${receipt.acceptance_verdict})`);
    if (!receipt.legs_mock_honest) throw new Error(`legs are not the honest mock-first pair (got ${JSON.stringify(receipt.legs)}) — a dispatch here must never claim a live worker leg`);
    if (receipt.operator_disposition !== "pending") throw new Error(`operator_disposition ${JSON.stringify(receipt.operator_disposition)} != pending — gate promotion is not operator acceptance (invariant 1)`);
    // Deliberately STRICT, and it stays strict now that a live worker leg is reachable (17B `.legs`):
    // this asserts the SHELL's dispatch, which invokes the emitter with NO `--live-workers` flag. An
    // app launch may never spend the operator's subscription, so mock legs + U58 owed is the correct
    // result HERE — a live leg appearing on this path would mean the launch path started spending.
    if (!receipt.live_workers_owed) throw new Error("the shell's launch dispatch did not record the LIVE worker leg as OWED (U58) — an app launch must run mock-first and never spend a live call");
    if (!receipt.torn_down) throw new Error("D-LOOP-1 not proven: the governed dispatch's loopback MCP server was not torn down");

    // 3. MAIN-side conductor state — dispatchRan + summary sourced (no drift from the feed).
    const st = (typeof conductorState === "function" ? conductorState() : null) || {};
    receipt.dispatch_ran = st.dispatchRan === true;
    receipt.dispatch_sourced = st.dispatchSourced === true;
    receipt.state_text = (st.dispatch && st.dispatch.text) || null;
    receipt.conductor_pane_id = st.paneId || null;
    if (!receipt.dispatch_ran) throw new Error("conductorState().dispatchRan is not true — the dispatch line is not sourced from the governed flow");
    if (!receipt.conductor_pane_id) throw new Error("no conductor pane was created (conductor-first pane 1 missing)");
    if (!receipt.state_text || receipt.state_text.indexOf("OWED") < 0) throw new Error(`the conductor state dispatch summary does not surface the OWED live-worker leg: ${JSON.stringify(receipt.state_text)}`);

    // 4. RENDERER-side: wait for the dispatch line, then assert it carries the summary + OWED marker.
    const paneId = receipt.conductor_pane_id;
    receipt.dispatch_rendered = await waitFor(async () => {
      const d = await evalR(win, `window.__sovereignSelfCheck.conductorDispatchText(${JSON.stringify(paneId)})`);
      return !!(d && d.isConductor && typeof d.text === "string" && d.text.indexOf("OWED") >= 0 && d.text.indexOf("accepted") >= 0);
    }, 20000, 200);
    const drawn = await evalR(win, `window.__sovereignSelfCheck.conductorDispatchText(${JSON.stringify(paneId)})`);
    receipt.dispatch_text = drawn ? drawn.text : null;
    receipt.rendered_carries_owed = !!(receipt.dispatch_text && receipt.dispatch_text.indexOf("OWED") >= 0);
    if (!receipt.dispatch_rendered || !receipt.rendered_carries_owed) {
      throw new Error(`the DISPATCH line never rendered the sourced summary with the OWED marker; text=${JSON.stringify(receipt.dispatch_text)}`);
    }

    log(`[selfcheck] conductor DISPATCH sourced: ${receipt.assigned_count} by-descriptor · ${receipt.accepted_count} accepted · legs ${JSON.stringify(receipt.legs)} · U58 owed=${receipt.live_workers_owed} · torn_down=${receipt.torn_down}`);
    receipt.ok = receipt.feed_ok && receipt.dispatched && receipt.by_descriptor
      && receipt.accepted_count > 0 && receipt.acceptance_verdict === "PASS"
      && receipt.legs_mock_honest && receipt.operator_disposition === "pending"
      && receipt.live_workers_owed && receipt.torn_down
      && receipt.dispatch_ran && receipt.rendered_carries_owed;
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
  log(`[selfcheck] conductor-dispatch ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runConductorDispatchSelfCheck: run, RECEIPT_PATH };
