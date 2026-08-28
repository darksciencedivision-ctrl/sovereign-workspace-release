"use strict";
/**
 * W-35 — three defects in one log line and the file it lands in (R-56 / R-57).
 *
 * VERIFIED ON THE TREE before repair, because the round-2 desktop report is reviewer-labelled and
 * section 12.1 leaves such claims unadjudicated until re-derived:
 *
 *   - `main.js` logged `argv.join(" ")` for the live conductor session, and
 *     `tools/live/emit_conductor_launch.py:185` appends `--settings <profile.settings_json>` to that
 *     argv. So the authority-boundary PROFILE — its hook command paths included — was reproduced
 *     verbatim into the durable log.
 *   - Worse than durable: `main.js` passes a `rendererSink` that sends EVERY line to the renderer
 *     over `shell:log`, and the renderer console.logs it. The profile therefore reached the
 *     least-trusted surface in the application, which is the one place invariant 29 says not to put
 *     things.
 *   - The logger has no rotation at all (`appendFileSync` per line), and `SOW_MAIN_LOG_FILE` was
 *     used raw as a path with no validation.
 *
 * THE RULE THIS UNIT APPLIES: identify, do not reproduce. A reader must be able to tell WHICH
 * profile a launch used — that is real diagnostic value and invariant 27 asks for it — without the
 * log becoming a copy of it. Naming it by digest satisfies both; dropping the argument entirely
 * would trade one defect for a blind spot.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createMainProcessLogger, redactArgvForLog } = require("../main-process-logger");

const tmpdir = () => fs.mkdtempSync(path.join(os.tmpdir(), "sow-w35-"));

// ---- identify the profile, do not reproduce it -------------------------------------------------

test("W-35 NEGATIVE: a --settings profile is NAMED, never reproduced, in a logged argv", () => {
  const settings = JSON.stringify({
    hooks: { PreToolUse: [{ command: "C:/repo/tools/live/voice_turn_boundary.js" }] },
    permissions: { allow: ["Bash(git status:*)"] },
  });
  const argv = ["claude", "--model", "claude-fable-5", "--settings", settings];

  const line = redactArgvForLog(argv);

  assert.ok(!line.includes("voice_turn_boundary.js"),
    "the profile's hook command path reached the log — this line is mirrored to the renderer");
  assert.ok(!line.includes("PreToolUse") && !line.includes("Bash(git status"),
    "the profile body must not be reproduced in any part");
  // …but it must still be identifiable. A log that hides which profile was used trades a leak for
  // a blind spot, and invariant 27 asks for the launch to be observable.
  assert.match(line, /--settings <profile sha256:[0-9a-f]{12}/,
    "the profile must be identified by digest so two launches can be told apart");
  assert.match(line, /claude --model claude-fable-5/,
    "the rest of argv is diagnostic and must survive");
});

test("W-35: two different profiles are distinguishable, and the same profile is stable", () => {
  const a = redactArgvForLog(["claude", "--settings", '{"a":1}']);
  const b = redactArgvForLog(["claude", "--settings", '{"b":2}']);
  const aAgain = redactArgvForLog(["claude", "--settings", '{"a":1}']);
  assert.notStrictEqual(a, b, "different profiles must not collapse to the same identifier");
  assert.strictEqual(a, aAgain, "the identifier must be stable for the same profile");
});

test("W-35: an argv with no --settings is unchanged", () => {
  const argv = ["ollama", "run", "qwen3:8b"];
  assert.strictEqual(redactArgvForLog(argv), argv.join(" "));
});

// ---- bound the file ----------------------------------------------------------------------------

test("W-35 NEGATIVE: the log file is bounded and rotates instead of growing forever", () => {
  const dir = tmpdir();
  const file = path.join(dir, "main-process.log");
  const logger = createMainProcessLogger({
    file, stdout: { on() {}, write() {} }, stderr: { on() {} }, maxBytes: 4096,
  });
  for (let i = 0; i < 500; i += 1) logger.log(`line ${i} ${"padding".repeat(20)}`);

  const size = fs.statSync(file).size;
  assert.ok(size <= 4096 * 2,
    `the live log grew to ${size} bytes against a 4096-byte ceiling — appendFileSync per line with `
    + "no rotation is an unbounded write on a long-running process");
  // The most recent line must survive rotation: a bound that discards the newest entry has made
  // the log useless at exactly the moment it is read.
  const tail = fs.readFileSync(file, "utf8");
  assert.match(tail, /line 499/, "rotation must keep the newest lines, not the oldest");
});

test("W-35: rotation keeps ONE previous generation, so the bound is on total growth", () => {
  const dir = tmpdir();
  const file = path.join(dir, "main-process.log");
  const logger = createMainProcessLogger({
    file, stdout: { on() {}, write() {} }, stderr: { on() {} }, maxBytes: 2048,
  });
  for (let i = 0; i < 800; i += 1) logger.log(`entry ${i} ${"x".repeat(64)}`);
  const files = fs.readdirSync(dir);
  assert.ok(files.length <= 2,
    `rotation left ${files.length} files (${files.join(", ")}) — an unbounded number of rotated `
    + "generations is the same unbounded disk use with more steps");
});

// ---- validate SOW_MAIN_LOG_FILE ----------------------------------------------------------------

test("W-35 NEGATIVE: a relative or traversing log path is REFUSED, not written to", () => {
  const dir = tmpdir();
  const fallback = path.join(dir, "fallback.log");

  // NOTE the traversal case is built by STRING CONCATENATION, not `path.join`. `path.join`
  // normalises `..` away, so it cannot express the input under test — the first draft of this test
  // used it and asserted against an already-clean path, which the validator rightly accepted.
  //
  // WHAT THIS VALIDATION DOES NOT DO, stated rather than implied: it does not constrain the log to
  // a permitted root. `SOW_MAIN_LOG_FILE` is set by whoever launches the process — the operator —
  // and the self-check harnesses legitimately point it at temp directories, so a root restriction
  // would break them without closing a boundary the operator is not already on. What it closes is
  // a MALFORMED path being used raw and silently.
  for (const bad of ["relative/main.log", `${dir}${path.sep}..${path.sep}..${path.sep}escape.log`]) {
    const refusals = [];
    const logger = createMainProcessLogger({
      file: bad, fallbackFile: fallback, onPathRefused: (why) => refusals.push(why),
      stdout: { on() {}, write() {} }, stderr: { on() {} },
    });
    assert.strictEqual(logger.file, fallback,
      `${bad} was accepted as a log path — an env-supplied path is an arbitrary-append primitive`);
    assert.strictEqual(refusals.length, 1, "a silently ignored override is worse than a refused one");
  }
});

test("W-35 POSITIVE: an ordinary absolute path is still honoured", () => {
  const dir = tmpdir();
  const file = path.join(dir, "logs", "main-process.log");
  const logger = createMainProcessLogger({
    file, stdout: { on() {}, write() {} }, stderr: { on() {} },
  });
  assert.strictEqual(logger.file, file);
  logger.log("hello");
  assert.match(fs.readFileSync(file, "utf8"), /\[shell\] hello/);
});
