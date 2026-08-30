"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * CONDUCTOR governed-spawn SOURCE (Phase 16C `.spawn`).
 *
 * On launch the shell's pane 1 (the conductor-first CONDUCTOR node, §12.4) is GOVERNED-BORN through
 * the Python `node_runtime/supervisor/conductor_pane_spawn.spawn_conductor_pane` — the full live-gate
 * chain (LIVE_OPERATION_AUTHORIZED + provider-live + R8 §6 operator terms + `claude` CLI presence +
 * the I-X3 SubscriptionGovernor), exactly as a live worker pane. `tools/live/emit_conductor_spawn.py
 * --emit-conductor-spawn` runs that governed spawn (with NO launcher ⇒ the interactive `claude`
 * ConPTY drive is deferred to the operator-run shell, §6), tears the I-X3 terminal down (D-LOOP-1),
 * and prints the result as a stable JSON contract (`conductor_spawn_feed@1.0`). This module invokes
 * that emitter as a BOUNDED one-shot subprocess (the same `py -3.12` the shell uses for the IPC
 * gateway, the 16B picker, and the 16C `.selection` badge), parses the feed, and hands it to main so
 * pane 1's `node_state` + governed-birth is SOURCED from Python, not a hardcoded string. Mirrors
 * `apps/desktop/conductor/source.js`. Read-only glue: no model call, no credential, no network here.
 *
 * FAIL-CLOSED, by contract (invariant 3 / invariant 20 spirit): a timeout, a non-zero exit, non-JSON
 * output, or a malformed shape yields the UNAVAILABLE feed — `spawned:false`, `node_state:"unstarted"`,
 * no chrome. The shell still shows the conductor-first placeholder (no naked session, invariant 2) but
 * honestly reports it was NOT governed-born this launch, rather than fabricating a governed spawn. A
 * governed REFUSAL emitted by Python (e.g. live not authorized) is a well-formed feed with
 * `spawned:false, refused:true, reason` — surfaced as-is, also never a fabricated spawn.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process, with
 * zero dependence on a live host (apps/desktop/test/conductor-spawn-source.test.js).
 */
const { spawn: realSpawn } = require("child_process");

class ConductorSpawnSourceError extends Error {}

const CONDUCTOR_SPAWN_FEED_SCHEMA = "conductor_spawn_feed@1.0";

// The unavailable feed — the fail-closed shape when the emitter cannot be reached/parsed. NOT a
// refusal (which Python emits with refused:true): the shell could not source a governed spawn at all,
// so pane 1 is an honest un-governed-live placeholder. NEVER a fabricated governed birth (invariant 3).
function unavailableSpawnFeed() {
  return {
    schema: CONDUCTOR_SPAWN_FEED_SCHEMA,
    spawned: false,
    refused: false,
    reason: "conductor spawn feed unavailable",
    node_state: "unstarted",
    launched: false,
    chrome: null,
    launch: null,
    selection_record: null,
    torn_down: false,
    governor_released: true, // nothing was acquired, so nothing leaked
    live_authorized: false,
    cli_present: false,
  };
}

// A payload is a usable feed only if it carries the pinned schema and a boolean `spawned`, and — when
// it claims a spawn — the governed chrome + launch the renderer folds. A governed REFUSAL
// (spawned:false) is well-formed without chrome. Anything else (a stray log line, a shape drift) is
// refused — fail closed.
function isWellFormedSpawnFeed(f) {
  if (!f || typeof f !== "object") return false;
  if (f.schema !== CONDUCTOR_SPAWN_FEED_SCHEMA) return false;
  if (typeof f.spawned !== "boolean") return false;
  if (f.spawned) {
    return !!f.chrome && typeof f.chrome === "object"
      && !!f.launch && typeof f.launch === "object"
      && typeof f.node_state === "string" && f.node_state.length > 0;
  }
  // a refusal: must say so and give a reason (never a silent empty spawn)
  return f.refused === true && typeof f.reason === "string" && f.reason.length > 0;
}

/**
 * Run the `--emit-conductor-spawn` emitter once and return the parsed feed. STRICT: throws
 * ConductorSpawnSourceError on timeout / non-zero exit / non-JSON / malformed shape.
 * @param {object} opts
 * @param {function} [opts.spawn]      child_process.spawn (injected in tests)
 * @param {string}   [opts.python]     interpreter (default resolved by python-runtime.js)
 * @param {string[]} [opts.pythonArgs] leading args (default ["-3.12"])
 * @param {string}   opts.cwd          repo root (so the tool's sys.path/imports resolve)
 * @param {number}   [opts.timeoutMs]  hard bound (default 25000 — a governed spawn touches more than a read)
 * @returns {Promise<object>} the feed dict
 */
function fetchConductorSpawnFeed(opts = {}) {
  const spawn = opts.spawn || realSpawn;
  const python = opts.python || defaultPython();
  const pythonArgs = opts.pythonArgs || defaultPythonArgs();
  const cwd = opts.cwd;
  const timeoutMs = opts.timeoutMs || 25000;
  const args = [...pythonArgs, "tools/live/emit_conductor_spawn.py", "--emit-conductor-spawn"];

  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(python, args, { cwd });
    } catch (e) {
      reject(new ConductorSpawnSourceError(`could not launch the conductor-spawn emitter: ${e.message}`));
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (fn, arg) => { if (settled) return; settled = true; clearTimeout(to); try { child.kill(); } catch { /* gone */ } fn(arg); };
    const to = setTimeout(
      () => finish(reject, new ConductorSpawnSourceError(`conductor-spawn emitter timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish(reject, new ConductorSpawnSourceError(`conductor-spawn emitter failed to run: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new ConductorSpawnSourceError(`conductor-spawn emitter exited ${code}${err ? `: ${err.trim().slice(0, 200)}` : ""}`));
        return;
      }
      let parsed;
      try { parsed = JSON.parse(out); }
      catch (e) { finish(reject, new ConductorSpawnSourceError(`conductor-spawn emitter emitted non-JSON: ${e.message}`)); return; }
      if (!isWellFormedSpawnFeed(parsed)) {
        finish(reject, new ConductorSpawnSourceError("conductor-spawn emitter emitted a malformed feed"));
        return;
      }
      finish(resolve, parsed);
    });
  });
}

/**
 * DISPLAY contract: NEVER throws. Returns {ok:true, feed} on success, else {ok:false, error, feed:
 * unavailableSpawnFeed()} so the renderer/main always has a shape to fold — fail-closed, no fabricated
 * governed spawn. Note ok:true simply means a well-formed feed was parsed; that feed may itself be a
 * governed REFUSAL (feed.spawned === false) — the caller reads feed.spawned for governed birth.
 */
async function sourceConductorSpawnFeed(opts = {}) {
  try {
    const feed = await fetchConductorSpawnFeed(opts);
    return { ok: true, feed };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}`, feed: unavailableSpawnFeed() };
  }
}

module.exports = {
  ConductorSpawnSourceError,
  CONDUCTOR_SPAWN_FEED_SCHEMA,
  fetchConductorSpawnFeed,
  sourceConductorSpawnFeed,
  unavailableSpawnFeed,
  isWellFormedSpawnFeed,
};
