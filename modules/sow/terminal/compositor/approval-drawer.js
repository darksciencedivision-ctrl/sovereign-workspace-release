"use strict";
/**
 * Approval-queue drawer render model (OP-7 §12.5 item 5), phase-15e.objective.
 *
 * The operator's approval drawer surfaces the three things the conductor needs the operator to
 * decide — a decomposed PLAN awaiting approval, a PROTECTED/destructive action queued for approval,
 * and a CLARIFICATION the conductor is asking for — in ONE list with a badge count. The authority
 * and the queue live Python-side (control_plane/orchestration/operator_surface.ApprovalQueue): only
 * the operator may resolve an item (invariant 1), and a gate-failed plan is not approvable
 * (invariant 16). This module is the PURE, deterministic render model for that drawer — it folds the
 * `approval_drawer@1.0` snapshot (from ApprovalQueue.drawer_model(), delivered read-only over IPC)
 * into rows + a badge the renderer paints. It renders nothing and performs no I/O; the drawn drawer
 * is an operator-run surface (the Phase-1 substitution pattern).
 *
 * Fail-closed + observable (the bars this must clear, mirroring the inspector model):
 *   - a malformed/absent snapshot yields an EMPTY, `ok:false` model — never a fabricated count, and
 *     never a throw into the always-visible chrome;
 *   - `badgeCount` is RECOMPUTED from the rows here, so an inflated `badge_count` in the payload can
 *     never drive the badge (the number means what its name says);
 *   - a row of an unknown kind is NOT dropped — it is surfaced with a generic label so a new kind
 *     stays visible rather than vanishing.
 */

// The kinds the drawer knows how to label. An unknown kind is tolerated (never dropped) and labeled
// generically — deterministic, and it never hides a kind this view has not been taught yet.
const KIND_LABELS = {
  plan: "Plan",
  protected_action: "Protected action",
  clarification: "Clarification",
};
const KNOWN_KINDS = Object.keys(KIND_LABELS);

function kindLabel(kind) {
  return Object.prototype.hasOwnProperty.call(KIND_LABELS, kind) ? KIND_LABELS[kind] : "Unknown";
}

function isPlainObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function normalizeRow(raw) {
  if (!isPlainObject(raw)) return null;
  const kind = typeof raw.kind === "string" ? raw.kind : "unknown";
  const id = typeof raw.item_id === "string" && raw.item_id.trim() ? raw.item_id : null;
  if (!id) return null; // a row with no id cannot be acted on — fail closed, drop THIS row only
  return {
    id,
    seq: Number.isFinite(raw.seq) ? raw.seq : 0,
    kind,
    kindLabel: kindLabel(kind),
    known: KNOWN_KINDS.includes(kind),
    summary: typeof raw.summary === "string" ? raw.summary : "",
    origin: typeof raw.origin === "string" ? raw.origin : "unknown",
    // Only an APPROVABLE item may be approved (a gate-failed plan is approvable:false — invariant
    // 16). Default false: an absent/ambiguous flag must never render an Approve affordance.
    approvable: raw.approvable === true,
    ref: typeof raw.ref === "string" && raw.ref.trim() ? raw.ref : null,
    detail: isPlainObject(raw.detail) ? raw.detail : {},
  };
}

/**
 * Fold an `approval_drawer@1.0` snapshot into the drawer render model.
 * Returns { ok, schema, badgeCount, kindCounts, rows, empty, error }.
 */
function buildApprovalDrawer(snapshot) {
  const base = {
    ok: false, schema: null, badgeCount: 0,
    kindCounts: { plan: 0, protected_action: 0, clarification: 0, unknown: 0 },
    rows: [], empty: true, error: null,
  };
  if (!isPlainObject(snapshot)) {
    return { ...base, error: "approval snapshot unavailable" };
  }
  const pendingRaw = Array.isArray(snapshot.pending) ? snapshot.pending : [];
  // sort by seq so the drawer order is deterministic regardless of payload order
  const rows = pendingRaw
    .map(normalizeRow)
    .filter((r) => r !== null)
    .sort((a, b) => a.seq - b.seq);
  const kindCounts = { plan: 0, protected_action: 0, clarification: 0, unknown: 0 };
  for (const r of rows) {
    if (Object.prototype.hasOwnProperty.call(kindCounts, r.kind)) kindCounts[r.kind] += 1;
    else kindCounts.unknown += 1;
  }
  return {
    ok: true,
    schema: typeof snapshot.schema === "string" ? snapshot.schema : null,
    // RECOMPUTED from the rows — the payload's own badge_count is never trusted to drive the badge
    badgeCount: rows.length,
    kindCounts,
    rows,
    empty: rows.length === 0,
    error: null,
  };
}

/**
 * One-line summary for the drawer header / accessibility label. Deterministic.
 */
function summarizeApprovalDrawer(view) {
  if (!view || view.ok !== true) return "approvals unavailable";
  if (view.badgeCount === 0) return "no pending approvals";
  const parts = [];
  for (const kind of KNOWN_KINDS) {
    const n = view.kindCounts[kind];
    if (n > 0) parts.push(`${n} ${KIND_LABELS[kind].toLowerCase()}`);
  }
  if (view.kindCounts.unknown > 0) parts.push(`${view.kindCounts.unknown} other`);
  return `${view.badgeCount} pending (${parts.join(" · ")})`;
}

module.exports = { buildApprovalDrawer, summarizeApprovalDrawer, kindLabel, KIND_LABELS, KNOWN_KINDS };
