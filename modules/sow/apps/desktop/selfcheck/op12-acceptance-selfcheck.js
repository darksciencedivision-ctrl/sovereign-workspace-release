"use strict";
/**
 * Phase 18C `.close` in-Electron self-check (D-P16-0 binding, per-track) — the OP-12 **acceptance**
 * receipt, in the world this host is actually in.
 *
 * WHAT 18C ASKS FOR, AND WHY THIS IS NOT IT. Directive §17 defines acceptance as ONE harmless live
 * probe per provider plus ONE in-Electron receipt per provider (picker → supervised pane → exact
 * provider+model verified → harmless prompt → live response → teardown → lease 0 → no credential
 * material in any log → tree clean). Its entry condition is the OPERATOR's: each CLI's own login,
 * **and their own edit to the never-committed `config/live_operation.json`**. On this host that file
 * cites `OP-6`, so `grok_build` and `google_antigravity` are DENIED. §17 is explicit that an unmet
 * entry condition is **skip-with-record, not failure** — so this receipt evidences the fail-closed
 * world, and `op12-acceptance-verdict.worldIsFailClosed` REFUSES to let it stand in for the live
 * legs the moment the operator opens the switch.
 *
 * What it establishes, each leg naming the fact it measures:
 *
 *   1. **the host is ready and the switch is the only thing missing** — both providers enumerate
 *      from their own CLIs (`grok models` / `agy models`), and the governed ticket for the host's own
 *      option is refused with `gates.selection_offered:true`, `gates.cli_present:true` and
 *      `refused_by:"live_operation"`. Every gate before the switch PASSED. That is the whole 18C
 *      story on this host, and it is read from gate IDs, never prose;
 *   2. **the operator's click is refused too**, one layer earlier, by the shell's front-line guard,
 *      with the provider's own reason (§14 — never the other's text);
 *   3. **nothing was born and nothing was leased**: the live-session count is unmoved across every
 *      attempt, the refusal ticket carries no lease and no launch block, the in-process governor
 *      slot came back, and the DURABLE ledger reads 0 on both OP-12 subscriptions — measured against
 *      a byte comparison of the operator's real ledger file taken before the run;
 *   4. **§17's lease-to-zero line is VISIBLE** (invariant 27): the status bar's own rows AND its
 *      painted text show `grok 0/1` and `agy 0/1`;
 *   5. **§17's "no credential material in any log"**, measured: sentinel placeholder VALUES are
 *      planted in this process's environment under the OP-12 credential NAMES, and must appear in
 *      neither the shell's main-process log nor this receipt. §2.2 stands — no real credential is
 *      ever read, and a sentinel hit is reported by SINK, never by value;
 *   6. **the OWED block names every acceptance leg this run did not perform**, each with a
 *      reference (the live probe, the live pane receipt, U227's node record, `agy`'s offline-
 *      unverifiable auth, and the operator's switch itself).
 *
 * WHAT IT DOES NOT ESTABLISH, stated so the receipt cannot be read as more: no live Grok or
 * Antigravity call is made, no pane is opened for either provider, no terminal is leased, and no
 * Sovereign node RECORD exists for either — since OP-12.1 (2026-08-01) that is because nothing is
 * WIRED to create one, not because the vocabulary refuses it (`node@1.1` admits both ids). Those
 * are the live legs, and they are named as OWED rather than approximated.
 *
 * DISCLOSED COST (D-P18-7/U271, amended at 18B `.close` and again here): verifying a selection
 * against the host's own enumeration runs that provider's `--version` + `models` commands, which
 * leave this host. COUNTED rather than characterised: this check performs THREE enumerations per
 * provider — the picker read (which probes both) plus the launcher ask and the ticket read for that
 * provider's own selection. The first draft of this note said "exactly the two OP-12 selections it
 * verifies", which was wrong twice over: five enumerations, and each OP-12 selection probed BOTH
 * CLIs, so verifying an Antigravity selection emitted a grok.com metadata call under the operator's
 * SuperGrok session. `_host_offered_options` now scopes an OP-12 selection to its OWN provider
 * (U290) — the cross-provider half of the egress U276 closed for a local selection.
 */
const fs = require("fs");
const path = require("path");

const { receiptPath } = require("./receipt-path");
const { sourceIdentity } = require("./voice-conductor-selfcheck");
const { fetchPickerModel } = require("../picker/source");
const { sourceWorkerLaunchTicket, releaseWorkerTerminal } = require("../picker/launch-source");
const { fetchLeaseStatus } = require("../conductor/launch-source");
const {
  OP12_PROVIDERS, OP12_SUBSCRIPTION_REFS, OP12_CREDENTIAL_NAMES, REQUIRED_OWED_KEYS,
  worldIsFailClosed, authorityRefusalIsFailClosed, uxGuardRefused, leasesAreZero,
  statusBarPaintsZeroOfOne, noCredentialMaterial, owedLegsAreNamed,
} = require("./op12-acceptance-verdict");

const RECEIPT_SCHEMA = "phase18c_acceptance_selfcheck@1.0";
const RECEIPT_PATH = receiptPath("PHASE18C_ACCEPTANCE_SELFCHECK.json");
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
/** The OPERATOR's real durable-terminal ledger — read only, to prove this check never touched it. */
const REAL_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", "terminal_leases.json");
const TIMEOUT_MS = 120000;

const DISPLAY = { grok_build: "Grok Build", google_antigravity: "Gemini · Antigravity" };

/** Every acceptance leg the fail-closed world cannot perform, named with a reference (§17). */
const OWED = Object.freeze({
  live_provider_probe:
    "§17's ONE harmless live probe per provider (GROK_PROVIDER_OK / GEMINI_PROVIDER_OK) has NEVER "
    + "executed: the supervised path exists (U234, 18C .probe-path) and the operator's live switch "
    + "cites OP-6, so the probe is refused before any CLI runs",
  live_in_electron_receipt:
    "§17's per-provider LIVE in-Electron receipt (picker → supervised pane → verified provider+model "
    + "→ harmless prompt → live response → teardown) is OWED — no pane has ever been opened for "
    + "either provider (directive §17 entry condition unmet ⇒ skip-with-record)",
  provider_node_record:
    "no Sovereign node RECORD exists for either provider. Through 18C the reason was that none "
    + "COULD: node@1.0's `adapter` enum is frozen and has no member for them, and NodeRegistry."
    + "register refused both with an append-only registration_refused event — which is why this "
    + "gate did NOT close on U227 being answered. The operator ruled U227 on 2026-08-01 (OP-12.1, "
    + "directive §17.1) by SUCCESSOR SCHEMA: schemas/node.schema@1.1.json admits both ids while "
    + "the frozen @1.0 stays untouched, so the registry now accepts them. The leg stays OWED "
    + "because nothing has been WIRED to create the records yet — phase 18D `.close`",
  antigravity_auth_state:
    "recorded at 18A: `agy` 1.1.9 exposes no offline auth surface, so whether the operator is signed "
    + "in is UNVERIFIABLE here and only a live call can answer it (U233)",
  grok_auth_state:
    "the other half of §17's per-CLI login entry condition, stated so a reader can tell WHICH half "
    + "is unmet: `grok models` answered with the CLI's own listing on this host, which is as far as "
    + "an offline surface can go — a signed-out CLI reports it there. That is evidence of a usable "
    + "session, NOT of a live reply, which stays owed with the probe (18A recon; U233's sibling)",
  probe_acceptance_holes:
    "U238, CLOSED at 18E `.hardening` — recorded here because this OWED key shipped at 18C naming "
    + "the holes as live: whitespace-deleting and punctuation-rewriting echoes accepted by "
    + "`_token_answered` (six shapes measured), and acceptance reading the best-effort "
    + "`extract_probe_text`, whose whole-document fallback let a token in any field certify a "
    + "provider that said nothing. Both were closed BEFORE any live acceptance leg ran (directive "
    + "§17.2(2)): the echo subtraction now runs on an alphanumeric-only fold, and acceptance reads "
    + "`extract_probe_response_field` — a recognised response field, or the whole document when that "
    + "document IS a bare JSON string (the one case with no field to look in, because the string is "
    + "the payload), or nothing. Two limits are NOT covered by the word CLOSED and are recorded, not "
    + "absorbed: a PARAPHRASED echo still passes, because the subtraction removes a contiguous "
    + "prompt (U304); and neither provider's real `-p --output-format json` document has been read "
    + "against the strict reader, so a nested answer would now be REFUSED — the safe direction, but "
    + "unverified (U305). What stays OWED is the live leg itself, plus those two limits",
  operator_live_switch:
    "the entry condition itself: extending config/live_operation.json to name both providers is the "
    + "operator's own edit to a never-committed file (directive §17; the code-pinned scope half "
    + "shipped at 18B .scope per U237)",
});

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

function readText(file) {
  try { return fs.readFileSync(file, "utf8"); } catch { return null; }
}

async function run(ctx) {
  const { win, isSupervised, spawnFromSelection, workerLauncher, sessionManager, mainLogFile,
    log } = ctx;
  const receipt = {
    schema: RECEIPT_SCHEMA,
    check: "phase-18c.close",
    authorization: "OP-12 (operator, 2026-07-31); acceptance criteria AUTONOMOUS_BUILD_DIRECTIVE.md §17",
    source: sourceIdentity(),
    started: new Date().toISOString(),
    ok: false,
    // the world, first — everything below is only meaningful inside it
    world: null,
    entry_conditions_met: false,
    live_legs_performed: false,
    supervision_ready: false,
    picker_sourced: false,
    // per provider
    options_offered: {},        // provider → {count, slugs, available_count, group_reason}
    ux_guard: {},               // provider → {ok, reasons, result}
    authority: {},              // provider → {ok, reasons, refused_by, gates, reason}
    launcher_record: {},        // provider → the shell launcher's OWN record of the refused attempt
    // the negatives that make the refusals mean something
    sessions_before: null,
    sessions_after: null,
    lease_status: null,         // provider ref → in_use, from the DURABLE ledger
    lease_zero: null,
    real_ledger_unchanged: false,
    statusbar_rows: null,
    statusbar_painted_text: null,
    statusbar_zero_of_one: null,
    credential_scan: null,
    credential_scan_log_file: null,
    ticket_key_release: [],     // D-LOOP-1 for the one emitter session key this check chose itself
    credential_sentinel_names: OP12_CREDENTIAL_NAMES.slice(),
    owed: OWED,
    owed_named: null,
    error: null,
  };

  // §2.2: PLACEHOLDER values, planted under credential-bearing NAMES. Nothing real is ever read.
  // Named with this process's pid so a hit cannot be some other run's string.
  const sentinels = OP12_CREDENTIAL_NAMES.map((n) => `sow-18c-sentinel-${n}-${process.pid}`);
  const priorEnv = new Map();
  OP12_CREDENTIAL_NAMES.forEach((name, i) => {
    priorEnv.set(name, process.env[name]);
    process.env[name] = sentinels[i];
  });
  const realLedgerBefore = readText(REAL_LEDGER);
  const ticketSessionKeys = [];   // reclaim keys for every direct emitter ask, released in `finally`

  try {
    receipt.supervision_ready = await waitFor(isSupervised, 30000, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY within 30s — nothing is asked for, let alone "
        + "born, without a verified channel (invariant 2)");
    }

    // ---- the world -------------------------------------------------------------------------
    // Read from the REAL host enumeration, which is where the shell itself reads the operator's
    // switch. `authorization.providers` is the code-pinned scope intersected with the operator's
    // file; naming an OP-12 provider there is what would make the live legs runnable.
    const pickerRes = await fetchPickerModel({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    receipt.picker_sourced = pickerRes.ok === true;
    if (!receipt.picker_sourced) {
      throw new Error(`the host picker enumeration failed: ${pickerRes.error} — an acceptance `
        + "receipt is never written against an unverifiable offer");
    }
    const picker = pickerRes.picker || {};
    receipt.world = worldIsFailClosed(picker.authorization);
    if (!receipt.world.fail_closed) {
      // NOT an error in the host's sense — it is a REFUSAL to write a fail-closed receipt for a
      // world that is no longer fail-closed. The live legs are runnable and owed; running them is a
      // live spend, which this check deliberately does not make on its own initiative.
      throw new Error(`${receipt.world.reason} — this receipt evidences the fail-closed world only; `
        + "re-run 18C with the LIVE acceptance legs (directive §17)");
    }

    const options = Array.isArray(picker.options) ? picker.options : [];
    const groups = Array.isArray(picker.providers) ? picker.providers : [];
    const mgr = sessionManager();
    receipt.sessions_before = mgr ? mgr.registry.alive().length : null;

    for (const provider of OP12_PROVIDERS) {
      const mine = options.filter((o) => o && o.provider === provider);
      const group = groups.find((g) => g && g.provider === provider) || {};
      receipt.options_offered[provider] = {
        count: mine.length,
        slugs: mine.map((o) => o.model_slug),
        available_count: mine.filter((o) => o.available).length,
        group_reason: (group.status && group.status.reason) || null,
      };
      if (!mine.length) {
        throw new Error(`${DISPLAY[provider]} enumerated no model on this host — 18B established `
          + "that both CLIs publish their own listings; without one there is nothing to refuse");
      }
      if (receipt.options_offered[provider].available_count !== 0) {
        throw new Error(`${DISPLAY[provider]} offers ${receipt.options_offered[provider].available_count} `
          + "AVAILABLE option(s) in a world whose switch denies it — the grey is not honest");
      }

      // ---- leg 2: the operator's own CLICK, through the production path -----------------------
      const option = mine[0];
      const clicked = await spawnFromSelection({
        option, role: "reasoning", mode: "autonomous", targetPaneId: null,
      });
      const ux = uxGuardRefused(clicked, provider);
      receipt.ux_guard[provider] = {
        ok: ux.ok, reasons: ux.reasons, recorded: clicked && clicked.recorded,
        launched: clicked && clicked.launched, error: (clicked && clicked.error) || null,
      };
      if (!ux.ok) {
        throw new Error(`${provider}: the operator's click was not refused honestly — ${ux.reasons.join("; ")}`);
      }

      // ---- leg 1: past the front-line guard, into the AUTHORITY -------------------------------
      // The click above never reaches Python (the shared guard refuses a greyed option first), which
      // is correct for the UI and useless as evidence about the switch. So the HOST's own option —
      // greyed exactly as enumerated, not a forgery — is put through the launcher, which asks the
      // Python emitter. `_assert_option_offered` matches it (available:false is one of the identity
      // fields), every gate before the live one passes, and the live one refuses. No pane is created
      // on this path: a governed refusal starts nothing, so there is nothing to tear down.
      const paneId = `pane-18c-acceptance-${provider}-${process.pid}`;
      const launch = await workerLauncher().launchWorkerPane({
        paneId, selection: { option, role: "reasoning", mode: "autonomous" },
      });
      // …and the ticket itself, for the gate MAP the launcher does not surface. Same production
      // read-source, same emitter; one extra enumeration scoped to THIS provider (D-P18-7/U290).
      // Its session key is reclaimed in `finally`, unconditionally: in this world the emitter
      // refuses before `ix3_counted`, so nothing is ever held — but if the operator opened the
      // switch between the picker read above and this call, a durable terminal would be counted
      // against a session that will never exist and nothing else would hand it back (spec-audit
      // MINOR-11). `releaseWorkerTerminal` reclaims nothing when nothing is held.
      const ticketSessionId = `${paneId}#ticket`;
      ticketSessionKeys.push(ticketSessionId);
      const ticketRes = await sourceWorkerLaunchTicket({
        cwd: REPO_ROOT, holderPid: process.pid, sessionId: ticketSessionId, paneId,
        selection: { option, role: "reasoning", mode: "autonomous" },
        shellEnv: process.env, timeoutMs: TIMEOUT_MS,
      });
      const ticket = (ticketRes && ticketRes.ticket) || null;
      const sessionsNow = mgr ? mgr.registry.alive().length : null;
      const verdict = authorityRefusalIsFailClosed({
        provider, ticket, launch,
        sessions_before: receipt.sessions_before, sessions_after: sessionsNow,
      });
      receipt.authority[provider] = {
        ok: verdict.ok, reasons: verdict.reasons,
        refused_by: (ticket && ticket.refused_by) || null,
        launch_refused_by: (launch && launch.refusedBy) || null,
        gates: (ticket && ticket.gates) || null,
        reason: (ticket && ticket.reason) || null,
        lease: (ticket && ticket.lease) || null,
        subscription_governed: ticket ? ticket.subscription_governed : null,
        sessions_after: sessionsNow,
      };
      // The launcher's OWN record for the attempt, read back rather than assumed: a refused launch
      // must leave a `refused` record holding no lease and governing no subscription. (The record
      // survives this check by design — there is no `forget` on the launcher's surface, and the pane
      // id is synthetic, so nothing renders it, no chrome is written for it and no layout snapshot
      // carries it. Stated rather than tidied away, because an inert leftover is still a leftover.)
      const rec = workerLauncher().record(paneId);
      receipt.launcher_record[provider] = {
        pane_id: paneId, state: rec.state, lease_id: rec.leaseId,
        subscription_governed: rec.subscriptionGoverned, refused_by: rec.refusedBy,
        supervised: rec.supervised, argv: rec.argv,
      };
      if (rec.state !== "refused" || rec.leaseId !== null || rec.argv !== null) {
        throw new Error(`${provider}: the launcher's own record for a refused attempt reads `
          + `state=${rec.state} lease=${JSON.stringify(rec.leaseId)} argv=${JSON.stringify(rec.argv)}`);
      }
      if (!verdict.ok) {
        throw new Error(`${provider}: the governed refusal is not fail-closed evidence — `
          + verdict.reasons.join("; "));
      }
    }
    receipt.sessions_after = mgr ? mgr.registry.alive().length : null;

    // ---- leg 3: the DURABLE ledger, and the operator's own file untouched --------------------
    const st = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    const zero = leasesAreZero(st.ok ? st.status : null);
    receipt.lease_status = zero.in_use;
    receipt.lease_zero = { ok: zero.ok, reasons: zero.reasons };
    if (!zero.ok) throw new Error(`the §17 lease line does not read zero: ${zero.reasons.join("; ")}`);
    receipt.real_ledger_unchanged = readText(REAL_LEDGER) === realLedgerBefore;
    if (!receipt.real_ledger_unchanged) {
      throw new Error("this check changed the operator's real durable lease ledger — a refusal path "
        + "must write nothing there");
    }

    // ---- leg 4: the same fact where the operator READS it ------------------------------------
    const bar = await evalR(win, "window.sovereign.statusBar()");
    receipt.statusbar_rows = (bar && Array.isArray(bar.rows))
      ? bar.rows.map((r) => ({ provider: r.provider, label: r.label, allowance: r.allowance }))
      : null;
    receipt.statusbar_painted_text = await evalR(win, `(function(){
      const el = document.getElementById("statusbar");
      return el ? el.textContent.replace(/\\s+/g, " ").trim() : null;
    })()`);
    const painted = statusBarPaintsZeroOfOne(receipt.statusbar_rows, receipt.statusbar_painted_text);
    receipt.statusbar_zero_of_one = { ok: painted.ok, reasons: painted.reasons, labels: painted.painted };
    if (!painted.ok) {
      throw new Error(`the §17 lease-to-zero line is not visible to the operator: ${painted.reasons.join("; ")}`);
    }

    // ---- leg 5: §17's credential line, measured ----------------------------------------------
    const logFile = mainLogFile || null;
    receipt.credential_scan_log_file = logFile;
    const scan = noCredentialMaterial({
      [logFile || "main-process.log (path unknown)"]: logFile ? readText(logFile) : null,
      "PHASE18C_ACCEPTANCE_SELFCHECK.json (this receipt, pre-write)": JSON.stringify(receipt),
    }, sentinels);
    receipt.credential_scan = {
      ok: scan.ok, reasons: scan.reasons, sinks_checked: scan.sinks_checked,
      sentinels_checked: scan.sentinels_checked,
    };
    if (!scan.ok) throw new Error(`§17 credential scan: ${scan.reasons.join("; ")}`);

    // ---- leg 6: what this run did NOT establish, named -----------------------------------------
    const owed = owedLegsAreNamed(receipt.owed);
    receipt.owed_named = { ok: owed.ok, reasons: owed.reasons, keys: REQUIRED_OWED_KEYS.slice() };
    if (!owed.ok) throw new Error(`the OWED block is incomplete: ${owed.reasons.join("; ")}`);

    log("[selfcheck] op12-acceptance: both providers enumerate from their own CLIs and are refused "
      + "at the live_operation gate with every earlier gate passed; 0 sessions, 0 leases, "
      + "0/1 painted for each");
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  } finally {
    // D-LOOP-1 on the one key this check chose itself. Unconditional: `releaseWorkerTerminal`
    // reclaims nothing when nothing is held, and the branch where something IS held is exactly the
    // one where the check has already failed and could not clean up by any other route.
    for (const sessionId of ticketSessionKeys) {
      try {
        const rel = await releaseWorkerTerminal(sessionId, { cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
        receipt.ticket_key_release.push({ session_id: sessionId, ok: rel.ok === true,
          released: rel.released === true, count: rel.count || 0 });
      } catch (e) {
        receipt.ticket_key_release.push({ session_id: sessionId, ok: false,
          error: String((e && e.message) || e) });
      }
    }
    for (const [name, value] of priorEnv) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }

  // DERIVED, not declared. Both used to be literal `false` assignments — fields named for a
  // measurement the code did not make (validator MINOR-7 / spec-audit NIT-16). `entry_conditions_met`
  // is the operator's two-part condition: the live switch naming both providers (measured: it does
  // not, or the run would have thrown) AND each CLI's own login, whose Antigravity half is
  // UNVERIFIABLE offline — so it can never read true from here, and now it says so by construction.
  // `live_legs_performed` is derived from the fact that nothing was started and nothing was leased.
  receipt.entry_conditions_met = Boolean(
    receipt.world && receipt.world.fail_closed === false
    && receipt.world.op12_authorized && receipt.world.op12_authorized.length === OP12_PROVIDERS.length);
  receipt.live_legs_performed = !(
    Number.isInteger(receipt.sessions_before) && receipt.sessions_after === receipt.sessions_before
    && receipt.lease_zero && receipt.lease_zero.ok === true);
  receipt.ok = receipt.error === null
    && receipt.entry_conditions_met === false && receipt.live_legs_performed === false
    && receipt.supervision_ready && receipt.picker_sourced
    && !!(receipt.world && receipt.world.fail_closed)
    && OP12_PROVIDERS.every((p) => receipt.ux_guard[p] && receipt.ux_guard[p].ok === true)
    && OP12_PROVIDERS.every((p) => receipt.authority[p] && receipt.authority[p].ok === true)
    && Number.isInteger(receipt.sessions_before)
    && receipt.sessions_after === receipt.sessions_before
    && !!(receipt.lease_zero && receipt.lease_zero.ok)
    && receipt.real_ledger_unchanged
    && !!(receipt.statusbar_zero_of_one && receipt.statusbar_zero_of_one.ok)
    && !!(receipt.credential_scan && receipt.credential_scan.ok)
    && !!(receipt.owed_named && receipt.owed_named.ok)
    && !!(receipt.source && receipt.source.commit)
    // §17 names "repo-status-unchanged" / tree clean as an acceptance element, and both sibling
    // receipts that publish this same `sourceIdentity()` block gate on the whole fact. This one
    // required only the commit hash, so it could have gone green while describing code that was
    // never committed (validator MEDIUM-4 / spec-audit MEDIUM-3).
    && receipt.source.tracked_product_tree_clean === true
    && (receipt.source.unexpected_untracked_product_files || []).length === 0;

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  receipt.scope_note = "this is the SKIP-WITH-RECORD receipt directive §17 prescribes for an unmet "
    + "entry condition, NOT the 18C live acceptance. No live MODEL call was made for either provider "
    + "— no prompt, no completion (the token-free metadata calls that DID leave this host are "
    + "disclosed and counted in scope_note_disclosed_cost) — no pane was opened, no terminal was "
    + "leased, and no Sovereign node record exists for either (nothing is wired to create one yet; "
    + "since OP-12.1 the vocabulary no longer forbids it — see OWED.provider_node_record). What it establishes is that "
    + "the operator's switch is the ONLY thing refusing: both providers enumerate from their own "
    + "CLIs, the host's own greyed option is verified against that enumeration "
    + "(gates.selection_offered:true), the CLI is present (gates.cli_present:true), and the refusal "
    + "comes from the live_operation gate by ID — with nothing spawned, no lease taken, the "
    + "in-process governor slot returned, the durable ledger at 0 on both OP-12 subscriptions and "
    + "the operator's ledger file byte-identical. The verdict module refuses to let this receipt be "
    + "RECORDED AS EVIDENCE if the operator has opened the switch: the run throws, and the receipt "
    + "is still written with ok:false and the reason, so it can never be reused as a substitute for "
    + "the live legs.";
  receipt.scope_note_disclosed_cost = "verifying a selection against the host's own enumeration runs "
    + "that provider's `--version` + `models` commands, which leave this host (D-P18-7 / U271). "
    + "COUNTED, not estimated: this check performs THREE enumerations per provider — the picker read "
    + "(which probes both) plus the launcher ask and the ticket read for that provider's own "
    + "selection — i.e. 3 `grok --version`/`grok models` pairs and 3 `agy` pairs. It was 5 each "
    + "before this unit narrowed `_host_offered_options` to the SELECTED OP-12 provider (U290): "
    + "verifying an Antigravity selection used to emit a grok.com metadata call under the operator's "
    + "SuperGrok session, which is the cross-provider half of the egress U276 closed for a local "
    + "selection. No prompt, no completion, no model call, no credential read.";
  receipt.scope_note_gate_map = "gates.operator_terms_confirmed reads true for both providers, and "
    + "as of 18E `.hardening` that value is SUPPLIED BY THE CALLER rather than defaulted inside the "
    + "gate chain — it is still a hard-coded true, moved one frame up to where its authority can be "
    + "cited and read, which is the whole of the improvement and no more than that. "
    + "`build_worker_launch_ticket` now requires `operator_terms_confirmed` "
    + "and `profile_loader` as keywords — U292(a)/U91's and U98's shapes, the same pair closed in "
    + "provider_probe_session.py at 18C `.probe-path` (U283) — and main(), the sole production "
    + "caller, supplies the terms flag citing OP-9/OP-12 and the profile via "
    + "profile_loader_from_host(), so invariant 20's air-gap refusal is reachable on the product "
    + "path (tests/unit/test_worker_emitter_gate_inputs.py drives main() under "
    + "SOVEREIGN_DEPLOYMENT_PROFILE=offline_airgapped and gets refused_by profile_roster). What the "
    + "gate still is NOT is a measurement of the operator's subscription terms — nothing machine-"
    + "readable can measure that (invariant 1); it is a citation of a recorded ruling, written at "
    + "the call site where a reader can check it. This receipt's verdict does not rest on that gate "
    + "either way: the legs it requires are selection_offered, cli_present, live_operation_authorized "
    + "and ix3_counted.";
  receipt.scope_note_credential_scan = "the sentinel scan covers the TWO sinks this run can read — "
    + "the shell's own durable main-process log and this receipt's payload. In this world nothing "
    + "was spawned, so there is no PTY transcript and no child environment to scan; that is a narrow "
    + "leg, and it is narrow because the world is. The payload is re-scanned immediately before it "
    + "is written, so fields added after the first scan (error, the scope notes, env, ok) are "
    + "covered too (spec-audit MINOR-14).";

  // The FINAL payload, re-scanned. The in-run scan covered the receipt as it stood at leg 5; error,
  // the scope notes, `env` and `ok` are all written after it, and a throw between the two put an
  // unscanned string into the published artifact (spec-audit MINOR-14). A hit here refuses the
  // write outright — publishing the leak is worse than publishing nothing.
  const payload = JSON.stringify(receipt, null, 2) + "\n";
  const finalScan = noCredentialMaterial({ "the receipt payload as written": payload }, sentinels);
  if (!finalScan.ok) {
    receipt.ok = false;
    log(`[selfcheck] op12-acceptance REFUSED TO WRITE: ${finalScan.reasons.join("; ")}`);
    return receipt;
  }
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, payload);
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] op12-acceptance ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runOp12AcceptanceSelfCheck: run, RECEIPT_PATH, OWED };
