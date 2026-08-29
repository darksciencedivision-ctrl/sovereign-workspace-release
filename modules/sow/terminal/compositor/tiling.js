"use strict";
/**
 * Product pane-layout policy + geometry (Plan §10.2), phase-14a.tiling.
 *
 * This is the real workspace tiling — the deterministic policy the Phase-1 spike's
 * `tools/spike_compositor/lib/layout.js` only sketched. It consumes the geometry-free
 * `PaneModel.tilingMembers()` ({id, pinned, attention, activity}) and produces:
 *   - a near-square grid for the *tiled* (visible) set, with P0/P1 panes given double cells;
 *   - a right-hand *status-card rail* for everything auto-collapsed (P3/P4 + P2 overflow).
 *
 * Priority classes (Plan §10.2), highest first:
 *   P0  operator-pinned          — pinned === true; never auto-moved, never collapsed
 *   P1  awaiting-operator        — activity "awaiting_operator" (approvals/clarify/gate)
 *   P2  active-interactive       — activity "active" (conductor, debating/working nodes)
 *   P3  background-busy          — activity "background"
 *   P4  completed/idle           — activity "idle"
 *
 * Hard rules enforced here (fail-closed, deterministic — never model output):
 *   1. Visible/tiled set = P0..P2 up to `maxVisible` (default 8, operator-tunable). P3/P4 and
 *      any P2 that overflows the budget collapse to status cards.
 *   2. P0 (pinned) and P1 (awaiting-operator) are ALWAYS tiled and can NEVER be auto-collapsed
 *      — even when their count alone exceeds `maxVisible`. Operator-required panes are a hard
 *      guarantee, not a best-effort (Plan §10.2: "can never be auto-collapsed — hard rule").
 *   3. Recompute is debounced 250 ms and fires ONLY on a membership change (see membershipKey /
 *      LayoutScheduler). `attention` and other chrome flips restyle without reflow.
 *
 * `attention` is deliberately NOT a priority input: it is a chrome pulse (busy/needs-a-glance)
 * that must restyle a pane WITHOUT triggering a relayout. Priority comes from pinned + activity.
 */

const DEFAULT_MAX_VISIBLE = 8;

const ACTIVITY_TO_PRIORITY = {
  awaiting_operator: "P1",
  active: "P2",
  background: "P3",
  idle: "P4",
};

/** P0..P4 for a tiling member. pinned wins over activity (an operator-pinned pane is P0
 *  regardless of what its node is doing). Fail-closed on an unknown activity. */
function classify(member) {
  if (member.pinned) return "P0";
  const p = ACTIVITY_TO_PRIORITY[member.activity];
  if (!p) throw new Error(`unknown pane activity ${JSON.stringify(member.activity)}`);
  return p;
}

/** Near-square grid dimensions for n cells: cols = ceil(sqrt(n)), rows = ceil(n / cols). */
function nearSquare(n) {
  if (n <= 0) return { cols: 0, rows: 0 };
  const cols = Math.ceil(Math.sqrt(n));
  return { cols, rows: Math.ceil(n / cols) };
}

/** Grid geometry over the already-selected tiled set (stable order preserved). P0/P1 panes
 *  get a double (span-2) cell when there is more than one pane and at least two columns. */
function gridGeometry(tiled) {
  const n = tiled.length;
  const g = nearSquare(n);
  const cells = [];
  let slot = 0;
  for (const m of tiled) {
    const wide = (m.priority === "P0" || m.priority === "P1") && n > 1 && g.cols >= 2;
    const span = wide ? 2 : 1;
    cells.push({ id: m.id, slot, span, priority: m.priority });
    slot += span;
  }
  const totalSlots = cells.reduce((s, c) => s + c.span, 0);
  const rows = g.cols > 0 ? Math.ceil(totalSlots / g.cols) : 0;
  return { cols: g.cols, rows, cells };
}

function resolveMaxVisible(opts) {
  const mv = opts.maxVisible ?? DEFAULT_MAX_VISIBLE;
  if (!Number.isInteger(mv) || mv < 1) {
    throw new Error(`maxVisible must be a positive integer, got ${JSON.stringify(opts.maxVisible)}`);
  }
  return mv;
}

/**
 * Compute the full layout plan for a set of tiling members.
 * @param members [{id, pinned, attention, activity}] in stable (creation/z) order.
 * @param opts    {maxVisible?} operator-tunable visible cap (default 8).
 * @returns {grid:{cols,rows,cells:[{id,slot,span,priority}]}, cards:[{id,priority}], maxVisible}
 */
function planLayout(members, opts = {}) {
  const maxVisible = resolveMaxVisible(opts);
  const classified = members.map((m) => ({ id: m.id, priority: classify(m) }));

  // Always-tiled, in priority order: P0 (pinned) then P1 (awaiting-operator). Hard rule —
  // never collapsed, even if this alone exceeds maxVisible.
  const p0 = classified.filter((m) => m.priority === "P0");
  const p1 = classified.filter((m) => m.priority === "P1");
  const p2 = classified.filter((m) => m.priority === "P2");
  const background = classified.filter((m) => m.priority === "P3" || m.priority === "P4");

  const reserved = p0.length + p1.length;
  const budget = Math.max(0, maxVisible - reserved); // remaining slots P2 may claim
  const p2Visible = p2.slice(0, budget);
  const p2Overflow = p2.slice(budget);

  const tiled = [...p0, ...p1, ...p2Visible];
  // Rail: P2 overflow first (nearest to promotion), then background/idle. P1 is NEVER here.
  const cards = [...p2Overflow, ...background].map((m) => ({ id: m.id, priority: m.priority }));

  return { grid: gridGeometry(tiled), cards, maxVisible };
}

/**
 * A stable key that changes iff the LAYOUT (tiled cells + card set) changes. Used to gate
 * relayout: chrome-only flips (attention, gate-status dot, connectivity) leave this unchanged
 * so they restyle without a reflow (Plan §10.2 "recompute … on membership change only").
 */
function membershipKey(members, opts = {}) {
  const { grid, cards, maxVisible } = planLayout(members, opts);
  const tiledKey = grid.cells.map((c) => `${c.id}@${c.slot}x${c.span}:${c.priority}`).join(",");
  const cardKey = cards.map((c) => `${c.id}:${c.priority}`).join(",");
  return `mv${maxVisible}|${grid.cols}x${grid.rows}|[${tiledKey}]|cards[${cardKey}]`;
}

/**
 * Debounced, membership-gated relayout scheduler (Plan §10.2: "recompute debounced 250 ms on
 * membership change only"). Time is injected (`timer`) so the debounce is deterministically
 * testable headless — the geometry above stays pure and time-free.
 *
 * update(members, opts) returns true when the change was membership-relevant (a relayout was
 * (re)scheduled) and false when it was chrome-only (ignored). Rapid membership changes within
 * the debounce window coalesce into a single onLayout call carrying the latest state.
 */
class LayoutScheduler {
  constructor({ debounceMs = 250, timer, onLayout } = {}) {
    if (typeof onLayout !== "function") throw new Error("LayoutScheduler requires an onLayout callback");
    this._debounceMs = debounceMs;
    this._timer = timer || { set: (fn, ms) => setTimeout(fn, ms), clear: (h) => clearTimeout(h) };
    this._onLayout = onLayout;
    this._lastKey = null;
    this._handle = null;
    this._pending = null; // [members, opts] snapshot to lay out when the timer fires
  }

  update(members, opts = {}) {
    const key = membershipKey(members, opts);
    if (key === this._lastKey) return false; // chrome-only change — no reflow
    this._lastKey = key;
    this._pending = [members, opts];
    if (this._handle !== null) this._timer.clear(this._handle);
    this._handle = this._timer.set(() => {
      this._handle = null;
      const [mem, o] = this._pending;
      this._onLayout(planLayout(mem, o));
    }, this._debounceMs);
    return true;
  }

  /** Cancel any pending relayout (teardown / window close). */
  dispose() {
    if (this._handle !== null) {
      this._timer.clear(this._handle);
      this._handle = null;
    }
  }
}

module.exports = {
  DEFAULT_MAX_VISIBLE,
  classify,
  nearSquare,
  gridGeometry,
  planLayout,
  membershipKey,
  LayoutScheduler,
};
