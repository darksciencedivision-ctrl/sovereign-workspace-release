"use strict";
/**
 * Phase 17E — the pure verdict logic behind the fully-live assembled receipt.
 *
 * The in-Electron check itself cannot run under `node --test` (it needs a window, a supervisor and a
 * live model). What CAN be tested here is the part that decides what the receipt is allowed to
 * CLAIM: whether a dispatch feed really carries a live worker leg, whether the approval drawer is
 * showing this session's own events rather than the deterministic demonstration trio, and whether
 * the OWED block names every leg the run did not evidence.
 *
 * These are written first and each falsification is asserted independently, because the failure mode
 * this track exists to prevent is a green composition receipt whose legs were satisfied by a
 * mock/canned/absent producer — exactly the shape 17D found in the approval drawer (finding F2).
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  liveDispatchIsHonest, approvalDrawerIsRealSessionEvents, demoIdsPresent, owedMarkersAreComplete,
  twoTerminalsOnOneAllowance, composeVerdict, DEMO_APPROVAL_IDS, REQUIRED_OWED_KEYS,
} = require("../selfcheck/fully-live-verdict");

// A feed shaped exactly like the one 17B `.legs` produced on this host (docs/evidence/live/
// PHASE17B_LEGS_DISPATCH_FEED.json), trimmed to the fields the verdict reads.
function liveFeed(overrides = {}) {
  return {
    schema: "conductor_dispatch_feed@1.0",
    dispatched: true,
    by_descriptor: true,
    accepted_count: 1,
    acceptance_verdict: "PASS",
    operator_disposition: "pending",
    synthesized_by: "conductor_fable5",
    legs: { conductor: "mock", workers: "live" },
    worker_legs: { "worker:worker-claude-live": "live" },
    worker_evidence: [{
      node_id: "worker-claude-live", leg: "live", adapter: "claude_code",
      executed: true, spent: true, verified: true, model: "claude-opus-5[1m]", tasks: ["t-1"],
    }],
    live_workers_owed: { owed: false, issue: "U58", live_nodes: [{ node_id: "worker-claude-live" }] },
    torn_down: true,
    ...overrides,
  };
}

// ---- the live dispatch leg (DONE leg d) --------------------------------------------------------

test("a live-worker dispatch feed with an executed+spent+verified checkpoint is honest", () => {
  const v = liveDispatchIsHonest(liveFeed());
  assert.equal(v.ok, true, v.reasons.join("; "));
  assert.deepEqual(v.reasons, []);
  assert.deepEqual(v.live_nodes, ["worker-claude-live"]);
});

test("the MOCK-first feed the shell sources at launch is NOT a live dispatch", () => {
  // This is the feed every ordinary app launch produces. If the composition check could pass on it,
  // the whole leg would be satisfied by the thing it exists to distinguish itself from.
  const v = liveDispatchIsHonest(liveFeed({
    legs: { conductor: "mock", workers: "mock" },
    worker_legs: { "worker:worker-A": "mock" },
    worker_evidence: [],
    live_workers_owed: { owed: true, issue: "U58" },
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /legs\.workers/.test(r)), v.reasons.join("; "));
});

test("a worker leg labelled live whose checkpoint was never executed is refused", () => {
  const v = liveDispatchIsHonest(liveFeed({
    worker_evidence: [{ node_id: "w", leg: "live", executed: false, spent: true, verified: true }],
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /executed/.test(r)), v.reasons.join("; "));
});

test("a worker leg labelled live whose checkpoint was not VERIFIED is refused (U45)", () => {
  const v = liveDispatchIsHonest(liveFeed({
    worker_evidence: [{ node_id: "w", leg: "live", executed: true, spent: true, verified: false }],
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /verified/.test(r)), v.reasons.join("; "));
});

test("a live worker leg is refused while the feed still records the live legs as OWED", () => {
  const v = liveDispatchIsHonest(liveFeed({ live_workers_owed: { owed: true, issue: "U58" } }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /live_workers_owed/.test(r)), v.reasons.join("; "));
});

test("a dispatch nothing accepted, or that no gate passed, is refused", () => {
  assert.equal(liveDispatchIsHonest(liveFeed({ accepted_count: 0 })).ok, false);
  assert.equal(liveDispatchIsHonest(liveFeed({ acceptance_verdict: "FAIL" })).ok, false);
});

// ---- a red leg has to say WHY, in the producer's own words -------------------------------------
// The first re-run of this composition against the fixed tree came back red on exactly this leg and
// the receipt could not say why: it recorded the legs and the evidence rows but dropped the feed's
// `node_refusals`, `failed_count` and `gate_summary`, which are the only fields that distinguish
// "the vendor CLI faulted" from "the artifact was published and the STAGE gate refused it". Both
// produce accepted_count 0. A verdict that cannot tell them apart sends the next unit to spend
// another live call to learn what the run already knew.

test("a dispatch whose artifact the STAGE gate refused says so, with the tally", () => {
  const v = liveDispatchIsHonest(liveFeed({
    accepted_count: 0, acceptance_verdict: "FAIL", failed_count: 1,
    node_refusals: [],
    gate_summary: { plan: "PASS", stage_pass: 0, stage_total: 1, acceptance: "FAIL" },
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /stage gate passed 0 of 1/.test(r)), v.reasons.join("; "));
  // and it must NOT claim a node refusal that the feed does not record
  assert.ok(!v.reasons.some((r) => /the node itself refused/.test(r)), v.reasons.join("; "));
});

test("a dispatch the NODE refused reports the node's own words, attributed to the node", () => {
  const v = liveDispatchIsHonest(liveFeed({
    accepted_count: 0, acceptance_verdict: "FAIL", failed_count: 1,
    node_refusals: [{
      task_id: "t-1", node_id: "worker-claude-live",
      node_reported_reasons: ["RuntimeError: claude CLI exited 1: usage limit reached"],
    }],
    gate_summary: { plan: "PASS", stage_pass: 0, stage_total: 0, acceptance: "FAIL" },
  }));
  assert.equal(v.ok, false);
  const joined = v.reasons.join("; ");
  assert.ok(/the node itself refused/.test(joined), joined);
  assert.ok(/worker-claude-live/.test(joined), joined);
  assert.ok(/usage limit reached/.test(joined), joined);
});

test("the diagnosis is added only to a FAILING verdict — a green feed stays reason-free", () => {
  const v = liveDispatchIsHonest(liveFeed({
    failed_count: 0, node_refusals: [],
    gate_summary: { plan: "PASS", stage_pass: 1, stage_total: 1, acceptance: "PASS" },
  }));
  assert.equal(v.ok, true, v.reasons.join("; "));
  assert.deepEqual(v.reasons, []);
});

test("a packet the flow marks accepted-by-the-operator is refused (invariant 1)", () => {
  const v = liveDispatchIsHonest(liveFeed({ operator_disposition: "accepted" }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /operator_disposition/.test(r)), v.reasons.join("; "));
});

test("routing that was not by descriptor is refused (invariant 4)", () => {
  assert.equal(liveDispatchIsHonest(liveFeed({ by_descriptor: false })).ok, false);
});

test("a dispatch whose loopback MCP server was left running is refused (D-LOOP-1)", () => {
  const v = liveDispatchIsHonest(liveFeed({ torn_down: false }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /torn_down/.test(r)), v.reasons.join("; "));
});

test("a feed with no synthesis is refused — the conductor must fold the accepted set", () => {
  const v = liveDispatchIsHonest(liveFeed({ synthesized_by: null }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /synthes/i.test(r)), v.reasons.join("; "));
});

test("an absent or malformed feed is refused rather than read optimistically", () => {
  assert.equal(liveDispatchIsHonest(null).ok, false);
  assert.equal(liveDispatchIsHonest({}).ok, false);
  assert.equal(liveDispatchIsHonest(liveFeed({ dispatched: false })).ok, false);
});

test("a MOCK worker in a pool the feed labels `live` is refused (gate-validator D4)", () => {
  // The aggregate label was trusted where it should have been cross-checked: a pool of one live and
  // one mock worker passed, because only the rows already claiming `live` were examined. `live` is a
  // claim about the POOL, so a row that does not carry it makes the label an overstatement — the
  // honest label for a mixed pool is not `live`.
  const v = liveDispatchIsHonest(liveFeed({
    worker_evidence: [
      { node_id: "worker-claude-live", leg: "live", executed: true, spent: true, verified: true },
      { node_id: "worker-mock-b", leg: "mock", executed: true },
    ],
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /worker-mock-b/.test(r)), v.reasons.join("; "));
  assert.deepEqual(v.live_nodes, ["worker-claude-live"]);
});

test("a worker row with no leg label at all is refused, not read as live", () => {
  const v = liveDispatchIsHonest(liveFeed({
    worker_evidence: [{ node_id: "worker-unlabelled", executed: true, spent: true, verified: true }],
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /worker-unlabelled/.test(r)), v.reasons.join("; "));
});

// ---- the approval drawer (DONE leg e) ----------------------------------------------------------

// The row shape the shell actually produced on this host (PHASE17D_APPROVALS_SELFCHECK.json).
function realDrawer(overrides = {}, rowOverrides = {}) {
  return {
    source: "session_events", sourced: true, badgeCount: 1, eventCount: 1,
    rows: [{
      id: "ap-1", kind: "protected_action", origin: "voice", ref: "q-483c0cc053d2",
      detail: {
        event_id: "ev-1", at: "2026-07-31T10:56:16.989Z",
        channel: "voice:capture", feed_schema: "conductor_voice_feed@1.0",
      },
      ...rowOverrides,
    }],
    ...overrides,
  };
}

test("a drawer folded from this session's own events, carrying the queued proposal, passes", () => {
  const v = approvalDrawerIsRealSessionEvents(realDrawer());
  assert.equal(v.ok, true, v.reasons.join("; "));
});

test("the id `ap-1` does NOT decide it — the real queue mints that id for its first row too", () => {
  // This is what the first fully-live run found: an id-based rule failed a genuine event. The rule is
  // provenance, so the same id passes WITH a recorded event behind it and fails WITHOUT one.
  assert.equal(approvalDrawerIsRealSessionEvents(realDrawer()).ok, true);
  assert.deepEqual(demoIdsPresent(realDrawer()), ["ap-1"]);
  const canned = approvalDrawerIsRealSessionEvents(realDrawer({}, { detail: { verb: "spawn" } }));
  assert.equal(canned.ok, false);
  assert.ok(canned.reasons.some((r) => /recorded event id/.test(r)), canned.reasons.join("; "));
});

test("a row recorded on some other channel is refused (invariant 11)", () => {
  const v = approvalDrawerIsRealSessionEvents(realDrawer({}, {
    detail: { event_id: "ev-1", channel: "demo:fixture", feed_schema: "x@1.0" },
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /demo:fixture/.test(r)), v.reasons.join("; "));
});

test("a row with no broker reference is refused", () => {
  const v = approvalDrawerIsRealSessionEvents(realDrawer({}, { ref: "" }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /broker queue reference/.test(r)), v.reasons.join("; "));
});

test("a drawer sourced from the old canned emitter is refused even with plausible rows", () => {
  const v = approvalDrawerIsRealSessionEvents(realDrawer({ source: "emitter" }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /source/.test(r)), v.reasons.join("; "));
});

test("a fail-closed empty view is not evidence, however it is labelled", () => {
  const v = approvalDrawerIsRealSessionEvents(realDrawer({ sourced: false }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /not sourced/.test(r)), v.reasons.join("; "));
});

test("a drawer folded from ZERO recorded events cannot be showing a recorded event", () => {
  const v = approvalDrawerIsRealSessionEvents(realDrawer({ eventCount: 0 }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /recorded events/.test(r)), v.reasons.join("; "));
});

test("an empty drawer does not satisfy the leg — the run must CAUSE the event it approves", () => {
  const v = approvalDrawerIsRealSessionEvents(realDrawer({ badgeCount: 0, rows: [] }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /no row/.test(r)), v.reasons.join("; "));
});

test("a row that is not the protected action this run caused is refused", () => {
  const v = approvalDrawerIsRealSessionEvents(realDrawer({}, { kind: "clarification" }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /protected_action/.test(r)), v.reasons.join("; "));
});

// The rule said "shows ONLY real session events" and read ONE row — the gate-validator's D1. It fed
// the real demonstration trio in alongside a genuine row and the leg went green, which is 17D's F2
// with an extra row in front of it. Provenance is now required of EVERY row, in every position.

/**
 * The 16D demonstration trio as `tests/support/demo_approval_queue.py` really builds it.
 *
 * The plan and clarification rows carry `ref: null` — `operator_surface` gives a broker reference
 * only to a protected action, and an earlier version of this fixture invented refs for all three
 * (gate-validator m6). That made the fixture EASIER to reject than the real thing, which is the wrong
 * direction for a test whose whole point is that the trio must be refused.
 */
function demoTrioRows() {
  return [
    { id: "ap-1", kind: "plan", origin: "conductor", ref: null,
      detail: { objective: "add a health endpoint", tasks: 2 } },
    { id: "ap-2", kind: "protected_action", origin: "voice", ref: "q-demo0000",
      detail: { verb: "terminate", target: "node-b", args: {}, category: "destructive",
                reason: "destructive verb requires operator approval" } },
    { id: "ap-3", kind: "clarification", origin: "voice", ref: null,
      detail: { text: "run the deploy?", confidence: 0.4 } },
  ];
}

test("a GENUINE plan row with no broker ref is not refused — only protected actions carry one", () => {
  // gate-validator m2: the rule required `ref` of every row, but `operator_surface` builds genuine
  // session-event plan and clarification rows with `ref: None` by design. The check named
  // `approval_drawer_shows_only_real_session_events` therefore refused three of the four real kinds.
  // The failure direction was safe (never a false pass) and the name was still wrong.
  const real = realDrawer().rows[0];
  const planRow = { id: "ap-7", kind: "plan", origin: "conductor", ref: null,
    detail: { event_id: "ev-2", channel: "conductor:plan", feed_schema: "operator_surface@1.0",
              objective: "add a health endpoint", tasks: 2 } };
  const v = approvalDrawerIsRealSessionEvents(realDrawer({
    rows: [planRow, real], eventCount: 2, badgeCount: 2,
  }));
  assert.equal(v.ok, true, v.reasons.join("; "));
});

test("a protected action with no broker ref is still refused", () => {
  const real = realDrawer().rows[0];
  const v = approvalDrawerIsRealSessionEvents(realDrawer({ rows: [{ ...real, ref: null }] }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /broker queue reference/.test(r)), v.reasons.join("; "));
});

test("the demonstration trio is refused BEHIND a genuine row, not just in front of it (D1)", () => {
  const real = realDrawer().rows[0];
  const v = approvalDrawerIsRealSessionEvents(realDrawer({
    rows: [{ ...real, id: "ap-0" }, ...demoTrioRows()], eventCount: 1, badgeCount: 4,
  }));
  assert.equal(v.ok, false, "the whole 16D trio rendered as operator work and the leg passed");
  for (const id of ["ap-1", "ap-2", "ap-3"]) {
    assert.ok(v.reasons.some((r) => r.includes(id)), `${id} unexamined: ${v.reasons.join("; ")}`);
  }
});

test("every row is examined — a canned row anywhere in the list fails the whole feed", () => {
  const real = realDrawer().rows[0];
  const canned = { id: "ap-9", kind: "clarification", ref: "c-1", detail: { text: "?" } };
  assert.equal(approvalDrawerIsRealSessionEvents(
    realDrawer({ rows: [real, canned] })).ok, false);
  assert.equal(approvalDrawerIsRealSessionEvents(
    realDrawer({ rows: [canned, real] })).ok, false);
});

test("a drawer of SEVERAL rows all carrying provenance still passes — the rule is not row-count", () => {
  const real = realDrawer().rows[0];
  const alsoReal = { id: "ap-2", kind: "clarification", origin: "voice", ref: "c-77",
    detail: { event_id: "ev-2", at: "2026-07-31T12:21:15.000Z", channel: "voice:capture",
              feed_schema: "conductor_voice_feed@1.0" } };
  const v = approvalDrawerIsRealSessionEvents(realDrawer({ rows: [real, alsoReal], eventCount: 2 }));
  assert.equal(v.ok, true, v.reasons.join("; "));
});

test("a row whose channel is the fold's `unknown` default is not provenance", () => {
  // `_provenance_detail` writes "unknown" when a recorded event names no channel — a row that
  // reached the drawer without one must not read as though it had been recorded on a real feed.
  const v = approvalDrawerIsRealSessionEvents(realDrawer({}, {
    detail: { event_id: "ev-1", channel: "unknown", feed_schema: "conductor_voice_feed@1.0" },
  }));
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /unknown/.test(r)), v.reasons.join("; "));
});

// ---- I-X3: two live terminals on one allowance (gate-validator/spec-audit F13) ------------------

test("two terminals held at once against an allowance of two is the leg", () => {
  const v = twoTerminalsOnOneAllowance({ allowance: 2, max_in_use_observed: 2 });
  assert.equal(v.ok, true, v.reasons.join("; "));
});

test("the leg does not hard-code the policy constant — a narrowed allowance is not a defect", () => {
  // `live_authorization` explicitly permits an operator config that narrows to 1. The old check
  // asserted `allowance === 2`, so that entirely legitimate configuration went RED for a reason that
  // is not a defect. What the leg claims is that two terminals were held WITHIN the allowance.
  const v = twoTerminalsOnOneAllowance({ allowance: 1, max_in_use_observed: 1 });
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /allowance 1/.test(r)), v.reasons.join("; "));
  assert.equal(twoTerminalsOnOneAllowance({ allowance: 3, max_in_use_observed: 2 }).ok, true);
});

test("a count that exceeded the allowance is refused — that is a governor failure, not evidence", () => {
  const v = twoTerminalsOnOneAllowance({ allowance: 2, max_in_use_observed: 3 });
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /exceed/.test(r)), v.reasons.join("; "));
});

test("one terminal, or an unsampled count, does not prove two were held at once", () => {
  assert.equal(twoTerminalsOnOneAllowance({ allowance: 2, max_in_use_observed: 1 }).ok, false);
  assert.equal(twoTerminalsOnOneAllowance({ allowance: 2, max_in_use_observed: null }).ok, false);
  assert.equal(twoTerminalsOnOneAllowance(null).ok, false);
});

// ---- the OWED block ----------------------------------------------------------------------------

function fullOwed() {
  return {
    spoken_microphone: "the physical mic half is the operator's first use (directive §16 17C/17E)",
    physical_key_delivery: "U69 — OS-level keydown into the focused xterm produced no terminal data",
    conductor_initiated_dispatch: "U58 residual — the governed dispatch is invoked by the shell, "
      + "not chosen by the live conductor CLI over MCP",
    speech_out_tts: "I-V2/D-VOICE-02 — no TTS is built; an operator reversal would be OP-9-TTS",
    cloud_kimi_qwen: "OP-10 16B — cloud-only Kimi K3 / Qwen 3.8 need a new provider authorization",
    diagnostic_ledger_scope: "U111 — this run's live terminals are counted in a DIAGNOSTIC ledger "
      + "that also counts the durable one as a baseline; the operator's own shell is counted, not "
      + "adopted, and the residual (U215) is that the overlay is one-way",
    vendor_session_store_retention: "U146 — the audio is discarded, but the delivered transcript is "
      + "durable in the vendor CLI's own session store, outside this workspace",
  };
}

test("the vendor session store is an OWED key — discarding the audio is not discarding the words", () => {
  // The spec-auditor found this one at the gate itself, which is exactly the residual the verdict
  // module's header names (U214): the OWED list is AUTHORED, so a leg nobody wrote down is invisible
  // to `owedMarkersAreComplete`. 17C's receipt disclosed U146; the composition dropped it while
  // asserting `audio_was_transcribed_then_discarded` — true of OUR store, and not the whole story.
  assert.ok(REQUIRED_OWED_KEYS.includes("vendor_session_store_retention"));
  const owed = fullOwed();
  delete owed.vendor_session_store_retention;
  assert.equal(owedMarkersAreComplete(owed).ok, false);
});

test("the diagnostic ledger scope is an OWED key — the I-X3 leg names where it was measured", () => {
  // The spec-auditor's F1: the receipt presented the scratch ledger purely as a SAFETY property
  // ("it can never touch the operator's terminals") while it was also the reason the enforcing
  // governor counted zero. Both directions are now stated, and the receipt cannot drop the marker.
  assert.ok(REQUIRED_OWED_KEYS.includes("diagnostic_ledger_scope"));
  const owed = fullOwed();
  delete owed.diagnostic_ledger_scope;
  assert.equal(owedMarkersAreComplete(owed).ok, false);
});

test("an OWED block naming every unevidenced leg passes", () => {
  const v = owedMarkersAreComplete(fullOwed());
  assert.equal(v.ok, true, v.reasons.join("; "));
});

test("every required OWED key is load-bearing — dropping any one fails", () => {
  for (const key of REQUIRED_OWED_KEYS) {
    const owed = fullOwed();
    delete owed[key];
    const v = owedMarkersAreComplete(owed);
    assert.equal(v.ok, false, `dropping ${key} still passed`);
    assert.ok(v.reasons.some((r) => r.includes(key)), v.reasons.join("; "));
  }
});

test("an empty or whitespace OWED string is not a marker", () => {
  const owed = fullOwed();
  owed.spoken_microphone = "   ";
  assert.equal(owedMarkersAreComplete(owed).ok, false);
});

test("an OWED value that names no issue/decision reference is refused", () => {
  const owed = fullOwed();
  owed.physical_key_delivery = "some of this is still outstanding";
  const v = owedMarkersAreComplete(owed);
  assert.equal(v.ok, false);
  assert.ok(v.reasons.some((r) => /physical_key_delivery/.test(r)), v.reasons.join("; "));
});

// ---- the composed verdict ----------------------------------------------------------------------

test("composeVerdict fails on any false check and names every one of them", () => {
  const v = composeVerdict({ a: true, b: false, c: true, d: false });
  assert.equal(v.ok, false);
  assert.deepEqual(v.failed, ["b", "d"]);
});

test("composeVerdict refuses an EMPTY check set — a receipt with no legs is not a pass", () => {
  const v = composeVerdict({});
  assert.equal(v.ok, false);
  assert.ok(v.failed.includes("no_checks_were_recorded"));
});

test("composeVerdict treats a non-boolean as a failure, never as truthy", () => {
  const v = composeVerdict({ a: "yes", b: 1, c: true });
  assert.equal(v.ok, false);
  assert.deepEqual(v.failed, ["a", "b"]);
});
