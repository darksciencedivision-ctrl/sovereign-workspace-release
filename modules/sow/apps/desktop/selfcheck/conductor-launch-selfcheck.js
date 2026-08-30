"use strict";
/**
 * Phase 17A `.lease` in-Electron self-check (D-P16-0 binding, per-track).
 *
 * Runs INSIDE the packaged Electron runtime and proves the piece 17A needs before pane 1 can ever
 * hold a live session: the shell can obtain a **governed launch ticket** — an authorization produced
 * by the Python gate chain, not by the shell — and the **durable I-X3 lease that ticket carries is
 * genuinely held by THIS Electron process and visible to a separate process**, then handed back.
 *
 * Why this must run in-runtime and not only headless (the binding lesson): the ticket is sourced by
 * spawning `py -3.12` from the Electron main process with `cwd` = repo root. Interpreter resolution,
 * cwd, argv quoting and the 25 s bound are exactly the class of thing that passes in a Node test and
 * fails at first launch. Headless tests cover the parse/fold; this covers the runtime.
 *
 * Flow:
 *   1. source a launch ticket with holderPid = THIS process's pid — the long-lived owner of the
 *      session the ticket authorizes (a lease owned by the emitter would count a terminal nobody
 *      holds);
 *   2. assert the governed facts: every gate true, argv INTERACTIVE (no `-p`/`--print`/
 *      `--output-format`), the credential-scrub NAME list present (§2.2 — names, never values), the
 *      CONDUCTOR chrome governed, and the emitter's own in-process governor released;
 *   3. assert the lease is DURABLE and HELD: holder_pid == our pid, in_use >= 1, and a SEPARATE
 *      process (the `--emit-lease-status` run) can see it — the cross-process count that makes I-X3
 *      real for a session that outlives its emitter;
 *   4. release it and assert the count returns to 0 — D-LOOP-1: this check leaves no live terminal
 *      behind. The release runs in a `finally`, so a failed assertion still hands the terminal back.
 *
 * A host that is not live-authorized (or has no `claude` CLI) yields a governed REFUSAL. That is an
 * honest outcome, and the receipt records it as `refused` with the reason — but it is NOT a pass:
 * this self-check exists to prove the authorized path works on the operator's host, so a refusal
 * fails loudly rather than quietly recording a stub.
 *
 * This check makes NO live model call: it obtains and releases an authorization. The ConPTY launch
 * of that argv is `.pty`; the type→answer round trip is `.roundtrip`.
 */
const fs = require("fs");
const { receiptPath } = require("./receipt-path");
const path = require("path");

const {
  sourceConductorLaunchTicket, releaseConductorLease, fetchLeaseStatus, scrubbedLaunchEnv,
  BANNED_FLAGS, LAUNCH_TICKET_SCHEMA,
} = require("../conductor/launch-source");

const RECEIPT_PATH = receiptPath("PHASE17A_LAUNCH_TICKET_SELFCHECK.json");
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

// SCRATCH ledger (`SOW_TERMINAL_LEASE_LEDGER`), never the operator's real one. A lease is keyed to
// `(subscription_ref, node_id)` and this check uses the production conductor identity on purpose —
// so against the real ledger it would ADOPT and then RELEASE a lease the operator's own running
// conductor may hold, uncounting a live session, and its "count is 0 again" assertion would be
// false on any host that is legitimately busy. The mechanism under test is identical; only the file
// is ours. Per-pid so two runs never collide.
const SCRATCH_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", `selfcheck-17a-${process.pid}.json`);

// Phase 17A `.pty`: a terminal is counted per SESSION (U75), so a ticket request must name the
// session it authorizes. This check obtains and releases an authorization without ever spawning it,
// so the key is its own — it can never collide with, or reclaim, the operator's live pane-1 session.
const SELFCHECK_SESSION_ID = `selfcheck-17a-lease#${process.pid}`;

async function run(ctx) {
  const { log } = ctx;
  const receipt = {
    check: "phase-17a.lease",
    started: new Date().toISOString(),
    ok: false,
    // the governed authorization
    ticket_sourced: false,
    ticket_schema: null,
    ticket_error: null,
    authorized: false,
    refused: false,
    reason: null,
    node_state: null,
    gates: null,
    // the launch spec the shell will execute in pane 1's ConPTY at `.pty`
    argv: null,
    interactive: false,
    no_headless_flags: false,
    env_scrub_name_count: null,
    env_scrub_drops_named_vars: false,
    env_values_absent_from_ticket: false,
    chrome_governed: false,
    // the governed identity the session must run under, and the ticket's own statement of what it
    // does NOT establish (an authorization is not containment — that is `.pty`'s work)
    identity: null,
    containment_disclosed: false,
    // isolation: this check never touches the operator's real ledger
    ledger_scope: "scratch",
    ledger_path: SCRATCH_LEDGER,
    // the durable I-X3 lease
    lease_id: null,
    lease_subscription_ref: null,
    lease_session_id: null,
    lease_durable: false,
    lease_holder_pid: null,
    electron_main_pid: process.pid,
    lease_held_by_this_process: false,
    lease_in_use: null,
    lease_allowance: null,
    lease_visible_cross_process: false,
    emitter_governor_released: false,
    // D-LOOP-1
    lease_released: false,
    in_use_after_release: null,
    error: null,
  };
  let leaseId = null;
  const priorLedger = process.env.SOW_TERMINAL_LEASE_LEDGER;
  process.env.SOW_TERMINAL_LEASE_LEDGER = SCRATCH_LEDGER; // inherited by every `py` child below
  try {
    // 1. source the governed ticket, owned by THIS long-lived process.
    const res = await sourceConductorLaunchTicket({
      cwd: REPO_ROOT, holderPid: process.pid, sessionId: SELFCHECK_SESSION_ID, timeoutMs: 60000,
    });
    receipt.ticket_sourced = res.ok === true;
    receipt.ticket_error = res.error || null;
    const t = res.ticket || {};
    receipt.ticket_schema = t.schema || null;
    receipt.authorized = t.authorized === true;
    receipt.refused = t.refused === true;
    receipt.reason = t.reason || null;
    receipt.node_state = t.node_state || null;
    receipt.gates = t.gates || null;
    if (!receipt.ticket_sourced) throw new Error(`launch ticket was not sourced from Python: ${receipt.ticket_error || "unknown"}`);
    if (receipt.ticket_schema !== LAUNCH_TICKET_SCHEMA) throw new Error(`ticket carries an unexpected schema: ${receipt.ticket_schema}`);
    if (!receipt.authorized) throw new Error(`governed launch REFUSED on this host: ${receipt.reason || "unknown"}`);
    leaseId = t.lease && t.lease.lease_id;

    // 2. the governed facts — interactive, scrub-by-name, chrome governed, no in-process leak.
    const launch = t.launch || {};
    receipt.argv = Array.isArray(launch.argv) ? launch.argv.slice() : null;
    receipt.interactive = launch.interactive === true && launch.one_shot === false;
    receipt.no_headless_flags = Array.isArray(receipt.argv) && !BANNED_FLAGS.some((f) => receipt.argv.includes(f));
    const names = Array.isArray(launch.env_scrub_names) ? launch.env_scrub_names : null;
    receipt.env_scrub_name_count = names ? names.length : null;
    // the scrub is a PURE fold over a probe env: every named var is dropped, nothing else is
    const probe = { PATH: "p", KEEP_ME: "k" };
    for (const n of names || []) probe[n] = "value-that-must-not-survive";
    const scrubbed = scrubbedLaunchEnv(t, probe);
    receipt.env_scrub_drops_named_vars = (names || []).every((n) => !(n in scrubbed))
      && scrubbed.KEEP_ME === "k" && scrubbed.PATH === "p";
    // §2.2: the ticket transmits NAMES only — no name=value pair and no env map ever crosses.
    receipt.env_values_absent_from_ticket = !("env" in launch)
      && !(names || []).some((n) => JSON.stringify(t).includes(`${n}=`));
    receipt.chrome_governed = !!t.chrome && t.chrome.governed === true && t.chrome.interactive === true
      && t.chrome.role === "conductor";
    // The governed identity the shell must spawn UNDER (it cannot invent one — invariant 2/29) and
    // the ticket's own honesty about its limits: `chrome.governed` records AUTHORIZATION provenance,
    // not an enforced sandbox, so the ticket must say `supervisor_bound:false` until `.pty` binds it.
    receipt.identity = t.identity || null;
    receipt.containment_disclosed = !!t.containment && t.containment.authorized === true
      && t.containment.supervisor_bound === false && typeof t.containment.owed_to === "string";
    receipt.emitter_governor_released = t.governor_released === true;
    if (!receipt.interactive) throw new Error("ticket is not an interactive launch (one_shot must be false — the operator drives it, OP-8 §13.1)");
    if (!receipt.no_headless_flags) throw new Error(`ticket argv carries a headless flag: ${JSON.stringify(receipt.argv)}`);
    if (!names) throw new Error("ticket carries no env_scrub_names list (§2.2 — the shell cannot scrub by name)");
    if (!receipt.env_scrub_drops_named_vars) throw new Error("scrubbedLaunchEnv did not drop exactly the named vars");
    if (!receipt.env_values_absent_from_ticket) throw new Error("the ticket appears to carry env VALUES — §2.2 violation");
    if (!receipt.chrome_governed) throw new Error("ticket chrome is not the governed interactive CONDUCTOR chrome");
    if (!receipt.identity || !receipt.identity.node_id || !receipt.identity.permission_profile_id) {
      throw new Error("ticket carries no governed identity (node_id + permission profile) to spawn under");
    }
    if (!receipt.containment_disclosed) throw new Error("ticket does not disclose that it is an authorization, NOT containment (owed to .pty)");
    if (!receipt.emitter_governor_released) throw new Error("the emitter's in-process I-X3 count was not released");

    // 3. the durable lease — held by THIS process and visible to a separate one.
    const lease = t.lease || {};
    receipt.lease_id = lease.lease_id || null;
    receipt.lease_subscription_ref = lease.subscription_ref || null;
    receipt.lease_session_id = lease.session_id || null;
    receipt.lease_durable = lease.durable === true;
    receipt.lease_holder_pid = Number.isFinite(lease.holder_pid) ? lease.holder_pid : null;
    receipt.lease_held_by_this_process = receipt.lease_holder_pid === process.pid;
    receipt.lease_in_use = Number.isFinite(lease.in_use) ? lease.in_use : null;
    receipt.lease_allowance = Number.isFinite(lease.allowance) ? lease.allowance : null;
    if (!receipt.lease_id || !receipt.lease_durable) throw new Error("ticket carries no durable lease — an uncounted live terminal defeats I-X3");
    if (!receipt.lease_held_by_this_process) throw new Error(`lease holder_pid ${receipt.lease_holder_pid} is not this Electron process (${process.pid})`);
    if (receipt.lease_session_id !== SELFCHECK_SESSION_ID) {
      throw new Error(`the terminal is counted under ${receipt.lease_session_id}, not the session asked for (U75)`);
    }

    const st = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
    const subs = (st.ok && st.status && st.status.subscriptions) || {};
    const entry = subs[lease.subscription_ref] || null;
    receipt.lease_visible_cross_process = !!entry && entry.in_use >= 1
      && (entry.holders || []).some((h) => h.lease_id === receipt.lease_id && h.holder_pid === process.pid);
    if (!receipt.lease_visible_cross_process) {
      throw new Error("a separate process could not see this lease — the durable I-X3 count is not real");
    }

    log(`[selfcheck] governed launch ticket: argv=${JSON.stringify(receipt.argv)} · lease=${receipt.lease_id} held by pid ${process.pid} · ${receipt.lease_in_use}/${receipt.lease_allowance}`);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  } finally {
    // 4. D-LOOP-1 — hand the terminal back whatever happened above.
    if (leaseId) {
      try {
        const rel = await releaseConductorLease(leaseId, { cwd: REPO_ROOT, timeoutMs: 60000 });
        receipt.lease_released = rel.ok === true && rel.released === true;
        const after = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: 60000 });
        const subs = (after.ok && after.status && after.status.subscriptions) || {};
        const e2 = subs[receipt.lease_subscription_ref || ""];
        receipt.in_use_after_release = e2 ? e2.in_use : 0;
      } catch (e) {
        receipt.error = receipt.error || `release failed: ${String((e && e.message) || e)}`;
      }
    }
    // leave the host exactly as found: restore the env and remove the scratch ledger
    if (priorLedger === undefined) delete process.env.SOW_TERMINAL_LEASE_LEDGER;
    else process.env.SOW_TERMINAL_LEASE_LEDGER = priorLedger;
    try { fs.rmSync(SCRATCH_LEDGER, { force: true }); } catch { /* nothing to remove */ }
  }

  receipt.ok = receipt.error === null
    && receipt.ticket_sourced && receipt.authorized && receipt.interactive
    && receipt.no_headless_flags && receipt.env_scrub_drops_named_vars
    && receipt.env_values_absent_from_ticket && receipt.chrome_governed
    && receipt.emitter_governor_released && receipt.lease_durable
    && receipt.containment_disclosed
    && receipt.lease_held_by_this_process && receipt.lease_visible_cross_process
    && receipt.lease_released && receipt.in_use_after_release === 0;

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  receipt.scope_note = "obtains + releases a governed authorization against a SCRATCH ledger; makes "
    + "NO live model call and never touches the operator's real lease file. The ConPTY launch of "
    + "this argv is 17A `.pty`; type→answer is 17A `.roundtrip`. Over-allowance refusal, gate "
    + "honesty, dead-holder reaping and the lock rule are covered by the Python suite "
    + "(tests/unit/test_terminal_lease.py, test_emit_conductor_launch.py), not here. `interactive` "
    + "and `chrome_governed` are SHAPE assertions over constants at the source — they guard against "
    + "producer drift, not behavior.";
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] conductor-launch ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runConductorLaunchSelfCheck: run, RECEIPT_PATH };
