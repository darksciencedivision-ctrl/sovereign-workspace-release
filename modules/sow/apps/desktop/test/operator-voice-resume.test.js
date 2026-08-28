"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  shouldOperatorResumeVoiceTurn, isOperatorTypedKey, operatorKeyKind,
} = require("../voice/operator-resume");

test("only the explicit main-owned Ctrl+Shift+Escape gesture is the RECOVERY CHORD", () => {
  assert.equal(shouldOperatorResumeVoiceTurn({
    type: "keyDown", key: "Escape", control: true, shift: true, isAutoRepeat: false,
  }), true);
});

test("ordinary typing, partial chords, key-up and auto-repeat are not the chord", () => {
  assert.equal(shouldOperatorResumeVoiceTurn(null), false);
  assert.equal(shouldOperatorResumeVoiceTurn(
    { type: "keyDown", key: "a", control: true, shift: true, isAutoRepeat: false },
  ), false);
  assert.equal(shouldOperatorResumeVoiceTurn(
    { type: "keyDown", key: "Escape", control: false, shift: true, isAutoRepeat: false },
  ), false);
  assert.equal(shouldOperatorResumeVoiceTurn(
    { type: "keyUp", key: "Escape", control: true, shift: true, isAutoRepeat: false },
  ), false);
  assert.equal(shouldOperatorResumeVoiceTurn(
    { type: "keyDown", key: "Escape", control: true, shift: true, isAutoRepeat: true },
  ), false);
});

// `.disarm` (U166): the chord alone was the only way back, and it appears in no chrome, no string and
// no operator document (it is also Windows' Task Manager shortcut). The operator's ORDINARY typing —
// observed by Electron main before the page sees it — is what actually ends a voice turn.

test("a real keystroke Electron main observes is operator provenance for ending a voice turn", () => {
  for (const key of ["a", "7", " ", "Enter", "Backspace", "ArrowLeft", "F5", "Escape"]) {
    assert.equal(isOperatorTypedKey({ type: "keyDown", key, control: false, shift: false }), true, key);
  }
  // auto-repeat is still the operator holding a key down
  assert.equal(isOperatorTypedKey({ type: "keyDown", key: "a", isAutoRepeat: true }), true);
  // a modifier alone is not typing, and neither is a key-up or a malformed event
  for (const key of ["Control", "Shift", "Alt", "Meta", "AltGraph", "CapsLock", ""]) {
    assert.equal(isOperatorTypedKey({ type: "keyDown", key }), false, key);
  }
  assert.equal(isOperatorTypedKey({ type: "keyUp", key: "a" }), false);
  assert.equal(isOperatorTypedKey(null), false);
  assert.equal(isOperatorTypedKey({ type: "char", key: "a" }), false);
});

test("the audit records the KIND of key, never the key — an audited keystroke log is a keylogger", () => {
  assert.equal(operatorKeyKind({ type: "keyDown", key: "s" }), "printable");
  assert.equal(operatorKeyKind({ type: "keyDown", key: "Enter" }), "submit");
  assert.equal(operatorKeyKind({ type: "keyDown", key: "c", control: true }), "control-combination");
  assert.equal(operatorKeyKind({ type: "keyDown", key: "Backspace" }), "editing");
  assert.equal(operatorKeyKind({ type: "keyDown", key: "F5" }), "non-printing");
  for (const key of ["s", "Enter", "Backspace", "F5"]) {
    assert.doesNotMatch(operatorKeyKind({ type: "keyDown", key }), new RegExp(`\\b${key}\\b`));
  }
});
