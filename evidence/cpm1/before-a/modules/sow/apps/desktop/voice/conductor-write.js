"use strict";
/**
 * Phase 17C `.close-revalidate` — the voice→conductor delivery, as testable code.
 *
 * WHY IT LIVES HERE. `.close` wrote this orchestration inside `apps/desktop/main.js`, which cannot be
 * required headlessly (it calls `app.whenReady()` at load). Both mandatory reviews of that tree made
 * the same complaint they had already made at 17B `.spawn`: a fix that no check can see is a claim,
 * not a fix — the validator reverted half of BLOCKING-1's fix and all 393 + 186 tests stayed green.
 * The whole decision now lives in a pure module over injected I/O, and every guard below has a test
 * that goes red when it is removed. Main binds it to the real session manager and nothing else.
 *
 * THE FOUR GUARDS, in the order they run, each fail-closed and each from a real defect:
 *   1. GOVERNED CONDUCTOR ONLY. The sink is the pane running the governed conductor launch. The target
 *      is not a parameter: it was one, and the `.mic` receipt shows the operator's transcript
 *      Enter-submitted into a `powershell.exe` stand-in — voice text reaching a command interpreter.
 *   2. NO RESIDUE. A body written but never submitted stays in the input box; the next utterance would
 *      be appended and the pair submitted as one message the operator never spoke.
 *   3. THE PANE MUST BE ACCEPTING TEXT. The live CLI gates its own tool use with a numbered selection
 *      list, where characters are choices. `.close` gated the submit key and left the BODY free to be
 *      typed into it (voice/pane-state.js).
 *   4. THE ECHO WINDOW IS EXACT OR NOTHING. The submit key follows an observed echo, read from the
 *      bytes appended after the write — never from the scrollback, which could contain an earlier echo
 *      of the same sentence (voice/echo-confirm.js + RingBuffer.sliceFrom).
 *
 * Deterministic: no Electron, no fs, no timers of its own (the caller injects `now`/`sleep`).
 */

const { echoedInOrder } = require("./echo-confirm");
const { paneAcceptsTypedText } = require("./pane-state");

//: How long the submit key waits for the pane to echo the body before it is withheld. Measured on this
//: host: the live TUI echoes a freshly-written utterance's head within a few hundred ms; 8 s is slack
//: for a busy repaint, not an expectation.
const SUBMIT_ECHO_TIMEOUT_MS = 8000;
const SUBMIT_ECHO_POLL_MS = 120;
// How long to wait for the vendor's own `UserPromptSubmit` hook to present the armed payload back to
// the supervisor after the submit key. Short: this is a loopback round trip inside one host, and a
// turn still pending at the deadline is reported as submitted, not as a failure (17C `.disarm`).
const SUBMIT_ADMIT_TIMEOUT_MS = 4000;

const _no = (written, reason, extra) => ({ written, submitted: false, reason, ...(extra || {}) });

/**
 * Is a supervisor-owned, runtime-enforced non-executing boundary bound to this conductor RIGHT NOW?
 *
 * One predicate, two uses (U179). Guard 1 refuses without it; guard 3 passes it to `pane-state`,
 * which is the only thing that lets a `manual mode on` pane be typed into. It used to pass the
 * literal `true` there, so pane-state's own refusal — vendor chrome alone is not authority,
 * invariant 29 — could never fire, and the guard above was the only thing standing between an
 * unbound session and the operator's sentence being typed into it.
 *
 * WHAT IT STILL DOES NOT ESTABLISH, and this is the narrowed residual: the pane's MODE is reported
 * by vendor chrome and nothing in this repo observes it independently (the launch argv pins the
 * model, not the permission mode). What this predicate buys is that accepting that chrome is
 * conditioned on a live supervisor-owned restriction, re-read at the moment of the write.
 */
function supervisorEnforcedBoundary(boundary) {
  return Boolean(boundary && boundary.schema === "voice_turn_boundary@1.0"
    && boundary.supervisor_owned === true && boundary.non_executing_voice_turns === true
    && boundary.enforced_by_supervisor_process === true
    && boundary.broker_schema === "supervisor_voice_turn_authority@1.0");
}

/** Only an operator submit/cancel can resolve text already sitting in the input box. */
function operatorInputResolvesResidue(data) {
  const s = String(data == null ? "" : data);
  return /[\r\n\x03]/.test(s);
}

/**
 * Deliver a routed CHAT transcript into the live conductor input.
 *
 * @param {string} text the transcript the BRIDGE routed as chat (never re-classified here)
 * @param {object} io injected I/O, all synchronous unless noted:
 *   paneId            — the conductor pane id (null ⇒ refuse)
 *   hasSession()      — a session record exists for that pane
 *   isTerminal()      — that record is EXITED/KILLED (a record is not a process)
 *   launchState()     — the governed conductor launch state ("running" ⇒ governed sink)
 *   authorityBoundary() — the runtime-bound supervisor-process boundary
 *   armAuthority(body) — supervisor mints one exact pending turn + unpredictable marker
 *   cancelAuthority(turnId, reason) — removes a pending turn after a delivery failure
 *   emittedAll()      — every byte the pane's ConPTY has emitted (Buffer|string|null)
 *   streamPosition()  — the pane's MONOTONIC stream position (number|null)
 *   emittedSince(from)— bytes appended after `from`, or NULL when that window is unanswerable
 *   write(data)       — write to the pane's ConPTY; returns whether a LIVE handle took the bytes
 *   getResidue()/setResidue(r) — the unsubmitted-utterance record (guard 2)
 *   now()             — epoch ms
 *   sleep(ms)         — async delay
 * @returns {Promise<{written:boolean, submitted:boolean, reason:string, flattened?:boolean,
 *                    echo?:object, pane_state?:object, residue?:object}>}
 */
async function deliverChat(text, io) {
  const paneId = io.paneId;
  if (!paneId) return _no(false, "no conductor pane");
  if (!io.hasSession()) return _no(false, "conductor session not admitted (owed 16F)");
  // A registry RECORD is not a live process: the manager deletes the pty handle on exit while the
  // record survives until the next launch forgets it. Without this a spoken utterance after the
  // conductor exited reported "delivered" with nothing to receive it.
  if (io.isTerminal()) return _no(false, "the conductor session has ended — nothing would receive it");
  // Guard 1 — the sink is the GOVERNED conductor node, never merely a pane holding a session.
  const launch = io.launchState();
  if (launch !== "running") {
    return _no(false, `pane ${paneId} is not running a governed conductor session (launch state: `
      + `${launch}) — nothing was written`);
  }
  // Vendor TUI chrome is interaction state, never authority. The runtime boundary exists only when
  // Electron main's authenticated authority service is listening; the pinned hook is transport.
  const readBoundary = () => (io.authorityBoundary ? io.authorityBoundary() : null);
  const boundary = readBoundary();
  if (!supervisorEnforcedBoundary(boundary)) {
    return _no(false, "direct voice chat is disabled: no non-executing boundary with supervisor-process "
      + "enforcement is bound to this conductor (invariants 25/29)");
  }
  // Interior newlines would submit the first fragment and leave the rest as a second prompt: one
  // utterance, two model calls, the second a fragment. Collapse them and record that it happened.
  const raw = String(text == null ? "" : text).replace(/[\r\n]+$/, "");
  const body = raw.replace(/[\r\n]+/g, " ");
  const flattened = body !== raw;
  if (!body.trim()) return _no(false, "nothing to deliver (empty transcript)", { flattened });

  // Guard 2 — an unsubmitted utterance is still in the input box.
  const residue = io.getResidue();
  if (residue) {
    return _no(false, "the conductor input still holds an utterance that was never submitted "
      + `("${residue.excerpt}") — clear pane ${paneId} with Enter or Ctrl-C before `
      + "speaking again, or this one would be spliced onto it", { flattened, residue: { ...residue } });
  }
  // Guard 3 — the pane must be showing its text input. Positive evidence only, and the boundary is
  // RE-READ here rather than assumed from guard 1 (U179): the authority service can stop between the
  // two, and a manual-mode pane with no live restriction is precisely what pane-state refuses.
  const state = paneAcceptsTypedText(io.emittedAll(),
    { supervisorBoundary: supervisorEnforcedBoundary(readBoundary()) });
  const pane_state = { accepting: state.accepting, state: state.state, evidence: state.evidence };
  if (!state.accepting) return _no(false, state.reason, { flattened, pane_state });

  // Guard 4 — bound the echo search to what is appended AFTER the write.
  const from = io.streamPosition();
  if (!Number.isInteger(from)) {
    return _no(false, "the session's output buffer is unreadable — nothing was written (fail closed)",
      { flattened, pane_state });
  }
  // The exact turn is armed by the long-lived supervisor process immediately before the body write.
  // The vendor hook cannot mint this marker or state. A later hook event must present this exact
  // payload back to the supervisor before model processing, or the prompt is blocked.
  let armed;
  try {
    armed = await io.armAuthority(body);
  } catch (e) {
    return _no(false, `the supervisor could not arm a non-executing voice turn (${e.name || "Error"}: `
      + `${e.message}) — nothing was written`, { flattened, pane_state });
  }
  if (!armed || armed.ok !== true || typeof armed.turn_id !== "string"
      || !/^[0-9a-f]{32}$/i.test(armed.turn_id)
      || typeof armed.prompt_marker !== "string"
      || armed.prompt_marker !== `[[SOVEREIGN_VOICE_CHAT_V2:${armed.turn_id}]] `
      || armed.payload !== `${armed.prompt_marker}${body}`) {
    return _no(false, `the supervisor arm failed or returned a malformed turn${armed && armed.reason
      ? ` (${armed.reason})` : ""} — nothing was written`, { flattened, pane_state });
  }
  const payload = armed.payload;
  const cancelAuthority = (reason) => {
    try { return io.cancelAuthority(armed.turn_id, reason) === true; }
    catch { return false; }
  };
  const mark = (why) => io.setResidue({ excerpt: body.slice(0, 60), why });
  let bodyTaken = false;
  try {
    bodyTaken = io.write(payload) === true;
  } catch (e) {
    cancelAuthority("body write raised after possible partial delivery");
    mark("body write raised after possible partial delivery");
    return { written: true, submitted: false, flattened, pane_state,
             reason: `the conductor body write failed after possible partial delivery (${e.name || "Error"}: `
               + `${e.message}) — the next spoken utterance is blocked` };
  }
  if (!bodyTaken) {
    cancelAuthority("the session had no live ConPTY handle");
    return _no(false, "the session has no live ConPTY handle", { flattened, pane_state });
  }
  const deadline = io.now() + SUBMIT_ECHO_TIMEOUT_MS;
  let echo = echoedInOrder("", payload);
  let window = "";
  let lost = false;
  for (;;) {
    const w = io.emittedSince(from);
    if (w === null || w === undefined) { lost = true; break; }
    window = w;
    echo = echoedInOrder(window, payload);
    if (echo.echoed || io.now() >= deadline) break;
    await io.sleep(SUBMIT_ECHO_POLL_MS);
  }
  if (lost) {
    cancelAuthority("echo window lost before submit");
    mark("echo window lost");
    return { written: true, submitted: false, flattened, pane_state,
             echo: { matched: 0, total: echo.totalSegments, ratio: 0, first_missing: null, window: "lost" },
             reason: "the pane's output outran the echo window (its scrollback trimmed the bytes this "
               + "shell was watching), so the submit key was withheld — it would otherwise be confirmed "
               + "by output that is not this utterance's echo" };
  }
  const echoProbe = { matched: echo.matchedSegments, total: echo.totalSegments, ratio: echo.ratio,
                      first_missing: echo.firstMissingSegment,
                      // the window this verdict was reached in. "appended" is the only safe one; a
                      // reader (and the receipt) can see which one was used instead of trusting main.
                      window: "appended", window_bytes: window.length };
  if (!echo.echoed) {
    cancelAuthority(`echo incomplete (${echo.matchedSegments}/${echo.totalSegments})`);
    mark(`echoed ${echo.matchedSegments}/${echo.totalSegments}`);
    return { written: true, submitted: false, flattened, echo: echoProbe, pane_state,
             reason: `the conductor pane echoed ${echo.matchedSegments}/${echo.totalSegments} of the `
               + `utterance within ${SUBMIT_ECHO_TIMEOUT_MS}ms — the submit key was withheld (it would `
               + "otherwise answer whatever the pane is showing)" };
  }
  // The session can end while we wait (an exit, a kill, lost supervision).
  let submitTaken = false;
  try {
    submitTaken = !io.isTerminal() && io.write("\r") === true;
  } catch (e) {
    cancelAuthority("submit key write raised");
    mark("submit key write raised");
    return { written: true, submitted: false, flattened, echo: echoProbe, pane_state,
             reason: `the submit key failed (${e.name || "Error"}: ${e.message}) — the body may remain `
               + "in the input and the next spoken utterance is blocked" };
  }
  if (!submitTaken) {
    cancelAuthority("session ended before submit");
    mark("session ended before the submit key");
    return { written: true, submitted: false, flattened, echo: echoProbe, pane_state,
             reason: "the session ended before the submit key" };
  }
  // Phase 17C `.disarm` (spec-audit M-6): THE TURN MUST STILL BE THE ONE WE ARMED.
  //
  // A voice turn is armed here, before the body write, and only becomes ACTIVE when the CLI's own
  // `UserPromptSubmit` presents the exact payload back to the supervisor. `.disarm` gave the operator
  // a way to end a turn — their next keystroke — and that window now overlaps this one: an operator
  // who releases push-to-talk and immediately touches the keyboard clears the PENDING turn, after
  // which the marked prompt is (correctly, fail-closed) blocked and the model never sees the
  // utterance. Returning `submitted: true` there would render "Delivered to conductor" for something
  // the conductor was never given — the exact fabrication `.close` added this write record to end.
  //
  // So the delivery reports what the supervisor actually holds. The vendor's hook round trip takes a
  // moment, so the fate is POLLED to a bound rather than read once — reading it immediately would
  // call every healthy delivery "pending".
  //
  // WHAT `vendor_reported_submission` IS, since the badge is drawn from it (U180). It is the CLI's
  // own `UserPromptSubmit` hook presenting the exact armed payload back to the supervisor. The child
  // holds both the payload and the bearer, so this is its claim ABOUT ITSELF: it could present the
  // marked payload without the prompt ever reaching the model, and the echo that corroborates it is
  // also its own output. For the RESTRICTION that direction is safe — a forged admission arms a
  // denial against itself — but for the DELIVERY CLAIM it is the unsafe one, so the fate is named
  // for the fact that measured it and the operator's badge says whose claim it is. The second fact
  // main measures for itself (the submit key taken by a live ConPTY handle) is necessary and not
  // sufficient: it says the bytes left, not that a model received them.
  //
  // ONLY that fate is a delivery. The first draft of this reported a turn still PENDING at the
  // deadline as submitted, on the reasoning that the key was delivered and nothing had ended the
  // turn. That is fail-OPEN on an answered negative (spec-audit M-A): `pending` is the supervisor
  // saying "the CLI has NOT presented this payload back to me", and it was being treated as better
  // news than `unavailable`, which knows strictly less. Buildout §4 says fail closed on ambiguity,
  // and the badge reads `submitted` alone — so a late admission would otherwise leave a permanent
  // "Delivered to conductor" for an utterance that was voided a moment later.
  const readFate = () => {
    if (typeof io.turnFate !== "function") return "unavailable";
    try { return io.turnFate(armed.turn_id); } catch { return "unavailable"; }
  };
  let fate = readFate();
  const fateDeadline = io.now() + SUBMIT_ADMIT_TIMEOUT_MS;
  while (fate === "pending" && io.now() < fateDeadline) {
    await io.sleep(SUBMIT_ECHO_POLL_MS);
    fate = readFate();
  }
  if (fate !== "vendor_reported_submission") {
    // WHY it is not a delivery, in the operator's words — `ended` collapsed four causes while the
    // operator was told one of them (spec-audit M-C). What this does NOT assert is where their text
    // went: whether a vendor CLI restores a hook-blocked prompt to its input box or consumes it is
    // not pinned by anything in this repo (M-B), so the operator is pointed at the pane rather than
    // told what it contains.
    const why = {
      ended_by_operator: "you ended the voice turn (a keystroke, or Ctrl+Shift+Escape) before the "
        + "conductor accepted the utterance, so it was NOT delivered",
      ended_by_process_exit: "the conductor session ended before it accepted the utterance, so it "
        + "was NOT delivered",
      ended_by_cancel: "the voice turn was cancelled before the conductor accepted the utterance, "
        + "so it was NOT delivered",
      ended: "the supervisor no longer holds this voice turn, so the utterance was NOT delivered",
      pending: `the conductor had not accepted the utterance ${SUBMIT_ADMIT_TIMEOUT_MS}ms after the `
        + "submit key, so this delivery is UNCONFIRMED — it may still land",
      unavailable: "the submit key was sent, but this shell could not ask whether the supervisor "
        + "still held the voice turn, so the delivery is UNCONFIRMED",
    }[fate] || `the voice turn's state is ${fate}, so the delivery is UNCONFIRMED`;
    // Every non-delivery marks the residue, including the two UNCONFIRMED ones (spec-audit m-C):
    // the body may be sitting in the input, and splicing the next utterance onto it is the failure
    // that record exists to prevent. The pending turn is NOT cancelled — it may still be admitted.
    mark(fate);
    return { written: true, submitted: false, flattened, echo: echoProbe, pane_state, turn_fate: fate,
             reason: `${why} — check pane ${paneId} before speaking again` };
  }
  return { written: true, submitted: true, flattened, echo: echoProbe, pane_state, turn_fate: fate,
           // the operator's badge reads this, so it travels with the claim (U180)
           submission_basis: "vendor_reported",
           authority_boundary: {
             schema: boundary.schema,
             broker_schema: boundary.broker_schema,
             non_executing_voice_turns: true,
             enforced_by_supervisor_process: true,
             turn_id: armed.turn_id,
           },
           reason: `written to conductor input (echo-confirmed ${echo.matchedSegments}/`
             + `${echo.totalSegments}); the conductor CLI reported the prompt as submitted` };
}

module.exports = {
  deliverChat, operatorInputResolvesResidue, supervisorEnforcedBoundary,
  SUBMIT_ECHO_TIMEOUT_MS, SUBMIT_ECHO_POLL_MS,
  // exported so a test (and a receipt) can name the bound the admit check depends on (spec-audit m-D)
  SUBMIT_ADMIT_TIMEOUT_MS,
};
