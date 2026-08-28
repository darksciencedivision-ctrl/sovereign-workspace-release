"use strict";

const crypto = require("node:crypto");
const http = require("node:http");

const MAX_BODY = 1024 * 1024;

/**
 * U335 (unit 19.7) — how long a node's SILENCE may stand as evidence that its Sovereign MCP session
 * is alive. `_lastSeen` is stamped when a request ARRIVES (`_handle`), so a node blocked inside its
 * longest possible single call is still fresh: `mcp_server/sovereign_tools.py`'s AppControlClient
 * gives every call a 180 s ceiling (`sovereign_tools.py:40`, never overridden at its one
 * construction site), and a call that outlives it fails on the node's side. Past that ceiling, no
 * in-flight request can explain the silence — but silence is not proof of death, which is exactly
 * why the state past this window is `stale` and not `disconnected`. `stale` means UNVERIFIED, it
 * clears on the next request of any kind, and nothing in this file decides what a caller does
 * about it.
 *
 * WHAT THIS DOES NOT OBSERVE, named precisely because the first version of this comment called the
 * gap "silence" and left a reader to infer the rest (gate-validator round 1, MAJOR-3): `_lastSeen`
 * sees only the calls a node makes THROUGH THIS GATEWAY. In `mcp_server/sovereign_tools.py` that is
 * every tool with a shell-side effect — `get_worker_status`, `assign_task`, `send_message`,
 * `publish_progress`, `publish_candidate`, `open_debate`, `post_debate_turn`, `spawn_worker`,
 * `stop_worker`, `list_models` — and NOT the store-only ones, which include WRITES and not only
 * reads (round-2 validator, MINOR-1, which also corrected the line numbers below):
 * `read_messages` (:153), `abort_debate` (:202), `close_debate` (:208), `publish_synthesis` (:263)
 * and the artifact publish/read never reach here. A worker spending four minutes reading its
 * messages, or one that has just published a synthesis, is therefore working and `stale`. So
 * there are THREE sources of legitimate silence, not two: a call in flight (bounded by the 180 s
 * ceiling), a model thinking, and a node doing store-only MCP work. The last one is why the state
 * is UNVERIFIED and why every caller's refusal on it has to be retryable and provokable — it is
 * not evidence of a dead node, and this file does not claim it is.
 */
const DEFAULT_STALE_AFTER_MS = 180000;

/** The states that mean *this node HAS had a working Sovereign MCP session* — as opposed to
 *  `configured` (a credential was issued and nothing ever arrived) or `disconnected` (no credential).
 *
 *  It exists because the two questions are different and 19.7's first draft answered both with
 *  `state === "connected"`. "Has this node ever reached us?" governs whether it is worth PROVOKING
 *  (readiness types a challenge; its answer is itself a gateway call). "Has it reached us recently?"
 *  governs whether work may be handed over unverified. Collapsing them meant a healthy idle worker
 *  could be moved to STALLED by a readiness run that never typed anything — the U329 defect class,
 *  re-created inside the unit written to avoid it (gate-validator round 1, BLOCKING-1). */
const SESSION_ESTABLISHED_STATES = Object.freeze(["connected", "stale"]);

/** @param {{state?: string}|null} mcp a `connectionState()` record. */
const sessionEstablished = (mcp) =>
  Boolean(mcp && SESSION_ESTABLISHED_STATES.includes(mcp.state));

/**
 * U334 (unit 19.7) — the ceiling on `stop()`. `http.Server.close()` does not resolve while any
 * connection is open, and an MCP client holding a request open could therefore leave Electron
 * awaiting this forever after `event.preventDefault()`. Halfway through the budget the remaining
 * connections are destroyed; at the end, `stop()` resolves REGARDLESS and says what happened.
 *
 * WHY TWO STAGES rather than one destroy: `close()` first stops accepting and lets a request that is
 * already mid-flight finish, which is the graceful outcome and the common one (a node's tool call
 * completes and its keep-alive socket goes idle). Destroying immediately would abort a call the node
 * is waiting on. Destroying NEVER is what shipped, and that is the defect: a keep-alive socket alone
 * is enough to hold `close()` open indefinitely, so the graceful path has to have an end.
 */
const DEFAULT_STOP_TIMEOUT_MS = 5000;

function json(res, status, payload) {
  const body = Buffer.from(JSON.stringify(payload), "utf8");
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": body.length,
    "Cache-Control": "no-store" });
  res.end(body);
}

function bearer(req) {
  const value = String(req.headers.authorization || "");
  const match = /^Bearer\s+([^\s]+)$/i.exec(value);
  return match ? match[1] : null;
}

class SovereignControlServer {
  constructor({ handlers = {}, log = () => {}, onOperation = () => {},
    staleAfterMs = DEFAULT_STALE_AFTER_MS, now = () => Date.now() } = {}) {
    this._handlers = handlers;
    this._log = log;
    this._credentials = new Map();
    this._lastSeen = new Map();
    this._operations = new Map();
    this._onOperation = onOperation;
    this._server = null;
    this._stopping = null;
    this._staleAfterMs = Number.isFinite(staleAfterMs) && staleAfterMs > 0
      ? staleAfterMs : DEFAULT_STALE_AFTER_MS;
    this._now = now;
    this.port = null;
    // Empty until `start()` binds: an unstarted server answers to no Host at all, which is the
    // fail-closed direction.
    this._allowedHosts = new Set();
  }

  issueCredential(identity) {
    if (!identity || !identity.node_id || !identity.role || !identity.project_id) {
      throw new Error("node control identity is incomplete");
    }
    const token = crypto.randomBytes(32).toString("base64url");
    this._credentials.set(token, Object.freeze({ ...identity }));
    return token;
  }

  revokeCredential(token) {
    if (!token) return;
    const identity = this._credentials.get(token);
    this._credentials.delete(token);
    if (identity) this._lastSeen.delete(identity.node_id);
  }

  revokeNode(nodeId) {
    for (const [token, identity] of this._credentials) {
      if (identity.node_id === nodeId) this._credentials.delete(token);
    }
    this._lastSeen.delete(nodeId);
  }

  identityFor(token) { return this._credentials.get(token) || null; }

  hasNode(nodeId) {
    return [...this._credentials.values()].some((identity) => identity.node_id === nodeId);
  }

  /**
   * U335: what this server can HONESTLY say about a node's MCP session, with the age of the evidence
   * attached. It used to answer `connected` from any `_lastSeen` at all, so a worker whose Python MCP
   * subprocess had died behind a still-running PTY reported connected forever off a timestamp minutes
   * old, and the conductor could assign work to a node unable to make a single tool call.
   *
   * Four states, and the difference between the last two is the whole point: `disconnected` (no
   * credential — this node cannot call at all), `configured` (a credential was issued and NOTHING has
   * ever arrived on it), `connected` (a request arrived within the staleness window), `stale` (one
   * arrived, but longer ago than silence can account for). `stale` is "I cannot verify", never "it is
   * dead" — it clears the moment any request arrives, so nothing here can pin a healthy node.
   * An unparseable timestamp fails CLOSED to `stale` rather than being counted as fresh.
   */
  connectionState(nodeId) {
    const lastSeen = this._lastSeen.get(nodeId) || null;
    const configured = this.hasNode(nodeId);
    if (!lastSeen) {
      return { state: configured ? "configured" : "disconnected", last_seen: null,
        last_seen_age_ms: null, fresh: false, stale_after_ms: this._staleAfterMs };
    }
    const at = Date.parse(lastSeen);
    // A clock that has moved backwards yields a negative age; report 0 rather than a negative number,
    // and never let it read as "older than the window" or as fresher than the evidence is.
    const age = Number.isFinite(at) ? Math.max(0, this._now() - at) : null;
    const fresh = age !== null && age <= this._staleAfterMs;
    return { state: fresh ? "connected" : "stale", last_seen: lastSeen, last_seen_age_ms: age,
      fresh, stale_after_ms: this._staleAfterMs };
  }

  operationState(nodeId) {
    const events = this._operations.get(nodeId) || [];
    return { count: events.length, last: events.length ? { ...events[events.length - 1] } : null,
      events: events.map((event) => ({ ...event })) };
  }

  operationCount(nodeId, operation) {
    return (this._operations.get(nodeId) || []).filter((event) => event.operation === operation && event.ok).length;
  }

  _recordOperation(identity, operation, arguments_, ok, error = null) {
    const event = { operation, arguments: arguments_ || {}, ok, error,
      at: new Date().toISOString() };
    const events = this._operations.get(identity.node_id) || [];
    events.push(event);
    if (events.length > 200) events.splice(0, events.length - 200);
    this._operations.set(identity.node_id, events);
    try { this._onOperation(identity, event); } catch { /* observability cannot break a tool call */ }
  }

  childEnv(identity, base = {}) {
    const token = this.issueCredential(identity);
    return { env: { ...base, SOVEREIGN_CONTROL_PORT: String(this.port || ""),
      SOVEREIGN_CONTROL_TOKEN: token,
      SOVEREIGN_STORE_ROOT: identity.store_root || ".sovereign_store" }, token };
  }

  async start() {
    if (this._server) return this.port;
    // A server that was stopped and is started again is not still stopping: the memoised outcome
    // below belongs to the socket that is gone, and leaving it in place would make the NEXT stop()
    // return the previous run's verdict.
    this._stopping = null;
    this._server = http.createServer((req, res) => this._handle(req, res));
    await new Promise((resolve, reject) => {
      const onError = (e) => { this._server.off("listening", onListen); reject(e); };
      const onListen = () => { this._server.off("error", onError); resolve(); };
      this._server.once("error", onError);
      this._server.once("listening", onListen);
      this._server.listen(0, "127.0.0.1");
    });
    this.port = this._server.address().port;
    // W-40: the Host values this server will answer to, pinned at BIND time and never cleared, so
    // the check survives `stop()` zeroing `this.port`. Only the forms actually bound: it listens on
    // 127.0.0.1 alone, so `[::1]` is not among them — accepting an address this process never bound
    // would be broadening past loopback to look thorough.
    this._allowedHosts = new Set([`127.0.0.1:${this.port}`, `localhost:${this.port}`]);
    return this.port;
  }

  /**
   * U334: shut the gateway down inside a stated budget, and REPORT what that took.
   *
   * What it used to be: `await new Promise((resolve) => server.close(() => resolve()))` — no
   * timeout, no connection teardown. `close()` resolves only once every socket is gone, and an MCP
   * client with an open keep-alive connection (which every attached node has) never has to close
   * one. This was an unbounded await on the quit path, reached AFTER `event.preventDefault()` had
   * taken responsibility for exiting: a node that never let go left Electron alive with no window
   * and no further quit event to arrive.
   *
   * NOT "the single" one, which is what this comment claimed until the round-2 gate-validator
   * checked it (MAJOR-1). `apps/desktop/voice/turn-authority.js:687` is the same shape — a
   * `net.Server`, `await new Promise((resolve) => server.close(resolve))`, no budget, no connection
   * teardown — and it is awaited one step EARLIER on the same path (`main.js` `completeNormalQuit`
   * and `teardownSelfCheck`). Phase 19.9 bounded that server too ([[U435]]).
   *
   * It never REJECTS and never throws, because both call sites are teardown paths where a thrown
   * shutdown error is worse than a reported one. The outcome — `{closed, forced, timed_out}` — is
   * what a caller (and the receipt) reads; `closed: false` says the socket outlived the budget and
   * is the honest answer. It is never rendered as success BY THIS METHOD OR BY THE TEARDOWN LOG
   * LINE. Phase 19.9 also includes this outcome in `main.js`'s completion verdict, so a gateway
   * that outlives the budget makes normal quit exit nonzero ([[U432]]).
   *
   * Idempotent by memo: `teardown()` starts it and `completeNormalQuit()` awaits the SAME promise,
   * so quitting cannot start two shutdowns or wait two budgets.
   */
  async stop({ timeoutMs = DEFAULT_STOP_TIMEOUT_MS } = {}) {
    if (this._stopping) return this._stopping;
    const server = this._server;
    // Credentials and per-node state go FIRST and unconditionally: from this moment no new tool call
    // is authenticated, whatever the socket does. A stop that times out has still revoked everything.
    this._server = null;
    this.port = null;
    this._credentials.clear();
    this._lastSeen.clear();
    this._operations.clear();
    if (!server) {
      return {
        closed: true, was_listening: false, forced: false, timed_out: false,
        timeout_ms: null, waited_ms: 0,
      };
    }
    const budget = Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : DEFAULT_STOP_TIMEOUT_MS;
    const startedAt = this._now();
    this._stopping = new Promise((resolve) => {
      let settled = false;
      let forced = false;
      const finish = (outcome) => {
        if (settled) return;
        settled = true;
        clearTimeout(forceAt);
        clearTimeout(giveUpAt);
        this._log(`control: gateway stop ${outcome.closed ? "closed" : "TIMED OUT"}`
          + `${outcome.forced ? " after destroying open connections" : ""} `
          + `in ${outcome.waited_ms} ms (budget ${budget} ms)`);
        resolve(outcome);
      };
      const waited = () => Math.max(0, this._now() - startedAt);
      // Halfway: the graceful close has had its chance; anything still holding a socket is destroyed.
      const forceAt = setTimeout(() => {
        forced = true;
        try {
          if (typeof server.closeAllConnections === "function") server.closeAllConnections();
        } catch { /* a shutdown path may not fail on its own cleanup */ }
      }, Math.max(1, Math.floor(budget / 2)));
      // The end of the budget: resolve REGARDLESS. A late `close` callback finds `settled` true.
      const giveUpAt = setTimeout(() => finish({
        closed: false, was_listening: true, forced, timed_out: true,
        timeout_ms: budget, waited_ms: waited(),
      }), budget);
      server.close(() => finish({
        closed: true, was_listening: true, forced, timed_out: false,
        timeout_ms: budget, waited_ms: waited(),
      }));
    });
    return this._stopping;
  }

  async _handle(req, res) {
    if (req.method !== "POST" || req.url !== "/v1/tools/call") {
      json(res, 404, { ok: false, error: "not found" });
      return;
    }
    // W-40: who can REACH this surface, decided before who may use it. The bearer check below is
    // still the authority; these two narrow the set of contexts that get to present a bearer at all.
    //
    // Origin: no legitimate caller here is a web page — the callers are the shell's own child
    // processes holding a bearer from their launch environment. An `Origin` header is therefore
    // positive evidence the request came from a browser context, and the answer is to refuse rather
    // than to evaluate it against a list.
    //
    // Host: a server that answers to any Host is reachable from a page whose domain has been
    // re-pointed at 127.0.0.1. The bearer requirement still stands in that scenario, which is why
    // this is hardening and not a bypass being closed — but it removes the reachability the token
    // would otherwise be the only thing standing behind.
    if (req.headers.origin !== undefined) {
      json(res, 403, { ok: false, error: "origin-bearing requests are refused (no browser client)" });
      return;
    }
    // Only the loopback forms this server GENUINELY binds, with the port it is actually on. It
    // listens on `127.0.0.1` alone (see `start()`), so `[::1]` is deliberately NOT accepted: no
    // request can legitimately arrive claiming an address this process never bound, and accepting
    // one would be broadening past actual loopback to look thorough. `localhost` is accepted because
    // that is what an IPv4 client resolves to here.
    //
    // The port is matched too. It costs nothing and it means a Host naming a DIFFERENT service on
    // this machine is refused rather than quietly answered.
    // Read from `_allowedHosts`, pinned at bind time, NOT from `this.port` — `stop()` sets
    // `this.port = null` while in-flight requests are still being answered, so checking against it
    // refused every shutdown-window call with 403 and hid the 503 the shutdown path exists to send.
    // That was this unit's own defect and an existing test caught it: a reachability check must not
    // depend on state that teardown clears.
    if (!this._allowedHosts.has(String(req.headers.host || ""))) {
      json(res, 403, { ok: false, error: "unexpected Host header" });
      return;
    }
    // A call that arrives while the shell is quitting is not an authentication problem, and telling
    // a node it is one is this unit's own failure mode (gate-validator round 1, MEDIUM-2): `stop()`
    // clears every credential at kill-request time, so a node's perfectly valid token would
    // otherwise answer 401.
    //
    // HOW WIDE THAT WINDOW IS. Not the "up to 30 s" this comment first claimed, and not the
    // "milliseconds" that replaced it — one unsupported number followed by another (spec-auditor,
    // MEDIUM-2). What is MEASURED, on this host, Node 20: the round-2 validator drove a socket
    // that had already completed a request and `close()` dropped it immediately; leg A of
    // `docs/evidence/receipts/PHASE19_7_RUNTIME_HONESTY_SELFCHECK_19.7-round2-repairs_20260814T005949Z.json`
    // drove a socket that had never sent one and it survived until the halfway destroy
    // (`forced: true, waited_ms: 411` of an 800 ms budget — the receipt is NAMED because there are
    // SIX of them and their numbers differ: 415 ms at the round-3 tree, 402 ms at the tree this
    // comment ships in, 404 ms in a validator's own run. An unattributed measurement in this file
    // is the defect this file is about — and "five" was itself already wrong when it was written,
    // which is why the count is now stated against a list rather than remembered).
    // Both are real, they are
    // different populations, and the honest bound on this branch is therefore the destroy at
    // `budget/2` — 2.5 s by default — not either adjective. The refusal itself is unchanged;
    // nothing is served either way, only what it SAYS about itself.
    if (this._stopping) {
      json(res, 503, { ok: false, error: "the Sovereign application gateway is shutting down" });
      return;
    }
    const identity = this.identityFor(bearer(req));
    if (!identity) {
      json(res, 401, { ok: false, error: "node control authentication failed" });
      return;
    }
    // Stamped from the SAME clock `connectionState` ages it against (U335). Two clocks would make
    // the age a difference between unrelated numbers — which, with the negative clamp below it,
    // reads as permanently fresh: the exact defect this window exists to remove.
    this._lastSeen.set(identity.node_id, new Date(this._now()).toISOString());
    let payload = null;
    try {
      payload = await this._readBody(req);
      const operation = payload && payload.operation;
      if (operation === "identity") {
        json(res, 200, { ok: true, result: identity });
        return;
      }
      const handler = this._handlers[operation];
      if (typeof handler !== "function") throw new Error(`unsupported operation ${JSON.stringify(operation)}`);
      const result = await handler(identity, payload.arguments || {});
      this._recordOperation(identity, operation, payload.arguments || {}, true);
      json(res, 200, { ok: true, result });
    } catch (e) {
      try {
        const operation = payload ? payload.operation : null;
        if (operation && operation !== "identity") this._recordOperation(identity, operation,
          payload.arguments || {}, false, `${e.name || "Error"}: ${e.message}`);
      } catch { /* preserve the original failure */ }
      this._log(`control: ${identity.role}/${identity.node_id} request refused: ${e.message}`);
      json(res, 400, { ok: false, error: `${e.name || "Error"}: ${e.message}` });
    }
  }

  _readBody(req) {
    return new Promise((resolve, reject) => {
      const chunks = [];
      let size = 0;
      req.on("data", (chunk) => {
        size += chunk.length;
        if (size > MAX_BODY) {
          reject(new Error("request too large"));
          req.destroy();
          return;
        }
        chunks.push(chunk);
      });
      req.on("end", () => {
        try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}")); }
        catch (e) { reject(new Error(`malformed JSON: ${e.message}`)); }
      });
      req.on("error", reject);
    });
  }
}

module.exports = {
  SovereignControlServer, sessionEstablished, SESSION_ESTABLISHED_STATES,
  DEFAULT_STALE_AFTER_MS, DEFAULT_STOP_TIMEOUT_MS,
};
