"use strict";
/**
 * Approval-drawer SOURCE + decision-router tests (Phase 17D `.events`) — the glue that turns the
 * bounded `py -3.12 tools/live/emit_approval_drawer.py` / `emit_approval_decision.py` emitters into the
 * drawer the shell renders and the governed decide it routes.
 *
 * Two layers, mirroring statusbar-governor-source.test.js:
 *   (1) unit — a FAKE spawn proves the parse + timeout + fail-closed fold deterministically, with no
 *       live host: good drawer feed, malformed shape, non-zero exit, non-JSON, timeout, launch error;
 *       the recorded-events log reaches BOTH emitters (the decide must resolve over the same queue the
 *       operator was looking at); a governed refusal is surfaced as-is, a bad decision never reaches
 *       Python;
 *   (2) live integration — the REAL emitters over a REAL recorded log: an empty session yields an
 *       EMPTY drawer (finding F2 — no canned trio), a recorded protected utterance yields exactly that
 *       row re-derived by the real classifier, and approving a recorded clarification is REFUSED
 *       (invariant 16), self-authorizing nothing.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const { SessionApprovalLog } = require("../approvals/session-events");
const {
  APPROVAL_DRAWER_FEED_SCHEMA, APPROVAL_DECISION_FEED_SCHEMA, ApprovalSourceError,
  APPROVAL_DECISION_KEY_ENV, SESSION_APPROVAL_DECISION_KEY, approvalEmitterEnv,
  isWellFormedDrawerFeed, isWellFormedDecisionFeed, unavailableApprovalFeed,
  fetchApprovalDrawerFeed, sourceApprovalDrawerFeed, routeApprovalDecision,
} = require("../approvals/drawer-source");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;

const GOOD_DRAWER = {
  schema: APPROVAL_DRAWER_FEED_SCHEMA,
  sourced: true,
  objective: "obj",
  drawer: {
    schema: "approval_drawer@1.0",
    badge_count: 3,
    kind_counts: { plan: 1, protected_action: 1, clarification: 1 },
    pending: [
      { item_id: "ap-1", seq: 1, kind: "plan", summary: "Plan", origin: "conductor", approvable: true, ref: null, detail: {} },
      { item_id: "ap-2", seq: 2, kind: "protected_action", summary: "spawn", origin: "typed", approvable: true, ref: "q-abc", detail: {} },
      { item_id: "ap-3", seq: 3, kind: "clarification", summary: "clarify", origin: "voice", approvable: false, ref: null, detail: {} },
    ],
  },
  badge_count: 3,
  kinds_present: ["clarification", "plan", "protected_action"],
  event_count: 3,
  decision_count: 0,
  demo_items: false,
  side_effects_owed: { owed: true, issue: "17E", note: "owed" },
  torn_down: true,
};

const REFUSED_DECISION = {
  schema: APPROVAL_DECISION_FEED_SCHEMA,
  resolved: false, refused: true,
  reason: "ApprovalError: approval item 'ap-3' is not approvable (invariant 16, no override path)",
  item_id: "ap-3", decision: "approve", self_authorized: false, torn_down: true,
};

function fakeSpawn({ stdout = "", stderr = "", code = 0, neverExit = false, throwOnSpawn = false, emitError = null } = {}) {
  const calls = [];
  const spawn = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    if (throwOnSpawn) throw new Error("ENOENT");
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => { child.killed = true; };
    child.killed = false;
    setImmediate(() => {
      if (emitError) { child.emit("error", new Error(emitError)); return; }
      if (stdout) child.stdout.emit("data", Buffer.from(stdout));
      if (stderr) child.stderr.emit("data", Buffer.from(stderr));
      if (!neverExit) child.emit("exit", code);
    });
    return child;
  };
  spawn.calls = calls;
  return spawn;
}

// ---- (1a) unit: the drawer read-source --------------------------------------
test("fetchApprovalDrawerFeed parses a good drawer feed and invokes --emit-approval-drawer", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_DRAWER) });
  const feed = await fetchApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(feed.schema, APPROVAL_DRAWER_FEED_SCHEMA);
  assert.equal(feed.drawer.pending.length, 3);
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--emit-approval-drawer"));
  assert.ok(args.some((a) => a.endsWith("emit_approval_drawer.py")));
});

test("sourceApprovalDrawerFeed returns {ok:true, feed} on a good drawer", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_DRAWER) });
  const res = await sourceApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, true);
  assert.equal(res.feed.badge_count, 3);
});

test("non-zero exit → {ok:false} with the fail-closed empty drawer (never throws)", async () => {
  const spawn = fakeSpawn({ code: 2, stderr: "boom" });
  const res = await sourceApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
  assert.match(res.error, /exited 2/);
  assert.equal(res.feed.sourced, false);
  assert.deepEqual(res.feed.drawer.pending, []);
});

test("non-JSON output → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ stdout: "not json" });
  const res = await sourceApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
  assert.match(res.error, /non-JSON/);
});

test("malformed drawer feed (no pending array) → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: APPROVAL_DRAWER_FEED_SCHEMA, drawer: {} }) });
  const res = await sourceApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
  assert.match(res.error, /malformed/);
});

test("wrong schema → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ schema: "other@9", drawer: { pending: [] } }) });
  const res = await sourceApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
});

test("timeout → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ neverExit: true });
  const res = await sourceApprovalDrawerFeed({ spawn, cwd: REPO_ROOT, timeoutMs: 30 });
  assert.equal(res.ok, false);
  assert.match(res.error, /timed out/);
});

test("spawn launch throw → {ok:false} fail-closed (never throws into renderer)", async () => {
  const spawn = fakeSpawn({ throwOnSpawn: true });
  const res = await sourceApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
  assert.match(res.error, /could not launch/);
});

test("fetchApprovalDrawerFeed (strict) throws ApprovalSourceError on a bad exit", async () => {
  const spawn = fakeSpawn({ code: 2 });
  await assert.rejects(() => fetchApprovalDrawerFeed({ spawn, cwd: REPO_ROOT }), ApprovalSourceError);
});

// ---- (1b) unit: the decision router -----------------------------------------
test("routeApprovalDecision surfaces a GOVERNED refusal as ok:true (not a fault)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(REFUSED_DECISION) });
  const res = await routeApprovalDecision({ spawn, cwd: REPO_ROOT, itemId: "ap-3", decision: "approve" });
  assert.equal(res.ok, true);                    // well-formed decision feed
  assert.equal(res.feed.resolved, false);        // ...that records a governed refusal
  assert.equal(res.feed.refused, true);
  assert.equal(res.feed.self_authorized, false); // load-bearing: the shell did not self-authorize
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--emit-approval-decision"));
  assert.ok(args.includes("--item") && args.includes("ap-3"));
  assert.ok(args.includes("--decision") && args.includes("approve"));
});

test("routeApprovalDecision forwards --reason only when non-empty", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify({ ...REFUSED_DECISION, resolved: true, refused: false }) });
  await routeApprovalDecision({ spawn, cwd: REPO_ROOT, itemId: "ap-2", decision: "reject", reason: "later" });
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--reason") && args.includes("later"));
});

test("routeApprovalDecision refuses to route a bad decision (never reaches Python as approve/reject)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(REFUSED_DECISION) });
  const res = await routeApprovalDecision({ spawn, cwd: REPO_ROOT, itemId: "ap-2", decision: "sudo-approve" });
  assert.equal(res.ok, false);
  assert.equal(spawn.calls.length, 0); // nothing spawned — the shell forwarded no illegal decision
});

test("routeApprovalDecision requires an item id", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(REFUSED_DECISION) });
  const res = await routeApprovalDecision({ spawn, cwd: REPO_ROOT, itemId: "", decision: "reject" });
  assert.equal(res.ok, false);
  assert.equal(spawn.calls.length, 0);
});

test("routeApprovalDecision non-zero exit → {ok:false} fail-closed", async () => {
  const spawn = fakeSpawn({ code: 2, stderr: "boom" });
  const res = await routeApprovalDecision({ spawn, cwd: REPO_ROOT, itemId: "ap-2", decision: "reject" });
  assert.equal(res.ok, false);
});

// ---- well-formedness predicates ---------------------------------------------
test("isWellFormedDrawerFeed accepts a drawer with pending[], rejects others", () => {
  assert.equal(isWellFormedDrawerFeed(GOOD_DRAWER), true);
  assert.equal(isWellFormedDrawerFeed({ schema: APPROVAL_DRAWER_FEED_SCHEMA, drawer: {} }), false);
  assert.equal(isWellFormedDrawerFeed({ schema: "x@1", drawer: { pending: [] } }), false);
  assert.equal(isWellFormedDrawerFeed(null), false);
});

test("isWellFormedDecisionFeed accepts a boolean resolved, rejects others", () => {
  assert.equal(isWellFormedDecisionFeed(REFUSED_DECISION), true);
  assert.equal(isWellFormedDecisionFeed({ schema: APPROVAL_DECISION_FEED_SCHEMA, resolved: "no" }), false);
  assert.equal(isWellFormedDecisionFeed({ schema: "x@1", resolved: true }), false);
});

test("unavailableApprovalFeed is an honest empty drawer", () => {
  const f = unavailableApprovalFeed("boom");
  assert.equal(f.sourced, false);
  assert.equal(f.reason, "boom");
  assert.deepEqual(f.drawer.pending, []);
  assert.equal(f.side_effects_owed.issue, "17E");
  assert.equal(f.demo_items, false);
});

// ---- (1c) unit: the recorded log reaches both emitters ----------------------
test("the events log path is forwarded to the drawer emitter", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_DRAWER) });
  await fetchApprovalDrawerFeed({ spawn, cwd: REPO_ROOT, eventsPath: "C:/tmp/session-events.jsonl" });
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--events"));
  assert.ok(args.includes("C:/tmp/session-events.jsonl"));
});

test("no events path yields no --events flag (an empty session, not a broken call)", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(GOOD_DRAWER) });
  await fetchApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(spawn.calls[0].args.includes("--events"), false);
});

test("the decide routes over the SAME log the drawer was folded from", async () => {
  const spawn = fakeSpawn({ stdout: JSON.stringify(REFUSED_DECISION) });
  await routeApprovalDecision({ spawn, cwd: REPO_ROOT, itemId: "ap-1", decision: "reject",
    eventsPath: "C:/tmp/session-events.jsonl" });
  const args = spawn.calls[0].args;
  assert.ok(args.includes("--events") && args.includes("C:/tmp/session-events.jsonl"));
});

// ---- (2) live integration: the REAL emitters --------------------------------
test("LIVE: an empty session yields an EMPTY drawer — the canned trio is gone (finding F2)",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    const res = await sourceApprovalDrawerFeed({ cwd: REPO_ROOT, timeoutMs: 60000 });
    assert.equal(res.ok, true);
    assert.equal(res.feed.sourced, true);
    assert.equal(res.feed.badge_count, 0);
    assert.deepEqual(res.feed.drawer.pending, []);
    assert.equal(res.feed.demo_items, false);
  });

test("LIVE: a RECORDED protected utterance yields exactly that row, re-derived by the real classifier",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sov-appr-"));
    const logPath = path.join(dir, "session-events.jsonl");
    try {
      const sessionLog = new SessionApprovalLog({ logPath });
      sessionLog.begin();
      sessionLog.recordUtterance({
        schema: "conductor_voice_feed@1.0", sourced: true,
        outcome: { kind: "proposed_action", source: "voice", text: "spawn a gpt-5.5 worker node",
          confidence: 0.95 },
      });
      const res = await sourceApprovalDrawerFeed({ cwd: REPO_ROOT, timeoutMs: 60000, eventsPath: logPath });
      assert.equal(res.ok, true);
      assert.equal(res.feed.badge_count, 1);
      assert.equal(res.feed.drawer.pending[0].kind, "protected_action");
      assert.equal(res.feed.drawer.pending[0].detail.verb, "spawn");
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

// ---- W-43: producer authenticity for approval decisions (U206) ---------------
test("W-43: the session key is minted once and reaches BOTH emitters", () => {
  assert.match(SESSION_APPROVAL_DECISION_KEY, /^[0-9a-f]{64}$/,
    "a 32-byte random key, hex — the Python side refuses anything shorter");
  const env = approvalEmitterEnv({ PATH: "C:\\Windows" });
  assert.equal(env[APPROVAL_DECISION_KEY_ENV], SESSION_APPROVAL_DECISION_KEY);
  assert.equal(env.PATH, "C:\\Windows", "the rest of the environment must survive");
});

test("W-43: an INHERITED key of the same name cannot ride through", () => {
  // The stage-3/stage-4 rule the credential scrubber already applies: the shell's own minted value
  // is applied AFTER the spread, so an operator-set variable never becomes the session key.
  const env = approvalEmitterEnv({ [APPROVAL_DECISION_KEY_ENV]: "00".repeat(32) });
  assert.equal(env[APPROVAL_DECISION_KEY_ENV], SESSION_APPROVAL_DECISION_KEY);
});

test("W-43: both emitters are spawned WITH the key — a builder without it refuses every decision", async () => {
  const drawerSpawn = fakeSpawn({ stdout: JSON.stringify(GOOD_DRAWER) });
  await fetchApprovalDrawerFeed({ spawn: drawerSpawn, cwd: REPO_ROOT });
  assert.equal(drawerSpawn.calls[0].opts.env[APPROVAL_DECISION_KEY_ENV], SESSION_APPROVAL_DECISION_KEY);
  const decideSpawn = fakeSpawn({ stdout: JSON.stringify(REFUSED_DECISION) });
  await routeApprovalDecision({ spawn: decideSpawn, cwd: REPO_ROOT, itemId: "ap-1", decision: "reject" });
  assert.equal(decideSpawn.calls[0].opts.env[APPROVAL_DECISION_KEY_ENV], SESSION_APPROVAL_DECISION_KEY);
});

test("a well-formed feed that says sourced:false is NOT ok — the honest reason reaches the chrome", async () => {
  // Before this, main.js folded `res.ok` into `sourced` and a Python-declared unavailable feed was
  // rendered as a successfully-sourced EMPTY drawer: the operator saw "nothing pending" for a log
  // that could not be re-derived. Registered as its own finding — it predates W-43 and covers every
  // unavailable feed — but W-43's repair is invisible without it.
  const spawn = fakeSpawn({ stdout: JSON.stringify({ ...GOOD_DRAWER, sourced: false,
    reason: "SessionEventError: recorded decision on 'ap-1' carries no valid producer authenticity stamp" }) });
  const res = await sourceApprovalDrawerFeed({ spawn, cwd: REPO_ROOT });
  assert.equal(res.ok, false);
  assert.match(res.error, /producer authenticity/);
});

test("LIVE: W-43 END TO END — a producer-minted decision persists, a hand-built one does not",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    // The cross-process proof no Python test can give: the decision is minted by ONE `py -3.12`
    // process and verified by ANOTHER, so it exercises the key delivery and not just the HMAC.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sov-appr-w43-"));
    const logPath = path.join(dir, "session-events.jsonl");
    try {
      const sessionLog = new SessionApprovalLog({ logPath });
      sessionLog.begin();
      sessionLog.recordUtterance({
        schema: "conductor_voice_feed@1.0", sourced: true,
        outcome: { kind: "proposed_action", source: "voice", text: "spawn a gpt-5.5 worker node",
          confidence: 0.95 },
      });
      const before = await sourceApprovalDrawerFeed({ cwd: REPO_ROOT, timeoutMs: 60000, eventsPath: logPath });
      assert.equal(before.feed.badge_count, 1, "the row is pending before anything decides it");

      // (1) the genuine path: the authority resolves, mints, the shell appends, the drawer honors it.
      const decided = await routeApprovalDecision({ cwd: REPO_ROOT, timeoutMs: 60000, itemId: "ap-1",
        decision: "reject", reason: "not now", eventsPath: logPath });
      assert.equal(decided.feed.resolved, true);
      assert.equal(sessionLog.recordGovernedDecision(decided.feed.decision_event) !== null, true);
      const after = await sourceApprovalDrawerFeed({ cwd: REPO_ROOT, timeoutMs: 60000, eventsPath: logPath });
      assert.equal(after.ok, true);
      assert.equal(after.feed.badge_count, 0, "a producer-minted decision disposes the row it names");

      // (2) the forged path: the same decision, written straight into the log by something that is
      //     not the producer. This is U206's exact attack, and it is now refused.
      const forgedLog = path.join(dir, "forged.jsonl");
      const lines = fs.readFileSync(logPath, "utf8").trim().split(/\r?\n/);
      const forged = JSON.parse(lines[1]);
      delete forged.decision.producer;
      delete forged.decision.authenticity;
      fs.writeFileSync(forgedLog, `${lines[0]}\n${JSON.stringify(forged)}\n`);
      const tampered = await sourceApprovalDrawerFeed({ cwd: REPO_ROOT, timeoutMs: 60000, eventsPath: forgedLog });
      assert.equal(tampered.ok, false, "a hand-built decision must not dispose an approvable row");
      assert.match(tampered.error, /authenticity/);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

test("LIVE: the decide emitter REFUSES approving a recorded clarification (invariant 16), self-authorizing nothing",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sov-appr-"));
    const logPath = path.join(dir, "session-events.jsonl");
    try {
      const sessionLog = new SessionApprovalLog({ logPath });
      sessionLog.begin();
      sessionLog.recordUtterance({
        schema: "conductor_voice_feed@1.0", sourced: true,
        outcome: { kind: "clarify", source: "voice", text: "uh do the roster thing", confidence: 0.2 },
      });
      const res = await routeApprovalDecision({ cwd: REPO_ROOT, timeoutMs: 60000, itemId: "ap-1",
        decision: "approve", eventsPath: logPath });
      assert.equal(res.ok, true);
      assert.equal(res.feed.resolved, false);
      assert.equal(res.feed.refused, true);
      assert.equal(res.feed.self_authorized, false);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
