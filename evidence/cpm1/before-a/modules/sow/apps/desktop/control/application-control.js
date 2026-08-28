"use strict";
/**
 * Require-able orchestration/application-control logic (Phase 19.9, U338).
 *
 * Electron main owns the live bindings: panes, SessionManager, picker source, renderer sends and
 * the loopback gateway. This module owns the decisions and sequencing that used to be trapped in
 * main.js: role checks, task/debate/message deadlines, worker spawn/stop, assignment delivery and
 * collaboration notifications. Every dependency is injected so node --test executes the same
 * functions the HTTP gateway calls.
 */

function requireControlRole(identity, ...roles) {
  if (!identity || !roles.includes(identity.role)) {
    throw new Error(`operation requires ${roles.join("|")} role`);
  }
}

function normalizedProvider(value) {
  const raw = String(value || "").trim();
  return raw || null;
}

/**
 * The shape of an identifier that may be INTERPOLATED into a prompt a peer's ConPTY will receive
 * (W-01, R-01). The notify handlers are HTTP-reachable on the control gateway and deliberately
 * carry no `requireControlRole`: the MCP server calls them as a side effect of an already-authorized
 * `send_message` on behalf of the SENDING node, which is usually a worker, so a blanket conductor
 * gate would refuse legitimate worker->conductor delivery. What is missing is not a role check but a
 * constraint on the payload, which today is entirely caller-authored.
 *
 * An identifier is a NAME. It is therefore checked for the shape of one and REFUSED when it is not,
 * rather than sanitized: a sanitizer would silently deliver a different id than the one the caller
 * named, and the caller is the party this gate exists to distrust.
 */
const SOVEREIGN_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;

/** A refusal that NAMES its gate, so a caller reports which constraint refused rather than a string. */
function controlRefusal(gate, reason) {
  const error = new Error(`${gate}: ${reason}`);
  error.gate = gate;
  return error;
}

function requireSovereignIds(gate, fields) {
  for (const [name, value] of Object.entries(fields)) {
    const text = value === null || value === undefined ? "" : String(value);
    if (!SOVEREIGN_ID.test(text)) {
      throw controlRefusal(gate, `${name} is not a Sovereign identifier`);
    }
  }
}

/**
 * The nodes this notify may reach, from state the SHELL already holds (W-01 part 2).
 *
 * `liveWorkerRecords`, `chromeFor` and `conductorNodeId` are already on this module's io surface, so
 * no new dependency is taken here — and deliberately NOT `fetchOperationalState`, which spawns
 * `py -3.12` and is far too expensive to pay per notification.
 *
 * A `taskId` of null means the notify carries no task to scope by (`notify_debate_turn` has only a
 * debate id), and the bound is then "a node this shell actually governs" rather than "any string" —
 * weaker than the task scope, and still not the arbitrary recipient the defect allowed. The
 * conductor is always reachable: a worker answering the operator is the legitimate case this whole
 * path exists for.
 */
function deliverableNodeIds(io, taskId) {
  const allowed = new Set();
  for (const rec of io.liveWorkerRecords() || []) {
    if (!rec || !rec.nodeId) continue;
    const chrome = io.chromeFor(rec.paneId) || rec.chrome || {};
    if (taskId === null || chrome.task_id === taskId) allowed.add(rec.nodeId);
  }
  const conductor = io.conductorNodeId && io.conductorNodeId();
  if (conductor) allowed.add(conductor);
  return allowed;
}

function scopedRecipients(io, gate, requested, taskId) {
  const allowed = deliverableNodeIds(io, taskId);
  const scoped = [];
  const refused = [];
  for (const nodeId of requested || []) (allowed.has(nodeId) ? scoped : refused).push(nodeId);
  if (refused.length) {
    io.log(`control: ${gate} dropped ${refused.length} recipient(s) outside this notify's scope: `
      + `${refused.join(", ")}`);
  }
  return scoped;
}

function taskPrompt(task) {
  return [
    "SOVEREIGN MCP ASSIGNMENT", `Task: ${task.task_id}`, `Thread: ${task.thread_id}`,
    `Objective: ${task.objective}`, `Scope: ${JSON.stringify(task.scope || {})}`,
    `Constraints: ${(task.constraints || []).join("; ") || "none"}`,
    `Expected output: ${task.expected_output || "candidate result"}`,
    `Acceptance criteria: ${(task.acceptance_criteria || []).join("; ") || "none"}`,
    `Peer nodes: ${(task.peer_nodes || []).join(", ")}`,
    "Use the Sovereign publish_progress tool for lifecycle updates, send_message/read_messages for peer questions, "
      + "post_debate_turn for debate participation, and publish_candidate for the final result. "
      + "Do not leave the result only in terminal scrollback or mark IN_PROGRESS as complete.",
  ].join("\n");
}

function createDeadlineController(io) {
  const workerTaskTimers = new Map();
  const peerResponseTimers = new Map();
  const debateTurnTimers = new Map();
  const setTimer = io.setTimeout || setTimeout;
  const clearTimer = io.clearTimeout || clearTimeout;
  const workerSoftMs = Number(io.workerTaskSoftDeadlineMs);
  const workerHardMs = Number(io.workerTaskHardDeadlineMs);
  const peerMs = Number(io.peerResponseDeadlineMs);
  const debateMs = Number(io.debateTurnDeadlineMs);

  function clearWorkerTaskDeadline(nodeId) {
    const timers = workerTaskTimers.get(nodeId);
    if (!timers) return;
    clearTimer(timers.soft);
    clearTimer(timers.hard);
    workerTaskTimers.delete(nodeId);
  }

  function markWorkerDeadlineFailure(nodeId, taskId, stage) {
    const current = io.workerRecordFor({ node_id: nodeId });
    if (!current || !["READY", "BUSY"].includes(current.operationalState)) return;
    const failure = { ...io.readinessFailure(current, stage), task_id: taskId };
    io.setWorkerOperationalState(current.paneId, "STALLED", { structuredFailure: failure });
    Promise.resolve(io.notifyNode(io.conductorNodeId(),
      `Worker ${nodeId} missed ${stage} for task ${taskId}. Structured failure: ${JSON.stringify(failure)}`))
      .catch(() => {});
  }

  function clearPeerResponseTimer(questionId, nodeId) {
    const key = `${questionId}:${nodeId}`;
    const pending = peerResponseTimers.get(key);
    if (pending) clearTimer(pending.timer);
    peerResponseTimers.delete(key);
  }

  function schedulePeerResponseTimers(message) {
    for (const nodeId of message.recipient_node_ids || []) {
      clearPeerResponseTimer(message.message_id, nodeId);
      const timer = setTimer(() => {
        peerResponseTimers.delete(`${message.message_id}:${nodeId}`);
        markWorkerDeadlineFailure(nodeId, message.task_id, "peer_message_response_deadline");
      }, peerMs);
      timer && timer.unref?.();
      peerResponseTimers.set(`${message.message_id}:${nodeId}`, {
        timer, nodeId, taskId: message.task_id, questionId: message.message_id,
      });
    }
  }

  function clearDebateTurnTimer(debateId, nodeId) {
    const key = `${debateId}:${nodeId}`;
    const pending = debateTurnTimers.get(key);
    if (pending) clearTimer(pending.timer);
    debateTurnTimers.delete(key);
  }

  function scheduleDebateTurnTimers(debate) {
    for (const nodeId of debate.participant_node_ids || []) {
      clearDebateTurnTimer(debate.debate_id, nodeId);
      const timer = setTimer(() => {
        debateTurnTimers.delete(`${debate.debate_id}:${nodeId}`);
        markWorkerDeadlineFailure(nodeId, debate.task_id, "debate_turn_deadline");
      }, debateMs);
      timer && timer.unref?.();
      debateTurnTimers.set(`${debate.debate_id}:${nodeId}`, {
        timer, nodeId, taskId: debate.task_id, debateId: debate.debate_id,
      });
    }
  }

  function clearNodeDeadlines(nodeId) {
    clearWorkerTaskDeadline(nodeId);
    for (const [key, pending] of peerResponseTimers) {
      if (pending.nodeId === nodeId) {
        clearTimer(pending.timer);
        peerResponseTimers.delete(key);
      }
    }
    for (const [key, pending] of debateTurnTimers) {
      if (pending.nodeId === nodeId) {
        clearTimer(pending.timer);
        debateTurnTimers.delete(key);
      }
    }
  }

  function scheduleWorkerTaskDeadline(record, taskId) {
    clearWorkerTaskDeadline(record.nodeId);
    const soft = setTimer(() => {
      const current = io.workerRecordFor({ node_id: record.nodeId });
      if (!current || current.operationalState !== "BUSY") return;
      io.setWorkerOperationalState(current.paneId, "BUSY", {
        readiness: { ...(current.readiness || {}), soft_deadline_reached: true },
      });
    }, workerSoftMs);
    const hard = setTimer(() => {
      const current = io.workerRecordFor({ node_id: record.nodeId });
      if (!current || current.operationalState !== "BUSY") return;
      const failure = { ...io.readinessFailure(current, "worker_task_hard_deadline"), task_id: taskId };
      io.setWorkerOperationalState(current.paneId, "STALLED", { structuredFailure: failure });
      Promise.resolve(io.notifyNode(io.conductorNodeId(),
        `Worker ${current.nodeId} stalled on task ${taskId}. Structured failure: ${JSON.stringify(failure)}`))
        .catch(() => {});
    }, workerHardMs);
    soft && soft.unref?.();
    hard && hard.unref?.();
    workerTaskTimers.set(record.nodeId, { soft, hard, taskId });
  }

  function onOperation(identity, event) {
    if (!event.ok) return;
    const args = event.arguments || {};
    if (event.operation === "notify_message" && args.message) {
      if (args.message.message_kind === "question") schedulePeerResponseTimers(args.message);
      if (args.message.message_kind === "answer" && args.message.reply_to) {
        clearPeerResponseTimer(args.message.reply_to, identity.node_id);
      }
    }
    if (event.operation === "notify_debate" && args.debate) scheduleDebateTurnTimers(args.debate);
    if (event.operation === "notify_debate_turn" && args.turn) {
      clearDebateTurnTimer(args.debate_id, args.turn.node_id);
    }
    if (identity.role !== "worker") return;
    const record = io.workerRecordFor({ node_id: identity.node_id });
    if (!record) return;
    const patch = { lastSuccessfulMcpOperation: event.operation };
    const task = args.task;
    if (event.operation === "notify_message" && task) {
      patch.lastProgressAt = event.at;
      if (["CANDIDATE_READY", "COMPLETED", "FAILED", "CANCELLED", "BLOCKED"].includes(task.status)) {
        clearNodeDeadlines(identity.node_id);
        patch.operationalState = task.status === "FAILED" ? "FAILED" : "READY";
      } else {
        patch.operationalState = "BUSY";
      }
    }
    io.updateWorkerRecord(record.paneId, patch);
    io.pushConductor();
  }

  return {
    clearNodeDeadlines, scheduleWorkerTaskDeadline, onOperation,
    pendingCounts: () => ({ workers: workerTaskTimers.size, peers: peerResponseTimers.size,
      debates: debateTurnTimers.size }),
  };
}

function createApplicationControl(io) {
  const deadlines = createDeadlineController(io);

  async function listModels(identity) {
    requireControlRole(identity, "conductor", "worker", "operator");
    const model = await io.fetchPickerModel({ cwd: io.repoRoot });
    io.setPickerModel(model);
    if (!model || model.ok !== true) {
      throw new Error((model && model.error) || "live model registry unavailable");
    }
    return (model.picker.options || []).map((o) => ({
      provider_id: o.provider, adapter_id: o.adapter, model_id: o.model_slug,
      display_name: o.label, roles: o.roles, available: o.available === true,
      registered: o.registered !== false, conductor_capable: o.conductor_capable === true,
      authentication_status: o.authentication_status, unavailable_reason: o.unavailable_reason,
    }));
  }

  async function spawnWorker(identity, args = {}) {
    requireControlRole(identity, "conductor");
    const provider = normalizedProvider(args.provider);
    const modelId = String(args.model_id || "").trim();
    if (!provider || !modelId) {
      throw new Error("spawn_worker requires the exact provider_id and model_id returned by list_models");
    }
    await listModels(identity);
    const sourceOptions = (io.pickerModel().picker || {}).options || [];
    const option = sourceOptions.find((o) => o.provider === provider && o.model_slug === modelId
      && o.available === true && Array.isArray(o.roles) && o.roles.includes("reasoning"));
    if (!option) throw new Error(`provider/model ${provider}/${modelId} is not an available registered worker option`);
    // W-12: match the picker lookup three lines above, which has always keyed on provider AND
    // model. Keying the duplicate check on the PROVIDER alone meant that asking for model B while
    // model A of the same provider was live returned `{duplicate:true}` and handed the conductor
    // the WRONG MODEL'S node, reported ready. One provider, two models, two nodes.
    const duplicate = io.liveWorkerRecords().find((r) => r.chrome
      && r.chrome.provider === provider && r.chrome.model_slug === modelId);
    if (duplicate) {
      if (duplicate.operationalState !== "READY") await io.runWorkerReadiness(duplicate.paneId);
      const node = io.operationalNodeStatus(duplicate);
      return { duplicate: true, ready: node.ready, node };
    }
    const res = await io.spawnFromSelection({ option, role: "reasoning", mode: "attended", targetPaneId: null });
    if (!res.launched) throw new Error(res.error || res.reason || `${provider} launch failed`);
    const rec = io.workerRecordForPane(res.target);
    const chrome = { ...(io.chromeFor(res.target) || rec.chrome || {}),
      operational_role: args.role || "research" };
    io.setChrome(res.target, chrome);
    io.persistLayoutSnapshot();
    io.sendPaneChrome(res.target, chrome);
    const readiness = await io.runWorkerReadiness(rec.paneId);
    const node = io.operationalNodeStatus({ ...io.workerRecordForPane(rec.paneId), chrome });
    io.pushConductor();
    io.log(`control: conductor ${identity.node_id} spawned ${provider}/${modelId} in ${res.target} `
      + `(node ${node.node_id}, MCP ${node.mcp_state})`);
    return { duplicate: false, ready: node.ready, readiness, node };
  }

  async function stopWorker(identity, args = {}) {
    requireControlRole(identity, "conductor");
    const rec = io.workerRecordFor(args);
    if (!rec) throw new Error("no matching live worker");
    deadlines.clearNodeDeadlines(rec.nodeId);
    io.killPane(rec.paneId);
    return { stopping: true, node: io.operationalNodeStatus({ ...rec, state: "terminating" }) };
  }

  function preflightAssignment(identity, args = {}) {
    requireControlRole(identity, "conductor");
    const ownerNodeIds = args.worker_node_ids || (args.task && args.task.owner_node_ids);
    if (!Array.isArray(ownerNodeIds)) throw new Error("assignment carries no worker nodes");
    // Preflight EVERY owner before typing to any pane. A two-owner task must not half-deliver when
    // the second node is stale (U436). Python invokes this before create_task too, so a routine
    // refusal does not append a durable BLOCKED row to project history.
    return ownerNodeIds.map((nodeId) => {
      const rec = io.workerRecordFor({ node_id: nodeId });
      const refusal = io.assignmentRefusal({ nodeId, record: rec,
        mcp: io.mcpState(nodeId, rec) });
      if (refusal) {
        io.log(`control: assignment to ${nodeId} refused (${refusal.code}) — ${refusal.reason}`);
        throw new Error(refusal.reason);
      }
      return { nodeId, rec };
    });
  }

  async function assignTask(identity, args = {}) {
    const task = args.task;
    const admitted = preflightAssignment(identity, { task });
    const delivered = [];
    for (const { nodeId, rec } of admitted) {
      const written = await io.writePanePrompt(rec.paneId, taskPrompt(task));
      if (!written) throw new Error(`worker ${nodeId} pane rejected the assignment write`);
      const chrome = { ...(io.chromeFor(rec.paneId) || rec.chrome || {}), task_id: task.task_id,
        task_status: "ASSIGNED", progress_state: "assignment delivered" };
      io.setChrome(rec.paneId, chrome);
      io.sendPaneChrome(rec.paneId, chrome);
      delivered.push({ node_id: nodeId, pane_id: rec.paneId, written: true });
      io.setWorkerOperationalState(rec.paneId, "BUSY", { lastProgressAt: new Date().toISOString() });
      deadlines.scheduleWorkerTaskDeadline(rec, task.task_id);
    }
    io.persistLayoutSnapshot();
    io.pushConductor();
    return { task_id: task.task_id, delivered };
  }

  async function notifyMessage(identity, args = {}) {
    const message = args.message;
    if (!message || message.sender_node_id !== identity.node_id) throw new Error("message sender identity mismatch");
    requireSovereignIds("notify_message_identifiers", {
      message_id: message.message_id, task_id: message.task_id,
      sender_node_id: message.sender_node_id,
    });
    const task = args.task;
    if (task && task.task_id === message.task_id) {
      const sender = io.workerRecordFor({ node_id: identity.node_id });
      if (sender) {
        const chrome = { ...(io.chromeFor(sender.paneId) || sender.chrome || {}),
          task_id: task.task_id, task_status: task.status,
          progress_state: (task.latest_progress && (task.latest_progress.working_on
            || task.latest_progress.completed || task.latest_progress.what_remains)) || task.status };
        io.setChrome(sender.paneId, chrome);
        io.sendPaneChrome(sender.paneId, chrome);
        io.persistLayoutSnapshot();
        io.pushConductor();
      }
    }
    const prompt = `Sovereign MCP message ${message.message_id} arrived for task ${message.task_id} from `
      + `${message.sender_node_id}. Use the Sovereign read_messages tool for task ${message.task_id} now and respond through MCP.`;
    const recipients = scopedRecipients(io, "notify_message_recipients",
      message.recipient_node_ids, message.task_id);
    return { deliveries: await Promise.all(recipients
      .map((nodeId) => io.notifyNode(nodeId, prompt))) };
  }

  async function notifyDebate(identity, args = {}) {
    const debate = args.debate;
    if (!debate || debate.opened_by_node_id !== identity.node_id) throw new Error("debate caller identity mismatch");
    requireSovereignIds("notify_debate_identifiers", {
      debate_id: debate.debate_id, task_id: debate.task_id,
      opened_by_node_id: debate.opened_by_node_id,
    });
    // `debate.proposition` is free text, not an identifier, and is NOT shape-checked here: its
    // control characters are flattened at the write boundary (W-02, `control/pane-writer.js`), which
    // is the one place every system write passes. Checking it here as well would be a second policy.
    const prompt = `Sovereign debate ${debate.debate_id} opened for task ${debate.task_id}: ${debate.proposition}. `
      + "Read task messages and post your bounded turn with the Sovereign post_debate_turn tool.";
    const recipients = scopedRecipients(io, "notify_debate_recipients",
      debate.participant_node_ids, debate.task_id);
    return { deliveries: await Promise.all(recipients
      .map((nodeId) => io.notifyNode(nodeId, prompt))) };
  }

  async function notifyDebateTurn(identity, args = {}) {
    const turn = args.turn;
    if (!turn || turn.node_id !== identity.node_id) throw new Error("debate turn identity mismatch");
    requireSovereignIds("notify_debate_turn_identifiers", {
      debate_id: args.debate_id, node_id: turn.node_id,
    });
    const prompt = `A peer posted a turn in Sovereign debate ${args.debate_id}. Read messages and answer through MCP if needed.`;
    const participants = Array.isArray(args.participant_node_ids) ? args.participant_node_ids : [];
    // No task id travels with a debate turn, so the bound here is governed-node membership rather
    // than task scope. Stated rather than silently weaker (see `deliverableNodeIds`).
    const recipients = scopedRecipients(io, "notify_debate_turn_recipients",
      participants.filter((nodeId) => nodeId !== identity.node_id), null);
    return { deliveries: await Promise.all(recipients
      .map((nodeId) => io.notifyNode(nodeId, prompt))) };
  }

  async function getWorkerStatus(identity, args = {}) {
    requireControlRole(identity, "conductor", "worker", "operator");
    const rows = io.liveWorkerRecords().map(io.operationalNodeStatus);
    if (args.node_id) return rows.filter((r) => r.node_id === args.node_id);
    const provider = normalizedProvider(args.provider);
    return provider ? rows.filter((r) => r.provider_id === provider) : rows;
  }

  return {
    handlers: {
      list_models: listModels, spawn_worker: spawnWorker, stop_worker: stopWorker,
      preflight_assignment: preflightAssignment, assign_task: assignTask,
      get_worker_status: getWorkerStatus,
      notify_message: notifyMessage, notify_debate: notifyDebate,
      notify_debate_turn: notifyDebateTurn,
    },
    deadlines,
  };
}

module.exports = {
  normalizedProvider,
  requireControlRole, taskPrompt, createDeadlineController, createApplicationControl,
};
