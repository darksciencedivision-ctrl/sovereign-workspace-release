"use strict";
/**
 * Phase 18E `.live.electron` in-Electron self-check (D-P16-0 binding, per-track) — **the LIVE OP-12
 * acceptance leg**, the last owed leg of Phase 18.
 *
 * WHY THIS TARGET EXISTS. `op12-acceptance` is the SKIP-WITH-RECORD receipt for a world whose live
 * switch denied both OP-12 providers, and its verdict module refuses to let that receipt stand in
 * for the live legs the moment the operator opens the switch. The operator opened it; that check
 * then failed BY DESIGN (`PHASE18C_ACCEPTANCE_SELFCHECK.json`, 2026-08-02T00:11Z, `ok:false`), and
 * OP-12.2 (directive §17.2) made its error text the spec for this one. This is the sibling target
 * the open-switch world demands — not a "live mode" bolted onto the fail-closed one, because the
 * two receipts assert opposite things about the same world and a flag that flips a verdict is how
 * one of them ends up asserting nothing.
 *
 * WHAT IT ESTABLISHES, per provider, each leg naming the fact it measures (§17 / §17.2(1)):
 *
 *   1. **the operator's own picker selection** — an option this host really enumerated from the
 *      provider's own CLI, put through `spawnFromSelection`, the exact function the
 *      `pane:spawnFromSelection` IPC handler calls when the operator clicks *spawn*;
 *   2. **a supervised ConPTY pane that IS a registered Sovereign node** — the durable I-X3 terminal
 *      counted against that provider's own resource (allowance 1), and a `node@1.1` record on the
 *      OPERATOR's durable node log that goes `SPAWNING` → `READY` (carrying the supervised pid) →
 *      `TERMINATED` + `exit`, bound to THIS session, on a hash chain that still links end to end;
 *   3. **the exact provider and model, verified** — off the binary that was actually spawned and
 *      the model id the argv actually asked for, not off the chrome that describes them;
 *   4. **ONE harmless prompt, ONE live response** — through the RENDERER's own input path
 *      (`term.input()` → `pane:input` → `SessionManager.write` → the ConPTY), with the falsifiable
 *      probe 17A introduced: operands spelled in words so the prompt contains no digit, drawn fresh
 *      per run, and the answer token asserted ABSENT from the pane before submitting. An echo is
 *      not an answer, and a CLI that exits zero having said nothing is not a live response (U310);
 *   5. **teardown** — the session killed here, the durable terminal back at 0/1 read from a
 *      SEPARATE process, and the node record closed on the same log (D-LOOP-1);
 *   6. **§17's credential line over every sink this check can read** — the shell's durable
 *      main-process log, THIS receipt, the pane's rendered PTY output, the CHILD ENVIRONMENT, and
 *      the two DURABLE STORES this run writes into (the node event log and the lease ledger, both
 *      written by `py -3.12` children that inherit this process's environment). The 18C scan covered
 *      two sinks because in that world nothing was ever spawned. **What the transcript sink is, and
 *      is not** (spec-audit M-2): `grok` and `agy` are full-screen TUIs on xterm's ALTERNATE buffer,
 *      which keeps no scrollback — so that sink is the pane's screen as rendered at teardown, not
 *      the session's whole output. Material printed and then repainted over is NOT covered by it,
 *      and no claim to the contrary is made here or in the receipt (recorded as U324).
 *
 * LIVE SCOPE (§17.2, and the standing budget the `.live.shape` unit overran and recorded as U312):
 * **ONE live exchange per provider** — one prompt, one answer, one session, killed here. The two
 * providers run STRICTLY SEQUENTIALLY and the check asserts the previous session is gone before
 * the next is asked for: no simultaneous same-provider sessions, and in fact none at all.
 *
 * THE REAL LEDGER, deliberately. Every other live self-check in this build redirects
 * `SOW_TERMINAL_LEASE_LEDGER` to a scratch file, because it must never adopt or release a terminal
 * the operator's own conductor holds. This one does NOT, and that is the point of §17.2's
 * "durable-ledger consistency": the acceptance leg is about the operator's real I-X3 accounting —
 * a real terminal counted 1/1 against `grok_build_subscription` / `google_antigravity_subscription`
 * and handed back to 0. No other LEASED session can hold those two: their allowance is 1 each and
 * the conductor runs on `claude_code`. What the ledger cannot see is a provider CLI the operator ran
 * BY HAND — including the very `grok`/`agy` invocation this check's own operator step asks for,
 * which takes no lease (U325). So run the operator step, answer the modal, and let that CLI exit
 * before re-running this check. The same argument applies to the node log, which is the operator's
 * real one by necessity — a record on a scratch log is the substitution 18D already made and named
 * OWED.
 */
const fs = require("fs");
const path = require("path");

const { receiptPath } = require("./receipt-path");
const { sourceIdentity } = require("./voice-conductor-selfcheck");
const { fetchPickerModel } = require("../picker/source");
const { releaseWorkerTerminal } = require("../picker/launch-source");
const { fetchLeaseStatus } = require("../conductor/launch-source");
const {
  buildRoundTripProbe, probeIsFalsifiable, answerObserved, promptEchoed,
} = require("../conductor/roundtrip-probe");
const {
  OP12_PROVIDERS, OP12_SUBSCRIPTION_REFS, OP12_CREDENTIAL_NAMES, REQUIRED_OWED_KEYS,
  worldIsLiveOpen, paneRunsExactlyThisSelection, childEnvIsScrubbed, liveAnswerIsHonest,
  nodeRecordLifecycleIsComplete, appendOnlyChainIsIntact, owedLegsAreNamed,
  paneConsentGate, consentOutcomeIsHonest, repoUnchangedByTheRun, credentialSinkMap, sentinelPlan,
  leasesAreZero, noCredentialMaterial,
} = require("./op12-live-acceptance-verdict");

const RECEIPT_SCHEMA = "phase18e_live_acceptance_selfcheck@1.0";

/** A RUN-STAMPED receipt name, and the reason is a defect this target caused twice.
 *
 * Every other self-check writes to one fixed path, which is fine for a check that is re-run to
 * re-prove the same thing. This one is a LIVE leg: each run is a different world (different pids,
 * leases, node-log rows, and a different answer to "has the operator cleared U317 yet"). Writing
 * them all to one name meant (a) a superseded run left NO artifact at all, which is how a unit came
 * to report three runs where the operator's durable node log recorded four (U322), and (b) the
 * operator instruction "just run it again" would silently overwrite the receipt an already-published
 * checkpoint cites BY CONTENT — the inversion this track keeps hitting, handed to the operator as a
 * command (spec-audit MAJOR-3, gate-validator MEDIUM-3).
 *
 * So: `…_<unit>_<UTC stamp>.json`, never overwritten, and the canonical name stays exactly as the
 * `.live.electron` unit published it. `--unit` (or `SOW_SELFCHECK_UNIT`) labels which work unit ran
 * it; without one it is `run`.
 */
const RECEIPT_STAMP = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
const RECEIPT_UNIT = String(process.env.SOW_SELFCHECK_UNIT || "run")
  .replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 40);
const RECEIPT_PATH = receiptPath(
  `PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_${RECEIPT_UNIT}_${RECEIPT_STAMP}.json`);
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
/** The OPERATOR's real durable stores — this leg is ABOUT them (see the header). */
const REAL_LEDGER = path.join(REPO_ROOT, ".sovereign_store", "leases", "terminal_leases.json");
const REAL_NODE_LOG = path.join(REPO_ROOT, ".sovereign_store", "nodes", "node_events.jsonl");

const DISPLAY = { grok_build: "Grok Build", google_antigravity: "Gemini · Antigravity" };

/** Per-step ceilings. Their sum stays under this kind's launcher bound, so a stall FAILS here with
 * the step that stalled NAMED rather than being killed blind (exit 124 writes no receipt). */
const SUPERVISION_MS = 30000;
const EMITTER_MS = 120000;
const BANNER_MS = 60000;
const QUIESCE_MS = 60000;
const ECHO_MS = 30000;
const ANSWER_MS = 210000;
const KILL_MS = 20000;
const RELEASE_MS = 60000;
const NODE_CLOSE_MS = 45000;

/** Which model each provider's live leg PREFERS: the option whose own NAME advertises the smallest
 * tier this host enumerates (`…-flash-low`), because §17 asks for one harmless prompt and nothing
 * about the answer's depth. This is a NAME heuristic, not a cost claim — no pricing data exists
 * anywhere on this path and none is implied (U321(b)). Never a fabrication: if the host does not
 * offer it, the first AVAILABLE option this host really enumerated is used and the receipt records
 * which. */
const PREFERRED_MODEL = {
  grok_build: "grok-4.5",
  google_antigravity: "gemini-3.6-flash-low",
};

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

function readText(file) {
  try { return fs.readFileSync(file, "utf8"); } catch { return null; }
}

/** The operator's durable node log, as rows. An unreadable log is `null` — never an empty list,
 * which would read as "nothing was ever written" (fail closed). */
function readNodeRows() {
  const text = readText(REAL_NODE_LOG);
  if (typeof text !== "string") return null;
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try { rows.push(JSON.parse(line)); } catch { return null; }
  }
  return rows;
}

/** The rendered xterm buffer for a pane (read-only renderer observability hook). */
async function paneText(win, paneId) {
  const expr = `window.__sovereignSelfCheck && window.__sovereignSelfCheck.paneText(${JSON.stringify(paneId)})`;
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

/** Type through the REAL renderer input wiring (term.onData → pane:input → manager.write → PTY). */
async function typeInto(win, paneId, data) {
  const expr = `window.__sovereignSelfCheck.typeInto(${JSON.stringify(paneId)}, ${JSON.stringify(data)})`;
  try { return await win.webContents.executeJavaScript(expr); } catch { return false; }
}

/**
 * An interactive provider TUI is ready for input once it has painted SOMETHING and stopped
 * repainting. Deliberately not keyed on the workspace path the way the `claude` check is: `grok`
 * and `agy` paint their own banners, and requiring one CLI's chrome from another is how a check
 * fails for a reason that has nothing to do with the fact it measures.
 */
async function waitForQuiescence(win, paneId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  let stableSince = null;
  while (Date.now() < deadline) {
    const text = await paneText(win, paneId);
    const painted = typeof text === "string" && text.trim().length > 0;
    if (painted && text === last) {
      if (stableSince === null) stableSince = Date.now();
      if (Date.now() - stableSince >= 2500) return { ready: true, text };
    } else {
      stableSince = null;
    }
    last = text;
    await sleep(500);
  }
  return { ready: false, text: last };
}

/** The provider's own available option, preferring a named model — never fabricated. */
function pickOption(options, provider) {
  const mine = (options || []).filter((o) => o && o.provider === provider && o.available === true
    && (o.roles || []).includes("reasoning"));
  return mine.find((o) => o.model_slug === PREFERRED_MODEL[provider]) || mine[0] || null;
}

const samePath = (a, b) => {
  const x = path.resolve(String(a || ""));
  const y = path.resolve(String(b || ""));
  return process.platform === "win32" ? x.toLowerCase() === y.toLowerCase() : x === y;
};

/** Every §17 acceptance leg a LIVE run still does not establish, each with a reference. */
const OWED = Object.freeze({
  operator_first_use:
    "the operator has not typed into either pane themselves. Where this receipt types at all it "
    + "drives the RENDERER's own input path (invariant 27's surface, not a back door), which is as "
    + "close as a machine can get; the operator's own use is the half only they can discharge, "
    + "exactly as directive §16's DEFINITION OF DONE reserves the spoken-mic leg to them",
  provider_answer_quality:
    "for a provider listed in `providers_live` — and ONLY for one listed there — what is "
    + "established is that a live model answered one arithmetic probe: nothing about that "
    + "provider's capability, tool use, agentic behaviour or fitness for any role. §17 asks for one "
    + "harmless prompt and this receipt claims no more than that. A provider absent from that list "
    + "has no answer of any quality on this run",
  concurrent_same_provider:
    "§17 forbids simultaneous same-provider sessions, so the allowance-1 refusal path (a second "
    + "grok/agy pane while one is live) is NOT exercised here. Its governed refusal is covered by "
    + "the headless suite and by 18B's picker legs; deliberately unexercised is not the same as "
    + "unknown, and it is stated rather than left to inference",
  op6_provider_pane_records:
    "U313: `claude_code` and `openai_codex_cli` panes hold a durable terminal and STILL no Sovereign "
    + "node record — registering them would change behaviour OP-12's own supersession list names "
    + "untouchable. This receipt covers the two OP-12 providers only",
  provider_workspace_trust:
    "each OP-12 CLI raises its OWN directory-trust consent on an interactive launch in this "
    + "workspace (grok: \"Yes, proceed\"; agy: \"Do you trust the contents of this project?\"), and "
    + "no argv flag dismisses it — both panes already run in the least-authority mode each CLI "
    + "offers (`--permission-mode plan` / `--mode plan`) and are asked anyway. Answering it grants a "
    + "frontier CLI read/edit/execute authority over the operator's workspace, which is a protected "
    + "action the loop never self-authorizes (invariant 1) and which OP-12's own directive §11 "
    + "refuses as an unsandboxed default. Until the operator answers it once themselves, that "
    + "provider's typed round trip is skip-with-record, and this receipt names the step rather than "
    + "pressing the key",
  containment_beyond_env:
    "U25 (the OS job-object handoff) and U78(a) (permission-profile binding) are unchanged and still "
    + "owed. What is measured here is supervised admission, the Python-minted identity, the governed "
    + "workspace as the ConPTY cwd, and the §2.2 credential scrub on the child's environment — not "
    + "that the pid is provably the pane's own descendant (invariant 29's harness-level half)",
});

async function run(ctx) {
  const { win, isSupervised, spawnFromSelection, workerLaunchState, workerLauncher, sessionManager,
    killSession, paneModel, ptySpawnObserved, mainLogFile, log } = ctx;
  const receipt = {
    schema: RECEIPT_SCHEMA,
    check: "phase-18e.live.electron",
    // A self-declared label for WHICH work unit ran this target, so two receipts of the same kind
    // are not told apart by filename alone (gate-validator MINOR-1). It carries no authority: it is
    // whatever the runner said, while `source.commit` and `started` are measured.
    unit: process.env.SOW_SELFCHECK_UNIT || null,
    authorization: "OP-12.2 (operator, 2026-08-02); acceptance criteria AUTONOMOUS_BUILD_DIRECTIVE.md "
      + "§17 + §17.2(1)",
    source: sourceIdentity(),
    started: new Date().toISOString(),
    ok: false,
    ledger_scope: "the OPERATOR's real durable ledger and node log — see scope_note_real_stores",
    electron_main_pid: process.pid,
    supervision_ready: false,
    picker_sourced: false,
    world: null,
    // per provider, in the order they ran
    legs: {},
    providers_attempted: [],
    providers_live: [],
    // §6/§17 skip-with-record: which providers stopped on their own consent gate, and the one-time
    // operator step each is waiting for. Empty is the claim that nothing was gated.
    providers_consent_gated: [],
    operator_steps: [],
    // the shared negatives, measured after BOTH legs
    sessions_before: null,
    sessions_after: null,
    lease_status: null,
    lease_zero: null,
    real_ledger_leases_empty: null,
    node_log_rows_before: null,
    node_log_rows_after: null,
    node_log_chain: null,
    source_after: null,
    repo_unchanged_by_the_run: null,
    live_exchanges_spent: null,
    credential_scan: null,
    credential_scan_log_file: null,
    lease_ledger_file: null,
    node_log_file: null,
    credential_sentinel_names: OP12_CREDENTIAL_NAMES.slice(),
    owed: OWED,
    owed_named: null,
    error: null,
  };

  // §2.2: PLACEHOLDER values planted under credential-bearing NAMES. Nothing real is ever read, and
  // a hit is reported by SINK, never by value. Named with this process's pid so a hit cannot be some
  // other run's string. These are ALSO what makes the child-environment leg meaningful: the scrub
  // list is non-empty by construction, so "the name is absent from the child" measures a removal
  // rather than an absence.
  // A name the host ALREADY sets is SKIPPED, not captured: the earlier version read whatever real
  // value was there into a Map for the run's duration, which §2.2 and OP-12 §13 forbid in the same
  // breath as storing one ("never create, READ, store, or transmit"). Skipping is also the only way
  // not to overwrite an operator's live credential with a placeholder. The skipped names are
  // reported — names are this build's own constants, not secrets — so a thin scan is never mistaken
  // for a complete one.
  const plan = sentinelPlan(process.env, OP12_CREDENTIAL_NAMES, process.pid);
  const planted = plan.planted;
  const plantedSentinels = plan.sentinels;
  planted.forEach((name, i) => { process.env[name] = plantedSentinels[i]; });
  receipt.credential_sentinels_planted = planted.slice();
  receipt.credential_sentinels_skipped_present_on_host = plan.skipped.slice();
  const transcripts = {};        // provider → the pane's rendered transcript, scanned below
  const started = [];            // paneIds this check spawned, killed in `finally` whatever happened

  try {
    receipt.supervision_ready = await waitFor(isSupervised, SUPERVISION_MS, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY within 30s — nothing is asked for, let alone "
        + "born, without a verified control-plane channel (invariant 2)");
    }
    const mgr = sessionManager();
    receipt.sessions_before = mgr ? mgr.registry.alive().length : null;
    receipt.node_log_rows_before = (readNodeRows() || []).length;

    // ---- the world: a LIVE receipt is only written where the switch really authorizes -----------
    const pickerRes = await fetchPickerModel({ cwd: REPO_ROOT, timeoutMs: EMITTER_MS });
    receipt.picker_sourced = pickerRes.ok === true;
    if (!receipt.picker_sourced) {
      throw new Error(`the host picker enumeration failed: ${pickerRes.error} — an acceptance `
        + "receipt is never written against an unverifiable offer");
    }
    const picker = pickerRes.picker || {};
    receipt.world = worldIsLiveOpen(picker.authorization);
    if (!receipt.world.op12_authorized.length) {
      // The mirror of the 18C refusal: that receipt refuses to stand in for the live legs in an
      // OPEN world; this one refuses to claim them in a CLOSED one. Skip-with-record is `op12-
      // acceptance`'s job and it already exists — pointing at it is more honest than writing a
      // second, weaker copy of it here.
      throw new Error(`${receipt.world.reason} — the live acceptance legs cannot run; the `
        + "skip-with-record receipt for that world is `op12-acceptance` (directive §17)");
    }
    const options = Array.isArray(picker.options) ? picker.options : [];

    // ---- one provider at a time. STRICTLY sequential (§17: no simultaneous sessions) ------------
    for (const provider of receipt.world.op12_authorized) {
      const leg = {
        provider,
        display: DISPLAY[provider] || provider,
        option: null,
        sessions_at_start: mgr ? mgr.registry.alive().length : null,
        no_other_session_live: false,
        pane_id: null,
        launched: false,
        launch_reason: null,
        launch_refused_by: null,
        node_id: null,
        session_pid: null,
        session_state: null,
        argv: null,
        model_slug_launched: null,
        exact_selection: null,
        child_env: null,
        env_scrub_count: null,
        lease_id: null,
        lease_in_use: null,
        lease_session_keyed: false,
        lease_visible_cross_process: false,
        banner_seen: false,
        banner_excerpt: null,
        quiescent: false,
        probe_prompt: null,
        probe_expected_token: null,
        probe_falsifiable: false,
        probe_rerolls: 0,
        consent_gate: null,
        consent_operator_step: null,
        consent_detected_before_typing: false,
        consent_outcome: null,
        skipped_with_record: false,
        answer_absent_before_submit: false,
        typed_via_renderer: false,
        prompt_echoed: false,
        submitted: false,
        answer_seen: false,
        answer_form: null,
        answer_latency_ms: null,
        answer_excerpt: null,
        pane_excerpt_at_teardown: null,
        live_answer: null,
        session_killed: false,
        lease_released: false,
        in_use_after_release: null,
        node_registration: null,
        node_attested: null,
        node_closure: null,
        node_lifecycle: null,
        ok: false,
        error: null,
      };
      receipt.legs[provider] = leg;
      receipt.providers_attempted.push(provider);
      try {
        // §17's no-simultaneous-sessions line, measured rather than promised by the loop's shape:
        // the previous provider's session must already be gone.
        leg.no_other_session_live = leg.sessions_at_start === receipt.sessions_before;
        if (!leg.no_other_session_live) {
          throw new Error(`${leg.sessions_at_start} session(s) are live before this leg starts `
            + `(baseline ${receipt.sessions_before}) — §17 allows no simultaneous provider session`);
        }
        const option = pickOption(options, provider);
        if (!option) {
          throw new Error(`${DISPLAY[provider]} offers no AVAILABLE reasoning model on this host — `
            + "nothing may be fabricated to launch (operator directive §8)");
        }
        leg.option = { label: option.label, model_slug: option.model_slug,
          verified: option.verified === true, preferred: option.model_slug === PREFERRED_MODEL[provider] };

        // ---- leg 1: the OPERATOR's own picker click, through the production path -----------------
        const res = await spawnFromSelection({
          option, role: "reasoning", mode: "autonomous", targetPaneId: null,
        });
        leg.pane_id = res.target || null;
        leg.launched = res.launched === true;
        leg.launch_reason = res.reason || res.error || null;
        leg.launch_refused_by = res.refusedBy || null;
        leg.node_id = res.nodeId || null;
        leg.argv = Array.isArray(res.argv) ? res.argv.slice() : null;
        if (leg.pane_id) started.push(leg.pane_id);
        if (!leg.launched) {
          throw new Error(`the governed live launch did not run (${leg.launch_refused_by || "no gate"}): `
            + `${leg.launch_reason || "unknown"}`);
        }

        // ---- leg 2+3: the pane IS this provider, on this model, supervised and counted -----------
        const record = workerLaunchState(leg.pane_id);
        const session = (mgr && mgr.registry.has(leg.pane_id)) ? mgr.registry.get(leg.pane_id) : null;
        const spawned = ptySpawnObserved() || null;
        leg.session_state = session ? session.state : null;
        leg.session_pid = session ? session.pid : null;
        leg.lease_id = record.leaseId || null;
        leg.node_registration = record.nodeRegistration || null;
        leg.node_attested = { attested: record.nodeAttested === true,
          outcome: record.nodeAttestation || null };
        const exact = paneRunsExactlyThisSelection({
          provider, option, launch: res, record, session, spawned, repoRoot: REPO_ROOT, samePath,
        });
        leg.exact_selection = { ok: exact.ok, reasons: exact.reasons };
        leg.model_slug_launched = exact.model_slug_launched;
        if (!exact.ok) {
          throw new Error(`the pane is not verifiably this provider on this model: `
            + exact.reasons.join("; "));
        }
        // …and it is a REGISTERED Sovereign node, which is what §17.2(1) asks the pane to be.
        if (!leg.node_registration || leg.node_registration.registered !== true) {
          throw new Error("the ticket wrote no Sovereign node record for this pane "
            + `(${(leg.node_registration && leg.node_registration.reason) || "no registration block"}) `
            + "— invariant 2: a counted terminal is a node, and §17.2(1) asks for the record");
        }
        if (!leg.node_attested.attested) {
          throw new Error("the pane's node record was never moved to READY with its supervised pid "
            + `(${(leg.node_attested.outcome && leg.node_attested.outcome.error) || "no outcome"}) — `
            + "the record would read SPAWNING for a process that is demonstrably running");
        }

        // ---- §2.2 on the environment the CHILD was handed ----------------------------------------
        const scrubNames = (record.envScrubNames || []).filter((n) => n in process.env);
        const env = childEnvIsScrubbed({ spawned, scrubNames, credentialNames: OP12_CREDENTIAL_NAMES });
        leg.child_env = { ok: env.ok, reasons: env.reasons, inherited: spawned && spawned.inheritedEnv === true };
        leg.env_scrub_count = env.scrub_count;
        if (!env.ok) throw new Error(`the child environment is not scrubbed: ${env.reasons.join("; ")}`);

        // ---- the durable I-X3 terminal, seen from a SEPARATE process ------------------------------
        const st = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: EMITTER_MS });
        const entry = ((st.ok && st.status && st.status.subscriptions) || {})[OP12_SUBSCRIPTION_REFS[provider]] || null;
        leg.lease_in_use = entry ? entry.in_use : 0;
        const holder = entry && (entry.holders || []).find((h) => h.lease_id === leg.lease_id);
        leg.lease_visible_cross_process = Boolean(holder && holder.holder_pid === process.pid);
        leg.lease_session_keyed = Boolean(holder && holder.session_id === record.sessionId);
        if (!leg.lease_visible_cross_process || !leg.lease_session_keyed) {
          throw new Error(`a separate process cannot see this pane's durable terminal keyed to its `
            + `session (in_use=${leg.lease_in_use}) — the I-X3 count is not real`);
        }

        // ---- leg 4: the pane is not black, then ONE harmless prompt and ONE live answer ----------
        leg.banner_seen = await waitFor(async () => {
          const text = await paneText(win, leg.pane_id);
          return typeof text === "string" && text.trim().length > 0;
        }, BANNER_MS, 500);
        const bannerText = await paneText(win, leg.pane_id);
        leg.banner_excerpt = typeof bannerText === "string"
          ? bannerText.replace(/\s+/g, " ").trim().slice(0, 200) : null;
        if (!leg.banner_seen) {
          throw new Error("the live session rendered NOTHING into its pane — a blank pane is the "
            + "defect 16A exists for, and there is nothing to type into");
        }
        const quiet = await waitForQuiescence(win, leg.pane_id, QUIESCE_MS);
        leg.quiescent = quiet.ready;
        if (!leg.quiescent) {
          throw new Error("the live session never settled into a quiescent view — keystrokes would "
            + "land in a half-drawn frame");
        }

        // ---- the gate that answers to nobody but the operator -------------------------------------
        // BEFORE a probe is drawn, let alone typed. A modal that consumes keystrokes cannot answer
        // an arithmetic question, and pushing one into it would spend a live exchange of the
        // directive's per-provider budget on a prompt that reaches no model.
        const gateBefore = paneConsentGate(provider, quiet.text);
        if (gateBefore.gate) {
          leg.consent_gate = gateBefore.gate;
          leg.consent_operator_step = gateBefore.operator_step;
          leg.consent_detected_before_typing = true;
          throw new Error(`${DISPLAY[provider]} is waiting on its own ${gateBefore.gate} gate, `
            + "which the loop may not answer (invariant 1; operator directive §11) — this leg is "
            + `SKIPPED WITH RECORD. One-time operator step: ${gateBefore.operator_step}`);
        }

        let probe = null;
        const before = quiet.text || "";
        for (let roll = 0; roll < 5; roll += 1) {
          probe = buildRoundTripProbe();
          leg.probe_rerolls = roll;
          if (!answerObserved(before, probe).seen) break;
          probe = null;   // this draw's answer is already on screen — it would pass for free
        }
        if (!probe) throw new Error("could not draw an answer token absent from the pane in 5 attempts");
        leg.probe_prompt = probe.prompt;
        leg.probe_expected_token = probe.expectedToken;
        leg.probe_falsifiable = probeIsFalsifiable(probe);
        leg.answer_absent_before_submit = !answerObserved(before, probe).seen;

        await win.webContents.executeJavaScript(
          `window.__sovereignSelfCheck.focusPane(${JSON.stringify(leg.pane_id)})`);
        leg.typed_via_renderer = (await typeInto(win, leg.pane_id, probe.prompt)) === true;
        if (leg.typed_via_renderer) {
          leg.prompt_echoed = await waitFor(
            async () => promptEchoed(await paneText(win, leg.pane_id), probe), ECHO_MS, 500);
        }
        const submittedAt = Date.now();
        if (leg.prompt_echoed) leg.submitted = (await typeInto(win, leg.pane_id, "\r")) === true;
        let observed = { seen: false, form: null };
        if (leg.submitted) {
          const got = await waitFor(async () => {
            observed = answerObserved(await paneText(win, leg.pane_id), probe);
            return observed.seen;
          }, ANSWER_MS, 1500);
          leg.answer_seen = got && observed.seen;
          leg.answer_form = observed.form;
          leg.answer_latency_ms = got ? Date.now() - submittedAt : null;
        }
        const after = await paneText(win, leg.pane_id);
        transcripts[provider] = typeof after === "string" ? after : null;
        leg.answer_excerpt = typeof after === "string"
          ? after.replace(/\s+/g, " ").trim().slice(-300) : null;
        const honest = liveAnswerIsHonest({
          falsifiable: leg.probe_falsifiable, absentBefore: leg.answer_absent_before_submit,
          echoed: leg.prompt_echoed, submitted: leg.submitted,
          answer: { seen: leg.answer_seen, form: leg.answer_form },
        });
        leg.live_answer = { ok: honest.ok, reasons: honest.reasons };
        if (!honest.ok) {
          // …but WHY. A gate can rise after quiescence — `agy` settled on its sign-in screen and
          // reached the trust prompt only later — and "the keystrokes are not reaching the live
          // session" is a dead-terminal finding about a session that was alive and waiting for a
          // human. The pane is asked once more before that sentence is allowed to stand.
          // …and only where the prompt never echoed. A modal does not echo what you type, so an
          // echoed prompt says the pane was a real prompt and the gate text came out of scrollback;
          // blaming it there would bury a U310 (keystrokes landed, model said nothing).
          const gateAfter = leg.prompt_echoed ? { gate: null } : paneConsentGate(provider, after);
          if (gateAfter.gate) {
            leg.consent_gate = gateAfter.gate;
            leg.consent_operator_step = gateAfter.operator_step;
            throw new Error(`${DISPLAY[provider]} reached its own ${gateAfter.gate} gate rather `
              + "than a prompt: what was typed was consumed by a modal the loop may not answer "
              + "(invariant 1; operator directive §11) — this leg is SKIPPED WITH RECORD. "
              + `One-time operator step: ${gateAfter.operator_step}`);
          }
          throw new Error(`${DISPLAY[provider]} did not produce an honest live answer: `
            + honest.reasons.join("; "));
        }
        log(`[selfcheck] ${provider} LIVE: "${probe.prompt}" → ${probe.expectedToken} `
          + `(${leg.answer_form}) in ${leg.answer_latency_ms}ms on ${leg.model_slug_launched}`);
      } catch (e) {
        leg.error = String((e && e.message) || e);
      }

      // ---- leg 5: teardown for THIS provider, before the next one is even asked for -------------
      // Outside the try on purpose: a leg that failed mid-way still holds a live session and a
      // durable terminal, and D-LOOP-1 is not conditional on the leg having gone well.
      try {
        if (leg.pane_id) {
          // The pane's transcript is a §17 credential SINK, and it exists whatever happened above:
          // a leg that stopped at a consent gate never reached the read further up, and leaving the
          // sink null made the scan fail closed on a transcript that was sitting right there. Read
          // it BEFORE the kill, and only if the answered path did not already capture it.
          if (transcripts[provider] === undefined || transcripts[provider] === null) {
            const t = await paneText(win, leg.pane_id);
            transcripts[provider] = typeof t === "string" ? t : null;
            leg.pane_excerpt_at_teardown = typeof t === "string"
              ? t.replace(/\s+/g, " ").trim().slice(-300) : null;
          }
          const pid = leg.session_pid;
          try { killSession(leg.pane_id); } catch { /* already terminal */ }
          leg.session_killed = await waitFor(() => {
            if (!Number.isInteger(pid)) return true;
            try { process.kill(pid, 0); return false; } catch { return true; }
          }, KILL_MS, 250);
          leg.lease_released = await waitFor(async () => {
            const afterStatus = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: EMITTER_MS });
            if (!afterStatus.ok || !afterStatus.status) { leg.in_use_after_release = null; return false; }
            const e2 = (afterStatus.status.subscriptions || {})[OP12_SUBSCRIPTION_REFS[provider]] || null;
            leg.in_use_after_release = e2 ? e2.in_use : 0;
            return leg.in_use_after_release === 0;
          }, RELEASE_MS, 1500);
          // the node record's own end, read off the OPERATOR's log rather than off the report
          const closed = await waitFor(async () => {
            const rows = readNodeRows();
            if (!rows) return false;
            const life = nodeRecordLifecycleIsComplete({
              rows, nodeKey: leg.node_id, sessionId: workerLaunchState(leg.pane_id).sessionId,
              recordUuid: (leg.node_registration && leg.node_registration.node_id) || "",
              pid: leg.session_pid,
            });
            leg.node_lifecycle = { ok: life.ok, reasons: life.reasons,
              incarnation: life.incarnation, states: life.states };
            return life.ok;
          }, NODE_CLOSE_MS, 1500);
          leg.node_closure = workerLaunchState(leg.pane_id).nodeClosure || null;
          if (!closed && leg.node_lifecycle === null) {
            leg.node_lifecycle = { ok: false, incarnation: null, states: [],
              reasons: ["the operator's durable node log could not be read after teardown"] };
          }
          try { if (paneModel && paneModel().panes.has(leg.pane_id)) paneModel().destroyPane(leg.pane_id); }
          catch { /* pane already gone */ }
        }
      } catch (e) {
        leg.error = leg.error || `teardown failed: ${String((e && e.message) || e)}`;
      }
      leg.ok = leg.error === null
        && leg.launched === true
        && !!(leg.exact_selection && leg.exact_selection.ok)
        && !!(leg.child_env && leg.child_env.ok)
        && !!(leg.live_answer && leg.live_answer.ok)
        && leg.lease_visible_cross_process && leg.lease_session_keyed
        && leg.session_killed && leg.lease_released && leg.in_use_after_release === 0
        && !!(leg.node_lifecycle && leg.node_lifecycle.ok)
        && !!(leg.node_attested && leg.node_attested.attested);
      // …and HOW it is allowed to be reported when a consent gate is what stopped it.
      const consent = consentOutcomeIsHonest({
        gate: leg.consent_gate, operator_step: leg.consent_operator_step,
        detected_before_typing: leg.consent_detected_before_typing,
        typed: leg.typed_via_renderer, submitted: leg.submitted, echoed: leg.prompt_echoed,
        answer_seen: leg.answer_seen, ok: leg.ok,
      });
      leg.consent_outcome = { ok: consent.ok, reasons: consent.reasons };
      leg.skipped_with_record = consent.skipped;
      if (leg.consent_gate) {
        receipt.providers_consent_gated.push(provider);
        // …with what consenting GRANTS, in the field the operator will actually act on. The
        // disclosure sat only in `owed`, one indirection away from the instruction.
        receipt.operator_steps.push(`${DISPLAY[provider] || provider} (${leg.consent_gate}): `
          + `${leg.consent_operator_step}. What answering it grants: directory-scoped authority for `
          + "that CLI to read, edit and execute in this workspace — which is why the decision is "
          + "yours and not the loop's.");
      }
      if (leg.ok) receipt.providers_live.push(provider);
      else if (!receipt.error) {
        receipt.error = `${DISPLAY[provider] || provider}: ${leg.error || "a leg did not pass"}`;
      }
    }

    // ---- the shared negatives, after BOTH legs --------------------------------------------------
    receipt.sessions_after = mgr ? mgr.registry.alive().length : null;
    const finalStatus = await fetchLeaseStatus({ cwd: REPO_ROOT, timeoutMs: EMITTER_MS });
    const zero = leasesAreZero(finalStatus.ok ? finalStatus.status : null);
    receipt.lease_status = zero.in_use;
    receipt.lease_zero = { ok: zero.ok, reasons: zero.reasons };
    // …and the operator's ledger FILE, not merely the count derived from it. It legitimately
    // CHANGED during this run (a terminal was taken and handed back), so "unchanged" — the 18C/18D
    // assertion — would be the wrong question here; what must hold is that it holds nothing now.
    try {
      const ledger = JSON.parse(readText(REAL_LEDGER) || "{}");
      receipt.real_ledger_leases_empty = Array.isArray(ledger.leases) && ledger.leases.length === 0;
    } catch { receipt.real_ledger_leases_empty = false; }

    const rowsAfter = readNodeRows();
    receipt.node_log_rows_after = rowsAfter ? rowsAfter.length : null;
    const chain = appendOnlyChainIsIntact(rowsAfter);
    receipt.node_log_chain = { ok: chain.ok, reasons: chain.reasons, rows: chain.rows };

    // ---- §17's credential line, over every sink this check can read -----------------------------
    // The two DURABLE STORES are in the scan because this run writes into both of them through
    // `py -3.12` children that inherit this process's sentinel-bearing environment (spec-audit M-2);
    // a serialization change that ever put an environment value into a record would land there and
    // nowhere else. The receipt sink names the file actually written, not the sibling this target
    // once wrote (the `.close` run is copied to a dated path — reviewer NIT n-2).
    const logFile = mainLogFile || null;
    receipt.credential_scan_log_file = logFile;
    receipt.lease_ledger_file = REAL_LEDGER;
    receipt.node_log_file = REAL_NODE_LOG;
    const sinks = credentialSinkMap({
      logFile, logText: logFile ? readText(logFile) : null,
      receiptName: path.basename(RECEIPT_PATH), receiptPayload: JSON.stringify(receipt),
      nodeLogPath: REAL_NODE_LOG, nodeLogText: readText(REAL_NODE_LOG),
      ledgerPath: REAL_LEDGER, ledgerText: readText(REAL_LEDGER),
      providers: receipt.providers_attempted, transcripts,
    });
    const scan = noCredentialMaterial(sinks, plantedSentinels);
    receipt.credential_scan = { ok: scan.ok, reasons: scan.reasons,
      sinks_checked: scan.sinks_checked, sentinels_checked: scan.sentinels_checked };

    const owed = owedLegsAreNamed(receipt.owed);
    receipt.owed_named = { ok: owed.ok, reasons: owed.reasons, keys: REQUIRED_OWED_KEYS.slice() };

    // §17's "repo status unchanged" acceptance line, taken AFTER the live sessions rather than
    // before them. `receipt.source` is stamped while the receipt object is built — i.e. before
    // anything is spawned — so on its own it says nothing about what two frontier CLIs did with
    // this repo as their ConPTY cwd, which is the whole reason §17 asks (spec-auditor M-5).
    receipt.source_after = sourceIdentity();
    // CLEAN at both ends, not merely EQUAL at both ends (gate-validator MEDIUM-4) — and the rule
    // lives in the verdict module, where `node --test` can weaken it and see it go red.
    receipt.repo_unchanged_by_the_run = repoUnchangedByTheRun(receipt.source, receipt.source_after);
  } catch (e) {
    receipt.error = receipt.error || String((e && e.message) || e);
  } finally {
    // D-LOOP-1: no session this check started outlives it, whatever happened above, and every
    // durable terminal is quiesced BEFORE this function returns — a straggler release running after
    // the check has reported is a terminal the operator's next read would still see counted.
    try {
      const mgr = sessionManager();
      const pids = [];
      for (const paneId of started) {
        const rec = mgr && mgr.registry.get(paneId);
        if (rec && rec.pid) pids.push(rec.pid);
        try { killSession(paneId); } catch { /* already terminal */ }
        try { if (paneModel && paneModel().panes.has(paneId)) paneModel().destroyPane(paneId); }
        catch { /* pane already gone */ }
      }
      const dead = await waitFor(() => pids.every((p) => {
        try { process.kill(p, 0); return false; } catch { return true; }
      }), KILL_MS, 250);
      const quiesced = await waitFor(
        () => workerLauncher().heldSessions().length === 0, RELEASE_MS, 500);
      if (!dead || !quiesced) {
        // Belt to that braces: reclaim by the session key this check knows, so a hung release
        // cannot leave one of the operator's two OP-12 terminals counted for a dead session.
        for (const paneId of started) {
          const sid = workerLaunchState(paneId).sessionId;
          if (sid) { try { await releaseWorkerTerminal(sid, { cwd: REPO_ROOT, timeoutMs: EMITTER_MS }); } catch { /* reported below */ } }
        }
        receipt.error = receipt.error
          || `teardown did not quiesce (processes gone=${dead}, releases settled=${quiesced}) — `
          + "the durable terminal(s) were reclaimed by session key as a fallback";
      }
    } catch (e) {
      receipt.error = receipt.error || `teardown failed: ${String((e && e.message) || e)}`;
    }
    // Only what this check PLANTED is removed. Nothing the host already had was touched or read, so
    // there is nothing to put back — the restore path no longer holds any real value at all.
    for (const name of planted) delete process.env[name];
  }

  receipt.ok = receipt.error === null
    && receipt.supervision_ready && receipt.picker_sourced
    && !!(receipt.world && receipt.world.live === true)
    // EVERY OP-12 provider, not merely every one attempted: a receipt green on one provider while
    // the other was never authorized would report partial coverage as acceptance.
    && OP12_PROVIDERS.every((p) => receipt.legs[p] && receipt.legs[p].ok === true)
    // A consent-gated leg is skip-with-record and can never be one of the live ones. The conjunct
    // is redundant with the line above only while `leg.ok` stays honest — which is exactly the
    // thing a receipt should not have to assume about itself.
    && OP12_PROVIDERS.every((p) => receipt.legs[p] && receipt.legs[p].consent_outcome
      && receipt.legs[p].consent_outcome.ok === true && !receipt.legs[p].consent_gate)
    && receipt.providers_live.length === OP12_PROVIDERS.length
    && Number.isInteger(receipt.sessions_before)
    && receipt.sessions_after === receipt.sessions_before
    && !!(receipt.lease_zero && receipt.lease_zero.ok)
    && receipt.real_ledger_leases_empty === true
    && !!(receipt.node_log_chain && receipt.node_log_chain.ok)
    && Number.isInteger(receipt.node_log_rows_before)
    && Number.isInteger(receipt.node_log_rows_after)
    && receipt.node_log_rows_after > receipt.node_log_rows_before
    && !!(receipt.credential_scan && receipt.credential_scan.ok)
    && !!(receipt.owed_named && receipt.owed_named.ok)
    && !!(receipt.source && receipt.source.commit)
    && receipt.source.tracked_product_tree_clean === true
    && (receipt.source.unexpected_untracked_product_files || []).length === 0
    && !!(receipt.repo_unchanged_by_the_run && receipt.repo_unchanged_by_the_run.ok);

  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  // WHAT THIS RUN EVIDENCED, computed — never a template. The first live run's receipt described
  // the chain it was BUILT to measure in the past tense while `providers_live` was empty, so the
  // prose said a model had answered on a run where none had (found independently by both mandatory
  // reviewers). Every outcome sentence below is now derived from the legs.
  receipt.live_exchanges_spent = OP12_PROVIDERS
    .filter((p) => receipt.legs[p] && receipt.legs[p].submitted === true).length;
  const answered = receipt.providers_live.length
    ? `A LIVE ANSWER IS CLAIMED FOR: ${receipt.providers_live.join(", ")}.`
    : "NO LIVE ANSWER IS CLAIMED FOR EITHER PROVIDER ON THIS RUN.";
  const gatedNote = receipt.providers_consent_gated.length
    ? ` ${receipt.providers_consent_gated.join(", ")} stopped at the CLI's own directory-trust `
      + "modal (see `scope_note_consent_gate` and `operator_steps`) — everything BEFORE the typed "
      + "prompt is still measured and still claimed for them."
    : "";
  receipt.scope_note = "this is the LIVE OP-12 acceptance leg directive §17.2(1) asks for. The "
    + "chain it is built to measure, per provider, is: a real picker selection this host enumerated "
    + "from the provider's own CLI → a supervised ConPTY pane holding a durable I-X3 terminal on "
    + "that provider's own allowance-1 resource → a `node@1.1` Sovereign node record on the "
    + "OPERATOR's durable node log, moved to READY with the supervised pid → the exact provider and "
    + "model verified off the binary that was spawned and the model id the argv asked for → ONE "
    + "harmless falsifiable prompt typed through the RENDERER's own input path → a live answer read "
    + "back out of the xterm buffer → the session killed here, the terminal back at 0/1 read from a "
    + "separate process, and the node record closed on the same append-only log. A provider is only "
    + `claimed to have completed that chain if it is listed in \`providers_live\`. ${answered}`
    + `${gatedNote} What this leg does NOT claim even when green is in \`owed\`: the operator's own `
    + "first use, anything about a model's capability beyond one arithmetic token, the deliberately "
    + "unexercised same-provider concurrency refusal, U313's OP-6 pane records, the workspace-trust "
    + "consent that is the operator's alone, and the containment U25/U78(a) still owe.";
  receipt.scope_note_real_stores = "unlike every other live self-check in this build, this one does "
    + "NOT redirect the lease ledger to a scratch file, and it reads and writes the operator's real "
    + "node log. That is the leg, not an oversight: §17.2(1) asks for durable-ledger AND node-log "
    + "consistency, which is a statement about the operator's real I-X3 accounting. The two OP-12 "
    + "resources have allowance 1 each and no other LEASED session can hold them (the conductor "
    + "runs on claude_code), so this check cannot adopt or release a terminal a governed session "
    + "holds. What the ledger CANNOT see is a provider CLI the operator ran by hand — including the "
    + "`grok`/`agy` invocation `operator_steps` asks for, which takes no lease (U325); let that one "
    + "exit before re-running this check, or §17's no-simultaneous-same-provider-sessions line is "
    + "answered by an accounting that cannot see the other session. The ledger is asserted EMPTY at "
    + "the end rather than unchanged — it legitimately changed, twice, and 'unchanged' would have "
    + "been the wrong question.";
  receipt.scope_note_live_cost = `${receipt.live_exchanges_spent} live exchange(s) spent on this `
    + "run — counted from the legs that actually submitted a prompt, never from the plan. The "
    + "CEILING is one prompt and one answer per provider, which is the budget directive §17/§17.2 "
    + "sets and which the `.live.shape` unit overran and recorded as U312; a leg that stopped at a "
    + "consent gate submitted nothing and therefore cost nothing. The sessions run strictly "
    + "sequentially and each is killed before the next is asked for, so no two provider sessions "
    + "ever exist at once. On top of that "
    + "the run makes TOKEN-FREE metadata calls that leave this host (D-P18-7/U271): one picker "
    + "enumeration (`--version` + `models` for both CLIs) plus, inside each provider's governed "
    + "ticket, one further enumeration scoped to that provider alone (U290). No credential is read, "
    + "stored or transmitted at any point (§2.2) — both CLIs use their own host-native auth.";
  receipt.scope_note_consent_gate = "a leg listed in `providers_consent_gated` carries `ok:false` "
    + "and an `error`, and the §17 criterion it was to establish is UNMET — but not by anything the "
    + "product did: it stopped at the CLI's own directory-trust modal, which only the operator may "
    + "answer (invariant 1; operator directive §11's no-always-approve, no-unsandboxed-defaults "
    + "rule, and its line that a provider CLI's own always-approve setting is never operator "
    + "approval). No PERMITTED argv flag dismisses that modal — the two that might are the ones §11 "
    + "forbids, and neither was tried. It is recorded, not skipped silently, with the one-time "
    + "operator step named in `operator_steps`. Everything BEFORE the typed prompt is "
    + "still measured and still claimed for that provider — the governed picker spawn, the "
    + "supervised ConPTY pane, the exact provider+model, the durable I-X3 terminal seen from a "
    + "separate process, the `node@1.1` record's whole life on the operator's append-only log, the "
    + "§2.2 child-environment scrub and teardown to zero. What is NOT claimed is the live exchange "
    + "itself, and `ok` stays false while any of it is owed. The gated leg spends no live budget: "
    + "no prompt is pushed into a modal that reaches no model.";
  receipt.scope_note_credential_scan = "the sentinel scan in `credential_scan` covers FOUR sink "
    + "classes — the shell's durable main-process log, this receipt's payload, each pane's screen as "
    + "rendered at teardown, and the two DURABLE STORES this run writes into (the operator's node "
    + "event log and lease ledger, written by py children that inherit this process's environment); "
    + "`sinks_checked` lists every file by path. A FIFTH sink, each child's ENVIRONMENT, is measured "
    + "separately and reported per leg in `child_env`, by NAME rather than by value, because the "
    + "shell observes the child's env keys and never its values — which is also the only §2.2-safe "
    + "way to measure it. WHAT THE PANE SINK IS NOT (U324): grok and agy are full-screen TUIs on "
    + "xterm's ALTERNATE buffer, which keeps no scrollback, so that sink is the screen at teardown "
    + "and NOT the session's whole output — anything printed and then repainted over is outside it, "
    + "and no claim is made that it is covered. The payload is re-scanned immediately before it "
    + "is written, so fields added after the first scan are covered too, and a hit there refuses "
    + "the write outright: publishing the leak is worse than publishing nothing.";

  const payload = JSON.stringify(receipt, null, 2) + "\n";
  const finalScan = noCredentialMaterial({ "the receipt payload as written": payload }, plantedSentinels);
  if (!finalScan.ok) {
    receipt.ok = false;
    log(`[selfcheck] op12-live-acceptance REFUSED TO WRITE: ${finalScan.reasons.join("; ")}`);
    return receipt;
  }
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, payload);
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] op12-live-acceptance ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runOp12LiveAcceptanceSelfCheck: run, RECEIPT_PATH, OWED, PREFERRED_MODEL };
