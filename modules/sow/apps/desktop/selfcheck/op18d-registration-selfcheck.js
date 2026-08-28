"use strict";
/**
 * Phase 18D `.close` in-Electron self-check (D-P16-0 binding, per-track) — **the node-record
 * wiring OP-12.1 authorized, exercised inside the packaged shell on the operator's host under a
 * FIXTURE live-operation switch, in a world whose real switch still denies both providers.**
 * (The headline said "the two OP-12 providers are Sovereign nodes now", which the thirty lines
 * below corrected and a headline should not need correcting — spec-audit MINOR-4.)
 *
 * WHAT 18D IS. OP-12.1 (operator, 2026-08-01, directive §17.1) resolved U227 by SUCCESSOR SCHEMA:
 * `schemas/node.schema@1.1.json` beside the untouched frozen `@1.0`, admitting `grok_build`,
 * `google_antigravity` and the `ollama_local` id drift. 18D `.amendment` shipped exactly that and
 * wired nothing to it — its own evidence says so. `.close` is the wiring plus the legs 18C skipped
 * ON THE REGISTRATION FENCE, and this receipt is where that is measured rather than argued.
 *
 * WHAT IT ESTABLISHES, each leg naming the fact:
 *
 *   1. **the vocabulary admits both, from the real files** — `adapter_version_map()` over the real
 *      `schemas/` directory reports `node@1.1` for both providers, `node@1.0` for a frozen member,
 *      and NOTHING for `kimi_k3` (still OWED-pending-operator);
 *   2. **both register as nodes through the product path** — the real `governed_probe_session`,
 *      the real `NodeRegistry`, a real hash-chained append-only log, a record that validates
 *      against `node@1.1` with the real jsonschema validator, and the record CLOSED with the
 *      session (`spawn` → `transition` → `exit`, D-LOOP-1 in the node log);
 *   3. **the fence still refuses** — an adapter no version admits, a session that does not claim
 *      supervision, and a process not spawned by the supervisor (I-C1), each auditable;
 *   4. **and the operator's live world did not move** — their switch still cites OP-6, both
 *      providers are still DENIED at the picker and through the shell's own launcher, the live
 *      session count is unmoved, both OP-12 subscriptions read 0/1 in the status bar the operator
 *      looks at, and their durable ledger file is byte-identical.
 *
 * THE ONE SUBSTITUTION, named here and in the receipt: leg 2's live-operation switch is a FIXTURE
 * config in a scratch directory, because the operator's own file still denies both providers and
 * opening it is theirs alone (invariant 1). Directive §17 calls an unmet entry condition
 * skip-with-record; §6 says substitute the nearest faithful equivalent and run the full governance
 * path around it. **No CLI is executed and no live model call is made** — the session body does
 * nothing. What is NOT established is therefore precise: no live probe, no live pane, and no node
 * record for a LIVE session on the operator's own durable log. Those stay OWED, and
 * `liveWorldUnchanged` refuses to let this receipt stand in for them the moment the switch opens.
 *
 * DISCLOSED COST (D-P18-7/U271/U290): the picker read this check performs enumerates both OP-12
 * CLIs — `grok --version`/`grok models` and the `agy` pair — token-free metadata that leaves this
 * host. One picker read, so one pair each. No prompt, no completion, no credential read.
 */
const fs = require("fs");
const path = require("path");

const { receiptPath } = require("./receipt-path");
const { sourceIdentity } = require("./voice-conductor-selfcheck");
const { fetchPickerModel } = require("../picker/source");
const { fetchLeaseStatus, runPythonEmitter } = require("../conductor/launch-source");
const {
  OP12_CREDENTIAL_NAMES, worldIsFailClosed, leasesAreZero,
} = require("./op12-acceptance-verdict");
const {
  OP12_PROVIDERS, REQUIRED_OWED_KEYS, registrationIsWired, liveWorldUnchanged, owedLegsAreNamed,
  owedClaimsAgreeWithMeasurements, noCredentialMaterial,
} = require("./op18d-registration-verdict");

const RECEIPT_SCHEMA = "phase18d_registration_selfcheck@1.0";
const RECEIPT_PATH = receiptPath("PHASE18D_REGISTRATION_SELFCHECK.json");
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const REAL_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", "terminal_leases.json");
const REGISTRATION_EMITTER = "tools/live/emit_provider_node_registration.py";
const TIMEOUT_MS = 120000;

/** Every §17 acceptance leg this world still cannot perform, each with a reference. */
const OWED = Object.freeze({
  live_provider_probe:
    "§17's ONE harmless live probe per provider (GROK_PROVIDER_OK / GEMINI_PROVIDER_OK) has still "
    + "NEVER executed. The supervised path exists (U234) and now registers a node record (18D "
    + "`.close`), but the operator's live switch cites OP-6, so the probe is refused before any "
    + "CLI runs",
  live_in_electron_receipt:
    "§17's per-provider LIVE in-Electron receipt (picker → supervised pane → verified "
    + "provider+model → harmless prompt → live response → teardown) is OWED — no pane has ever "
    + "been opened for either provider (entry condition unmet ⇒ skip-with-record)",
  durable_node_record_for_a_live_session:
    "U227 is RESOLVED and the wiring is proven here, but every record measured by this receipt was "
    + "written on a SCRATCH log under a FIXTURE live-operation switch. No record exists on the "
    + "operator's own durable node log (.sovereign_store/nodes/), because no live session has ever "
    + "existed to write one — that lands with the live probe, not before it",
  antigravity_auth_state:
    "recorded at 18A: `agy` exposes no offline auth surface, so whether the operator is signed in "
    + "is UNVERIFIABLE here and only a live call can answer it (U233)",
  grok_auth_state:
    "`grok models` answers with the CLI's own listing on this host, which is as far as an offline "
    + "surface can go — evidence of a usable session, NOT of a live reply, which stays owed with "
    + "the probe (18A recon; U233's sibling)",
  operator_live_switch:
    "the entry condition itself: extending config/live_operation.json to name both providers is "
    + "the operator's own edit to a never-committed file, and the code-pinned scope half shipped "
    + "at 18B `.scope` (U237). This build cannot write it — the switch is the operator's "
    + "(invariant 1)",
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

function isWellFormedRegistrationReport(r) {
  // `durable_store` is REQUIRED: the receipt's central negative claim is checked against it, and a
  // report without it would let that claim pass unmeasured (spec-audit MINOR-7).
  return !!r && typeof r === "object" && r.schema === "provider_node_registration@1.0"
    && !!r.vocabulary && !!r.registrations && !!r.refusals && !!r.real_switch && !!r.durable_store;
}

async function run(ctx) {
  const { win, isSupervised, sessionManager, mainLogFile, log } = ctx;
  const receipt = {
    schema: RECEIPT_SCHEMA,
    check: "phase-18d.close",
    authorization: "OP-12.1 (operator, 2026-08-01); AUTONOMOUS_BUILD_DIRECTIVE.md §17.1",
    source: sourceIdentity(),
    started: new Date().toISOString(),
    ok: false,
    supervision_ready: false,
    picker_sourced: false,
    world: null,                 // the operator's switch, through the shell's own enumeration
    registration_report: null,   // the full producer document (it is the evidence, not a summary)
    registration_wired: null,
    live_world_unchanged: null,
    sessions_before: null,
    sessions_after: null,
    lease_status: null,          // provider ref → in_use, from the DURABLE ledger
    lease_zero: null,
    real_ledger_unchanged: false,
    statusbar_painted_text: null,
    options_offered: {},
    credential_scan: null,
    credential_scan_log_file: null,
    credential_sentinel_names: OP12_CREDENTIAL_NAMES.slice(),
    owed: OWED,
    owed_named: null,
    owed_agrees: null,
    error: null,
  };

  // §2.2: PLACEHOLDER values under credential-bearing NAMES. Nothing real is ever read, and a hit
  // is reported by SINK, never by value.
  const sentinels = OP12_CREDENTIAL_NAMES.map((n) => `sow-18d-sentinel-${n}-${process.pid}`);
  const priorEnv = new Map();
  OP12_CREDENTIAL_NAMES.forEach((name, i) => {
    priorEnv.set(name, process.env[name]);
    process.env[name] = sentinels[i];
  });
  const realLedgerBefore = readText(REAL_LEDGER);

  try {
    receipt.supervision_ready = await waitFor(isSupervised, 30000, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY within 30s — nothing is measured, let alone "
        + "registered, without a verified channel (invariant 2)");
    }
    const mgr = sessionManager();
    receipt.sessions_before = mgr ? mgr.registry.alive().length : null;

    // ---- the operator's world, from the shell's own enumeration -------------------------------
    const pickerRes = await fetchPickerModel({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    receipt.picker_sourced = pickerRes.ok === true;
    if (!receipt.picker_sourced) {
      throw new Error(`the host picker enumeration failed: ${pickerRes.error} — a receipt about `
        + "the operator's world is never written against an unverifiable one");
    }
    const picker = pickerRes.picker || {};
    receipt.world = worldIsFailClosed(picker.authorization);
    const options = Array.isArray(picker.options) ? picker.options : [];
    const groups = Array.isArray(picker.providers) ? picker.providers : [];
    for (const provider of OP12_PROVIDERS) {
      const mine = options.filter((o) => o && o.provider === provider);
      const group = groups.find((g) => g && g.provider === provider) || {};
      receipt.options_offered[provider] = {
        count: mine.length,
        available_count: mine.filter((o) => o.available).length,
        group_reason: (group.status && group.status.reason) || null,
      };
      // The registration fence is gone; the LIVE gate is not. A provider that became available
      // here would mean the operator opened the switch — handled by `liveWorldUnchanged` below.
      if (!mine.length) {
        throw new Error(`${provider} enumerated no model on this host — 18B established that both `
          + "CLIs publish their own listings, and a receipt about them needs them present");
      }
    }

    // ---- the registration report, produced by the real product modules ------------------------
    receipt.registration_report = await runPythonEmitter(
      ["--emit-provider-node-registration"],
      { cwd: REPO_ROOT, script: REGISTRATION_EMITTER, timeoutMs: TIMEOUT_MS },
      isWellFormedRegistrationReport, "provider-node-registration");
    const wired = registrationIsWired(receipt.registration_report);
    receipt.registration_wired = { ok: wired.ok, reasons: wired.reasons };
    if (!wired.ok) {
      throw new Error(`the OP-12 node registration is not wired: ${wired.reasons.join("; ")}`);
    }

    // ---- and nothing in the operator's live world moved ---------------------------------------
    receipt.sessions_after = mgr ? mgr.registry.alive().length : null;
    const st = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: TIMEOUT_MS });
    const zero = leasesAreZero(st.ok ? st.status : null);
    receipt.lease_status = zero.in_use;
    receipt.lease_zero = { ok: zero.ok, reasons: zero.reasons };
    receipt.real_ledger_unchanged = readText(REAL_LEDGER) === realLedgerBefore;
    const unchanged = liveWorldUnchanged({
      report: receipt.registration_report,
      sessionsBefore: receipt.sessions_before, sessionsAfter: receipt.sessions_after,
      leaseZero: zero, realLedgerUnchanged: receipt.real_ledger_unchanged,
    });
    receipt.live_world_unchanged = { ok: unchanged.ok, reasons: unchanged.reasons };
    if (!unchanged.ok) {
      throw new Error(`the operator's live world is not what this receipt evidences: `
        + unchanged.reasons.join("; "));
    }

    // …and the same fact where the operator READS it (invariant 27).
    receipt.statusbar_painted_text = await evalR(win, `(function(){
      const el = document.getElementById("statusbar");
      return el ? el.textContent.replace(/\\s+/g, " ").trim() : null;
    })()`);
    if (!/grok\s*0\/1/i.test(receipt.statusbar_painted_text || "")
        || !/agy\s*0\/1/i.test(receipt.statusbar_painted_text || "")) {
      throw new Error(`the status bar does not paint 0/1 for both OP-12 subscriptions: `
        + JSON.stringify(receipt.statusbar_painted_text));
    }

    // ---- §17's credential line, measured ------------------------------------------------------
    const logFile = mainLogFile || null;
    receipt.credential_scan_log_file = logFile;
    const scan = noCredentialMaterial({
      [logFile || "main-process.log (path unknown)"]: logFile ? readText(logFile) : null,
      "PHASE18D_REGISTRATION_SELFCHECK.json (this receipt, pre-write)": JSON.stringify(receipt),
    }, sentinels);
    receipt.credential_scan = { ok: scan.ok, reasons: scan.reasons,
      sinks_checked: scan.sinks_checked, sentinels_checked: scan.sentinels_checked };
    if (!scan.ok) throw new Error(`§17 credential scan: ${scan.reasons.join("; ")}`);

    // ---- what this run did NOT establish, named ------------------------------------------------
    const owed = owedLegsAreNamed(receipt.owed);
    receipt.owed_named = { ok: owed.ok, reasons: owed.reasons, keys: REQUIRED_OWED_KEYS.slice() };
    if (!owed.ok) throw new Error(`the OWED block is incomplete: ${owed.reasons.join("; ")}`);
    // …and the claims must AGREE with what the report measured, not merely be present and wordy.
    const agree = owedClaimsAgreeWithMeasurements(receipt.owed, receipt.registration_report);
    receipt.owed_agrees = { ok: agree.ok, reasons: agree.reasons };
    if (!agree.ok) throw new Error(`an OWED claim contradicts a measurement: ${agree.reasons.join("; ")}`);

    log("[selfcheck] op18d-registration: both OP-12 providers register as node@1.1 Sovereign "
      + "nodes through the product path, the fence still refuses what no version admits, and the "
      + "operator's live world is unmoved (0 sessions, 0 leases, 0/1 painted)");
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  } finally {
    for (const [name, value] of priorEnv) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }

  receipt.ok = receipt.error === null
    && receipt.supervision_ready && receipt.picker_sourced
    && !!(receipt.world && receipt.world.fail_closed)
    && !!(receipt.registration_wired && receipt.registration_wired.ok)
    && !!(receipt.live_world_unchanged && receipt.live_world_unchanged.ok)
    && !!(receipt.credential_scan && receipt.credential_scan.ok)
    && !!(receipt.owed_named && receipt.owed_named.ok)
    && !!(receipt.owed_agrees && receipt.owed_agrees.ok)
    && !!(receipt.source && receipt.source.commit)
    && receipt.source.tracked_product_tree_clean === true
    && (receipt.source.unexpected_untracked_product_files || []).length === 0;

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  receipt.scope_note = "this receipt establishes that the OP-12.1 amendment is WIRED: both "
    + "providers register as Sovereign nodes through the real governed path, under node@1.1, on a "
    + "verified append-only log, with the record closed when the session ends and the fence still "
    + "refusing an id no schema version admits. It does NOT establish a live leg. The one "
    + "substitution is named in the producer document and repeated here: leg 2 reads the "
    + "live-operation switch from a FIXTURE config in a scratch directory, because the operator's "
    + "own file cites OP-6 and denies both providers, and opening it is theirs alone (invariant "
    + "1). No CLI was executed, no live model call was made, no pane was opened, no operator "
    + "terminal was leased, and no record was written to the operator's durable node log — see "
    + "OWED.durable_node_record_for_a_live_session. The verdict module refuses to let this receipt "
    + "be recorded as evidence if the operator has opened the switch: the run throws and the "
    + "receipt is written with ok:false and the reason.";
  receipt.scope_note_disclosed_cost = "the picker read enumerates both OP-12 CLIs — one "
    + "`grok --version`/`grok models` pair and one `agy` pair, token-free metadata that leaves "
    + "this host (D-P18-7/U271). No prompt, no completion, no model call, no credential read. The "
    + "registration report itself performs NO host calls of any kind.";

  // The FINAL payload, re-scanned: `error`, the scope notes, `env` and `ok` are all written after
  // the in-run scan, and publishing a leak is worse than publishing nothing (18C spec-audit
  // MINOR-14, carried forward deliberately).
  const payload = JSON.stringify(receipt, null, 2) + "\n";
  const finalScan = noCredentialMaterial({ "the receipt payload as written": payload }, sentinels);
  if (!finalScan.ok) {
    receipt.ok = false;
    log(`[selfcheck] op18d-registration REFUSED TO WRITE: ${finalScan.reasons.join("; ")}`);
    return receipt;
  }
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, payload);
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] op18d-registration ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runOp18dRegistrationSelfCheck: run, RECEIPT_PATH, OWED };
