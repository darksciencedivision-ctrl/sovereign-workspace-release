"use strict";
/**
 * Phase 16E `.wire` — unit tests for the PURE conductor voice-IN delivery decision (voice/deliver.js).
 * The load-bearing property: a spoken transcript reaches the conductor input ONLY when the Python
 * bridge routed it as CHAT; a protected/destructive action is queued (never delivered — invariant 25),
 * a low-confidence transcript clarifies (never delivered), and nothing is ever fabricated as delivered.
 */
const test = require("node:test");
const assert = require("node:assert");
const { decideDelivery, buildCaptureResult } = require("../voice/deliver");

function chatFeed(text = "show status") {
  return {
    schema: "conductor_voice_feed@1.0",
    sourced: true,
    engine: { name: "mock-stt", mock: true, real_available: false },
    outcome: { kind: "chat", source: "voice", text, confidence: 0.95, reason: "", queue_item_id: null },
    delivered: true,
    delivered_text: text,
    queued: false,
    needs_clarification: false,
    tts: false,
    live_capture_owed: { owed: true, issue: "16F" },
  };
}

test("decideDelivery delivers a sourced CHAT transcript verbatim", () => {
  const d = decideDelivery(chatFeed("show status"));
  assert.equal(d.shouldDeliver, true);
  assert.equal(d.text, "show status");
});

test("decideDelivery NEVER delivers a queued protected/destructive action (invariant 25)", () => {
  const f = chatFeed();
  f.outcome = { kind: "proposed_action", source: "voice", text: "terminate node-B", reason: "protected", queue_item_id: "cmd-1" };
  f.delivered = false;
  f.queued = true;
  const d = decideDelivery(f);
  assert.equal(d.shouldDeliver, false);
  assert.equal(d.text, null);
  assert.match(d.reason, /queued for approval/i);
});

test("decideDelivery NEVER delivers a low-confidence clarify outcome", () => {
  const f = chatFeed();
  f.outcome = { kind: "clarify", source: "voice", text: "", reason: "low confidence", queue_item_id: null };
  f.delivered = false;
  f.needs_clarification = true;
  const d = decideDelivery(f);
  assert.equal(d.shouldDeliver, false);
  assert.match(d.reason, /low confidence|repeat/i);
});

test("decideDelivery fails closed on the unavailable feed (sourced:false)", () => {
  const d = decideDelivery({ schema: "conductor_voice_feed@1.0", sourced: false, reason: "emit timed out" });
  assert.equal(d.shouldDeliver, false);
  assert.match(d.reason, /unavailable/i);
});

test("decideDelivery fails closed when a chat outcome carries empty text (no fabrication)", () => {
  const f = chatFeed("");
  f.delivered_text = "   ";
  f.outcome.text = "";
  const d = decideDelivery(f);
  assert.equal(d.shouldDeliver, false);
  assert.match(d.reason, /no transcript|fail-closed/i);
});

test("decideDelivery handles null/garbage input fail-closed", () => {
  assert.equal(decideDelivery(null).shouldDeliver, false);
  assert.equal(decideDelivery(42).shouldDeliver, false);
});

test("buildCaptureResult marks delivered_to_conductor ONLY when the write landed", () => {
  const written = buildCaptureResult(chatFeed(), {
    written: true,
    submitted: true,
    authority_boundary: {
      schema: "voice_turn_boundary@1.0",
      non_executing_voice_turns: true,
    },
  });
  assert.equal(written.delivered_to_conductor, true);
  assert.equal(written.delivered, true);
  assert.equal(written.write.authority_boundary.non_executing_voice_turns, true);
  assert.match(written.note, /written into the conductor input/i);

  // bridge routed CHAT but this capture has no governed-conductor submission — never fabricate one
  const owed = buildCaptureResult(chatFeed(), { written: false, reason: "conductor session not admitted" });
  assert.equal(owed.delivered_to_conductor, false);
  assert.equal(owed.delivered, true); // the bridge's routing verdict is preserved
  assert.match(owed.note, /no confirmed governed-conductor submission/);
});

test("a body that landed WITHOUT its submit key is not delivered to the conductor", () => {
  // Phase 17C `.close`: the destination is a real interactive TUI. Text written into its input box
  // that was never submitted is exactly the failure the operator cannot see — the transcript is on
  // screen, so it LOOKS delivered, and the conductor never received it. Fail closed: the claim needs
  // both writes, and the reason says which one is missing.
  const half = buildCaptureResult(chatFeed(), { written: true, submitted: false, reason: "the session ended before the submit key" });
  assert.equal(half.delivered_to_conductor, false);
  assert.equal(half.write.written, true);
  assert.equal(half.write.submitted, false);
  assert.match(half.note, /not submitted|submit key/i);
});

test("the fold carries the turn's FATE, so a voided utterance is legible downstream", () => {
  // Phase 17C `.disarm` (U171): `deliverChat` now reports what the supervisor still held for the
  // turn after the submit key — `ended` means the operator's keystroke voided the utterance before
  // the conductor accepted it. The fold is an explicit whitelist, so a new field it does not name is
  // silently dropped: the badge stayed honest (it keys off `submitted`), but the receipt and the
  // Inspector could not see WHY a delivery failed. Found while reading the live receipt, which
  // recorded `turn_fate: null` for a delivery whose fate the delivery module knew.
  const voided = buildCaptureResult(chatFeed(), {
    written: true, submitted: false, turn_fate: "ended",
    reason: "you ended the voice turn before the conductor accepted the utterance",
  });
  assert.equal(voided.delivered_to_conductor, false);
  assert.equal(voided.write.turn_fate, "ended");
  const ok = buildCaptureResult(chatFeed(), { written: true, submitted: true, turn_fate: "admitted" });
  assert.equal(ok.write.turn_fate, "admitted");
  // …and a write record that does not report one says so, rather than implying a fate it never had
  assert.equal(buildCaptureResult(chatFeed(), { written: true, submitted: true }).write.turn_fate, null);
});

test("buildCaptureResult never claims TTS and carries a visible engine descriptor", () => {
  const r = buildCaptureResult(chatFeed(), { written: true, submitted: true });
  assert.equal(r.tts, false);
  assert.equal(r.engine.mock, true);
});

test("buildCaptureResult on a queued action reports queued, not delivered", () => {
  const f = chatFeed();
  f.outcome = { kind: "proposed_action", source: "voice", text: "terminate node-B", reason: "protected", queue_item_id: "cmd-1" };
  f.delivered = false;
  f.queued = true;
  const r = buildCaptureResult(f, { written: false, reason: "protected/destructive action — queued for approval (never delivered)" });
  assert.equal(r.queued, true);
  assert.equal(r.delivered_to_conductor, false);
  assert.equal(r.delivered, false);
});
