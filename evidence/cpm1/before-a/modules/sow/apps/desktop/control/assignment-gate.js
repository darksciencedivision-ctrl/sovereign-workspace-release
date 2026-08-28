"use strict";
const { sessionEstablished } = require("./sovereign-control-server");
/**
 * Whether a task may be delivered to a worker node — U335, Phase 19 unit 19.7.
 *
 * WHAT WAS WRONG. `controlAssignTask` refused a worker on its PANE state alone (`state !== "running"
 * || operationalState !== "READY"`) and then typed the assignment into its ConPTY. Both of those
 * facts are about the terminal, not about the node: a worker whose Python MCP subprocess had died
 * behind a still-running PTY is `running`/`READY` forever, because nothing clears either. The
 * conductor could therefore assign work to a node that could not make a single tool call, and the
 * assignment would sit in a pane with a `task_status: "ASSIGNED"` badge over it. The audit recorded
 * that as "a dead MCP subprocess behind a live PTY reports connected"; this is its assignment half.
 *
 * WHAT THIS ADDS is the third fact — the one the node itself produces. `SovereignControlServer`
 * stamps `_lastSeen` when a request ARRIVES, so a node that has called within the staleness window
 * has demonstrably still got a working MCP session; past that window nothing has been demonstrated.
 * The gate refuses on that, and the refusal says which of the three facts failed.
 *
 * `stale` IS NOT `dead`, AND THAT IS WHY THIS IS A PER-ATTEMPT REFUSAL. A worker that is simply
 * idle — a real case: the conductor may decompose for minutes before assigning — goes stale without
 * anything being wrong with it, and this gate will refuse that worker. Two things keep that from
 * becoming the class of defect 19.4 spent a unit removing (a classification that pins a healthy
 * worker forever):
 *
 *   - **Nothing is written down ABOUT THE WORKER.** The gate returns a refusal for THIS attempt. It
 *     sets no operational state, records no structured failure, and the next call re-derives from
 *     scratch — so the moment the node makes any gateway call at all, the same assignment succeeds.
 *     What this does NOT say, because the first version of it did (spec-auditor, MAJOR-2): the
 *     CALLER's failure path used to write. Phase 19.9 closes [[U436]] by invoking this gate for
 *     every owner before `create_task`, then repeating the same preflight before any pane write.
 *     A routine stale-owner refusal therefore leaves neither a durable BLOCKED row nor a first
 *     owner half-delivered.
 *   - **The refusal names an exit that EXISTS.** `retryable: true`, the age, and the one provocation
 *     a conductor can actually perform are in the reason.
 *
 * THE EXIT, STATED EXACTLY, because the first version of this file named one that does not exist
 * (gate-validator round 1, BLOCKING-1: it told the caller to "re-run readiness", and no re-run is
 * reachable for a worker already READY — `runWorkerReadiness` is called only from the two spawn
 * paths). What a conductor holding a stale worker can do, today, in the shipped product:
 * `send_message` to that node → `controlNotifyMessage` → `notifyNode` types a prompt into its pane
 * asking it to read its messages and answer through MCP, and the answer is a gateway call that
 * clears the staleness. Failing that, the node's own next gateway call clears it. Both are real;
 * neither is instant, and this comment does not pretend otherwise. Nor is the first one guaranteed:
 * `notifyNode` goes through the U328 write gate and can be WITHHELD if that pane is showing a modal
 * (`control/pane-writer.js` answers `{written: false, refused}`), in which case the provocation did
 * not happen and the caller is told so (round-2 validator, MINOR-3).
 *
 * TWO residues, recorded rather than rounded off ([[U434]]):
 *   - There is no server→node ping and no node heartbeat, so an idle worker cannot be VERIFIED on
 *     demand — only provoked. A heartbeat on a cadence shorter than the window is the proper fix.
 *   - `_lastSeen` observes gateway-mediated calls only, so a node doing store-only MCP work
 *     (`read_messages`, `close_debate`, artifact reads) goes stale while working. That is why this
 *     refusal is worded as UNVERIFIED and never as failure, and it is the strongest argument for the
 *     heartbeat above.
 *
 * It lives here, not in `main.js`, for the reason every other module in this directory does: main.js
 * cannot be required in a test (U338), and a gate nobody can drive is a gate nobody has graded.
 */

/** The pane facts a worker must present before its node state is even consulted. */
const RUNNING = "running";
const READY = "READY";

/**
 * @param {object} arg
 * @param {string} arg.nodeId            the node the conductor named
 * @param {object|null} arg.record       the worker launch record, or null when there is no such worker
 * @param {object|null} arg.mcp          `SovereignControlServer.connectionState(nodeId)`, or null when
 *                                       there is no gateway to ask (which is itself a refusal)
 * @returns {null|{node_id:string, code:string, reason:string, retryable:boolean, mcp_state:(string|null),
 *                 last_seen:(string|null), last_seen_age_ms:(number|null), stale_after_ms:(number|null)}}
 *          null when the assignment may proceed.
 */
function assignmentRefusal({ nodeId, record = null, mcp = null } = {}) {
  const id = String(nodeId || "");
  const state = mcp && typeof mcp.state === "string" ? mcp.state : null;
  const base = {
    node_id: id, mcp_state: state,
    last_seen: (mcp && mcp.last_seen) || null,
    last_seen_age_ms: mcp && Number.isFinite(mcp.last_seen_age_ms) ? mcp.last_seen_age_ms : null,
    stale_after_ms: mcp && Number.isFinite(mcp.stale_after_ms) ? mcp.stale_after_ms : null,
  };
  // 1. THE PROCESS, first — the same order `worker-readiness.js` restored for U329. A worker that is
  //    gone is reported as gone, never as a connection problem.
  if (!record || record.state !== RUNNING) {
    return {
      ...base, code: "worker_not_running", retryable: false,
      reason: `worker ${id} is not task-ready (${record ? record.state : "not running"})`,
    };
  }
  // 2. The readiness verdict the state machine already reached.
  if (record.operationalState !== READY) {
    return {
      ...base, code: "worker_not_ready", retryable: true,
      reason: `worker ${id} is not task-ready (${record.operationalState || "unknown"})`,
    };
  }
  // 3. THE NODE'S OWN SESSION. Fail closed when there is no gateway to ask at all: "I cannot see" is
  //    not "nothing is wrong" (invariant 27, Buildout §4).
  if (!mcp) {
    return {
      ...base, code: "mcp_unreadable", retryable: true,
      reason: `worker ${id} is READY but its Sovereign MCP session cannot be read from this shell`,
    };
  }
  if (!sessionEstablished(mcp)) {
    return {
      ...base, code: "mcp_never_connected", retryable: true,
      reason: `worker ${id} is READY but has never called the Sovereign MCP gateway (${state || "unknown"})`,
    };
  }
  if (state === "stale") {
    const age = base.last_seen_age_ms;
    const window = base.stale_after_ms;
    return {
      ...base, code: "mcp_unverified", retryable: true,
      reason: `worker ${id} is READY but its Sovereign MCP session is UNVERIFIED — its last call `
        + `arrived ${age === null ? "at an unreadable time" : `${age} ms ago`}`
        + `${window === null ? "" : `, past the ${window} ms staleness window`}. `
        + "It may be healthy and idle, or busy on store-only MCP reads. Provoke it with send_message "
        + "to that node, or wait for its next call — this refusal clears on the node's next gateway "
        + "call and nothing about the worker was changed.",
    };
  }
  return null;
}

module.exports = { assignmentRefusal, RUNNING, READY };
