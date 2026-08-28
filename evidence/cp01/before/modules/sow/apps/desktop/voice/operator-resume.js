"use strict";

/**
 * Operator provenance for ending a supervisor-owned voice turn, read from the input events
 * ELECTRON MAIN observes itself (`before-input-event`, which fires before the page — and therefore
 * before any renderer code — sees the key). Renderer focus is intentionally absent: the renderer is
 * the least-trusted surface (invariant 29) and a pane id it supplies cannot be an authority input.
 *
 * TWO gestures, for two different situations:
 *
 *  • `isOperatorTypedKey` — the operator is TYPING. This is what actually bounds a voice turn
 *    (`.disarm`/U166): everything the vendor CLI does between an admitted spoken prompt and the
 *    operator's next keystroke is treated as voice-originated and non-executing; the operator taking
 *    the keyboard back ends that window. The vendor child cannot produce this event — it is not in
 *    the window's input path at all — which is the property a vendor lifecycle event lacked.
 *  • `shouldOperatorResumeVoiceTurn` — the explicit Ctrl+Shift+Escape recovery chord, kept from
 *    `.close-revalidate2` for the case where the operator wants the restriction gone without typing
 *    into the pane. It is CONSUMED by main (never typed into the CLI); an ordinary keystroke is not.
 *
 * A modifier pressed alone is not typing: holding Shift to capitalise the first letter of a sentence
 * would otherwise end the turn a keystroke early, and a chord's own Control/Shift would end it before
 * the chord completed.
 */
const MODIFIER_KEYS = new Set([
  "Control", "Shift", "Alt", "Meta", "AltGraph", "CapsLock", "NumLock", "ScrollLock", "Dead",
]);

const EDITING_KEYS = new Set(["Backspace", "Delete", "Tab"]);

function shouldOperatorResumeVoiceTurn(input) {
  return Boolean(input
    && input.type === "keyDown"
    && input.isAutoRepeat !== true
    && input.key === "Escape"
    && input.control === true
    && input.shift === true);
}

function isOperatorTypedKey(input) {
  return Boolean(input
    && input.type === "keyDown"
    && typeof input.key === "string"
    && input.key.length > 0
    && !MODIFIER_KEYS.has(input.key));
}

/**
 * A COARSE class for the audit record. The key itself is deliberately never returned: the audit is
 * append-only and reaches evidence receipts, so recording which keys the operator pressed would make
 * this an audited keylogger. The kind is enough to read the trail ("the operator typed, then the
 * turn ended") and carries none of what they typed.
 */
function operatorKeyKind(input) {
  if (!isOperatorTypedKey(input)) return "none";
  const key = input.key;
  if (input.control === true || input.meta === true || input.alt === true) return "control-combination";
  if (key === "Enter") return "submit";
  if (EDITING_KEYS.has(key)) return "editing";
  return key.length === 1 ? "printable" : "non-printing";
}

module.exports = { shouldOperatorResumeVoiceTurn, isOperatorTypedKey, operatorKeyKind };
