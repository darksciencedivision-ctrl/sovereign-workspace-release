"use strict";
/**
 * G26 evidence driver — a DEV/EVIDENCE loopback bridge, extracted from main.js so it is testable
 * without the Electron main process (F-128, remediation/p1).
 *
 * It drives the SAME governed delivery path the renderer uses (handleOperatorText), plus explicit
 * conductor launch/interrupt and a read-only /state, so a headless capture can exercise the real
 * path end to end. That makes it useful for evidence — and dangerous if exposed: the reported
 * defect (F-128) was that it shipped ON in the product launch env with NO authentication, so any
 * web page could POST /send into the agentic conductor as the operator, and a DNS-rebinding page
 * could read /state.
 *
 * This module is a DEV seam, never a product surface. Two things close F-128:
 *   1. shell/modules/sow.json no longer sets SOW_OPERATOR_TEXT_DRIVER_PORT, so the driver never
 *      starts under the Workspace.
 *   2. Even when a developer sets the port, the driver FAILS CLOSED without a per-launch bearer
 *      token, refuses Origin-bearing (browser) and non-loopback-Host requests, requires
 *      application/json, caps the request body, and survives a bind conflict instead of crashing
 *      the shell. The reachability + bearer pattern mirrors SovereignControlServer.
 *
 * The token travels through the launch environment the harness controls; its name carries TOKEN,
 * so the existing credential-scrub machinery keeps it out of provider child environments.
 */
const http = require("http");
const crypto = require("node:crypto");

const MAX_BODY = 64 * 1024;
const MIN_TOKEN_CHARS = 16;

function bearerToken(req) {
  const m = /^Bearer\s+(\S+)$/i.exec(String(req.headers.authorization || ""));
  return m ? m[1] : null;
}

// Constant-time compare; unequal lengths are a mismatch and never reach timingSafeEqual (which
// throws on a length difference).
function tokenMatches(got, token) {
  if (typeof got !== "string" || !token) return false;
  const a = Buffer.from(got, "utf8");
  const b = Buffer.from(token, "utf8");
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

/**
 * The request handler, with the effectful operations injected as `handlers` so the module can be
 * driven in a test without Electron. `token` gates every request; `port` scopes the Host allowlist
 * to the loopback forms this server actually binds.
 *
 * `handlers` supplies async functions: `send(payload)`, `launchConductor()`, `interrupt()`,
 * `state()`.
 */
function createOperatorTextHandler({ port, token, handlers, log = () => {} }) {
  const allowedHosts = new Set([`127.0.0.1:${port}`, `localhost:${port}`]);
  const json = (res, status, obj) => {
    const body = Buffer.from(JSON.stringify(obj), "utf8");
    res.writeHead(status, {
      "content-type": "application/json",
      "content-length": body.length,
      "cache-control": "no-store",
    });
    res.end(body);
  };
  return (req, res) => {
    // Reachability first (mirrors SovereignControlServer). No legitimate caller here is a web page,
    // so an Origin header is positive evidence of a browser context; and only the loopback Host
    // forms this server binds are answered. Together these close the cross-site POST into the
    // conductor and the DNS-rebinding read of /state, before the bearer check even runs.
    if (req.headers.origin !== undefined) {
      json(res, 403, { error: "origin-bearing requests are refused (no browser client)" });
      return;
    }
    if (!allowedHosts.has(String(req.headers.host || ""))) {
      json(res, 403, { error: "unexpected Host header" });
      return;
    }
    if (!tokenMatches(bearerToken(req), token)) {
      json(res, 401, { error: "operator text driver authentication failed" });
      return;
    }
    // A cross-site "simple request" is text/plain; requiring application/json means such a request
    // (which needs no CORS preflight) cannot reach the delivery path even if the two checks above
    // were somehow satisfied.
    if (req.method === "POST") {
      const ct = String(req.headers["content-type"] || "").split(";")[0].trim().toLowerCase();
      if (ct !== "application/json") {
        json(res, 415, { error: "content-type must be application/json" });
        return;
      }
    }
    let body = "";
    let tooLarge = false;
    req.on("data", (c) => {
      if (tooLarge) return;
      body += c;
      if (Buffer.byteLength(body, "utf8") > MAX_BODY) {
        tooLarge = true;
        json(res, 413, { error: "request body too large" });
        req.destroy();
      }
    });
    req.on("error", () => { try { req.destroy(); } catch (_e) { /* already gone */ } });
    req.on("end", async () => {
      if (tooLarge) return;
      let payload = {};
      try { payload = body ? JSON.parse(body) : {}; } catch (_e) { /* {} */ }
      try {
        if (req.method === "POST" && req.url === "/send") {
          json(res, 200, await handlers.send(payload));
        } else if (req.method === "POST" && req.url === "/launch-conductor") {
          json(res, 200, await handlers.launchConductor());
        } else if (req.method === "POST" && req.url === "/interrupt") {
          json(res, 200, await handlers.interrupt());
        } else if (req.method === "GET" && req.url === "/state") {
          json(res, 200, await handlers.state());
        } else {
          json(res, 404, { error: "not found" });
        }
      } catch (e) {
        json(res, 400, { error: (e && e.message) || String(e) });
      }
    });
  };
}

/**
 * Start the driver from the environment, or return null when it must not run. Fail closed: off
 * unless a port is set, and refused (with a logged reason) unless a token of at least
 * MIN_TOKEN_CHARS is also set — an enabled driver with no token is exactly the unauthenticated
 * surface F-128 reported. Returns the http.Server (for the caller/tests to close), or null.
 */
function startOperatorTextDriver({ env = process.env, handlers, log = () => {} }) {
  const port = parseInt(env.SOW_OPERATOR_TEXT_DRIVER_PORT || "", 10);
  if (!port) return null;
  const token = String(env.SOW_OPERATOR_TEXT_DRIVER_TOKEN || "");
  if (token.length < MIN_TOKEN_CHARS) {
    log("G26 driver NOT started: SOW_OPERATOR_TEXT_DRIVER_PORT is set but "
      + "SOW_OPERATOR_TEXT_DRIVER_TOKEN is missing or shorter than "
      + `${MIN_TOKEN_CHARS} chars — a dev/evidence seam must never run unauthenticated (F-128).`);
    return null;
  }
  const server = http.createServer(createOperatorTextHandler({ port, token, handlers, log }));
  // A bind conflict (port already in use) previously reached process.on("uncaughtException") and
  // exited the whole shell with code 1 (F-128 secondary a). Handle it here: log and continue.
  server.on("error", (e) => {
    log(`G26 driver server error (not fatal): ${(e && e.message) || String(e)}`);
  });
  server.listen(port, "127.0.0.1",
    () => log(`G26 driver listening on 127.0.0.1:${port} (token-gated)`));
  return server;
}

module.exports = { createOperatorTextHandler, startOperatorTextDriver, MAX_BODY, MIN_TOKEN_CHARS };
