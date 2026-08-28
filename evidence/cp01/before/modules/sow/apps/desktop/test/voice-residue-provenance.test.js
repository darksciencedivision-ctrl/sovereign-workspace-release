"use strict";
/**
 * W-39 — the residue block was cleared from a channel the code itself says is not the operator.
 *
 * INVARIANT: only authenticated operator-originated input may clear voice residue; child terminal
 * traffic never may.
 *
 * THE DEFECT, and the reason it is worth a unit: the comment DIRECTLY ABOVE the offending line
 * already stated the rule. `pane:input` bytes "look like the operator typing — this is the channel
 * their keystrokes travel — but xterm.js also emits `onData` for the terminal REPLIES it generates
 * by itself when the pane's own process prints a cursor-position or device-attribute query. The
 * supervised CLI prints into this pane, so it could have elicited an 'operator' byte on demand and
 * disarmed its own restriction: the forged-lifecycle bypass again, one channel over. Only
 * `before-input-event` — the OS input path, which the child is not on — is operator provenance."
 *
 * And then the handler cleared the residue on exactly that channel. The reasoning was written down
 * and the code did the other thing.
 *
 * WHAT THE RESIDUE BLOCK IS FOR: a withheld voice submit records residue so the NEXT delivery
 * refuses until the operator resolves it — otherwise a second spoken sentence is appended to the
 * first and the pair submitted as one prompt the operator never said, badged "Delivered to
 * conductor". A supervised CLI that can clear that block by printing a DA/CPR query can re-open
 * exactly that.
 *
 * WHAT WAS NOT DONE, deliberately (operator ruling): no new provenance flag, and
 * `operatorInputResolvesResidue` is NOT broadened. That predicate exists, is pure and is tested in
 * its own file. The bug was never the predicate — it was the channel calling it.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { operatorKeyKind } = require("../voice/operator-resume");

const MAIN = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");

const slice = (source, from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start > 0 && end > start, `could not locate ${from} … ${to}`);
  return source.slice(start, end);
};
const executableOnly = (region) =>
  region.replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n");

const paneInputHandler = () =>
  executableOnly(slice(MAIN, 'ipcMain.handle("pane:input"', "return manager.write(id, data);"));
const resumeHandler = () =>
  executableOnly(slice(MAIN, "function handleOperatorResumeInput(event, input)", "\n/**"));

test("W-39 NEGATIVE: a synthetic DA/CPR auto-reply cannot clear residue — pane:input never clears", () => {
  const body = paneInputHandler();
  assert.ok(!body.includes("clearConductorInputResidue"),
    "the pane:input handler still clears voice residue. xterm.js emits onData for the terminal "
    + "replies the CHILD elicits, so a supervised CLI printing a cursor-position query clears the "
    + "block that exists to stop two spoken sentences being submitted as one");
  assert.ok(!body.includes("operatorInputResolvesResidue"),
    "the residue predicate is still consulted on the child-reachable channel — the predicate is "
    + "correct, the channel is not");
});

test("W-39: the residue decision moved to the operator-provenance path, not to a new flag", () => {
  const body = resumeHandler();
  assert.match(body, /clearConductorInputResidue\(/,
    "before-input-event is the OS input path the child is not on; the decision belongs there");
  // The existing classification is reused. A second predicate here would be a fork of a decision
  // `operator-resume.js` already makes, and the two would drift.
  assert.match(body, /operatorKeyKind\(input\)/,
    "the existing key classification must drive it — no new provenance flag (operator ruling)");
});

test("W-39: the classification actually distinguishes the two clearing cases", () => {
  // Behavioural, against the real module: the source pins above say WHERE the decision is made;
  // this says the classification it relies on can carry the decision at all.
  assert.strictEqual(operatorKeyKind({ type: "keyDown", key: "Enter" }), "submit");
  assert.strictEqual(operatorKeyKind({ type: "keyDown", key: "c", control: true }),
    "control-combination");
  assert.strictEqual(operatorKeyKind({ type: "keyDown", key: "a" }), "printable");
  // …and that an event which is not operator-typed at all classifies as none, so the branch that
  // guards the clearing cannot be entered by a non-operator event.
  assert.strictEqual(operatorKeyKind({ type: "keyUp", key: "Enter" }), "none");
});

test("W-39: an ordinary printable keystroke does NOT clear the residue", () => {
  const body = resumeHandler();
  // The clearing must be conditional on the two resolving kinds. If it ran for every operator key,
  // typing a single character into the pane would silently discard the block — which is the same
  // defect with a different trigger, and would still pass a test that only checked "it moved".
  assert.match(body, /"submit"|"control-combination"/,
    "the clearing must be gated on the resolving key kinds, not on any operator key");
});
