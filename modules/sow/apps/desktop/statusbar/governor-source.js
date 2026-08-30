"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * Subscription-concurrency status-bar GOVERNOR read-source — Phase 16D `.statusbar`.
 *
 * The operator saw the shipped shell's status bar report "concurrency count unavailable
 * (fail-closed)": the always-visible n/2 bar reads the `subscription_status` IPC op, but the gateway
 * the running shell spawns (`EchoControlSurface`) does not expose it. This module closes that gap the
 * SAME way the 16B picker and 16C conductor feeds closed theirs — a BOUNDED one-shot `py -3.12`
 * read-source (`tools/live/emit_subscription_status.py --emit-subscription-status`), NOT the WS-IPC
 * channel — that builds the REAL `SubscriptionGovernor` seeded from the enforced `LiveAuthorization`
 * and prints its `status()`. This module invokes it, parses the one JSON line, and folds the governor
 * status through the SAME pure view model the tested IPC path uses
 * (`terminal/statusbar/statusbar-model`), so the bar renders a readable n/allowance count.
 *
 * SUBSTITUTION (directive §6, recorded): a bounded subprocess emitter, not the authenticated
 * `SubscriptionStatusControlSurface` over IPC. That surface stays the design endpoint for a
 * long-lived governor-backed gateway; swapping the shell's gateway surface would displace the
 * supervisor's `health`/`session_event` liveness path (a first-launch regression class D-P16-0
 * warns against), so `.statusbar` uses the proven isolated read-source. Identical to `picker:` /
 * the conductor feeds.
 *
 * FAIL-CLOSED, by contract: a timeout, a non-zero exit, non-JSON output, a shape drift, or an
 * `authorized:false` / `status:null` feed yields the UNKNOWN status-bar model
 * (`buildStatusBarModel({status:null})` → an em-dash `—/allowance` row PER PROVIDER — `—/2` for the
 * OP-6 pair, `—/1` for the OP-12 pair since U255 — with `readable:false`) carrying `.error` — never a
 * fabricated `0/2`. The status bar is not load-bearing for supervision, so a fault degrades the bar
 * to the honest unknown, it never throws into the renderer.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process,
 * with zero dependence on a live host (apps/desktop/test/statusbar-governor-source.test.js).
 *
 * Read-only: the emitter performs no model call and touches no credential (§2.2/§2.4) — it reads the
 * fail-closed LiveAuthorization gate and builds an in-memory governor.
 */
const { spawn: realSpawn } = require("child_process");
const { buildStatusBarModel, summarizeStatusBar } = require("../../../terminal/statusbar/statusbar-model");

const FEED_SCHEMA = "subscription_status_feed@1.0";

class GovernorStatusSourceError extends Error {}

// A payload is a usable governor feed only if it is the pinned schema and carries either a readable
// `status` object or an explicit `status:null` (the fail-closed unknown). Anything else (a stray log
// line, a truncated read, a producer drift) is refused — fail closed.
function isWellFormedFeed(f) {
  if (!f || typeof f !== "object" || f.schema !== FEED_SCHEMA) return false;
  const s = f.status;
  return s === null || (s !== undefined && typeof s === "object" && !Array.isArray(s));
}

/**
 * Run `--emit-subscription-status` once and return the parsed feed. STRICT: throws
 * GovernorStatusSourceError on timeout / non-zero exit / non-JSON / malformed shape.
 * @param {object} opts
 * @param {function} [opts.spawn]      child_process.spawn (injected in tests)
 * @param {string}   [opts.python]     interpreter (default resolved by python-runtime.js)
 * @param {string[]} [opts.pythonArgs] leading args (default ["-3.12"])
 * @param {string}   opts.cwd          repo root (so the tool's sys.path/imports resolve)
 * @param {number}   [opts.timeoutMs]  hard bound (default 20000)
 * @returns {Promise<object>} the feed dict
 */
function fetchGovernorStatusFeed(opts = {}) {
  const spawn = opts.spawn || realSpawn;
  const python = opts.python || defaultPython();
  const pythonArgs = opts.pythonArgs || defaultPythonArgs();
  const cwd = opts.cwd;
  const timeoutMs = opts.timeoutMs || 20000;
  const args = [...pythonArgs, "tools/live/emit_subscription_status.py", "--emit-subscription-status"];

  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(python, args, { cwd });
    } catch (e) {
      reject(new GovernorStatusSourceError(`could not launch the subscription-status emitter: ${e.message}`));
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (fn, arg) => { if (settled) return; settled = true; clearTimeout(to); try { child.kill(); } catch { /* gone */ } fn(arg); };
    const to = setTimeout(
      () => finish(reject, new GovernorStatusSourceError(`subscription-status emit timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish(reject, new GovernorStatusSourceError(`subscription-status emitter failed to run: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new GovernorStatusSourceError(`subscription-status emitter exited ${code}${err ? `: ${err.trim().slice(0, 200)}` : ""}`));
        return;
      }
      let parsed;
      try { parsed = JSON.parse(out); }
      catch (e) { finish(reject, new GovernorStatusSourceError(`subscription-status emitter emitted non-JSON: ${e.message}`)); return; }
      if (!isWellFormedFeed(parsed)) {
        finish(reject, new GovernorStatusSourceError("subscription-status emitter emitted a malformed feed (missing schema/status)"));
        return;
      }
      finish(resolve, parsed);
    });
  });
}

/**
 * DISPLAY contract: NEVER throws. Returns the folded status-bar model + summary, plus a `source`
 * marker and the feed's `authorized` flag. On any fault (or an `authorized:false`/`status:null` feed)
 * it returns the fail-closed unknown model (em-dash rows, `readable:false`) carrying `.error` — so the
 * always-visible bar renders honestly rather than a fabricated count.
 * @returns {{readable, cap, providers, rows, summary, source, feedAuthorized, error?}}
 */
async function fetchStatusBarModelFromGovernor(opts = {}) {
  try {
    const feed = await fetchGovernorStatusFeed(opts);
    // The feed's OWN per-provider allowance goes with the status: it is what the emitter computed
    // from the operator's live authorization, so a narrowed config narrows the bar. Dropping it was
    // U255's residue — the ceiling was supposed to be SOURCED from the feed (spec-audit Md-4).
    const model = buildStatusBarModel({ status: feed.status,             // status:null ⇒ unknown
      allowanceByProvider: feed.allowance_by_provider || null });
    const out = { ...model, summary: summarizeStatusBar(model), source: "emitter", feedAuthorized: !!feed.authorized };
    if (!feed.authorized) out.error = feed.reason || "live operation not authorized (fail-closed)";
    return out;
  } catch (e) {
    const model = buildStatusBarModel({ status: null });
    return {
      ...model,
      summary: summarizeStatusBar(model),
      source: "emitter",
      feedAuthorized: false,
      error: `${e.name || "Error"}: ${e.message}`,
    };
  }
}

module.exports = {
  FEED_SCHEMA,
  GovernorStatusSourceError,
  isWellFormedFeed,
  fetchGovernorStatusFeed,
  fetchStatusBarModelFromGovernor,
};
