"use strict";
/**
 * Routing/artifact inspector data model (Plan §10.3), phase-14a.inspector.
 *
 * The §10.3 always-visible "Routing/artifact inspector" is a PER-TASK view of three governed
 * dimensions the control plane already produces:
 *   - context routed   — what the scoped-context compiler (control_plane/routing) assembled for
 *                        the task: role + the exact included entry ids (need-to-know), never a
 *                        blanket forward (invariant 8);
 *   - artifacts published — the shared-memory entries attributed to the task, each with its
 *                        content hash, lifecycle status, and provenance (invariant 11);
 *   - gate chain       — the gate@1.0 verdicts (control_plane/gates) recorded against the task,
 *                        in order, with the evidence/reasons each references (invariant 16).
 *
 * This module is the PURE, deterministic aggregation core — the testable heart of the inspector.
 * It takes already-read records (the shell fetches them read-only over the D-IPC-01 channel via
 * apps/desktop/inspector/source.js) and folds them into a stable per-task model. It renders
 * nothing and performs no I/O; the panel that draws this is an operator-run surface (like the
 * window itself), exactly the Phase-1 substitution pattern.
 *
 * Fail-closed + observable (the two bars this code must clear):
 *   - a malformed record (not a plain object) THROWS — never guess past ambiguous input;
 *   - a record with no resolvable task id is NOT dropped: it lands in an explicit `unattributed`
 *     bucket so a mis-provenanced artifact stays visible rather than vanishing (invariant 27);
 *   - the same entry id seen at two different statuses is a real inconsistency: the current row
 *     is the most-advanced status (deterministic), and the divergence is recorded in `anomalies`.
 * No model output ever decides policy — this is a read-only lens over governed state.
 */

// Lifecycle statuses the inspector understands, most-advanced last. Mirrors mcp_server/
// lifecycle.py. Unknown statuses are tolerated (real store data is never dropped) and ordered
// after the known ones by name, so ordering stays deterministic without failing closed on a
// status this view has not been taught yet.
const STATUS_ORDER = [
  "CANDIDATE",
  "UNDER_REVIEW",
  "DISPUTED",
  "REJECTED",
  "ACCEPTED_WITH_RESERVATIONS",
  "ACCEPTED",
  "SUPERSEDED",
  "ARCHIVED",
];
const _STATUS_RANK = new Map(STATUS_ORDER.map((s, i) => [s, i]));

function statusRank(status) {
  // Known statuses keep their lifecycle position; unknown ones sort AFTER all known ones,
  // then lexicographically — deterministic, and it never hides an unrecognised status.
  const r = _STATUS_RANK.get(status);
  return r === undefined ? STATUS_ORDER.length : r;
}

function isPlainObject(x) {
  return x !== null && typeof x === "object" && !Array.isArray(x);
}

function requireObject(x, what) {
  if (!isPlainObject(x)) {
    throw new Error(`inspector: malformed ${what} record (expected an object, got ${JSON.stringify(x)})`);
  }
  return x;
}

/** Resolve a task id from a value that may be a string, or null/undefined/"" when unattributed. */
function normTaskId(v) {
  return typeof v === "string" && v.length > 0 ? v : null;
}

/** An entry's task id lives in its provenance (memory_service stamps provenance.task_id). */
function entryTaskId(entry) {
  const prov = isPlainObject(entry.provenance) ? entry.provenance : {};
  return normTaskId(prov.task_id);
}

function toArtifactRow(entry) {
  const prov = isPlainObject(entry.provenance) ? entry.provenance : {};
  return {
    entryId: entry.entry_id ?? null,
    hash: entry.content_hash ?? null, // §10.3 "artifacts published (hash, …)"
    kind: entry.kind ?? null,
    status: entry.status ?? null,
    author: prov.author_node ?? null,
    ts: prov.ts ?? null,
    provenance: prov,
  };
}

function toGateRow(gate) {
  const row = {
    gateId: gate.gate_id ?? null,
    kind: gate.kind ?? null,
    verdict: gate.verdict ?? null,
    evidence: Array.isArray(gate.evidence) ? gate.evidence.slice() : [],
    reasons: Array.isArray(gate.reasons) ? gate.reasons.slice() : [],
    debateRef: gate.debate_ref ?? null,
  };
  // Gate@1.0 records are computed by control_plane/gates but NOT persisted and NOT exposed by
  // any read op (see terminal/inspector/derive.js). Over the read path a gate decision is
  // durably visible only as a kind:"decision" memory entry. derive.js reconstructs a gate row
  // from such an entry and marks it `derived:true` with the origin fields below so the panel
  // never presents a reconstructed row as a native structured verdict (fail-closed honesty).
  if (gate.derived) {
    row.derived = true;
    row.sourceEntryId = gate.source_entry_id ?? null; // the decision entry this was read from
    row.author = gate.author ?? null;                 // provenance.author_node
    row.ts = gate.ts ?? null;                         // provenance.ts
    row.entryStatus = gate.entry_status ?? null;      // the decision entry's lifecycle status
  }
  return row;
}

function blankTask(taskId) {
  return {
    taskId,
    contextRouted: null, // {role, objective, includedEntryIds:[…], count} or null if never routed
    artifacts: [],
    gateChain: [],
  };
}

/**
 * Fold read records into a per-task inspector model.
 * @param {object} input
 * @param {Array} input.entries  shared-memory entries (from read_status across statuses)
 * @param {Array} input.gates    gate@1.0 verdict records
 * @param {Array} input.routes   scoped-context descriptors {task_id, role, objective?, included_entry_ids:[…]}
 * @returns {{tasks:Array, unattributed:object, anomalies:Array}}
 */
function buildInspectorModel({ entries = [], gates = [], routes = [] } = {}) {
  const tasks = new Map(); // taskId -> task record (insertion tracked, sorted on output)
  const unattributed = { artifacts: [], gates: [], routes: [] };
  const anomalies = [];
  const seenEntries = new Map(); // entry_id -> {taskId, status} (dedupe + divergence detection)

  const task = (id) => {
    let t = tasks.get(id);
    if (!t) { t = blankTask(id); tasks.set(id, t); }
    return t;
  };

  // -- artifacts published (memory entries) ----------------------------------
  for (const raw of entries) {
    const entry = requireObject(raw, "entry");
    const row = toArtifactRow(entry);
    const tid = entryTaskId(entry);

    if (row.entryId != null) {
      const prev = seenEntries.get(row.entryId);
      if (prev) {
        // A second read of the same head is idempotent; a DIFFERENT status is a real divergence.
        if (prev.status !== row.status) {
          anomalies.push({
            kind: "status-divergence",
            entryId: row.entryId,
            statuses: [prev.status, row.status],
            note: "same entry id reported at two statuses; keeping the most-advanced",
          });
          if (statusRank(row.status) <= statusRank(prev.status)) continue; // keep the advanced one
          // this row is more advanced: replace the earlier one in place
          const bucket = prev.taskId == null ? unattributed.artifacts : task(prev.taskId).artifacts;
          const i = bucket.findIndex((a) => a.entryId === row.entryId);
          if (i >= 0) bucket.splice(i, 1);
        } else {
          continue; // exact duplicate — idempotent double read
        }
      }
      seenEntries.set(row.entryId, { taskId: tid, status: row.status });
    }

    if (tid == null) unattributed.artifacts.push(row);
    else task(tid).artifacts.push(row);
  }

  // -- gate chain ------------------------------------------------------------
  for (const raw of gates) {
    const gate = requireObject(raw, "gate");
    const tid = normTaskId(gate.task_id);
    const row = toGateRow(gate);
    if (tid == null) unattributed.gates.push(row);
    else task(tid).gateChain.push(row);
  }

  // -- context routed --------------------------------------------------------
  for (const raw of routes) {
    const route = requireObject(raw, "route");
    const tid = normTaskId(route.task_id);
    const included = Array.isArray(route.included_entry_ids) ? route.included_entry_ids.slice() : [];
    const routed = {
      role: route.role ?? null,
      objective: route.objective ?? null,
      includedEntryIds: included,
      count: included.length,
    };
    if (tid == null) { unattributed.routes.push(routed); continue; }
    const t = task(tid);
    if (t.contextRouted) {
      // Two routing records for one task: the compiler emits one scoped bundle per assignment.
      // A second is a real re-route; record it rather than silently overwriting.
      anomalies.push({ kind: "duplicate-route", taskId: tid, note: "more than one routed context for a task; keeping the latest" });
    }
    t.contextRouted = routed;
  }

  // -- deterministic output --------------------------------------------------
  for (const t of tasks.values()) {
    t.artifacts.sort((a, b) => statusRank(a.status) - statusRank(b.status) || String(a.entryId).localeCompare(String(b.entryId)));
  }
  const orderedTasks = [...tasks.values()].sort((a, b) => String(a.taskId).localeCompare(String(b.taskId)));

  return { tasks: orderedTasks, unattributed, anomalies };
}

/** The per-task record for `taskId`, or null if the task is unknown to the model. */
function taskView(model, taskId) {
  return model.tasks.find((t) => t.taskId === taskId) || null;
}

/** Compact counts for the status-bar/inspector badge (observability, invariant 27). */
function summarize(model) {
  const artifacts = model.tasks.reduce((n, t) => n + t.artifacts.length, 0) + model.unattributed.artifacts.length;
  const gates = model.tasks.reduce((n, t) => n + t.gateChain.length, 0) + model.unattributed.gates.length;
  const routed = model.tasks.filter((t) => t.contextRouted).length;
  const unattributed =
    model.unattributed.artifacts.length + model.unattributed.gates.length + model.unattributed.routes.length;
  return {
    taskCount: model.tasks.length,
    artifactCount: artifacts,
    gateCount: gates,
    routedTaskCount: routed,
    unattributedCount: unattributed,
    anomalyCount: model.anomalies.length,
  };
}

module.exports = {
  STATUS_ORDER,
  statusRank,
  buildInspectorModel,
  taskView,
  summarize,
};
