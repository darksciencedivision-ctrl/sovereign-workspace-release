"use strict";
/**
 * F-128 (remediation/p1) — the G26 operator text driver must not be an unauthenticated bridge into
 * the agentic conductor. These tests drive the extracted handler over a real loopback socket and
 * assert every reachability/auth gate, plus the fail-closed startup rules and the bind-conflict
 * crash fix.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const {
  createOperatorTextHandler,
  startOperatorTextDriver,
  MAX_BODY,
} = require("../control/operator-text-driver");

const TOKEN = "0123456789abcdef-token";

// A handler-backed server on an ephemeral port. The handler is built with the SAME port the socket
// ends up bound to, so its Host allowlist matches the default Host node sends.
function serve(handlers) {
  return new Promise((resolve) => {
    const server = http.createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.on("request", createOperatorTextHandler({ port, token: TOKEN, handlers }));
      resolve({ server, port });
    });
  });
}

function request(port, { method = "GET", url = "/state", headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: "127.0.0.1", port, path: url, method, headers }, (res) => {
      let data = "";
      res.on("data", (d) => { data += d; });
      res.on("end", () => resolve({ status: res.statusCode, body: data }));
    });
    req.on("error", reject);
    if (body !== undefined) req.write(body);
    req.end();
  });
}

function noopHandlers() {
  return {
    send: async (p) => ({ ok: true, echoed: p }),
    launchConductor: async () => ({ launched: true }),
    interrupt: async () => ({ interrupted: true }),
    state: async () => ({ launchState: "idle" }),
  };
}

const authJson = { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" };

test("a request with no token is refused", async () => {
  const { server, port } = await serve(noopHandlers());
  try {
    const r = await request(port, { method: "POST", url: "/send",
      headers: { "content-type": "application/json" }, body: JSON.stringify({ text: "hi" }) });
    assert.strictEqual(r.status, 401);
  } finally { server.close(); }
});

test("a request with the wrong token is refused", async () => {
  const { server, port } = await serve(noopHandlers());
  try {
    const r = await request(port, { method: "POST", url: "/send",
      headers: { authorization: "Bearer wrong-token-value-here", "content-type": "application/json" },
      body: JSON.stringify({ text: "hi" }) });
    assert.strictEqual(r.status, 401);
  } finally { server.close(); }
});

test("an Origin-bearing request is refused before auth (browser client)", async () => {
  const { server, port } = await serve(noopHandlers());
  try {
    const r = await request(port, { method: "POST", url: "/send",
      headers: { ...authJson, origin: "https://evil.example" },
      body: JSON.stringify({ text: "hi" }) });
    assert.strictEqual(r.status, 403);
  } finally { server.close(); }
});

test("a foreign Host header is refused (DNS-rebinding read of /state)", async () => {
  const { server, port } = await serve(noopHandlers());
  try {
    const r = await request(port, { url: "/state",
      headers: { authorization: `Bearer ${TOKEN}`, host: "attacker.example" } });
    assert.strictEqual(r.status, 403);
  } finally { server.close(); }
});

test("a text/plain POST is refused (no CORS-simple bypass)", async () => {
  let delivered = false;
  const h = noopHandlers();
  h.send = async () => { delivered = true; return { ok: true }; };
  const { server, port } = await serve(h);
  try {
    const r = await request(port, { method: "POST", url: "/send",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "text/plain" },
      body: JSON.stringify({ text: "hi" }) });
    assert.strictEqual(r.status, 415);
    assert.strictEqual(delivered, false, "text/plain must never reach the delivery path");
  } finally { server.close(); }
});

test("a valid, authenticated POST /send reaches the delivery path", async () => {
  let seen = null;
  const h = noopHandlers();
  h.send = async (p) => { seen = p; return { ok: true }; };
  const { server, port } = await serve(h);
  try {
    const r = await request(port, { method: "POST", url: "/send", headers: authJson,
      body: JSON.stringify({ text: "hello conductor" }) });
    assert.strictEqual(r.status, 200);
    assert.deepStrictEqual(seen, { text: "hello conductor" });
  } finally { server.close(); }
});

test("an over-cap body is refused", async () => {
  const { server, port } = await serve(noopHandlers());
  try {
    const big = "x".repeat(MAX_BODY + 1024);
    const r = await request(port, { method: "POST", url: "/send", headers: authJson,
      body: JSON.stringify({ text: big }) });
    assert.strictEqual(r.status, 413);
  } finally { server.close(); }
});

test("startOperatorTextDriver is OFF when no port is set", () => {
  const server = startOperatorTextDriver({ env: {}, handlers: noopHandlers() });
  assert.strictEqual(server, null);
});

test("startOperatorTextDriver fails closed when a port is set but no token", () => {
  const logs = [];
  const server = startOperatorTextDriver({
    env: { SOW_OPERATOR_TEXT_DRIVER_PORT: "17890" },
    handlers: noopHandlers(),
    log: (m) => logs.push(m),
  });
  assert.strictEqual(server, null);
  assert.ok(logs.some((m) => /unauthenticated|token/i.test(m)), "must log the refusal reason");
});

test("a bind conflict is handled, not fatal (no uncaughtException)", async () => {
  // Occupy a port, then start the driver on the same port with a valid token; its server 'error'
  // handler must log and not throw. Previously this reached process.on('uncaughtException') and
  // exited the shell (F-128 secondary a).
  const blocker = http.createServer();
  await new Promise((r) => blocker.listen(0, "127.0.0.1", r));
  const port = blocker.address().port;
  const logs = [];
  let server = null;
  try {
    assert.doesNotThrow(() => {
      server = startOperatorTextDriver({
        env: { SOW_OPERATOR_TEXT_DRIVER_PORT: String(port),
          SOW_OPERATOR_TEXT_DRIVER_TOKEN: TOKEN },
        handlers: noopHandlers(),
        log: (m) => logs.push(m),
      });
    });
    // Give the async 'error' event a tick to fire.
    await new Promise((r) => setTimeout(r, 50));
    assert.ok(logs.some((m) => /server error/i.test(m)), "the bind conflict must be logged");
  } finally {
    if (server) server.close();
    blocker.close();
  }
});
