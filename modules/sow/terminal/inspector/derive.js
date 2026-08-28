"use strict";
/**
 * Honest read-model derivation for the routing/artifact inspector (Plan §10.3), phase-14a.inspector.
 *
 * WHY THIS MODULE EXISTS — the truth about what is readable.
 * The §10.3 inspector wants three dimensions per task: context routed, artifacts published, and
 * the gate chain. Only ONE of them has a durable read path today over the D-IPC-01 channel:
 *
 *   • artifacts published — REAL. `read_status` returns the shared-memory entries (entry_id,
 *     kind, status, content_hash, provenance). This is the trustworthy spine of the inspector.
 *
 *   • gate chain — NOT persisted as a structured record. control_plane/gates/engine.py computes a
 *     gate@1.0 verdict, drives the in-memory TaskGraph with it, and DISCARDS it — there is no
 *     store table and no read op for gate@1.0. What IS durable: the conductor path publishes each
 *     gate DECISION as a `kind:"decision"` memory entry (see control_plane/orchestration/
 *     conductor_prototype.py: the plan gate is `publish(kind="decision", …)`), and a stage-gate
 *     promotion stamps `provenance.gate_result` on the promoted artifact (memory_service.transition).
 *     So the gate chain is RECONSTRUCTED here from decision entries + gate_result, each row marked
 *     `derived:true`. We never fabricate a structured verdict the store does not hold.
 *
 *   • context routed — NOT readable AT ALL. ContextCompiler emits a ScopedContext dataclass that
 *     is never serialized, never stored, never returned by any op (control_plane/routing/
 *     context_compiler.py). We therefore return `routes: []` and set `routingReadable: false`
 *     rather than invent a bundle. Where an artifact records `provenance.source_artifacts`, those
 *     ids ride along on the artifact row (inspector-model keeps full provenance) as the only
 *     honest, readable trace of what fed a task — but that is per-artifact provenance, not the
 *     scoped-context bundle, and is not presented as one.
 *
 * This module is PURE and deterministic: no I/O, no clock, no randomness, no model output. It maps
 * the flat readable-entry list into the {entries, gates, routes} shape buildInspectorModel folds.
 * Fail-closed: a malformed record (not a plain object) THROWS — it never guesses past ambiguity.
 *
 * The two structural gaps (gate@1.0 not persisted; ScopedContext ephemeral) are recorded as
 * uncertainties in the phase evidence; if a later phase adds real gate/route read ops, source.js
 * feeds them straight into buildInspectorModel and this derivation narrows to entries-only.
 */

// The memory kind that carries a gate decision durably (mcp_server lifecycle / schemas/memory).
const GATE_DECISION_KIND = "decision";

function isPlainObject(x) {
  return x !== null && typeof x === "object" && !Array.isArray(x);
}

function requireObject(x, what) {
  if (!isPlainObject(x)) {
    throw new Error(`derive: malformed ${what} (expected an object, got ${JSON.stringify(x)})`);
  }
  return x;
}

/**
 * A decision entry -> a DERIVED gate-chain row shaped like buildInspectorModel's gate input.
 * task_id/verdict/evidence come from the entry's own governed provenance; nothing is invented.
 */
function decisionToGate(entry) {
  const prov = isPlainObject(entry.provenance) ? entry.provenance : {};
  return {
    // top-level shape buildInspectorModel/toGateRow reads:
    gate_id: entry.entry_id ?? null,
    kind: GATE_DECISION_KIND,
    // gate_result is the readable gate outcome a promotion stamped; absent -> null (never guessed).
    verdict: typeof prov.gate_result === "string" && prov.gate_result.length > 0 ? prov.gate_result : null,
    evidence: Array.isArray(prov.evidence) ? prov.evidence.slice() : [],
    reasons: [],
    debate_ref: null,
    task_id: typeof prov.task_id === "string" && prov.task_id.length > 0 ? prov.task_id : null,
    // origin markers so the panel/tests know this is reconstructed, not a native gate@1.0 record:
    derived: true,
    source_entry_id: entry.entry_id ?? null,
    author: prov.author_node ?? null,
    ts: prov.ts ?? null,
    entry_status: entry.status ?? null, // the decision entry's lifecycle state (ACCEPTED/…)
  };
}

/**
 * Map the flat list of readable memory entries into the inspector-model input shape.
 * @param {Array} entries  shared-memory entries (union of read_status across all statuses)
 * @returns {{entries:Array, gates:Array, routes:Array, routingReadable:boolean}}
 *   entries  — the non-decision entries (findings / artifact_ref / evidence / directive / …),
 *              i.e. "artifacts published" per §10.3;
 *   gates    — gate rows DERIVED from kind:"decision" entries (each `derived:true`);
 *   routes   — [] always: ScopedContext is ephemeral and has no read path;
 *   routingReadable — false always (today): explicit, observable statement of the gap.
 */
function deriveInputs(entries = []) {
  if (!Array.isArray(entries)) {
    throw new Error(`derive: expected an array of entries, got ${JSON.stringify(entries)}`);
  }
  const workEntries = [];
  const gates = [];
  for (const raw of entries) {
    const entry = requireObject(raw, "entry");
    if (entry.kind === GATE_DECISION_KIND) {
      gates.push(decisionToGate(entry)); // gate-chain dimension (derived)
    } else {
      workEntries.push(entry); // artifacts-published dimension (real)
    }
  }
  return {
    entries: workEntries,
    gates,
    routes: [], // ScopedContext is never serialized/stored/exposed — do not fabricate one
    routingReadable: false,
  };
}

module.exports = { GATE_DECISION_KIND, deriveInputs, decisionToGate };
