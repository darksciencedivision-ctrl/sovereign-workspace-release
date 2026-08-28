"use strict";

/**
 * Readiness evidence may report only facts the runtime observed (U337, Phase 19.8).
 *
 * A launch record saying `supervised:true` is an assertion made on the success branch. It becomes
 * evidence only when the SessionManager still reports the exact pid + generation. Likewise an MCP
 * session is `connected` only when the gateway currently reports that state; `stale` is established
 * but unverified and must not be promoted to a fabricated true. Fields for provider authentication,
 * workspace acceptance, MCP discovery, identity validation and permission resolution are deliberately
 * absent: this runtime has no independent observer for them.
 */

function processSupervisionObserved(record, processIdentity) {
  return Boolean(record && record.supervised === true
    && Number.isInteger(record.pid) && Number.isInteger(record.sessionGeneration)
    && processIdentity && Number.isInteger(processIdentity.pid)
    && Number.isInteger(processIdentity.generation)
    && record.pid === processIdentity.pid
    && record.sessionGeneration === processIdentity.generation);
}

function observedReadinessEvidence({
  record = null, processIdentity = null, mcpState = null, nodeRegistered,
} = {}) {
  const evidence = {};
  if (processIdentity !== undefined && processIdentity !== null) {
    evidence.process_supervised = processSupervisionObserved(record, processIdentity);
  }
  if (typeof nodeRegistered === "boolean") evidence.node_registered = nodeRegistered;
  if (mcpState && typeof mcpState.state === "string") {
    evidence.mcp_connected = mcpState.state === "connected";
  }
  return evidence;
}

module.exports = { processSupervisionObserved, observedReadinessEvidence };
