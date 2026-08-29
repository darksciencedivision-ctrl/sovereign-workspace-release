"use strict";
/** Require-able live orchestration state projection (Phase 19.9, U338). */

const ACTIVE_WORKER_STATES = new Set(["running", "launching", "terminating"]);

function summarizeDispatch(nodes) {
  if (!nodes.length) return null;
  const ready = nodes.filter((node) => node.ready).length;
  const unverified = nodes.filter((node) => node.ready && node.mcp_fresh !== true).length;
  const activeTasks = nodes.filter((node) => node.task_status).length;
  return {
    text: `dispatch · ${nodes.length} governed worker${nodes.length === 1 ? "" : "s"} · ${ready} READY`
      + `${unverified ? ` (${unverified} MCP-unverified)` : ""}`
      + `${activeTasks ? ` · ${activeTasks} assigned` : ""}`,
    dispatched: true,
    owed: false,
    accepted: ready,
    mcp_unverified: unverified,
    legs: nodes.map((node) => ({
      node_id: node.node_id,
      provider_id: node.provider_id,
      model_id: node.model_id,
      pane_id: node.pane_id,
      ready: node.ready,
      mcp_state: node.mcp_state,
      mcp_fresh: node.mcp_fresh,
      task_status: node.task_status,
    })),
  };
}

function createOperationalState(io) {
  const liveWorkerRecords = () => (io.workerRecords() || [])
    .filter((record) => ACTIVE_WORKER_STATES.has(record.state));

  const operationalNodeStatus = (record) => {
    const chrome = io.chromeFor(record.paneId) || record.chrome || {};
    const mcp = io.mcpState(record.nodeId);
    return {
      node_id: record.nodeId,
      incarnation: record.nodeRegistration && record.nodeRegistration.incarnation,
      pane_id: record.paneId,
      session_id: record.sessionId,
      pid: record.pid,
      provider_id: chrome.provider || null,
      model_id: chrome.model_slug || null,
      role: chrome.operational_role || chrome.role || "worker",
      workspace: record.cwd,
      permission_profile: chrome.permission_profile_id || "pp-worker-reasoning",
      node_state: record.operationalState || record.state,
      ready: record.state === "running" && record.operationalState === "READY"
        && record.nodeAttested === true && io.sessionEstablished(mcp),
      supervised: record.supervised === true,
      lease_id: record.leaseId,
      lease_state: record.leaseId ? "active" : "not_applicable",
      subscription_ref: record.subscriptionRef,
      mcp_state: mcp.state,
      mcp_fresh: mcp.fresh === true,
      mcp_last_seen_age_ms: mcp.last_seen_age_ms ?? null,
      last_seen: mcp.last_seen,
      task_status: chrome.task_status || null,
      process_tree_owned: record.supervised === true,
      readiness: record.readiness || null,
      structured_failure: record.structuredFailure || null,
      created_utc: record.startedAt || record.created_utc || null,
      backend: (chrome.backend || record.backend || null),
    };
  };

  const operationalConductorStatus = () => {
    const launch = io.conductorLaunch();
    if (launch.state !== "running" || !launch.nodeId) return null;
    const descriptor = io.conductorDescriptor() || {};
    const mcp = io.mcpState(launch.nodeId);
    return {
      node_id: launch.nodeId,
      pane_id: io.conductorPaneId(),
      session_id: launch.sessionId,
      pid: launch.pid,
      provider_id: descriptor.provider_id || null,
      model_id: descriptor.model_id || null,
      role: "conductor",
      workspace: io.repoRoot,
      node_state: launch.operationalState || launch.state,
      ready: launch.state === "running" && launch.operationalState === "READY"
        && io.sessionEstablished(mcp),
      supervised: true,
      lease_id: launch.leaseId,
      lease_state: "active",
      subscription_ref: launch.subscriptionRef,
      mcp_state: mcp.state,
      mcp_fresh: mcp.fresh === true,
      mcp_last_seen_age_ms: mcp.last_seen_age_ms ?? null,
      last_seen: mcp.last_seen,
      task_status: null,
      process_tree_owned: true,
    };
  };

  const operationalDispatchSummary = () => summarizeDispatch(
    liveWorkerRecords().map(operationalNodeStatus),
  );

  const workerRecordFor = (args = {}) => {
    const records = liveWorkerRecords();
    if (args.node_id) return records.find((record) => record.nodeId === args.node_id) || null;
    const provider = io.normalizedProvider(args.provider);
    if (provider) {
      return records.find((record) => record.chrome && record.chrome.provider === provider) || null;
    }
    return null;
  };

  return {
    liveWorkerRecords,
    operationalConductorStatus,
    operationalDispatchSummary,
    operationalNodeStatus,
    workerRecordFor,
  };
}

module.exports = { ACTIVE_WORKER_STATES, createOperationalState, summarizeDispatch };
