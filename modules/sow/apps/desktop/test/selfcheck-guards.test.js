"use strict";
/**
 * Phase 17C `.disarm-authority` — two properties that live in files rather than in behaviour, and
 * that every review so far has had to find by reading.
 *
 *   U185: the OS speech synthesizer is reachable from the packaged app (main `require`s the
 *         self-check modules unconditionally), so EVERY entry point that can invoke the fixture
 *         generator must refuse outside a self-check run. One of the two had the guard. I-V2 /
 *         D-VOICE-02: the product never speaks.
 *   U186: `tools/mutation/pane_input_bypass_mutations.js` is the only artifact that FALSIFIES the
 *         `pane:input` wiring guard, and nothing ran it. It pins the `main.js` it was shown to catch
 *         mutations on, and that pin goes stale silently the moment `main.js` legitimately changes —
 *         at which point the harness refuses to run (exit 3) and the evidence quietly means nothing.
 *         This test is what makes the ordinary suite go red instead.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const DESKTOP = path.resolve(__dirname, "..");
const REPO = path.resolve(DESKTOP, "..", "..");
const SELFCHECK_DIR = path.join(DESKTOP, "selfcheck");
const HARNESS = path.join(REPO, "tools", "mutation", "pane_input_bypass_mutations.js");

test("every caller of the fixture synthesizer refuses outside a self-check run (U185/I-V2)", () => {
  const callers = fs.readdirSync(SELFCHECK_DIR)
    .filter((f) => f.endsWith(".js"))
    .map((f) => ({ file: f, src: fs.readFileSync(path.join(SELFCHECK_DIR, f), "utf8") }))
    .filter((m) => m.src.includes("make_voice_fixture.py"));
  assert.ok(callers.length >= 2, `expected the fixture generator to have callers, found ${callers.length}`);
  for (const caller of callers) {
    // the refusal must precede THE SPAWN, not merely appear somewhere in the file — a module header
    // that mentions the generator is not a guard, and the first mention in one of these files is one
    // EPC-01 P0-2: the interpreter default moved behind python-runtime.js, so the spawn now
    // reads `spawn(defaultPython(), [...defaultPythonArgs(), "…/make_voice_fixture.py"`. Both
    // forms are accepted deliberately — this guard is about WHERE THE GUARD SITS relative to
    // the spawn, not about which interpreter expression the spawn uses.
    const spawnAt = /spawn\(\s*(?:"py"|defaultPython\(\))[\s\S]{0,160}?make_voice_fixture\.py/
      .exec(caller.src);
    assert.ok(spawnAt, `${caller.file} names the fixture generator but no spawn of it was found`);
    const at = spawnAt.index;
    const before = caller.src.slice(Math.max(0, at - 1200), at);
    assert.match(before, /process\.env\.SHELL_SELFCHECK/,
      `${caller.file} can reach the OS speech synthesizer with no SHELL_SELFCHECK guard (I-V2)`);
    assert.match(before, /I-V2|D-VOICE-02/,
      `${caller.file}'s guard must say which invariant it enforces`);
  }
});

test("every self-check module PARSES and LOADS — the headless suite's blind spot (U291)", () => {
  // 18C `.close` shipped a SyntaxError in `op12-acceptance-selfcheck.js` (two `catch` clauses on
  // one `try`) in a work commit whose full suite was green, and it was found only when the packaged
  // Electron run hard-timed-out with no receipt. Nothing headless loads these modules — they are
  // required by `main.js`, which cannot be required in a test — so the entire selfcheck directory
  // was outside every syntax check the repo runs. That is D-P16-0's lesson (headless tests alone
  // shipped a runtime that failed at first launch) reproduced inside the very files that exist to
  // prevent it. A broken module here does not fail loudly: it takes the whole shell down at
  // startup, or wedges the launcher until its hard timeout with nothing written.
  //
  // PARSE every file (no execution, so `run.js` — which spawns Electron at load — is safe to
  // include), then LOAD the module-shaped ones, which is what `main.js` actually does.
  const vm = require("node:vm");
  const files = fs.readdirSync(SELFCHECK_DIR).filter((f) => f.endsWith(".js"));
  assert.ok(files.length >= 20, `expected the self-check modules, found ${files.length}`);
  for (const file of files) {
    const src = fs.readFileSync(path.join(SELFCHECK_DIR, file), "utf8");
    assert.doesNotThrow(() => new vm.Script(src, { filename: file }),
      `${file} does not parse — it would break the packaged shell at startup, and no other test `
      + "in this repo loads it");
  }
  for (const file of files.filter((f) => f !== "run.js")) {
    assert.doesNotThrow(() => require(path.join(SELFCHECK_DIR, file)),
      `${file} does not load — main.js requires it unconditionally at startup`);
  }
});

test("the falsification harness's pinned baseline is the main.js that ships (U186)", () => {
  const harness = fs.readFileSync(HARNESS, "utf8");
  const pin = /const PINNED_BASELINE = "([0-9A-F]{64})"/.exec(harness);
  assert.ok(pin, "the harness must pin the tree its mutations were shown to be caught on");
  const actual = crypto.createHash("sha256")
    .update(fs.readFileSync(path.join(DESKTOP, "main.js"))).digest("hex").toUpperCase();
  assert.strictEqual(actual, pin[1],
    "main.js has changed since the pane:input bypass mutations were last shown to be CAUGHT on it. "
    + "Re-run `npm run test:falsify` from apps/desktop (it restores main.js byte-identically) and "
    + "update PINNED_BASELINE to the hash it reports — an unfalsified guard is not a guard.");
});

test("every falsification harness is runnable by name, not only by memory (U186)", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(DESKTOP, "package.json"), "utf8"));
  assert.match(String(pkg.scripts["test:falsify"] || ""), /pane_input_bypass_mutations\.js/);
  assert.match(String(pkg.scripts["test:falsify:authority"] || ""), /disarm_authority_mutations\.js/);
  // …and every harness in the directory has a script: one added and left unnamed is one nobody runs
  const harnesses = fs.readdirSync(path.join(REPO, "tools", "mutation")).filter((f) => f.endsWith(".js"));
  const named = Object.values(pkg.scripts).join(" ");
  for (const h of harnesses) assert.ok(named.includes(h), `no npm script runs tools/mutation/${h}`);
});
