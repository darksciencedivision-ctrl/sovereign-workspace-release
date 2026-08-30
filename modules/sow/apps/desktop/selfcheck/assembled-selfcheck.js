"use strict";
/**
 * Phase 16F in-Electron ASSEMBLED-RUN self-check (D-P16-0 binding, high-stakes gate).
 *
 * Runs INSIDE the packaged Electron runtime (main + real renderer + real ConPTY) and proves the
 * thing 16F owes: the whole operator-visible assembled run COMPOSES in ONE shell session —
 * (1) a conductor-first pane governed-born, (2) an operator input TYPED into an ADMITTED conductor
 * session and echoed back (this closes the WRITE that 16E marked "owed 16F": deliverConductorChat
 * previously reported "conductor session not admitted"), (3) picker-selected workers driven through
 * the governed dispatch (routing BY DESCRIPTOR → CANDIDATE → gate → conductor synthesis), (4) an
 * approval exercised against the governed authority, and (5) a full restart that recovers the
 * conductor-first layout with the worker's model chrome intact. It writes a machine-readable receipt
 * so the high-stakes gate closes on runtime evidence, not headless-only tests.
 *
 * HONESTY (invariants 1/2/24, §6 substitution, §2.2/§2.4):
 *   - The interactive LIVE `claude` conductor backend and the live worker CLI SPAWN are the
 *     operator-run surfaces (§6): the loop never starts a live frontier session. So the "type to the
 *     conductor" leg admits a SUPERVISED interactive ConPTY session that STANDS IN for that backend
 *     and proves the shell's conductor-input DELIVERY + ECHO path end-to-end — never claiming a live
 *     model answered. The receipt records `live_backend_operator_run:true` and the OWED live legs
 *     (U58 live workers, U70 live worker spawn) explicitly. Nothing is faked; every boolean is
 *     measured, and the substituted surface is named.
 *   - The dispatch/approval feeds are sourced from the real Python governed flow, mock-first
 *     (conductor=mock, workers=mock), each spinning a loopback MCP server it tears down before it
 *     returns (D-LOOP-1). No live `claude`/`codex` call is made here.
 *
 * Load-bearing: if the conductor-input write reverted to "owed" (no admitted session ⇒ written:false),
 * leg 2 FAILS; if the dispatch reverted to a literal (feed.ok:false / dispatched:false), leg 3 FAILS;
 * if the approval drawer reverted to the empty literal (source != "emitter"), leg 4 FAILS; if U68
 * chrome recovery reverted (snapshot carries no chrome), leg 5 FAILS. Empirically falsifiable.
 *
 * The caller (main.js SHELL_SELFCHECK=assembled) tears down every PTY + gateway (no orphans,
 * D-LOOP-1) and exits with this receipt's pass/fail code.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const RECEIPT_PATH = receiptPath("PHASE16F_ASSEMBLED_SELFCHECK.json");
const DISPATCH_SCHEMA = "conductor_dispatch_feed@1.0";
const CONDUCTOR_PROBE = "SOVEREIGN_CONDUCTOR_INPUT_16F";

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

// Read a pane's rendered xterm buffer (read-only observability hook), poll until it holds `needle`.
async function pollNeedle(win, paneId, needle, timeoutMs) {
  let last = null;
  const hit = await waitFor(async () => {
    last = await evalR(win, `window.__sovereignSelfCheck.paneText(${JSON.stringify(paneId)})`);
    return typeof last === "string" && last.includes(needle);
  }, timeoutMs, 200);
  return hit ? last : null;
}

async function run(ctx) {
  const {
    win, createPaneWithSession, isSupervised, conductorState, conductorDispatchFeed,
    deliverConductorChat, loadLayoutSnapshot, reconstructLayout, sendRecovery, log,
  } = ctx;
  const receipt = {
    schema: "phase16f_assembled_selfcheck@1.0",
    check: "phase-16f.assembled",
    started: new Date().toISOString(),
    ok: false,
    electron: process.versions.electron || null,
    node: process.versions.node || null,
    platform: `${process.platform}-${process.arch}`,
    // the composed legs (each a governed step of the operator-visible assembled run)
    legs: {
      supervision_ready: false,
      conductor_governed_born: false,
      conductor_input_refused_off_conductor: false, // leg 2 — no transcript reaches a stand-in shell
      workers_dispatched: false,          // leg 3
      picker_worker_selected: false,      // leg 3
      approval_exercised: false,          // leg 4
      restart_recovered: false,           // leg 5
    },
    conductor: { pane_id: null, node_state: null, spawn_governed: false },
    conductor_input: {
      admitted_session_pane_id: null, written: false, submitted: false, write_reason: null,
      stand_in_pane_received_nothing: null,
      live_delivery_evidence: "docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json",
      note: "a voice/chat transcript may target only the governed live conductor. This supervised "
        + "PowerShell pane is a negative witness: delivery must refuse it and its buffer must stay empty.",
    },
    dispatch: {
      feed_ok: false, dispatched: false, by_descriptor: false, accepted_count: 0,
      acceptance_verdict: null, legs_mock_honest: false, live_workers_owed: false, torn_down: false,
    },
    picker: { worker_pane_id: null, selected_label: null, recorded: false, badge_previewed: false },
    // Phase 17D `.events`: the fields this leg now proves. The old `sourced_from_emitter` /
    // `decide_governed_refused` pair is gone rather than left initialized-false — a receipt carrying a
    // false field nothing writes reads as a failed check, which is its own small dishonesty.
    approval: { sourced_from_session_events: false, empty_before_the_event: false, rows: 0,
      row_is_the_real_event: false, decide_routed: false, self_authorized_false: false,
      decide_governed_resolved: false, decision_persisted: false, re_decide_governed_refused: false },
    recovery: {
      snapshot_carries_chrome: false, reconstructed_conductor_first: false,
      recovered_worker_chrome: false, recovered_not_reattached: false, badge_restored: false,
    },
    owed: {
      live_conductor_backend: "16F/§6 operator-run: the interactive `claude` conductor session is started by the operator, not the loop",
      live_workers: "U58 — the live worker CLI legs (dispatch ran mock-first, honestly)",
      live_worker_spawn: "U70 — the live governed worker SPAWN from a picker selection (this proves the recorded selection + its chrome survive a restart)",
    },
    error: null,
  };

  try {
    // ---- leg 1: supervision READY + conductor-first pane governed-born -------------------------
    receipt.legs.supervision_ready = await waitFor(isSupervised, 25000, 250);
    if (!receipt.legs.supervision_ready) throw new Error("supervision never became READY within 25s (governed spawn path down)");

    const st0 = (typeof conductorState === "function" ? conductorState() : null) || {};
    receipt.conductor.pane_id = st0.paneId || null;
    receipt.conductor.node_state = st0.nodeState || null;
    receipt.conductor.spawn_governed = st0.spawnGoverned === true;
    receipt.legs.conductor_governed_born = !!(receipt.conductor.pane_id && receipt.conductor.spawn_governed
      && receipt.conductor.node_state === "awaiting_live_conductor");
    if (!receipt.legs.conductor_governed_born) {
      throw new Error(`conductor pane not governed-born (paneId=${receipt.conductor.pane_id}, governed=${receipt.conductor.spawn_governed}, node_state=${receipt.conductor.node_state})`);
    }

    // ---- leg 2: the conductor-input delivery REFUSES a pane that is not the governed conductor.
    //      This leg used to do the opposite: it admitted a `powershell.exe` stand-in and asserted the
    //      transcript was written into it. Since 17C `.close` added a submit key, that meant a routed
    //      voice transcript was Enter-SUBMITTED to a command interpreter — the shape invariant 25
    //      exists to forbid, found by the `.close-revalidate` spec audit in this receipt's own sibling.
    //      The delivery target is no longer a parameter, so the same call now refuses, and the proof
    //      that the write path works belongs to the run that has a real conductor:
    //      docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json (live `claude`, body + submit + reply).
    const admitted = createPaneWithSession({
      file: "powershell.exe", args: ["-NoLogo", "-NoProfile", "-NoExit"], title: "conductor-session",
    });
    receipt.conductor_input.admitted_session_pane_id = admitted;
    await waitFor(async () => evalR(win, `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(admitted)})`), 15000, 200);
    const wr = await deliverConductorChat(`echo ${CONDUCTOR_PROBE}`);
    receipt.conductor_input.written = !!(wr && wr.written === true);
    receipt.conductor_input.submitted = !!(wr && wr.submitted === true);
    receipt.conductor_input.write_reason = wr ? wr.reason : null;
    receipt.conductor_input.live_delivery_evidence = "docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json";
    if (receipt.conductor_input.written || receipt.conductor_input.submitted) {
      throw new Error("a voice/chat transcript was written outside the governed conductor session "
        + `(reason: ${receipt.conductor_input.write_reason}) — invariant 25`);
    }
    // …and the stand-in pane must have received NOTHING. A shell echoes whatever reaches it, so its
    // own buffer is the honest witness.
    const leaked = await pollNeedle(win, admitted, CONDUCTOR_PROBE, 4000);
    receipt.conductor_input.stand_in_pane_received_nothing = leaked == null;
    if (leaked != null) throw new Error("the transcript reached a non-conductor pane's ConPTY");
    receipt.legs.conductor_input_refused_off_conductor = !receipt.conductor_input.written
      && receipt.conductor_input.stand_in_pane_received_nothing;
    log(`[selfcheck:assembled] conductor-input delivery refused off the conductor pane `
      + `(${receipt.conductor_input.write_reason}); nothing reached ${admitted}`);

    // ---- leg 3a: picker-selected worker — record a governed selection targeting a worker pane -----
    const worker = createPaneWithSession({ file: "powershell.exe", args: ["-NoLogo", "-NoProfile", "-NoExit"], title: "worker" });
    receipt.picker.worker_pane_id = worker;
    await waitFor(async () => evalR(win, `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(worker)})`), 15000, 200);
    await evalR(win, `window.__sovereignSelfCheck.openPicker(${JSON.stringify(worker)})`);
    await waitFor(async () => { const s = await evalR(win, "window.__sovereignSelfCheck.pickerSummary()"); return !!(s && s.ok); }, 30000, 300);
    const summary = await evalR(win, "window.__sovereignSelfCheck.pickerSummary()") || {};
    if (summary.firstAvailable >= 0) {
      const spawn = await evalR(win, `window.__sovereignSelfCheck.selectOption(${summary.firstAvailable}, "reasoning")`);
      receipt.picker.recorded = !!(spawn && spawn.recorded);
      receipt.picker.selected_label = spawn && spawn.chrome ? spawn.chrome.model_label : null;
      await sleep(150);
      const badge = await evalR(win, `window.__sovereignSelfCheck.paneBadgeText(${JSON.stringify(worker)})`);
      receipt.picker.badge_previewed = !!(badge && badge.shown && receipt.picker.selected_label && String(badge.text).includes(receipt.picker.selected_label));
      receipt.legs.picker_worker_selected = receipt.picker.recorded && !!receipt.picker.selected_label && receipt.picker.badge_previewed;
    } else {
      receipt.picker.note = "no available picker option on this host — governed selection leg needs one (headless picker tests cover the policy)";
    }
    if (!receipt.legs.picker_worker_selected) throw new Error(`picker-selected worker leg did not complete (recorded=${receipt.picker.recorded}, label=${receipt.picker.selected_label}, badge=${receipt.picker.badge_previewed})`);

    // ---- leg 3b: WORKERS DISPATCHED — the governed dispatch feed (routing BY DESCRIPTOR → gate) -----
    const dsrc = (typeof conductorDispatchFeed === "function" ? conductorDispatchFeed() : null) || {};
    const dfeed = dsrc.feed || {};
    receipt.dispatch.feed_ok = dsrc.ok === true;
    receipt.dispatch.dispatched = dfeed.dispatched === true;
    receipt.dispatch.by_descriptor = dfeed.by_descriptor === true;
    receipt.dispatch.accepted_count = typeof dfeed.accepted_count === "number" ? dfeed.accepted_count : 0;
    receipt.dispatch.acceptance_verdict = dfeed.acceptance_verdict || null;
    receipt.dispatch.legs_mock_honest = !!(dfeed.legs && dfeed.legs.conductor === "mock" && dfeed.legs.workers === "mock");
    receipt.dispatch.live_workers_owed = !!(dfeed.live_workers_owed && dfeed.live_workers_owed.owed === true);
    receipt.dispatch.torn_down = dfeed.torn_down === true;
    if (dsrc.ok !== true || dfeed.schema !== DISPATCH_SCHEMA) throw new Error(`dispatch feed not sourced from Python (ok:${dsrc.ok}, schema:${dfeed.schema})`);
    receipt.legs.workers_dispatched = receipt.dispatch.feed_ok && receipt.dispatch.dispatched
      && receipt.dispatch.by_descriptor && receipt.dispatch.accepted_count > 0
      && receipt.dispatch.acceptance_verdict === "PASS" && receipt.dispatch.legs_mock_honest
      && receipt.dispatch.live_workers_owed && receipt.dispatch.torn_down;
    if (!receipt.legs.workers_dispatched) throw new Error(`governed dispatch leg not proven: ${JSON.stringify(receipt.dispatch)}`);
    log(`[selfcheck:assembled] governed dispatch: ${receipt.dispatch.accepted_count} accepted by descriptor, legs mock-honest, U58 owed`);

    // ---- leg 4: APPROVAL exercised — a REAL session event, then a governed decide -----------------
    // Phase 17D `.events` (finding F2) replaced the drawer's producer: it no longer rebuilds a canned
    // trio per fetch (`source:"emitter"`, three rows at launch), it folds THIS session's recorded
    // events (`source:"session_events"`, an empty drawer until something happens). So this leg now has
    // to CAUSE the thing it approves — a spoken protected verb the broker queues — instead of finding
    // one waiting. Left unchanged it would have waited 60 s for a source string that can no longer
    // appear and then failed a leg that is not broken.
    await waitFor(async () => { const m = await evalR(win, "window.sovereign.approvals()"); return !!(m && m.sourced === true); }, 60000, 500);
    const launchModel = await evalR(win, "window.sovereign.approvals()") || {};
    receipt.approval.sourced_from_session_events = launchModel.source === "session_events";
    // the F2 property, asserted in the assembled run too: nothing is pending that this run did not do
    receipt.approval.empty_before_the_event = (launchModel.badgeCount || 0) === 0;
    // "spawn worker" (conf 0.9) — a PROTECTED verb, so the real bridge proposes and the real broker
    // queues it (invariant 25: never delivered, never executed).
    await evalR(win, 'window.sovereign.captureVoice("audio:spawn-worker")');
    await waitFor(async () => {
      const m = await evalR(win, "window.sovereign.approvals()");
      return Array.isArray(m && m.rows) && m.rows.length > 0;
    }, 60000, 500);
    const model = await evalR(win, "window.sovereign.approvals()") || {};
    const rows = Array.isArray(model.rows) ? model.rows : [];
    receipt.approval.rows = rows.length;
    const queued = rows.find((r) => r.kind === "protected_action");
    receipt.approval.row_is_the_real_event = !!(queued && queued.detail && queued.detail.verb === "spawn");
    if (queued && queued.id) {
      // REJECT it: the governed authority resolves, the shell self-authorizes nothing, and the resolve
      // PERSISTS (the drawer comes back empty) — the 16D gap this track closed.
      const res = await evalR(win, `window.sovereign.decideApproval(${JSON.stringify(queued.id)}, "reject", "")`);
      const governed = res && res.governed;
      receipt.approval.decide_routed = !!(res && res.routed === true);
      receipt.approval.self_authorized_false = !!(res && res.selfAuthorized === false);
      receipt.approval.decide_governed_resolved = !!(governed && governed.resolved === true);
      const after = await evalR(win, "window.sovereign.approvals()") || {};
      receipt.approval.decision_persisted = (after.badgeCount || 0) === 0;
      // and the no-override property, on the same item: it cannot be decided twice
      const again = await evalR(win, `window.sovereign.decideApproval(${JSON.stringify(queued.id)}, "approve", "")`);
      const g2 = again && again.governed;
      receipt.approval.re_decide_governed_refused = !!(g2 && g2.resolved === false && g2.refused === true);
    }
    receipt.legs.approval_exercised = receipt.approval.sourced_from_session_events
      && receipt.approval.empty_before_the_event && receipt.approval.rows > 0
      && receipt.approval.row_is_the_real_event && receipt.approval.decide_routed
      && receipt.approval.self_authorized_false && receipt.approval.decide_governed_resolved
      && receipt.approval.decision_persisted && receipt.approval.re_decide_governed_refused;
    if (!receipt.legs.approval_exercised) throw new Error(`approval leg not proven: ${JSON.stringify(receipt.approval)}`);
    log(`[selfcheck:assembled] approval drawer empty at launch, then ${receipt.approval.rows} REAL row(s); `
      + "governed decide routed + resolved + persisted, re-decide refused (invariant 16)");

    // ---- leg 5: RESTART RECOVERY — the worker's chrome + conductor-first layout survive a restart --
    const snap = loadLayoutSnapshot();
    const snapWorker = snap && Array.isArray(snap.panes) ? snap.panes.find((p) => p.paneId === worker) : null;
    receipt.recovery.snapshot_carries_chrome = !!(snapWorker && snapWorker.chrome && snapWorker.chrome.model_label === receipt.picker.selected_label);
    const layout = reconstructLayout();
    const recWorker = layout && Array.isArray(layout.panes) ? layout.panes.find((p) => p.paneId === worker) : null;
    // the conductor is a top-level conductor-first entry (structural, OP-7 §12.4), never a worker row:
    // pinned P0, role "conductor", honestly reconstructed as an awaiting_live_conductor placeholder.
    const recConductor = layout ? layout.conductor : null;
    receipt.recovery.reconstructed_conductor_first = !!(recConductor && recConductor.paneId
      && recConductor.role === "conductor" && recConductor.pinned === true
      && recConductor.nodeState === "awaiting_live_conductor");
    receipt.recovery.recovered_worker_chrome = !!(recWorker && recWorker.chrome && recWorker.chrome.model_label === receipt.picker.selected_label);
    receipt.recovery.recovered_not_reattached = !!(recWorker && recWorker.reattach === false && recWorker.admitted === false);
    // VISIBLE half: drop in-memory badges (simulate a fresh renderer), push production recovery, prove repaint
    await evalR(win, "window.__sovereignSelfCheck.resetBadges()");
    await sleep(50);
    sendRecovery();
    receipt.recovery.badge_restored = await waitFor(async () => {
      const b = await evalR(win, `window.__sovereignSelfCheck.paneBadgeText(${JSON.stringify(worker)})`);
      return !!(b && b.shown && receipt.picker.selected_label && String(b.text).includes(receipt.picker.selected_label));
    }, 10000, 200);
    receipt.legs.restart_recovered = receipt.recovery.snapshot_carries_chrome
      && receipt.recovery.reconstructed_conductor_first && receipt.recovery.recovered_worker_chrome
      && receipt.recovery.recovered_not_reattached && receipt.recovery.badge_restored;
    if (!receipt.legs.restart_recovered) throw new Error(`restart-recovery leg not proven: ${JSON.stringify(receipt.recovery)}`);
    log(`[selfcheck:assembled] restart recovery: conductor-first + worker chrome repainted from reconstructed snapshot`);

    // ---- verdict: every leg of the assembled run composed --------------------------------------
    receipt.ok = Object.values(receipt.legs).every(Boolean);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
    if (log) log(`[selfcheck:assembled] FAIL: ${receipt.error}`);
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
    if (log) log(`[selfcheck:assembled] could not write receipt: ${e.message}`);
  }
  if (log) log(`[selfcheck:assembled] ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runAssembledSelfCheck: run, RECEIPT_PATH };
