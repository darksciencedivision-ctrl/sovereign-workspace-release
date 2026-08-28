"use strict";
/**
 * The session's own approval events, append-only — Phase 17D `.events` (OP-11 §16, finding F2).
 *
 * The operator opened the shipped shell and found three pending approvals waiting for them that no
 * session had produced: Phase 16D's demonstration trio, rebuilt on every fetch. The drawer now shows
 * exactly what THIS run produced, and this module is the record it is folded from.
 *
 * WHAT GOES IN, AND WHAT DOES NOT. Only facts a governed Python producer already reported back to the
 * shell:
 *   - `recordUtterance(voiceFeed)` — a `conductor_voice_feed@1.0` whose bridge outcome was
 *     `proposed_action` (a protected/destructive verb the CommandBroker queued) or `clarify` (an
 *     utterance the bridge would not route). The transcript, its surface and its STT confidence are
 *     recorded verbatim; the CLASSIFICATION is recorded as a claim, not as a conclusion.
 *   - `recordDispatchPlan(dispatchFeed)` — a `conductor_dispatch_feed@1.0` whose governed dispatch
 *     decomposed an objective and had the real gate engine judge the plan. The `gate@1.0` record is
 *     carried verbatim.
 * A CHAT utterance records nothing (it went to the conductor, there is nothing to approve), and a
 * feed that is not `sourced` records nothing (an unavailable feed is not an event).
 *
 * THE SHELL DOES NOT GET TO SAY WHAT AN EVENT MEANS. Everything that decides how a row appears —
 * whether it is a protected action or a question, whether a plan may be approved — is re-derived
 * from these records by the real classifiers in `control_plane/orchestration/session_approvals.py`
 * (the same CommandBroker/router that decided it live, the same gate-derived approvability). A
 * recorded classification that no longer matches fails the whole feed closed. This module therefore
 * writes evidence, not verdicts; that is what keeps invariant 29 (never trust the harness) true of a
 * file the harness writes.
 *
 * THE LOG IS PER RUN. It is truncated at startup, deliberately: a pending row refers to a broker
 * classification and a session that do not survive the process, so carrying rows across a restart
 * would put items in the drawer that no longer correspond to anything — the F2 shape again, one
 * restart later. Recovery of a genuinely pending approval across restarts needs the durable queue
 * that is recorded as owed, not a stale file.
 *
 * It lives OUTSIDE version control (`apps/desktop/.approvals/`, gitignored) and is capped: it holds
 * the operator's transcripts, and it is diagnostic state, not the canonical record (invariant 12 —
 * the append-only history is MCP's). RETENTION, stated rather than implied: transcripts (never audio
 * — invariant 26 is the capture store's, and it deletes) survive on disk from the moment they are
 * written until the NEXT launch truncates the file. There is no TTL and no disposal at quit, which is
 * the same "the purge only runs when they next use the feature" gap the capture store already fixed
 * for audio. Recorded as owed (U208), not papered over.
 */
const fs = require("fs");
const path = require("path");

const SESSION_APPROVAL_EVENT_SCHEMA = "session_approval_event@1.0";
const DEFAULT_LOG_PATH = path.join(__dirname, "..", ".approvals", "session-events.jsonl");
// The bound exists so an unattended shell cannot grow this file without limit. It is generous
// relative to a session's real approval traffic; when it trips we say so in the log rather than
// silently dropping the operator's oldest pending item.
const DEFAULT_MAX_EVENTS = 500;

const UTTERANCE_KINDS = new Set(["proposed_action", "clarify"]);

function isPlainObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

class SessionApprovalLog {
  /**
   * @param {object} opts {logPath?, maxEvents?, log?, now?}
   */
  constructor(opts = {}) {
    this.logPath = opts.logPath || DEFAULT_LOG_PATH;
    this.maxEvents = Number.isFinite(opts.maxEvents) ? opts.maxEvents : DEFAULT_MAX_EVENTS;
    this._log = typeof opts.log === "function" ? opts.log : () => {};
    this._now = typeof opts.now === "function" ? opts.now : () => new Date().toISOString();
    this._seq = 0;
    this._dropped = 0;
  }

  path() { return this.logPath; }
  count() { return this._seq; }
  dropped() { return this._dropped; }

  /** Start a fresh session log (truncate). Never throws into launch — a log we cannot write means an
   * empty drawer, which is the fail-closed direction. */
  begin() {
    this._seq = 0;
    this._dropped = 0;
    try {
      fs.mkdirSync(path.dirname(this.logPath), { recursive: true });
      fs.writeFileSync(this.logPath, "");
      return true;
    } catch (e) {
      this._log(`approvals: could not start the session-approval log (drawer stays empty): ${e && e.message}`);
      return false;
    }
  }

  /** Append one already-built event record. Returns the record, or null if it was not written. */
  append(record) {
    if (!isPlainObject(record)) return null;
    if (this._seq >= this.maxEvents) {
      if (this._dropped === 0) {
        this._log(`approvals: session-approval log reached its ${this.maxEvents}-event cap — further `
          + "events are NOT recorded (the drawer shows what fits, and says so)");
      }
      this._dropped += 1;
      return null;
    }
    this._seq += 1;
    const full = {
      schema: SESSION_APPROVAL_EVENT_SCHEMA,
      event_id: `ev-${this._seq}`,
      at: this._now(),
      ...record,
    };
    try {
      fs.appendFileSync(this.logPath, JSON.stringify(full) + "\n");
      return full;
    } catch (e) {
      this._seq -= 1;
      this._log(`approvals: could not record a session approval event: ${e && e.message}`);
      return null;
    }
  }

  /**
   * Record a voice/typed utterance the governed bridge did NOT deliver as chat. Returns the record,
   * or null when there is nothing for the operator to decide.
   * @param {object} feed a `conductor_voice_feed@1.0`
   * @param {object} opts {channel?}
   */
  recordUtterance(feed, opts = {}) {
    if (!isPlainObject(feed) || feed.sourced !== true) return null;
    const outcome = isPlainObject(feed.outcome) ? feed.outcome : null;
    if (!outcome || !UTTERANCE_KINDS.has(outcome.kind)) return null;   // chat ⇒ nothing to approve
    const text = typeof outcome.text === "string" ? outcome.text : "";
    if (!text.trim()) return null;   // an empty transcript is not an event (the builder refuses it)
    const source = outcome.source === "voice" || outcome.source === "typed" ? outcome.source : null;
    if (!source) return null;
    return this.append({
      kind: "utterance",
      utterance: {
        text,
        source,
        confidence: typeof outcome.confidence === "number" ? outcome.confidence : null,
        // the classification the governed feed reported — a CLAIM the Python builder re-derives
        classified_as: outcome.kind,
      },
      provenance: {
        channel: opts.channel || "voice:capture",
        feed_schema: typeof feed.schema === "string" ? feed.schema : null,
      },
    });
  }

  /**
   * Record a governed dispatch's decomposed plan + its real gate verdict — a gate promotion the
   * operator has not disposed of. Returns the record, or null if the feed carries no gated plan.
   *
   * `opts.operatorObjective` must be TRUE, and that is the whole point of the flag. The shell also
   * runs a governed dispatch at launch to demonstrate the dispatch machinery, over the emitter's own
   * fixed smoke objective. Surfacing THAT as a pending approval would put a plan nobody asked for in
   * the drawer on every launch — finding F2 again, one layer down. Only a plan the conductor
   * decomposed from an objective the OPERATOR gave belongs here.
   *
   * @param {object} feed a `conductor_dispatch_feed@1.0`
   * @param {object} opts {channel?, operatorObjective}
   */
  recordDispatchPlan(feed, opts = {}) {
    if (!isPlainObject(feed)) return null;
    if (opts.operatorObjective !== true) return null;
    const plan = isPlainObject(feed.plan) ? feed.plan : null;
    if (!plan) return null;
    const gate = isPlainObject(plan.plan_gate) ? plan.plan_gate : null;
    // No gate record ⇒ no plan was judged ⇒ nothing to surface. The builder would refuse it anyway;
    // refusing here keeps a normal "nothing dispatched" launch from failing the whole drawer closed.
    if (!gate || typeof gate.verdict !== "string") return null;
    if (typeof plan.objective !== "string" || !plan.objective.trim()) return null;
    return this.append({
      kind: "plan",
      plan: {
        objective: plan.objective,
        tasks: Array.isArray(plan.tasks) ? plan.tasks : [],
        refused: Array.isArray(plan.refused) ? plan.refused : [],
        plan_gate: gate,
        plan_blocked: plan.plan_blocked === true,
      },
      provenance: {
        channel: opts.channel || "conductor:dispatch",
        feed_schema: typeof feed.schema === "string" ? feed.schema : null,
        operator_originated: true,
      },
    });
  }

  /**
   * Persist a decision the GOVERNED authority already made. The event is the one Python minted on the
   * resolve (`decision_event` on the decision feed): on THIS path the shell authors no decision record
   * of its own, so an honest shell cannot record an approval the authority did not grant.
   *
   * W-43 (U206) makes that a property of the FILE and not only of this code path: the authority now
   * stamps the decision record it mints, and the drawer builder refuses any decision without a valid
   * stamp. This method therefore carries `producer` and `authenticity` through UNCHANGED. They are
   * copied explicitly, like every other field, rather than by spreading `d` — the explicit copy is
   * what stops a caller smuggling extra fields into a record the verifier signs over, and a field
   * added to the record later must be added here deliberately or the stamp will not verify, which
   * fails CLOSED and loudly. Anything malformed is refused here, as before.
   */
  recordGovernedDecision(decisionEvent) {
    if (!isPlainObject(decisionEvent)) return null;
    if (decisionEvent.schema !== SESSION_APPROVAL_EVENT_SCHEMA) return null;
    if (decisionEvent.kind !== "decision" || !isPlainObject(decisionEvent.decision)) return null;
    const d = decisionEvent.decision;
    if (typeof d.item_id !== "string" || !d.item_id) return null;
    if (d.decision !== "approve" && d.decision !== "reject") return null;
    // The shell does not judge the stamp — it cannot, it holds no key — but a decision arriving here
    // without one can only be an unstamped forgery or a producer that failed to mint, and recording
    // it would put a row in the log that the builder will refuse and fail the whole drawer closed.
    if (typeof d.producer !== "string" || !d.producer) return null;
    if (typeof d.authenticity !== "string" || !d.authenticity) return null;
    return this.append({
      kind: "decision",
      decision: {
        item_id: d.item_id,
        decision: d.decision,
        reason: typeof d.reason === "string" ? d.reason : "",
        operator_role: typeof d.operator_role === "string" ? d.operator_role : "",
        producer: d.producer,
        authenticity: d.authenticity,
      },
      provenance: isPlainObject(decisionEvent.provenance)
        ? decisionEvent.provenance
        : { channel: "approvals:decide" },
    });
  }
}

module.exports = {
  SessionApprovalLog,
  SESSION_APPROVAL_EVENT_SCHEMA,
  DEFAULT_LOG_PATH,
  DEFAULT_MAX_EVENTS,
};
