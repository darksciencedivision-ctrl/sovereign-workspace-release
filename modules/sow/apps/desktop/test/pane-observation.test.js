"use strict";
/**
 * EPC-03 L4-1/L4-2 — what a worker pane is showing, prepared for a conductor to read.
 *
 * Run against a REAL `RingBuffer` through the REAL `createScreenWindow`, not a stub, because the
 * property that matters is a composition: the reader bounds bytes and lines, the redactor removes
 * secrets, and the character bound trims what is left. A stub of any one of them would prove the
 * test author's model of it rather than the thing.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const RingBuffer = require("../../../terminal/session/ring-buffer");
const { createScreenWindow } = require("../control/worker-readiness");
const { observePane, observePanes, OBSERVATION_SCHEMA } = require("../control/pane-observation");

function paneWith(text, { capacity = 256 * 1024 } = {}) {
  const buffer = new (RingBuffer.RingBuffer || RingBuffer)(capacity);
  buffer.push(Buffer.from(text, "utf8"));
  return { buffer, window: createScreenWindow({ bufferFor: () => buffer }) };
}

test("a pane's visible output is observed, with the schema pinned", () => {
  const { window } = paneWith("$ npm test\n2561 passed, 3 skipped\n$ ");
  const obs = observePane(window, "pane-1");
  assert.equal(obs.schema, OBSERVATION_SCHEMA);
  assert.equal(obs.pane_id, "pane-1");
  assert.equal(obs.answerable, true);
  assert.match(obs.text, /2561 passed/);
});

test("ANSI escapes never reach the conductor", () => {
  // The reader already normalises through plainScreen; this pins that the observation inherits it
  // rather than reading around it.
  const { window } = paneWith("[32mPASS[0m ]0;titleok\n");
  const obs = observePane(window, "pane-1");
  assert.ok(!obs.text.includes(""), JSON.stringify(obs.text));
  assert.match(obs.text, /PASS/);
});

test("a secret in the pane does not reach the conductor, and the removal is reported", () => {
  const secret = "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAA";
  const { window } = paneWith(`$ echo $ANTHROPIC_API_KEY\n${secret}\n$ `);
  const obs = observePane(window, "pane-1");
  assert.ok(!obs.text.includes(secret), obs.text);
  assert.ok(obs.redactions >= 1);
  assert.ok(obs.redaction_kinds.includes("api_key"), JSON.stringify(obs.redaction_kinds));
});

test("redaction happens BEFORE the character bound, not after", () => {
  // The bug this pins: truncating first splits a secret across the boundary and leaves the
  // surviving half matched by NO rule, because every vendor rule keys off the prefix.
  //
  // The first version of this test put the secret at the start of a long window, and a mutation
  // run showed it proved nothing: truncate-first simply DROPPED the secret and the test passed.
  // So the cut is now placed deliberately INSIDE the secret. `maxChars` is chosen so that
  // `full.length - maxChars` lands part-way through it: redact-first turns the whole span into a
  // marker, truncate-first hands the conductor the tail of a live credential.
  const secret = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345";   // 36 chars
  const suffix = secret.slice(16);                          // what a mid-secret cut would strand
  const trailer = "\nnext line of ordinary pane output";
  const filler = "filler ".repeat(100);
  const { window } = paneWith(`${filler}${secret}${trailer}\n`);
  // Keep the last (secret.length - 16) + trailer characters: the cut falls 16 chars into it.
  const obs = observePane(window, "pane-1",
    { maxChars: (secret.length - 16) + trailer.length, maxLines: 500 });
  assert.ok(obs.truncated, "the window must actually be truncated for this test to mean anything");
  assert.ok(!obs.text.includes(suffix),
    `a mid-secret truncation stranded the tail of a credential:\n${obs.text}`);
  assert.ok(!obs.text.includes("ghp_"), obs.text);
});

test("the character bound keeps the TAIL and reports what it dropped", () => {
  const lines = Array.from({ length: 300 }, (_, i) => `line ${i}`).join("\n");
  const { window } = paneWith(lines);
  const obs = observePane(window, "pane-1", { maxChars: 200, maxLines: 500 });
  assert.ok(obs.chars <= 200, `chars ${obs.chars}`);
  assert.equal(obs.truncated, true);
  assert.ok(obs.dropped_chars > 0);
  // What a pane is SHOWING is at the bottom; the top is scrollback nobody asked for.
  assert.match(obs.text, /line 299/);
  assert.ok(!obs.text.includes("line 0\n"), obs.text.slice(0, 80));
});

test("a pane with no buffer is UNANSWERABLE, never an empty success", () => {
  const window = createScreenWindow({ bufferFor: () => null });
  const obs = observePane(window, "pane-9");
  assert.equal(obs.answerable, false);
  assert.equal(obs.text, "");
  assert.match(obs.reason, /no readable stream buffer|not answerable/i);
});

test("a reader that throws produces an honest record, not an exception", () => {
  // This sits on the conductor's path. A pane that cannot be read must not take the dispatch.
  const window = createScreenWindow({ bufferFor: () => { throw new Error("gone"); } });
  const obs = observePane(window, "pane-9");
  assert.equal(obs.answerable, false);
  assert.equal(typeof obs.reason, "string");
});

test("a missing window is refused rather than assumed empty", () => {
  for (const bad of [null, undefined, {}, 42]) {
    const obs = observePane(bad, "pane-1");
    assert.equal(obs.answerable, false);
    assert.equal(obs.schema, OBSERVATION_SCHEMA);
  }
});

test("the observation carries NO leg and no execution claim", () => {
  const { window } = paneWith("worker output\n");
  const obs = observePane(window, "pane-1");
  assert.equal(obs.legs, undefined);
  assert.equal(obs.executed, undefined);
  assert.match(obs.note, /Not a claim that it ran anything/);
});

test("several panes share ONE budget rather than one budget each", () => {
  // The conductor has one context window, not one per pane. A scheme that gave each pane the full
  // budget would let four panes overrun it fourfold without any single record looking wrong.
  const buffers = new Map([
    ["pane-1", Buffer.from("a".repeat(5000), "utf8")],
    ["pane-2", Buffer.from("b".repeat(5000), "utf8")],
    ["pane-3", Buffer.from("c".repeat(5000), "utf8")],
  ]);
  const rings = new Map();
  for (const [id, bytes] of buffers) {
    const ring = new (RingBuffer.RingBuffer || RingBuffer)(256 * 1024);
    ring.push(bytes);
    rings.set(id, ring);
  }
  const window = createScreenWindow({ bufferFor: (id) => rings.get(id) || null });
  const observed = observePanes(window, [...rings.keys()], { totalMaxChars: 1200 });
  assert.equal(observed.length, 3);
  const total = observed.reduce((n, o) => n + o.chars, 0);
  assert.ok(total <= 1200, `three panes used ${total} of a 1200 budget`);
});

test("an empty pane list observes nothing rather than everything", () => {
  const { window } = paneWith("x\n");
  assert.deepEqual(observePanes(window, []), []);
  assert.deepEqual(observePanes(window, null), []);
});
