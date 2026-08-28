"use strict";
/** Require-able conductor readiness state machine (Phase 19.9, U338). */

function createConductorReadiness(io) {
  return async function runConductorReadiness() {
    const descriptor = io.descriptor();
    let launch = { ...io.launch(), operationalState: "MCP_CONNECTING" };
    io.setLaunch(launch);
    io.push();

    const admission = io.admit(descriptor);
    if (!admission.ok) {
      launch = { ...io.launch(), operationalState: admission.state, reason: admission.reason };
      io.setLaunch(launch);
      io.push();
      return { ready: false, state: admission.state, reason: launch.reason };
    }
    if (!await io.waitForNodeMcp(io.launch().nodeId, io.mcpTimeoutMs())) {
      launch = { ...io.launch(), operationalState: "STALLED",
        reason: "conductor Sovereign MCP readiness timed out" };
      io.setLaunch(launch);
      io.push();
      return { ready: false, state: "STALLED", reason: launch.reason };
    }

    const baseline = io.operationCount(io.launch().nodeId, "get_worker_status");
    let lastToolSucceeded = false;
    let lastAnswered = false;
    for (let turn = 1; turn <= admission.readiness_turns; turn += 1) {
      const probe = io.buildProbe();
      const prompt = turn === 1
        ? `First call the Sovereign get_worker_status tool. Then ${probe.prompt}`
        : probe.prompt;
      const mark = io.window.mark(io.paneId());
      const refusal = io.writeRefusal(io.paneId());
      if (refusal) {
        launch = { ...io.launch(), operationalState: refusal.state,
          reason: `conductor readiness withheld: ${refusal.reason}` };
        io.setLaunch(launch);
        io.push();
        return { ready: false, state: refusal.state, reason: launch.reason };
      }
      if (!await io.writePrompt(io.paneId(), prompt)) {
        launch = { ...io.launch(), operationalState: "FAILED",
          reason: "conductor readiness prompt was not delivered" };
        io.setLaunch(launch);
        io.push();
        return { ready: false, state: "FAILED", reason: launch.reason };
      }
      const deadline = io.now() + io.responseDeadlineMs();
      let answered = false;
      let toolSucceeded = false;
      while (!answered && io.now() < deadline) {
        toolSucceeded = io.operationCount(io.launch().nodeId, "get_worker_status") > baseline;
        const answerWindow = io.window.since(io.paneId(), mark);
        if (toolSucceeded && answerWindow.answerable
            && io.answerObserved(answerWindow.text, probe).seen) {
          answered = true;
          break;
        }
        await io.sleep(250);
      }
      lastToolSucceeded = toolSucceeded;
      lastAnswered = answered;
      if (!answered) {
        launch = { ...io.launch(), operationalState: "STALLED",
          reason: admission.readiness_turns > 1
            ? `conductor typed readiness response timed out on turn ${turn} of ${admission.readiness_turns}`
            : "conductor typed readiness response timed out" };
        io.setLaunch(launch);
        io.push();
        return { ready: false, state: "STALLED", reason: launch.reason };
      }
    }

    const observedProcess = io.processIdentity(io.paneId());
    const observedMcp = io.mcpState(io.launch().nodeId);
    launch = { ...io.launch(), operationalState: "READY",
      mcpState: observedMcp ? observedMcp.state : "disconnected",
      readiness: {
        descriptor_admitted: admission.ok === true, decided_by: admission.decided_by,
        provider_id: admission.provider_id, model_id: admission.model_id,
        selection_source: admission.selection_source,
        ...io.observedEvidence({
          record: io.launch(), processIdentity: observedProcess, mcpState: observedMcp,
          nodeRegistered: Boolean(io.launch().nodeId && observedProcess),
        }),
        status_tool_succeeded: lastToolSucceeded,
        readiness_response_succeeded: lastAnswered,
        readiness_responses: admission.readiness_turns,
      } };
    io.setLaunch(launch);
    io.push();
    return { ready: true, state: "READY", readiness: launch.readiness };
  };
}

module.exports = { createConductorReadiness };
