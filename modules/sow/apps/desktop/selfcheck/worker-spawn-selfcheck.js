"use strict";
/**
 * Phase 17B `.spawn` in-Electron self-check (D-P16-0 binding, per-track).
 *
 * `.ticket` proved the shell can OBTAIN a governed worker authorization. This proves it EXECUTES
 * one: the operator's picker click starts a REAL model session in a REAL pane. It is the machine-
 * checkable half of the operator's finding F3 ("selecting a model records + badges but launches
 * nothing") and of U70's spawn half.
 *
 * It drives the PRODUCTION path — `spawnFromSelection`, the exact function the
 * `pane:spawnFromSelection` IPC handler calls when the operator clicks *spawn* in the picker — never
 * a test-only spawn. What it establishes, each leg naming the gate or fact it exercises:
 *
 *   1. **a LOCAL model pane really runs** (`ollama run <tag>`): supervised admission, the
 *      Python-minted node identity, the authorized workspace as the ConPTY's cwd, the credential
 *      scrub measured on the environment the CHILD was handed, and bytes reaching the RENDERER's
 *      xterm buffer — a pane that renders nothing is the blank pane the operator reported;
 *   2. **a FRONTIER model pane really runs** (`claude --model <probed slug>`) holding a DURABLE
 *      I-X3 terminal keyed to its session and visible to a separate process — and handing it back
 *      when the session ends (D-LOOP-1);
 *   3. **the fail-closed half, in-runtime**: a FABRICATED option (one this host never offered) starts
 *      NOTHING and the pane says which gate refused it; a second selection into a pane that already
 *      holds a live session is refused WITHOUT killing the running one;
 *   4. **U105**: the env var NAMES the SHELL holds are what get classified, so the scrub list is
 *      about the environment the child is actually born into.
 *
 * LIVE SCOPE (deliberately minimal, §16 "live exchanges MINIMAL"): every session started here is
 * killed here. No prompt is sent and no model answer is claimed — the conductor→worker exchange
 * (CANDIDATE → gate → synthesis) is 17B `.legs`/U58.
 *
 * NOT established here, stated so the receipt cannot be read as more: U100's undelivered-ticket
 * release is driven by the headless suite (`apps/desktop/test/worker-spawn.test.js`) — forcing a
 * mid-flight emitter failure in-runtime would mean corrupting the emitter, which would prove the
 * corruption, not the release. Containment beyond the four facts above (permission-profile binding
 * U78(a), OS job object U25) stays owed and the ticket says so.
 *
 * SCRATCH lease ledger throughout: this check must never adopt or release a terminal the operator's
 * own running conductor holds. A PINNED VRAM budget, computed from the host's own residency snapshot
 * exactly as `.ticket` does, so the local leg exercises admission mechanics on a busy host and an
 * idle one alike rather than whatever the daemon happens to be serving.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const { fetchPickerModel, fetchHostResidency } = require("../picker/source");
const { fetchLeaseStatus } = require("../conductor/launch-source");

const RECEIPT_PATH = receiptPath("PHASE17B_SPAWN_SELFCHECK.json");
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SCRATCH_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", `selfcheck-17bspawn-${process.pid}.json`);
/** The OPERATOR's real durable-terminal ledger — read only, to prove this check never touched it. */
const REAL_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", "terminal_leases.json");

// See worker-launch-selfcheck.js for why the budget is COMPUTED rather than a constant: a flat
// figure lands on whichever branch the daemon's current state produces, and a leg that exercises a
// different gate than its name claims is evidence for the wrong thing.
const PINNED_VRAM_FLOOR_MB = 24576;
const PINNED_VRAM_HEADROOM_MB = 1024;
const PROBE_VRAM_BUDGET_MB = "1048576";
const TIMEOUT_MS = 90000;

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

/** An available option matching a predicate, PREFERRING a named model — never fabricated. */
function pick(options, predicate, preferred) {
  const available = (options || []).filter((o) => o && o.available && predicate(o));
  return available.find((o) => o.model_slug === preferred) || available[0] || null;
}

async function run(ctx) {
  const { win, spawnFromSelection, workerLaunchState, workerLauncher, sessionManager, killSession,
    paneModel, isSupervised, ptySpawnObserved, paneChromeOf, conductorPaneIdOf, log } = ctx;
  const receipt = {
    check: "phase-17b.spawn",
    started: new Date().toISOString(),
    ok: false,
    electron_main_pid: process.pid,
    ledger_scope: "scratch",
    ledger_path: SCRATCH_LEDGER,
    supervision_ready: false,
    // the host enumeration every selection below is taken from (never fixtures)
    picker_sourced: false,
    picker_option_count: null,
    host_used_vram_mb: null,
    local_budget_pinned_mb: null,
    local_option: null,
    frontier_option: null,
    // 1. LOCAL pane
    local_pane_id: null,
    local_launched: false,
    local_state: null,
    local_reason: null,
    local_argv: null,
    local_interactive_argv: false,
    local_node_id: null,
    local_session_registered: false,
    local_session_state: null,
    local_session_pid: null,
    local_session_pid_alive: false,
    local_pty_spawn_is_this_pane: false,
    local_cwd_passed_to_pty: null,
    local_child_env_inherited_verbatim: null,
    local_env_scrub_names_absent_from_child: false,
    local_env_scrub_count: null,
    local_pane_output_seen: false,
    local_pane_excerpt: null,
    local_chrome_node_state: null,
    local_chrome_governed: null,
    local_subscription_governed: null,
    // 2. FRONTIER pane
    frontier_pane_id: null,
    frontier_launched: false,
    frontier_state: null,
    frontier_reason: null,
    frontier_argv: null,
    frontier_node_id: null,
    frontier_session_state: null,
    frontier_session_pid_alive: false,
    frontier_node_id_minted: false,
    frontier_pty_spawn_is_this_pane: false,
    frontier_cwd_passed_to_pty: null,
    frontier_env_scrub_count: null,
    frontier_env_scrub_names_absent_from_child: false,
    frontier_lease_id: null,
    frontier_lease_session_keyed: false,
    frontier_lease_visible_cross_process: false,
    frontier_lease_in_use: null,
    frontier_pane_output_seen: false,
    frontier_lease_released_on_exit: false,
    frontier_in_use_after_exit: null,
    // 3. the fail-closed half, in-runtime — each leg asserts its OWN gate
    forged_launch_refused: false,
    forged_reason: null,
    forged_refused_by: null,
    forged_started_no_session: false,
    forged_chrome_node_state: null,
    occupied_pane_refused: false,
    occupied_reason: null,
    occupied_first_session_survived: false,
    occupied_launch_record_intact: false,
    occupied_record_state_after: null,
    occupied_held_after: false,
    occupied_chrome_after: null,
    occupied_chrome_intact: false,
    occupied_chrome_governed_after: null,
    occupied_chrome_refused_by_after: null,
    // the CONDUCTOR pane is not a worker pane — refused by pane id, not by a CSS rule
    conductor_pane_id: null,
    conductor_pane_refused: false,
    conductor_pane_reason: null,
    conductor_pane_started_no_session: false,
    // the ENDED-chrome revision: a pane whose session died stops claiming a live governed node
    ended_chrome_node_state: null,
    ended_chrome_governed: null,
    ended_chrome_model_label_kept: false,
    ended_chrome_revised: false,
    // 4. U105 — both halves recorded separately: a list that names the var and a child that still
    // holds it are different facts, and only reporting their AND hides which one broke.
    shell_env_names_classified: false,
    shell_only_credential_name: null,
    shell_only_name_in_scrub_list: false,
    shell_only_name_absent_from_child: false,
    // D-LOOP-1
    sessions_killed: false,
    surviving_pids: null,
    // …and the host is left as found: the scratch ledger removed, the operator's REAL ledger byte-
    // identical. Asserted rather than claimed, because an append-only note after the `.spawn` run
    // recorded an empty scratch ledger surviving it and the mechanism did not reproduce.
    scratch_ledger_removed: false,
    real_ledger_unchanged: false,
    error: null,
  };

  const priorLedger = process.env.SOW_TERMINAL_LEASE_LEDGER;
  const priorBudget = process.env.SOW_VRAM_BUDGET_MB;
  // read BEFORE the redirection, so "the operator's real ledger is untouched" is a comparison and
  // not an assertion about code that was believed not to write there
  let realLedgerBefore = null;
  try { realLedgerBefore = fs.existsSync(REAL_LEDGER) ? fs.readFileSync(REAL_LEDGER, "utf8") : null; } catch { realLedgerBefore = null; }
  process.env.SOW_TERMINAL_LEASE_LEDGER = SCRATCH_LEDGER;
  const started = [];   // paneIds this check spawned, killed in `finally` whatever happened
  let frontierSubRef = null;
  try {
    // 0. admission — invariant 2. Nothing is asked for, let alone born, without a verified channel.
    receipt.supervision_ready = await waitFor(isSupervised, 30000, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY (control-plane/IPC gateway did not verify within 30s)");
    }

    // 0b. the host's residency, read under a budget nothing can falsify, so the pinned budget below
    // is arithmetic on real numbers (see the constants).
    process.env.SOW_VRAM_BUDGET_MB = PROBE_VRAM_BUDGET_MB;
    const probe = await fetchHostResidency({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    const snapshot = (probe.residency && probe.residency.snapshot) || null;
    if (!probe.ok || !snapshot) throw new Error(`could not read this host's residency snapshot: ${probe.error || "no snapshot"}`);
    receipt.host_used_vram_mb = Number.isFinite(snapshot.used_vram_mb) ? snapshot.used_vram_mb : null;
    if (receipt.host_used_vram_mb === null) throw new Error("the residency snapshot reports no used_vram_mb");
    const biggest = (snapshot.models || []).reduce(
      (m, e) => (Number.isFinite(e.footprint_mb) && e.footprint_mb > m ? e.footprint_mb : m), 0);
    const pinnedBudget = String(Math.max(
      PINNED_VRAM_FLOOR_MB, receipt.host_used_vram_mb + biggest + PINNED_VRAM_HEADROOM_MB));
    receipt.local_budget_pinned_mb = pinnedBudget;
    process.env.SOW_VRAM_BUDGET_MB = pinnedBudget;

    // U105, forced through the divergence that is REAL on this host rather than a var the emitter
    // can see anyway. Python's `os.environ` UPPER-CASES every key on Windows; Node keeps the case the
    // var was created with, and deletes from a plain object by exact spelling. So a mixed-case
    // credential var yields `ANTHROPIC_…_API_KEY` from a list classified in the emitter's own
    // environment, the shell deletes a key by that spelling, nothing matches — and the var reaches
    // the child. (An UPPER-CASE name would have proven nothing: both processes spell it identically,
    // which is why the first version of this leg stayed green with the fix reverted.) The value is a
    // literal placeholder — §2.2: NAMES cross to the emitter, never values.
    const SHELL_ONLY_KEY = `Anthropic_Selfcheck_${process.pid}_Api_Key`;
    process.env[SHELL_ONLY_KEY] = "not-a-credential-placeholder";
    receipt.shell_only_credential_name = SHELL_ONLY_KEY;

    // 1. the REAL host enumeration — the same source the picker drawer renders.
    const pickerRes = await fetchPickerModel({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    receipt.picker_sourced = pickerRes.ok === true;
    const options = (pickerRes.picker && pickerRes.picker.options) || [];
    receipt.picker_option_count = options.length;
    if (!receipt.picker_sourced) throw new Error(`host picker enumeration failed: ${pickerRes.error}`);
    const localOpt = pick(options, (o) => o.locality === "local"
      && (o.roles || []).includes("reasoning"), "qwen3:8b");
    const frontierOpt = pick(options, (o) => o.locality === "frontier" && o.adapter === "claude_code"
      && (o.roles || []).includes("reasoning"), "fable-5");
    receipt.local_option = localOpt && { label: localOpt.label, model_slug: localOpt.model_slug };
    receipt.frontier_option = frontierOpt && { label: frontierOpt.label, model_slug: frontierOpt.model_slug };
    if (!localOpt) throw new Error("the host picker offered no available LOCAL reasoning model to launch");
    if (!frontierOpt) throw new Error("the host picker offered no available claude_code option to launch");

    // ---- LEG 1: a LOCAL model pane, launched through the operator's own path -------------------
    const localRes = await spawnFromSelection({
      option: localOpt, role: "reasoning", mode: "attended", targetPaneId: null,
    });
    receipt.local_pane_id = localRes.target || null;
    receipt.local_launched = localRes.launched === true;
    receipt.local_state = localRes.state || null;
    receipt.local_reason = localRes.reason || null;
    receipt.local_argv = localRes.argv ? localRes.argv.slice() : null;
    receipt.local_node_id = localRes.nodeId || null;
    receipt.local_chrome_node_state = (localRes.chrome || {}).node_state || null;
    receipt.local_chrome_governed = (localRes.chrome || {}).governed === true;
    if (receipt.local_pane_id) started.push(receipt.local_pane_id);
    if (!receipt.local_launched) {
      throw new Error(`the governed LOCAL worker launch did not run: ${receipt.local_reason || "unknown"}`);
    }
    const localRec = workerLaunchState(receipt.local_pane_id);
    receipt.local_subscription_governed = localRec.subscriptionGoverned;
    receipt.local_env_scrub_count = localRec.scrubbedCount;
    // an INTERACTIVE `ollama run <tag>` — a third positional would be a one-shot prompt
    receipt.local_interactive_argv = Array.isArray(receipt.local_argv)
      && receipt.local_argv.includes("run")
      && receipt.local_argv.filter((a) => !String(a).startsWith("-")).length === 3;
    if (!receipt.local_interactive_argv) throw new Error(`the local argv is not an interactive ollama session: ${JSON.stringify(receipt.local_argv)}`);
    if (receipt.local_subscription_governed !== false) throw new Error("a LOCAL pane must hold no subscription terminal (invariant 19)");

    const mgr = sessionManager();
    receipt.local_session_registered = Boolean(mgr && mgr.registry.has(receipt.local_pane_id));
    if (!receipt.local_session_registered) throw new Error("the local worker session is not registered with the SessionManager (unsupervised process?)");
    const lrec = mgr.registry.get(receipt.local_pane_id);
    receipt.local_session_state = lrec.state;
    receipt.local_session_pid = lrec.pid || null;
    if (receipt.local_session_state !== "RUNNING") throw new Error(`the local worker session is ${receipt.local_session_state}, not RUNNING`);
    try { process.kill(receipt.local_session_pid, 0); receipt.local_session_pid_alive = true; } catch { receipt.local_session_pid_alive = false; }
    if (!receipt.local_session_pid_alive) throw new Error(`the launched pid ${receipt.local_session_pid} is not alive`);
    if (receipt.local_node_id !== `worker-${receipt.local_pane_id}`) {
      throw new Error(`the session runs under node id ${receipt.local_node_id}, not the Python-minted worker-${receipt.local_pane_id} (invariant 2/29)`);
    }
    // THE REAL BOUNDARY: what node-pty was actually handed (§2.2 — KEY NAMES only, never a value).
    // `ptySpawnObserved()` is the LAST spawn, so it is only evidence about THIS pane if the binary
    // it records is this pane's — asserted rather than assumed from ordering (validator MINOR-3).
    const spawned = ptySpawnObserved() || {};
    receipt.local_pty_spawn_is_this_pane = spawned.file === localRec.executable;
    if (!receipt.local_pty_spawn_is_this_pane) {
      throw new Error(`the observed node-pty spawn (${spawned.file}) is not this pane's binary `
        + `(${localRec.executable}) — the env/cwd evidence below would be about another session`);
    }
    receipt.local_cwd_passed_to_pty = spawned.cwd || null;
    receipt.local_child_env_inherited_verbatim = spawned.inheritedEnv === true;
    const childKeys = new Set(spawned.envKeys || []);
    const scrubNames = (localRec.envScrubNames || []).filter((n) => n in process.env);
    // CASE-INSENSITIVELY, exactly as the frontier leg below and as the launcher's own leftover guard:
    // a field named "…names_absent_from_child" that only proves "absent by exact spelling" over-
    // claims on a case-insensitive OS, and case divergence is the very defect U105 exists for. The
    // frontier leg was written this way when it was added and the local one was left behind
    // (spec-audit MINOR-1).
    const lowerChildKeysAll = new Set([...childKeys].map((k) => k.toLowerCase()));
    receipt.local_env_scrub_names_absent_from_child = !spawned.inheritedEnv
      && scrubNames.length > 0
      && scrubNames.every((n) => !lowerChildKeysAll.has(String(n).toLowerCase()))
      && childKeys.has("PATH");
    // U105 in-runtime: the ticket must name the var in the SHELL's OWN spelling (the only spelling
    // the shell can delete by), and no key that case-insensitively matches it may survive into the
    // child. The second half is the one that fails when the fix is reverted: the child keeps
    // `Anthropic_…_Api_Key` while the list said `ANTHROPIC_…_API_KEY`.
    const lowerChildKeys = lowerChildKeysAll;
    receipt.shell_env_names_classified = (localRec.envScrubNames || []).includes(SHELL_ONLY_KEY)
      && !lowerChildKeys.has(SHELL_ONLY_KEY.toLowerCase());
    receipt.shell_only_name_in_scrub_list = (localRec.envScrubNames || []).includes(SHELL_ONLY_KEY);
    receipt.shell_only_name_absent_from_child = !lowerChildKeys.has(SHELL_ONLY_KEY.toLowerCase());
    if (receipt.local_cwd_passed_to_pty !== REPO_ROOT) {
      throw new Error(`the ConPTY was started in ${receipt.local_cwd_passed_to_pty}, not the governed workspace ${REPO_ROOT}`);
    }
    if (!receipt.local_env_scrub_names_absent_from_child) {
      throw new Error(receipt.local_child_env_inherited_verbatim
        ? "the child inherited this shell's environment verbatim — the §2.2 scrub was not applied"
        : `the child's environment still carries a credential-bearing name, lost PATH, or had none to drop (${scrubNames.length} named)`);
    }
    if (!receipt.shell_env_names_classified) {
      throw new Error(receipt.shell_only_name_in_scrub_list
        ? `the ticket named ${SHELL_ONLY_KEY} but a key matching it still reached the child (§2.2)`
        : `the shell's own spelling of ${SHELL_ONLY_KEY} was not classified into the ticket's scrub `
          + "list — the list still describes the EMITTER's environment, where Windows/Python spell "
          + "it in upper case and the shell cannot delete by that name (U105)");
    }
    // the pane is not black: the live process's bytes reach the RENDERER's buffer
    receipt.local_pane_output_seen = await waitFor(async () => {
      const text = await paneText(win, receipt.local_pane_id);
      return typeof text === "string" && text.trim().length > 0;
    }, TIMEOUT_MS, 500);
    const ltext = await paneText(win, receipt.local_pane_id);
    receipt.local_pane_excerpt = typeof ltext === "string" ? ltext.replace(/\s+/g, " ").trim().slice(0, 200) : null;
    if (!receipt.local_pane_output_seen) throw new Error("the live LOCAL worker session rendered NOTHING into its pane");
    if (receipt.local_chrome_node_state !== "running" || receipt.local_chrome_governed !== true) {
      throw new Error(`a RUNNING governed pane reported chrome ${JSON.stringify(receipt.local_chrome_node_state)} `
        + `governed=${receipt.local_chrome_governed} (invariant 3/27)`);
    }

    // ---- LEG 3a: a second selection into the SAME pane is refused, and does not disturb leg 1 --
    // "Not disturbed" is asserted on THREE things, because the first version of this leg asserted
    // only the OS process and stayed green while the refusal destroyed the session's governance
    // accounting: the refusal overwrote the pane's RUNNING launch record, and every release gate
    // keys on that state, so the durable terminal became unreleasable for the life of the shell
    // (gate-validator BLOCKING-1/MAJOR-2, 2026-07-26). The process, the launch RECORD (state,
    // session key, and — for a frontier pane — the lease this shell must still hand back) and the
    // pane CHROME all have to come through untouched.
    const beforeRec = workerLaunchState(receipt.local_pane_id);
    const beforeChrome = (localRes.chrome || {}).node_state;
    const occupied = await spawnFromSelection({
      option: localOpt, role: "reasoning", mode: "attended", targetPaneId: receipt.local_pane_id,
    });
    receipt.occupied_reason = occupied.reason || occupied.error || null;
    receipt.occupied_pane_refused = occupied.launched === false
      && /already holds a live session/.test(receipt.occupied_reason || "");
    const stillThere = mgr.registry.get(receipt.local_pane_id);
    receipt.occupied_first_session_survived = Boolean(stillThere && stillThere.state === "RUNNING"
      && stillThere.pid === receipt.local_session_pid);
    const afterRec = workerLaunchState(receipt.local_pane_id);
    receipt.occupied_launch_record_intact = afterRec.state === "running"
      && afterRec.sessionId === beforeRec.sessionId && afterRec.leaseId === beforeRec.leaseId;
    receipt.occupied_record_state_after = afterRec.state;
    receipt.occupied_held_after = workerLauncher().heldSessions().includes(beforeRec.sessionId);
    // The defect this leg exists for flipped THREE fields, not one: `node_state` to launch_refused,
    // `governed` to false, and `launch_refused_by` to the gate that refused a click the running
    // session had nothing to do with. Comparing only node_state made the field name
    // (`chrome_intact`) assert more than the property (spec-audit MINOR-9).
    const occChrome = occupied.chrome || {};
    receipt.occupied_chrome_after = occChrome.node_state || null;
    receipt.occupied_chrome_governed_after = occChrome.governed === true;
    receipt.occupied_chrome_refused_by_after = occChrome.launch_refused_by || null;
    receipt.occupied_chrome_intact = receipt.occupied_chrome_after === beforeChrome
      && receipt.occupied_chrome_governed_after === true
      && receipt.occupied_chrome_refused_by_after === null;
    if (!receipt.occupied_pane_refused) throw new Error(`a selection into an occupied pane was not refused: ${receipt.occupied_reason}`);
    if (!receipt.occupied_first_session_survived) throw new Error("the running session was disturbed by a refused selection");
    if (!receipt.occupied_launch_record_intact || !receipt.occupied_held_after) {
      throw new Error("a refused selection destroyed the live session's release accounting "
        + `(state=${receipt.occupied_record_state_after}, still held=${receipt.occupied_held_after}) `
        + "— the terminal would never be handed back (D-LOOP-1)");
    }
    if (!receipt.occupied_chrome_intact) {
      throw new Error(`a refused selection repainted a RUNNING pane as `
        + `${JSON.stringify(receipt.occupied_chrome_after)} / governed=${receipt.occupied_chrome_governed_after} `
        + `/ refused_by=${JSON.stringify(receipt.occupied_chrome_refused_by_after)} (invariant 3/27)`);
    }

    // ---- LEG 3c: pane 1 is the CONDUCTOR's — a worker model is never launched into it -----------
    // The guard moved out of a CSS rule and into governance (validator MINOR-4) and then had no
    // test and no receipt leg at all: it lived in `main.js`, where nothing headless can reach it.
    // The RULE now lives in `picker/pane-wiring.refuseSelection` (unit-tested); this asserts the
    // shell actually applies it, against the REAL pinned pane id rather than a hard-coded "pane-1".
    receipt.conductor_pane_id = (typeof conductorPaneIdOf === "function" && conductorPaneIdOf()) || null;
    if (!receipt.conductor_pane_id) {
      throw new Error("the shell has no pinned CONDUCTOR pane — the conductor-pane guard cannot be exercised");
    }
    const beforeConductorSessions = mgr.registry.alive().length;
    const intoConductor = await spawnFromSelection({
      option: localOpt, role: "reasoning", mode: "attended", targetPaneId: receipt.conductor_pane_id,
    });
    receipt.conductor_pane_reason = intoConductor.reason || intoConductor.error || null;
    receipt.conductor_pane_started_no_session = mgr.registry.alive().length === beforeConductorSessions;
    receipt.conductor_pane_refused = intoConductor.launched === false
      && /is the CONDUCTOR pane/.test(receipt.conductor_pane_reason || "")
      && receipt.conductor_pane_started_no_session;
    if (!receipt.conductor_pane_refused) {
      throw new Error(`a worker model was not refused into the CONDUCTOR pane `
        + `${receipt.conductor_pane_id} (no new session=${receipt.conductor_pane_started_no_session}): `
        + `${receipt.conductor_pane_reason}`);
    }

    // ---- LEG 3b: a FABRICATED option starts nothing, and the pane says which gate refused it ---
    const forged = { ...frontierOpt, model_slug: "fable-99-not-offered-by-this-host",
      label: "Fable 99 (fabricated by the self-check)", available: true, verified: true };
    const sessionsBefore = mgr.registry.alive().length;
    const forgedRes = await spawnFromSelection({
      option: forged, role: "reasoning", mode: "autonomous", targetPaneId: null,
    });
    receipt.forged_reason = forgedRes.reason || forgedRes.error || null;
    receipt.forged_refused_by = forgedRes.refusedBy || null;
    receipt.forged_chrome_node_state = (forgedRes.chrome || {}).node_state || null;
    receipt.forged_started_no_session = mgr.registry.alive().length === sessionsBefore;
    // the GATE id, not words in the prose: a boolean any refusal satisfies is evidence for whichever
    // gate happened to fire (the lesson the `.ticket` receipt legs were rewritten for).
    receipt.forged_launch_refused = forgedRes.launched === false
      && receipt.forged_refused_by === "host_enumeration"
      && /is not one this host currently offers/.test(receipt.forged_reason || "")
      && receipt.forged_chrome_node_state === "launch_refused"
      && receipt.forged_started_no_session;
    if (!receipt.forged_launch_refused) {
      throw new Error(`a FABRICATED option was not refused by the host-enumeration gate with a `
        + `dark pane (refused_by=${receipt.forged_refused_by}, chrome=${receipt.forged_chrome_node_state}, `
        + `no new session=${receipt.forged_started_no_session}): ${receipt.forged_reason}`);
    }

    // ---- LEG 2: a FRONTIER model pane — the same path, plus a real durable I-X3 terminal -------
    const frontierRes = await spawnFromSelection({
      option: frontierOpt, role: "reasoning", mode: "autonomous", targetPaneId: null,
    });
    receipt.frontier_pane_id = frontierRes.target || null;
    receipt.frontier_launched = frontierRes.launched === true;
    receipt.frontier_state = frontierRes.state || null;
    receipt.frontier_reason = frontierRes.reason || null;
    receipt.frontier_argv = frontierRes.argv ? frontierRes.argv.slice() : null;
    receipt.frontier_node_id = frontierRes.nodeId || null;
    if (receipt.frontier_pane_id) started.push(receipt.frontier_pane_id);
    if (!receipt.frontier_launched) {
      throw new Error(`the governed FRONTIER worker launch did not run: ${receipt.frontier_reason || "unknown"}`);
    }
    const frec = workerLaunchState(receipt.frontier_pane_id);
    frontierSubRef = frec.subscriptionRef;
    receipt.frontier_lease_id = frec.leaseId || null;
    if (frec.subscriptionGoverned !== true) throw new Error("a FRONTIER pane must be subscription-governed (I-X3)");
    const fsess = mgr.registry.get(receipt.frontier_pane_id);
    receipt.frontier_session_state = fsess && fsess.state;
    try { process.kill(fsess.pid, 0); receipt.frontier_session_pid_alive = true; } catch { receipt.frontier_session_pid_alive = false; }
    if (receipt.frontier_session_state !== "RUNNING" || !receipt.frontier_session_pid_alive) {
      throw new Error(`the frontier worker session is ${receipt.frontier_session_state} (pid alive=${receipt.frontier_session_pid_alive})`);
    }
    // The frontier leg asserts the SAME containment facts as the local one, because the scope_note
    // claimed them for both while only the local leg established any of them — and this is the leg
    // that consumes one of the operator's subscription terminals (spec-audit MAJOR-2).
    receipt.frontier_node_id_minted = receipt.frontier_node_id === `worker-${receipt.frontier_pane_id}`;
    const fspawned = ptySpawnObserved() || {};
    receipt.frontier_pty_spawn_is_this_pane = fspawned.file === frec.executable;
    receipt.frontier_cwd_passed_to_pty = fspawned.cwd || null;
    const fChildKeys = new Set(fspawned.envKeys || []);
    const fLower = new Set([...fChildKeys].map((k) => k.toLowerCase()));
    const fScrub = (frec.envScrubNames || []).filter((n) => n in process.env);
    receipt.frontier_env_scrub_count = fScrub.length;
    receipt.frontier_env_scrub_names_absent_from_child = fspawned.inheritedEnv !== true
      && fScrub.length > 0 && fScrub.every((n) => !fLower.has(n.toLowerCase()))
      && fChildKeys.has("PATH");
    if (!receipt.frontier_node_id_minted) {
      throw new Error(`the frontier session runs under node id ${receipt.frontier_node_id}, not the `
        + `Python-minted worker-${receipt.frontier_pane_id} (invariant 2/29)`);
    }
    if (!receipt.frontier_pty_spawn_is_this_pane) {
      throw new Error(`the observed node-pty spawn (${fspawned.file}) is not the frontier pane's binary (${frec.executable})`);
    }
    if (receipt.frontier_cwd_passed_to_pty !== REPO_ROOT) {
      throw new Error(`the frontier ConPTY was started in ${receipt.frontier_cwd_passed_to_pty}, not the governed workspace ${REPO_ROOT}`);
    }
    if (!receipt.frontier_env_scrub_names_absent_from_child) {
      throw new Error("the frontier child's environment still carries a credential-bearing name, "
        + "lost PATH, or inherited this shell's env verbatim (§2.2)");
    }
    const st = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    const subs = (st.ok && st.status && st.status.subscriptions) || {};
    const entry = subs[frontierSubRef] || null;
    const holder = entry && (entry.holders || []).find((h) => h.lease_id === receipt.frontier_lease_id);
    receipt.frontier_lease_in_use = entry ? entry.in_use : 0;
    receipt.frontier_lease_visible_cross_process = Boolean(holder && holder.holder_pid === process.pid);
    receipt.frontier_lease_session_keyed = Boolean(holder && holder.session_id === frec.sessionId);
    if (!receipt.frontier_lease_visible_cross_process) throw new Error("a separate process cannot see the worker's held terminal — the durable I-X3 count is not real");
    if (!receipt.frontier_lease_session_keyed) throw new Error("the durable terminal is not keyed to this worker ConPTY session");
    receipt.frontier_pane_output_seen = await waitFor(async () => {
      const text = await paneText(win, receipt.frontier_pane_id);
      return typeof text === "string" && text.trim().length > 0;
    }, TIMEOUT_MS, 500);
    if (!receipt.frontier_pane_output_seen) throw new Error("the live FRONTIER worker session rendered NOTHING into its pane");

    // ---- D-LOOP-1 on the exit edge: killing the frontier session hands its terminal back -------
    killSession(receipt.frontier_pane_id);
    receipt.frontier_lease_released_on_exit = await waitFor(async () => {
      const after = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
      if (!after.ok || !after.status) { receipt.frontier_in_use_after_exit = null; return false; }
      const e2 = (after.status.subscriptions || {})[frontierSubRef] || null;
      receipt.frontier_in_use_after_exit = e2 ? e2.in_use : 0;
      return receipt.frontier_in_use_after_exit === 0;
    }, 45000, 1000);
    if (!receipt.frontier_lease_released_on_exit) {
      throw new Error(`the durable terminal was not handed back when the worker session ended `
        + `(in_use=${receipt.frontier_in_use_after_exit}) — D-LOOP-1`);
    }

    // ---- the ENDED-chrome revision: the badge stops reading `live` for a dead pane -------------
    // The same kill above is the event that must correct the pane's chrome. This was fixed in
    // `main.js` and NOTHING could see it: no test (main.js is not headlessly requirable) and no
    // receipt field, because every pane here was killed in `finally`, after the last assertion
    // (spec-audit MAJOR-2/MAJOR-1). The rule is now `pane-wiring.endedWorkerChrome` (unit-tested);
    // this asserts the shell WIRES it — and reads the chrome the operator's badge is drawn from.
    const endedChrome = await waitFor(async () => {
      const c = paneChromeOf(receipt.frontier_pane_id);
      return Boolean(c && c.node_state !== "running");
    }, 30000, 250) ? paneChromeOf(receipt.frontier_pane_id) : paneChromeOf(receipt.frontier_pane_id);
    receipt.ended_chrome_node_state = (endedChrome || {}).node_state || null;
    receipt.ended_chrome_governed = endedChrome ? endedChrome.governed === true : null;
    receipt.ended_chrome_model_label_kept = Boolean(endedChrome && endedChrome.model_label
      && endedChrome.model_label === frontierOpt.label);
    receipt.ended_chrome_revised = receipt.ended_chrome_node_state === "session_killed"
      && receipt.ended_chrome_governed === false
      && receipt.ended_chrome_model_label_kept;
    if (!receipt.ended_chrome_revised) {
      throw new Error(`a pane whose governed session was KILLED still reports chrome `
        + `${JSON.stringify(receipt.ended_chrome_node_state)} governed=${receipt.ended_chrome_governed} `
        + `(model badge kept=${receipt.ended_chrome_model_label_kept}) — the operator's badge would `
        + "keep reading `live` for a dead pane, and the layout snapshot would carry that into the "
        + "next boot (invariants 3/27)");
    }

    log(`[selfcheck] worker panes launched: local ${receipt.local_pane_id} (${(receipt.local_argv || []).join(" ")}) · `
      + `frontier ${receipt.frontier_pane_id} (${(receipt.frontier_argv || []).join(" ")}), terminal released`);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  } finally {
    // D-LOOP-1: no session this check started outlives it, whatever happened above.
    try {
      const mgr = sessionManager();
      const pids = [];
      for (const paneId of started) {
        const rec = mgr && mgr.registry.get(paneId);
        if (rec && rec.pid) pids.push(rec.pid);
        try { killSession(paneId); } catch { /* already terminal */ }
        try { if (paneModel && paneModel().panes.has(paneId)) paneModel().destroyPane(paneId); } catch { /* pane already gone */ }
      }
      receipt.sessions_killed = await waitFor(() => pids.every((p) => {
        try { process.kill(p, 0); return false; } catch { return true; }
      }), 20000, 250);
      receipt.surviving_pids = pids.filter((p) => {
        try { process.kill(p, 0); return true; } catch { return false; }
      });
      // Every release this check's kills triggered runs ASYNCHRONOUSLY through the launcher, and
      // the ledger env var is process-wide: restoring it while one is still in flight would point a
      // straggler release at the operator's REAL ledger — which is precisely what the receipt's
      // `scope_note_live_terminal` used to say could "never" happen (spec-audit MINOR-6). So the
      // releases are quiesced FIRST, under the scratch redirection, and only then is the env put
      // back. Bounded: a hung release must not wedge the check, so a timeout is recorded, not waited
      // out forever.
      const quiesced = await waitFor(
        () => workerLauncher().heldSessions().length === 0, 30000, 250);
      if (!quiesced) {
        receipt.error = receipt.error
          || "worker terminal releases did not quiesce within 30s — the env restore below could point "
          + "a straggler release at the operator's REAL lease ledger";
      }
    } catch (e) {
      receipt.error = receipt.error || `teardown failed: ${String((e && e.message) || e)}`;
    }
    // Leave the host exactly as found — and CHECK it, rather than assert it in a comment. After the
    // `.spawn` run an empty scratch ledger was found still on disk while this comment claimed
    // otherwise, and the mechanism recorded in that append-only note (a kill-triggered release
    // rewriting the file) did not reproduce under direct probing (validator MINOR-4). So the two
    // facts that matter are now measured and gate the receipt: the scratch file is gone, and the
    // operator's REAL ledger is byte-identical to what it was before this check ran.
    try { fs.rmSync(SCRATCH_LEDGER, { force: true }); } catch { /* nothing to remove */ }
    receipt.scratch_ledger_removed = !fs.existsSync(SCRATCH_LEDGER);
    try {
      const after = fs.existsSync(REAL_LEDGER) ? fs.readFileSync(REAL_LEDGER, "utf8") : null;
      receipt.real_ledger_unchanged = after === realLedgerBefore;
    } catch { receipt.real_ledger_unchanged = false; }
    if (priorLedger === undefined) delete process.env.SOW_TERMINAL_LEASE_LEDGER;
    else process.env.SOW_TERMINAL_LEASE_LEDGER = priorLedger;
    if (priorBudget === undefined) delete process.env.SOW_VRAM_BUDGET_MB;
    else process.env.SOW_VRAM_BUDGET_MB = priorBudget;
    if (receipt.shell_only_credential_name) delete process.env[receipt.shell_only_credential_name];
  }

  receipt.ok = receipt.error === null
    && receipt.supervision_ready && receipt.picker_sourced
    && receipt.local_launched && receipt.local_interactive_argv
    && receipt.local_session_registered && receipt.local_session_state === "RUNNING"
    && receipt.local_session_pid_alive && receipt.local_cwd_passed_to_pty === REPO_ROOT
    && receipt.local_env_scrub_names_absent_from_child && receipt.shell_env_names_classified
    && receipt.local_pane_output_seen && receipt.local_chrome_node_state === "running"
    && receipt.local_subscription_governed === false
    && receipt.occupied_pane_refused && receipt.occupied_first_session_survived
    && receipt.forged_launch_refused
    && receipt.occupied_launch_record_intact && receipt.occupied_held_after
    && receipt.occupied_chrome_intact && receipt.local_pty_spawn_is_this_pane
    && receipt.conductor_pane_refused && receipt.ended_chrome_revised
    && receipt.scratch_ledger_removed && receipt.real_ledger_unchanged
    && receipt.frontier_launched && receipt.frontier_session_pid_alive
    && receipt.frontier_node_id_minted && receipt.frontier_pty_spawn_is_this_pane
    && receipt.frontier_cwd_passed_to_pty === REPO_ROOT
    && receipt.frontier_env_scrub_names_absent_from_child
    && receipt.frontier_lease_visible_cross_process && receipt.frontier_lease_session_keyed
    && receipt.frontier_pane_output_seen && receipt.frontier_lease_released_on_exit
    && receipt.frontier_in_use_after_exit === 0
    && receipt.sessions_killed && (receipt.surviving_pids || []).length === 0;

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  receipt.scope_note_live_terminal = "while the FRONTIER leg's session runs, a live `claude` terminal "
    + "exists on the operator's subscription that the REAL durable ledger does not count — this check "
    + "redirects the ledger to a scratch file for the whole run, so the governor it exercises is the "
    + "scratch one and it adopts or releases nothing the operator's own conductor holds. That used to "
    + "be stated as \"can never\", which was stronger than the code established: the redirection was "
    + "torn down while kill-triggered releases were still in flight, and a straggler landing after the "
    + "restore would have read the REAL ledger path (spec-audit MINOR-6). Teardown now QUIESCES the "
    + "releases before restoring the env, and the receipt MEASURES both facts rather than claiming "
    + "them: `scratch_ledger_removed` and `real_ledger_unchanged` (a byte comparison against a read "
    + "taken before the redirection) are conjuncts of ok. The window is one bounded session, killed in "
    + "this run (spec-audit MINOR-8; the same inherited pattern as the 17A `.pty` check, now applied "
    + "to a second live session class).";
  receipt.scope_note_substitutions = "the residency snapshot the pinned budget is arithmetic on is "
    + `read under SOW_VRAM_BUDGET_MB=${PROBE_VRAM_BUDGET_MB} (1 TiB) — a budget nothing on this host `
    + "can falsify, so the snapshot is the daemon's real state rather than a refusal; the launch legs "
    + `then run under the PINNED budget recorded in local_budget_pinned_mb (${receipt.local_budget_pinned_mb}). `
    + "Both are substitutions in the sense of directive §6 and neither is this host's real capacity "
    + "(U96): they test admission MECHANICS. The probe budget was disclosed only in code before "
    + "(spec-audit NIT).";
  receipt.scope_note = "drives the PRODUCTION picker→launch path (`spawnFromSelection`, the exact "
    + "function the `pane:spawnFromSelection` IPC handler calls) against options the REAL host "
    + "picker offered, a SCRATCH lease ledger and a VRAM budget computed from this host's own "
    + "residency snapshot. What is established, now on BOTH legs (the frontier leg previously "
    + "asserted only its lease and its output while the note claimed the containment facts for it "
    + "too — spec-audit MAJOR-2): a local and a frontier model session really RUN in real panes, "
    + "each with supervised admission, the Python-minted node id, the governed workspace as the "
    + "ConPTY cwd, and the credential scrub measured on the environment the CHILD was handed (with "
    + "the observed node-pty spawn matched to that pane's own binary before any of it is read as "
    + "evidence), and each rendering bytes into the renderer buffer; the frontier one holds a "
    + "durable I-X3 terminal keyed to its session, visible cross-process, handed back on exit; a "
    + "fabricated option and an occupied pane are refused by their OWN gates with nothing started, "
    + "and the occupied refusal leaves the running session's process, launch RECORD, held-terminal "
    + "accounting and pane chrome (state, governed AND refused_by) untouched; a worker model is "
    + "refused into the pinned CONDUCTOR pane by pane id; and the pane whose governed session is "
    + "KILLED has its chrome revised to session_killed/governed:false with the model badge kept, so "
    + "the operator's badge stops reading `live` for a dead pane and the layout snapshot carries the "
    + "correction into the next boot. Those last three legs exist because the rules they cover lived "
    + "in `main.js`, where no test and no receipt field could see them (spec-audit MAJOR-2). What is "
    + "NOT: no prompt is sent and no model "
    + "answer is claimed (conductor→worker CANDIDATE→gate→synthesis is `.legs`/U58); U100's "
    + "undelivered-ticket release is proven by the headless suite, not here, because forcing a "
    + "mid-flight emitter failure in-runtime proves the corruption rather than the release; the "
    + "containment the ticket lists as owed (permission-profile binding U78(a), OS job object U25) "
    + "is unchanged and still owed. The local leg's budget is deliberately generous — it tests "
    + "admission MECHANICS, not this host's real capacity (U96).";
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] worker-spawn ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runWorkerSpawnSelfCheck: run, RECEIPT_PATH };
