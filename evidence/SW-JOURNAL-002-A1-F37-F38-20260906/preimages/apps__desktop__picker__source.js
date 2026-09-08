"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * Per-pane model-picker data SOURCE (Phase 16B `.source`).
 *
 * The picker OPTION SET is host-enumerated by ONE authority — the operator-run metric
 * `tools/live/enumerate_pane_picker.build_host_picker`, exposed as `--emit-picker` (a stable
 * JSON contract). This module invokes that enumerator as a BOUNDED one-shot subprocess (the same
 * `py -3.12` the shell already uses for the IPC gateway), parses the picker JSON, and hands it to
 * the renderer. The shell NEVER re-implements or fabricates the option list — it renders exactly
 * what the host enumeration produced (greyed-with-reason for an unauthorized/absent provider,
 * live residency for a local model). Read-only: the enumerator performs no model call and touches
 * no credential (§2.2); it reads the fail-closed LiveAuthorization gate, the benign codex/claude
 * presence probes, and the operator's live `ollama list`.
 *
 * FAIL-CLOSED, by contract: a timeout, a non-zero exit, non-JSON output, or a payload without a
 * `providers` array yields the EMPTY picker (no options) carrying `.error` — never a fabricated
 * or partial option. The picker button is not load-bearing for supervision, so a fault degrades
 * the dropdown to "unavailable", it never throws into the renderer.
 *
 * Injectable (`spawn`) so the parse/timeout/fail-closed logic is unit-tested with a fake process,
 * with zero dependence on a live host (apps/desktop/test/picker-source.test.js).
 */
const { spawn: realSpawn } = require("child_process");

class PickerSourceError extends Error {}

// Pinned by `tools/live/enumerate_pane_picker.HOST_RESIDENCY_SCHEMA` — a drifted producer is refused.
const HOST_RESIDENCY_SCHEMA = "host_residency@1.0";

// The empty picker — the fail-closed shape. Zero options, zero counts; authorization unknown.
// Rendering this shows "picker unavailable (fail-closed)", NEVER a fabricated model (invariant 20
// air-gap-honesty spirit: an absent enumeration is reported as absent, not guessed).
function emptyPicker() {
  return {
    providers: [],
    options: [],
    authorization: { authorized: false, reason: "picker enumeration unavailable (fail-closed)" },
    counts: { total: 0, available: 0, frontier: 0, local: 0 },
  };
}

// A payload is a usable picker only if it carries the arrays the renderer folds over. Anything
// else (a stray log line, a truncated read, a shape drift) is refused — fail closed.
function isWellFormedPicker(p) {
  return !!p && Array.isArray(p.providers) && Array.isArray(p.options)
    && p.counts && typeof p.counts === "object";
}

/**
 * Run the `--emit-picker` enumerator once and return the parsed picker dict. STRICT: throws
 * PickerSourceError on timeout / non-zero exit / non-JSON / malformed shape.
 * @param {object} opts
 * @param {function} [opts.spawn]    child_process.spawn (injected in tests)
 * @param {string}   [opts.python]   interpreter (default resolved by python-runtime.js)
 * @param {string[]} [opts.pythonArgs] leading args (default ["-3.12"])
 * @param {string}   opts.cwd        repo root (so the tool's sys.path/imports resolve)
 * @param {number}   [opts.timeoutMs] hard bound (default 20000)
 * @returns {Promise<object>} the picker dict
 */
function fetchHostPicker(opts = {}) {
  return runEnumerator("--emit-picker", opts, isWellFormedPicker,
    "malformed picker (missing providers/options/counts)");
}

/**
 * A payload is a usable residency report only if it carries the pinned schema, the budget dict, and
 * — when a snapshot is present at all — the NUMBERS a consumer computes with. `snapshot: null` is
 * legitimate (no planner could be built); a snapshot missing `used_vram_mb`, or carrying a model
 * entry without a name or footprint, is not.
 *
 * The field checks are the point. `host_residency@1.0` has no file in `schemas/` (U104), so this
 * predicate IS the contract — and a version of it that validated only the schema string would let a
 * caller compute a VRAM budget from fields nothing had checked (spec-audit MAJOR-1, 2026-07-26).
 */
function isWellFormedResidency(r) {
  if (!r || r.schema !== HOST_RESIDENCY_SCHEMA) return false;
  if (!r.budget || typeof r.budget !== "object") return false;
  if (!("established" in r.budget)) return false;
  if (r.snapshot === null || r.snapshot === undefined) return true;
  const s = r.snapshot;
  if (typeof s !== "object") return false;
  if (!Number.isFinite(s.used_vram_mb) || !Number.isFinite(s.total_vram_mb)) return false;
  if (!Array.isArray(s.models)) return false;
  return s.models.every((m) => m && typeof m.model === "string" && m.model
    && Number.isFinite(m.footprint_mb) && typeof m.status === "string");
}

/**
 * The host's VRAM budget + the planner's own snapshot (`--emit-residency`). DISPLAY contract, never
 * throws: `{ok, residency}`. Read-only, no model call, no credential — the same enumerator the
 * picker comes from. Its purpose is arithmetic a caller must be able to make DETERMINISTIC: the
 * in-Electron self-check computes the budgets for its VRAM legs from this instead of guessing a
 * constant and getting whichever branch of the admission gate the daemon's current state produced.
 */
async function fetchHostResidency(opts = {}) {
  try {
    return { ok: true, residency: await runEnumerator("--emit-residency", opts,
      isWellFormedResidency, "malformed residency report (missing schema/budget)") };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}`, residency: null };
  }
}

/** ONE bounded `py -3.12 enumerate_pane_picker.py <mode>` run, parsed and shape-checked. STRICT:
 * throws PickerSourceError on timeout / non-zero exit / non-JSON / malformed shape. */
function runEnumerator(mode, opts, isWellFormed, malformedNote) {
  const spawn = opts.spawn || realSpawn;
  const python = opts.python || defaultPython();
  const pythonArgs = opts.pythonArgs || defaultPythonArgs();
  const cwd = opts.cwd;
  const timeoutMs = opts.timeoutMs || 20000;
  const args = [...pythonArgs, "tools/live/enumerate_pane_picker.py", mode];

  return new Promise((resolve, reject) => {
    let child;
    try {
      // `env` is optional and per-child: the enumerator reads host facts out of the environment
      // (SOW_VRAM_BUDGET_MB, PATH), so a caller that needs to enumerate under DIFFERENT host
      // conditions must be able to say so without mutating the shell's own process env, which
      // every other enumerator call would then inherit (spec-audit MINOR-7). Absent ⇒ inherit,
      // which is the product path.
      child = spawn(python, args, opts.env ? { cwd, env: opts.env } : { cwd });
    } catch (e) {
      reject(new PickerSourceError(`could not launch the picker enumerator: ${e.message}`));
      return;
    }
    let out = "";
    let err = "";
    let settled = false;
    const finish = (fn, arg) => { if (settled) return; settled = true; clearTimeout(to); try { child.kill(); } catch { /* gone */ } fn(arg); };
    const to = setTimeout(
      () => finish(reject, new PickerSourceError(`picker enumeration timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    if (child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", (e) => finish(reject, new PickerSourceError(`picker enumerator failed to run: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new PickerSourceError(`picker enumerator exited ${code}${err ? `: ${err.trim().slice(0, 200)}` : ""}`));
        return;
      }
      let parsed;
      try { parsed = JSON.parse(out); }
      catch (e) { finish(reject, new PickerSourceError(`picker enumerator emitted non-JSON: ${e.message}`)); return; }
      if (!isWellFormed(parsed)) {
        finish(reject, new PickerSourceError(`picker enumerator emitted a ${malformedNote}`));
        return;
      }
      finish(resolve, parsed);
    });
  });
}

/**
 * DISPLAY contract: NEVER throws. Returns {ok:true, picker} on success, else {ok:false, error,
 * picker: emptyPicker()} so the renderer always has a shape to fold — fail-closed, no fabricated
 * options. The dropdown surfaces the error honestly.
 */
async function fetchPickerModel(opts = {}) {
  try {
    const picker = await fetchHostPicker(opts);
    return { ok: true, picker };
  } catch (e) {
    return { ok: false, error: `${e.name || "Error"}: ${e.message}`, picker: emptyPicker() };
  }
}

module.exports = {
  PickerSourceError, HOST_RESIDENCY_SCHEMA, fetchHostPicker, fetchPickerModel, fetchHostResidency,
  emptyPicker, isWellFormedPicker, isWellFormedResidency,
};
