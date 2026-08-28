"use strict";
/**
 * Phase 19 unit 19.4 — U329, the half of the property that lives in `main.js`.
 *
 * `worker-readiness.test.js` proves the state machine behaves; `readiness-window-selfcheck.test.js`
 * proves the in-Electron check discriminates. Neither can see the question this file asks: does
 * `main.js` bind readiness — and the self-check it hands its ctx — to the PRODUCTION objects, or to
 * lookalikes? A receipt driven against a re-creation of the write gate would be green and would
 * evidence nothing, which is the exact shape of the defect the round-1 reviewers found (a test
 * passing because its harness stubbed `writeRefusal` to null).
 *
 * `main.js` cannot be `require`d in a test (U338; unit 19.9 owns the extraction), so these are
 * source-shape assertions — the class the cold audit called unable to distinguish working code from
 * a syntax error.
 *
 * WHAT GRADES THEM, stated exactly, because the first version of this paragraph claimed a grading it
 * did not have (round-3 gate-validator, MINOR-2): only the `writeRefusal → paneWriteRefusalFor`
 * binding is mutation-graded, by M8 in `tools/mutation/system_pane_write_mutations.js`, and M8 grades
 * it through `test/system-pane-write-wiring.test.js` rather than through this file.
 * `readiness_signal_mutations.js` does NOT run this suite — its SUITE is `worker-readiness.test.js`
 * and its pins cover `control/worker-readiness.js` alone. The `window`, `record`,
 * `setOperationalState` and self-check-ctx assertions below are therefore ungraded today; that is
 * [[U382]], owner unit 19.9. Saying so is the point: a stated grading that does not exist is the
 * defect this unit keeps finding in its own instruments.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const MAIN = fs.readFileSync(path.join(__dirname, "..", "main.js"), "utf8");

/** The object literal passed to a call, by brace matching from the call site. */
function callArgument(callee) {
  const at = MAIN.indexOf(`${callee}({`);
  assert.ok(at > 0, `main.js no longer calls ${callee}({...})`);
  const open = MAIN.indexOf("{", at);
  let depth = 0;
  for (let i = open; i < MAIN.length; i += 1) {
    if (MAIN[i] === "{") depth += 1;
    else if (MAIN[i] === "}") {
      depth -= 1;
      if (depth === 0) return MAIN.slice(open + 1, i);
    }
  }
  throw new Error(`${callee}({...}) is unbalanced`);
}

test("readiness is bound to the U328 write gate, not to a private write of its own", () => {
  const io = callArgument("createWorkerReadiness");
  assert.match(io, /writeRefusal:\s*\(paneId\)\s*=>\s*paneWriteRefusalFor\(paneId\)/,
    "the refusal readiness waits on must be the production gate's");
  assert.match(io, /writePrompt:\s*\(paneId,\s*prompt\)\s*=>\s*writePanePrompt\(paneId,\s*prompt\)/,
    "the prompt must go out through the gated write path");
  assert.doesNotMatch(io, /manager\s*\??\.\s*write\s*\(/,
    "U328: readiness may not reach the PTY itself");
});

test("readiness classifies through the bounded window instance, never a snapshot", () => {
  const io = callArgument("createWorkerReadiness");
  assert.match(io, /window:\s*readinessWindow/,
    "readiness must be handed the production bounded window");
  assert.doesNotMatch(io, /snapshot\(\)/,
    "U329: no binding readiness reads may be a whole-buffer snapshot");
  const built = callArgument("createScreenWindow");
  assert.match(built, /bufferFor:/,
    "the window is built over the pane's RingBuffer, so the bound is sliceFrom()'s");
  assert.doesNotMatch(built, /snapshot\(\)/);
});

test("readiness reads and writes the REAL launch record, not a copy kept beside it", () => {
  const io = callArgument("createWorkerReadiness");
  assert.match(io, /record:\s*\(paneId\)\s*=>\s*workerLauncher\(\)\.record\(paneId\)/);
  assert.match(io,
    /setOperationalState:\s*\(paneId,\s*state,\s*patch\)\s*=>\s*setWorkerOperationalState\(/);
});

test("the in-Electron check is handed those same production bindings", () => {
  // The ctx is assembled inside the SHELL_SELFCHECK block; each of these is the shipped object by
  // shorthand, which is what makes the receipt's legs evidence about this shell.
  for (const binding of ["readinessWindow,", "setWorkerOperationalState,", "writePanePrompt,",
    "paneWriteRefusalFor,", "workerLauncher,"]) {
    assert.ok(MAIN.includes(`\n        ${binding}`),
      `the self-check ctx must expose the production ${binding.replace(",", "")}`);
  }
});
