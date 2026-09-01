"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * CONDUCTOR governed-dispatch SOURCE (Phase 16C `.dispatch`; closes U58 as far as evidence allows).
 *
 * The govern-born conductor pane (`.spawn`) dispatches work to worker nodes over MCP and synthesizes
 * their gated results (OP-8 §13.4). `tools/live/emit_conductor_dispatch.py --emit-conductor-dispatch`
 * runs ONE governed dispatch through the REAL live_flow loop (decompose → assign BY DESCRIPTOR →
 * CANDIDATE over MCP → real gate engine → conductor synthesis) MOCK-first (no live model call), tears
 * the loopback MCP server down (D-LOOP-1), and prints the folded `conductor_dispatch_feed@1.0` JSON.
 * This module invokes that emitter as a BOUNDED one-shot subprocess (the same `py -3.12` the shell uses
 * for the IPC gateway, the 16B picker, and the 16C `.selection`/`.spawn` feeds), parses the feed, and
 * hands it to main so the conductor chrome's dispatch line is SOURCED from Python, never a literal.
 * Mirrors `apps/desktop/conductor/spawn-source.js`. Read-only glue: no model call, no credential, no
 * network here — the dispatch it sources is itself mock-first, so the shell makes no live call either.
 *
 * FAIL-CLOSED, by contract (invariant 3 / invariant 20 spirit): a timeout, a non-zero exit, non-JSON
 * output, or a malformed shape yields the UNAVAILABLE feed — `dispatched:false`, no assignments. The
 * shell shows an honest "dispatch unavailable" rather than fabricating a dispatch. A governed
 * NON-dispatch emitted by Python (e.g. a plan-gate block) is a well-formed feed with `dispatched:false`
 * and a `reason` — surfaced as-is, also never a fabricated dispatch.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process, with
 * zero dependence on a live host (apps/desktop/test/conductor-dispatch-source.test.js).
 */
const { spawn: realSpawn } = require("child_process");

class ConductorDispatchSourceError extends Error {}

const CONDUCTOR_DISPATCH_FEED_SCHEMA = "conductor_dispatch_feed@1.0";

// The U58 record the fail-closed feed still carries — the live-worker leg is owed regardless of
// whether this launch could source a dispatch (never dropped, so the shell always states the truth).
const LIVE_WORKERS_OWED = Object.freeze({
  owed: true,
  issue: "U58",
  note: "this launch's dispatch is mock-first; a LIVE worker leg exists only when one is asked for "
    + "(--live-workers) and is evidenced by 17B `.legs` and the 17E fully-live receipt. What remains "
    + "owed under U58 is narrower: the live conductor CLI does not itself CHOOSE to delegate.",
});

// The unavailable feed — the fail-closed shape when the emitter cannot be reached/parsed. NEVER a
// fabricated dispatch (invariant 3): dispatched:false, no assignments, the honest reason.
function unavailableDispatchFeed() {
  return {
    schema: CONDUCTOR_DISPATCH_FEED_SCHEMA,
    dispatched: false,
    reason: "conductor dispatch feed unavailable",
    objective: null,
    assignments: [],
    assigned_count: 0,
    by_descriptor: false,
    queued_count: 0,
    failed_count: 0,
    accepted_count: 0,
    acceptance_packet: null,
    acceptance_verdict: null,
    operator_disposition: null,
    legs: { conductor: "skipped", workers: "skipped" },
    gate_summary: null,
    synthesized_by: null,
    live_workers_owed: { ...LIVE_WORKERS_OWED },
    ts: null,
    torn_down: true,
  };
}

// A payload is a usable feed only if it carries the pinned schema and a boolean `dispatched`, and —
// when it claims a dispatch — the assignment list + the legs the renderer folds. A governed
// NON-dispatch (dispatched:false) is well-formed with a reason string. Anything else is refused.
function isWellFormedDispatchFeed(f) {
  if (!f || typeof f !== "object") return false;
  if (f.schema !== CONDUCTOR_DISPATCH_FEED_SCHEMA) return false;
  if (typeof f.dispatched !== "boolean") return false;
  if (f.dispatched) {
    return Array.isArray(f.assignments) && f.assignments.length > 0
      && !!f.legs && typeof f.legs === "object"
      && typeof f.accepted_count === "number";
  }
  // a non-dispatch must say why (never a silent empty dispatch)
  return typeof f.reason === "string" && f.reason.length > 0;
}

/**
 * Run the `--emit-conductor-dispatch` emitter once and return the parsed feed. STRICT: throws
 * ConductorDispatchSourceError on timeout / non-zero exit / non-JSON / malformed shape.
 * @param {object} opts
 * @param {function} [opts.spawn]      child_process.spawn (injected in tests)
 * @param {string}   [opts.python]     interpreter (default resolved by python-runtime.js)
 * @param {string[]} [opts.pythonArgs] leading args (default ["-3.12"])
 * @param {string}   opts.cwd          repo root (so the tool's sys.path/imports resolve)
 * @param {boolean}  [opts.liveWorkers] Phase 17E: ask the emitter for a governed LIVE worker
 *   (`--live-workers`). SPENDS one live exchange, so it is opt-in and no launch path passes it —
 *   `apps/desktop/test/conductor-dispatch-live-workers.test.js` is the guard on that.
 * @param {number}   [opts.timeoutMs]  hard bound (default 40000 mock / 900000 live — a live dispatch
 *   spins an MCP server AND waits on a real model; 17B `.legs` measured 277 s on this host)
 * @returns {Promise<object>} the feed dict
 */
function fetchConductorDispatchFeed(opts = {}) {
  const spawn = opts.spawn || realSpawn;
  const python = opts.python || defaultPython();
  const pythonArgs = opts.pythonArgs || defaultPythonArgs();
  const cwd = opts.cwd;
  const liveWorkers = opts.liveWorkers === true;
  // The OPERATOR'S objective, when he has given one. Absent, the emitter keeps its replayable smoke
  // objective and this path is byte-for-byte what it was.
  const objective = typeof opts.objective === "string" && opts.objective.trim()
    ? opts.objective.trim() : null;
  const timeoutMs = opts.timeoutMs || (liveWorkers ? 900000 : 40000);
  const args = [...pythonArgs, "tools/live/emit_conductor_dispatch.py", "--emit-conductor-dispatch"];
  if (liveWorkers) args.push("--live-workers");
  // OVER STDIN, NEVER ARGV. The objective is operator-authored free text of arbitrary length and
  // content, and a process argument list is the wrong place for it — the hazard W-01 names and the
  // reason `select_conductor.py` reads its selection from a pipe. The flag only says a payload is
  // coming; the payload itself never touches the command line.
  if (objective) args.push("--objective-stdin");

  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(python, args, { cwd });
    } catch (e) {
      reject(new ConductorDispatchSourceError(`could not launch the conductor-dispatch emitter: ${e.message}`));
      return;
    }
    if (objective) {
      // Written and closed immediately: the emitter reads to EOF, so an unclosed pipe would hang
      // it until the timeout above rather than failing.
      try {
        child.stdin.write(JSON.stringify({ objective }));
        child.stdin.end();
      } catch (e) {
        reject(new ConductorDispatchSourceError(
          `could not send the objective to the conductor-dispatch emitter: ${e.message}`));
        return;
      }
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (fn, arg) => { if (settled) return; settled = true; clearTimeout(to); try { child.kill(); } catch { /* gone */ } fn(arg); };
    const to = setTimeout(
      () => finish(reject, new ConductorDispatchSourceError(`conductor-dispatch emitter timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish(reject, new ConductorDispatchSourceError(`conductor-dispatch emitter failed to run: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new ConductorDispatchSourceError(`conductor-dispatch emitter exited ${code}${err ? `: ${err.trim().slice(0, 200)}` : ""}`));
        return;
      }
      let parsed;
      try { parsed = JSON.parse(out); }
      catch (e) { finish(reject, new ConductorDispatchSourceError(`conductor-dispatch emitter emitted non-JSON: ${e.message}`)); return; }
      if (!isWellFormedDispatchFeed(parsed)) {
        finish(reject, new ConductorDispatchSourceError("conductor-dispatch emitter emitted a malformed feed"));
        return;
      }
      finish(resolve, parsed);
    });
  });
}

/**
 * DISPLAY contract: NEVER throws. Returns {ok:true, feed} on success, else {ok:false, error, feed:
 * unavailableDispatchFeed()} so the renderer/main always has a shape to fold — fail-closed, no
 * fabricated dispatch. Note ok:true simply means a well-formed feed was parsed; that feed may itself
 * be a governed NON-dispatch (feed.dispatched === false) — the caller reads feed.dispatched.
 */
async function sourceConductorDispatchFeed(opts = {}) {
  // (`liveWorkers` rides through untouched — the display contract is the same either way: a live
  //  dispatch that times out or fails is the honest unavailable feed, never a fabricated live leg.)
  try {
    const feed = await fetchConductorDispatchFeed(opts);
    return { ok: true, feed };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}`, feed: unavailableDispatchFeed() };
  }
}

module.exports = {
  ConductorDispatchSourceError,
  CONDUCTOR_DISPATCH_FEED_SCHEMA,
  fetchConductorDispatchFeed,
  sourceConductorDispatchFeed,
  unavailableDispatchFeed,
  isWellFormedDispatchFeed,
};
