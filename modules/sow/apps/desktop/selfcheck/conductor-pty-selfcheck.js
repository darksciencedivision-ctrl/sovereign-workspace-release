"use strict";
/**
 * Phase 17A `.pty` in-Electron self-check (D-P16-0 binding, per-track).
 *
 * `.lease` proved the shell can OBTAIN a governed authorization. This proves it can EXECUTE one: the
 * real interactive `claude` conductor session runs inside pane 1's ConPTY, through the supervised
 * session path, holding a durable I-X3 terminal that is visible to other processes and handed back
 * when the session ends. It is the end of the operator's black pane (first-use finding F3) as far as
 * a machine can check it — the type→answer round trip is `.roundtrip`.
 *
 * Why in-runtime and not only headless (the binding lesson): the ConPTY spawn, the credential-scrub
 * applied to a REAL child environment, node-pty's cwd binding, the renderer's xterm view attaching to
 * a pane whose session appeared after first paint — every one of those passes in a Node test and can
 * fail at first launch. This drives the PRODUCTION path (`launchConductorSession`, the same function
 * the on-launch spawn and the pane-1 control call), never a test-only spawn.
 *
 * Flow:
 *   1. wait for supervision READY — a session is only ever born on a verified channel (invariant 2);
 *   2. launch through the production path; assert the ticket was governed and the argv INTERACTIVE;
 *   3. assert the session is genuinely supervised and RUNNING: registered in the SessionManager with
 *      a live pid, admitted (a refusal would have thrown), bound to the ticket's workspace cwd;
 *   4. assert the durable terminal is held under the SESSION key by THIS process and is visible to a
 *      separate process — and that the always-visible status bar now reads it (U76: the bar can no
 *      longer report 0/2 against a held terminal);
 *   5. assert the live process actually produced bytes into the RENDERER's pane buffer — a spawned
 *      process that renders nothing is exactly the blank pane the operator reported;
 *   6. kill the session and assert the durable count returns to 0 (D-LOOP-1 — no live terminal, and
 *      no `claude` process, outlives this check). The teardown runs in `finally`.
 *
 * LIVE SCOPE (deliberately minimal, §16 "live exchanges MINIMAL"): this starts an interactive CLI and
 * kills it. It sends NO prompt and asks for no completion — the receipt claims a running governed
 * session, never a model answer.
 *
 * SCRATCH ledger throughout (`SOW_TERMINAL_LEASE_LEDGER`): the check must never adopt, or release, a
 * terminal the operator's own running conductor holds.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const { fetchLeaseStatus } = require("../conductor/launch-source");
const { fetchStatusBarModelFromGovernor } = require("../statusbar/governor-source");

const RECEIPT_PATH = receiptPath("PHASE17A_PTY_SELFCHECK.json");
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SCRATCH_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", `selfcheck-17apty-${process.pid}.json`);

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

/** The rendered xterm buffer for a pane (read-only renderer observability hook). */
async function paneText(win, paneId) {
  const expr = `window.__sovereignSelfCheck && window.__sovereignSelfCheck.paneText(${JSON.stringify(paneId)})`;
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

async function run(ctx) {
  const { win, isSupervised, conductorState, launchConductorSession, conductorLaunchState,
    sessionManager, killSession, ptySpawnObserved, log } = ctx;
  const receipt = {
    check: "phase-17a.pty",
    started: new Date().toISOString(),
    ok: false,
    // isolation
    ledger_scope: "scratch",
    ledger_path: SCRATCH_LEDGER,
    electron_main_pid: process.pid,
    // 1-2: the governed launch
    supervision_ready: false,
    pane_id: null,
    launched: false,
    launch_state: null,
    launch_reason: null,
    argv: null,
    interactive_argv: false,
    session_id: null,
    // 3: supervised + contained (as far as this build enforces — see scope_note)
    session_registered: false,
    session_state: null,
    session_pid: null,
    session_pid_alive: false,
    node_id: null,
    workspace_cwd: null,
    cwd_passed_to_pty: null,
    cwd_observed_in_child: false,
    env_scrub_count: null,
    env_scrub_names_absent_from_child: false,
    child_env_inherited_verbatim: null,
    child_env_key_count: null,
    // 4: the durable terminal
    lease_id: null,
    lease_session_keyed: false,
    lease_visible_cross_process: false,
    lease_in_use: null,
    lease_allowance: null,
    statusbar_reads_the_held_terminal: false,
    statusbar_row: null,
    // 5: the pane is no longer black
    pane_output_seen: false,
    pane_excerpt: null,
    // 6: D-LOOP-1
    session_killed: false,
    lease_released: false,
    in_use_after_release: null,
    node_state_after_exit: null,
    error: null,
  };

  const priorLedger = process.env.SOW_TERMINAL_LEASE_LEDGER;
  process.env.SOW_TERMINAL_LEASE_LEDGER = SCRATCH_LEDGER; // inherited by every `py` child below
  let sessionId = null;
  let paneId = null;
  try {
    // 1. supervision READY (fail-closed: no verified channel ⇒ no session at all)
    receipt.supervision_ready = await waitFor(isSupervised, 30000, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY (control-plane/IPC gateway did not verify within 30s)");
    }
    paneId = conductorState().paneId;
    receipt.pane_id = paneId;
    if (!paneId) throw new Error("no conductor pane exists to launch into");

    // 2. THE PRODUCTION LAUNCH PATH (identical to on-launch and to the pane-1 control)
    const res = await launchConductorSession({ reason: "in-Electron self-check (17A .pty)" });
    const st = conductorLaunchState();
    sessionId = st.sessionId;
    receipt.launched = res.launched === true;
    receipt.launch_state = st.state;
    receipt.launch_reason = st.reason || (res && res.reason) || null;
    receipt.session_id = sessionId;
    receipt.argv = Array.isArray(st.argv) ? st.argv.slice() : null;
    receipt.env_scrub_count = st.scrubbedCount;
    receipt.workspace_cwd = st.cwd || null;
    receipt.lease_id = st.leaseId || null;
    if (!receipt.launched) {
      // A governed refusal is an HONEST outcome, but not a pass: this check exists to prove the
      // authorized path runs on the operator's host.
      throw new Error(`the governed live launch did not run: ${receipt.launch_reason || "unknown"}`);
    }
    receipt.interactive_argv = Array.isArray(receipt.argv) && receipt.argv[0] === "claude"
      && !receipt.argv.includes("-p") && !receipt.argv.includes("--print")
      && !receipt.argv.includes("--output-format");
    if (!receipt.interactive_argv) throw new Error(`the launched argv is not an interactive claude session: ${JSON.stringify(receipt.argv)}`);

    // 3. supervised, running, workspace-bound
    const mgr = sessionManager();
    receipt.session_registered = Boolean(mgr && mgr.registry.has(paneId));
    if (!receipt.session_registered) throw new Error("the conductor session is not registered with the SessionManager (unsupervised process?)");
    const rec = mgr.registry.get(paneId);
    receipt.session_state = rec.state;
    receipt.session_pid = rec.pid || null;
    receipt.node_id = rec.nodeId || (rec.spec && rec.spec.nodeId) || null;
    // THE REAL BOUNDARY (validator finding: the previous version compared the ticket to itself).
    // `ptySpawnObserved()` is what node-pty was actually handed, recorded inside ptyFactory.
    const spawned = ptySpawnObserved() || {};
    receipt.cwd_passed_to_pty = spawned.cwd || null;
    receipt.child_env_inherited_verbatim = spawned.inheritedEnv === true;
    receipt.child_env_key_count = Array.isArray(spawned.envKeys) ? spawned.envKeys.length : null;
    // §2.2 OBSERVED, not asserted: every credential name that exists in THIS process's environment
    // must be absent from the environment the child was given, while ordinary vars survive.
    const scrubNames = (st.envScrubNames || []).filter((n) => n in process.env);
    const childKeys = new Set(spawned.envKeys || []);
    receipt.env_scrub_count = scrubNames.length;
    receipt.env_scrub_names_absent_from_child = !spawned.inheritedEnv
      && scrubNames.every((n) => !childKeys.has(n))
      && childKeys.has("PATH");
    if (receipt.session_state !== "RUNNING") throw new Error(`the conductor session is ${receipt.session_state}, not RUNNING`);
    try { process.kill(receipt.session_pid, 0); receipt.session_pid_alive = true; } catch { receipt.session_pid_alive = false; }
    if (!receipt.session_pid_alive) throw new Error(`the launched pid ${receipt.session_pid} is not alive`);
    if (receipt.cwd_passed_to_pty !== REPO_ROOT) {
      throw new Error(`the ConPTY was started in ${receipt.cwd_passed_to_pty}, not the governed workspace ${REPO_ROOT}`);
    }
    if (!receipt.env_scrub_names_absent_from_child) {
      throw new Error(receipt.child_env_inherited_verbatim
        ? "the child inherited this shell's environment verbatim — the §2.2 scrub was not applied"
        : "the child's environment still carries a credential-bearing name (or lost PATH)");
    }

    // 4. the durable terminal — session-keyed, cross-process visible, and READ BY THE STATUS BAR
    const leaseStatus = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
    const subs = (leaseStatus.ok && leaseStatus.status && leaseStatus.status.subscriptions) || {};
    const entry = subs[st.subscriptionRef] || null;
    const holder = entry && (entry.holders || []).find((h) => h.lease_id === receipt.lease_id);
    receipt.lease_visible_cross_process = Boolean(holder && holder.holder_pid === process.pid);
    receipt.lease_session_keyed = Boolean(holder && holder.session_id === sessionId);
    receipt.lease_in_use = entry ? entry.in_use : 0;
    receipt.lease_allowance = leaseStatus.ok && leaseStatus.status ? leaseStatus.status.allowance : null;
    if (!receipt.lease_visible_cross_process) throw new Error("a separate process cannot see the held terminal — the durable I-X3 count is not real");
    if (!receipt.lease_session_keyed) throw new Error("the durable terminal is not keyed to this ConPTY session (U75)");

    // U76: the ALWAYS-VISIBLE bar must now read the very terminal this session holds — it used to
    // build a fresh in-process governor under a different ref and report 0/2 against a live session.
    const bar = await fetchStatusBarModelFromGovernor({ cwd: REPO_ROOT, timeoutMs: 60000 });
    const row = (bar.rows || []).find((r) => r.subscriptionRef === st.subscriptionRef);
    receipt.statusbar_row = row
      ? { ref: row.subscriptionRef, provider: row.provider, label: row.label, inUse: row.inUse, allowance: row.allowance, state: row.state }
      : null;
    receipt.statusbar_reads_the_held_terminal = Boolean(row && row.inUse >= 1 && row.state !== "unknown");
    if (!receipt.statusbar_reads_the_held_terminal) {
      throw new Error(`the status bar reports ${row ? row.label : "nothing"} for ${st.subscriptionRef} while a terminal is genuinely held (U76)`);
    }

    // 5. the pane is no longer black: the live process's output reaches the RENDERER's buffer
    const gotOutput = await waitFor(async () => {
      const text = await paneText(win, paneId);
      return typeof text === "string" && text.trim().length > 0;
    }, 60000, 500);
    receipt.pane_output_seen = gotOutput;
    const text = await paneText(win, paneId);
    receipt.pane_excerpt = typeof text === "string" ? text.replace(/\s+/g, " ").trim().slice(0, 200) : null;
    if (!receipt.pane_output_seen) throw new Error("the live conductor session rendered NOTHING into pane 1 (the black pane is not fixed)");
    // The CHILD's own statement of its working directory: `claude` prints the workspace it opened.
    // Whitespace is stripped from both sides so the pane's line wrapping cannot break the match.
    const squashed = (typeof text === "string" ? text : "").replace(/\s+/g, "");
    receipt.cwd_observed_in_child = squashed.includes(REPO_ROOT.replace(/\s+/g, ""));
    if (!receipt.cwd_observed_in_child) {
      throw new Error("the live session did not report the governed workspace in its own output — the cwd binding is unproven");
    }
    log(`[selfcheck] live conductor running in ${paneId}: pid ${receipt.session_pid}, terminal ${receipt.lease_in_use}/${receipt.lease_allowance}, pane rendering`);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  } finally {
    // 6. D-LOOP-1 — the live session and its terminal never outlive this check.
    try {
      if (paneId && sessionManager() && sessionManager().registry.has(paneId)) {
        killSession(paneId);
        receipt.session_killed = await waitFor(
          () => { try { process.kill(receipt.session_pid, 0); return false; } catch { return true; } }, 15000, 250);
      }
      // the kill fires the production exit hook, which releases the terminal asynchronously
      const released = await waitFor(async () => {
        const after = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
        // An UNREADABLE count is not a released terminal (validator finding: this used to fold a
        // failed read into `in_use: 0` and report the lease released).
        if (!after.ok || !after.status) { receipt.in_use_after_release = null; return false; }
        const subs2 = after.status.subscriptions || {};
        const e2 = subs2[conductorLaunchState().subscriptionRef || ""] || null;
        receipt.in_use_after_release = e2 ? e2.in_use : 0;
        return receipt.in_use_after_release === 0;
      }, 45000, 1000);
      receipt.lease_released = released;
      receipt.node_state_after_exit = conductorState().nodeState;
    } catch (e) {
      receipt.error = receipt.error || `teardown failed: ${String((e && e.message) || e)}`;
    }
    if (priorLedger === undefined) delete process.env.SOW_TERMINAL_LEASE_LEDGER;
    else process.env.SOW_TERMINAL_LEASE_LEDGER = priorLedger;
    try { fs.rmSync(SCRATCH_LEDGER, { force: true }); } catch { /* nothing to remove */ }
  }

  receipt.ok = receipt.error === null
    && receipt.supervision_ready && receipt.launched && receipt.interactive_argv
    && receipt.session_registered && receipt.session_state === "RUNNING" && receipt.session_pid_alive
    && receipt.cwd_passed_to_pty === REPO_ROOT && receipt.cwd_observed_in_child
    && receipt.env_scrub_names_absent_from_child
    && receipt.lease_visible_cross_process && receipt.lease_session_keyed
    && receipt.statusbar_reads_the_held_terminal && receipt.pane_output_seen
    && receipt.session_killed && receipt.lease_released && receipt.in_use_after_release === 0;

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  receipt.scope_note = "starts and kills a REAL interactive `claude` session through the production "
    + "launch path against a SCRATCH lease ledger; sends NO prompt and claims no model answer (the "
    + "type→answer round trip is 17A `.roundtrip`). `pane_output_seen` proves the session's bytes "
    + "reach the renderer buffer, not that a model replied. CONTAINMENT observed here: supervised "
    + "admission (SessionManager refuses without an admitted node), the governed node identity, the "
    + "workspace binding (the cwd node-pty was handed AND the workspace the child itself reports in "
    + "its own output) and the credential env scrub (measured on the environment the child was "
    + "given, not on the ticket's name list). NOT established and still owed: the permission-profile "
    + "binding (the ticket carries `permission_profile_id`; nothing applies it) and OS "
    + "job-object/ACL containment (U25) — the latter unchanged for every shell session. "
    + "`env_scrub_count` is host-dependent: it counts the credential-bearing names that exist in "
    + "THIS shell's environment, which may legitimately be 0.";
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] conductor-pty ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runConductorPtySelfCheck: run, RECEIPT_PATH };
