"use strict";

const { traitsFor } = require("./provider-traits");

/** Provider-facing readiness is stricter than process lifecycle.  These values extend the existing
 * launch record; they do not own process transitions or leases. */
const PROVIDER_STATES = Object.freeze([
  "STARTING", "AUTH_REQUIRED", "WORKSPACE_TRUST_REQUIRED", "MCP_CONNECTING",
  "MCP_PERMISSION_REQUIRED", "PROVIDER_SETUP_REQUIRED", "READY", "BUSY", "STALLED", "FAILED",
]);

function plainScreen(text) {
  return String(text || "")
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, " ");
}

/** The rules that hold for EVERY provider, declared or not. Authentication, workspace trust and an
 *  MCP permission prompt are states of the governed session, not of a vendor's TUI, so an
 *  undeclared provider is classified by them exactly as a declared one is. */
const UNIVERSAL_RULES = Object.freeze([
  Object.freeze({
    id: "provider_auth",
    pattern: /not authenticated|not signed in|sign in to continue|authentication required/i,
    state: "AUTH_REQUIRED", terminal_state: "AUTH_REQUIRED",
    reason: "provider authentication is unresolved",
  }),
  Object.freeze({
    id: "workspace_trust",
    pattern: /do you trust the contents of this project|yes,? i trust this folder|yes,? proceed/i,
    state: "WORKSPACE_TRUST_REQUIRED", terminal_state: "WORKSPACE_TRUST_REQUIRED",
    reason: "provider workspace trust is unresolved",
  }),
  Object.freeze({
    id: "mcp_permission",
    pattern: /permission required|approve this tool|allow this tool|mcp permission/i,
    also: /sovereign|mcp/i,
    state: "MCP_PERMISSION_REQUIRED", terminal_state: "MCP_PERMISSION_REQUIRED",
    reason: "Sovereign MCP permission is unresolved",
  }),
]);

const ruleMatches = (rule, s) => rule.pattern.test(s) && (!rule.also || rule.also.test(s));

/**
 * The provider state a screen shows, or null.
 *
 * 19.6 ([[U393]] MINOR-1): the provider-scoped rules are no longer `provider === "<vendor>"`
 * branches in this function — they are declared in `provider-traits.js` and consulted through the
 * descriptor. Behaviour is unchanged for the three vendors that had branches; what changed is that
 * a provider with no declaration is now classified by the universal rules and by nothing else,
 * which is what the inline form did by accident and could not be checked for.
 */
function classifyProviderScreen(provider, text) {
  const s = plainScreen(text);
  for (const rule of UNIVERSAL_RULES) {
    if (ruleMatches(rule, s)) {
      return { state: rule.state, terminal_state: rule.terminal_state, reason: rule.reason };
    }
  }
  for (const rule of traitsFor(provider).screen_rules) {
    if (ruleMatches(rule, s)) {
      return { state: rule.state, terminal_state: rule.terminal_state, reason: rule.reason };
    }
  }
  return null;
}

function occurrenceCount(text, token) {
  if (!token) return 0;
  let count = 0;
  let at = 0;
  const haystack = plainScreen(text);
  while ((at = haystack.indexOf(token, at)) !== -1) { count += 1; at += token.length; }
  return count;
}

function structuredProviderFailure({ provider, model, nodeId, taskId = null, stage,
  lastSuccessfulMcpOperation = null, lastProgressTimestamp = null,
  providerTerminalState = "STALLED", leaseState = "unknown", processState = "unknown",
  retryEligibility = "governed_retry_only" }) {
  return {
    provider, model, node_id: nodeId, task_id: taskId, stage,
    last_successful_mcp_operation: lastSuccessfulMcpOperation,
    last_progress_timestamp: lastProgressTimestamp,
    provider_terminal_state: providerTerminalState,
    lease_state: leaseState, process_state: processState, retry_eligibility: retryEligibility,
  };
}

module.exports = {
  PROVIDER_STATES, plainScreen, classifyProviderScreen, occurrenceCount, structuredProviderFailure,
};
