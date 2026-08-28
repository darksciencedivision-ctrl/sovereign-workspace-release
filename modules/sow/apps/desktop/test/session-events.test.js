"use strict";
/**
 * The session's approval-event record (Phase 17D `.events`, finding F2).
 *
 * The drawer is only as honest as this log, so what matters here is what the shell REFUSES to write:
 * an unavailable feed, an ordinary chat utterance, an empty transcript, a dispatch with no gate
 * record, and — the load-bearing one — a decision the Python authority did not mint. The shell records
 * evidence; the Python builder (tests/unit/test_session_approvals.py) decides what it means.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {
  SessionApprovalLog, SESSION_APPROVAL_EVENT_SCHEMA,
} = require("../approvals/session-events");

function withLog(fn, opts = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sov-sessev-"));
  const logPath = path.join(dir, "session-events.jsonl");
  const lines = [];
  const log = new SessionApprovalLog({ logPath, log: (m) => lines.push(m), ...opts });
  try {
    return fn(log, () => readEvents(logPath), lines);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function readEvents(p) {
  if (!fs.existsSync(p)) return [];
  return fs.readFileSync(p, "utf8").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
}

const VOICE_FEED = (outcome) => ({ schema: "conductor_voice_feed@1.0", sourced: true, outcome });

// ---- utterances -------------------------------------------------------------
test("a protected-verb utterance is recorded with its transcript, surface and claimed class", () => {
  withLog((log, events) => {
    log.begin();
    const rec = log.recordUtterance(VOICE_FEED({
      kind: "proposed_action", source: "voice", text: "spawn a gpt-5.5 worker node", confidence: 0.9,
    }));
    assert.ok(rec);
    assert.equal(rec.schema, SESSION_APPROVAL_EVENT_SCHEMA);
    assert.equal(rec.kind, "utterance");
    assert.equal(rec.utterance.text, "spawn a gpt-5.5 worker node");
    assert.equal(rec.utterance.source, "voice");
    assert.equal(rec.utterance.confidence, 0.9);
    assert.equal(rec.utterance.classified_as, "proposed_action");
    assert.equal(rec.provenance.channel, "voice:capture");
    assert.equal(events().length, 1);
  });
});

test("a low-confidence utterance is recorded as the clarification it was", () => {
  withLog((log) => {
    log.begin();
    const rec = log.recordUtterance(VOICE_FEED({
      kind: "clarify", source: "voice", text: "uh do the roster thing", confidence: 0.2,
    }));
    assert.equal(rec.utterance.classified_as, "clarify");
  });
});

test("an ordinary CHAT utterance records nothing — it reached the conductor, there is nothing to approve", () => {
  withLog((log, events) => {
    log.begin();
    assert.equal(log.recordUtterance(VOICE_FEED({
      kind: "chat", source: "voice", text: "what is the build status", confidence: 0.99,
    })), null);
    assert.deepEqual(events(), []);
  });
});

test("an unavailable voice feed records nothing (a fault is not an event)", () => {
  withLog((log, events) => {
    log.begin();
    assert.equal(log.recordUtterance({ schema: "conductor_voice_feed@1.0", sourced: false }), null);
    assert.equal(log.recordUtterance(null), null);
    assert.deepEqual(events(), []);
  });
});

test("an empty transcript and an unknown surface are refused", () => {
  withLog((log, events) => {
    log.begin();
    assert.equal(log.recordUtterance(VOICE_FEED({ kind: "clarify", source: "voice", text: "   " })), null);
    assert.equal(log.recordUtterance(VOICE_FEED({
      kind: "proposed_action", source: "somewhere-else", text: "spawn a worker",
    })), null);
    assert.deepEqual(events(), []);
  });
});

// ---- dispatched plans -------------------------------------------------------
const DISPATCH_FEED = (plan) => ({ schema: "conductor_dispatch_feed@1.0", dispatched: true, plan });

test("a dispatched plan is recorded with its real gate record, verbatim", () => {
  withLog((log) => {
    log.begin();
    const gate = { schema: "gate@1.0", gate_id: "g-plan-1", kind: "plan", verdict: "PASS",
      criteria: ["plan_has_tasks"], evidence: [], debate_ref: null, decided_by: "gate_engine",
      reasons: [], task_id: null };
    const rec = log.recordDispatchPlan(DISPATCH_FEED({
      objective: "Summarize the roster", tasks: [{ task_id: "t1" }], refused: [],
      plan_gate: gate, plan_blocked: false,
    }), { operatorObjective: true });
    assert.equal(rec.kind, "plan");
    assert.deepEqual(rec.plan.plan_gate, gate);
    assert.equal(rec.plan.plan_blocked, false);
    assert.equal(rec.provenance.channel, "conductor:dispatch");
  });
});

test("a dispatch with no gate record records nothing (nothing was judged)", () => {
  withLog((log, events) => {
    log.begin();
    assert.equal(log.recordDispatchPlan(DISPATCH_FEED({ objective: "x", plan_gate: null }),
      { operatorObjective: true }), null);
    assert.equal(log.recordDispatchPlan({ schema: "conductor_dispatch_feed@1.0" },
      { operatorObjective: true }), null);
    assert.deepEqual(events(), []);
  });
});

test("a dispatch the OPERATOR did not ask for is refused — the launch demo never reaches the drawer", () => {
  withLog((log, events) => {
    log.begin();
    const gate = { schema: "gate@1.0", gate_id: "g-plan-1", kind: "plan", verdict: "PASS",
      criteria: ["plan_has_tasks"], evidence: [], debate_ref: null, decided_by: "gate_engine",
      reasons: [], task_id: null };
    const feed = DISPATCH_FEED({ objective: "Design the offline conductor roster", tasks: [],
      refused: [], plan_gate: gate, plan_blocked: false });
    // this is exactly the shape the launch-time demonstration dispatch produces (finding F2 one
    // layer down): a real gate verdict over an objective nobody asked for
    assert.equal(log.recordDispatchPlan(feed), null);
    assert.equal(log.recordDispatchPlan(feed, { operatorObjective: false }), null);
    assert.deepEqual(events(), []);
  });
});

// ---- decisions: only what the authority minted ------------------------------
// The shape Python mints since W-43: the four decided fields plus the producer name and the
// authenticity stamp over them. The stamp value is opaque to the shell — it holds no key.
const MINTED_DECISION = Object.freeze({
  item_id: "ap-1", decision: "reject", reason: "later", operator_role: "operator",
  producer: "session_approvals.route_session_decision@1.0",
  authenticity: "b".repeat(64),
});

test("a governed decision event is persisted so the resolve survives the next rebuild", () => {
  withLog((log, events) => {
    log.begin();
    const rec = log.recordGovernedDecision({
      schema: SESSION_APPROVAL_EVENT_SCHEMA, event_id: "dec-ap-1", kind: "decision",
      decision: { ...MINTED_DECISION },
      provenance: { channel: "approvals:decide" },
    });
    assert.equal(rec.decision.item_id, "ap-1");
    assert.equal(rec.decision.decision, "reject");
    assert.equal(events().length, 1);
  });
});

test("W-43: the producer stamp survives the shell's copy UNCHANGED, or the decision cannot verify", () => {
  withLog((log, events) => {
    log.begin();
    log.recordGovernedDecision({
      schema: SESSION_APPROVAL_EVENT_SCHEMA, event_id: "dec-ap-1", kind: "decision",
      decision: { ...MINTED_DECISION }, provenance: { channel: "approvals:decide" },
    });
    // The shell re-stamps event_id/at on append, which is why neither is inside the signature; what
    // it must NOT do is alter, drop or re-order anything the signature covers.
    const written = events()[0];
    assert.deepEqual(written.decision, MINTED_DECISION,
      "every signed field must reach the log byte-identical — the drawer verifies over exactly these");
    assert.equal(written.event_id, "ev-1");
  });
});

test("a decision the authority did not mint is refused — the shell cannot record its own approval", () => {
  withLog((log, events) => {
    log.begin();
    // no schema (a hand-built object), wrong kind, and an illegal decision value
    assert.equal(log.recordGovernedDecision({ kind: "decision", decision: { item_id: "ap-1", decision: "approve" } }), null);
    assert.equal(log.recordGovernedDecision({
      schema: SESSION_APPROVAL_EVENT_SCHEMA, kind: "utterance",
      decision: { item_id: "ap-1", decision: "approve" },
    }), null);
    assert.equal(log.recordGovernedDecision({
      schema: SESSION_APPROVAL_EVENT_SCHEMA, kind: "decision",
      decision: { item_id: "ap-1", decision: "sudo-approve", operator_role: "operator" },
    }), null);
    // W-43: an UNSTAMPED decision — the exact shape the pre-W-43 authority minted, and the exact
    // shape a forger writes. Recording it would fail the whole drawer closed on the next rebuild.
    assert.equal(log.recordGovernedDecision({
      schema: SESSION_APPROVAL_EVENT_SCHEMA, kind: "decision",
      decision: { item_id: "ap-1", decision: "approve", reason: "", operator_role: "operator" },
    }), null);
    // …and a stamp with no producer beside it, which is the same absence one field over.
    assert.equal(log.recordGovernedDecision({
      schema: SESSION_APPROVAL_EVENT_SCHEMA, kind: "decision",
      decision: { ...MINTED_DECISION, producer: "" },
    }), null);
    assert.deepEqual(events(), []);
  });
});

// ---- the log itself ---------------------------------------------------------
test("begin() starts a fresh run — yesterday's pending rows never reappear", () => {
  withLog((log, events) => {
    log.begin();
    log.recordUtterance(VOICE_FEED({ kind: "clarify", source: "voice", text: "something", confidence: 0.1 }));
    assert.equal(events().length, 1);
    log.begin();
    assert.deepEqual(events(), []);
    assert.equal(log.count(), 0);
  });
});

test("event ids are monotonic and the file is append-only JSONL", () => {
  withLog((log, events) => {
    log.begin();
    log.recordUtterance(VOICE_FEED({ kind: "clarify", source: "voice", text: "one", confidence: 0.1 }));
    log.recordUtterance(VOICE_FEED({ kind: "clarify", source: "voice", text: "two", confidence: 0.1 }));
    assert.deepEqual(events().map((e) => e.event_id), ["ev-1", "ev-2"]);
    assert.deepEqual(events().map((e) => e.utterance.text), ["one", "two"]);
  });
});

test("the cap is announced, not silently applied", () => {
  withLog((log, events, lines) => {
    log.begin();
    for (let i = 0; i < 4; i += 1) {
      log.recordUtterance(VOICE_FEED({ kind: "clarify", source: "voice", text: `u${i}`, confidence: 0.1 }));
    }
    assert.equal(events().length, 2);
    assert.equal(log.dropped(), 2);
    assert.ok(lines.some((l) => /cap/.test(l)));
  }, { maxEvents: 2 });
});

test("an unwritable log leaves an EMPTY drawer rather than throwing into launch", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sov-sessev-"));
  try {
    // a directory where the file should be: every write fails, nothing throws
    const logPath = path.join(dir, "session-events.jsonl");
    fs.mkdirSync(logPath);
    const lines = [];
    const log = new SessionApprovalLog({ logPath, log: (m) => lines.push(m) });
    assert.equal(log.begin(), false);
    assert.equal(log.recordUtterance(VOICE_FEED({
      kind: "proposed_action", source: "voice", text: "spawn a worker", confidence: 0.9,
    })), null);
    assert.equal(log.count(), 0);
    assert.ok(lines.length >= 1);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
