"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createConductorReadiness } = require("../control/conductor-readiness");

function harness(overrides = {}) {
  let launch = { nodeId: "cond-1", pid: 55, sessionGeneration: 3, supervised: true,
    operationalState: "STARTING" };
  let clock = 1000;
  let calls = 0;
  const writes = [];
  const io = {
    descriptor: () => ({ provider_id: "p", model_id: "m" }),
    launch: () => launch,
    setLaunch: (next) => { launch = next; },
    push: () => {},
    admit: () => ({ ok: true, readiness_turns: 2, decided_by: "descriptor",
      provider_id: "p", model_id: "m", selection_source: "test" }),
    waitForNodeMcp: async () => true,
    mcpTimeoutMs: () => 100,
    operationCount: () => { calls += 1; return calls; },
    buildProbe: () => ({ prompt: `probe-${writes.length + 1}`, expected: "answer" }),
    window: { mark: () => 0, since: () => ({ answerable: true, text: "answer" }) },
    paneId: () => "pane-1",
    writeRefusal: () => null,
    writePrompt: async (_pane, prompt) => { writes.push(prompt); return true; },
    responseDeadlineMs: () => 100,
    now: () => clock,
    sleep: async (ms) => { clock += ms; },
    answerObserved: () => ({ seen: true }),
    processIdentity: () => ({ pid: 55, generation: 3 }),
    mcpState: () => ({ state: "connected" }),
    observedEvidence: () => ({ process_supervised: true, mcp_connected: true }),
    ...overrides,
  };
  return { run: createConductorReadiness(io), launch: () => launch, writes };
}

test("the admitted descriptor drives its declared number of readiness turns", async () => {
  const { run, launch, writes } = harness();
  const result = await run();
  assert.equal(result.ready, true);
  assert.equal(writes.length, 2);
  assert.equal(launch().readiness.readiness_responses, 2);
  assert.equal(launch().readiness.status_tool_succeeded, true);
  assert.equal(launch().readiness.readiness_response_succeeded, true,
    "success evidence must survive outside the loop that measured it");
});

test("an admission refusal is honored before MCP or pane activity", async () => {
  let waited = false;
  const { run, writes } = harness({
    admit: () => ({ ok: false, state: "FAILED", reason: "descriptor refused" }),
    waitForNodeMcp: async () => { waited = true; return true; },
  });
  const result = await run();
  assert.deepEqual(result, { ready: false, state: "FAILED", reason: "descriptor refused" });
  assert.equal(waited, false);
  assert.equal(writes.length, 0);
});

test("a modal refusal withholds every readiness byte", async () => {
  const { run, writes } = harness({ writeRefusal: () => ({ state: "AUTH_REQUIRED", reason: "login" }) });
  const result = await run();
  assert.equal(result.state, "AUTH_REQUIRED");
  assert.match(result.reason, /withheld: login/);
  assert.equal(writes.length, 0);
});

test("a missing tool-backed answer stalls and names the failing turn", async () => {
  let clock = 0;
  const { run } = harness({
    operationCount: () => 0,
    now: () => clock,
    sleep: async (ms) => { clock += ms; },
    responseDeadlineMs: () => 500,
  });
  const result = await run();
  assert.equal(result.ready, false);
  assert.equal(result.state, "STALLED");
  assert.match(result.reason, /turn 1 of 2/);
});
