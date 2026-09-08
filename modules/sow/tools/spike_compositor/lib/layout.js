"use strict";
/** Near-square grid (Plan 10.2 simplified for the spike): cols=ceil(sqrt(n)), rows=ceil(n/cols).
 *  Pinned/attention panes get a double cell when space allows. Recompute only on membership change. */
function grid(n) {
  if (n <= 0) return { cols: 0, rows: 0 };
  const cols = Math.ceil(Math.sqrt(n));
  return { cols, rows: Math.ceil(n / cols) };
}
function layout(panes /* [{id, pinned, attention}] */) {
  const n = panes.length;
  const g = grid(n);
  const cells = [];
  let slot = 0;
  const order = [...panes].sort((a, b) => (b.pinned - a.pinned) || (b.attention - a.attention));
  for (const p of order) {
    const double = (p.pinned || p.attention) && n > 1 && g.cols >= 2;
    cells.push({ id: p.id, slot, span: double ? 2 : 1 });
    slot += double ? 2 : 1;
  }
  const totalSlots = cells.reduce((s, c) => s + c.span, 0);
  const rows = Math.ceil(totalSlots / g.cols);
  return { cols: g.cols, rows, cells };
}
/** Stable key: layout must only be recomputed when this changes (not on state restyles). */
function membershipKey(panes) {
  return panes.map((p) => `${p.id}:${p.pinned ? 1 : 0}:${p.attention ? 1 : 0}`).join("|");
}
module.exports = { grid, layout, membershipKey };
