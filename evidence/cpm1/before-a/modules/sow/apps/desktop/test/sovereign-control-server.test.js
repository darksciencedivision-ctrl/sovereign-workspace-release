"use strict";

const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

const { SovereignControlServer } = require("../control/sovereign-control-server");

async function call(port, token, operation, args = {}) {
  const response = await fetch(`http://127.0.0.1:${port}/v1/tools/call`, {
    method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ operation, arguments: args }),
  });
  return { status: response.status, body: await response.json() };
}

test("opaque node credentials bind tool calls to the issued identity", async () => {
  const seen = [];
  const server = new SovereignControlServer({ handlers: {
    echo: (identity, args) => { seen.push(identity); return { identity, args }; },
  } });
  await server.start();
  try {
    const token = server.issueCredential({ node_id: "cond-1", role: "conductor", project_id: "proj" });
    const identity = await call(server.port, token, "identity");
    assert.equal(identity.status, 200);
    assert.equal(identity.body.result.node_id, "cond-1");
    const result = await call(server.port, token, "echo", { provider: "grok_build" });
    assert.equal(result.body.result.identity.role, "conductor");
    assert.deepEqual(result.body.result.args, { provider: "grok_build" });
    assert.equal(server.connectionState("cond-1").state, "connected");
    assert.equal(seen.length, 1);
  } finally { await server.stop(); }
});

test("unknown or revoked node credentials fail closed", async () => {
  const server = new SovereignControlServer();
  await server.start();
  try {
    const unknown = await call(server.port, "invented", "identity");
    assert.equal(unknown.status, 401);
    const token = server.issueCredential({ node_id: "w-1", role: "worker", project_id: "proj" });
    server.revokeNode("w-1");
    const revoked = await call(server.port, token, "identity");
    assert.equal(revoked.status, 401);
  } finally { await server.stop(); }
});

// ---- U335 (unit 19.7): what the gateway may honestly say about a node's MCP session -------------

test("a node's connection state carries the AGE of its evidence and goes stale, not connected", async () => {
  let clock = 1_000_000;
  const server = new SovereignControlServer({
    handlers: { echo: () => ({ ok: true }) },
    staleAfterMs: 10_000, now: () => clock,
  });
  await server.start();
  try {
    // No credential at all: this node cannot call, and that is not the same as silence.
    assert.equal(server.connectionState("ghost").state, "disconnected");
    const token = server.issueCredential({ node_id: "w-1", role: "worker", project_id: "proj" });
    // A credential and NOTHING ever arriving on it: `configured`, never `connected`. This is the
    // audited case — a worker whose MCP subprocess never came up behind a live PTY.
    const configured = server.connectionState("w-1");
    assert.equal(configured.state, "configured");
    assert.equal(configured.fresh, false);
    assert.equal(configured.last_seen, null);

    await call(server.port, token, "echo");
    const fresh = server.connectionState("w-1");
    assert.equal(fresh.state, "connected");
    assert.equal(fresh.fresh, true);
    assert.equal(fresh.last_seen_age_ms, 0);
    assert.equal(fresh.stale_after_ms, 10_000);

    // Inside the window, silence is still explained by a call in flight.
    clock += 9_999;
    assert.equal(server.connectionState("w-1").state, "connected");
    // Past it, nothing explains the silence — and the honest word for that is UNVERIFIED. The
    // shipped code answered `connected` off this same timestamp forever.
    clock += 2;
    const stale = server.connectionState("w-1");
    assert.equal(stale.state, "stale");
    assert.equal(stale.fresh, false);
    assert.equal(stale.last_seen_age_ms, 10_001);
    assert.equal(stale.last_seen, fresh.last_seen, "the evidence itself is not rewritten by ageing");

    // THE EXIT PATH: a stale node is not pinned. One request of any kind clears it.
    await call(server.port, token, "echo");
    assert.equal(server.connectionState("w-1").state, "connected");
  } finally { await server.stop(); }
});

test("an unparseable last-seen stamp fails closed to stale rather than counting as fresh", async () => {
  const server = new SovereignControlServer({ now: () => 5_000_000 });
  server.issueCredential({ node_id: "w-2", role: "worker", project_id: "proj" });
  server._lastSeen.set("w-2", "not-a-timestamp");   // only reachable by corrupting it deliberately
  const state = server.connectionState("w-2");
  assert.equal(state.state, "stale");
  assert.equal(state.fresh, false);
  assert.equal(state.last_seen_age_ms, null);
});

test("a clock that moves backwards reports age 0, never a negative age or false staleness", async () => {
  let clock = 2_000_000;
  const server = new SovereignControlServer({ staleAfterMs: 1_000, now: () => clock });
  server.issueCredential({ node_id: "w-3", role: "worker", project_id: "proj" });
  server._lastSeen.set("w-3", new Date(clock).toISOString());
  clock -= 60_000;
  const state = server.connectionState("w-3");
  assert.equal(state.last_seen_age_ms, 0);
  assert.equal(state.state, "connected");
});

// ---- U334 (unit 19.7): stop() has an end ---------------------------------------------------------

// The two values PRODUCTION uses. `main.js` constructs the server with no `staleAfterMs` and calls
// `stop()` with no argument, so these constants ARE U334's bound and U335's window in the shipped
// shell — and every other test and every self-check leg injects its own, which is how the
// gate-validator's round-1 mutations of both defaults survived the entire suite (BLOCKING-2).
test("the shipped defaults are the ones the audit's fixes rest on, and they are graded", async () => {
  const server = new SovereignControlServer();
  assert.deepEqual(await server.stop(), {
    closed: true, was_listening: false, forced: false, timed_out: false,
    timeout_ms: null, waited_ms: 0,
  });
  server.issueCredential({ node_id: "w-default", role: "worker", project_id: "proj" });
  assert.equal(server.connectionState("w-default").stale_after_ms, 180000,
    "the staleness window must be the AppControlClient call ceiling (sovereign_tools.py:40)");
  await server.start();
  const outcome = await server.stop();
  assert.equal(outcome.timeout_ms, 5000, "the default stop budget is what the quit path actually waits");
});

test("a stop that times out still leaves no credential able to authenticate", async () => {
  const server = new SovereignControlServer();
  const port = await server.start();
  const raw = server._server;
  raw.closeAllConnections = () => {};
  const token = server.issueCredential({ node_id: "w-revoked", role: "worker", project_id: "proj" });
  // …and the node CALLS, so `_lastSeen` holds a stamp for it. Round 1 asserted revocation against a
  // name that was never a node; round 2 found the repair had only moved the hole — a node that had
  // never called leaves `_lastSeen` empty either way, so deleting `_lastSeen.clear()` still passed.
  // `connectionState` reads `_lastSeen` FIRST, so that deletion would report a revoked node as
  // `connected`. The node has to have spoken for this assertion to mean anything.
  await call(port, token, "identity");
  const socket = net.connect(port, "127.0.0.1");
  await new Promise((resolve, reject) => { socket.once("connect", resolve); socket.once("error", reject); });
  try {
    assert.equal(server.connectionState("w-revoked").state, "connected");
    const outcome = await server.stop({ timeoutMs: 300 });
    assert.equal(outcome.timed_out, true);
    assert.equal(server.identityFor(token), null, "the issued credential must be gone");
    assert.equal(server.connectionState("w-revoked").state, "disconnected");
  } finally {
    socket.destroy();
    await new Promise((resolve) => raw.close(resolve));
  }
});

test("a call arriving during shutdown is told it is a shutdown, not an auth failure", async () => {
  // Driven over a REAL socket, against the real HTTP server. The first version called `_handle`
  // directly and excused itself by calling this non-deterministic; the round-2 validator provoked
  // it on the first attempt. The population that reaches this branch is a request whose headers
  // were still arriving when `stop()` ran, which is exactly what this sets up.
  const server = new SovereignControlServer();
  const port = await server.start();
  const token = server.issueCredential({ node_id: "w-late", role: "worker", project_id: "proj" });
  const socket = net.connect(port, "127.0.0.1");
  await new Promise((resolve, reject) => { socket.once("connect", resolve); socket.once("error", reject); });
  const body = JSON.stringify({ operation: "identity", arguments: {} });
  let response = "";
  socket.on("data", (chunk) => { response += String(chunk); });
  // Headers, deliberately unterminated: the server has the connection but not yet a request.
  // W-40: the Host now carries the PORT, as every real client on a non-default port does. This
  // hand-rolled request omitted it and was refused 403 by the new Host check before it could reach
  // the shutdown path this test is about — the outer guard shadowing the inner one. Fixed at the
  // request, NOT by loosening the check: a portless Host is not a shape any real caller sends here.
  socket.write(`POST /v1/tools/call HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\n`
    + `Authorization: Bearer ${token}\r\nContent-Type: application/json\r\n`
    + `Content-Length: ${Buffer.byteLength(body)}\r\n`);
  const stopping = server.stop({ timeoutMs: 1500 });
  await new Promise((resolve) => setTimeout(resolve, 50));
  socket.write(`\r\n${body}`);          // …and now the request completes, mid-shutdown
  try {
    const deadline = Date.now() + 3000;
    while (!response.includes("\r\n\r\n") && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    assert.match(response, /^HTTP\/1\.1 503 /, `expected a 503, got: ${response.slice(0, 80)}`);
    assert.match(response, /shutting down/);
    assert.doesNotMatch(response, /authentication failed/,
      "a shutdown reported as an auth failure is the defect (MEDIUM-2)");
  } finally {
    socket.destroy();
    await stopping;
  }
});

test("a server started again after a stop reports its OWN next shutdown, not the last one", async () => {
  const server = new SovereignControlServer();
  await server.start();
  const first = await server.stop({ timeoutMs: 400 });
  const port = await server.start();
  assert.ok(port > 0);
  const second = await server.stop({ timeoutMs: 900 });
  assert.notEqual(second, first);
  assert.equal(second.timeout_ms, 900, "the memo must not survive a restart");
});

test("stop() closes gracefully and reports it, without destroying anything it did not have to", async () => {
  const server = new SovereignControlServer();
  await server.start();
  const outcome = await server.stop({ timeoutMs: 2000 });
  assert.equal(outcome.closed, true);
  assert.equal(outcome.forced, false);
  assert.equal(outcome.timed_out, false);
  assert.equal(outcome.was_listening, true);
  // Idempotent: the quit path calls this twice (teardown starts it, completeNormalQuit awaits it).
  assert.deepEqual(await server.stop(), outcome);
});

test("an open connection is destroyed inside the budget instead of holding the quit path open", async () => {
  const server = new SovereignControlServer();
  const port = await server.start();
  const socket = net.connect(port, "127.0.0.1");
  await new Promise((resolve, reject) => { socket.once("connect", resolve); socket.once("error", reject); });
  try {
    const started = Date.now();
    // The shipped code awaited `server.close()` with this socket open: it would never have resolved.
    const outcome = await server.stop({ timeoutMs: 600 });
    const waited = Date.now() - started;
    assert.equal(outcome.closed, true);
    assert.equal(outcome.forced, true, "the halfway destroy is what let close() finish");
    assert.equal(outcome.timed_out, false);
    assert.ok(waited < 3000, `stop() must finish inside its budget, waited ${waited} ms`);
  } finally { socket.destroy(); }
});

test("a socket that survives the destroy still ends the wait, reported as the timeout it was", async () => {
  const server = new SovereignControlServer();
  const port = await server.start();
  const raw = server._server;                     // captured before stop() releases it
  raw.closeAllConnections = () => {};             // the one thing that cannot be provoked for real:
                                                  // a connection that outlives the forced destroy
  const socket = net.connect(port, "127.0.0.1");
  await new Promise((resolve, reject) => { socket.once("connect", resolve); socket.once("error", reject); });
  try {
    const outcome = await server.stop({ timeoutMs: 300 });
    assert.equal(outcome.timed_out, true);
    assert.equal(outcome.closed, false, "a socket that outlived the budget is not reported as closed");
    assert.equal(outcome.forced, true);
    // …and every credential is gone regardless, so nothing can authenticate against the survivor.
    assert.equal(server.connectionState("anyone").state, "disconnected");
    assert.equal(server.port, null);
  } finally {
    socket.destroy();
    await new Promise((resolve) => raw.close(resolve));
  }
});

test("live shell wiring allows slow provider MCP startup and preserves lifecycle/timing bindings", () => {
  const main = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");
  assert.match(main, /async function waitForNodeMcp\(nodeId, timeoutMs = 120000\)/);
  const endedStart = main.indexOf("function markWorkerPaneChromeEnded");
  const endedEnd = main.indexOf("async function spawnFromSelection", endedStart);
  assert.match(main.slice(endedStart, endedEnd), /pushConductor\(\)/);
  const conductorStateStart = main.indexOf("function conductorState");
  const conductorStateEnd = main.indexOf("function createConductorPane", conductorStateStart);
  const conductorState = main.slice(conductorStateStart, conductorStateEnd);
  assert.match(conductorState, /conductorLaunch\.operationalState === "READY"/);
  assert.match(conductorState, /nodeState: operationalNodeState/);
  // U371 (closed in unit 19.4): the measured 500 ms default is still main.js's, but it is now
  // PARSED rather than coerced — `Number(env || 500)` answered NaN for a malformed override, and
  // `setTimeout(NaN)` is 0 ms, which does not shorten U364's echo-settle wait but DELETES it.
  assert.match(main, /intervalMs\("SOVEREIGN_PROVIDER_PASTE_SETTLE_MS", 500\)/);
  assert.match(main, /intervalMs\("SOVEREIGN_CODEX_SUBMIT_CONFIRM_MS", 200\)/);
  assert.doesNotMatch(main, /Number\(process\.env\.SOVEREIGN_\w+_MS \|\|/,
    "a millisecond interval from the environment must be parsed, not coerced (U371)");
  // The live-measured paste/submit timing moved into `control/pane-writer.js` with the U328 modal
  // gate (unit 19.3), where it is driven by real tests instead of matched as a string. main.js still
  // owns the two measured constants and hands both to the writer; the writer still awaits both and
  // still keeps the second Enter provider-specific, so Gemini/Grok get exactly one submission.
  const writeStart = main.indexOf("const paneWriter = createPaneWriter({");
  const writeEnd = main.indexOf("function paneWriteRefusalFor", writeStart);
  assert.ok(writeStart > 0 && writeEnd > writeStart, "main.js must build the gated pane writer");
  assert.match(main.slice(writeStart, writeEnd), /pasteSettleMs: \(\) => PROVIDER_PASTE_SETTLE_MS/);
  assert.match(main.slice(writeStart, writeEnd), /submitConfirmMs: \(\) => CODEX_SUBMIT_CONFIRM_MS/);
  const writer = fs.readFileSync(path.resolve(__dirname, "..", "control", "pane-writer.js"), "utf8");
  assert.match(writer, /await io\.sleep\(io\.pasteSettleMs\(\)\)/);
  // 19.6 ([[U393]] MINOR-1): the second Enter is still provider-specific and Gemini/Grok still get
  // exactly one submission — what changed is that WHICH providers need it is read from the declared
  // traits instead of compared inline. The behaviour itself is asserted by driving the writer in
  // `pane-writer.test.js` ("the codex second Enter is gated too", and the one-Enter control for an
  // undeclared provider); this line only pins that main.js's writer has not gone back to a name.
  assert.match(writer, /traitsFor\(io\.providerFor\(paneId\)\)\.submit_confirm_enter/);
  assert.doesNotMatch(writer, /io\.providerFor\(paneId\) === "/,
    "provider behaviour in the write path is declared in provider-traits.js, not compared here");
  assert.match(writer, /await io\.sleep\(io\.submitConfirmMs\(\)\)/);
  const quitStart = main.indexOf("async function completeNormalQuit");
  assert.ok(quitStart > 0);
  const quitBody = main.slice(quitStart, main.indexOf("app.whenReady", quitStart));
  assert.match(quitBody, /await manager\.shutdown\(15000\)/);
  assert.match(quitBody, /await waitForSessionReleases\(15000\)/);
  assert.match(quitBody, /workerLauncher\(\)\.heldSessions\(\)/);
  assert.match(quitBody, /conductorLaunch\.leaseId/);
  assert.match(main, /trackSessionRelease\(onConductorSessionEnded\(event\), "conductor"\)/);
  assert.match(main, /trackSessionRelease\(workerLauncher\(\)\.onWorkerSessionEnded\(event\), "worker"\)/);
  assert.match(main, /app\.on\("before-quit", \(event\) => \{/);
  assert.match(main, /event\.preventDefault\(\)/);
});
