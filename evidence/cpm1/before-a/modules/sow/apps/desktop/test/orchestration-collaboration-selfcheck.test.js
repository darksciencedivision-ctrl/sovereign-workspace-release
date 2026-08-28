"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

process.env.SHELL_SELFCHECK_RECEIPT_DIR = fs.mkdtempSync(
  path.join(os.tmpdir(), "u337-selfcheck-"));
const {
  runOrchestrationCollaborationSelfCheck, governedDispatchChecks, RECEIPT_PATH,
} = require("../selfcheck/orchestration-collaboration-selfcheck");

const feed = () => ({
  schema: "conductor_dispatch_feed@1.0",
  dispatched: true,
  assignments: [{ task: "t-1", node: "worker-A" }],
  by_descriptor: true,
  accepted_count: 2,
  acceptance_verdict: "PASS",
  acceptance_packet: "m-acceptance",
  operator_disposition: "pending",
  legs: { conductor: "mock", workers: "mock" },
  live_workers_owed: { owed: true, issue: "U58" },
  torn_down: true,
});
const source = () => ({ ok: true, feed: feed() });

function runtime(overrides = {}) {
  return {
    sourceIdentity: () => ({ commit: "a".repeat(40), tracked_product_tree_clean: true }),
    runGovernedDispatch: async () => source(),
    conductorDispatchFeed: () => source(),
    conductorState: () => ({
      dispatchRan: true, dispatchSourced: true, paneId: "pane-1",
      dispatch: { accepted: 2, owed: true, text: "2 accepted / LIVE worker OWED" },
    }),
    win: { webContents: { executeJavaScript: async () => ({
      isConductor: true, text: "dispatch: 2 accepted / LIVE worker OWED",
    }) } },
    log: () => {},
    ...overrides,
  };
}

test("the governed dispatch verdict requires candidates, gates, pending operator disposition and teardown", () => {
  assert.equal(Object.values(governedDispatchChecks(source())).every(Boolean), true);
  assert.equal(governedDispatchChecks({ ok: true, feed: { ...feed(), torn_down: false } })
    .collaboration_resources_torn_down, false);
  assert.equal(governedDispatchChecks({ ok: true, feed: {
    ...feed(), legs: { conductor: "live", workers: "live" },
  } }).no_live_provider_leg_was_claimed, false);
});

test("the self-check receipt binds source, a fresh governed run, main state and renderer", async () => {
  const receipt = await runOrchestrationCollaborationSelfCheck(runtime());
  assert.equal(receipt.ok, true, JSON.stringify(receipt, null, 2));
  assert.equal(receipt.check, "orchestration-collaboration");
  assert.equal(receipt.live_exchanges, 0);
  assert.ok(Number.isInteger(receipt.electron_main_pid));
  assert.equal(receipt.failed_checks.length, 0);
  assert.equal(receipt.missing_checks.length, 0);
  assert.equal(fs.existsSync(RECEIPT_PATH), true);
});

test("a dirty product tree or malformed production feed fails the receipt", async () => {
  const receipt = await runOrchestrationCollaborationSelfCheck(runtime({
    sourceIdentity: () => ({ commit: "b".repeat(40), tracked_product_tree_clean: false }),
    runGovernedDispatch: async () => ({ ok: true, feed: { ...feed(), acceptance_packet: null } }),
  }));
  assert.equal(receipt.ok, false);
  assert.ok(receipt.failed_checks.includes("receipt_matches_clean_tracked_product_tree"));
  assert.ok(receipt.failed_checks.includes("fresh_synthesis_acceptance_packet_exists"));
});
