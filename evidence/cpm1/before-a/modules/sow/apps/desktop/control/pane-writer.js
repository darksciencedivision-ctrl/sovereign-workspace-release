"use strict";
/**
 * The SYSTEM→PANE write path, and the one gate on it (U328, Phase 19 unit 19.3).
 *
 * WHAT THIS IS FOR. A provider CLI asks for workspace trust, for authentication, or for permission
 * to run a Sovereign MCP tool by drawing a NUMBERED MENU in its ConPTY with the permissive option
 * highlighted. Answering it takes one carriage return. Until this module existed, every system
 * write — peer-message notices, debate turns, worker deadline reports, the conductor's own
 * readiness prompt — ended in `manager.write(paneId, "\r")` with nothing having looked at the
 * screen. `controlAssignTask` gated its assignment on the worker's operational state; `notifyNode`
 * and `runConductorReadiness` gated nothing at all, and the conductor pane is the pane the operator
 * converses in (OP-8 §13).
 *
 * THE STANDARD IS "UNABLE", NOT "UNLIKELY" — AND ONE HALF OF IT IS MET. Invariant 1 reserves final
 * authority to the operator and D-P18-13 records that a provider's own accept-mode is not operator
 * approval. The half that IS met is structural: the gate is on the write path rather than on its
 * callers, so no system caller can reach the PTY without being classified, and a future caller
 * cannot forget it.
 *
 * THE VERDICT, AND WHAT THE WINDOW BOUGHT (U363, unit 19.4-followon). `classifyProviderScreen` is a
 * DENYLIST of six PROVIDER-STATE phrase families, and it returns null for everything else, which
 * this module used to write into. The gate-validator at the 19.3 review demonstrated it against this
 * module: of ten realistic permission screens, NINE were allowed through, including "Do you want to
 * proceed? 1. Yes 2. Yes, and do not ask again". 19.3 recorded why it did not simply add patterns:
 * on a whole-buffer read a broader denylist trades an unanswered modal for a permanently mute pane
 * — one delivered body containing trigger text pins that pane for the life of its scrollback.
 *
 * The window came first (this unit bounds it, below), so the verdict is now affordable, and
 * `modalAffordance` (`control/modal-affordance.js`) is it: the AFFORDANCE families — "do you want to
 * proceed", a numbered yes/no selection, `(y/N)`, "press enter to continue", "yes, and don't ask
 * again", and the two authority-expanding mode banners — refuse the write. Those patterns are not
 * newly guessed: they are the ones `voice/pane-state.js` has enforced on the OPERATOR's voice since
 * 17C, moved rather than rewritten, and the asymmetry 19.3 named (the operator's voice gated more
 * strictly than a system notice) is what this removes. Their provenance is stated exactly where they
 * live (`control/modal-affordance.js`): several were read off this host's live provider panes, three
 * are the same families written out and evidenced on no real pane.
 *
 * WHAT IS STILL NOT MET, stated because a denylist that got longer is not a denylist that ended.
 * `voice/pane-state.js` additionally demands POSITIVE evidence — the pane's text input must be the
 * most recent chrome drawn — and refuses on `unknown`. This module does NOT, because its input
 * markers are `claude`-shaped and a positive-evidence rule here would mute every pane whose vendor
 * chrome this shell has never seen (codex, grok, antigravity), which is the same product failure in
 * the other direction. So the property is "cannot answer a modal this shell RECOGNISES, as the
 * pane's CURRENT screen stood at the last read before each keystroke". Stronger than 19.3's, still
 * short of "cannot answer a modal": U363 stays open for the positive-evidence half, with the
 * per-provider input chrome it needs — and, per [[U395]], "the pane's CURRENT screen" below means
 * the last `TAIL_LINES` non-blank lines of it, which is not the same sentence.
 *
 * WHY THE SUBMIT KEY IS CHECKED AGAIN. The provider draws its permission prompt IN RESPONSE to the
 * body it was just handed. Checking once, before the body, leaves open precisely the window the
 * modal appears in — and the body is harmless noise while the Enter behind it is the answer. Every
 * write is therefore gated, the submit keys included.
 *
 * WHY OUR OWN ECHO IS EXCLUDED. The pane echoes what we wrote, so a prompt that quotes a structured
 * failure could classify the pane against us and withhold its own submit key forever. The screen
 * read before a submit key has our body removed (see `withoutOwnEcho`). A real modal in the same
 * screen still refuses, unless our body's own character sequence happens to span it — which the
 * shipped call sites' long fixed templates do not, and which is bounded but not prevented (U360).
 *
 * SCREEN TEXT IS THE WEAKEST SIGNAL AND IT IS THE ONLY ONE HERE — SO IT IS READ AS A SCREEN NOW
 * (U373 residual, this unit). Until this unit the gate classified a whole `buffer.snapshot()`, 256 KB
 * of scrollback, so text that merely MENTIONED "not signed in" refused every later system write to
 * that pane for the life of its scrollback: not one withheld message retried by the next
 * notification, a mute pane. `debate.proposition` and a task's `objective`/`constraints` go into
 * those bodies verbatim, so a model's own words could do it — and `worker-readiness.js`'s negative
 * control (a healthy connected worker stays READY) was true of that module and FALSE of the shell,
 * because the worker's prompt was undeliverable and it stalled (U373's residual, asserted in the
 * suite and measured in leg F of the 19.4 receipt).
 *
 * The gate now reads the pane's CURRENT SCREEN through the same bounded reader readiness uses —
 * `createScreenWindow` over `RingBuffer.sliceFrom()`, injected by `main.js` as the very same object
 * (`paneScreenFromWindow`), never a second reader that could drift from it. A modal is what the pane
 * is SHOWING; a modal that has scrolled out of the tail is not up, and a sentence somebody typed
 * twenty screens ago was never evidence about now. `sliceFrom` answers NULL rather than widening
 * when the region cannot be reproduced exactly, and this module maps that null to UNREADABLE — "I
 * cannot see" refuses, exactly as it did before (invariant 27, Buildout Directive §4).
 *
 * SAY WHAT THAT COSTS, because bounding a gate is a LOOSENING and the direction matters: every
 * screen the whole-buffer read refused and the tail does not is now written into. Most of that is
 * the intended effect (it is how the stalled healthy worker gets its prompt) and it is why the
 * verdict was widened in the same unit rather than later. But the first version of this paragraph
 * described the residual as a modal "pushed past" the bound by LATER output, and the round-1
 * validator measured a case that needs no later output at all: the window is the last `TAIL_LINES`
 * NON-BLANK lines, so a full-screen repaint that draws a live trust modal near the TOP of a pane
 * taller than that bound leaves the modal outside it, on the current screen, writable. `TAIL_LINES`
 * is 80 for that reason (the spawn default is 30 rows and the renderer fits larger), which covers
 * the spawn default with margin and not every possible pane. The honest statement of what this gate
 * reads is "the last 80 non-blank lines OF THE LAST 16 KB" — and that byte budget is spent on the
 * RAW stream, escape sequences included, so a heavily-repainting TUI buys fewer lines with it than
 * plain text does. That is not a remote case: the round-2 validator measured a 30-row full-screen
 * repaint with per-cell SGR colouring at 32,596 bytes, twice the budget, which drops a live modal
 * at row 5 of a SPAWN-DEFAULT pane out of the window and lets this gate write into it. The gap
 * between what this reads and "the current screen" is [[U395]] — a row-aware bound closes the
 * geometry half, the byte budget and the missing emulator ([[U372]]) are the rest, and at the
 * default geometry it is the BYTE half that bites first.
 *
 * Dependencies are injected (`createPaneWriter(io)`) for the same reason `voice/conductor-write.js`
 * takes a binding: `main.js` cannot be required in a test (U338), so anything that could be got
 * wrong lives here where it can be driven, and `main.js` keeps only the calls that build it.
 */
const { classifyProviderScreen, plainScreen } = require("./provider-readiness");
const { modalAffordance } = require("./modal-affordance");
const { traitsFor } = require("./provider-traits");

/** How many paste-settle intervals a write may wait for its own echo to finish rendering before it
 *  judges the submit key (U364). Bounded so a provider that renders our body somewhere this shell
 *  cannot see it costs a settle window, not a hang. */
const ECHO_SETTLE_POLLS = 8;

/** The refusal for a pane whose screen this shell cannot read. Fail closed on ambiguity (Buildout
 *  Directive §4): a pane whose modal state cannot be ruled out is a pane no keystroke may enter. */
const UNREADABLE = Object.freeze({
  state: "STALLED",
  terminal_state: "PANE_SCREEN_UNREADABLE",
  reason: "the pane screen could not be read, so no write into it can be shown to be safe",
});

/** The refusal for a pane whose CURRENT screen is showing something a keystroke would answer (U363).
 *  `state` is a real `PROVIDER_STATES` value because callers put it in a node's operational state;
 *  the terminal state is what distinguishes it from a provider that needs SETUP — nothing here says
 *  the provider is broken, only that this shell may not type into it right now. */
const modalRefusal = (affordance) => Object.freeze({
  state: "PROVIDER_SETUP_REQUIRED",
  terminal_state: affordance.kind === "unsafe_mode"
    ? "PANE_AUTHORITY_EXPANDING_MODE" : "PANE_AWAITING_OPERATOR_DECISION",
  reason: affordance.kind === "unsafe_mode"
    ? `the pane is in an authority-expanding interaction mode ("${affordance.text}"), so a system `
      + "write would be executing under a permission the operator did not give (D-P18-13)"
    : `the pane's screen is showing a confirmation or selection prompt ("${affordance.text}"), so a `
      + "keystroke would be answering it (invariant 1: the operator holds final authority)",
});

/**
 * The decision, as a pure function: a refusal object, or null when the write may proceed.
 * `screenReadable` must be the literal `true` — "probably readable" is the ambiguity this fails on.
 *
 * ORDER: the provider-state families first, because when a screen says BOTH "not signed in" and
 * "press enter to continue" the useful thing to report is the authentication, not the keypress. Then
 * the affordance. Both refuse; only the reason differs.
 */
function paneWriteRefusal({ provider = null, screenReadable = false, screen = "" } = {}) {
  if (screenReadable !== true) return { ...UNREADABLE };
  const state = classifyProviderScreen(provider, screen);
  if (state) return state;
  const affordance = modalAffordance(plainScreen(screen));
  return affordance ? { ...modalRefusal(affordance) } : null;
}

/**
 * The pane's CURRENT screen, read through the shell's ONE bounded window (U373 residual, unit
 * 19.4-followon). `window` is `createScreenWindow`'s object — `main.js` passes the SAME instance it
 * gives readiness, so the gate and the state machine cannot come to read different things.
 *
 * Fail-closed mapping, and it is the whole reason this adapter exists rather than a `.text` access:
 * `answerable: false` — no session, no buffer, a trimmed region, a buffer that threw — becomes
 * UNREADABLE, which refuses. Only an exactly-reproduced window is a screen this gate will judge.
 */
function paneScreenFromWindow(window, options = {}) {
  return (paneId) => {
    let read = null;
    try { read = window.read(paneId, options); } catch { read = null; }
    if (!read || read.answerable !== true) {
      return { readable: false, text: "", reason: (read && read.reason) || null };
    }
    return { readable: true, text: read.text };
  };
}

/** The pane's provider id: its own governed chrome first, the conductor descriptor for pane 1. */
function paneProviderResolver({ chromeFor, conductorPaneId, conductorProvider }) {
  return (paneId) => {
    const chrome = chromeFor(paneId) || {};
    if (chrome.provider) return chrome.provider;
    const conductor = conductorPaneId();
    // `null === null` would route every unknown pane through the conductor branch.
    if (paneId !== null && paneId !== undefined && paneId === conductor) return conductorProvider();
    return null;
  };
}

/** Regex-escape one character of a body we are removing from a screen. */
const escapeChar = (ch) => ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * The screen with our own body removed, so the pane's echo of it cannot classify against us.
 *
 * The first version of this split on the exact body string, and the in-Electron receipt
 * (`PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.close_20260810T111123Z.json`, leg B) falsified
 * it on the first real ConPTY it met: `buffer.snapshot()` is the raw PTY stream, so PSReadLine's
 * syntax colouring puts escape sequences INSIDE the echoed line and the terminal wraps it. The
 * exact substring is not there to find, the echo classified against us, and a notice quoting modal
 * text had its own submit key withheld — the fail-closed direction, and still a message that never
 * arrived. Recorded as U360; this is the fix and the receipt is its falsification.
 *
 * So: strip the escapes first (`plainScreen`, the same normaliser the classifier uses), then match
 * the body character by character with whitespace allowed between characters, which covers a wrap
 * anywhere including mid-token.
 *
 * State the direction correctly, because the first version of this paragraph had it backwards and
 * the review caught it: removing MORE text before classification makes the gate accept MORE screens,
 * not fewer. Every screen the exact version accepted, this one accepts; leg B of the 19.3 receipt is
 * one it refused and this one accepts, which is the entire point of the change. The new acceptances
 * are bounded to screens that literally contain our own body's character sequence in order with only
 * whitespace between characters — nothing in the code confines the deletion to our echo's REGION, so
 * a coincidental match is possible in principle, and short or model-supplied bodies widen it. On the
 * shipped call sites (long fixed-prefix templates) no such deletion is reachable; a body-length
 * floor and a cap on how much of a screen this may delete would make the bound enforced rather than
 * merely likely (U360).
 */
function withoutOwnEcho(text, body, onFallback = null) {
  const s = plainScreen(text);
  const plainBody = plainScreen(body).trim();
  if (!plainBody) return s;
  const tolerant = plainBody.split("").filter((ch) => !/\s/.test(ch))
    .map(escapeChar).join("\\s*");
  try {
    return s.replace(new RegExp(tolerant, "gi"), " ");
  } catch (e) {
    // V8 refuses a pattern past its size limit, and a body has no length cap (a task objective or a
    // debate proposition arrives here verbatim). The fallback is the EXACT match U360 was opened
    // for — the shipped defect, restored — so it may not happen silently (invariant 27).
    if (typeof onFallback === "function") onFallback(String((e && e.message) || e));
    return s.split(String(body)).join(" ");
  }
}

/**
 * One ESCAPE RUN - CSI, OSC, a two-character sequence, or a bare ESC that begins none of them. The
 * whole run is matched so its PAYLOAD leaves with it: stripping the ESC byte alone would remove the
 * one character that is a control and leave `[2J` behind as visible text, which is the wrong half.
 */
const ESCAPE_SEQUENCE = new RegExp(
  "\\u001b\\[[\\u0030-\\u003f]*[\\u0020-\\u002f]*[\\u0040-\\u007e]"   // CSI ... final byte
  + "|\\u001b\\][^\\u0007\\u001b]*(?:\\u0007|\\u001b\\\\)?"           // OSC ... BEL | ST
  + "|\\u001b[\\u0040-\\u005f]"                                       // ESC + one Fe
  + "|\\u001b", "g");                                                 // a bare ESC

/** The C0 controls (and DEL) left once the escape runs are gone. CR and LF are deliberately NOT
 *  here: they are collapsed to a SPACE above, because deleting them would join two sentences into
 *  one word and silently change what the body says. */
const RESIDUAL_CONTROLS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;

/**
 * Flatten a body that did NOT originate on the operator's OS input path (W-02, R-02).
 *
 * `taskPrompt` (`control/application-control.js:23`) and the debate prompt (`:311`) interpolate
 * `task.objective`, `constraints` and `debate.proposition` verbatim, and the validation behind them
 * is `.strip()` only (`mcp_server/collaboration_service.py:116-124`). An embedded CR therefore
 * SUBMITS the fragment before it, which lets the model that wrote the body answer the victim
 * provider's own permission modal - the property this module exists to make impossible, reached
 * from the one direction the gate cannot see, because the gate classifies the SCREEN and this is
 * the BODY. An embedded ESC/CSI run additionally repaints the pane, including the very region the
 * readiness classifier reads.
 *
 * This lives at the WRITE BOUNDARY rather than at each call site on purpose: per-call-site
 * flattening is how the NEXT interpolation site gets missed. The CR/LF half is
 * `voice/conductor-write.js:116-117` moved rather than rewritten - the operator's own voice has
 * been flattened this way since 17C, and a model's words may not be trusted further than the
 * operator's own. That module keeps its copy because it guards a DIFFERENT boundary (voice ->
 * conductor) and reports `flattened` to its caller; this is not a second policy on this path.
 *
 * The submit key is NOT flattened here. It is written separately by this module and gated
 * separately (see "WHY THE SUBMIT KEY IS CHECKED AGAIN"); this function only ever sees a body.
 */
function flattenBody(body) {
  const raw = String(body === null || body === undefined ? "" : body).replace(/[\r\n]+$/, "");
  return raw
    .replace(ESCAPE_SEQUENCE, "")
    .replace(/[\r\n]+/g, " ")
    .replace(RESIDUAL_CONTROLS, "");
}

function createPaneWriter(io) {

  function refusalOn(paneId, ownBody) {
    const screen = io.paneScreen(paneId);
    const readable = !!screen && screen.readable === true;
    return paneWriteRefusal({
      provider: io.providerFor(paneId),
      screenReadable: readable,
      screen: readable
        ? withoutOwnEcho(screen.text, ownBody,
          (why) => io.log(`pane write echo-exclusion FELL BACK to exact matching for ${paneId}: `
            + `${why} (U360) — a wrapped echo may now refuse its own submit key`))
        : "",
    });
  }

  /** The refusal a caller must surface before it reports a generic failure. */
  const refusalFor = (paneId) => refusalOn(paneId, null);

  /** Is our whole body on the screen — i.e. does the exclusion have something complete to remove?
   *  Takes the same fallback logger as `refusalOn`: the round-2 review found this call passing none,
   *  so on this path the restored U360 defect happened SILENTLY, thirty lines below a comment saying
   *  it may not (invariant 27). It cannot change a verdict — a false answer here only spends more of
   *  the bounded wait — but a guard that degrades unobservably is the thing this phase keeps finding. */
  function echoIsWhole(paneId, body) {
    const screen = io.paneScreen(paneId);
    if (!screen || screen.readable !== true) return false;
    const excluded = withoutOwnEcho(screen.text, body,
      (why) => io.log(`pane echo-completeness check FELL BACK to exact matching for ${paneId}: `
        + `${why} (U360) — the settle wait may run its full bound`));
    return excluded !== plainScreen(screen.text);
  }

  /**
   * Every byte the system sends to a pane passes here. Returns
   * `{ written, refused, residue_possible }` — a governed refusal and a dead PTY handle are
   * different facts HERE. Three of the four call sites then collapse this record to its boolean
   * (`main.js`'s `writePanePrompt`) and report a generic delivery failure, so the distinction is
   * available and not yet used: U361 owns closing that, and it is not claimed as done.
   */
  async function writePrompt(paneId, prompt) {
    const before = refusalOn(paneId, null);
    if (before) {
      io.log(`pane write REFUSED for ${paneId}: ${before.reason} (U328)`);
      return { written: false, refused: before, residue_possible: false };
    }
    // W-02: the body is flattened HERE, once, before any byte of it can reach the PTY. Every later
    // use of it below is the SAME bytes the pane actually received - an echo exclusion that looked
    // for the UNflattened text would be searching the screen for something never written.
    const body = flattenBody(prompt);
    if (!io.write(paneId, body)) return { written: false, refused: null, residue_possible: false };

    // The body is out. From here a refusal means the submit key is WITHHELD and the body is sitting
    // in the provider's input box — the caller is told so it does not read this as "nothing happened".
    const submit = async () => {
      const now = refusalOn(paneId, body);
      if (now) {
        io.log(`pane submit WITHHELD for ${paneId}: ${now.reason} (U328) — body may remain in the input`);
        return { written: false, refused: now, residue_possible: true };
      }
      return null;
    };

    await io.sleep(io.pasteSettleMs());
    // U364: the exclusion can only remove a body that is COMPLETELY on the screen. A pane caught
    // mid-render leaves a FRAGMENT of our own text, and a fragment can classify — measured on this
    // host, where the same leg passed one run and failed the next purely on echo timing. So when the
    // screen would refuse AND our echo is not yet whole, wait for it, bounded. Nothing about the
    // verdict changes: the bound expiring means we classify whatever is on the screen, exactly as
    // before, fail-closed. A screen that is already clean breaks out on the first look — but say
    // what that costs, because the first version of this line said "pays nothing" and the 19.4
    // round-2 review priced it: ONE extra `refusalOn`, i.e. one bounded window read (≤TAIL_BYTES,
    // ≤TAIL_LINES) plus one tolerant-regex pass over it. A refused write pays that up to
    // 2×ECHO_SETTLE_POLLS times plus the settle sleeps — ~4 s at the 500 ms default — synchronously
    // on the main thread. The 1–14 ms per pass measured on this host for bodies of 200–20 000
    // characters was measured when a pass was a 256 KB SNAPSHOT, so it is a ceiling this code can no
    // longer reach and is not a measurement of what it does now. The sleeps dominate either way;
    // that is a bound, not a benchmark, and no receipt times it yet (U370).
    for (let i = 0; i < ECHO_SETTLE_POLLS; i += 1) {
      if (refusalOn(paneId, body) === null || echoIsWhole(paneId, body)) break;
      await io.sleep(io.pasteSettleMs());
    }
    const beforeEnter = await submit();
    if (beforeEnter) return beforeEnter;
    if (!io.write(paneId, "\r")) return { written: false, refused: null, residue_possible: true };

    if (traitsFor(io.providerFor(paneId)).submit_confirm_enter) {
      // Codex confirms a multi-character paste with the first Enter and submits with the next one.
      // That second Enter is a keystroke like any other and is gated like any other.
      // 19.6 ([[U393]] MINOR-1): which providers behave that way is DECLARED in `provider-traits.js`
      // rather than compared here, so a provider this build has never heard of gets one Enter by a
      // stated rule instead of by the absence of a branch.
      await io.sleep(io.submitConfirmMs());
      const beforeConfirm = await submit();
      if (beforeConfirm) return beforeConfirm;
      return { written: io.write(paneId, "\r"), refused: null, residue_possible: false };
    }
    return { written: true, refused: null, residue_possible: false };
  }

  /**
   * Deliver a prompt to a node's pane. Keeps the `{ node_id, pane_id, written }` shape its callers
   * already read, and adds the reason a refusal happened so a withheld notice is not silent.
   */
  async function notifyNode(nodeId, prompt) {
    const conductor = io.conductorTarget();
    const paneId = conductor && conductor.nodeId === nodeId
      ? conductor.paneId : io.workerPaneFor(nodeId);
    if (paneId === null || paneId === undefined) {
      return { node_id: nodeId, pane_id: null, written: false, refused: null,
        provider_terminal_state: null, residue_possible: false };
    }
    const result = await writePrompt(paneId, prompt);
    return {
      node_id: nodeId, pane_id: paneId, written: result.written,
      refused: result.refused ? result.refused.reason : null,
      provider_terminal_state: result.refused ? result.refused.terminal_state : null,
      residue_possible: result.residue_possible === true,
    };
  }

  return { refusalFor, writePrompt, notifyNode };
}

module.exports = {
  paneWriteRefusal, paneScreenFromWindow, paneProviderResolver, createPaneWriter, withoutOwnEcho,
  modalRefusal, flattenBody,
};
