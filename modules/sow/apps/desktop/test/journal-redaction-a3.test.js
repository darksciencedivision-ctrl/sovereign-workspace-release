"use strict";
/**
 * SW-JOURNAL-002-A3 item 1 (F-47): the journal redactor must stop treating the REPL's
 * idle help hint as a filesystem path.
 *
 * This is a PRIVACY control. The narrowing is therefore tested from both sides: the hint
 * and a bare slash survive, and every real path the reviewer named — plus Windows paths
 * and credential names, whose branches this change must not touch — still redacts. If any
 * real-path assertion here can be weakened without the hint test failing, the file has
 * failed its purpose.
 *
 * Measured defect (A3 F-47): cleanText's rule `/` + any non-space run matched `/?` inside
 * `>>> Send a message (/? for help)`; one session journal held 101 [REDACTED:path] tokens,
 * all from that one hint line.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const { cleanText } = require("../control/workspace-journal");

const HINT = ">>> Send a message (/? for help)";

test("F-47: the REPL idle hint is terminal text, not a path, and survives intact", () => {
  const r = cleanText(HINT);
  assert.equal(r.text, HINT);
  assert.doesNotMatch(r.text, /REDACTED:path/);
  assert.equal(r.redactions, 0);
});

test("F-47: a bare slash — between spaces, at end of text, alone — is not a path", () => {
  assert.equal(cleanText("and / or").text, "and / or");
  assert.equal(cleanText("trailing /").text, "trailing /");
  assert.equal(cleanText("/").text, "/");
  assert.doesNotMatch(cleanText("divide a / b now").text, /REDACTED/);
});

test("F-47: every real POSIX path the reviewer named still redacts", () => {
  const cases = [
    ["/etc/passwd", "a path at line start"],
    ["see /home/user/x.txt now", "a path mid-sentence"],
    ["logs live in /var/log", "a path at end of sentence"],
    ["(/usr/bin/env)", "a path inside parentheses"],
    ["failed:\n/opt/app/run --flag", "a path at the start of a later line"],
    ["/.config/app/state", "a dot-initial path segment"],
    ["run /srv/deploy.sh then stop", "an executable path"],
  ];
  for (const [input, why] of cases) {
    const r = cleanText(input);
    assert.match(r.text, /REDACTED:path/, why + " must redact: " + input);
    assert.ok(r.redactions >= 1, why + " must count: " + input);
    assert.ok(r.kinds.includes("journal_privacy"), why + " must be kinded: " + input);
  }
  // The specific segments must not survive in any form.
  assert.doesNotMatch(cleanText("/etc/passwd").text, /etc|passwd/);
  assert.doesNotMatch(cleanText("see /home/user/x.txt now").text, /home|user|x\.txt/);
  assert.doesNotMatch(cleanText("(/usr/bin/env)").text, /usr|bin|env/);
});

test("F-47: protocol-relative // stays untouched, as before the narrowing", () => {
  assert.equal(cleanText("// not a path, a comment style").text,
    "// not a path, a comment style");
});

test("F-47: the Windows-path branch is untouched and still redacts", () => {
  const r = cleanText("file at C:\\Users\\person\\private.txt here");
  assert.match(r.text, /REDACTED:path/);
  assert.doesNotMatch(r.text, /Users|person|private/);
  const unc = cleanText("share \\\\server\\docs\\file.txt");
  assert.match(unc.text, /REDACTED:path/);
  assert.doesNotMatch(unc.text, /server|docs/);
});

test("F-47: the credential-name branch is untouched and still redacts", () => {
  const r = cleanText("OPENAI_API_KEY=sk-" + "x".repeat(30));
  assert.doesNotMatch(r.text, /OPENAI_API_KEY/);
  assert.doesNotMatch(r.text, /sk-xxxx/);
  assert.match(r.text, /REDACTED/);
  assert.ok(r.redactions >= 1);
});

test("F-47 mutation control: restoring the broad rule re-redacts the hint, and only the hint tests notice", () => {
  const filename = require.resolve("../control/workspace-journal");
  const source = fs.readFileSync(filename, "utf8");
  // The narrowing is exactly this lookahead; deleting it restores the pre-A3 broad rule.
  const anchor = '(?!\\/)(?=[^\\s"\'<>?])';
  assert.ok(source.includes(anchor), "the narrowing anchor must exist in the source");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor, "(?!\\/)"), filename);
  // Under the old rule the hint is redacted — this is the decisive difference.
  assert.match(mutant.exports.cleanText(HINT).text, /REDACTED:path/,
    "the broad rule must fail the hint test; otherwise the new tests are not decisive");
  // Under the current rule it is not, while real paths redact under BOTH.
  assert.doesNotMatch(cleanText(HINT).text, /REDACTED:path/);
  assert.match(mutant.exports.cleanText("/etc/passwd").text, /REDACTED:path/);
  assert.match(cleanText("/etc/passwd").text, /REDACTED:path/);
  assert.equal(fs.readFileSync(filename, "utf8"), source, "the control must not modify the source");
});
