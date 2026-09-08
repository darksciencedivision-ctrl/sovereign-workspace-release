"use strict";
/**
 * SW-ORCH-001 F-21 — the conductor's delegation is reachable by the operator.
 *
 * THE DEFECT. `runObjective` (main.js), `conductor:run-objective` (ipcMain), and `runObjective`
 * (preload) have all existed since EPC-03. The only reference to the preload method anywhere in
 * the renderer was `channel-sweep.js`, a channel-closure probe. So the loop main.js describes as
 * joined — operator objective → governed dispatch → delegation → candidates — had no operator
 * entry point, `delegateToPane` sat wired and uninvoked, and no synthesized worker result could
 * ever reach the conductor. Voice terminated in the same place for the same reason: it shares
 * `deliverConductorChat` with typed text.
 *
 * EVIDENCE SHAPE. These are SOURCE PINS and are named as such, following the convention
 * `runtime-honesty-wiring.test.js` sets: `renderer/renderer.js` runs in a browser context with no
 * module boundary and this repository carries no DOM harness. The behaviour underneath is driven
 * where it can be driven — `conductor-delegation.test.js` for the delegation itself,
 * `conductor-dispatch-source.test.js` for the feed, `channel-sweep.test.js` for the channel — and
 * the operator-visible result is the s7 acceptance run. What these pins catch is precisely how
 * this defect arose and how it would return: the modules were all fine, the caller was missing.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const RENDERER = fs.readFileSync(
  path.resolve(__dirname, "..", "renderer", "renderer.js"), "utf8");
const INDEX = fs.readFileSync(
  path.resolve(__dirname, "..", "renderer", "index.html"), "utf8");
const PRELOAD = fs.readFileSync(path.resolve(__dirname, "..", "preload.js"), "utf8");

const slice = (source, from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start > 0 && end > start, `could not locate ${from} … ${to}`);
  return source.slice(start, end);
};

/** Whole-line and block comments removed, so a pin cannot be satisfied by the prose about it —
 *  the MINOR-1 shape `runtime-honesty-wiring.test.js` records. */
const executableOnly = (region) =>
  region.replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n");

const DELEGATE_REGION = () => executableOnly(
  slice(RENDERER, "const delegateBtn = document.getElementById", "// ---- routing/artifact"));

// --- the defect itself -------------------------------------------------------------------------

test("F-21: the renderer actually calls runObjective, not only the channel sweep", () => {
  const callers = RENDERER.split("\n")
    .map((line, i) => [i + 1, line])
    .filter(([, line]) => /S\.runObjective\s*\(/.test(line) && !/^\s*(\/\/|\*)/.test(line));
  assert.ok(callers.length >= 1,
    "renderer.js must invoke S.runObjective — this is the whole of F-21");
});

test("F-21: the operator control exists in the markup and is wired", () => {
  assert.match(INDEX, /id="conductor-delegate"/,
    "the composer must carry a delegate control");
  assert.match(DELEGATE_REGION(), /delegateBtn\.addEventListener\("click"/,
    "the control must be wired to a handler");
  assert.match(DELEGATE_REGION(), /S\.runObjective\(\{ objective: text \}\)/,
    "the handler must pass the operator's text as the objective");
});

// --- explicit, not automatic (s7.2 / s7.3) -----------------------------------------------------

test("F-21: delegation is a separate action from sending a message", () => {
  const button = slice(INDEX, 'id="conductor-delegate"', "</button>");
  assert.match(button, /type="button"/,
    "the delegate control must NOT be the form's submit action, or Enter in the composer would "
    + "delegate every message the operator types");

  const submit = executableOnly(slice(
    RENDERER, 'document.getElementById("conductor-form").addEventListener("submit"',
    "// ---- EPC-03"));
  assert.match(submit, /S\.sendOperatorText\(text\)/,
    "submitting the composer still sends a message");
  assert.doesNotMatch(submit, /runObjective/,
    "submitting the composer must never delegate — most messages are conversation, and only the "
    + "operator says when a message is work");
});

test("F-21: voice never becomes an objective by its content", () => {
  // The voice path shares deliverConductorChat with typed text. A spoken utterance may reach the
  // conductor; it may not decide on its own to spend worker time.
  const voice = executableOnly(slice(
    RENDERER,
    "// ---- Phase 17C `.mic`: push-to-talk over the real microphone",
    "// ---- shell:layout"));
  assert.ok(voice.includes("S.captureVoice"),
    "sanity: this really is the push-to-talk region");
  assert.doesNotMatch(voice, /runObjective/,
    "the push-to-talk path must not call runObjective");
});

// --- honest availability (s7.4) ----------------------------------------------------------------

test("F-21: the control is unavailable with a stated reason, from state the renderer holds", () => {
  const region = DELEGATE_REGION();
  assert.match(region, /function delegateBlockedReason\(\)/);
  assert.match(region, /conductor\.live !== true/,
    "a conductor that is not running is a reason");
  assert.match(region, /liveWorkerPaneCount\(\) < 1/,
    "no live worker pane is a reason");
  assert.match(region, /delegateInFlight/,
    "a dispatch already in flight is a reason");
  assert.match(region, /aria-disabled/,
    "unavailability is conveyed to assistive tech");
  assert.match(region, /whyEl\.textContent/,
    "the reason is RENDERED beside the control, not parked in a tooltip");
});

test("F-21: the control is never `disabled`, so a press always produces an answer", () => {
  /**
   * The defect this pins, measured on the operator's host: "I put two plus two in the objective
   * and press delegate, but nothing happens." The conductor was unstarted, so the control set
   * `disabled = true` — and a disabled button dispatches NO click event, so the handler's own
   * refusal line never ran and the reason sat unread in a `title` attribute. Silence is the one
   * answer a governed surface must never give: it is indistinguishable from a broken product.
   */
  const region = DELEGATE_REGION();
  assert.doesNotMatch(region, /delegateBtn\.disabled\s*=/,
    "setting .disabled suppresses the click event and with it the refusal the operator needs");
  assert.match(region, /delegateBtn\.addEventListener\("click"/,
    "the handler must be reachable in every state");
  // the handler's FIRST act is to answer the blocked case, before touching the objective
  const handler = region.slice(region.indexOf('delegateBtn.addEventListener("click"'));
  assert.match(handler.slice(0, 260), /if \(why\) \{ line\("warn"/,
    "a blocked press must render the reason rather than returning silently");
});

test("F-21: every unavailability reason names what to do about it", () => {
  const reasons = executableOnly(
    slice(RENDERER, "function delegateBlockedReason()", "function refreshDelegateControl()"));
  // "the conductor is not running" is true and useless on its own.
  assert.match(reasons, /press ▶ live|send it a message/,
    "the conductor case must name the remedy");
  assert.match(reasons, /open a pane and pick a model/,
    "the no-worker case must name the remedy");
  assert.match(reasons, /wait for it to finish/,
    "the in-flight case must say what the operator is waiting on");
});

test("F-21: availability is re-evaluated on the pushes that change it", () => {
  const exec = executableOnly(RENDERER);
  const refreshes = exec.match(/window\.__sovRefreshDelegate\(\)/g) || [];
  assert.ok(refreshes.length >= 2,
    "both shell:state (worker panes) and shell:conductor (conductor liveness) must re-evaluate "
    + "the control, or it reflects whatever was true when the bar was built");
});

// --- honesty of what is rendered (s7.5 / s7.6 / s7.7) -------------------------------------------

test("F-21: a screen-read candidate is surfaced as one, never as a node's own publication", () => {
  const region = DELEGATE_REGION();
  assert.match(region, /self_published === false/,
    "the surface must branch on self_published");
  assert.match(region, /self_published: false/,
    "and say so in the operator-visible text");
  assert.match(region, /d\.candidate\.source/,
    "and name the source (observed_pane_output)");
  assert.match(region, /read from the pane's output/,
    "a reviewer looking at this surface must be able to tell a read candidate from a published one");
});

test("F-21: every governed refusal is surfaced verbatim, never collapsed", () => {
  const region = DELEGATE_REGION();
  assert.match(region, /res\.ok !== true/, "a non-dispatch is handled");
  assert.match(region, /res && res\.reason/, "with the governed reason carried through");
  assert.match(region, /d\.refused\.reason/, "a refused pane write shows the gate's own reason");
  assert.match(region, /d\.delivered !== true/, "an undelivered assignment is reported");
  assert.match(region, /d\.answered !== true/, "a silent pane is reported");
  assert.doesNotMatch(region, /catch \(e\) \{\s*\}/, "no swallowed failure");
});

test("F-21: the OWED live-worker leg keeps saying so after a delegation", () => {
  const region = DELEGATE_REGION();
  assert.match(region, /live_workers_owed/,
    "U58 is not discharged by making delegation reachable, and the surface must not imply it is");
  assert.match(region, /still OWED/);
});

// --- nothing new was invented (s7.1) -----------------------------------------------------------

test("F-21: no new IPC channel or preload method was added for this", () => {
  const channels = PRELOAD.match(/conductor:run-objective/g) || [];
  assert.strictEqual(channels.length, 1,
    "the existing channel is reused exactly once; a second one would be a parallel path");
  assert.doesNotMatch(DELEGATE_REGION(), /ipcRenderer/,
    "the renderer reaches main only through the preload surface (contextIsolation, invariant 29)");
});
