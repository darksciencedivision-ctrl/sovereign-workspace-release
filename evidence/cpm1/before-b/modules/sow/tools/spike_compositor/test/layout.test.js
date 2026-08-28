"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { grid, layout, membershipKey } = require("../lib/layout");

test("near-square grid for n=1..12", () => {
  for (let n = 1; n <= 12; n++) {
    const g = grid(n);
    assert.ok(g.cols * g.rows >= n, `n=${n} fits`);
    assert.ok(g.cols - g.rows <= 1, `n=${n} near-square`);
  }
});
test("6 panes -> 3x2", () => { assert.deepEqual(grid(6), { cols: 3, rows: 2 }); });
test("8 panes -> 3x3", () => { assert.deepEqual(grid(8), { cols: 3, rows: 3 }); });
test("pinned pane gets a double cell and leads the order", () => {
  const l = layout([
    { id: "a", pinned: false, attention: false },
    { id: "b", pinned: true, attention: false },
    { id: "c", pinned: false, attention: false },
  ]);
  assert.equal(l.cells[0].id, "b");
  assert.equal(l.cells[0].span, 2);
});
test("membership key is stable under non-membership state changes", () => {
  const panes = [{ id: "a", pinned: false, attention: false }];
  const k1 = membershipKey(panes);
  panes[0].busy = true; // restyle-only property
  assert.equal(membershipKey(panes), k1);
  panes[0].pinned = true; // membership-relevant
  assert.notEqual(membershipKey(panes), k1);
});
