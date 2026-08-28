"use strict";
/**
 * CONDUCTOR **model-probe** read-source (Phase 17A `.roundtrip`).
 *
 * `.pty` launched the real interactive `claude` session in pane 1 with the operator's conductor
 * SELECTION LABEL as its `--model` slug. The session ran, took the keystrokes, and answered every
 * prompt with "There's an issue with the selected model (fable-5). It may not exist or you may not
 * have access to it." A live session that cannot answer is the black pane with extra steps.
 *
 * So before the shell asks for a launch ticket, it asks Python what slug the host CLI actually
 * ACCEPTS (`tools/live/probe_conductor_model.py`): one minimal live call per candidate, behind the
 * same live gates and holding one durable I-X3 terminal while it runs, cached on the host so the
 * next launch is offline. The decision is Python's; this module only reads it (invariant 1/7).
 *
 * FAIL-CLOSED, and specifically fail-closed in the direction that PRESERVES the operator's
 * selection: a timeout, a non-zero exit, non-JSON, a shape drift or a governed refusal all yield
 * `{ok:false}` with an `unprobed` resolution, and the launch proceeds exactly as it did before this
 * module existed (label carried verbatim). "Could not probe" must never become "unavailable" — that
 * would silently strip the operator's chosen model on a network hiccup.
 */
const { runPythonEmitter } = require("./launch-source");

const MODEL_PROBE_SCHEMA = "conductor_model_probe@1.0";
const PROBE_EMITTER = "tools/live/probe_conductor_model.py";

/** Up to one minimal live call per candidate slug (the Python side bounds each at 90 s), plus
 * interpreter startup and the ledger write — the budget must EXCEED the worst case it contains, or
 * a slow-but-succeeding probe is killed just before it records its verdict. A probe that outruns
 * this is INCONCLUSIVE, not a verdict. */
const DEFAULT_PROBE_TIMEOUT_MS = 240000;
const MODEL_PROBE_STRATEGIES = Object.freeze({
  claude_code: "host_probe",
});

function unprobed(reason) {
  return {
    schema: MODEL_PROBE_SCHEMA,
    ok: false,
    refused: false,
    reason,
    label: null,
    source: "unavailable",
    spent_live_call: false,
    resolution: { model: null, model_available: null, source: "unprobed" },
    record: null,
  };
}

/** Return a descriptor-driven probe plan. An adapter with no implemented probe is UNPROBED;
 * registry membership is not evidence that the host CLI accepts a model slug. */
function modelProbeStrategy(descriptor) {
  if (!descriptor || typeof descriptor.adapter_id !== "string") return "unprobed";
  return MODEL_PROBE_STRATEGIES[descriptor.adapter_id] || "unprobed";
}

function unprobedDescriptorResult(descriptor) {
  const adapter = descriptor && descriptor.adapter_id;
  const probe = unprobed(`no host model probe is implemented for ${adapter || "this adapter"}`);
  probe.label = (descriptor && descriptor.display_name) || null;
  probe.resolution.label = probe.label;
  return { ok: false, probe };
}

/** A payload is usable only with the pinned schema and a resolution whose two fields are exactly
 * the tri-state the launch path understands: slug-or-null, and true/false/null availability. */
function isWellFormedProbe(p) {
  if (!p || typeof p !== "object") return false;
  if (p.schema !== MODEL_PROBE_SCHEMA) return false;
  if (typeof p.ok !== "boolean" || typeof p.refused !== "boolean") return false;
  const r = p.resolution;
  if (!r || typeof r !== "object") return false;
  if (!(r.model === null || (typeof r.model === "string" && r.model.length > 0))) return false;
  if (!(r.model_available === null || typeof r.model_available === "boolean")) return false;
  return typeof r.source === "string" && r.source.length > 0;
}

/**
 * DISPLAY contract: never throws. `{ok, probe, error?}`. `ok:true` means a well-formed payload was
 * parsed — read `probe.resolution` for what it decided and `probe.refused` for a governed refusal.
 *
 * `ledgerOnly` reports what the host already recorded without spending anything; `reprobe` forces a
 * fresh live probe (the operator's "the CLI changed, ask again" lever).
 */
async function sourceConductorModelProbe(opts = {}) {
  const args = ["--emit-model-probe"];
  if (opts.label) args.push("--label", String(opts.label));
  if (opts.reprobe) args.push("--reprobe");
  if (opts.ledgerOnly) args.push("--ledger-only");
  try {
    const probe = await runPythonEmitter(
      args,
      { ...opts, script: PROBE_EMITTER, timeoutMs: opts.timeoutMs || DEFAULT_PROBE_TIMEOUT_MS },
      isWellFormedProbe,
      "conductor-model-probe",
    );
    return { ok: true, probe };
  } catch (e) {
    const error = `${e.name || "Error"}: ${e.message}`;
    return { ok: false, error, probe: unprobed(error) };
  }
}

/** One-line, operator-readable account of what the probe decided (logged at launch). */
function describeProbe(probe) {
  const r = (probe && probe.resolution) || {};
  if (r.model_available === true) return `model ${r.model} ACCEPTED by the host CLI (${probe.source})`;
  if (r.model_available === false) {
    return `the host CLI accepts none of the candidate slugs for ${probe.label} — launching on the `
      + `CLI default and RECORDING the fallback (${probe.source})`;
  }
  return `model availability UNPROBED (${(probe && probe.reason) || r.source || "no record"}) — `
    + "the operator's selection is carried verbatim";
}

module.exports = {
  MODEL_PROBE_SCHEMA,
  PROBE_EMITTER,
  DEFAULT_PROBE_TIMEOUT_MS,
  MODEL_PROBE_STRATEGIES,
  sourceConductorModelProbe,
  isWellFormedProbe,
  unprobed,
  modelProbeStrategy,
  unprobedDescriptorResult,
  describeProbe,
};
