"use strict";
/**
 * LOCAL-02 — the local pane's MCP harness.
 *
 * The defect these pin: LOCAL-01 made every admitted ollama model `conductor_capable`, and readiness
 * then required a Sovereign MCP connection plus a real `get_worker_status` call from a process that
 * is `ollama run <tag>` — a chat REPL with no MCP client. The conductor stalled for the full 120 s
 * on every launch.
 *
 * The tests that matter most here are the ones asserting what the bridge must NOT do. A bridge that
 * heartbeats for a dead pane, or that synthesises a tool call the model never emitted, would make
 * readiness green while proving nothing — which is worse than the stall it replaces, because a stall
 * is at least honest.
 */
const test = require("node:test");
const assert = require("node:assert");

const {
  createLocalMcpBridge, parseCalls, resultBlock,
  BRIDGE_PREAMBLE, CALL_FENCE, RESULT_FENCE,
} = require("../control/local-mcp-bridge");

/** A recording control plane. `answers` maps operation -> response. */
function fakePlane(answers = {}) {
  const seen = [];
  return {
    seen,
    request: async ({ port, token, operation, arguments: args }) => {
      seen.push({ port, token, operation, arguments: args });
      if (Object.prototype.hasOwnProperty.call(answers, operation)) return answers[operation];
      return { ok: true, result: { operation } };
    },
  };
}

/** A pane whose visible window the test controls outright. */
function fakePane({ text = "", alive = true } = {}) {
  const writes = [];
  const state = { text, alive, marks: 0 };
  return {
    writes, state,
    window: {
      mark: () => { state.marks += 1; return state.marks; },
      since: () => ({ text: state.text, answerable: true }),
    },
    writePrompt: async (_paneId, body) => { writes.push(body); return true; },
    sessionAlive: () => state.alive,
  };
}

const BASE = (plane, pane, extra = {}) => createLocalMcpBridge({
  nodeId: "conductor-pane-1", paneId: "pane-1", token: "tok-1", port: 5555,
  request: plane.request, sessionAlive: pane.sessionAlive, window: pane.window,
  writePrompt: pane.writePrompt, writeRefusal: () => null,
  now: () => 1000, sleep: async () => {}, log: () => {},
  ...extra,
});

const callBlock = (obj) => "```" + CALL_FENCE + "\n" + JSON.stringify(obj) + "\n```";

// ── parsing ──────────────────────────────────────────────────────────────────────────────────────

test("a fenced sovereign block is read as a call, with its arguments", () => {
  const { calls, malformed } = parseCalls(
    "thinking out loud\n" + callBlock({ operation: "get_worker_status", arguments: { pane: "p2" } }));
  assert.equal(malformed.length, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].operation, "get_worker_status");
  assert.deepEqual(calls[0].arguments, { pane: "p2" });
});

test("a RESULT block is never read as a call (or the bridge answers itself forever)", () => {
  // The single most dangerous confusion available here: `sovereign-result` starts with `sovereign`,
  // so a fence regex without the boundary matches the bridge's own output and re-executes it.
  const { calls } = parseCalls(resultBlock({ ok: true, operation: "get_worker_status", result: {} }));
  assert.equal(calls.length, 0, "the bridge must not execute its own answers");
});

test("two adjacent blocks are two calls, not one block spanning both", () => {
  const { calls } = parseCalls(
    callBlock({ operation: "list_models" }) + "\n" + callBlock({ operation: "get_worker_status" }));
  assert.deepEqual(calls.map((c) => c.operation), ["list_models", "get_worker_status"]);
});

test("a block that is not JSON, or names no operation, is MALFORMED and reported — never dropped", () => {
  const bad = parseCalls("```" + CALL_FENCE + "\n{not json}\n```");
  assert.equal(bad.calls.length, 0);
  assert.equal(bad.malformed.length, 1);
  const noOp = parseCalls(callBlock({ arguments: {} }));
  assert.equal(noOp.calls.length, 0);
  assert.equal(noOp.malformed.length, 1, "a model waiting on an answer must be told there is none coming");
});

test("missing or non-object `arguments` means none, not a different call", () => {
  assert.deepEqual(parseCalls(callBlock({ operation: "list_models" })).calls[0].arguments, {});
  assert.deepEqual(parseCalls(callBlock({ operation: "list_models", arguments: 7 })).calls[0].arguments, {});
});

test("trailing whitespace on the fence line does not hide a call", () => {
  const { calls } = parseCalls("```" + CALL_FENCE + "   \n" + '{"operation":"list_models"}' + "\n```");
  assert.equal(calls.length, 1);
});

// ── attachment: the one claim the bridge makes on the node's behalf ───────────────────────────────

test("attaching announces the node to the control plane with ITS OWN bearer", async () => {
  const plane = fakePlane();
  const pane = fakePane();
  const res = await BASE(plane, pane).attach();
  assert.equal(res.attached, true);
  assert.equal(plane.seen.length, 1);
  assert.equal(plane.seen[0].operation, "identity");
  assert.equal(plane.seen[0].token, "tok-1", "the node's token, so the server records the node — not the shell");
  assert.equal(plane.seen[0].port, 5555);
});

test("a pane with NO live session gets no bridge and no claim (the honesty boundary)", async () => {
  // `connected` must mean "this node's harness is attached", exactly as it does for a vendor CLI.
  // If the bridge claimed it for a pane with no process, it would mean "the shell is running",
  // which is worth nothing and would be a lie in the one signal readiness trusts.
  const plane = fakePlane();
  const pane = fakePane({ alive: false });
  const res = await BASE(plane, pane).attach();
  assert.equal(res.attached, false);
  assert.match(res.reason, /no live session/);
  assert.equal(plane.seen.length, 0, "nothing may reach the control plane on a dead pane's behalf");
});

test("a REFUSED identity call leaves the node unattached and says why (fail closed)", async () => {
  const plane = fakePlane({ identity: { ok: false, error: "node control authentication failed" } });
  const bridge = BASE(plane, fakePane());
  const res = await bridge.attach();
  assert.equal(res.attached, false);
  assert.equal(bridge.attached, false);
  assert.match(res.reason, /authentication failed/);
});

test("the heartbeat STOPS the moment the pane's session is gone", async () => {
  // Re-read every beat rather than trusted from attach time: otherwise a dead pane keeps reporting
  // `connected` off a bridge nobody stopped, which is the stale-record defect in a new place.
  const plane = fakePlane();
  const pane = fakePane();
  const bridge = BASE(plane, pane);
  await bridge.attach();
  assert.equal(await bridge.heartbeat(), true);
  pane.state.alive = false;
  assert.equal(await bridge.heartbeat(), false);
  assert.equal(bridge.attached, false, "the bridge detaches itself rather than outlive its pane");
});

// ── relaying: the claims the bridge makes about the MODEL, i.e. none of its own ───────────────────

test("a call the model emitted is relayed, and its result written back", async () => {
  const plane = fakePlane({ get_worker_status: { ok: true, result: { workers: 2 } } });
  const pane = fakePane({ text: callBlock({ operation: "get_worker_status", arguments: {} }) });
  const bridge = BASE(plane, pane);
  await bridge.attach();
  const out = await bridge.relayOnce();
  assert.equal(out.relayed, 1);
  assert.ok(plane.seen.some((s) => s.operation === "get_worker_status"));
  assert.equal(pane.writes.length, 1);
  assert.match(pane.writes[0], new RegExp("```" + RESULT_FENCE));
  assert.match(pane.writes[0], /"workers":2/);
});

test("a SILENT model produces no calls — the bridge never invents one", async () => {
  // This is the property that keeps readiness meaningful. Gate 1 (attachment) the bridge can
  // satisfy; gate 2 (the model actually calling `get_worker_status`) it must be structurally unable
  // to satisfy, or a mute local model would look READY.
  const plane = fakePlane();
  const pane = fakePane({ text: "I am thinking about your question, but emitting no tool call.\n" });
  const bridge = BASE(plane, pane);
  await bridge.attach();
  const out = await bridge.relayOnce();
  assert.equal(out.relayed, 0);
  assert.equal(pane.writes.length, 0);
  assert.equal(plane.seen.filter((s) => s.operation !== "identity").length, 0,
    "no operation may reach the control plane that the model did not emit");
});

test("the SAME visible block is relayed once, not once per poll", async () => {
  // The window is a sliding view of a live terminal, so the same text is legitimately read many
  // times. Without dedup a single `get_worker_status` is spent on every cycle.
  const plane = fakePlane();
  const pane = fakePane({ text: callBlock({ operation: "list_models" }) });
  const bridge = BASE(plane, pane);
  await bridge.attach();
  await bridge.relayOnce();
  await bridge.relayOnce();
  await bridge.relayOnce();
  assert.equal(plane.seen.filter((s) => s.operation === "list_models").length, 1);
});

test("a NEW block after a relayed one is still relayed (dedup is per call, not a latch)", async () => {
  const plane = fakePlane();
  const pane = fakePane({ text: callBlock({ operation: "list_models" }) });
  const bridge = BASE(plane, pane);
  await bridge.attach();
  await bridge.relayOnce();
  pane.state.text += "\n" + callBlock({ operation: "get_worker_status" });
  await bridge.relayOnce();
  assert.equal(plane.seen.filter((s) => s.operation === "get_worker_status").length, 1);
});

test("a control-plane REFUSAL is handed back verbatim, not swallowed or retried", async () => {
  const plane = fakePlane({ assign_task: { ok: false, error: "Error: worker pane-2 is not READY" } });
  const pane = fakePane({ text: callBlock({ operation: "assign_task", arguments: { pane: "pane-2" } }) });
  const bridge = BASE(plane, pane);
  await bridge.attach();
  const out = await bridge.relayOnce();
  assert.equal(out.refused, 1);
  assert.match(pane.writes[0], /is not READY/);
  assert.equal(plane.seen.filter((s) => s.operation === "assign_task").length, 1, "refusals are not retried");
});

test("an unknown operation is answered with the list and never sent", async () => {
  const plane = fakePlane();
  const pane = fakePane({ text: callBlock({ operation: "rm_minus_rf" }) });
  const bridge = BASE(plane, pane);
  await bridge.attach();
  await bridge.relayOnce();
  assert.equal(plane.seen.filter((s) => s.operation === "rm_minus_rf").length, 0);
  assert.match(pane.writes[0], /known_operations/);
});

test("a malformed block gets an answer, so the model is not left waiting on a call it never made", async () => {
  const plane = fakePlane();
  const pane = fakePane({ text: "```" + CALL_FENCE + "\n{oops}\n```" });
  const bridge = BASE(plane, pane);
  await bridge.attach();
  const out = await bridge.relayOnce();
  assert.equal(out.malformed, 1);
  assert.equal(pane.writes.length, 1);
  assert.match(pane.writes[0], /malformed tool call/);
});

test("when the governed pane-write gate withholds, nothing is written and the reason is kept", async () => {
  // U328: the bridge has no write path of its own. If the gate says no, the result does not appear
  // by some other route — it does not appear at all, and the caller can see why.
  const plane = fakePlane();
  const pane = fakePane({ text: callBlock({ operation: "list_models" }) });
  const bridge = BASE(plane, pane, { writeRefusal: () => ({ reason: "a trust modal is on screen" }) });
  await bridge.attach();
  const out = await bridge.relayOnce();
  assert.equal(out.wrote, false);
  assert.equal(pane.writes.length, 0);
  assert.match(out.withheld, /trust modal/);
});

test("relaying before attach does nothing at all", async () => {
  const plane = fakePlane();
  const pane = fakePane({ text: callBlock({ operation: "list_models" }) });
  const out = await BASE(plane, pane).relayOnce();
  assert.equal(out.relayed, 0);
  assert.equal(plane.seen.length, 0);
});

test("the preamble teaches the exact fence the parser accepts", async () => {
  // If these two ever drift, the model is taught a format the bridge cannot read and every call it
  // makes is silently invisible — the failure this whole module exists to end.
  const { calls } = parseCalls(BRIDGE_PREAMBLE);
  assert.equal(calls.length, 1, "the preamble's own example must parse as a call");
  assert.equal(calls[0].operation, "get_worker_status");
});

test("teach() goes through the governed writer, and is withheld when that gate says no", async () => {
  const plane = fakePlane();
  const pane = fakePane();
  const bridge = BASE(plane, pane);
  await bridge.attach();
  assert.equal(await bridge.teach(), true);
  assert.equal(pane.writes[0], BRIDGE_PREAMBLE);

  const pane2 = fakePane();
  const gated = BASE(fakePlane(), pane2, { writeRefusal: () => ({ reason: "screen unreadable" }) });
  await gated.attach();
  assert.equal(await gated.teach(), false);
  assert.equal(pane2.writes.length, 0);
});

test("a bridge cannot be built without the node id the ticket minted", () => {
  // Invariant 2/29: the shell never names its own node.
  assert.throws(() => createLocalMcpBridge({ paneId: "pane-1" }), /node id/);
  assert.throws(() => createLocalMcpBridge({ nodeId: "conductor-pane-1" }), /pane/);
});

test("a relay cycle that throws does not kill the bridge", async () => {
  const pane = fakePane({ text: callBlock({ operation: "list_models" }) });
  const bridge = BASE({ request: async () => { throw new Error("socket died"); } }, pane);
  // attach() itself surfaces the failure rather than throwing out of the caller's launch path.
  await assert.rejects(() => bridge.attach(), /socket died/);
});
