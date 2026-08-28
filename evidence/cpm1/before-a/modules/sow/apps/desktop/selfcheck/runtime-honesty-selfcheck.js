"use strict";
/**
 * Phase 19 unit 19.7 in-Electron self-check (D-P16-0 binding) — THE RUNTIME TELLS THE TRUTH ABOUT
 * ITS OWN FAILURES.
 *
 * WHY IT EXISTS. Three defects in the audited range are all the same defect wearing different
 * clothes: the shell reporting a state it had not established. `stop()` awaited a close that an open
 * socket could hold forever (U334) — an unbounded wait after `event.preventDefault()`, i.e. a shell
 * that says it is quitting and does not; `connectionState` answered `connected` off any timestamp
 * at all (U335) — a dead MCP subprocess behind a live PTY reported as a working node; and an
 * unreadable orchestration feed was shaped as an empty one (U336) — "I cannot see" rendered as
 * "nothing happened". The headless suite drives the modules. What it cannot show is the same code
 * inside the packaged runtime, which is the whole reason D-P16-0 exists: 14A shipped a shell that
 * passed headless tests and failed at first launch.
 *
 * The legs, in the order they run:
 *
 *  A. THE GATEWAY STOPS INSIDE ITS BUDGET, IN THIS RUNTIME, WITH A SOCKET HELD OPEN. A real
 *     `SovereignControlServer` (the production class) is started on loopback inside Electron's main
 *     process; a real socket is opened against it and left open; `stop()` is called with a stated
 *     budget and must RESOLVE — the measured wall-clock is in the receipt. A credential is issued to
 *     a NAMED node first, and the same node is read back afterwards, because "every credential is
 *     revoked" asserted against a name that was never a node is true before the code under test runs
 *     (gate-validator round 1, BLOCKING-2). Under the audited code `stop()` never resolves here; this
 *     leg would end on its own `STOP_CEILING_MS` race and report `__unbounded` — the leg finishes,
 *     the shutdown does not, and the earlier version of this sentence blurred the two.
 *  F. THE DEFAULTS PRODUCTION ACTUALLY USES. Every other leg injects its own window and budget, so
 *     `DEFAULT_STALE_AFTER_MS` and `DEFAULT_STOP_TIMEOUT_MS` — which are what `main.js` runs on,
 *     since it passes neither — were graded by nothing. A default-constructed server is asked for
 *     both, in this runtime.
 *  B. THE STALE WINDOW, MEASURED ACROSS A REAL LOOPBACK REQUEST. A second production server, given
 *     an injected clock and a small window, is called over real HTTP by this process. Its state goes
 *     `configured` → `connected` → (clock advanced) `stale` → `connected` again on the next request.
 *     The last transition is the one that matters as much as the first: staleness is UNVERIFIED and
 *     must not pin a node.
 *  C. THE ASSIGNMENT GATE, ON THAT SAME SERVER. The production `assignmentRefusal` is asked about a
 *     worker record that is `running`/`READY` in every way a pane can be, over a node whose session
 *     has gone stale — and refuses, retryably, naming the age. Then the node calls again and the
 *     same record is assignable. This is the audited case reproduced and closed in the runtime.
 *  D. THE INSPECTOR, THROUGH THE REAL BRIDGE. `window.sovereign.inspector()` — the preload channel
 *     the drawer uses — is read and the INVARIANT is asserted, whichever way this host answers:
 *     `ok:true` requires both halves readable, and an unreadable half carries null counts rather
 *     than zeroes. Both branches are honest, and the receipt records which one this host produced.
 *  E. THE UNREADABLE BRANCH, FORCED, AND WHAT THE OPERATOR SEES. The production
 *     `fetchOperationalState` is called with a python binary that does not exist, so the emitter
 *     genuinely cannot run: the model must carry `available:false` and null (never zero) counts.
 *     That model is then painted by the PRODUCTION `renderInspector` in the real renderer — three
 *     times, because the rule has three cases and the first version of this leg only checked one and
 *     failed itself on a legitimate zero: nothing readable (the fail-closed banner, no count of
 *     anything), the LIVE half unreadable beside real legacy counts, and the LEGACY half unreadable
 *     beside real live counts. The unreadable side must say UNREADABLE and print no number; the
 *     readable side must still print its own. The pixel, not just the object.
 *
 * WHAT IS CHECK-OWNED, said here and in the receipt: legs A–C use the production class and the
 * production gate but on servers this CHECK starts, because stopping the shell's own live gateway
 * mid-run would tear down the very runtime being measured; the worker record in leg C is the
 * check's, because no worker was launched (this check starts no model and spends no live exchange);
 * leg E's failing python path is the check's, deliberately, since a real emitter failure cannot be
 * summoned on demand. Leg D reads the shell's OWN gateway and its OWN emitter with nothing injected.
 *
 * U334's other half — that `teardown()` is where the gateway stop now lives — is NOT measured here:
 * this check writes its receipt before the shell's teardown runs, and a check that quit the shell to
 * observe it would have nothing left to write with. It is covered by a source pin
 * (`test/runtime-honesty-wiring.test.js`) and named as the weaker evidence it is.
 *
 * It starts no model, spends no live exchange, touches no credential, and every socket and server it
 * creates is closed inside this unit (D-LOOP-1).
 */
const fs = require("fs");
const net = require("net");
const path = require("path");
const { receiptPath } = require("./receipt-path");
const { sourceIdentity } = require("./voice-conductor-selfcheck");
const { SovereignControlServer } = require("../control/sovereign-control-server");
const { assignmentRefusal } = require("../control/assignment-gate");
const { fetchOperationalState } = require("../inspector/operational-source");

const RECEIPT_STAMP = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
const RECEIPT_UNIT = String(process.env.SOW_SELFCHECK_UNIT || "run")
  .replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 40);
const RECEIPT_PATH = receiptPath(
  `PHASE19_7_RUNTIME_HONESTY_SELFCHECK_${RECEIPT_UNIT}_${RECEIPT_STAMP}.json`);

/** Leg A's budget, and the ceiling this leg is allowed to take. The budget is deliberately small:
 *  the property is that the wait ENDS, and a small budget makes a regression to the unbounded await
 *  unmistakable rather than slow. */
const STOP_BUDGET_MS = 800;
const STOP_CEILING_MS = 5000;
/** Leg B/C's staleness window. Small for the same reason — the production default is 180 s, which
 *  is the MCP client's own call ceiling, and waiting that out would prove nothing extra. */
const STALE_WINDOW_MS = 5000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function evalR(win, expr) {
  try { return await win.webContents.executeJavaScript(expr); } catch (e) { return { __error: String(e && e.message) }; }
}

/** A worker record that is, by every fact a PANE can present, ready for work. */
const readyWorkerRecord = () => ({ nodeId: "selfcheck-w-1", state: "running", operationalState: "READY" });

async function legStopIsBounded(receipt) {
  const server = new SovereignControlServer({ log: () => {} });
  let socket = null;
  try {
  const port = await server.start();
  // A credential for a node that EXISTS. The first version asserted revocation against the name
  // "anyone", which was never a node and answers `disconnected` before `stop()` has run at all — so
  // deleting the revocation entirely passed this leg (gate-validator round 1, BLOCKING-2).
  const token = server.issueCredential({ node_id: "selfcheck-revoked", role: "worker", project_id: "proj" });
  const beforeStop = server.connectionState("selfcheck-revoked");
  socket = net.connect(port, "127.0.0.1");
  await new Promise((resolve) => { socket.once("connect", resolve); socket.once("error", resolve); });
  const started = Date.now();
  let outcome = null;
  outcome = await Promise.race([
    server.stop({ timeoutMs: STOP_BUDGET_MS }),
    sleep(STOP_CEILING_MS).then(() => ({ __unbounded: true })),
  ]);
  const waited = Date.now() - started;
  const afterStop = server.connectionState("selfcheck-revoked");
  receipt.legs.A_stop_bounded = {
    held_open_socket: true, budget_ms: STOP_BUDGET_MS, waited_ms: waited,
    outcome, resolved_within_ceiling: !(outcome && outcome.__unbounded),
    node_before_stop: beforeStop, node_after_stop: afterStop,
    identity_after_stop: server.identityFor(token),
    port_released: server.port === null,
  };
  receipt.checks.stop_resolves_with_a_connection_open = Boolean(outcome && !outcome.__unbounded);
  receipt.checks.stop_reports_what_it_did = Boolean(outcome && !outcome.__unbounded
    && typeof outcome.closed === "boolean" && typeof outcome.forced === "boolean"
    && typeof outcome.timed_out === "boolean");
  receipt.checks.stop_revoked_every_credential = beforeStop.state === "configured"
    && afterStop.state === "disconnected" && server.identityFor(token) === null;
  } finally {
    if (socket) socket.destroy();
    await server.stop({ timeoutMs: STOP_BUDGET_MS });
  }
}

/**
 * The values PRODUCTION runs on. Every other leg here, and every headless test, injects its own
 * window and budget — so the two defaults were graded by nothing at all, and the gate-validator's
 * round-1 mutations of both survived the whole suite AND the first version of this receipt. `main.js`
 * constructs the gateway with no `staleAfterMs` and calls `stop()` with no argument, so these two
 * constants ARE U334's bound and U335's window in the shell an operator launches.
 */
async function legProductionDefaults(receipt) {
  const server = new SovereignControlServer({ log: () => {} });
  try {
  server.issueCredential({ node_id: "selfcheck-default", role: "worker", project_id: "proj" });
  const window = server.connectionState("selfcheck-default").stale_after_ms;
  await server.start();
  const outcome = await server.stop();
  receipt.legs.F_production_defaults = {
    stale_after_ms: window, stop_timeout_ms: outcome.timeout_ms,
    justification: "the staleness window is AppControlClient's own 180 s per-call ceiling "
      + "(mcp_server/sovereign_tools.py:40), so a node inside its longest possible single call is fresh",
  };
  receipt.checks.production_staleness_window_is_the_call_ceiling = window === 180000;
  receipt.checks.production_stop_budget_is_bounded = outcome.timeout_ms === 5000;
  } finally {
    await server.stop({ timeoutMs: STOP_BUDGET_MS });
  }
}

async function legStaleWindowAndGate(receipt) {
  let clock = Date.now();
  const server = new SovereignControlServer({
    handlers: { echo: () => ({ ok: true }) },
    staleAfterMs: STALE_WINDOW_MS, now: () => clock, log: () => {},
  });
  const port = await server.start();
  const token = server.issueCredential({
    node_id: "selfcheck-w-1", role: "worker", project_id: "proj",
  });
  const call = async () => {
    const response = await fetch(`http://127.0.0.1:${port}/v1/tools/call`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ operation: "echo", arguments: {} }),
    });
    return response.status;
  };
  try {
    const beforeAnyCall = server.connectionState("selfcheck-w-1");
    const status = await call();
    const afterCall = server.connectionState("selfcheck-w-1");
    const assignableFresh = assignmentRefusal({
      nodeId: "selfcheck-w-1", record: readyWorkerRecord(), mcp: afterCall,
    });
    clock += STALE_WINDOW_MS + 1;
    const aged = server.connectionState("selfcheck-w-1");
    const refusedStale = assignmentRefusal({
      nodeId: "selfcheck-w-1", record: readyWorkerRecord(), mcp: aged,
    });
    await call();
    const recovered = server.connectionState("selfcheck-w-1");
    const assignableAgain = assignmentRefusal({
      nodeId: "selfcheck-w-1", record: readyWorkerRecord(), mcp: recovered,
    });

    receipt.legs.B_stale_window = {
      request_status: status, before_any_call: beforeAnyCall, after_call: afterCall,
      after_window_elapsed: aged, after_next_call: recovered, window_ms: STALE_WINDOW_MS,
    };
    receipt.legs.C_assignment_gate = {
      worker_record: readyWorkerRecord(),
      fresh_refusal: assignableFresh, stale_refusal: refusedStale,
      refusal_after_recovery: assignableAgain,
    };
    receipt.checks.never_called_is_configured_not_connected = beforeAnyCall.state === "configured";
    receipt.checks.a_real_request_makes_it_connected = afterCall.state === "connected" && status === 200;
    receipt.checks.silence_past_the_window_is_stale = aged.state === "stale" && aged.fresh === false;
    receipt.checks.stale_carries_the_age_of_its_evidence =
      Number.isFinite(aged.last_seen_age_ms) && aged.last_seen_age_ms > STALE_WINDOW_MS;
    receipt.checks.a_ready_pane_over_a_stale_node_is_refused =
      Boolean(refusedStale && refusedStale.code === "mcp_unverified" && refusedStale.retryable === true);
    receipt.checks.a_fresh_node_is_assignable = assignableFresh === null;
    receipt.checks.staleness_does_not_pin_the_worker = assignableAgain === null
      && recovered.state === "connected";
  } finally {
    await server.stop({ timeoutMs: STOP_BUDGET_MS });
  }
}

async function legInspectorInvariant(ctx, receipt) {
  const { win } = ctx;
  const res = await evalR(win, "window.__sovereignSelfCheck.inspectorFetch()");
  const operational = (res && res.operational) || null;
  const operationalAvailable = Boolean(operational && operational.available === true);
  const legacyAvailable = Boolean(res && res.model && res.summary);
  const bothReadable = operationalAvailable && legacyAvailable;
  // Whatever this host answered, the CLAIM must match the evidence in both directions.
  const okMatchesReadability = Boolean(res) && (res.ok === true) === bothReadable;
  const unreadableCarriesNoCounts = operationalAvailable
    ? true
    : Boolean(operational && operational.summary === null && operational.tasks === null
      && operational.messages === null && operational.debates === null);
  receipt.legs.D_inspector_bridge = {
    ok: res && res.ok, error: (res && res.error) || null, legacy_error: (res && res.legacyError) || null,
    operational_available: operationalAvailable, legacy_available: legacyAvailable,
    operational_summary: operational ? operational.summary : null,
    nodes: operational && Array.isArray(operational.nodes) ? operational.nodes.length : null,
  };
  receipt.checks.inspector_ok_is_the_and_of_both_reads = okMatchesReadability;
  receipt.checks.inspector_unreadable_half_carries_no_counts = unreadableCarriesNoCounts;
}

async function legForcedUnreadable(ctx, receipt) {
  const model = await fetchOperationalState({
    cwd: ctx.repoRoot, projectId: "proj",
    storeRoot: path.join(ctx.repoRoot, ".sovereign_store"),
    // A binary that does not exist on any host: the emitter genuinely cannot run.
    python: "sovereign-no-such-python-19-7", pythonArgs: [], timeoutMs: 15000,
    nodes: [{ node_id: "selfcheck-w-1", ready: false, mcp_state: "stale" }],
  });
  const nullCounts = model.available === false && model.summary === null && model.tasks === null
    && model.messages === null && model.debates === null;
  const paint = async (payload) => {
    const painted = await evalR(ctx.win,
      `window.__sovereignSelfCheck.renderInspectorModel(${JSON.stringify(payload)})`);
    return typeof painted === "string" ? painted : "";
  };
  // E1 — NOTHING readable. The drawer must fall back to its fail-closed banner and print no number
  // that could be read as a count of anything.
  const nothingReadable = await paint({
    ok: false, error: "live orchestration: forced unreadable (19.7 self-check); control-plane channel forced unreadable",
    legacyError: "Error: control-plane channel not established (19.7 self-check)",
    model: null, summary: null, routingReadable: false,
  });
  // E2 — the LIVE half unreadable while the other carries REAL counts. This is the audited screen:
  // the operational feed failed, and what used to be painted there was `0 tasks · 0 messages ·
  // 0 debates`. The degradation must also be PER-HALF — an inspector that blanked the readable side
  // would be honest and useless — so the legacy counts have to survive on the same screen.
  const liveHalfUnreadable = await paint({
    ok: false, error: "live orchestration: forced unreadable (19.7 self-check)",
    operational: model, legacyError: null,
    model: { tasks: [{ taskId: "t-selfcheck", contextRouted: null, gateChain: [], artifacts: [] }],
      unattributed: { artifacts: [], gates: [] }, anomalies: [] },
    summary: { taskCount: 7, artifactCount: 3, gateCount: 2, unattributedCount: 0, anomalyCount: 0 },
    routingReadable: true,
  });
  // E3 — the OTHER half unreadable, against a readable live feed (this one's data is the check's:
  // the point is the renderer's rule, and a genuinely readable emitter is leg D's business).
  const legacyHalfUnreadable = await paint({
    ok: false, error: "control-plane channel forced unreadable (19.7 self-check)",
    operational: { ok: true, available: true, schema: "sovereign_operational_state@1.0",
      project_id: "proj", tasks: [], messages: [], debates: [], nodes: [],
      summary: { task_count: 4, message_count: 5, debate_count: 1, open_debate_count: 0 } },
    legacyError: "Error: control-plane channel not established (19.7 self-check)",
    model: null, summary: null, routingReadable: false,
  });
  const cut = (html) => {
    const at = html.indexOf("ARTIFACT / GATE EVIDENCE");
    return at < 0 ? { live: html, legacy: "" } : { live: html.slice(0, at), legacy: html.slice(at) };
  };
  const liveSection = (html) => cut(html).live;
  const legacySection = (html) => cut(html).legacy;
  receipt.legs.E_forced_unreadable = {
    available: model.available, error: model.error,
    summary: model.summary, tasks: model.tasks, messages: model.messages, debates: model.debates,
    live_nodes_preserved: Array.isArray(model.nodes) ? model.nodes.length : null,
    rendered_nothing_readable: nothingReadable.slice(0, 700),
    rendered_live_half_unreadable: liveHalfUnreadable.slice(0, 900),
    rendered_legacy_half_unreadable: legacyHalfUnreadable.slice(0, 900),
  };
  receipt.checks.forced_unreadable_feed_has_null_counts = nullCounts;
  receipt.checks.forced_unreadable_feed_keeps_live_nodes =
    Array.isArray(model.nodes) && model.nodes.length === 1;
  receipt.checks.rendered_says_unreadable =
    liveHalfUnreadable.includes("shared governed state UNREADABLE")
    && legacyHalfUnreadable.includes("artifact/gate evidence UNREADABLE");
  // The load-bearing negatives: an unreadable half prints no count, and with nothing readable at all
  // the drawer prints no count anywhere.
  receipt.checks.rendered_prints_no_fabricated_zero_counts =
    liveHalfUnreadable.includes("this is not a count of zero")
    && !/\d+\s+(tasks|messages|debates)/.test(liveSection(liveHalfUnreadable))
    && !/\d+\s+(tasks|artifacts|gates|messages|debates)/.test(nothingReadable)
    && nothingReadable.includes("inspector unavailable")
    // BOTH directions. Round 2 restored the fabricated zeros in the LEGACY unreadable branch and
    // this check still passed, because it only ever looked at the live half (MEDIUM-B) — the leg's
    // own prose said "in both directions" and one direction was graded.
    && !/\d+\s+(tasks|artifacts|gates)/.test(legacySection(legacyHalfUnreadable))
    && legacySection(legacyHalfUnreadable).includes("this is not a count of zero");
  // …and the readable half still prints ITS counts, in both directions.
  receipt.checks.rendered_degrades_per_half_not_globally =
    liveHalfUnreadable.includes("7 tasks") && liveHalfUnreadable.includes("3 artifacts")
    && legacyHalfUnreadable.includes("4 tasks") && legacyHalfUnreadable.includes("5 messages");
  // Clear the check's fabricated models out of the drawer. What is left is a banner naming THIS
  // check — not what an operator's refresh would show, which is what the previous comment claimed
  // (spec-auditor, MINOR): the drawer is repainted from a real read the next time it is opened.
  const cleared = await evalR(ctx.win,
    "window.__sovereignSelfCheck.renderInspectorModel({ ok: false, error: 'cleared by the 19.7 self-check — reopen the drawer for a real read' })");
  receipt.checks.drawer_cleanup_is_visible = typeof cleared === "string"
    && cleared.includes("cleared by the 19.7 self-check");
}

async function run(ctx) {
  const { log } = ctx;
  const receipt = {
    schema: "phase19_7_runtime_honesty_selfcheck@1.0",
    check: "runtime-honesty",
    unit: RECEIPT_UNIT,
    ok: false,
    started: new Date().toISOString(),
    finished: null,
    pid: process.pid,
    electron: process.versions.electron || null,
    node: process.versions.node || null,
    platform: `${process.platform}-${process.arch}`,
    source: sourceIdentity(),
    live_exchanges: 0,
    check_owned_bindings: [
      "legs A–C and F run production classes on servers this CHECK starts (stopping the shell's own "
        + "live gateway would tear down the runtime under measurement)",
      "leg C's worker launch record is the check's — no worker session was launched",
      "leg E's failing python binary is the check's, deliberately: a real emitter failure cannot be summoned",
      "leg E's READABLE halves are fabricated by the check (E2's '7 tasks · 3 artifacts' legacy model, "
        + "E3's '4 tasks · 5 messages' operational feed) — they exist to prove the degradation is "
        + "per-half; leg D is where a genuinely readable/unreadable pair is read from this host",
    ],
    not_measured_here: [
      "that teardown() is where the gateway stop now lives (U334's other half) — the receipt is "
        + "written before teardown runs; covered by a source pin in test/runtime-honesty-wiring.test.js",
      "that readiness still PROVOKES a stale worker rather than pinning it — driven headlessly in "
        + "test/worker-readiness.test.js against the production module; no pane is spawned here",
      "the 503 'shutting down' answer — no leg here provokes a request mid-shutdown; it is driven "
        + "over a real socket in test/sovereign-control-server.test.js",
      "`inspector_unreadable_half_carries_no_counts` measures nothing when leg D's host answers a "
        + "READABLE operational feed (it short-circuits true) — read D_inspector_bridge to see which "
        + "case this run actually had; leg E is where the unreadable shape is measured",
    ],
    checks: {},
    legs: {},
    failed_checks: [],
  };

  try {
    await legStopIsBounded(receipt);
    await legProductionDefaults(receipt);
    await legStaleWindowAndGate(receipt);
    await legInspectorInvariant(ctx, receipt);
    await legForcedUnreadable(ctx, receipt);
  } catch (e) {
    receipt.error = `${e && e.name}: ${e && e.message}`;
    if (log) log(`[selfcheck:runtime-honesty] crashed: ${e && e.message}`);
  }

  receipt.failed_checks = Object.entries(receipt.checks).filter(([, v]) => v !== true).map(([k]) => k);
  // A leg that could not be measured FAILS the check: an absent boolean is not a pass.
  const expected = [
    "stop_resolves_with_a_connection_open", "stop_reports_what_it_did",
    "stop_revoked_every_credential", "production_staleness_window_is_the_call_ceiling",
    "production_stop_budget_is_bounded", "never_called_is_configured_not_connected",
    "a_real_request_makes_it_connected", "silence_past_the_window_is_stale",
    "stale_carries_the_age_of_its_evidence", "a_ready_pane_over_a_stale_node_is_refused",
    "a_fresh_node_is_assignable", "staleness_does_not_pin_the_worker",
    "inspector_ok_is_the_and_of_both_reads", "inspector_unreadable_half_carries_no_counts",
    "forced_unreadable_feed_has_null_counts", "forced_unreadable_feed_keeps_live_nodes",
    "rendered_says_unreadable", "rendered_prints_no_fabricated_zero_counts",
    "rendered_degrades_per_half_not_globally", "drawer_cleanup_is_visible",
  ];
  receipt.missing_checks = expected.filter((name) => !(name in receipt.checks));
  receipt.ok = !receipt.error && receipt.missing_checks.length === 0
    && receipt.failed_checks.length === 0;
  receipt.finished = new Date().toISOString();

  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    if (log) log(`[selfcheck:runtime-honesty] could not write receipt: ${e && e.message}`);
  }
  if (log) {
    log(`[selfcheck:runtime-honesty] ok=${receipt.ok} failed=${receipt.failed_checks.join(",") || "-"} `
      + `missing=${receipt.missing_checks.join(",") || "-"} → ${RECEIPT_PATH}`);
  }
  return receipt;
}

module.exports = { runRuntimeHonestySelfCheck: run, RECEIPT_PATH };
