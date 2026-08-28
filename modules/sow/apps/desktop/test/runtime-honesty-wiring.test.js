"use strict";
/**
 * Unit 19.7 (U334/U335/U336) — the bindings that live in `main.js` and the renderer, pinned.
 *
 * These are SOURCE PINS and are the weaker half of this unit's evidence, deliberately named as such:
 * `main.js` cannot be required in a test (U338 — unit 19.9's charter) and `renderer/renderer.js`
 * runs in a browser context with no module boundary. The behaviour they guard is driven where it
 * can be driven — `sovereign-control-server.test.js`, `assignment-gate.test.js`,
 * `operational-source.test.js` — and measured in the packaged runtime by the `runtime-honesty`
 * in-Electron self-check. What these pins catch is the wiring being removed or routed around, which
 * is exactly how each of these three defects reached the audit: the module was fine, the caller was
 * not.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { summarizeDispatch } = require("../control/operational-state");

const MAIN = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");
const RENDERER = fs.readFileSync(path.resolve(__dirname, "..", "renderer", "renderer.js"), "utf8");

const slice = (source, from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start > 0 && end > start, `could not locate ${from} … ${to}`);
  return source.slice(start, end);
};

/** Whole-line comments removed. The POSITIVE assertions below run against this, because a pin that
 *  matches a phrase anywhere in the region is satisfied by the region's own prose: the
 *  gate-validator restored the fabricated zeros in `renderer.js` while leaving the sentences about
 *  them in a comment, and the pins still passed (round 1, MINOR-1). */
const executableOnly = (region) =>
  region.replace(/\/\*[\s\S]*?\*\//g, "")     // …and whole block comments, not just their first line
    .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n");

test("U334: the control gateway is torn down with every other resource, not after the quit path", () => {
  const teardown = executableOnly(slice(MAIN, "function teardown() {", "function waitForChildExit"));
  assert.match(teardown, /sovereignControl\.stop\(\)/,
    "the gateway must be stopped inside teardown(), where supervisor/gateway/scheduler already are");
  // …and the awaiting call sites still read the outcome, so nothing is fire-and-forget where the
  // result matters. Both are the same memoised promise.
  const quit = executableOnly(slice(MAIN, "async function completeNormalQuit", "app.whenReady"));
  assert.match(quit, /const controlStop = sovereignControl \? await sovereignControl\.stop\(\) : null/);
  const selfCheckTeardown = executableOnly(
    slice(MAIN, "async function teardownSelfCheck", "let normalQuitStarted"));
  assert.match(selfCheckTeardown, /const controlStop = sovereignControl \? await sovereignControl\.stop\(\) : null/);
  assert.match(quit, /controlStop=\$\{JSON\.stringify\(controlStop\)\}/,
    "an incomplete teardown must say what the gateway did");
});

test("U334: nothing in the shutdown path awaits an unbounded close again", () => {
  const server = fs.readFileSync(
    path.resolve(__dirname, "..", "control", "sovereign-control-server.js"), "utf8");
  const stop = executableOnly(slice(server, "  async stop(", "  async _handle("));
  assert.match(stop, /closeAllConnections/, "the halfway destroy is what ends a held-open socket");
  assert.match(stop, /timed_out: true/, "the budget must have an end that REPORTS itself");
  assert.doesNotMatch(stop, /await new Promise\(\(resolve\) => server\.close\(\(\) => resolve\(\)\)\)/,
    "the unbounded await is the defect (U334); it may not come back");
});

test("U335: the sentence an operator reads names the workers nothing has verified", () => {
  const summary = summarizeDispatch([
    { node_id: "stale", ready: true, mcp_state: "stale", mcp_fresh: false },
    { node_id: "fresh", ready: true, mcp_state: "connected", mcp_fresh: true,
      task_status: "IN_PROGRESS" },
  ]);
  assert.match(summary.text, /2 READY \(1 MCP-unverified\)/);
  assert.equal(summary.mcp_unverified, 1);
  assert.deepEqual(summary.legs.map((leg) => leg.mcp_fresh), [false, true]);
});

test("U336: the inspector's top-level ok is the AND of the two reads, never a literal", () => {
  const handler = executableOnly(
    slice(MAIN, 'ipcMain.handle("inspector:fetch"', 'ipcMain.handle("statusbar:fetch"'));
  assert.match(handler, /const operationalOk = operational\.available === true/);
  assert.match(handler, /ok: Boolean\(legacy\) && operationalOk/);
  assert.doesNotMatch(handler, /\n\s*ok: true,/,
    "reporting ok:true beside an unreadable half is the defect (U336)");
  // The unreadable half must not be replaced by an empty shape on the way out either.
  assert.match(handler, /model: legacy \? legacy\.model : null/);
  assert.match(handler, /summary: legacy \? legacy\.summary : null/);
});

test("U336: the drawer paints an unreadable half as unreadable, not as zero", () => {
  const render = executableOnly(
    slice(RENDERER, "function renderInspector(res)", "async function refreshInspector"));
  assert.match(render, /op\.available === true/);
  assert.match(render, /shared governed state UNREADABLE/);
  assert.match(render, /artifact\/gate evidence UNREADABLE/);
  assert.match(render, /this is not a count of zero/);
  assert.doesNotMatch(render, /summary: \{ task_count: 0/,
    "a zero-count stand-in for an unreadable feed is the defect (U336)");
  assert.doesNotMatch(render, /taskCount: 0, artifactCount: 0/,
    "…and the same stand-in for the legacy half is the same defect");
});
