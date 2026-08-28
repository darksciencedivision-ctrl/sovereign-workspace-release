"use strict";
/**
 * W-40 (first half) — the application-control HTTP surface accepted any Host and any Origin.
 *
 * The server listens on loopback and authenticates with a bearer token, which is the control that
 * actually stops an unauthorised caller. Host and Origin checks defend a different thing:
 *
 *   * DNS REBINDING. A page on an attacker's domain whose DNS is re-pointed at 127.0.0.1 reaches
 *     this server with `Host: attacker.example`. The bearer requirement still stands, so this is
 *     not by itself an authentication bypass — but a server that answers to any Host is reachable
 *     from a browser context at all, and the token is the only thing left between the two.
 *   * A BROWSER ORIGIN. No legitimate client of this surface is a web page: the callers are the
 *     shell's own child processes holding a bearer from their launch environment. So an `Origin`
 *     header is positive evidence the request came from somewhere it should not have, and the
 *     right answer is to refuse rather than to evaluate it.
 *
 * NOT the token check, and not a replacement for it. This narrows WHO CAN REACH the surface; the
 * bearer still decides who is allowed to use it.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const { SovereignControlServer } = require("../control/sovereign-control-server");

async function serve() {
  const server = new SovereignControlServer({ handlers: { identity: async () => ({ ok: true }) } });
  const port = await server.start();
  return { server, port: port || server.port };
}

function request(port, { host, origin } = {}) {
  return new Promise((resolve) => {
    const headers = { "content-type": "application/json" };
    if (host !== undefined) headers.Host = host;
    if (origin !== undefined) headers.Origin = origin;
    const req = http.request(
      { host: "127.0.0.1", port, path: "/v1/tools/call", method: "POST", headers },
      (res) => {
        let body = "";
        res.on("data", (d) => { body += d; });
        res.on("end", () => resolve({ status: res.statusCode, body }));
      });
    req.on("error", () => resolve({ status: 0, body: "" }));
    req.end(JSON.stringify({ operation: "identity", arguments: {} }));
  });
}

test("W-40 NEGATIVE: a request carrying a browser Origin is REFUSED", async () => {
  const { server, port } = await serve();
  try {
    const res = await request(port, { origin: "https://evil.example" });
    assert.strictEqual(res.status, 403,
      "an Origin header is positive evidence of a browser context; no legitimate caller of this "
      + "surface is a web page");
  } finally { await server.stop(); }
});

test("W-40 NEGATIVE: a foreign Host header is REFUSED (the DNS-rebinding shape)", async () => {
  const { server, port } = await serve();
  try {
    const res = await request(port, { host: "attacker.example" });
    assert.strictEqual(res.status, 403,
      "a server that answers to any Host is reachable from a rebound browser context");
  } finally { await server.stop(); }
});

test("W-40 POSITIVE: an ordinary loopback request is unaffected", async () => {
  const { server, port } = await serve();
  try {
    for (const host of [`127.0.0.1:${port}`, `localhost:${port}`]) {
      const res = await request(port, { host });
      assert.notStrictEqual(res.status, 403, `${host} must remain a legitimate Host`);
    }
  } finally { await server.stop(); }
});
