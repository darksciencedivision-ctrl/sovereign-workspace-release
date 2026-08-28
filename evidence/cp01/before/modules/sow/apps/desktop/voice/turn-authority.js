"use strict";
/**
 * Supervisor-process authority for direct voice CHAT turns.
 *
 * The attended vendor CLI remains untrusted. Its configured hook is a transport: every relevant
 * hook event is sent to this long-lived Electron main-process service over an authenticated
 * loopback socket. Turn state and every allow/deny/disarm decision live here. If this service is
 * absent, the transport returns a blocking hook result instead of guessing.
 *
 * The capability token is ephemeral, generated in memory for one shell process, and passed only to
 * its supervised child environment. It is not a provider credential and is never persisted or
 * included in receipts/logs. The boundary still depends on the first-party CLI honoring its pinned
 * hook contract; OS-level confinement of the vendor process remains the separately recorded U25.
 */
const crypto = require("node:crypto");
const net = require("node:net");

const REQUEST_SCHEMA = "voice_turn_authority_request@1.0";
const RESPONSE_SCHEMA = "voice_turn_authority_response@1.0";
const BOUNDARY_SCHEMA = "voice_turn_boundary@1.0";
const BROKER_SCHEMA = "supervisor_voice_turn_authority@1.0";
const TURN_STATE_SCHEMA = "supervisor_voice_turn_state@1.0";
const DEFAULT_STOP_TIMEOUT_MS = 5000;

/**
 * WHAT ENDS AN ADMITTED VOICE TURN (`.disarm`, U166).
 *
 * The restriction used to have no end at all: `_active` cleared only when SessionManager observed the
 * OS process exit. So the FIRST spoken utterance of a session blocked the operator's own typed
 * prompts and denied every tool for the rest of it — the opposite of directive §13 item 2, where
 * typing and speaking reach the SAME live session.
 *
 * The bound cannot come from the supervised child: it holds the transport bearer, so anything it can
 * SAY (`Stop`/`SessionEnd`, an unmarked `UserPromptSubmit`) is forgeable and stays an observation.
 * It cannot be a plain deadline either — a deadline hands authority back for the mere passage of
 * time, which a child need only WAIT OUT to escape the restriction it was placed under.
 *
 * So the window is bounded by the OPERATOR, on signals Electron main measures for itself, and the
 * property this buys is stated exactly: everything the CLI does between an admitted spoken prompt
 * and the operator's next keyboard action is treated as voice-originated and non-executing. Taking
 * the keyboard back is an act of operator authority (invariant 1) that the vendor process cannot
 * SYNTHESISE through any channel this shell gives it — not the hook transport, not its own
 * lifecycle, not the pane it prints into.
 *
 * WHAT THAT CLAIM IS NARROWED TO (U184). It cannot synthesise the keystroke; it CAN elicit one,
 * because it controls what the pane displays and can print "Press Enter to continue". That is the
 * same elicitation argument used below to refuse `pane:input`, one level down, and dropping it here
 * would overstate the mechanism — the property is that the operator's hand is in the loop, not that
 * the child has no influence over when it moves.
 *
 * WHAT THE KEYSTROKE DOES NOT DO (U178). It gives the OPERATOR their keyboard back; it does not give
 * the in-flight spoken turn an execution capability. The model is frequently still generating the
 * answer to the spoken prompt when the operator types, and clearing the restriction outright meant
 * that answer's tool calls stopped being denied — I-V3 / invariant 25 negated by the fix for U166.
 * So a disarmed ACTIVE turn moves to a terminal `ended` state that keeps denying `PreToolUse` and
 * `PermissionRequest` for that turn id, and the denial is lifted by the operator's NEXT PROMPT (or
 * the observed process exit). The forgery direction is the safe one: a child that fabricated a
 * `UserPromptSubmit` to escape would be lifting a restriction the operator had already ended, while
 * the restriction on ITS OWN turn is unreachable — that one ends only at an operator signal.
 *
 * WHAT THAT IS NOT: OS-level confinement. The supervised child runs as the operator's own user with
 * no job-object/ACL boundary (U25, still owed), so a same-user process can synthesize OS keyboard
 * input into the focused window and would be indistinguishable from the operator here. That is the
 * same argument used below to refuse `pane:input`, one layer further down, and it is a reason to
 * finish U25 — not a reason to hand the restriction's end back to the child's own say-so.
 *
 * The enumerated sources are the only ones accepted; anything else is REFUSED and recorded, so a
 * later caller cannot widen this by passing a persuasive string.
 *
 * WHAT IS DELIBERATELY *NOT* A SOURCE: bytes arriving on the `pane:input` IPC channel. That looks
 * like the operator typing — it is the channel their keystrokes travel — but xterm.js ALSO emits
 * `onData` for terminal REPLIES it generates on its own (cursor-position/device-attribute answers to
 * escape sequences printed by the pane's own process). The supervised child prints into that pane, so
 * it could elicit an "operator" byte on demand and end its own restriction. Only events Electron main
 * observes from the OS input path, which the child is not on, qualify.
 */
const OPERATOR_DISARM_SOURCES = Object.freeze({
  electron_main_before_input_event:
    "Electron main observed the operator press a key, before the page saw it",
  electron_main_operator_chord:
    "Electron main observed the operator's Ctrl+Shift+Escape recovery chord",
});

/**
 * The provenance the OTHER release path may carry. `reset()` is called from SessionManager's
 * observed node-pty exit and from `stop()` (this service shutting down, U176); any other string a
 * caller passes is recorded as `null` rather than as an unverified fact, so a receipt reading
 * `source` off a reset row is reading this service's answer. Both are facts Electron main measures
 * for itself — neither can be produced by the supervised child.
 */
const PROCESS_RELEASE_SOURCES = ["node_pty_exit", "supervisor_authority_stopped"];

//: The audit is appended by events the SUPERVISED CHILD dispatches (it holds the transport bearer),
//: so it is bounded like every other renderer-facing surface in this shell (U182). Dropped rows are
//: counted, never silently discarded, and no decision reads the audit — `_fates` below answers the
//: only question a caller asked it.
const DEFAULT_AUDIT_LIMIT = 2000;
//: Per-turn fates outlive their audit rows. Bounded by turn, not by event: a turn is created only by
//: `arm()`, which only this shell's own voice path calls.
const FATE_LIMIT = 200;

// What the OPERATOR is told, and it must match the code exactly: `before-input-event` fires for the
// whole window, so ANY key ends the turn, not only one typed into the conductor pane. The first
// draft said "type in the conductor pane", which scoped it narrower than the behaviour and hid U170
// from the one artifact the operator actually reads (spec-audit M-4, invariant 27).
const TURN_RECOVERY_HINT =
  "typing ends this voice turn — your next keystroke anywhere in this window does it, "
  + "including in another pane; or press Ctrl+Shift+Escape to end it without typing";
// …and what the operator is told once they HAVE ended it, which is not "nothing is happening" (U178):
// the answer their utterance is still producing keeps its tool denial until they send a prompt.
const TURN_ENDED_HINT =
  "you ended the voice turn and your keyboard is yours again — the answer it is still producing "
  + "cannot use tools until you send your next prompt";
const MARKER_PREFIX = "[[SOVEREIGN_VOICE_CHAT_V2:";
const MAX_REQUEST_BYTES = 64 * 1024;
const ENV_HOST = "SOW_VOICE_AUTH_HOST";
const ENV_PORT = "SOW_VOICE_AUTH_PORT";
const ENV_TOKEN = "SOW_VOICE_AUTH_TOKEN";
const ENV_SCHEMA = "SOW_VOICE_AUTH_SCHEMA";

function _hook(event, output) {
  return { schema: RESPONSE_SCHEMA, event, exitCode: 0, output };
}

function failClosedHookResult(event, reason) {
  const why = `Sovereign supervisor voice authority unavailable: ${reason}`;
  if (event === "PreToolUse") {
    return _hook(event, { hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: why,
    } });
  }
  if (event === "PermissionRequest") {
    return _hook(event, { hookSpecificOutput: {
      hookEventName: "PermissionRequest",
      decision: { behavior: "deny", message: why, interrupt: false },
    } });
  }
  if (event === "UserPromptSubmit" || event === "ConfigChange") {
    return _hook(event, { decision: "block", reason: why });
  }
  // A lifecycle notification that cannot reach the supervisor must not pretend it disarmed state.
  // Exit 2 makes the transport failure visible; the supervisor remains armed and future prompts /
  // tools continue to fail closed until the process is restarted or the real event is received.
  return { schema: RESPONSE_SCHEMA, event, exitCode: 2, output: null, error: why };
}

function _safeEqual(a, b) {
  const left = Buffer.from(String(a || ""), "utf8");
  const right = Buffer.from(String(b || ""), "utf8");
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

function _turnId(randomBytes) {
  return randomBytes(16).toString("hex");
}

function _marker(turnId) {
  return `${MARKER_PREFIX}${turnId}]] `;
}

function _copy(row) {
  return row ? JSON.parse(JSON.stringify(row)) : null;
}

class SupervisorVoiceTurnAuthority {
  constructor(opts = {}) {
    this.token = String(opts.token || crypto.randomBytes(32).toString("hex"));
    if (!/^[0-9a-f]{64}$/i.test(this.token)) {
      throw new TypeError("voice authority token must be 32 random bytes encoded as hex");
    }
    this._randomBytes = opts.randomBytes || crypto.randomBytes;
    this._now = opts.now || (() => new Date().toISOString());
    this._log = typeof opts.log === "function" ? opts.log : () => {};
    // The shell repaints the operator's restriction indicator from this (invariant 27). A turn is
    // admitted by a socket callback, not by anything the renderer asked for, so a chrome that only
    // repainted on operator action would show a stale restriction — the state has to push itself.
    this._onChange = typeof opts.onChange === "function" ? opts.onChange : () => {};
    // U181: the pinned hook and the module it requires live inside the supervised child's writable
    // cwd, and were hashed once at launch. Main binds a verifier that re-reads those bytes; absence
    // of a verifier is the headless/test case, where there is no launch ticket to verify against.
    this._verifyPolicy = typeof opts.verifyPolicy === "function" ? opts.verifyPolicy : null;
    this._pending = null;
    this._active = null;
    // U178: an ADMITTED turn the operator ended. Terminal for the turn — the answer it is still
    // producing keeps its denial — and cleared only by the operator's next prompt or a release.
    this._ended = null;
    this.audit = [];
    this._auditLimit = Number.isInteger(opts.auditLimit) && opts.auditLimit > 0
      ? opts.auditLimit : DEFAULT_AUDIT_LIMIT;
    this._auditDropped = 0;
    // turn_id -> fate, so a caller's question survives the audit ring (U182) and is answered by the
    // state machine rather than by a scan of rows the child can flood.
    this._fates = new Map();
    this._server = null;
    this._address = null;
    this._sockets = new Set();
    this._stopping = null;
  }

  _record(event, extra = {}) {
    // The caller's fields go FIRST: `schema`/`at`/`event` are this service's own answer, and a caller
    // passing `facts` must not be able to relabel the row it is appending (gate-validator R-6).
    const row = {
      ...extra,
      schema: "supervisor_voice_turn_audit@1.0",
      at: this._now(),
      event,
    };
    this.audit.push(row);
    // Bounded (U182). The child dispatches hook events at will and every one of them lands here; an
    // unbounded array behind a 120 ms reader is a memory sink the least-trusted party controls.
    while (this.audit.length > this._auditLimit) {
      this.audit.shift();
      this._auditDropped += 1;
    }
    this._log(`voice-authority: ${event}${extra.reason ? ` (${extra.reason})` : ""}`);
    return row;
  }

  /** Remember a turn's fate for `fateOf()`, bounded by turn (insertion-ordered, oldest evicted). */
  _fate(turnId, fate) {
    if (!turnId) return;
    this._fates.delete(turnId);
    this._fates.set(turnId, fate);
    while (this._fates.size > FATE_LIMIT) this._fates.delete(this._fates.keys().next().value);
  }

  /**
   * What became of one armed turn — the question the voice delivery asks after the submit key.
   *
   * `vendor_reported_submission` is named for what measured it (U180): the CLI presented the exact
   * armed payload back to this service through its hook. That is the CHILD's claim about itself —
   * it holds both the payload and the bearer — so it is the basis for a delivery *report*, never for
   * an authority decision. Every deny path above works the other way round, where trusting a forged
   * admission is the safe direction. An unknown turn is `ended`: this service does not hold it.
   */
  fateOf(turnId) {
    const id = String(turnId || "");
    if (!id) return "ended";
    return this._fates.get(id) || "ended";
  }

  /**
   * Re-verify the policy bytes at DISPATCH (U181) — the hook file and the module it requires sit in
   * the conductor's own writable workspace, so a hash taken once at launch says nothing about the
   * transport that just called. Anything other than an explicit ok, including a verifier that
   * throws, is a refusal: an unverifiable boundary is not a boundary.
   */
  _policyVerified() {
    if (!this._verifyPolicy) return null;
    let verdict;
    try {
      verdict = this._verifyPolicy();
    } catch (e) {
      verdict = { ok: false, reason: `the policy bytes could not be read: ${(e && e.message) || e}` };
    }
    if (verdict && verdict.ok === true) return null;
    const reason = (verdict && typeof verdict.reason === "string" && verdict.reason)
      || "the supervisor-pinned voice-turn policy bytes could not be verified at dispatch";
    this._record("policy_bytes_unverified", { reason });
    return reason;
  }

  /** Tell the shell the restriction changed. A chrome subscriber must never break authority. */
  _changed() {
    try { this._onChange(this.turnState()); } catch { /* the indicator is downstream of the decision */ }
  }

  /**
   * What the operator's chrome renders (invariant 27): whether a voice turn is restricting this
   * session right now, since when — and, because a state whose exit is undiscoverable is not
   * observable in any useful sense, how to end it.
   */
  turnState() {
    const active = this._active;
    const pending = this._pending;
    const ended = this._ended;
    // `restricted` is the OPERATOR-facing fact and stays what it was: is a voice turn holding this
    // session against them. `tools_denied` is the other half U178 added — after their keystroke they
    // have their keyboard back while the answer in flight still cannot execute anything. Two facts,
    // two fields: collapsing them would either mute the operator again or hide a live denial.
    return {
      schema: TURN_STATE_SCHEMA,
      restricted: Boolean(active || pending),
      phase: active ? "active" : pending ? "pending" : ended ? "ended" : "idle",
      turn_id: (active && active.turn_id) || (pending && pending.turn_id) || null,
      session_id: (active && active.session_id) || null,
      since: (active && active.admitted_at) || (pending && pending.armed_by_supervisor_at) || null,
      tools_denied: Boolean(active || pending || ended),
      denying_turn_id: (active && active.turn_id) || (pending && pending.turn_id)
        || (ended && ended.turn_id) || null,
      ended_at: (ended && ended.ended_at) || null,
      recovery: ended && !active && !pending ? TURN_ENDED_HINT : TURN_RECOVERY_HINT,
    };
  }

  /**
   * End the current turn on an OPERATOR signal Electron main measured itself (see
   * OPERATOR_DISARM_SOURCES). Returns the audit row, or null when there was nothing to disarm or the
   * source is not one main owns — never a partial release.
   */
  disarm(source, facts = {}) {
    const key = String(source == null ? "" : source);
    if (!Object.prototype.hasOwnProperty.call(OPERATOR_DISARM_SOURCES, key)) {
      this._record("voice_turn_disarm_refused", {
        source: key || null,
        reason: "not an operator signal Electron main observes for itself",
      });
      return null;
    }
    const active = this._active;
    const pending = this._pending;
    const turnId = (active && active.turn_id) || (pending && pending.turn_id) || null;
    if (!turnId) return null;   // nothing was restricted; a no-op is not an event
    this._pending = null;
    this._active = null;
    // U178. An ADMITTED turn keeps denying: its answer is very likely still being generated, and the
    // operator's keystroke was about their keyboard, not about that answer's authority. A PENDING
    // turn was never presented to the model, so there is nothing in flight to deny for — and its
    // payload can no longer be admitted at all (`arm()` minted it; `_pending` is gone).
    this._ended = active
      ? { turn_id: turnId, session_id: active.session_id || null, ended_at: this._now(), source: key }
      : null;
    if (active) this._fate(turnId, "vendor_reported_submission");
    else this._fate(turnId, "ended_by_operator");
    const row = this._record("voice_turn_disarmed", {
      // the caller's facts first: the identity fields below are this service's own answer and a
      // caller must not be able to overwrite them with a more flattering one
      ...facts,
      turn_id: turnId,
      phase: active ? "active" : "pending",
      session_id: (active && active.session_id) || null,
      source: key,
      basis: OPERATOR_DISARM_SOURCES[key],
      // said plainly in the trail the receipt reads: what this release did and did not lift
      tools_still_denied_for_turn: Boolean(active),
    });
    this._changed();
    return row;
  }

  arm(text) {
    if (this._pending) throw new Error("a voice turn is already pending");
    const body = String(text == null ? "" : text);
    if (!body.trim()) throw new Error("cannot arm an empty voice turn");
    const turnId = _turnId(this._randomBytes);
    const promptMarker = _marker(turnId);
    const payload = `${promptMarker}${body}`;
    this._pending = {
      turn_id: turnId,
      prompt_marker: promptMarker,
      payload,
      payload_sha256: crypto.createHash("sha256").update(payload, "utf8").digest("hex"),
      armed_by_supervisor_at: this._now(),
    };
    this._fate(turnId, "pending");
    this._record("voice_turn_pending", { turn_id: turnId });
    this._changed();
    return {
      turn_id: turnId,
      prompt_marker: promptMarker,
      payload,
      broker_schema: BROKER_SCHEMA,
    };
  }

  cancel(turnId, reason = "cancelled before vendor admission") {
    if (!this._pending || this._pending.turn_id !== turnId) return false;
    this._pending = null;
    this._fate(turnId, "ended_by_cancel");
    this._record("voice_turn_cancelled", { turn_id: turnId, reason });
    this._changed();
    return true;
  }

  /**
   * Release whatever turn is held because the supervised PROCESS is gone (SessionManager's observed
   * node-pty exit). `facts.source` is validated the way `disarm()`'s is (spec-audit m-1): the receipt
   * leg `every_release_carried_a_main_owned_provenance` reads `source` off these rows, so a caller
   * string that reached the audit unchecked would be the one input that leg trusts blindly.
   */
  reset(reason = "supervised conductor session ended", facts = {}) {
    const turnId = (this._active && this._active.turn_id)
      || (this._pending && this._pending.turn_id)
      // U178: a turn the operator ended is still denying tools for an answer in flight. When the
      // PROCESS goes, that answer goes with it, so this release covers the ended turn too — and says
      // so, rather than clearing it with no row (which is what U176 charged `stop()` with).
      || (this._ended && this._ended.turn_id) || null;
    const phase = this._active ? "active" : this._pending ? "pending" : this._ended ? "ended" : "idle";
    const wasAdmitted = Boolean(this._active) || Boolean(this._ended);
    this._pending = null;
    this._active = null;
    this._ended = null;
    if (turnId) {
      this._fate(turnId, wasAdmitted ? "vendor_reported_submission" : "ended_by_process_exit");
      // `phase` is recorded (validator R-4): a receipt that says "a live turn was released by the
      // process exit" must be able to show WHICH kind of turn — an admitted one or one still pending.
      const source = PROCESS_RELEASE_SOURCES.includes(String(facts.source)) ? String(facts.source) : null;
      this._record("voice_turn_reset", { ...facts, turn_id: turnId, reason, phase, source });
      this._changed();
    }
  }

  _authenticate(token) {
    if (!_safeEqual(token, this.token)) throw new Error("voice authority authentication failed");
  }

  _markedPrompt(prompt) {
    const raw = String(prompt || "");
    if (!raw.startsWith(MARKER_PREFIX)) return null;
    const end = raw.indexOf("]] ", MARKER_PREFIX.length);
    if (end < 0) return { malformed: true };
    return { turn_id: raw.slice(MARKER_PREFIX.length, end), payload: raw };
  }

  handle(request) {
    if (!request || typeof request !== "object") throw new TypeError("voice authority request is not an object");
    this._authenticate(request.token);
    const input = request.input && typeof request.input === "object" ? request.input : {};
    const event = String(input.hook_event_name || "");
    const sessionId = String(input.session_id || "").trim();
    const blocked = (reason) => _hook(event, { decision: "block", reason });
    const marked = event === "UserPromptSubmit" ? this._markedPrompt(input.prompt) : null;

    // U181 — the transport's own bytes, re-verified for THIS dispatch. Before anything else: a hook
    // whose file was rewritten during an unrestricted typed turn would otherwise be answered as if it
    // were the pinned one.
    const unverified = this._policyVerified();
    if (unverified) return failClosedHookResult(event, unverified);

    // U183 — the child supplies `session_id` and a receipt reads it back. Main mints its own session
    // id in a different namespace from the vendor CLI's, so the comparison that can honestly be made
    // is against the id THIS turn was admitted under. Recorded, never authority: a mismatch means the
    // reported field is untrustworthy, and every decision below already treats the child as untrusted.
    const heldSession = (this._active && this._active.session_id)
      || (this._ended && this._ended.session_id) || null;
    if (heldSession && sessionId && sessionId !== heldSession) {
      this._record("vendor_session_id_mismatch", {
        turn_id: (this._active && this._active.turn_id) || (this._ended && this._ended.turn_id) || null,
        admitted_session_id: heldSession,
        reported_session_id: sessionId,
        by: event,
        reason: "the vendor reported a different session id than the turn was admitted under",
      });
    }

    if (event === "UserPromptSubmit" && marked) {
      const pending = this._pending;
      if (!sessionId || marked.malformed || !pending
          || marked.turn_id !== pending.turn_id || marked.payload !== pending.payload) {
        this._record("voice_turn_rejected", {
          turn_id: marked.turn_id || null,
          reason: "prompt was not the exact supervisor-armed pending turn",
        });
        return blocked("voice prompt was not admitted by the supervisor process");
      }
      const superseded = this._active;
      this._pending = null;
      // a NEW spoken turn's restriction replaces whatever the last one left denying (U178)
      this._ended = null;
      this._fate(pending.turn_id, "vendor_reported_submission");
      this._active = {
        turn_id: pending.turn_id,
        session_id: sessionId,
        admitted_at: this._now(),
        payload_sha256: pending.payload_sha256,
      };
      if (superseded) {
        this._record("voice_turn_superseded", {
          turn_id: superseded.turn_id,
          by_turn_id: pending.turn_id,
          session_id: superseded.session_id,
        });
      }
      this._record("voice_turn_armed", {
        turn_id: pending.turn_id,
        session_id: sessionId,
      });
      this._changed();
      return _hook(event, { hookSpecificOutput: {
        hookEventName: "UserPromptSubmit",
        // Say what is actually true, in the one place the model reads. "…until the turn stops" said
        // this ended by itself; nothing ended it, and the session went mute (U166, spec-audit M4).
        additionalContext: "Sovereign supervisor marked this as a non-executing voice turn. "
          + "All tool calls and permission escalations are denied until the OPERATOR ends this turn "
          + "from the shell (their next keystroke does it); this session's own lifecycle events "
          + "cannot end it. Answer in text.",
      } });
    }

    if (event === "UserPromptSubmit") {
      if (this._pending || this._active) {
        this._record("overlapping_prompt_blocked", {
          session_id: sessionId || null,
          reason: "a supervisor-owned voice turn has not disarmed",
        });
        return blocked("a supervisor-owned voice turn is still pending or active");
      }
      // U178 — THE BOUND ON THE ENDED TURN. An unmarked prompt is the operator's own: it is what
      // their keystroke was the beginning of, and the answer the spoken turn was producing is over by
      // the time one arrives. This is the only release the child's own report can effect, and it is
      // the safe direction — a forged one lifts a restriction the operator had already ended, while
      // the restriction on the child's OWN active turn stays unreachable from this socket.
      if (this._ended) {
        const ended = this._ended;
        this._ended = null;
        this._record("voice_turn_ended_released", {
          turn_id: ended.turn_id,
          session_id: sessionId || null,
          admitted_session_id: ended.session_id || null,
          reason: "the operator's next prompt ended the voice turn's tool denial",
        });
        this._changed();
      }
      return _hook(event, null);
    }

    // The denial covers the ENDED turn too (U178): the operator's keystroke ended the turn for them,
    // not for the answer it is still generating.
    const restricted = Boolean(this._pending || this._active || this._ended);
    const phase = this._active ? "active" : this._pending ? "pending" : this._ended ? "ended" : "idle";
    const activeTurn = (this._active && this._active.turn_id)
      || (this._pending && this._pending.turn_id)
      || (this._ended && this._ended.turn_id) || null;
    if (event === "PreToolUse" && restricted) {
      this._record("tool_denied", {
        turn_id: activeTurn,
        session_id: sessionId || null,
        phase,
        tool_name: String(input.tool_name || ""),
      });
      return _hook(event, { hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: phase === "ended"
          ? "Sovereign supervisor: this answer belongs to a voice turn the operator ended; voice "
            + "turns are non-executing until their next prompt."
          : "Sovereign supervisor: voice turns are non-executing.",
      } });
    }
    if (event === "PermissionRequest" && restricted) {
      this._record("permission_denied", {
        turn_id: activeTurn,
        session_id: sessionId || null,
        phase,
        tool_name: String(input.tool_name || ""),
      });
      return _hook(event, { hookSpecificOutput: {
        hookEventName: "PermissionRequest",
        decision: {
          behavior: "deny",
          message: "Sovereign supervisor: voice turns cannot grant permissions.",
          interrupt: false,
        },
      } });
    }
    if (event === "ConfigChange") {
      // The launch ticket pins the hook/settings bytes. Letting the attended process change that
      // profile between turns would make the next "supervisor-enforced" claim stale before it was
      // used. Configuration changes require a governed relaunch with a newly validated ticket.
      this._record("config_change_blocked", {
        turn_id: activeTurn,
        session_id: sessionId || null,
        source: String(input.source || ""),
      });
      return blocked("the supervisor-pinned conductor permission profile cannot change in-session");
    }
    if (["Stop", "StopFailure", "SessionEnd"].includes(event) && this._active) {
      // The supervised child holds the transport bearer so it can send hook events. Consequently a
      // vendor lifecycle event is an OBSERVATION, never authority to remove the restriction: treating
      // SessionEnd as authoritative produced a reproducible deny → forged SessionEnd → allow bypass.
      // The restriction is cleared only by `reset()` (SessionManager's observed OS-process exit) or
      // `disarm()` on an operator signal Electron main measured itself — never from this socket.
      this._record("vendor_lifecycle_observed", {
        turn_id: this._active.turn_id,
        active_session_id: this._active.session_id,
        reported_session_id: sessionId || null,
        by: event,
      });
    }
    return _hook(event, null);
  }

  snapshot() {
    return {
      schema: BROKER_SCHEMA,
      listening: Boolean(this._server && this._address),
      pending: _copy(this._pending),
      active: _copy(this._active),
      ended: _copy(this._ended),
      turn: this.turnState(),
      audit: this.audit.map((row) => ({ ...row })),
      // what the ring dropped, so a reader can never mistake a bounded trail for a complete one
      audit_dropped: this._auditDropped,
    };
  }

  runtimeBoundary(ticketBoundary) {
    if (!this._server || !this._address) return null;
    if (!ticketBoundary || ticketBoundary.schema !== BOUNDARY_SCHEMA
        || ticketBoundary.supervisor_owned !== true
        || ticketBoundary.non_executing_voice_turns !== true
        || ticketBoundary.enforced_by_supervisor_process !== false) return null;
    return {
      schema: BOUNDARY_SCHEMA,
      supervisor_owned: true,
      non_executing_voice_turns: true,
      enforced_by_supervisor_process: true,
      broker_schema: BROKER_SCHEMA,
      transport: "authenticated-loopback-to-electron-main",
      hook_sha256: ticketBoundary.hook_sha256 || null,
      settings_sha256: ticketBoundary.settings_sha256 || null,
    };
  }

  address() {
    return this._address ? { ...this._address } : null;
  }

  childEnv(baseEnv = {}) {
    if (!this._address) throw new Error("voice authority is not listening");
    return {
      ...baseEnv,
      [ENV_HOST]: "127.0.0.1",
      [ENV_PORT]: String(this._address.port),
      [ENV_TOKEN]: this.token,
      [ENV_SCHEMA]: REQUEST_SCHEMA,
    };
  }

  async start() {
    if (this._server && this._address) return this.address();
    this._stopping = null;
    const server = net.createServer((socket) => {
      this._sockets.add(socket);
      socket.once("close", () => this._sockets.delete(socket));
      socket.setEncoding("utf8");
      let raw = "";
      let finished = false;
      const reply = (payload) => {
        if (finished) return;
        finished = true;
        socket.end(`${JSON.stringify(payload)}\n`);
      };
      socket.on("data", (chunk) => {
        raw += chunk;
        if (Buffer.byteLength(raw, "utf8") > MAX_REQUEST_BYTES) {
          reply(failClosedHookResult("", "request exceeded the bounded size"));
          return;
        }
        const end = raw.indexOf("\n");
        if (end < 0) return;
        try {
          const parsed = JSON.parse(raw.slice(0, end));
          if (parsed.schema !== REQUEST_SCHEMA) throw new Error("voice authority request schema mismatch");
          reply(this.handle(parsed));
        } catch (e) {
          reply(failClosedHookResult("", e.message));
        }
      });
      socket.on("error", () => { /* the hook sees a failed/closed request and fails closed */ });
    });
    server.unref();
    await new Promise((resolve, reject) => {
      const onError = (e) => { server.off("listening", onListening); reject(e); };
      const onListening = () => { server.off("error", onError); resolve(); };
      server.once("error", onError);
      server.once("listening", onListening);
      server.listen({ host: "127.0.0.1", port: 0, exclusive: true });
    });
    const address = server.address();
    if (!address || typeof address === "string" || address.address !== "127.0.0.1") {
      await new Promise((resolve) => server.close(resolve));
      throw new Error("voice authority did not bind an IPv4 loopback socket");
    }
    this._server = server;
    this._address = { address: address.address, family: address.family, port: address.port };
    this._record("supervisor_authority_started", { address: "127.0.0.1", port: address.port });
    return this.address();
  }

  async stop({ timeoutMs = DEFAULT_STOP_TIMEOUT_MS } = {}) {
    if (this._stopping) return this._stopping;
    const server = this._server;
    this._server = null;
    this._address = null;
    // U176: this used to clear both turns and record only `supervisor_authority_stopped`, so a
    // release by this path was invisible to the receipt leg that enumerates provenance rows
    // (invariant 27) — the one release with no `voice_turn_*` row of its own.
    this.reset("the supervisor voice authority service stopped", { source: "supervisor_authority_stopped" });
    if (!server) {
      return { closed: true, was_listening: false, forced: false, timed_out: false,
        timeout_ms: null, waited_ms: 0 };
    }
    const budget = Number.isFinite(timeoutMs) && timeoutMs > 0
      ? timeoutMs : DEFAULT_STOP_TIMEOUT_MS;
    const started = Date.now();
    this._stopping = new Promise((resolve) => {
      let settled = false;
      let forced = false;
      const finish = (outcome) => {
        if (settled) return;
        settled = true;
        clearTimeout(forceAt);
        clearTimeout(giveUpAt);
        this._record("supervisor_authority_stopped", outcome);
        resolve(outcome);
      };
      const waited = () => Math.max(0, Date.now() - started);
      const forceAt = setTimeout(() => {
        forced = true;
        for (const socket of this._sockets) socket.destroy();
      }, Math.max(1, Math.floor(budget / 2)));
      const giveUpAt = setTimeout(() => finish({
        closed: false, was_listening: true, forced, timed_out: true,
        timeout_ms: budget, waited_ms: waited(),
      }), budget);
      try {
        server.close(() => finish({
          closed: true, was_listening: true, forced, timed_out: false,
          timeout_ms: budget, waited_ms: waited(),
        }));
      } catch {
        finish({
          closed: false, was_listening: true, forced, timed_out: true,
          timeout_ms: budget, waited_ms: waited(),
        });
      }
    });
    return this._stopping;
  }
}

function requestSupervisor({ env = process.env, input, timeoutMs = 2000 } = {}) {
  return new Promise((resolve, reject) => {
    const host = String(env[ENV_HOST] || "");
    const port = Number(env[ENV_PORT]);
    const token = String(env[ENV_TOKEN] || "");
    if (host !== "127.0.0.1" || !Number.isInteger(port) || port < 1 || port > 65535
        || !/^[0-9a-f]{64}$/i.test(token) || env[ENV_SCHEMA] !== REQUEST_SCHEMA) {
      reject(new Error("supervisor voice authority environment is absent or malformed"));
      return;
    }
    const socket = net.createConnection({ host, port });
    socket.setEncoding("utf8");
    let raw = "";
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      socket.destroy();
      fn(value);
    };
    const timer = setTimeout(
      () => finish(reject, new Error(`supervisor voice authority timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    socket.on("connect", () => {
      socket.write(`${JSON.stringify({
        schema: REQUEST_SCHEMA,
        token,
        input: input && typeof input === "object" ? input : {},
      })}\n`);
    });
    socket.on("data", (chunk) => {
      raw += chunk;
      if (Buffer.byteLength(raw, "utf8") > MAX_REQUEST_BYTES) {
        finish(reject, new Error("supervisor voice authority response exceeded the bounded size"));
        return;
      }
      const end = raw.indexOf("\n");
      if (end < 0) return;
      try {
        const parsed = JSON.parse(raw.slice(0, end));
        if (parsed.schema !== RESPONSE_SCHEMA) throw new Error("response schema mismatch");
        finish(resolve, parsed);
      } catch (e) {
        finish(reject, new Error(`invalid supervisor voice authority response: ${e.message}`));
      }
    });
    socket.on("error", (e) => finish(reject, e));
    socket.on("end", () => {
      if (!settled) finish(reject, new Error("supervisor voice authority closed without a response"));
    });
  });
}

module.exports = {
  REQUEST_SCHEMA,
  RESPONSE_SCHEMA,
  BOUNDARY_SCHEMA,
  BROKER_SCHEMA,
  TURN_STATE_SCHEMA,
  DEFAULT_STOP_TIMEOUT_MS,
  OPERATOR_DISARM_SOURCES,
  TURN_RECOVERY_HINT,
  MARKER_PREFIX,
  ENV_HOST,
  ENV_PORT,
  ENV_TOKEN,
  ENV_SCHEMA,
  SupervisorVoiceTurnAuthority,
  requestSupervisor,
  failClosedHookResult,
};
