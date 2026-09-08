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
const { composeOwnDigest, paneNumber, SOURCE, trimPaneChrome } = require("./workspace-journal");
const { characterBudget, resolveTerminalRefs } = require("./conductor-view");

const DELEGATION_SCHEMA = "pane_delegation@1.0";

/** How long to let a local model answer before reading its screen, and how often to look.
 *  Bounded because a pane that never answers must produce an honest timeout rather than hold the
 *  conductor's turn open indefinitely. */
const DEFAULT_ANSWER_TIMEOUT_MS = 120_000;
const DEFAULT_POLL_MS = 1_000;
/** Output must be QUIET for this long before it is read as a finished answer. A local model
 *  streams tokens, so "the pane emitted something" is not "the pane is done". */
const DEFAULT_QUIET_MS = 3_000;

/** SW-CONDUCTOR-001 contract 5: the one-line delivery-position statement. A worker handed
 *  "terminal 2, redo yours as a list" had no way until now to know it is not terminal 2, so it
 *  guessed. Every recipient of an objective is told which terminal it is and how many terminals
 *  received the same objective — enough to tell a broadcast from a message meant for it alone.
 *  `audience` comes from the selection receipt (audienceFor, below); with no audience the prompt
 *  is byte-for-byte what it was before addressing existed. */
function audienceLine(audience) {
  if (!audience || !audience.pane_id) return null;
  const count = Number.isSafeInteger(audience.recipient_count) ? audience.recipient_count : null;
  if (count === null || count < 1) return null;
  const me = audience.pane_number ? "terminal #" + audience.pane_number : String(audience.pane_id);
  if (audience.addressed === true) {
    return count === 1
      ? `Delivery: addressed to ${me} alone — you are the only recipient of this objective.`
      : `Delivery: addressed — this objective named its recipients; ${count} received it and you are ${me}.`;
  }
  return `Delivery: broadcast — every live terminal received this objective (${count} recipients); you are ${me}.`;
}

function delegationPrompt(task, audience = null) {
  // Deliberately NOT `taskPrompt` from application-control. That prompt instructs the worker to
  // use `publish_progress`, `send_message` and `publish_candidate` — tools a local REPL does not
  // have. Sending it would tell a model to call things that do not exist, and a model told to
  // call a missing tool narrates calling it, which is the worst of both outcomes.
  const digest = typeof task.memory_digest === "string" && task.memory_digest.trim()
    ? task.memory_digest.trim() + "\n\n" : "";
  return [
    digest + `SOVEREIGN TASK ${task.task_id || "(unnamed)"}`,
    audienceLine(audience),
    `Objective: ${task.objective || ""}`,
    task.constraints && task.constraints.length
      ? `Constraints: ${task.constraints.join("; ")}` : null,
    `Expected output: ${task.expected_output || "a concise, complete answer"}`,
    "Answer directly and completely in this terminal. Do not ask for confirmation.",
  ].filter(Boolean).join("\n");
}

/** SW-CONDUCTOR-001 contracts 5+7: the position line needs to know how many terminals an
 *  objective went to and whether it was addressed or broadcast. Selection knows that; the prompt
 *  builder does not, and Phase 1's main.js budget is ONE call-site change (contract 7), so no
 *  task field, no options field and no new IPC can carry it. The receipt is that channel:
 *  selection records the audience per objective text, and delegation reads it back per pane.
 *  Keys are trimmed objective texts; the map is capped and evicts oldest-first. Two objectives in
 *  flight at once have distinct keys. A delegation whose objective never went through selection
 *  (direct delegateToPane calls, startup flows, other modules' tests) finds no receipt and gets
 *  exactly the pre-addressing prompt. The receipt is a projection for one prompt line, never
 *  authority for delivery: who received what is what selectObjectiveRecipientsFor returned and
 *  what the write gate's journal rows record. */
const AUDIENCE_RECEIPTS_MAX = 32;
const audienceReceipts = new Map();
function recordAudience(objectiveText, addressed, recipients) {
  const key = typeof objectiveText === "string" ? objectiveText.trim() : "";
  if (!key) return; // a selection with no objective text (the two-argument F-36 form) leaves no state at all
  if (!audienceReceipts.has(key) && audienceReceipts.size >= AUDIENCE_RECEIPTS_MAX) {
    const oldest = audienceReceipts.keys().next();
    if (!oldest.done) audienceReceipts.delete(oldest.value);
  }
  audienceReceipts.set(key, {
    addressed: addressed === true,
    recipient_count: recipients.length,
    panes: recipients.map((r) => ({ pane_id: r.pane_id, pane_number: r.pane_number })),
  });
}
function audienceFor(objectiveText, paneId) {
  const key = typeof objectiveText === "string" ? objectiveText.trim() : "";
  if (!key || !paneId) return null;
  const receipt = audienceReceipts.get(key);
  if (!receipt) return null;
  const pane = receipt.panes.find((p) => p.pane_id === paneId);
  if (!pane) return null;
  return { pane_id: pane.pane_id, pane_number: pane.pane_number,
    recipient_count: receipt.recipient_count, addressed: receipt.addressed };
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
async function delegateToPaneObserved(io, { paneId, nodeId, task, maxChars,
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
  const body = flattenBody(delegationPrompt(task, audienceFor(task.objective, paneId)));
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
    // SW-JOURNAL-002-A3 F-46b/c: terminal chrome the pane drew ITSELF — spinner runs and the
    // REPL's own idle line — is removed and counted BEFORE the echo exclusion (U360) runs, so
    // a spinner-only pane correctly reads as NO ANSWER instead of a blob of braille frames.
    const chrome = trimPaneChrome(observation.text, { writtenPrompt: body });
    return withoutOwnEcho(chrome.text, body,
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
  // SW-JOURNAL-002-A3 F-46b/c: declare what the chrome trim removed from this capture, so the
  // journal entry carries the counts the way it already carries redactions. Recomputing here
  // is safe and honest: trimPaneChrome is deterministic over the same inputs.
  const chrome = observation && observation.answerable === true
    ? trimPaneChrome(observation.text, { writtenPrompt: body }) : null;
  return {
    ...base,
    mark,
    at: lastAt,
    delivered: true,
    answered,
    observation,
    chrome: chrome ? { spinner_chars: chrome.spinner_chars, idle_lines: chrome.idle_lines,
      echoed_prefix_chars: chrome.echoed_prefix_chars, removed_chars: chrome.removed_chars,
      chrome_kinds: chrome.chrome_kinds } : null,
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

/** Recording is additive: the same write gate, mark, echo exclusion and settle loop run above. */
async function delegateToPane(io, options = {}) {
  const { journalFor } = require("./journal-runtime");
  let journal = null, journalError = null;
  try { journal = journalFor(io); } catch { journalError = "journal unavailable"; }
  const task = { ...(options.task || {}) };
  if (journal && options.paneId && options.task) {
    try {
      const profile = options.workerProfile || (journal.workerBudget
        ? await journal.workerBudget(options.paneId) : null);
      const prior = journal.privateEntries
        ? await journal.privateEntries(options.nodeId) : [];
      task.memory_digest = composeOwnDigest(prior, {
        budgetChars: characterBudget(profile), nodeId: options.nodeId,
      }).text;
    } catch {
      task.memory_digest = composeOwnDigest([], {
        nodeId: options.nodeId, absence: "store unavailable",
      }).text;
    }
  }
  const base = { node_id: options.nodeId || "(not reported)",
    pane_id: options.paneId || "(not reported)",
    model: options.model || (journal && journal.modelFor && journal.modelFor(options.paneId))
      || "(not reported)",
    task_id: task.task_id || "", objective: task.objective || "",
    self_published: false, source: "observed_pane_output" };
  const record = async (fields) => {
    if (!journal) return;
    try { await journal.record({ ...base, ...fields }); }
    catch { journalError = "journal unavailable: this observation was not fully persisted/projected"; }
    if (journal.recordPrivate) {
      try { await journal.recordPrivate({ ...base, ...fields }); }
      catch { journalError = journalError || "private node memory unavailable: this observation was not fully persisted/projected"; }
    }
  };
  // SW-JOURNAL-002-A3 F-46e: each fact recorded ONCE. The prompt has not been written yet, so
  // this row must not carry a copy of it — the objective and the task id are already on `base`
  // and ride every record. The prompt itself is recorded by prompt_written below: that row
  // exists precisely to say what was written.
  await record({ status: "delegation_requested", prompt: "" });
  const observedIO = { ...io, writePrompt: async (paneId, body) => {
    const written = await io.writePrompt(paneId, body);
    await record({ status: written && written.written === true ? "prompt_written" : "write_refused",
      prompt: body, reason: written && written.written === true ? ""
        : written && written.refused ? written.refused.reason : "the pane did not accept the prompt" });
    return written;
  } };
  const result = await delegateToPaneObserved(observedIO, { ...options, task });
  const obs = result.observation || {};
  await record({ status: result.answered ? "answered" : result.refused ? "write_refused"
      : result.delivered ? "unreadable" : "not_delivered",
    // SW-JOURNAL-002-A3 F-46e: the answered row records the ANSWER. The prompt lives on
    // prompt_written (or on write_refused, for a refused write); this was a third copy of it.
    prompt: "",
    answer: result.candidate ? result.candidate.content : "",
    reason: result.refused ? result.refused.reason : result.reason || "",
    redactions: obs.redactions || 0, redaction_kinds: obs.redaction_kinds || [],
    truncated: obs.truncated === true,
    // SW-JOURNAL-002-A3 F-46b/c: the chrome trimming that shaped this answer is declared here.
    chrome_removed: result.chrome ? result.chrome.removed_chars : 0,
    chrome_kinds: result.chrome ? result.chrome.chrome_kinds : [] });
  if (journalError) {
    (io.log || (() => {}))(journalError);
    return { ...result, journal_error: journalError };
  }
  return result;
}

/**
 * SW-CONDUCTOR-001: recipient selection gains an optional third argument, the objective text.
 * An objective that names terminals delivers only to the named live ones (contracts 2–4); an
 * objective that names none broadcasts to every live worker exactly as before (contract 1, the
 * operator's F-36 ruling, unreversed). A two-argument call behaves exactly as it always has and
 * leaves no state behind.
 *
 * THE DECLARED SIGNATURE STAYS TWO-PARAMETER ON PURPOSE, with the objective read from
 * `arguments`: the protected F-36 mutation-control test
 * (test/broadcast-delegation.test.js, "F-36 mutation control: restoring assignment-list
 * selection…") compiles its mutant by string-replacing this exact declaration line, character
 * for character from the `function` keyword through the opening brace. The line is deliberately
 * NOT quoted anywhere in this comment: a comment copy would be the replacement's FIRST
 * occurrence and the mutant would be swallowed into the comment block (measured, 2026-09-07 —
 * the protected test reported 2 !== 1 until the quoted copy was removed). Rewriting the
 * declaration into an explicit three-parameter form would silently no-op that replacement
 * instead, the "mutant" would become the shipped module itself, and the protected test would
 * fail against a third-argument call it was never meant to make. Keeping the declaration
 * byte-identical lets the mutant compile as intended and keeps both protected F-36 tests green
 * and unedited. The contractual three-parameter signature — additive, broadcast default — lives
 * one function down, where nothing is anchored to it.
 */
function selectObjectiveRecipients(liveRecords, registeredRecords = []) {
  return selectObjectiveRecipientsFor(liveRecords, registeredRecords,
    arguments.length > 2 ? arguments[2] : "");
}

/** Contract 6's signature: `selectObjectiveRecipientsFor(liveRecords, registeredRecords = [],
 *  objective = "")` — additive third parameter, broadcast default. */
function selectObjectiveRecipientsFor(liveRecords, registeredRecords = [], objective = "") {
  const recipients = [];
  const seen = new Set();
  for (const rec of liveRecords || []) {
    if (!rec || !rec.nodeId || !rec.paneId || seen.has(rec.paneId)) continue;
    seen.add(rec.paneId);
    recipients.push({
      node_id: rec.nodeId, pane_id: rec.paneId,
      role: rec.role || (rec.chrome && rec.chrome.role) || "",
      pane_number: paneNumber(rec.paneId),
    });
  }
  const skipped = [];
  for (const rec of registeredRecords || []) {
    if (!rec || !rec.nodeId) continue;
    if (recipients.some(row => row.node_id === rec.nodeId)) continue;
    skipped.push({
      node_id: rec.nodeId, pane_id: rec.paneId || null, delivered: false, answered: false,
      reason: "no live pane is registered for this assignment",
      pane_number: paneNumber(rec.paneId),
    });
  }

  const text = typeof objective === "string" ? objective.trim() : "";
  if (!text) return { recipients, skipped, notices: [] };

  // ---- addressing (SW-CONDUCTOR-001 contracts 1–4) ----
  // The parser is conductor-view's resolveTerminalRefs — deliberately the SAME one the read path
  // resolves operator prose with; no second parser exists. Its grammar is its own: a phrase it
  // does not match ("the third one", a bare "and 3") attempts no addressing, and the F-36
  // broadcast stands. Open panes are the live worker records plus every registered record holding
  // a pane id; a registered-but-not-live pane is open and not live, which is exactly the
  // distinction resolveTerminalRefs's two notices draw.
  const openPanes = [];
  for (const rec of liveRecords || []) {
    if (rec && rec.paneId) openPanes.push({ pane_id: rec.paneId, node_id: rec.nodeId || null, live: true });
  }
  for (const rec of registeredRecords || []) {
    if (rec && rec.paneId && !openPanes.some((p) => p.pane_id === rec.paneId))
      openPanes.push({ pane_id: rec.paneId, node_id: rec.nodeId || null, live: false });
  }
  const resolved = resolveTerminalRefs(text, openPanes);
  if (!resolved.attempted) {
    // Contract 1: an objective naming no terminal reaches every live worker, exactly as today.
    recordAudience(text, false, recipients);
    return { recipients, skipped, notices: [] };
  }
  // Contract 2: naming terminals narrows the delegation to those terminals. resolveTerminalRefs
  // resolves a pane to BOTH its pane id and its node id, so either identifies a recipient row.
  const named = new Set(resolved.ids);
  const addressed = recipients.filter((r) => named.has(r.pane_id) || named.has(r.node_id));
  // Contract 3: the parser's own notices carry through to the operator. They ride `skipped` rows
  // because main.js already folds skipped rows into the delegations it returns — the only
  // operator-facing channel the one-line Phase-1 budget allows. Each row is enriched with the
  // open-pane record its notice is about, when there is one.
  const notices = resolved.notices.slice();
  const numFromNotice = (reason) => (String(reason).match(/terminal (\d+)/) || [, ""])[1];
  const addressedSkipped = notices.map((reason) => {
    const pane = openPanes.find((p) => paneNumber(p.pane_id) === numFromNotice(reason)) || null;
    return { node_id: pane ? pane.node_id : null, pane_id: pane ? pane.pane_id : null,
      delivered: false, answered: false, reason, pane_number: numFromNotice(reason) };
  });
  if (!addressed.length) {
    // Contract 4: deliver to none and say so. A named-terminal miss NEVER falls back to
    // broadcast — the operator addressed someone specific, and delivering to everyone instead
    // is the worst outcome available.
    const say = "every terminal named by this objective is unreachable; it was delivered to no one"
      + " (a named terminal that cannot be reached never falls back to a broadcast)";
    notices.push(say);
    addressedSkipped.push({ node_id: null, pane_id: null, delivered: false, answered: false,
      reason: say, pane_number: "" });
  }
  // Registered records that were NOT addressed get no skipped rows in addressed mode: they were
  // never candidates, and a "no live pane" row for each would be noise beside the addressed miss.
  recordAudience(text, true, addressed);
  return { recipients: addressed, skipped: addressedSkipped, notices };
}

module.exports = {
  DELEGATION_SCHEMA, DEFAULT_ANSWER_TIMEOUT_MS, DEFAULT_QUIET_MS,
  delegationPrompt, delegateToPane, selectObjectiveRecipients, selectObjectiveRecipientsFor,
  audienceFor, paneNumber, SOURCE,
};
