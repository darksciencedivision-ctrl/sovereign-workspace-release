"use strict";
/**
 * APPROVAL-DRAWER read-source + decision router over the SESSION'S OWN events — Phase 17D `.events`.
 *
 * Phase 16D fed this drawer from a governed producer that built a canned plan and two canned commands
 * on every fetch, so the operator's first launch showed three pending approvals nobody had asked for
 * (finding F2). The read path is unchanged in shape — a BOUNDED one-shot `py -3.12` read-source, NOT
 * the WS-IPC channel — but both emitters now work over the session's OWN recorded approval events:
 *   - `sourceApprovalDrawerFeed` invokes `emit_approval_drawer.py --emit-approval-drawer [--events]`,
 *     which folds the log written by `approvals/session-events.js` through the real classifiers and
 *     prints `approval_drawer_feed@1.1`. No events ⇒ an EMPTY drawer. Main folds `feed.drawer` through
 *     the pure `buildApprovalDrawer` view the JS tests already cover.
 *   - `routeApprovalDecision` invokes `emit_approval_decision.py` over the SAME log and calls
 *     `ApprovalQueue.resolve` (operator-only, invariant 1; no override of a failed gate, invariant 16).
 *     The shell (Node) self-authorizes NOTHING — it forwards the operator's item id + decision, the
 *     Python authority resolves or refuses, and on a resolve it mints the `decision_event` the shell
 *     appends so the decision persists into every later rebuild.
 *
 * SUBSTITUTION (directive §6, recorded): a bounded subprocess emitter, not an authenticated IPC
 * surface — swapping the shell's EchoControlSurface gateway would displace the supervisor's liveness
 * path (a first-launch regression class D-P16-0 warns against). Identical to `.statusbar`.
 *
 * FAIL-CLOSED, by contract (invariant 3 / invariant 20 spirit): a timeout, a non-zero exit, non-JSON
 * output, or a malformed shape yields the UNAVAILABLE feed (`sourced:false`, empty drawer) — the shell
 * renders an honest "approvals unavailable", never a fabricated pending item. A GOVERNED refusal
 * emitted by Python (invariant 1/16) is a well-formed decision feed (`resolved:false, refused:true`)
 * surfaced as-is — also never faked. This module never throws into the always-visible chrome.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process, with
 * zero dependence on a live host (apps/desktop/test/approvals-drawer-source.test.js). Read-only glue:
 * no model call, no credential, no network here — the drawer it sources is itself mock-first.
 */
const { spawn: realSpawn } = require("child_process");
const crypto = require("crypto");

class ApprovalSourceError extends Error {}

/**
 * W-43 — PRODUCER AUTHENTICITY for approval decisions (U206).
 *
 * The decision producer and the drawer builder are two SEPARATE one-shot Python processes, so the
 * thing that distinguishes "minted by the trusted producer" from "written into the log by anything
 * that can write the log" has to be a secret they share and a log writer does not hold. This module
 * is the right owner of it: it is the one place that spawns BOTH.
 *
 * Minted once per shell process, which is exactly the lifetime of the log — `SessionApprovalLog`
 * `begin()` truncates it once per process. A decision cannot outlive the log it was recorded in, so
 * the key never needs to, and a stamp from a previous session can never verify in this one.
 *
 * Deliberately NOT in `process.env`: a key placed there would have to be scrubbed back out of every
 * pane, worker and conductor child environment, and would be one forgotten scrub away from leaking.
 * It lives in this module's memory and is handed to exactly two child processes, and it is applied
 * AFTER the `process.env` spread so an operator-set value of the same name cannot ride through.
 *
 * NOT a file beside the log: a key readable by whoever can write the log would authenticate the
 * forger too.
 */
const APPROVAL_DECISION_KEY_ENV = "SOW_APPROVAL_DECISION_KEY";
const SESSION_APPROVAL_DECISION_KEY = crypto.randomBytes(32).toString("hex");

/** The environment the approval emitters run with: this process's, plus the session key. */
function approvalEmitterEnv(baseEnv) {
  return { ...(baseEnv || process.env), [APPROVAL_DECISION_KEY_ENV]: SESSION_APPROVAL_DECISION_KEY };
}

const APPROVAL_DRAWER_FEED_SCHEMA = "approval_drawer_feed@1.1";
const APPROVAL_DECISION_FEED_SCHEMA = "approval_decision_feed@1.1";

// What the drawer still does NOT do, carried on every fail-closed feed so the shell never renders a
// promise the path has not kept (Phase 17D `.events`: a resolve now persists, its side effect does not).
const SIDE_EFFECTS_OWED = Object.freeze({
  owed: true,
  issue: "17E",
  note: "a resolved item persists and stops being pending; the downstream effect of an approve (broker execute / ObjectiveIntake assign) is not fired from this path.",
});

// The unavailable drawer feed — the fail-closed shape. NEVER a fabricated drawer (invariant 3):
// sourced:false, an empty drawer, the honest reason.
function unavailableApprovalFeed(reason = "approval drawer feed unavailable") {
  return {
    schema: APPROVAL_DRAWER_FEED_SCHEMA,
    sourced: false,
    source: "session_events",
    reason,
    event_count: 0,
    decision_count: 0,
    demo_items: false,
    drawer: { schema: "approval_drawer@1.0", badge_count: 0,
      kind_counts: { plan: 0, protected_action: 0, clarification: 0 }, pending: [] },
    badge_count: 0,
    kinds_present: [],
    side_effects_owed: { ...SIDE_EFFECTS_OWED },
    torn_down: true,
  };
}

// A payload is a usable drawer feed only if it carries the pinned schema and a `drawer` object with a
// `pending` array (the shape main folds through buildApprovalDrawer). Anything else is refused.
function isWellFormedDrawerFeed(f) {
  if (!f || typeof f !== "object" || f.schema !== APPROVAL_DRAWER_FEED_SCHEMA) return false;
  const d = f.drawer;
  return !!d && typeof d === "object" && !Array.isArray(d) && Array.isArray(d.pending);
}

// A decision feed is well-formed if it carries the pinned schema and a boolean `resolved`. A governed
// refusal (`resolved:false, refused:true, reason`) is well-formed and surfaced as-is.
function isWellFormedDecisionFeed(f) {
  return !!f && typeof f === "object" && f.schema === APPROVAL_DECISION_FEED_SCHEMA
    && typeof f.resolved === "boolean";
}

// Shared bounded-subprocess runner: spawn the emitter once, collect stdout, resolve the parsed feed
// or reject with ApprovalSourceError on timeout / non-zero exit / non-JSON / malformed shape.
function runEmitter({ spawn, python, pythonArgs, cwd, timeoutMs, args, wellFormed, label, env }) {
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(python, [...pythonArgs, ...args], { cwd, env });
    } catch (e) {
      reject(new ApprovalSourceError(`could not launch the ${label} emitter: ${e.message}`));
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (fn, arg) => { if (settled) return; settled = true; clearTimeout(to); try { child.kill(); } catch { /* gone */ } fn(arg); };
    const to = setTimeout(
      () => finish(reject, new ApprovalSourceError(`${label} emit timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish(reject, new ApprovalSourceError(`${label} emitter failed to run: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new ApprovalSourceError(`${label} emitter exited ${code}${err ? `: ${err.trim().slice(0, 200)}` : ""}`));
        return;
      }
      let parsed;
      try { parsed = JSON.parse(out); }
      catch (e) { finish(reject, new ApprovalSourceError(`${label} emitter emitted non-JSON: ${e.message}`)); return; }
      if (!wellFormed(parsed)) {
        finish(reject, new ApprovalSourceError(`${label} emitter emitted a malformed feed`));
        return;
      }
      finish(resolve, parsed);
    });
  });
}

/**
 * Run `--emit-approval-drawer` once and return the parsed feed. STRICT: throws ApprovalSourceError on
 * timeout / non-zero exit / non-JSON / malformed shape.
 * @param {object} opts {spawn?, python?, pythonArgs?, cwd, timeoutMs?}
 * @returns {Promise<object>} the drawer feed dict
 */
function fetchApprovalDrawerFeed(opts = {}) {
  return runEmitter({
    spawn: opts.spawn || realSpawn,
    python: opts.python || "py",
    pythonArgs: opts.pythonArgs || ["-3.12"],
    cwd: opts.cwd,
    // Phase 17D `.events`: folding a recorded log starts no MCP server and no flow, so the budget is
    // a Python interpreter start rather than a governed run — but it stays generous because a cold
    // `py -3.12` on a loaded host is not fast, and a timeout here means an empty drawer.
    timeoutMs: opts.timeoutMs || 40000,
    args: ["tools/live/emit_approval_drawer.py", "--emit-approval-drawer",
      ...(opts.eventsPath ? ["--events", opts.eventsPath] : [])],
    wellFormed: isWellFormedDrawerFeed,
    label: "approval-drawer",
    // W-43: the VERIFY half of the session key. The builder needs it to tell a producer-minted
    // decision from one somebody appended to the log.
    env: approvalEmitterEnv(opts.env),
  });
}

/**
 * DISPLAY contract: NEVER throws. Returns {ok:true, feed} on a well-formed drawer feed, else
 * {ok:false, error, feed: unavailableApprovalFeed()} so main always has a shape to fold — fail-closed,
 * no fabricated drawer.
 */
async function sourceApprovalDrawerFeed(opts = {}) {
  try {
    const feed = await fetchApprovalDrawerFeed(opts);
    // A well-formed feed that SAYS it is not sourced is not a drawer — it is Python reporting that
    // the log could not be re-derived in full (a corrupt line, a classification mismatch, a decision
    // the authority refuses, and since W-43 a decision no trusted producer minted). `ok` is the flag
    // main.js folds into `sourced` and into whether it shows the operator an error at all, so
    // answering `ok:true` here rendered every one of those as a successfully-sourced EMPTY drawer —
    // the honest reason Python computed never reached the chrome, and an emptied drawer is exactly
    // what a forged decision was trying to produce. Registered separately: the defect predates W-43
    // and covers every unavailable feed, not only the authenticity one.
    if (feed.sourced !== true) {
      const reason = typeof feed.reason === "string" && feed.reason ? feed.reason : "approval drawer could not be re-derived";
      return { ok: false, error: `ApprovalSourceError: ${reason}`, feed };
    }
    return { ok: true, feed };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}`, feed: unavailableApprovalFeed(`${e.name || "Error"}: ${e.message}`) };
  }
}

/**
 * Route the operator's decide through the governed authority. Runs `--emit-approval-decision` with the
 * operator's item id + decision; the Python `ApprovalQueue.resolve` decides (invariant 1/16). NEVER
 * throws. Returns {ok:true, feed} for a well-formed decision feed (which may itself be a governed
 * refusal, `feed.resolved === false`), else {ok:false, error}.
 * @param {object} opts {spawn?, python?, pythonArgs?, cwd, timeoutMs?, itemId, decision, reason?}
 */
async function routeApprovalDecision(opts = {}) {
  const itemId = typeof opts.itemId === "string" ? opts.itemId : "";
  const decision = opts.decision === "approve" || opts.decision === "reject" ? opts.decision : "";
  // The shell forwards intent; it does NOT self-authorize. A malformed decision never reaches Python
  // as an approve/reject — fail closed here (still not a decision the shell made about authority).
  if (!itemId || !decision) {
    return { ok: false, error: "a decision needs an item id and decision=approve|reject" };
  }
  const args = ["tools/live/emit_approval_decision.py", "--emit-approval-decision",
    "--item", itemId, "--decision", decision];
  if (typeof opts.reason === "string" && opts.reason.trim()) args.push("--reason", opts.reason);
  // the SAME recorded log the drawer was folded from — the authority resolves over the queue the
  // operator was actually looking at, not over a queue this process built for the occasion.
  if (opts.eventsPath) args.push("--events", opts.eventsPath);
  try {
    const feed = await runEmitter({
      spawn: opts.spawn || realSpawn,
      python: opts.python || "py",
      pythonArgs: opts.pythonArgs || ["-3.12"],
      cwd: opts.cwd,
      timeoutMs: opts.timeoutMs || 40000,
      args,
      wellFormed: isWellFormedDecisionFeed,
      label: "approval-decision",
      // W-43: the MINT half of the same key. Both emitters get it from one place, so they cannot
      // drift apart — a producer stamping under a key the builder does not hold would fail every
      // genuine decision closed, which is the failure mode of splitting this in two.
      env: approvalEmitterEnv(opts.env),
    });
    return { ok: true, feed };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}` };
  }
}

module.exports = {
  ApprovalSourceError,
  APPROVAL_DRAWER_FEED_SCHEMA,
  APPROVAL_DECISION_FEED_SCHEMA,
  APPROVAL_DECISION_KEY_ENV,
  SESSION_APPROVAL_DECISION_KEY,
  approvalEmitterEnv,
  SIDE_EFFECTS_OWED,
  unavailableApprovalFeed,
  isWellFormedDrawerFeed,
  isWellFormedDecisionFeed,
  fetchApprovalDrawerFeed,
  sourceApprovalDrawerFeed,
  routeApprovalDecision,
};
