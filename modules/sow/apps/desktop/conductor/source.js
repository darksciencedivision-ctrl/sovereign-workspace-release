"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * CONDUCTOR selection data SOURCE (Phase 16C `.selection`; closes U65).
 *
 * The conductor SELECTION + succession affordance are held by ONE Python authority
 * (`control_plane/conductor/selection.OPERATOR_SELECTED_CONDUCTOR` +
 * `node_runtime/supervisor/conductor_pane_spawn.conductor_succession_affordance`), emitted as a stable
 * JSON contract by `tools/live/emit_conductor_selection.py --emit-conductor-selection`. This module
 * invokes that emitter as a BOUNDED one-shot subprocess (the same `py -3.12` the shell already uses
 * for the IPC gateway + the 16B picker), parses the feed, and hands it to the renderer. The shell
 * NEVER keeps a hand-maintained copy of the selection — it renders exactly what Python holds, so the
 * badge can no longer drift from the operator's authority (the exact risk U65 flagged). This mirrors
 * `apps/desktop/picker/source.js` (the 16B read-source pattern). Read-only: no model call, no
 * credential, no network (§2.2/§2.4).
 *
 * FAIL-CLOSED, by contract (invariant 3): a timeout, a non-zero exit, non-JSON output, or a payload
 * missing `selection_record`/`succession` yields the UNKNOWN feed — a selection whose model is null,
 * which the pure badge (`terminal/compositor/conductor-pane.conductorBadge`) renders as
 * "(unknown selection)" and whose succession renders unavailable. The shell shows an honest "unknown"
 * rather than fabricating "fable-5" it could not source. This is STRICTLY more honest than the prior
 * literal, which always claimed fable-5 even if Python disagreed.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process,
 * with zero dependence on a live host (apps/desktop/test/conductor-source.test.js).
 */
const { spawn: realSpawn } = require("child_process");

class ConductorSourceError extends Error {}

const CONDUCTOR_SELECTION_FEED_SCHEMA = "conductor_selection_feed@1.0";

// The unknown feed — the fail-closed shape. A null selection model renders as "(unknown selection)"
// via conductorBadge; a null succession renders unavailable via conductorSuccessionControl. NEVER a
// fabricated model (invariant 3 / invariant 20 air-gap-honesty spirit: absent is reported as absent).
function unknownSelectionFeed() {
  return {
    schema: CONDUCTOR_SELECTION_FEED_SCHEMA,
    selection_record: {
      selection: { model: null },
      executing: { model: null, verified: false, is_fallback: false },
    },
    succession: null,
  };
}

// A payload is a usable feed only if it carries the sub-records the renderer folds over. Anything
// else (a stray log line, a truncated read, a shape drift) is refused — fail closed.
function isWellFormedFeed(f) {
  return !!f
    && !!f.selection_record && typeof f.selection_record === "object"
    && !!f.selection_record.selection && typeof f.selection_record.selection === "object"
    && !!f.selection_record.executing && typeof f.selection_record.executing === "object"
    && !!f.succession && typeof f.succession === "object";
}

/**
 * Run the `--emit-conductor-selection` emitter once and return the parsed feed. STRICT: throws
 * ConductorSourceError on timeout / non-zero exit / non-JSON / malformed shape.
 * @param {object} opts
 * @param {function} [opts.spawn]      child_process.spawn (injected in tests)
 * @param {string}   [opts.python]     interpreter (default resolved by python-runtime.js)
 * @param {string[]} [opts.pythonArgs] leading args (default ["-3.12"])
 * @param {string}   opts.cwd          repo root (so the tool's sys.path/imports resolve)
 * @param {number}   [opts.timeoutMs]  hard bound (default 20000)
 * @returns {Promise<object>} the feed dict
 */
function fetchConductorFeed(opts = {}) {
  const spawn = opts.spawn || realSpawn;
  const python = opts.python || defaultPython();
  const pythonArgs = opts.pythonArgs || defaultPythonArgs();
  const cwd = opts.cwd;
  const timeoutMs = opts.timeoutMs || 20000;
  const args = [...pythonArgs, "tools/live/emit_conductor_selection.py", "--emit-conductor-selection"];

  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(python, args, { cwd });
    } catch (e) {
      reject(new ConductorSourceError(`could not launch the conductor-selection emitter: ${e.message}`));
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (fn, arg) => { if (settled) return; settled = true; clearTimeout(to); try { child.kill(); } catch { /* gone */ } fn(arg); };
    const to = setTimeout(
      () => finish(reject, new ConductorSourceError(`conductor-selection emitter timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish(reject, new ConductorSourceError(`conductor-selection emitter failed to run: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new ConductorSourceError(`conductor-selection emitter exited ${code}${err ? `: ${err.trim().slice(0, 200)}` : ""}`));
        return;
      }
      let parsed;
      try { parsed = JSON.parse(out); }
      catch (e) { finish(reject, new ConductorSourceError(`conductor-selection emitter emitted non-JSON: ${e.message}`)); return; }
      if (!isWellFormedFeed(parsed)) {
        finish(reject, new ConductorSourceError("conductor-selection emitter emitted a malformed feed (missing selection_record/succession)"));
        return;
      }
      finish(resolve, parsed);
    });
  });
}

/**
 * DISPLAY contract: NEVER throws. Returns {ok:true, feed} on success, else {ok:false, error,
 * feed: unknownSelectionFeed()} so the renderer always has a shape to fold — fail-closed, no
 * fabricated selection. The badge renders "(unknown selection)" honestly on any fault.
 */
async function fetchConductorSelectionFeed(opts = {}) {
  try {
    const feed = await fetchConductorFeed(opts);
    return { ok: true, feed };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}`, feed: unknownSelectionFeed() };
  }
}

/** Validate and persist one operator-selected registered conductor descriptor. Never throws. */
function selectConductorPreference(selection, opts = {}) {
  const spawn = opts.spawn || realSpawn;
  const python = opts.python || defaultPython();
  const args = [...(opts.pythonArgs || defaultPythonArgs()), "tools/live/select_conductor.py", "--select-stdin"];
  return new Promise((resolve) => {
    let child;
    try { child = spawn(python, args, { cwd: opts.cwd }); }
    catch (e) { resolve({ ok: false, error: `${e.name || "Error"}: ${e.message}` }); return; }
    let out = ""; let err = ""; let settled = false;
    const finish = (value) => { if (settled) return; settled = true; clearTimeout(to); resolve(value); };
    const to = setTimeout(() => { try { child.kill(); } catch { /* gone */ }
      finish({ ok: false, error: "conductor selection timed out" }); }, opts.timeoutMs || 20000);
    child.stdout.on("data", (d) => { out += d.toString(); });
    child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish({ ok: false, error: `${e.name || "Error"}: ${e.message}` }));
    child.on("exit", (code) => {
      if (code !== 0) { finish({ ok: false, error: `selector exited ${code}: ${err.trim()}` }); return; }
      try { finish(JSON.parse(out)); }
      catch (e) { finish({ ok: false, error: `selector emitted non-JSON: ${e.message}` }); }
    });
    child.stdin.end(JSON.stringify(selection || {}));
  });
}

module.exports = {
  ConductorSourceError,
  CONDUCTOR_SELECTION_FEED_SCHEMA,
  fetchConductorFeed,
  fetchConductorSelectionFeed,
  unknownSelectionFeed,
  isWellFormedFeed,
  selectConductorPreference,
};
