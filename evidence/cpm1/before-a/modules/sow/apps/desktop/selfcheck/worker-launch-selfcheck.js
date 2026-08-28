"use strict";
/**
 * Phase 17B `.ticket` in-Electron self-check (D-P16-0 binding, per-track).
 *
 * Runs INSIDE the packaged Electron runtime and proves the piece 17B needs before a picker selection
 * can ever launch anything: for an option the operator is ACTUALLY shown on this host, the shell can
 * obtain a **governed worker launch ticket** — an authorization produced by the Python gate chain,
 * not by the shell — for BOTH localities, with each one's governance carried honestly:
 *
 *   * a LOCAL option (`ollama run <tag>`) — no subscription terminal (invariant 19), a real
 *     ResidencyPlanner decision instead (invariant 22);
 *   * a FRONTIER option (`claude --model <probed slug>`) — a DURABLE I-X3 lease held by THIS Electron
 *     process and visible to a separate process, then handed back (D-LOOP-1);
 *   * a FABRICATED option (one this host never offered), a budget too small to hold the model, and the
 *     CONDUCTOR role are all REFUSED with a reason and no argv — the fail-closed half must be
 *     exercised in-runtime too, or "it authorizes things" is all that was proven. Each refusal leg
 *     names the gate it exercises, so the receipt cannot be read as evidence for a different one.
 *
 * Why in-runtime and not only headless (the binding lesson): the ticket is sourced by spawning
 * `py -3.12` from the Electron main process with `cwd` = repo root AND the selection delivered on the
 * child's STDIN. Interpreter resolution, cwd, stdin plumbing and the timeout are exactly the class of
 * thing that passes in a Node test and fails at first launch.
 *
 * The options are read from the REAL host picker (`picker:fetch`'s own source) rather than fixtures,
 * so a ticket is only ever requested for something the operator could really select. A host with no
 * local models, or with no live authorization, yields honest refusals — but this check exists to
 * prove the authorized path works on the OPERATOR's host, so an unauthorized frontier leg fails
 * loudly rather than quietly recording a stub.
 *
 * This check makes NO live model call and spawns NO session: it obtains and releases authorizations.
 * The ConPTY launch of these argvs is 17B `.spawn`.
 */
const fs = require("fs");
const path = require("path");

const { fetchPickerModel, fetchHostResidency } = require("../picker/source");
const {
  sourceWorkerLaunchTicket, releaseWorkerTerminal, WORKER_TICKET_SCHEMA,
} = require("../picker/launch-source");
const { fetchLeaseStatus } = require("../conductor/launch-source");

const RECEIPT_PATH = path.resolve(
  __dirname, "..", "..", "..", "docs", "evidence", "receipts", "PHASE17B_TICKET_SELFCHECK.json"
);
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

// The ONLY node_state an AUTHORIZATION may report: no process exists yet and the same ticket says
// `containment.supervisor_bound: false`. Kept as a literal here deliberately — reading it off the
// ticket the leg is checking would make the assertion agree with whatever the emitter said
// (`node_runtime/supervisor/worker_pane_spawn._AUTHORIZED_NOT_STARTED` is the producer).
const AUTHORIZED_NOT_STARTED = "launch_authorized";

// SCRATCH ledger (`SOW_TERMINAL_LEASE_LEDGER`), never the operator's real one: this check takes and
// releases a frontier terminal, and against the real ledger its "count is 0 again" assertion would be
// false on any host whose conductor is legitimately running. The mechanism under test is identical;
// only the file is ours. Per-pid so two runs never collide.
const SCRATCH_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", `selfcheck-17b-${process.pid}.json`);

// A PINNED VRAM budget (`SOW_VRAM_BUDGET_MB`) for the duration of this check. Without it the local
// leg's outcome depends on what the operator's Ollama daemon happens to be serving at the moment the
// check runs — the gate-validator observed exactly that (2026-07-26): the same command produced
// ok:false with a model resident and ok:true fifteen minutes later. A D-P16-0 receipt has to mean
// the same thing on every run, so the check fixes the one host variable it is not testing (the real
// GPU budget) and RECORDS that it did. The mechanism under test — planner admission, displacement
// refusal, the ticket's budget disclosure — is identical either way.
// …but a PINNED CONSTANT was not enough, and the constant it replaced was worse. The budgets below
// are COMPUTED from the host's own residency snapshot (`--emit-residency`, read once under a budget
// too large to be falsified) so each leg exercises the branch its NAME claims:
//
//   * `1` MB, the previous squeeze, does not force "the model does not fit". On a host with anything
//     resident it FALSIFIES the budget instead, and the gate that fires is the provenance one —
//     nothing was measured and nothing about fit was proven, while the leg reported the fit gate as
//     exercised. The gate ids stopped one refusal family borrowing another's evidence; this was the
//     same borrowing INSIDE a family (spec-audit MAJOR-1, 2026-07-26).
//   * the floor is `used + largest-known-footprint + headroom` so the AUTHORIZED leg cannot be
//     starved by whatever the daemon happens to be serving. Deliberately GENEROUS, and therefore
//     deliberately fictional as a capacity claim: the leg tests admission mechanics, and the ticket
//     discloses the figure with `estimate:true` (validator MINOR-2). The squeeze is
//     `used + footprint - 1` — above what is resident (so the budget stands) and below what the
//     target needs (so the FIT gate is what says no), on an idle host and a busy one alike. At a
//     1MB footprint the two coincide and the pane is admitted; no real model is 1MB, and the leg
//     would fail LOUDLY rather than pass, so the boundary is safe (spec-audit MINOR-5).
const PINNED_VRAM_FLOOR_MB = 24576;
const PINNED_VRAM_HEADROOM_MB = 1024;
// A budget no host can falsify, used ONLY to read the snapshot the two real budgets are computed from.
const PROBE_VRAM_BUDGET_MB = "1048576";
const LOCAL_SESSION = `selfcheck-17b-local#${process.pid}`;
const FRONTIER_SESSION = `selfcheck-17b-frontier#${process.pid}`;
const TIMEOUT_MS = 90000;

/** An available option matching a predicate, PREFERRING a named model — never fabricated; null when
 * the host offers none. The preference is not cosmetic: the operator's definition-of-done names
 * `qwen3:8b` for the local leg, and the frontier leg is most informative on the label the 17A model
 * probe has actually visited (`fable-5`), because that is where the probe→argv wiring shows. A host
 * without the preferred model still gets a real receipt on whatever it does offer. */
function pick(options, predicate, preferred) {
  const available = (options || []).filter((o) => o && o.available && predicate(o));
  return available.find((o) => o.model_slug === preferred) || available[0] || null;
}

async function run(ctx) {
  const { log } = ctx;
  const receipt = {
    check: "phase-17b.ticket",
    started: new Date().toISOString(),
    ok: false,
    // the host enumeration the tickets are requested against (never fixtures)
    picker_sourced: false,
    picker_option_count: null,
    local_option: null,
    frontier_option: null,
    // LOCAL leg — residency-governed, never subscription-governed (invariant 19/22)
    local_authorized: false,
    local_argv: null,
    local_interactive: false,
    local_lease: "n/a",
    local_subscription_governed: null,
    local_residency: null,
    local_residency_budget: null,
    // the host snapshot the budgets are computed from, and the two budgets themselves
    host_residency_probed: false,
    host_used_vram_mb: null,
    local_budget_pinned_mb: null,
    local_squeeze_target: null,
    local_squeeze_footprint_mb: null,
    local_budget_squeezed_mb: null,
    local_node_id: null,
    local_node_state: null,
    local_reason: null,
    // FRONTIER leg — I-X3 counted, durable, visible cross-process, handed back
    frontier_authorized: false,
    frontier_argv: null,
    frontier_model_probe: null,
    frontier_no_headless_flags: false,
    frontier_env_scrub_name_count: null,
    frontier_env_values_absent: false,
    frontier_identity: null,
    frontier_node_state: null,
    frontier_containment_disclosed: false,
    frontier_lease_id: null,
    frontier_lease_durable: false,
    frontier_lease_holder_pid: null,
    electron_main_pid: process.pid,
    frontier_lease_held_by_this_process: false,
    frontier_lease_visible_cross_process: false,
    frontier_emitter_governor_released: false,
    frontier_reason: null,
    // The fail-closed half, exercised in-runtime. Each leg asserts the ticket's machine-readable
    // `refused_by` GATE ID, not words in the reason: a prose match is satisfied by whichever gate
    // happened to fire with the right vocabulary, which is how an enumeration crash once passed for
    // the invariant-22 admission gate (validator BLOCKING-1c).
    forged_option_refused: false,          // _assert_option_offered (the host-enumeration check)
    forged_refusal_reason: null,
    forged_refused_by: null,
    local_budget_refused: false,           // invariant 22: a pane that does not fit is not born
    local_budget_refusal_reason: null,
    local_budget_refused_by: null,
    conductor_role_refused: false,
    conductor_refusal_reason: null,
    conductor_refused_by: null,
    // What the operator is SHOWN must agree with what the admission gate will do. When NO local
    // pane can be authorized on this host — the budget cannot be established, OR the `ollama`
    // binary is not launchable — every local option is greyed with that reason; they used to be
    // offered as launchable while the gate refused all of them. The field is named for the
    // PROPERTY, not for one of the two conditions: the leg forces the RUNTIME one (see below),
    // and a field called `..._when_budget_unestablished` reporting a run in which the budget WAS
    // established is a name asserting a condition it did not exercise — the defect this leg was
    // rewritten to fix, recurring in the rewrite (validator MAJOR-1, round 3, 2026-07-26).
    local_greyed_leg: "not attempted",
    local_greyed_when_no_pane_can_be_authorized: false,
    local_greyed_reason: null,
    local_greyed_ticket_refused_by: null,
    // D-LOOP-1
    ledger_scope: "scratch",
    ledger_path: SCRATCH_LEDGER,
    terminals_released: false,
    in_use_after_release: null,
    error: null,
  };
  const priorLedger = process.env.SOW_TERMINAL_LEASE_LEDGER;
  const priorBudget = process.env.SOW_VRAM_BUDGET_MB;
  process.env.SOW_TERMINAL_LEASE_LEDGER = SCRATCH_LEDGER; // inherited by every `py` child below
  let frontierSubRef = null;
  let pinnedBudget = String(PINNED_VRAM_FLOOR_MB);
  try {
    // 0. READ the host's residency under a budget nothing can falsify, so every VRAM budget below
    // is arithmetic on real numbers rather than a constant that lands on whichever branch the
    // daemon's current state produces.
    process.env.SOW_VRAM_BUDGET_MB = PROBE_VRAM_BUDGET_MB;
    const probe = await fetchHostResidency({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    receipt.host_residency_probed = probe.ok === true && !!(probe.residency || {}).snapshot;
    const snapshot = (probe.residency && probe.residency.snapshot) || null;
    if (!receipt.host_residency_probed) {
      throw new Error(`could not read this host's residency snapshot: ${probe.error || "no snapshot"}`);
    }
    const snapModels = Array.isArray(snapshot.models) ? snapshot.models : [];
    receipt.host_used_vram_mb = Number.isFinite(snapshot.used_vram_mb) ? snapshot.used_vram_mb : null;
    if (receipt.host_used_vram_mb === null) throw new Error("the residency snapshot reports no used_vram_mb");

    // 1. the REAL host enumeration — the same source the picker drawer renders. Enumerated under the
    // pinned budget, which is computed to clear whatever is resident (see the constants).
    const biggest = snapModels.reduce(
      (m, e) => (Number.isFinite(e.footprint_mb) && e.footprint_mb > m ? e.footprint_mb : m), 0);
    pinnedBudget = String(Math.max(
      PINNED_VRAM_FLOOR_MB, receipt.host_used_vram_mb + biggest + PINNED_VRAM_HEADROOM_MB));
    receipt.local_budget_pinned_mb = pinnedBudget;
    process.env.SOW_VRAM_BUDGET_MB = pinnedBudget;
    const pickerRes = await fetchPickerModel({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    receipt.picker_sourced = pickerRes.ok === true;
    const options = (pickerRes.picker && pickerRes.picker.options) || [];
    receipt.picker_option_count = options.length;
    if (!receipt.picker_sourced) throw new Error(`host picker enumeration failed: ${pickerRes.error}`);

    const localOpt = pick(options, (o) => o.locality === "local"
      && (o.roles || []).includes("reasoning"), "qwen3:8b");
    const frontierOpt = pick(options, (o) => o.locality === "frontier" && o.adapter === "claude_code"
      && (o.roles || []).includes("reasoning"), "fable-5");
    receipt.local_option = localOpt && { label: localOpt.label, model_slug: localOpt.model_slug,
      residency: localOpt.residency };
    receipt.frontier_option = frontierOpt && { label: frontierOpt.label,
      model_slug: frontierOpt.model_slug, verified: frontierOpt.verified };
    if (!localOpt) throw new Error("the host picker offered no available LOCAL reasoning model to authorize");
    if (!frontierOpt) throw new Error("the host picker offered no available claude_code option to authorize");

    // 2. LOCAL leg — a governed pane for the operator's own local model.
    const localRes = await sourceWorkerLaunchTicket({
      cwd: REPO_ROOT, holderPid: process.pid, sessionId: LOCAL_SESSION, paneId: "selfcheck-pane-local",
      selection: { option: localOpt, role: "reasoning", mode: "attended" }, timeoutMs: TIMEOUT_MS,
    });
    const lt = localRes.ticket || {};
    receipt.local_reason = lt.reason || localRes.error || null;
    if (!localRes.ok) throw new Error(`local worker ticket was not sourced from Python: ${localRes.error}`);
    if (lt.schema !== WORKER_TICKET_SCHEMA) throw new Error(`local ticket carries an unexpected schema: ${lt.schema}`);
    receipt.local_authorized = lt.authorized === true;
    receipt.local_argv = lt.launch ? lt.launch.argv.slice() : null;
    receipt.local_interactive = !!lt.launch && lt.launch.interactive === true && lt.launch.one_shot === false;
    receipt.local_subscription_governed = lt.subscription_governed;
    receipt.local_lease = lt.lease === null ? "none (correct — local holds no subscription terminal)" : "PRESENT";
    receipt.local_residency = lt.residency || null;
    receipt.local_residency_budget = (lt.residency && lt.residency.budget) || null;
    receipt.local_node_id = (lt.identity && lt.identity.node_id) || null;
    if (!receipt.local_authorized) throw new Error(`local worker authorization REFUSED on this host: ${receipt.local_reason}`);
    if (!receipt.local_interactive) throw new Error("the local ticket is not an interactive launch");
    if (lt.subscription_governed !== false || lt.lease !== null) {
      throw new Error("a LOCAL worker must hold no subscription terminal (invariant 19)");
    }
    if (!lt.residency || typeof lt.residency !== "object") {
      throw new Error("a LOCAL worker must carry a ResidencyPlanner decision (invariant 22)");
    }
    // The authorization must DISCLOSE the budget it was decided against, and must not have been
    // reached by displacing a model the daemon is already serving (invariant 22).
    if (!receipt.local_residency_budget
      || !Number.isFinite(receipt.local_residency_budget.vram_budget_mb)
      || receipt.local_residency_budget.established !== true) {
      throw new Error("the local ticket does not disclose an ESTABLISHED VRAM budget it was "
        + `authorized against: ${JSON.stringify(receipt.local_residency_budget)}`);
    }
    if ((lt.residency.evicted || []).length || (lt.residency.awaiting_eviction || []).length) {
      throw new Error("the local authorization displaced a resident model — refused by design");
    }
    // No ticket may report a LIVE node state for a node that has not been born (invariant 3/27).
    // The local branch used to derive `node_state` from the residency decision, so an already-
    // resident model — which is what every `/api/ps` entry on this host is seeded to — reported
    // "ready" in the same ticket that says `containment.supervisor_bound: false` (spec-audit
    // MAJOR-1, 2026-07-26). It was invisible here because the receipt read `residency` and never
    // `chrome`; the field it hid in is now the field this leg asserts, on BOTH localities.
    receipt.local_node_state = (lt.chrome && lt.chrome.node_state) || null;
    if (receipt.local_node_state !== AUTHORIZED_NOT_STARTED) {
      throw new Error("a local worker AUTHORIZATION reported node_state "
        + `${JSON.stringify(receipt.local_node_state)} for a node that has not been spawned — `
        + `expected ${JSON.stringify(AUTHORIZED_NOT_STARTED)} (invariant 3/27)`);
    }

    // 3. FRONTIER leg — the same governed chain plus a real, durable, cross-process I-X3 terminal.
    const frontierRes = await sourceWorkerLaunchTicket({
      cwd: REPO_ROOT, holderPid: process.pid, sessionId: FRONTIER_SESSION,
      paneId: "selfcheck-pane-frontier",
      selection: { option: frontierOpt, role: "reasoning", mode: "autonomous" }, timeoutMs: TIMEOUT_MS,
    });
    const ft = frontierRes.ticket || {};
    receipt.frontier_reason = ft.reason || frontierRes.error || null;
    if (!frontierRes.ok) throw new Error(`frontier worker ticket was not sourced from Python: ${frontierRes.error}`);
    receipt.frontier_authorized = ft.authorized === true;
    if (!receipt.frontier_authorized) throw new Error(`frontier worker authorization REFUSED on this host: ${receipt.frontier_reason}`);
    const launch = ft.launch || {};
    receipt.frontier_argv = Array.isArray(launch.argv) ? launch.argv.slice() : null;
    receipt.frontier_model_probe = ft.model_probe || null;
    receipt.frontier_no_headless_flags = Array.isArray(receipt.frontier_argv)
      && !["-p", "--print", "--output-format"].some((f) => receipt.frontier_argv.includes(f));
    const names = Array.isArray(launch.env_scrub_names) ? launch.env_scrub_names : null;
    receipt.frontier_env_scrub_name_count = names ? names.length : null;
    // §2.2: the ticket transmits NAMES only — no name=value pair and no env map ever crosses.
    receipt.frontier_env_values_absent = !("env" in launch)
      && !(names || []).some((n) => JSON.stringify(ft).includes(`${n}=`));
    receipt.frontier_identity = ft.identity || null;
    receipt.frontier_containment_disclosed = !!ft.containment && ft.containment.authorized === true
      && ft.containment.supervisor_bound === false && typeof ft.containment.owed_to === "string";
    receipt.frontier_emitter_governor_released = ft.governor_released === true;
    const lease = ft.lease || {};
    frontierSubRef = lease.subscription_ref || null;
    receipt.frontier_lease_id = lease.lease_id || null;
    receipt.frontier_lease_durable = lease.durable === true;
    receipt.frontier_lease_holder_pid = Number.isFinite(lease.holder_pid) ? lease.holder_pid : null;
    receipt.frontier_lease_held_by_this_process = receipt.frontier_lease_holder_pid === process.pid;
    if (!receipt.frontier_no_headless_flags) throw new Error(`frontier argv carries a headless flag: ${JSON.stringify(receipt.frontier_argv)}`);
    if (!names) throw new Error("the frontier ticket carries no env_scrub_names list (§2.2)");
    if (!receipt.frontier_env_values_absent) throw new Error("the ticket appears to carry env VALUES — §2.2 violation");
    if (!receipt.frontier_identity || !receipt.frontier_identity.node_id
      || !receipt.frontier_identity.permission_profile_id) {
      throw new Error("the frontier ticket carries no Python-minted governed identity");
    }
    receipt.frontier_node_state = (ft.chrome && ft.chrome.node_state) || null;
    if (receipt.frontier_node_state !== AUTHORIZED_NOT_STARTED) {
      throw new Error("a frontier worker AUTHORIZATION reported node_state "
        + `${JSON.stringify(receipt.frontier_node_state)} for a node that has not been spawned — `
        + `expected ${JSON.stringify(AUTHORIZED_NOT_STARTED)} (invariant 3/27)`);
    }
    if (!receipt.frontier_containment_disclosed) throw new Error("the ticket does not disclose that it is an authorization, NOT containment");
    if (!receipt.frontier_emitter_governor_released) throw new Error("the emitter's in-process I-X3 count was not released");
    if (!receipt.frontier_lease_durable || !receipt.frontier_lease_held_by_this_process) {
      throw new Error(`the durable I-X3 lease is not held by this Electron process (${process.pid})`);
    }
    const st = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    const subs = (st.ok && st.status && st.status.subscriptions) || {};
    const entry = subs[frontierSubRef] || null;
    receipt.frontier_lease_visible_cross_process = !!entry && entry.in_use >= 1
      && (entry.holders || []).some((h) => h.lease_id === receipt.frontier_lease_id
        && h.holder_pid === process.pid);
    if (!receipt.frontier_lease_visible_cross_process) {
      throw new Error("a separate process could not see this worker lease — the durable I-X3 count is not real");
    }

    // 4. the fail-closed half, in-runtime: a greyed option and the conductor role.
    // (a) a FABRICATED option — a model this host does not offer, presented as available. This is
    // the ESCALATING direction (the previous leg flipped an available option to greyed, which gains
    // a caller nothing and would have been caught by a different gate anyway — validator FINDING 4).
    // The emitter re-derives the host's own offer and refuses anything that is not in it, so a shell
    // (or a drifted renderer) cannot talk a model that was never offered into being launchable.
    const forged = { ...frontierOpt, model_slug: "fable-99-not-offered-by-this-host",
      label: "Fable 99 (fabricated by the self-check)", available: true, verified: true };
    const forgedRes = await sourceWorkerLaunchTicket({
      cwd: REPO_ROOT, holderPid: process.pid, sessionId: `${FRONTIER_SESSION}.forged`,
      paneId: "selfcheck-pane-forged",
      selection: { option: forged, role: "reasoning", mode: "autonomous" }, timeoutMs: TIMEOUT_MS,
    });
    receipt.forged_refusal_reason = (forgedRes.ticket || {}).reason || forgedRes.error || null;
    // Assert the REASON, not merely "some refusal happened": a boolean that any gate can satisfy is
    // evidence for whichever gate happened to fire (validator FINDING 2/4).
    receipt.forged_refused_by = (forgedRes.ticket || {}).refused_by || null;
    receipt.forged_option_refused = forgedRes.ok === true && forgedRes.ticket.authorized === false
      && forgedRes.ticket.refused === true && forgedRes.ticket.launch === null
      && forgedRes.ticket.lease === null
      && receipt.forged_refused_by === "host_enumeration"
      && /is not one this host currently offers/.test(receipt.forged_refusal_reason || "");
    if (!receipt.forged_option_refused) {
      throw new Error(`a FABRICATED option was not refused by the host-enumeration gate: ${receipt.forged_refusal_reason}`);
    }

    // (b) a VRAM FIT refusal — a local option under a budget that STANDS (it is above everything the
    // host has resident, so nothing falsifies it) and is still one megabyte short of the model the
    // pane asks for. That is what makes this leg mean what its name says: the gate that refuses is
    // the FIT gate, on every host, idle or busy. Under the old flat `1` MB squeeze a busy host
    // falsified the budget instead and the PROVENANCE gate fired — a refusal that proves nothing was
    // measured, recorded under a field asserting a model did not fit (spec-audit MAJOR-1).
    // The target must not already be RESIDENT: re-requesting a model that is in VRAM displaces
    // nothing and is correctly authorized, so there would be no refusal to observe.
    // The no-displacement branch specifically — including its no-phantom-mutation property — is
    // pinned by the Python suite (`test_a_refused_local_pane_leaves_the_planner_state_untouched`),
    // because forcing a genuine displacement in-runtime would mean loading a model onto the
    // operator's GPU (validator #2).
    const footprintOf = (slug) => {
      const e = snapModels.find((m) => m && m.model === slug);
      return e && Number.isFinite(e.footprint_mb) && !["resident", "loading", "awaiting_eviction"]
        .includes(e.status) ? e.footprint_mb : null;
    };
    const squeezeOpt = footprintOf(localOpt.model_slug) !== null ? localOpt
      : (options.find((o) => o && o.available && o.locality === "local"
        && (o.roles || []).includes("reasoning") && footprintOf(o.model_slug) !== null) || null);
    if (!squeezeOpt) {
      throw new Error("no available, non-resident, sized LOCAL model to exercise the VRAM fit gate "
        + "with — the leg would be reporting some other gate's refusal");
    }
    const squeezeFootprint = footprintOf(squeezeOpt.model_slug);
    receipt.local_squeeze_target = squeezeOpt.model_slug;
    receipt.local_squeeze_footprint_mb = squeezeFootprint;
    // above everything resident (budget stands), below what the target needs (fit gate refuses)
    const squeezedBudget = String(receipt.host_used_vram_mb + Math.max(1, squeezeFootprint - 1));
    receipt.local_budget_squeezed_mb = squeezedBudget;
    process.env.SOW_VRAM_BUDGET_MB = squeezedBudget;
    let squeezedRes;
    try {
      squeezedRes = await sourceWorkerLaunchTicket({
        cwd: REPO_ROOT, holderPid: process.pid, sessionId: `${LOCAL_SESSION}.squeezed`,
        paneId: "selfcheck-pane-squeezed",
        selection: { option: squeezeOpt, role: "reasoning", mode: "attended" }, timeoutMs: TIMEOUT_MS,
      });
    } finally {
      process.env.SOW_VRAM_BUDGET_MB = pinnedBudget;
    }
    receipt.local_budget_refusal_reason = (squeezedRes.ticket || {}).reason || squeezedRes.error || null;
    receipt.local_budget_refused_by = (squeezedRes.ticket || {}).refused_by || null;
    receipt.local_budget_refused = squeezedRes.ok === true
      && squeezedRes.ticket.authorized === false && squeezedRes.ticket.refused === true
      && squeezedRes.ticket.launch === null
      && receipt.local_budget_refused_by === "vram_admission"
      // the id names the FAMILY; pair it with the gate's own arithmetic prose, as the other two legs
      // do, so a future fit-family refusal for an unrelated cause cannot satisfy this leg either.
      && /does not fit|larger than the whole|displacing/.test(receipt.local_budget_refusal_reason || "");
    if (!receipt.local_budget_refused) {
      throw new Error(`a local pane that does not fit VRAM was not refused by the vram_admission `
        + `gate (refused_by=${receipt.local_budget_refused_by}): ${receipt.local_budget_refusal_reason}`);
    }

    // (c) MAJOR-2/MAJOR-A: when NO local pane can be authorized on this host, the picker must GREY
    // every local option with the reason. Showing them as launchable while the admission gate
    // refuses all of them is the shell telling the operator something the gate will not honour.
    //
    // The condition is forced through the RUNTIME half, not the budget half, and that choice is the
    // fix to a real defect in the first attempt: falsifying the budget needs something resident, so
    // on an idle daemon the leg silently did not run and `ok:true` was still emitted — whether the
    // flagship fix of this sub-step appeared in the receipt was a coin flip on daemon state
    // (validator MAJOR-B). The `ollama` BINARY, by contrast, is found on PATH, and PATH is ours to
    // scrub per child process: the daemon stays reachable over HTTP so the models are still
    // ENUMERATED, while nothing can be launched — which is exactly the state the greying rule was
    // widened to cover, reproducible on every host, idle or busy.
    // Scrub ONLY the directory the resolved `ollama` binary lives in — not the whole PATH, which
    // also took `py` with it and left the enumerator unable to launch at all (a child that never
    // ran offers zero local options, which is not the same fact as offering them greyed).
    const ollamaDir = path.dirname(String((lt.launch || {}).executable || ""));
    const scrubbedPath = {};
    for (const [k, v] of Object.entries(process.env)) {
      if (!/^path$/i.test(k)) scrubbedPath[k] = v;
    }
    scrubbedPath.PATH = String(process.env.PATH || "").split(path.delimiter)
      .filter((d) => d && path.resolve(d).toLowerCase() !== path.resolve(ollamaDir).toLowerCase())
      .join(path.delimiter);
    if (!ollamaDir || scrubbedPath.PATH === process.env.PATH) {
      throw new Error(`could not scrub the ollama directory (${ollamaDir}) out of PATH — the `
        + "greying leg would not be exercising the runtime-absent condition it claims to");
    }
    const greyed = await fetchPickerModel({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS, env: scrubbedPath });
    // …and the ticket path agrees: the option the operator was shown a moment ago is refused,
    // because the host enumeration no longer backs it on those terms.
    const greyedTicket = await sourceWorkerLaunchTicket({
      cwd: REPO_ROOT, holderPid: process.pid, sessionId: `${LOCAL_SESSION}.greyed`,
      paneId: "selfcheck-pane-greyed", env: scrubbedPath,
      selection: { option: localOpt, role: "reasoning", mode: "attended" }, timeoutMs: TIMEOUT_MS,
    });
    const greyedLocal = ((greyed.picker || {}).options || []).filter((o) => o && o.locality === "local");
    receipt.local_greyed_reason = (greyedLocal[0] || {}).unavailable_reason || null;
    receipt.local_greyed_ticket_refused_by = (greyedTicket.ticket || {}).refused_by || null;
    receipt.local_greyed_leg = "exercised (runtime absent from a scrubbed PATH; the daemon stays "
      + "reachable so the models are still enumerated)";
    receipt.local_greyed_when_no_pane_can_be_authorized = greyed.ok === true && greyedLocal.length > 0
      && greyedLocal.every((o) => o.available === false && typeof o.unavailable_reason === "string"
        && /no local pane can be authorized/.test(o.unavailable_reason))
      && greyedTicket.ok === true && greyedTicket.ticket.authorized === false
      && receipt.local_greyed_ticket_refused_by === "host_enumeration";
    if (!receipt.local_greyed_when_no_pane_can_be_authorized) {
      throw new Error("with no launchable local runtime the picker still offered local options "
        + `as available (${greyedLocal.length} local, reason=${receipt.local_greyed_reason}, `
        + `ticket refused_by=${receipt.local_greyed_ticket_refused_by})`);
    }

    const condRes = await sourceWorkerLaunchTicket({
      cwd: REPO_ROOT, holderPid: process.pid, sessionId: `${FRONTIER_SESSION}.conductor`,
      paneId: "selfcheck-pane-conductor",
      selection: { option: frontierOpt, role: "conductor", mode: "attended" }, timeoutMs: TIMEOUT_MS,
    });
    receipt.conductor_refusal_reason = (condRes.ticket || {}).reason || condRes.error || null;
    receipt.conductor_refused_by = (condRes.ticket || {}).refused_by || null;
    // Same rule as the other two legs: name the gate. Without it "some gate said no" satisfied this
    // leg, so an unrelated refusal (an absent CLI, a full I-X3 count) read as proof that the worker
    // path refuses the conductor role (validator MINOR-2). `worker_role` is `worker_identity`'s own
    // gate — the conductor role is born by the dedicated conductor-first path, never here.
    receipt.conductor_role_refused = condRes.ok === true && condRes.ticket.authorized === false
      && condRes.ticket.refused === true && condRes.ticket.lease === null
      && receipt.conductor_refused_by === "worker_role"
      // paired with the gate's OWN reason, as the forged leg already is: `worker_role` covers three
      // checks (empty pane id, charset, unknown role), so the id alone proves the family, not the
      // rule this leg names (spec-audit MINOR-2).
      && /unknown worker role/.test(receipt.conductor_refusal_reason || "");
    if (!receipt.conductor_role_refused) {
      throw new Error(`the CONDUCTOR role was not refused by the worker-role gate `
        + `(refused_by=${receipt.conductor_refused_by}): ${receipt.conductor_refusal_reason}`);
    }

    log(`[selfcheck] worker tickets: local=${JSON.stringify(receipt.local_argv)} · `
      + `frontier=${JSON.stringify(receipt.frontier_argv)} · lease=${receipt.frontier_lease_id} `
      + `held by pid ${process.pid}`);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  } finally {
    // 5. D-LOOP-1 — hand back every terminal this check may have taken, whatever happened above.
    try {
      const released = [];
      for (const s of [LOCAL_SESSION, FRONTIER_SESSION, `${FRONTIER_SESSION}.forged`,
        `${FRONTIER_SESSION}.conductor`, `${LOCAL_SESSION}.squeezed`, `${LOCAL_SESSION}.greyed`]) {
        released.push(await releaseWorkerTerminal(s, { cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS }));
      }
      receipt.terminals_released = released.every((r) => r.ok === true);
      const after = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
      const subs = (after.ok && after.status && after.status.subscriptions) || {};
      const e2 = subs[frontierSubRef || ""];
      receipt.in_use_after_release = e2 ? e2.in_use : 0;
    } catch (e) {
      receipt.error = receipt.error || `release failed: ${String((e && e.message) || e)}`;
    }
    // leave the host exactly as found: restore the env and remove the scratch ledger
    if (priorLedger === undefined) delete process.env.SOW_TERMINAL_LEASE_LEDGER;
    else process.env.SOW_TERMINAL_LEASE_LEDGER = priorLedger;
    if (priorBudget === undefined) delete process.env.SOW_VRAM_BUDGET_MB;
    else process.env.SOW_VRAM_BUDGET_MB = priorBudget;
    try { fs.rmSync(SCRATCH_LEDGER, { force: true }); } catch { /* nothing to remove */ }
  }

  receipt.ok = receipt.error === null
    && receipt.picker_sourced && receipt.host_residency_probed
    && receipt.local_greyed_when_no_pane_can_be_authorized
    && receipt.local_authorized && receipt.local_interactive
    && receipt.local_subscription_governed === false && receipt.local_residency !== null
    && receipt.local_residency_budget !== null
    && receipt.frontier_authorized && receipt.frontier_no_headless_flags
    && receipt.frontier_env_values_absent && receipt.frontier_containment_disclosed
    && receipt.frontier_emitter_governor_released && receipt.frontier_lease_durable
    && receipt.frontier_lease_held_by_this_process && receipt.frontier_lease_visible_cross_process
    && receipt.forged_option_refused && receipt.local_budget_refused
    && receipt.conductor_role_refused
    && receipt.terminals_released && receipt.in_use_after_release === 0;

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  receipt.scope_note = "every VRAM budget here is COMPUTED from this host's own residency snapshot "
    + "(read once under an unfalsifiable probe budget) so each leg exercises the branch its name "
    + "claims on a busy host and an idle one alike. What that survives is stated narrowly, because "
    + "the earlier wording ('if the resident set changes mid-run every leg throws and the receipt is "
    + "RED') was not true of every leg — the authorized leg's generous budget can stay green if the "
    + "resident set SHRINKS (spec-audit MINOR-4, 2026-07-26). What is actually established is "
    + "narrower and sufficient: no leg can go green on a gate other than its own, because each "
    + "asserts its gate id and the fit leg asserts the gate's own arithmetic: "
    + "the authorized leg clears what is resident and is deliberately generous (used + the largest "
    + "known footprint + headroom), so it tests admission MECHANICS, not this host's real capacity; "
    + "the refusal leg stands above what is resident and falls short of the target, so the FIT gate "
    + "is what says no; the greying leg scrubs PATH for its own children so the runtime is unlaunchable "
    + "while the daemon stays reachable. The real GPU budget is not what this check tests. It "
    + "obtains + releases governed worker AUTHORIZATIONS for options the host "
    + "picker really offered, against a SCRATCH ledger; makes NO live model call and spawns NO "
    + "session. The ConPTY launch of these argvs — and the pane chrome that follows it — is 17B "
    + "`.spawn`; live worker CANDIDATE→gate→synthesis legs (U58) are 17B `.legs`. Over-allowance "
    + "refusal, gate honesty, dead-holder reaping and the shape contract are covered by the Python "
    + "and Node suites (tests/unit/test_emit_worker_launch.py, test_worker_pane_spawn.py, "
    + "apps/desktop/test/worker-launch-source.test.js), not here.";
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] worker-launch ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runWorkerLaunchSelfCheck: run, RECEIPT_PATH };
