"use strict";
/**
 * LOCAL-02 — the Sovereign MCP harness for a LOCAL pane (`ollama run <tag>`).
 *
 * WHAT WAS WRONG. LOCAL-01 opened the conductor seat to local models on the operator's own ruling
 * (ENTRY 018: "the conductor seat is agnostic ... It's not frontier only. That would defeat the
 * whole purpose of the system"), and `_local_conductor_registrations` marks every admitted ollama
 * model `conductor_capable=True`. `conductorAdmission` admits it, the governed spawn runs, and a
 * real `ollama run granite4.2:3b` process appears in pane 1. Then readiness asks for two things a
 * chat REPL cannot give:
 *
 *   1. `waitForNodeMcp` — `connectionState(nodeId).state === "connected"`, which only becomes true
 *      when an authenticated request ARRIVES at the control server from that node;
 *   2. turn 1 — the model must actually CALL `get_worker_status` (`operationCount` must rise).
 *
 * `build_interactive_ollama_command` emits exactly `["ollama", "run", tag]`. The child is handed
 * `SOVEREIGN_CONTROL_PORT` / `SOVEREIGN_CONTROL_TOKEN` (`main.js`, `childEnv`) and has nothing that
 * reads them, so no request ever arrives, `connectionState` stays `configured` — which the control
 * server's own doc defines as "a credential was issued and nothing ever arrived" — and the
 * conductor lands in STALLED after the full 120 s. Measured on the operator's host: `MCP connected`
 * appears in 3,499 log lines for `grok_build` and `google_antigravity` only, never once for
 * `ollama_local`. The local path was added; the downstream contract was not.
 *
 * WHAT THIS IS. The piece that was missing: a local pane's MCP client. A frontier node's harness is
 * its vendor CLI — the CLI holds the bearer, makes the calls, and is what `connected` has always
 * meant. A local pane has no such harness, because `ollama run` is a REPL and not an agent. This
 * module is that harness, and it lives shell-side because the PTY is the only surface a REPL
 * exposes.
 *
 * ── THE HONESTY BOUNDARY, which is the whole design ──────────────────────────────────────────────
 *
 * A bridge that simply heartbeats on a node's behalf would make `connected` mean "the shell is
 * running", which is worth nothing and would be a lie told in the one signal readiness trusts. The
 * line drawn here, and it is drawn in two different places for the two different claims:
 *
 *   * `connected` is a claim about the HARNESS, and the bridge may make it — but only for a pane
 *     with a LIVE session (`attach` refuses otherwise) and only for as long as that session lives
 *     (`detach` stops it). "This node's harness is attached to the control plane" is then exactly
 *     as true of the bridge as it is of the grok CLI, and it is the same claim in both cases. It is
 *     NOT a claim that the model is thinking, and it never was one for a frontier node either.
 *
 *   * every TOOL CALL is a claim about the MODEL, and the bridge never makes one. It relays blocks
 *     the model actually emitted into the pane, and nothing else — no synthesis, no retry of a call
 *     the model did not make, no "helpful" call on its behalf. So `operationCount(nodeId,
 *     "get_worker_status")` rising is real evidence the model emitted that call, which is precisely
 *     what readiness turn 1 is asking and the only thing that proves a conductor can conduct.
 *
 * The bridge therefore cannot make a mute model look READY: it can satisfy gate 1, which is about
 * attachment, and it is structurally unable to satisfy gate 2, which is about the model. A local
 * model that emits no tool call still STALLS, with the honest reason.
 *
 * ── THE WIRE ─────────────────────────────────────────────────────────────────────────────────────
 *
 * The model emits a fenced block; the bridge relays it and writes the result back as a DIFFERENT
 * fence (`sovereign-result`), which the scanner does not match, so a result can never be re-read as
 * a call:
 *
 *     ```sovereign
 *     {"operation": "get_worker_status", "arguments": {}}
 *     ```
 *
 * A fenced code block is the format a small instruct model is most reliably able to produce. The
 * protocol is TAUGHT to the model in the preamble (`BRIDGE_PREAMBLE`) rather than assumed.
 *
 * NO AUTHORITY LIVES HERE. The bridge holds the node's bearer and presents it; the control server
 * decides what that identity may do, exactly as it does for a CLI. A malformed or unknown operation
 * is refused BY THE SERVER and the refusal is handed back to the model verbatim. Writing into the
 * pane goes through the caller's governed writer (U328) — the bridge has no write path of its own,
 * so it cannot answer a modal on the operator's behalf (invariant 1).
 */

/** The fence the MODEL emits to make a call. Matched exactly — `sovereign-result` must not hit. */
const CALL_FENCE = "sovereign";
/** The fence the BRIDGE emits to return one. Never scanned, so a result is never re-executed. */
const RESULT_FENCE = "sovereign-result";

/**
 * ```sovereign\n {...} \n```
 *
 * The `(?![-\w])` after the tag is load-bearing: without it this also matches ```sovereign-result,
 * and the bridge would execute its own answers in a loop. `[^\S\r\n]*` allows trailing spaces on
 * the fence line, which models emit constantly. Non-greedy body, so two adjacent blocks are two
 * matches rather than one spanning both.
 */
const CALL_BLOCK = new RegExp(
  "```" + CALL_FENCE + "(?![-\\w])[^\\S\\r\\n]*\\r?\\n([\\s\\S]*?)```", "g");

/** What the model is told, once, before readiness asks it anything. */
const BRIDGE_PREAMBLE = [
  "You are the Conductor of a Sovereign workspace. You can call tools.",
  "To call one, emit a fenced block exactly like this and then STOP and wait for the result:",
  "```" + CALL_FENCE,
  '{"operation": "get_worker_status", "arguments": {}}',
  "```",
  "The result comes back to you in a ```" + RESULT_FENCE + " block. Never write that block yourself.",
  "Emit one call at a time. If you are only talking, do not emit a block at all.",
].join("\n");

/** Operations the control server exposes. Advisory ONLY — the server is the authority, and an
 *  operation absent here is still SENT and still refused there. It exists so an obvious typo can be
 *  answered locally with the list, which is far more use to a 3B model than a bare 400. */
const KNOWN_OPERATIONS = Object.freeze([
  "identity", "list_models", "spawn_worker", "stop_worker", "preflight_assignment",
  "assign_task", "get_worker_status", "notify_message", "notify_debate", "notify_debate_turn",
]);

/**
 * Extract the calls a window of pane text contains, in emission order.
 *
 * Returns `{calls, malformed}`. A block whose body is not JSON, or is JSON without a string
 * `operation`, is MALFORMED and reported rather than dropped: the model needs to be told, and a
 * bridge that silently ignores what it cannot read is how a model ends up waiting forever for an
 * answer to a call that was never made.
 */
function parseCalls(text) {
  const calls = [];
  const malformed = [];
  if (typeof text !== "string" || text === "") return { calls, malformed };
  CALL_BLOCK.lastIndex = 0;
  for (;;) {
    const m = CALL_BLOCK.exec(text);
    if (!m) break;
    const raw = String(m[1] || "").trim();
    let parsed = null;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      malformed.push({ raw, why: `not JSON: ${e.message}` });
      continue;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      malformed.push({ raw, why: "not a JSON object" });
      continue;
    }
    const operation = parsed.operation;
    if (typeof operation !== "string" || operation.trim() === "") {
      malformed.push({ raw, why: "no `operation` string" });
      continue;
    }
    const args = parsed.arguments;
    calls.push({
      operation: operation.trim(),
      // A model that omits `arguments`, or sends a non-object, means "none" — that is a formatting
      // slip and not a different call, and refusing it would spend a turn on punctuation.
      arguments: (args && typeof args === "object" && !Array.isArray(args)) ? args : {},
      raw,
    });
  }
  return { calls, malformed };
}

/** The block the bridge writes back. Kept in one place so the fence can never drift from the one
 *  `CALL_BLOCK` is written to exclude. */
function resultBlock(payload) {
  return "```" + RESULT_FENCE + "\n" + JSON.stringify(payload) + "\n```";
}

/**
 * @param io.nodeId        the Python-minted node id this bridge speaks as (never invented here).
 * @param io.paneId        the pane whose PTY carries the model.
 * @param io.token         the node's bearer, from the SAME `childEnv` mint the child was handed.
 * @param io.port          the control server's loopback port.
 * @param io.request       `({port, token, operation, arguments}) => {ok, result?, error?}`.
 * @param io.sessionAlive  `(paneId) => boolean` — is there a live session? Gates `connected`.
 * @param io.window        `{mark(paneId), since(paneId, mark)}` — the bounded reader (U329).
 * @param io.writePrompt   `(paneId, text) => Promise<boolean>` — the governed writer (U328).
 * @param io.writeRefusal  `(paneId) => refusal|null` — why a write is withheld, if it is.
 * @param io.now/sleep/log clocks and observability.
 */
function createLocalMcpBridge(io) {
  const nodeId = String(io.nodeId || "");
  const paneId = String(io.paneId || "");
  if (!nodeId) throw new Error("a local MCP bridge needs the node id the ticket minted");
  if (!paneId) throw new Error("a local MCP bridge needs the pane whose PTY it reads");

  const log = io.log || (() => {});
  const sleep = io.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const now = io.now || (() => Date.now());

  let attached = false;
  let mark = null;
  /** Calls already relayed, so a still-visible block in the window is not executed twice. The
   *  window is a SLIDING view of a live terminal: the same text is legitimately read many times,
   *  and without this a single `get_worker_status` would be spent on every poll. */
  const relayed = new Set();
  const stats = { calls_relayed: 0, calls_refused: 0, malformed: 0, heartbeats: 0, attached_at: null };

  async function call(operation, args) {
    return io.request({ port: io.port, token: io.token, operation, arguments: args || {} });
  }

  /**
   * Claim the harness is attached — the ONE claim this module makes on the node's behalf, and only
   * for a pane that really has a live session. A pane with no session gets no claim and no bridge:
   * that is the difference between "the harness is attached" and "the shell is running".
   */
  async function attach() {
    if (attached) return { attached: true, already: true };
    if (typeof io.sessionAlive === "function" && !io.sessionAlive(paneId)) {
      return { attached: false, reason: `pane ${paneId} has no live session — nothing to attach to` };
    }
    const res = await call("identity", {});
    if (!res || res.ok !== true) {
      // Fail closed and SAY so. The node stays `configured`, readiness times out with its own
      // reason, and nothing anywhere claims a connection that was refused.
      return { attached: false, reason: `control-plane identity call refused: ${(res && res.error) || "no answer"}` };
    }
    attached = true;
    stats.attached_at = new Date(now()).toISOString();
    mark = io.window.mark(paneId);
    log(`bridge: local MCP harness attached for ${nodeId} (pane ${paneId}) — `
      + `the node is now reachable on the control plane; tool calls remain the model's own`);
    return { attached: true, already: false };
  }

  function detach(why = "session ended") {
    if (!attached) return false;
    attached = false;
    relayed.clear();
    log(`bridge: local MCP harness detached for ${nodeId} (${why})`);
    return true;
  }

  /**
   * Keep `connectionState` fresh. This is the ATTACHMENT claim only, and it stops the moment the
   * session does — `sessionAlive` is re-read every beat rather than trusted from attach time, so a
   * dead pane cannot keep reporting `connected` off a bridge nobody stopped.
   */
  async function heartbeat() {
    if (!attached) return false;
    if (typeof io.sessionAlive === "function" && !io.sessionAlive(paneId)) {
      detach("the pane's session is gone");
      return false;
    }
    const res = await call("identity", {});
    if (res && res.ok === true) { stats.heartbeats += 1; return true; }
    return false;
  }

  /**
   * Read what the model has emitted since the last read, relay any calls, and write the results
   * back. Returns what happened, so a caller (and a test) can see it rather than infer it.
   */
  async function relayOnce() {
    if (!attached) return { relayed: 0, malformed: 0, refused: 0, wrote: false };
    const view = io.window.since(paneId, mark);
    const text = (view && typeof view.text === "string") ? view.text : "";
    const { calls, malformed } = parseCalls(text);
    const out = { relayed: 0, malformed: 0, refused: 0, wrote: false, results: [] };

    for (const bad of malformed) {
      const key = `bad:${bad.raw}`;
      if (relayed.has(key)) continue;
      relayed.add(key);
      stats.malformed += 1;
      out.malformed += 1;
      out.results.push({ ok: false, error: `malformed tool call (${bad.why})`,
        hint: `emit a \`\`\`${CALL_FENCE} block containing {"operation": ..., "arguments": {...}}` });
    }

    for (const c of calls) {
      const key = `call:${c.raw}`;
      if (relayed.has(key)) continue;
      relayed.add(key);
      if (!KNOWN_OPERATIONS.includes(c.operation)) {
        // Answered locally with the list, but NOT refused locally: the call is still sent below for
        // anything the server knows and this list does not. Only an operation the server itself
        // rejects is a refusal, and it is the server's to make.
        out.results.push({ ok: false, error: `unknown operation ${JSON.stringify(c.operation)}`,
          known_operations: KNOWN_OPERATIONS });
        out.refused += 1;
        stats.calls_refused += 1;
        continue;
      }
      const res = await call(c.operation, c.arguments);
      stats.calls_relayed += 1;
      out.relayed += 1;
      if (!res || res.ok !== true) {
        out.refused += 1;
        stats.calls_refused += 1;
        out.results.push({ ok: false, operation: c.operation,
          error: (res && res.error) || "the control plane returned no answer" });
      } else {
        out.results.push({ ok: true, operation: c.operation, result: res.result });
      }
    }

    if (out.results.length) {
      const refusal = typeof io.writeRefusal === "function" ? io.writeRefusal(paneId) : null;
      if (refusal) {
        // The governed writer withheld the write. The model is left waiting, and the REASON is
        // logged rather than swallowed — a result that never arrives is indistinguishable, from the
        // model's side, from a tool that does not work.
        log(`bridge: ${nodeId} tool result withheld by the pane-write gate: ${refusal.reason}`);
        out.withheld = refusal.reason;
      } else {
        for (const r of out.results) {
          // eslint-disable-next-line no-await-in-loop -- one write at a time is the point: the
          // governed writer settles a paste before the next, and interleaving them would race.
          const ok = await io.writePrompt(paneId, resultBlock(r));
          out.wrote = out.wrote || ok === true;
        }
      }
    }

    mark = io.window.mark(paneId);
    return out;
  }

  /** The preamble, delivered through the governed writer like any other system→pane text. */
  async function teach() {
    if (!attached) return false;
    const refusal = typeof io.writeRefusal === "function" ? io.writeRefusal(paneId) : null;
    if (refusal) {
      log(`bridge: ${nodeId} protocol preamble withheld by the pane-write gate: ${refusal.reason}`);
      return false;
    }
    const ok = await io.writePrompt(paneId, BRIDGE_PREAMBLE);
    if (ok) mark = io.window.mark(paneId);
    return ok === true;
  }

  /** Poll+heartbeat until stopped. Never throws: a bridge that dies takes the node's only MCP
   *  client with it, and a thrown error here would surface as a mute conductor with no reason. */
  function run({ pollMs = 500, heartbeatMs = 5000 } = {}) {
    let stopped = false;
    let lastBeat = 0;
    const loop = (async () => {
      while (!stopped && attached) {
        try {
          if (now() - lastBeat >= heartbeatMs) { lastBeat = now(); await heartbeat(); }
          if (attached) await relayOnce();
        } catch (e) {
          log(`bridge: ${nodeId} relay cycle failed (continuing): ${e.message}`);
        }
        await sleep(pollMs);
      }
    })();
    return { stop: (why) => { stopped = true; detach(why || "stopped"); return loop; }, loop };
  }

  return { attach, detach, heartbeat, relayOnce, teach, run, stats,
    get attached() { return attached; } };
}

/**
 * The default `request` — a loopback POST to the control server, shaped the way that server's own
 * reachability checks require (W-40): the node's bearer, an explicit `Host` naming the loopback
 * form and port it actually bound, and NO `Origin` header, since an origin-bearing request is
 * refused there as positive evidence of a browser client. Injectable, so every test above runs
 * without a socket.
 */
function createLoopbackRequest({ http = require("http"), timeoutMs = 10000 } = {}) {
  return function loopbackRequest({ port, token, operation, arguments: args }) {
    return new Promise((resolve) => {
      // Never rejects: a transport failure is an ANSWER ({ok:false}) so a dead socket reads the
      // same as a refusal and the relay loop keeps its one error path.
      const body = Buffer.from(JSON.stringify({ operation, arguments: args || {} }), "utf8");
      const req = http.request({
        host: "127.0.0.1", port, path: "/v1/tools/call", method: "POST",
        headers: {
          "content-type": "application/json",
          "content-length": body.length,
          host: `127.0.0.1:${port}`,
          authorization: `Bearer ${token}`,
        },
      }, (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          try { resolve(JSON.parse(text || "{}")); }
          catch { resolve({ ok: false, error: `control plane returned non-JSON (HTTP ${res.statusCode})` }); }
        });
      });
      req.setTimeout(timeoutMs, () => {
        req.destroy();
        resolve({ ok: false, error: `control plane did not answer within ${timeoutMs} ms` });
      });
      req.on("error", (e) => resolve({ ok: false, error: `control plane unreachable: ${e.message}` }));
      req.end(body);
    });
  };
}

module.exports = {
  createLocalMcpBridge, createLoopbackRequest, parseCalls, resultBlock,
  BRIDGE_PREAMBLE, KNOWN_OPERATIONS, CALL_FENCE, RESULT_FENCE,
};
