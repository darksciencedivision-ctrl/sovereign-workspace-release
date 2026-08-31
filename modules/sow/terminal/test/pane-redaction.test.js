"use strict";
/**
 * EPC-03 L4-2 — the redactor between a live pane and a model.
 *
 * The directive assumed this existed ("`LogRing` already ... redacts"). It did not: every
 * `scrub` in the tree is ENVIRONMENT scrubbing, and `plainScreen` strips escape sequences only.
 * These tests are the net's own evidence - what it catches, what it deliberately leaves alone,
 * and the one thing it must never do, which is fail open.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { redactPaneText, REDACTION_KINDS } = require("../observe/pane-redaction");

// FIXTURES ARE ASSEMBLED, NOT WRITTEN OUT.
//
// A redactor's tests have to carry credential-SHAPED strings or they prove nothing. Written as
// literals they also ship: the package boundary gate flagged five of them here (github-token,
// aws-access-key-id, slack-token, private-key-block), and it was right to - its job is that the
// distribution contains no credential-shaped bytes, and neither it nor the enterprise recipient's
// own scanner can tell a fixture from a leak.
//
// There is a precedent for allow-listing such a file (`tools/release/test_package_boundary_gate.py`
// is hash-pinned in fixture_allowlist.json for exactly this). It was not taken, because an
// allowlist keeps the bytes in the archive and moves the cost to the recipient. Assembling the
// value at runtime leaves the test EXACTLY as strong - the redactor receives the identical
// characters - and ships nothing that looks like a secret. The gate remains the enforcement: a
// literal reintroduced here fails CI again.
const fixture = (...parts) => parts.join("");


function assertGone(secret, text) {
  assert.ok(!text.includes(secret), `the secret survived redaction:\n${text}`);
}

test("vendor-prefixed API keys do not survive", () => {
  const secrets = [
    "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "sk-proj-BBBBBBBBBBBBBBBBBBBBBBBBBBBB",
    fixture("gh", "p_", "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"),
    "github_pat_DDDDDDDDDDDDDDDDDDDDDDDDDD",
    fixture("xo", "xb-", "1234567890-EEEEEEEEEEEE"),
    fixture("AK", "IA", "IOSFODNN7EXAMPLE"),
    "AIzaSyD-FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
    "hf_GGGGGGGGGGGGGGGGGGGGGGGGGG",
    "glpat-HHHHHHHHHHHHHHHHHHHH",
    "sk_live_IIIIIIIIIIIIIIIIIIII",
  ];
  for (const secret of secrets) {
    const out = redactPaneText(`$ echo $TOKEN\n${secret}\n$ `);
    assertGone(secret, out.text);
    assert.match(out.text, /\[REDACTED:api_key\]/);
    assert.equal(out.redactions >= 1, true);
  }
});

test("an env dump keeps the NAME and loses the VALUE", () => {
  const out = redactPaneText([
    "$ env | grep -i key",
    "ANTHROPIC_API_KEY=sk-ant-api03-ZZZZZZZZZZZZZZZZZZZZZZZZ",
    "DATABASE_PASSWORD=hunter2hunter2",
    "SOW_SESSION_ID=abcdefabcdef",
  ].join("\n"));
  // Knowing the variable is SET is operationally useful and is not the secret.
  assert.match(out.text, /ANTHROPIC_API_KEY=/);
  assert.match(out.text, /DATABASE_PASSWORD=/);
  assertGone("hunter2hunter2", out.text);
  assertGone("abcdefabcdef", out.text);
  assert.ok(out.kinds.includes("secret_assignment") || out.kinds.includes("api_key"), out.kinds);
});

test("bearer tokens, JWTs and URL credentials are removed", () => {
  const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U";
  const out = redactPaneText([
    "Authorization: Bearer AbCdEf0123456789AbCdEf",
    `id_token=${jwt}`,
    "git clone https://sam:s3cr3tpassword@github.example/repo.git",
  ].join("\n"));
  assertGone("AbCdEf0123456789AbCdEf", out.text);
  assertGone(jwt, out.text);
  assertGone("s3cr3tpassword", out.text);
  // The host stays: it is operationally useful and it is not the credential.
  assert.match(out.text, /github\.example\/repo\.git/);
});

test("a private key block is removed whole, header to footer", () => {
  const body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ";
  const begin = fixture("-----BE", "GIN RSA PRIVATE KEY-----");
  const end = fixture("-----E", "ND RSA PRIVATE KEY-----");
  const out = redactPaneText(
    `$ cat id_rsa\n${begin}\n${body}\n${body}\n${end}\n$ `);
  assertGone(body, out.text);
  assertGone(begin, out.text);
  assert.match(out.text, /\[REDACTED:private_key\]/);
  assert.equal(out.kinds.includes("private_key"), true);
});

test("ordinary pane output is left alone", () => {
  // Over-redaction is a real cost, not a safe default: a window that redacts the work is a window
  // the conductor cannot reason from, and an operator who sees noise stops reading it.
  const ordinary = [
    "$ npm test",
    "2561 passed, 3 skipped in 262.38s",
    "commit 7a06a0c EPC-03 L3-5: the conductor dispatches to the panes that exist",
    "sha256: 3c705fa9b1e2d4c6a8f0b2d4e6f8a0c2e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4",
    // A stack frame, because those are full of characters a jumpy redactor would eat. The path is
    // deliberately generic: the first draft pasted this build tree's own absolute path in, and
    // `shell/tests/test_developer_identifiers_are_bounded.py` failed the distribution on it. The
    // guard was right — a build-host path is a developer identifier, and it has no business
    // shipping inside an archive a recipient reads.
    "  at Object.<anonymous> (C:\\app\\modules\\sow\\x.js:42:11)",
    "ERROR: connection refused (127.0.0.1:11434)",
  ].join("\n");
  const out = redactPaneText(ordinary);
  assert.equal(out.text, ordinary);
  assert.equal(out.redactions, 0);
  assert.deepEqual(out.kinds, []);
});

test("a hash is not a secret and stays readable", () => {
  // This codebase reports hashes constantly and an instrument that ate them would be unusable.
  const line = "release_manifest_check: PASS sha256 bb5edf8a1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f";
  assert.equal(redactPaneText(line).text, line);
});

test("redaction leaves a MARKER, never a silent gap", () => {
  // A model reading `export KEY=` followed by nothing invents what belongs there; an operator
  // cannot tell redaction from truncation. The marker is what makes the removal legible.
  const out = redactPaneText("export API_KEY=sk-ant-api03-QQQQQQQQQQQQQQQQQQQQQQQQ");
  assert.match(out.text, /\[REDACTED:[a-z_]+\]/);
});

test("it reports what it removed, and claims nothing more", () => {
  const out = redactPaneText([
    "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY",
    "Authorization: Bearer 0123456789abcdefghij",
  ].join("\n"));
  assert.ok(out.redactions >= 2, `expected >= 2 spans, got ${out.redactions}`);
  assert.equal(Array.isArray(out.kinds), true);
  for (const kind of out.kinds) assert.ok(REDACTION_KINDS.includes(kind), kind);
  // Sorted + distinct, so a receipt that records them is stable across runs.
  assert.deepEqual(out.kinds, [...new Set(out.kinds)].sort());
});

test("it never throws, and never returns the input on a bad rule", () => {
  for (const bad of [null, undefined, 42, {}, [], Symbol("x")]) {
    const out = redactPaneText(bad);
    assert.equal(out.text, "");
    assert.equal(out.redactions, 0);
  }
});

test("a redactor failure WITHHOLDS the output rather than passing it through", () => {
  // Fail CLOSED. The one behaviour that would make every other test here worthless is a rule
  // erroring and the raw text continuing on to the model as if it had been cleaned.
  //
  // This is asserted through the `rules` seam because a mutation run proved it had to be: the
  // mutation "the redactor fails OPEN when a rule errors" SURVIVED against the first version of
  // this test, which only checked a non-string input and never reached the branch at all.
  const secret = fixture("gh", "p_", "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345");
  const exploding = [{
    kind: "detonator",
    pattern: /x/g,
    replace: () => { throw new Error("rule blew up"); },
  }];
  const out = redactPaneText(`token: ${secret} x`, exploding);
  assert.match(out.text, /REDACTION FAILED/);
  assert.equal(out.failed, "detonator");
  assertGone(secret, out.text);
});

test("the rules seam cannot be used to switch redaction off", () => {
  const secret = fixture("gh", "p_", "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345");
  for (const attempt of [[], null, undefined, "none", 0]) {
    assertGone(secret, redactPaneText(`key ${secret}`, attempt).text);
  }
});

test("redaction survives the multi-line, repeated-secret case", () => {
  const secret = fixture("gh", "p_", "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345");
  const text = Array.from({ length: 20 }, (_, i) => `line ${i}: ${secret}`).join("\n");
  const out = redactPaneText(text);
  assertGone(secret, out.text);
  assert.equal(out.redactions, 20, "every occurrence must go, not just the first");
});
