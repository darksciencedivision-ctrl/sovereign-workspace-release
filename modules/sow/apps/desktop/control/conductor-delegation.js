"use strict";
/**
 * The conductor delegates to a LOCAL pane and reads the answer back. EPC-03 L5-3/L5-4.
 *
 * The operator's ask, in his words:
 *
 *     "the conductor is absolutely supposed to be talking to those models and communicating with
 *      them, injecting their prompts, telling them what to do"
 *
 * WHY THIS EXISTS AND `assign_task` DOES NOT COVER IT. The existing assignment path writes a task
 * prompt into a pane and then WAITS for that worker to call `publish_candidate` over MCP. That is
 * correct for a frontier coding agent, which has the Sovereign MCP tools wired into it. A local
 * pane running `ollama run llama3.2:3b` is a bare REPL: it has no tools, it cannot call
 * `publish_candidate`, and it never will. Measured consequence — a local worker was assignable and
 * could never complete an assignment, because completion was defined as a call it cannot make.
 *
 * So the shell reads the answer off the pane and publishes it ON the pane's behalf. That is a
 * WEAKER form of evidence than a worker publishing through MCP, and the difference is carried in
 * the record rather than smoothed over: `self_published: false`, `source: "observed_pane_output"`.
 * A reviewer must be able to tell a candidate a node asserted from a candidate the shell read off
 * a screen, because only the first is the node's own claim.
 *
 * WHAT IT REUSES RATHER THAN REBUILDS:
 *   * the GATED write path (`pane-writer`) — every byte to a PTY passes the U328 modal gate, and
 *     a conductor's prompt is not exempt from a gate the operator's own voice is subject to;
 *   * the BOUNDED, REDACTED observation window (Layer 4) — the same one instrument, so what the
 *     conductor reads back is what the operator's surface reports it read;
 *   * the stream POSITION mark, so the answer is what the pane emitted AFTER the prompt. Reading
 *     the whole tail instead would let an earlier run's output satisfy this turn, which is exactly
 *     the defect `RingBuffer.sliceFrom` was built to close.
 *
 * WHAT IT DOES NOT DO. It does not make a worker leg live. `_assert_legs_honest` and
 * `build_acceptance_packet` remain the only things that may say a worker executed anything, and a
 * screen read is deliberately not routed into them here (L5-5). It does not retry a refused write:
 * a gate that refused is surfaced, never worked around.
 */
const { observePane } = require("./pane-observation");
const { flattenBody, withoutOwnEcho } = require("./pane-writer");

const DELEGATION_SCHEMA = "pane_delegation@1.0";

/** How long to let a local model answer before reading its screen, and how often to look.
 *  Bounded because a pane that never answers must produce an honest timeout rather than hold the
 *  conductor's turn open indefinitely. */
const DEFAULT_ANSWER_TIMEOUT_MS = 120_000;
const DEFAULT_POLL_MS = 1_000;
/** Output must be QUIET for this long before it is read as a finished answer. A local model
 *  streams tokens, so "the pane emitted something" is not "the pane is done". */
const DEFAULT_QUIET_MS = 3_000;

function delegationPrompt(task) {
  // Deliberately NOT `taskPrompt` from application-control. That prompt instructs the worker to
  // use `publish_progress`, `send_message` and `publish_candidate` — tools a local REPL does not
  // have. Sending it would tell a model to call things that do not exist, and a model told to
  // call a missing tool narrates calling it, which is the worst of both outcomes.
  return [
    `SOVEREIGN TASK ${task.task_id || "(unnamed)"}`,
    `Objective: ${task.objective || ""}`,
    task.constraints && task.constraints.length
      ? `Constraints: ${task.constraints.join("; ")}` : null,
    `Expected output: ${task.expected_output || "a concise, complete answer"}`,
    "Answer directly and completely in this terminal. Do not ask for confirmation.",
  ].filter(Boolean).join("\n");
}

/**
 * Delegate one task to one local pane and read the answer back.
 *
 * `io` supplies: `window` (the shared screen window), `writePrompt(paneId, body)` (the GATED
 * writer), `sleep(ms)`, and optionally `now()` and `log(message)`. Every one is injected so this
 * runs under `node --test` against the same functions the shell calls.
 *
 * Never throws. A delegation that fails produces a record saying how it failed; an exception here
 * would take the conductor's whole turn with it.
 */
async function delegateToPane(io, { paneId, nodeId, task, maxChars,
  timeoutMs = DEFAULT_ANSWER_TIMEOUT_MS, pollMs = DEFAULT_POLL_MS,
  quietMs = DEFAULT_QUIET_MS } = {}) {
  const now = io.now || (() => Date.now());
  const log = io.log || (() => {});
  const base = {
    schema: DELEGATION_SCHEMA, pane_id: paneId || null, node_id: nodeId || null,
    task_id: (task && task.task_id) || null,
    delivered: false, answered: false, refused: null, observation: null, candidate: null,
  };
  if (!paneId || !task) {
    return { ...base, reason: "a delegation needs a pane id and a task" };
  }

  // (1) The stream position BEFORE the prompt. Everything read later is bounded to what the pane
  //     emitted after this point, so an earlier run's answer cannot satisfy this turn.
  let mark = null;
  try {
    mark = io.window && typeof io.window.mark === "function" ? io.window.mark(paneId) : null;
  } catch {
    mark = null;
  }
  if (!Number.isInteger(mark)) {
    // A null mark makes every later read unbounded rather than exact. Refusing here is the same
    // fail-closed choice `createScreenWindow.mark` documents for its own callers.
    return { ...base, reason: "the pane has no readable stream position; a delegation that cannot "
      + "bound its read would accept an earlier answer as this one" };
  }

  // (2) The GATED write. A refusal is surfaced, never retried around.
  //
  // The body is flattened HERE so the echo exclusion below searches the screen for the bytes the
  // pane actually received. `pane-writer` flattens again at the boundary; flattening a flattened
  // body is a no-op, and looking for the UNflattened text would be searching for something never
  // written — the defect W-02 records against exactly this pairing.
  const body = flattenBody(delegationPrompt(task));
  let written = null;
  try {
    written = await io.writePrompt(paneId, body);
  } catch (err) {
    return { ...base, mark, reason: `pane write failed: ${err && err.message}` };
  }
  if (!written || written.written !== true) {
    const refusal = written && written.refused ? written.refused : null;
    log(`conductor delegation to ${paneId} was not delivered`
      + (refusal ? `: ${refusal.reason}` : ""));
    return {
      ...base, mark,
      refused: refusal ? { reason: refusal.reason, terminal_state: refusal.terminal_state || null }
        : null,
      residue_possible: !!(written && written.residue_possible),
      reason: refusal ? "the pane write gate refused this prompt"
        : "the pane did not accept the prompt",
    };
  }

  // (2a) OUR OWN ECHO IS NOT AN ANSWER.
  //
  // The pane echoes what we wrote. Without this, a pane that never answered at all still looked
  // answered — the delegation read its own prompt back and published it as the worker's candidate.
  // Found by the timeout test, which asserted `answered === false` for a silent pane and got true.
  //
  // `pane-writer.withoutOwnEcho` already solves this for the write gate, and is reused rather than
  // reimplemented: a second echo-exclusion would drift from the first, and then the gate and the
  // reader would disagree about what the pane said. Its documented fallback (U360) is passed a
  // logger here for the same reason it is there — a guard that degrades unobservably is the thing
  // this codebase keeps finding.
  const answerIn = (observation) => {
    if (!observation || observation.answerable !== true) return "";
    return withoutOwnEcho(observation.text, body,
      (why) => log(`conductor delegation echo-exclusion FELL BACK to exact matching for `
        + `${paneId}: ${why} (U360) — the pane's echo of our prompt may be read as its answer`))
      .trim();
  };

  // (3) Wait for the answer to SETTLE. A local model streams, so "output appeared" is not "the
  //     model is done" — the pane must go quiet before what is on it counts as an answer.
  const deadline = now() + timeoutMs;
  let lastAt = null;
  let lastLength = -1;
  let quietSince = null;
  while (now() < deadline) {
    await io.sleep(pollMs);
    const seen = observePane(io.window, paneId, { maxChars, notBefore: mark });
    // Measured on the ANSWER, not on the raw window: the echo arriving is not the model starting
    // to speak, and counting it as progress would restart the quiet timer for nothing.
    const length = seen.answerable === true ? answerIn(seen).length : -1;
    if (length !== lastLength) {
      lastLength = length;
      quietSince = now();
      lastAt = seen.at;
    } else if (length > 0 && quietSince !== null && now() - quietSince >= quietMs) {
      break;
    }
  }

  // (4) Read it back through the SAME bounded, redacted instrument the operator's surface uses.
  const observation = observePane(io.window, paneId, { maxChars, notBefore: mark });
  const answer = answerIn(observation);
  const answered = answer.length > 0;
  return {
    ...base,
    mark,
    at: lastAt,
    delivered: true,
    answered,
    observation,
    candidate: answered ? {
      node_id: nodeId || null,
      pane_id: paneId,
      task_id: task.task_id || null,
      content: answer,
      // The two fields that keep this honest. A candidate the shell READ is not a candidate the
      // node ASSERTED, and a reviewer must be able to tell them apart.
      self_published: false,
      source: "observed_pane_output",
      redactions: observation.redactions,
      redaction_kinds: observation.redaction_kinds,
      truncated: observation.truncated === true,
      note: "Read from the pane's own output because a local REPL holds no Sovereign MCP tools "
        + "and cannot call publish_candidate. Weaker evidence than a node's own publication, "
        + "and recorded as such.",
    } : null,
    reason: answered ? null
      : "the pane produced no readable output within the delegation window",
  };
}

module.exports = {
  DELEGATION_SCHEMA, DEFAULT_ANSWER_TIMEOUT_MS, DEFAULT_QUIET_MS,
  delegationPrompt, delegateToPane,
};
