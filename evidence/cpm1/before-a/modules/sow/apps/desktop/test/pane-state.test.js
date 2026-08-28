"use strict";
/**
 * Phase 17C `.close-revalidate` — the precondition that stops a spoken sentence being typed into a
 * live CLI's own permission prompt (both mandatory reviews' convergent BLOCKING finding).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { paneAcceptsTypedText, visibleText } = require("../voice/pane-state");

const ESC = String.fromCharCode(27);
//: The live `claude` input box as this host's pane really draws it (from the `.close` receipt's
//: rendered excerpt), with a repaint's worth of escape sequences in it.
const INPUT_FRAME = `${ESC}[2J${ESC}[H  Claude Code v2.1.220  Fable 5 - Claude Max\r\n`
  + `${ESC}[38;5;242m────────────────────────${ESC}[0m\r\n`
  + `${ESC}[1m❯ ${ESC}[0m\r\n`
  + `${ESC}[38;5;242m────────────────────────${ESC}[0m\r\n`
  + `  ⏸ plan mode on\r\n`;
//: The permission prompt it draws instead when it wants a protected action confirmed.
const PROMPT_FRAME = `${ESC}[2J${ESC}[H  Bash command\r\n  rm -rf .sovereign_store\r\n\r\n`
  + `  Do you want to proceed?\r\n  ❯ 1. Yes\r\n    2. Yes, and don't ask again\r\n    3. No\r\n`;

test("the live input box is recognised as accepting typed text", () => {
  const v = paneAcceptsTypedText(INPUT_FRAME);
  assert.strictEqual(v.accepting, true);
  assert.strictEqual(v.state, "input");
});

test("an open permission prompt refuses the write — the body never reaches it", () => {
  const v = paneAcceptsTypedText(INPUT_FRAME + PROMPT_FRAME);
  assert.strictEqual(v.accepting, false);
  assert.strictEqual(v.state, "prompt");
  assert.match(v.reason, /confirmation prompt/);
  assert.ok(v.evidence && /proceed|Yes/i.test(v.evidence));
});

test("THE SCENARIO: the prompt is the LAST thing drawn, however much input chrome precedes it", () => {
  // the operator has been chatting for a while; then a tool call opens the gate.
  const stream = INPUT_FRAME + "● working on it\r\n" + INPUT_FRAME + PROMPT_FRAME;
  assert.strictEqual(paneAcceptsTypedText(stream).state, "prompt");
});

test("the prompt being dismissed puts the pane back in an accepting state", () => {
  assert.strictEqual(paneAcceptsTypedText(PROMPT_FRAME + INPUT_FRAME).state, "input");
});

test("a pane with no recognised chrome is REFUSED, not assumed accepting", () => {
  const v = paneAcceptsTypedText("PS D:\\work> Get-ChildItem\r\nMode  LastWriteTime  Name\r\n");
  assert.strictEqual(v.accepting, false);
  assert.strictEqual(v.state, "unknown");
  assert.match(v.reason, /fail closed/);
});

test("unknown chrome AFTER a recognised input frame is refused — history is not current state", () => {
  const v = paneAcceptsTypedText(INPUT_FRAME
    + "\r\nVendor confirmation changed shape in this release\r\nChoose an option to continue\r\n");
  assert.strictEqual(v.accepting, false);
  assert.strictEqual(v.state, "unknown");
  assert.match(v.reason, /after the last input marker|fail closed/i);
});

test("unknown same-line chrome after the input marker is refused too", () => {
  const v = paneAcceptsTypedText(`${ESC}[H❯\r\n  ? for shortcuts  CONFIRM WITH ENTER`);
  assert.strictEqual(v.accepting, false);
  assert.strictEqual(v.state, "unknown");
});

test("bypass-permissions chrome is never positive evidence that voice may write", () => {
  const bypass = `${ESC}[2J${ESC}[H  Claude Code\r\n❯ \r\n  ⏸ bypass permissions on\r\n`;
  const v = paneAcceptsTypedText(bypass);
  assert.strictEqual(v.accepting, false);
  assert.notStrictEqual(v.state, "input");
});

test("accept-edits mode is also unsafe for direct voice delivery", () => {
  const v = paneAcceptsTypedText(`${ESC}[H❯\r\n  ⏸ accept edits on · ? for shortcuts\r\n`);
  assert.strictEqual(v.accepting, false);
  assert.strictEqual(v.state, "prompt");
});

test("manual mode is input state only: refused alone, accepted behind the supervisor boundary", () => {
  const frame = `${ESC}[H❯\r\n  ⏸ manual mode on · ? for shortcuts\r\n`;
  const alone = paneAcceptsTypedText(frame);
  assert.strictEqual(alone.accepting, false);
  assert.strictEqual(alone.state, "unknown");
  assert.match(alone.reason, /supervisor-owned|not authority/i);
  const bound = paneAcceptsTypedText(frame, { supervisorBoundary: true });
  assert.strictEqual(bound.accepting, true);
  assert.strictEqual(bound.state, "input");
});

test("the live manual footer's exact effort suffix is accepted only behind the boundary", () => {
  const frame = `${ESC}[H❯\r\n  ⏸ manual mode on · ? for shortcuts · ← for agents ● high · /effort\r\n`;
  assert.strictEqual(paneAcceptsTypedText(frame).accepting, false);
  const bound = paneAcceptsTypedText(frame, { supervisorBoundary: true });
  assert.strictEqual(bound.accepting, true);
  assert.strictEqual(bound.state, "input");
});

test("a later plan repaint supersedes historical manual mode", () => {
  const v = paneAcceptsTypedText(
    `${ESC}[H❯\r\n  ⏸ manual mode on · ? for shortcuts\r\n`
    + `${ESC}[H❯\r\n  ⏸ plan mode on · ? for shortcuts · ← for agents\r\n`);
  assert.strictEqual(v.accepting, true);
  assert.strictEqual(v.state, "input");
});

test("the realistic plan footer's exact shortcut suffix is accepted", () => {
  const v = paneAcceptsTypedText(`${ESC}[H❯\r\n  ⏸ plan mode on · ? for shortcuts · ← for agents\r\n`);
  assert.strictEqual(v.accepting, true);
});

test("an empty / silent pane is refused", () => {
  for (const empty of ["", "   \r\n", null, undefined, Buffer.alloc(0)]) {
    const v = paneAcceptsTypedText(empty);
    assert.strictEqual(v.accepting, false, `${JSON.stringify(empty)} must not be accepting`);
    assert.strictEqual(v.state, "unknown");
  }
});

test("an ordinary numbered list in a conductor answer does not read as a prompt", () => {
  // The gate must not fire on ordinary output, or the operator learns to ignore it.
  const answer = "● Here is the plan:\r\n  1. Read the file\r\n  2. Yes it compiles\r\n  3. Ship\r\n";
  assert.strictEqual(paneAcceptsTypedText(INPUT_FRAME + answer + INPUT_FRAME).state, "input");
});

test("other real confirmation shapes are refused too", () => {
  for (const shape of ["Overwrite the file? (y/n) ", "Continue? [y/N]", "Press Enter to confirm",
                       "Do you want to make this edit to main.js?"]) {
    const v = paneAcceptsTypedText(INPUT_FRAME + shape);
    assert.strictEqual(v.accepting, false, `${shape} must refuse`);
    assert.strictEqual(v.state, "prompt");
  }
});

test("markers split across a repaint's control codes are still read", () => {
  const split = `Do you want to${ESC}[1C proceed?${ESC}[K\r\n❯ 1. Yes`;
  assert.strictEqual(paneAcceptsTypedText(INPUT_FRAME + split).state, "prompt");
});

test("visibleText removes escapes without inventing or dropping words", () => {
  const t = visibleText(`${ESC}[38;5;242m? for shortcuts${ESC}[0m`);
  assert.match(t, /\? for shortcuts/);
  assert.ok(!t.includes(ESC));
});

test("a Buffer is accepted as well as a string (main reads the ring buffer)", () => {
  assert.strictEqual(paneAcceptsTypedText(Buffer.from(INPUT_FRAME, "utf8")).accepting, true);
});

//: The vendor's own usage notice, exactly as this host's pane drew it on 2026-07-30 with the input
//: box open. It is STATUS TEXT, not an affordance — but it is text, and the "unknown chrome after the
//: input marker" rule refused a delivery for it (U165). An operator whose voice input dies at 90% of
//: a session limit has lost the feature for the rest of that window, with a refusal reason that
//: blames "unrecognized pane chrome".
const USAGE_NOTICE = "  You've used 90% of your session limit · resets 3:30pm\r\n";

test("the vendor's usage notice does not revoke a still-open input box (U165)", () => {
  const v = paneAcceptsTypedText(INPUT_FRAME + USAGE_NOTICE);
  assert.strictEqual(v.accepting, true, v.reason);
  assert.strictEqual(v.state, "input");
});

test("…on the same collapsed line as the footer hints, which is how the pane really drew it", () => {
  const sameLine = `${ESC}[1m❯ ${ESC}[0m\r\n  ⏸ manual mode on · ? for shortcuts · ← for agents `
    + "You've used 90% of your session limit\r\n";
  const v = paneAcceptsTypedText(sameLine, { supervisorBoundary: true });
  assert.strictEqual(v.accepting, true, v.reason);
});

test("…and it does not become a licence for whatever follows it", () => {
  // The allowance is for the notice itself, not for everything after the last input marker.
  const v = paneAcceptsTypedText(INPUT_FRAME + USAGE_NOTICE + PROMPT_FRAME);
  assert.strictEqual(v.accepting, false);
  assert.strictEqual(v.state, "prompt");
  const unknown = paneAcceptsTypedText(INPUT_FRAME + USAGE_NOTICE + "  Some modal nobody knows\r\n");
  assert.strictEqual(unknown.accepting, false);
  assert.strictEqual(unknown.state, "unknown");
});

test("a lookalike that carries an affordance is NOT waved through as a usage notice", () => {
  const v = paneAcceptsTypedText(
    INPUT_FRAME + "  You've used 90% of your session limit. Continue? [y/N]\r\n");
  assert.strictEqual(v.accepting, false);
  assert.strictEqual(v.state, "prompt");
});
