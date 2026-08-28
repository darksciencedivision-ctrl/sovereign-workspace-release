"use strict";
/**
 * Phase 16C in-Electron governed-spawn self-check (D-P16-0 binding, per-track).
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer) and proves that pane 1 — the
 * conductor-first CONDUCTOR node (§12.4) — is GOVERNED-BORN this launch through the Python governed
 * spawn path (conductor_pane_spawn.spawn_conductor_pane), SOURCED from the bounded emitter
 * (tools/live/emit_conductor_spawn --emit-conductor-spawn), not from a hardcoded node_state string. It
 * writes a machine-readable receipt so the gate closes on runtime evidence, not headless-only tests.
 *
 * Flow:
 *   1. read the MAIN-side spawn feed (ctx.conductorSpawnFeed): assert a real subprocess feed was
 *      parsed (ok:true, the pinned schema) and it is a governed spawn (spawned:true) — the load-bearing
 *      proof pane 1 went through the live-gate chain, not a JS placeholder;
 *   2. assert the governed facts on the feed: node_state "awaiting_live_conductor" (the interactive
 *      `claude` ConPTY drive is the operator-run surface, §6 — deferred, not naked), the launch is
 *      INTERACTIVE (one_shot:false, no `-p`/`--output-format`/json in argv), env_credential_scrubbed,
 *      and D-LOOP-1 is proven: torn_down + governor_released (the I-X3 terminal was released);
 *   3. read the MAIN-side conductor state (ctx.conductorState): assert spawnGoverned:true,
 *      spawnSourced:true, and nodeState == the sourced feed's node_state (no drift);
 *   4. read the RENDERED .cbadge text off pane 1 and assert it carries that same node_state — so the
 *      Python governed spawn, the main state, and the pixel all agree;
 *   5. write the receipt. The caller tears down (no orphan PTY/gateway, D-LOOP-1) and exits pass/fail.
 *
 * Load-bearing: if the wiring reverted to the hardcoded node_state, ctx.conductorSpawnFeed().ok would
 * be false (no subprocess parsed) and conductorState().spawnGoverned would be false — this FAILS.
 *
 * No supervision is required: the conductor pane is a governed PLACEHOLDER (sessionId null, no naked
 * session — invariant 2) created conductor-first on launch; the governed spawn feed is sourced before
 * the window renders. This self-check makes NO live `claude` call (the emitter already deferred it and
 * tore its terminal down); it only inspects the sourced governed record.
 */
const fs = require("fs");
const path = require("path");

const RECEIPT_PATH = path.resolve(
  __dirname, "..", "..", "..", "docs", "evidence", "receipts", "PHASE16C_SPAWN_SELFCHECK.json"
);
const FEED_SCHEMA = "conductor_spawn_feed@1.0";
const BANNED_FLAGS = ["-p", "--output-format", "json"];

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
  const { win, conductorState, conductorSpawnFeed, log } = ctx;
  const receipt = {
    check: "phase-16c.spawn",
    started: new Date().toISOString(),
    ok: false,
    // main-side: was pane 1 GOVERNED-BORN via the Python governed spawn path?
    feed_ok: false,
    feed_schema: null,
    feed_error: null,
    spawned: false,
    node_state: null,
    // governed facts on the feed
    interactive: false,
    argv: null,
    no_headless_flags: false,
    env_credential_scrubbed: false,
    torn_down: false,
    governor_released: false,
    // conductor state (drift proof)
    spawn_governed: false,
    spawn_sourced: false,
    state_node_state: null,
    // renderer-side
    conductor_pane_id: null,
    badge_rendered: false,
    badge_text: null,
    rendered_carries_node_state: false,
    error: null,
  };
  try {
    // 1. MAIN-side spawn feed — the load-bearing proof pane 1 went through the governed spawn path.
    const src = (typeof conductorSpawnFeed === "function" ? conductorSpawnFeed() : null) || {};
    const feed = src.feed || {};
    receipt.feed_ok = src.ok === true;
    receipt.feed_schema = feed.schema || null;
    receipt.feed_error = src.error || null;
    receipt.spawned = feed.spawned === true;
    receipt.node_state = feed.node_state || null;
    if (!receipt.feed_ok) throw new Error(`conductor spawn feed was not sourced from Python (ok:false): ${receipt.feed_error || "unknown"}`);
    if (receipt.feed_schema !== FEED_SCHEMA) throw new Error(`sourced feed carries an unexpected schema: ${receipt.feed_schema}`);
    if (!receipt.spawned) throw new Error(`pane 1 was not governed-born (spawned:false, reason: ${feed.reason || "unknown"})`);

    // 2. the governed facts — interactive launch, credential-scrubbed, D-LOOP-1 teardown proven.
    if (receipt.node_state !== "awaiting_live_conductor") throw new Error(`node_state ${JSON.stringify(receipt.node_state)} != awaiting_live_conductor (deferred operator-run ConPTY, §6)`);
    const launch = feed.launch || {};
    receipt.argv = Array.isArray(launch.argv) ? launch.argv.slice() : null;
    receipt.interactive = launch.interactive === true && launch.one_shot === false;
    receipt.no_headless_flags = Array.isArray(receipt.argv) && !BANNED_FLAGS.some((f) => receipt.argv.includes(f));
    receipt.env_credential_scrubbed = launch.env_credential_scrubbed === true;
    receipt.torn_down = feed.torn_down === true;
    receipt.governor_released = feed.governor_released === true;
    if (!receipt.interactive) throw new Error("launch is not interactive (one_shot must be false — the operator drives it, OP-8 §13.1)");
    if (!receipt.no_headless_flags) throw new Error(`launch argv carries a one-shot/headless flag: ${JSON.stringify(receipt.argv)}`);
    if (!receipt.env_credential_scrubbed) throw new Error("launch env was not credential-scrubbed (§2.2)");
    if (!receipt.torn_down || !receipt.governor_released) throw new Error("D-LOOP-1 not proven: the governed spawn's I-X3 terminal was not torn down/released");

    // 3. MAIN-side conductor state — spawnGoverned + nodeState sourced (no drift from the feed).
    const st = (typeof conductorState === "function" ? conductorState() : null) || {};
    receipt.spawn_governed = st.spawnGoverned === true;
    receipt.spawn_sourced = st.spawnSourced === true;
    receipt.state_node_state = st.nodeState || null;
    receipt.conductor_pane_id = st.paneId || null;
    if (!receipt.spawn_governed) throw new Error("conductorState().spawnGoverned is not true — node_state is not sourced from the governed spawn");
    if (!receipt.conductor_pane_id) throw new Error("no conductor pane was created (conductor-first pane 1 missing)");
    if (receipt.state_node_state !== receipt.node_state) {
      throw new Error(`state node_state ${JSON.stringify(receipt.state_node_state)} != sourced feed node_state ${JSON.stringify(receipt.node_state)}`);
    }

    // 4. RENDERER-side: wait for the badge, then assert it carries the sourced node_state.
    const paneId = receipt.conductor_pane_id;
    receipt.badge_rendered = await waitFor(async () => {
      const b = await evalR(win, `window.__sovereignSelfCheck.conductorBadgeText(${JSON.stringify(paneId)})`);
      return !!(b && b.isConductor && typeof b.text === "string" && b.text.indexOf(receipt.node_state) >= 0);
    }, 20000, 200);
    const badge = await evalR(win, `window.__sovereignSelfCheck.conductorBadgeText(${JSON.stringify(paneId)})`);
    receipt.badge_text = badge ? badge.text : null;
    receipt.rendered_carries_node_state = !!(receipt.badge_text && receipt.badge_text.indexOf(receipt.node_state) >= 0);
    if (!receipt.badge_rendered || !receipt.rendered_carries_node_state) {
      throw new Error(`the CONDUCTOR badge never rendered the sourced node_state; text=${JSON.stringify(receipt.badge_text)}`);
    }

    log(`[selfcheck] conductor pane GOVERNED-BORN: node_state=${receipt.node_state} · argv=${JSON.stringify(receipt.argv)} · torn_down=${receipt.torn_down} released=${receipt.governor_released}`);
    receipt.ok = receipt.feed_ok && receipt.spawned && receipt.interactive && receipt.no_headless_flags
      && receipt.env_credential_scrubbed && receipt.torn_down && receipt.governor_released
      && receipt.spawn_governed && receipt.rendered_carries_node_state;
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
  log(`[selfcheck] conductor-spawn ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runConductorSpawnSelfCheck: run, RECEIPT_PATH };
