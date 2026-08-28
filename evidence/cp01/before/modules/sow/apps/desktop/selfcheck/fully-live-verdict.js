"use strict";
/**
 * Phase 17E — what the fully-live assembled receipt is ALLOWED to claim.
 *
 * Kept out of the check itself, and pure, so `node --test` can falsify each rule without a window, a
 * supervisor or a live model. Every rule here exists because a green receipt could otherwise have
 * been produced by the wrong producer:
 *
 *   • `liveDispatchIsHonest` — the shell's ordinary launch dispatch is MOCK-first and shaped exactly
 *     like a live one. The only differences are the leg labels and the per-worker checkpoint, so those
 *     are what get read: a leg labelled `live` whose checkpoint was not executed / not spent / not
 *     VERIFIED (U45) is refused, and so is a feed that still records the live legs as OWED.
 *   • `approvalDrawerIsRealSessionEvents` — 17D found the drawer rendering three deterministic
 *     demonstration items through the real authority path. The discriminator is PROVENANCE, not the
 *     id: measured on this host, the event-sourced queue mints `ap-1` for the first real row too, so
 *     an id-based rule would have failed a genuine event (this receipt's first run did exactly that)
 *     and would pass a canned one the moment the fixture renumbered. What a demonstration item cannot
 *     have is a recorded event behind it — an event id, the channel that recorded it, and the feed
 *     schema that channel speaks. `demoIdsPresent` still REPORTS the collision, because a reader who
 *     sees `ap-1` deserves to be told the ids are not distinguishing.
 *   • `owedMarkersAreComplete` — an assembled receipt's most dangerous failure is silence about the
 *     legs it did not evidence, so every one of them must be named WITH its issue/decision reference.
 *
 * HONEST RESIDUAL (spec-audit F5, recorded rather than overstated): the OWED list is AUTHORED. This
 * rule enforces that every leg we KNOW is unevidenced is named with a reference a reader can look
 * up; it cannot discover a leg nobody wrote down. The check that reads it is named for what it
 * measures — `every_known_unevidenced_leg_is_named_with_its_reference` — and finding a missing leg
 * remains the reviewers' job, not this function's.
 */

/** The deterministic demonstration items (tests/support/demo_approval_queue.py) — never a real event. */
const DEMO_APPROVAL_IDS = Object.freeze(["ap-1", "ap-2", "ap-3"]);

/** Every leg the fully-live run cannot evidence for itself, each of which must be named. */
const REQUIRED_OWED_KEYS = Object.freeze([
  "spoken_microphone",          // the physical mic — the operator's own first use
  "physical_key_delivery",      // U69 — OS keydown into the focused xterm
  "conductor_initiated_dispatch", // U58 residual — the live CLI does not itself choose to dispatch
  "speech_out_tts",             // I-V2/D-VOICE-02 — no TTS is built
  "cloud_kimi_qwen",            // OP-10 16B — cloud-only models need a new provider authorization
  "diagnostic_ledger_scope",    // U111 — where this run's I-X3 count was measured, and its residual
  // U146 — the composition dropped a disclosure 17C's own receipt made, and the spec-auditor found it
  // (which is exactly the residual the header names). `audio_was_transcribed_then_discarded` is true
  // of OUR capture store; the delivered utterance still becomes durable text in the vendor CLI's own
  // session store, outside this workspace. A reader of this receipt alone must not conclude that
  // speaking to the shell leaves nothing behind.
  "vendor_session_store_retention",
]);

/** An OWED marker must cite something a reader can look up, not merely gesture at incompleteness. */
const OWED_REFERENCE = /(U\d{1,3}|OP-\d|I-V2|D-VOICE-02|§\s*\d|directive\s+§)/;

function nonEmpty(s) { return typeof s === "string" && s.trim().length > 0; }

/**
 * Is this dispatch feed evidence that a LIVE worker did the work?
 * @returns {{ok: boolean, reasons: string[], live_nodes: string[]}}
 */
function liveDispatchIsHonest(feed) {
  const reasons = [];
  if (!feed || typeof feed !== "object") {
    return { ok: false, reasons: ["no dispatch feed was parsed"], live_nodes: [] };
  }
  if (feed.schema !== "conductor_dispatch_feed@1.0") reasons.push(`unexpected feed schema ${JSON.stringify(feed.schema)}`);
  if (feed.dispatched !== true) reasons.push("the feed records no dispatch (dispatched !== true)");
  if (feed.by_descriptor !== true) reasons.push("routing was not by descriptor (invariant 4)");
  const legs = feed.legs || {};
  if (legs.workers !== "live") reasons.push(`legs.workers is ${JSON.stringify(legs.workers)}, not "live"`);
  const evidence = Array.isArray(feed.worker_evidence) ? feed.worker_evidence : [];
  const live = evidence.filter((row) => row && row.leg === "live");
  if (live.length === 0) reasons.push("no worker_evidence row carries a live leg");
  // `legs.workers: "live"` is a claim about the POOL, so a row that does not carry the label makes
  // the label an overstatement (gate-validator D4 — a mixed pool used to pass because only the rows
  // already claiming `live` were read). The honest label for a mixed pool is not `live`.
  for (const row of evidence) {
    if (!row || row.leg === "live") continue;
    reasons.push(`${row.node_id || "(unnamed node)"}: the pool is labelled live but this row's leg `
      + `is ${JSON.stringify(row && row.leg)}`);
  }
  for (const row of live) {
    const id = row.node_id || "(unnamed node)";
    if (row.executed !== true) reasons.push(`${id}: live leg claimed but executed !== true`);
    if (row.spent !== true) reasons.push(`${id}: live leg claimed but spent !== true`);
    if (row.verified !== true) reasons.push(`${id}: live leg claimed but the checkpoint is not verified (U45)`);
  }
  if (!(typeof feed.accepted_count === "number" && feed.accepted_count > 0)) {
    reasons.push("no artifact was ACCEPTED by the gate");
  }
  if (feed.acceptance_verdict !== "PASS") reasons.push(`acceptance verdict ${JSON.stringify(feed.acceptance_verdict)}, not PASS`);
  if (feed.operator_disposition !== "pending") {
    reasons.push(`operator_disposition ${JSON.stringify(feed.operator_disposition)} — a gate promotion is not operator acceptance (invariant 1)`);
  }
  if (!nonEmpty(feed.synthesized_by)) reasons.push("nothing synthesized the accepted set into a packet");
  const owed = feed.live_workers_owed || {};
  if (owed.owed !== false) reasons.push("live_workers_owed still records the live worker legs as owed (U58)");
  if (feed.torn_down !== true) reasons.push("torn_down !== true — the loopback MCP server outlived the dispatch (D-LOOP-1)");
  // A red leg must be diagnosable from the receipt alone. `accepted_count: 0` is produced by two
  // very different runs — the vendor CLI faulted before anything was published, or the artifact WAS
  // published and the STAGE gate refused it — and the first re-run of this composition hit one of
  // them with no way to tell which. The feed already carries the distinguishing fields; they are
  // read here so the reasons name what happened instead of only that nothing was accepted. Appended
  // only when something is already wrong: a green feed's reasons stay empty.
  if (reasons.length) reasons.push(...dispatchDiagnosis(feed));
  return { ok: reasons.length === 0, reasons, live_nodes: live.map((row) => row.node_id).filter(Boolean) };
}

/**
 * WHY a dispatch produced nothing, read from the feed's own failure fields. Attributed as the feed
 * attributes it: a node's words are the NODE's (invariants 11/18), the tally is the gate engine's.
 * @returns {string[]} zero or more diagnosis lines — never a verdict of its own.
 */
function dispatchDiagnosis(feed) {
  const out = [];
  const refusals = Array.isArray(feed && feed.node_refusals) ? feed.node_refusals : [];
  for (const r of refusals) {
    if (!r || typeof r !== "object") continue;
    const said = (Array.isArray(r.node_reported_reasons) ? r.node_reported_reasons : [])
      .map((x) => String(x)).filter((x) => x.trim().length);
    out.push(`the node itself refused ${JSON.stringify(r.task_id)}: `
      + `${r.node_id || "(unnamed node)"} reported ${said.length ? said.join(" | ") : "(no reason recorded)"}`);
  }
  const gs = feed && feed.gate_summary;
  if (gs && typeof gs === "object" && Number.isFinite(gs.stage_total) && gs.stage_total > 0) {
    out.push(`stage gate passed ${gs.stage_pass} of ${gs.stage_total} artifact(s); `
      + `plan gate ${JSON.stringify(gs.plan)}, acceptance ${JSON.stringify(gs.acceptance)}`);
  }
  if (Number.isFinite(feed && feed.failed_count) && feed.failed_count > 0) {
    out.push(`${feed.failed_count} task(s) failed in this dispatch`);
  }
  return out;
}

/** Which rows carry an id the demonstration trio also uses. REPORTED, never gating — see the header. */
function demoIdsPresent(model) {
  const rows = Array.isArray(model && model.rows) ? model.rows : [];
  return rows.map((row) => row && row.id).filter((id) => DEMO_APPROVAL_IDS.includes(id));
}

/**
 * Is the approval drawer showing THIS session's own events, and the one this run caused?
 * @param {object} model the drawer model as the renderer reads it
 * @param {object} [opts] `expectedChannel` — the channel that recorded the event this run caused
 * @returns {{ok: boolean, reasons: string[]}}
 */
function approvalDrawerIsRealSessionEvents(model, opts = {}) {
  const expectedChannel = opts.expectedChannel || "voice:capture";
  const reasons = [];
  if (!model || typeof model !== "object") return { ok: false, reasons: ["no approval model was read"] };
  if (model.source !== "session_events") {
    reasons.push(`drawer source ${JSON.stringify(model.source)} — not folded from this session's events (17D F2)`);
  }
  if (model.sourced !== true) reasons.push("the drawer feed was not sourced (a fail-closed empty view is not evidence)");
  if (!(typeof model.eventCount === "number" && model.eventCount > 0)) {
    reasons.push(`the drawer was folded from ${JSON.stringify(model.eventCount)} recorded events`);
  }
  const rows = Array.isArray(model.rows) ? model.rows : [];
  if (rows.length === 0) reasons.push("no row is pending — the run must CAUSE the event it approves");
  // ONLY means every row (gate-validator D1). The rule used to validate the first protected_action
  // and leave the rest unread, so the entire demonstration trio could render behind a genuine row
  // with the leg still green — 17D's F2 with one honest row in front of it. PROVENANCE (invariant
  // 11) is what a canned item has no way to carry: the recorded event behind it, and the channel
  // that recorded it. `unknown` is the fold's own default for an event that named no channel, so it
  // is not provenance either.
  for (const row of rows) {
    const id = (row && row.id) || "(unnamed row)";
    const d = (row && row.detail && typeof row.detail === "object") ? row.detail : {};
    if (!nonEmpty(d.event_id)) reasons.push(`row ${id}: no recorded event id behind it`);
    if (!nonEmpty(d.channel) || d.channel === "unknown") {
      reasons.push(`row ${id}: recorded on channel ${JSON.stringify(d.channel)} — not a channel`);
    }
    // A broker ref is provenance only for the kind that HAS one. `operator_surface` builds genuine
    // session-event rows for plan gates and clarifications with `ref: null` by design — requiring it
    // of every row made this rule refuse three of the real kinds and pass only the one this run
    // happens to cause (gate-validator m2 at 17E `.close`). The failure direction was safe; the name
    // was not. Event id + channel remain required of EVERY row, and those are what a canned item
    // cannot carry.
    if (row && row.kind === "protected_action" && !nonEmpty(row.ref)) {
      reasons.push(`row ${id}: a protected action with no broker queue reference`);
    }
  }
  const queued = rows.find((row) => row && row.kind === "protected_action");
  if (!queued) {
    reasons.push("no protected_action row — the queued proposal this run caused is absent");
    return { ok: false, reasons };
  }
  const detail = (queued.detail && typeof queued.detail === "object") ? queued.detail : {};
  if (detail.channel !== expectedChannel) {
    reasons.push(`row ${queued.id}: recorded on channel ${JSON.stringify(detail.channel)}, not ${JSON.stringify(expectedChannel)}`);
  }
  if (!nonEmpty(detail.feed_schema)) reasons.push(`row ${queued.id}: the recording channel names no feed schema`);
  return { ok: reasons.length === 0, reasons };
}

/**
 * Were two live frontier terminals held at once, WITHIN one subscription's allowance?
 *
 * The policy constant does not live here: `live_authorization` explicitly permits an operator config
 * that narrows the allowance to 1, and the old check asserted `allowance === 2`, so that legitimate
 * configuration went red for a reason that is not a defect (spec-audit F13). What the leg claims is
 * that TWO terminals were counted at once and that the governor's cap contained them.
 * @returns {{ok: boolean, reasons: string[]}}
 */
function twoTerminalsOnOneAllowance(concurrency) {
  const reasons = [];
  const c = concurrency && typeof concurrency === "object" ? concurrency : {};
  const allowance = c.allowance;
  const observed = c.max_in_use_observed;
  if (!(typeof allowance === "number" && allowance >= 2)) {
    reasons.push(`allowance ${JSON.stringify(allowance)} — two terminals at once is not something `
      + `this host's governor permits, so this run cannot evidence the leg`);
  }
  if (typeof allowance === "number" && typeof observed === "number" && observed > allowance) {
    reasons.push(`${observed} terminals exceed the allowance of ${allowance} — that is a governor `
      + `failure, not evidence for it`);
  } else if (observed !== 2) {
    reasons.push(`the ledger was sampled at a maximum of ${JSON.stringify(observed)} terminals in `
      + `use — two were not observed held at the same time`);
  }
  return { ok: reasons.length === 0, reasons };
}

/**
 * Does the OWED block name every leg the run did not evidence, each with a reference?
 * @returns {{ok: boolean, reasons: string[]}}
 */
function owedMarkersAreComplete(owed) {
  const reasons = [];
  const block = owed && typeof owed === "object" ? owed : {};
  for (const key of REQUIRED_OWED_KEYS) {
    const value = block[key];
    if (!nonEmpty(value)) {
      reasons.push(`${key}: no OWED marker`);
      continue;
    }
    if (!OWED_REFERENCE.test(value)) {
      reasons.push(`${key}: the marker cites no issue/decision a reader can look up`);
    }
  }
  return { ok: reasons.length === 0, reasons };
}

/**
 * Fold the check set into the receipt verdict. A non-boolean is a FAILURE, never truthy: a check that
 * recorded a string or a number did not measure what its name says.
 * @returns {{ok: boolean, failed: string[]}}
 */
function composeVerdict(checks) {
  const entries = Object.entries(checks && typeof checks === "object" ? checks : {});
  if (entries.length === 0) return { ok: false, failed: ["no_checks_were_recorded"] };
  const failed = entries.filter(([, v]) => v !== true).map(([k]) => k);
  return { ok: failed.length === 0, failed };
}

module.exports = {
  DEMO_APPROVAL_IDS,
  REQUIRED_OWED_KEYS,
  liveDispatchIsHonest,
  dispatchDiagnosis,
  approvalDrawerIsRealSessionEvents,
  demoIdsPresent,
  owedMarkersAreComplete,
  twoTerminalsOnOneAllowance,
  composeVerdict,
};
