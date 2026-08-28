"use strict";
/**
 * Phase 19 unit 19.3 — U328, the half of the property that lives in `main.js`.
 *
 * `apps/desktop/test/pane-writer.test.js` proves the GATE refuses. This file proves `main.js` still
 * goes through it — because a gate in a module nobody calls is decoration, and the audit's finding
 * was precisely a call site, not a missing algorithm.
 *
 * `main.js` cannot be `require`d in a test (it is an Electron main process; U338 is the standing
 * register item for that, and unit 19.9 owns the extraction). These are therefore source-shape
 * assertions — which is exactly the class of test the cold audit called unable to distinguish
 * working code from a syntax error. That criticism is answered not by pretending otherwise but by
 * `tools/mutation/system_pane_write_mutations.js`, which splices each known bypass back into
 * `main.js` and requires this file to go RED for every one. A shape assertion that has been shown
 * to fail on the real bypass is worth what its falsification is worth, and no more.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const MAIN = fs.readFileSync(path.join(__dirname, "..", "main.js"), "utf8");

/** `assert.match` against a 180 KB file prints the whole file on failure, which buries the reason.
 *  These say what was looked for and what was not found, and nothing else. */
const mainHas = (re, msg) => assert.ok(re.test(MAIN), `${msg}\n  expected main.js to match ${re}`);
const mainLacks = (re, msg) => assert.ok(!re.test(MAIN), `${msg}\n  but main.js matches ${re}`);

/** The body of a top-level function declaration, by brace matching — so an assertion about
 *  `notifyNode` cannot be satisfied by a line that happens to sit somewhere else in the file. */
function body(name) {
  const decl = new RegExp(`\\n(?:async )?function ${name}\\s*\\(`).exec(MAIN);
  assert.ok(decl, `main.js no longer declares ${name}() at the top level`);
  const open = MAIN.indexOf("{", decl.index + decl[0].length - 1);
  assert.ok(open > 0, `${name}() has no body`);
  let depth = 0;
  for (let i = open; i < MAIN.length; i += 1) {
    if (MAIN[i] === "{") depth += 1;
    else if (MAIN[i] === "}") {
      depth -= 1;
      if (depth === 0) return MAIN.slice(open + 1, i);
    }
  }
  throw new Error(`${name}() body is unbalanced`);
}

test("the system→pane write path is the gate module, not main.js's own bytes", () => {
  mainHas(/require\("\.\/control\/pane-writer"\)/,
    "main.js must obtain the write path from the gated module");
  const write = body("writePanePrompt");
  assert.match(write, /paneWriter\.writePrompt\(/,
    "writePanePrompt must delegate to the gated writer");
  assert.doesNotMatch(write, /manager\s*\??\.\s*write\s*\(/,
    "U328: writePanePrompt must not reach the PTY itself — every byte goes through the gate");
});

test("notifyNode — the caller the cold audit named — routes through the gated writer", () => {
  const notify = body("notifyNode");
  assert.match(notify, /paneWriter\.notifyNode\(/);
  assert.doesNotMatch(notify, /manager\s*\??\.\s*write\s*\(/,
    "U328: notifyNode wrote into panes blind; it may not resolve its own PTY again");
  assert.doesNotMatch(notify, /writePanePrompt\(/,
    "notifyNode must not re-implement pane resolution around the writer's own routing");
});

test("the worker readiness turn still goes through the gate — now from its own module", () => {
  // Unit 19.4 moved the readiness state machine into `control/worker-readiness.js` (U329: the ORDER
  // of its signals had to become testable). The U328 property did not move: the turn still consults
  // the refusal before it types. What changed is where it can be PROVEN — `worker-readiness.test.js`
  // drives the module and asserts zero writes on a refused pane, which is stronger than the source
  // ordering this used to check. What main.js must still do is hand the module the REAL gate rather
  // than a re-implementation, and that is what stays here.
  const binding = MAIN.slice(MAIN.indexOf("const workerReadiness = createWorkerReadiness({"),
    MAIN.indexOf("const runWorkerReadiness ="));
  assert.ok(binding.length > 0, "main.js must build the worker readiness state machine");
  assert.match(binding, /writeRefusal:\s*\(paneId\) => paneWriteRefusalFor\(paneId\)/,
    "readiness must be given the production refusal, not its own screen read");
  assert.match(binding, /writePrompt:\s*\(paneId, prompt\) => writePanePrompt\(paneId, prompt\)/,
    "readiness must type through the gated write path");
  const turn = fs.readFileSync(
    path.join(__dirname, "..", "control", "worker-readiness.js"), "utf8");
  const gateAt = turn.indexOf("io.writeRefusal(");
  const writeAt = turn.indexOf("io.writePrompt(");
  assert.ok(gateAt !== -1 && writeAt !== -1);
  assert.ok(gateAt < writeAt, "a worker showing a modal must be classified, not typed into");
});

test("main.js holds exactly three PTY write sites, and none of them is a system notification", () => {
  // 1) the voice conductor-write binding (operator→pane, gated since 17C)
  // 2) the `pane:input` IPC handler (the operator's own keystrokes)
  // 3) the pane-writer io (system→pane, gated here)
  //
  // SAY WHAT THIS MEASURES, because the first version of this comment said "a fourth is a new
  // ungated path by construction" and that is not what a substring counter can know. It counts
  // spellings of a write ON THE `manager` IDENTIFIER — including `manager?.write(` and spacing,
  // which the round-2 gate-validator demonstrated slipping past the previous pattern with the whole
  // suite green. A write reached through an ALIAS (`const m = manager; m.write(…)`) is invisible to
  // any regex over this file and is NOT claimed to be caught here: that residual is U366(a), and
  // what actually stands behind it today is unit 19.9's extraction of main.js into requirable
  // modules, not this assertion.
  const sites = MAIN.match(/manager\s*\??\.\s*write\s*\(/g) || [];
  assert.strictEqual(sites.length, 3,
    `main.js has ${sites.length} manager.write() sites; every system→pane byte must go through `
    + "control/pane-writer.js (U328)");
  mainHas(/write:\s*\(paneId, data\) => \(manager \? manager\.write\(paneId, data\) : false\)/,
    "the pane-writer io must own the third site");
});

test("the two bindings main.js supplies are the tested ones, not inline re-implementations", () => {
  // A hand-rolled `paneScreen` that answers `readable: true` unconditionally opens the gate for
  // every pane, and no test in this repo could see it — which is why these live in the module.
  // U373 residual (19.4-followon): and it must be bound to `readinessWindow` — the SAME object the
  // readiness state machine classifies through, not a second reader built from the same parts. A
  // `createScreenWindow({...})` call spelled out here would be a second window that can drift from
  // the one under test, which is how the gate came to read 256 KB while readiness read a screen.
  mainHas(/paneScreen:\s*paneScreenFromWindow\(readinessWindow\)/,
    "the screen reader must be the module's, over the shell's one bounded window");
  // 19.6: the resolver is now HOISTED to a const so the in-Electron descriptor self-check can be
  // handed the very same function the write path uses (a check given a re-creation would evidence
  // the re-creation). It is still the module's factory and still the writer's `providerFor` — both
  // halves are pinned, because the hoist is exactly the shape a hand-rolled substitute would take.
  mainHas(/const paneProviderFor = paneProviderResolver\(\{/,
    "the provider resolver must be the module's");
  mainHas(/providerFor:\s*paneProviderFor,/,
    "the pane writer must be given that resolver, not another one");
  mainLacks(/readable:\s*true/,
    "main.js must not assert a pane is readable — paneScreenFromWindow decides that (fail closed)");
  mainLacks(/paneScreen:[^\n]*snapshot\(\)/,
    "the write gate may not read the whole scrollback again (U373)");
});


// ---- W-18a / R-12: a process-level fault must release the durable terminals ---------------------
// `apps/desktop/supervisor.js:25` documents the containment gap itself, and a grep of main.js
// returned NO `unhandledRejection` and NO `uncaughtException` handler. Node >= 15 exits the process
// on an unhandled rejection; teardown is cooperative through `before-quit`, which that exit does
// not run. One missed `.catch()` therefore orphaned every provider CLI, each holding a durable
// terminal whose holder_pid is the shell that just died skipping its release -- so the ledger's
// dead-holder reaping can never reclaim it.
//
// Source-shape assertions, per U338, and GRADED: `tools/mutation/system_pane_write_mutations.js`
// row P27 deletes the handlers and requires this file to go red.

test("W-18a: both process-level faults are handled, and release terminals before exiting", () => {
  mainHas(/process\.on\("unhandledRejection",/,
    "an unhandled rejection exits the process on Node >= 15 and must not strand a durable terminal");
  mainHas(/process\.on\("uncaughtException",/,
    "an uncaught exception must not strand a durable terminal either");

  const fault = body("exitOnUnrecoverableFault");
  assert.match(fault, /completeNormalQuit\(kind\)/,
    "the fault path must run the SAME teardown that releases the durable terminals, not just log");
  assert.match(fault, /faultExitStarted \|\| normalQuitStarted/,
    "a fault teardown must not run twice, nor race a before-quit teardown");
  assert.match(fault, /app\.exit\(1\)/,
    "a teardown that itself fails must still exit, and must exit non-zero");
});

test("W-18a: a teardown reached through a fault never reports success", () => {
  mainHas(/app\.exit\(faultKind \|\| !complete \? 1 : 0\)/,
    "exit 0 after a fault would tell the launcher the process ended cleanly when it did not");
});
