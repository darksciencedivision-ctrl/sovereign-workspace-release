"use strict";
/**
 * Worker readiness — the ORDER of the signals, and the WINDOW the weakest one may read (U329,
 * Phase 19 unit 19.4).
 *
 * WHAT WAS WRONG. `main.js` decided a live provider's state by keyword-matching `buffer.snapshot()`
 * — the whole retained ring buffer, 256 KB of scrollback — and it did so BEFORE consulting the MCP
 * connection, on a still-running process. Three consequences the cold audit recorded (B4/U329):
 *
 *   - **Sticky state.** Grok's startup promo overlay matches `classifyProviderScreen`; once the
 *     operator dismisses it the text is still in the scrollback, so every later readiness pass
 *     returned `PROVIDER_SETUP_REQUIRED` and never reached the connection check. No transition out
 *     existed except a fresh pane.
 *   - **Self-inflicted false positive.** The shell writes the operator's objective into the pane
 *     verbatim, so an objective reading "investigate why we keep hitting the usage limit on Grok"
 *     classified against Sovereign's own echoed text.
 *   - **Instrument disagreement, resolved the wrong way.** The headless exit-code-first probe passed
 *     for Gemini while the scraper said `AUTH_REQUIRED`, and the acceptance receipt adopted the
 *     scraper.
 *
 * THE RULE THIS RESTORES is `tools/providers/frontier_provider_recon.py:44-49`, quoted exactly
 * because a paraphrase of a binding source is how a rule gets softened: **"failure is determined by
 * exit code first, then structured error fields, then — only on a NONZERO exit — diagnostic text."**
 * That source governs a process that has FINISHED. This module also has to answer for one that is
 * still running, where no exit code exists yet, so it extends the same ordering: the process, then
 * the structured signal, then — only when neither answers — the screen. The extension is this
 * module's, not the cited source's, and the round-2 spec-auditor was right that the earlier
 * rendering blurred them. `orderedProviderSignal` is that order expressed once, in
 * a function a test can drive, rather than as the sequence of `if`s in a 3 000-line file nobody can
 * require (U338). A worker whose process is alive and whose MCP session is connected reaches its
 * readiness TURN without anything here classifying its screen, and answers it without anything here
 * classifying its screen: that is the negative control the register asked for. Inside the turn a
 * worker that has NOT yet answered does have its screen read, floored at the turn's own mark — see
 * "WHAT KILLS THE STICKY STATE" below, which is the precise version of this sentence.
 *
 * EVERY READ IN THIS FILE'S CALL GRAPH IS NOW BOUNDED, and the history is why that sentence is worth
 * a paragraph. The U328 write gate (`pane-writer.js`) decides whether a keystroke may ENTER a pane,
 * because a modal it fails to see is a modal the loop might answer (invariant 1). It used to answer
 * that from `buffer.snapshot()`, the entire retained scrollback, and the first version of this module
 * took that refusal and made it the WORKER'S STATE — so a healthy, connected worker whose scrollback
 * merely MENTIONED "not signed in" was reported AUTH_REQUIRED, and the audited pin survived the
 * reorder that was supposed to remove it. Both mandatory reviewers found it independently at the 19.4
 * gate. Two things fixed it, in two units: the gate's answer is used for exactly what it is evidence
 * of — *we may not type here yet* — and only the bounded window below may state a worker's
 * CONDITION (19.4); and the gate itself now reads that same bounded window (19.4-followon, [[U373]]'s
 * residual), so a mention twenty screens back no longer withholds a healthy worker's prompt and the
 * negative control holds END-TO-END rather than at module level.
 *
 * THE CALL SITE THAT IS NOT THIS MODULE'S, kept named rather than left to be inferred (round-2
 * spec-auditor, MAJOR-3): `main.js`'s conductor readiness path promotes the gate's refusal straight
 * to the conductor node's operational state. That promotion is unchanged; TWO things changed
 * underneath it, and an earlier version of this paragraph named only the first.
 *
 * The refusal is now a statement about the pane's CURRENT screen instead of its whole transcript,
 * which is what made the promotion wrong — that half NARROWS it. But the refusal SET also got wider
 * in the same unit (the affordance families), and through this same promotion that half WIDENS what
 * the conductor reports: a conductor pane merely showing `(y/n)`, "press enter to continue" or a
 * numbered yes/no now badges the conductor node `PROVIDER_SETUP_REQUIRED` and returns not-ready, on
 * a single-shot path with no retry, where before this unit it did not. Nothing is TYPED into that
 * pane either way — the gate is doing its job — but the operator reads a provider-setup label for a
 * pane whose provider is fine. [[U381]](a) is therefore narrowed in one direction and widened in the
 * other, not closed: it is still the gate's verdict wearing a readiness label, and the shape this
 * module uses (report the withheld write AS a withheld write) has not been carried to the conductor.
 * Round-2 spec-auditor, MEDIUM-2.
 *
 * THE WINDOW. Where screen text genuinely is the only signal on a running process, it is read
 * through `RingBuffer.sliceFrom()` (`terminal/session/ring-buffer.js:45-50`), never `snapshot()`.
 * The classification window is the pane's **tail**: at most `tailBytes` from the end of the stream,
 * then at most `tailLines` lines of that. A modal is what the pane is showing NOW — the last thing
 * it drew, with nothing after it — and that, not "everything it has ever said", is the question the
 * classifier is being asked. `sliceFrom` answers NULL rather than widening when the region cannot be
 * reproduced exactly, and that null is carried through as `answerable: false`: "I cannot see" and
 * "nothing is wrong" must not be the same value (invariant 27, Buildout Directive §4 fail-closed).
 *
 * A first version of this floored the window at a MARK taken when the readiness run began, so that
 * nothing said before we started watching could classify. Its own suite falsified it: a provider
 * sitting on a trust modal drawn at spawn emits nothing afterwards, so the window was empty, the
 * modal was invisible, and the run reported a bare `mcp_readiness_timeout` for a pane whose screen
 * said exactly what was wrong. The mark survives for what it is genuinely good for — counting OUR
 * OWN nonce (`since()`), which must not match an earlier run's — and the tail does the classifying.
 *
 * WHAT KILLS THE STICKY STATE is therefore the ORDER, not the window: a worker whose MCP session is
 * connected is READY without this module classifying its screen at all, so a dismissed overlay still
 * sitting in the scrollback of a working provider decides nothing. The screen only gets a vote when
 * the process is alive AND the provider is not talking to us — which is when something really is
 * wrong — and inside a readiness TURN that vote is further floored at the turn's own mark, because
 * "the provider drew this in answer to what we just typed" and "these words are somewhere in the
 * transcript" are different claims and only the first is evidence about now.
 *
 * WHAT THIS DOES NOT DO, stated because a receipt outlives the prose around it: this is a BYTE
 * window over a raw PTY stream, not a terminal emulator. A provider that repaints with cursor
 * addressing and emits fewer than a tail's worth while doing so leaves a dismissed overlay's bytes
 * inside the tail, so on a pane whose MCP session is ALSO down the run can still name the overlay
 * rather than the disconnection. That is a diagnostic imprecision on an already-failing pane, not a
 * pin, and it is re-derived from scratch on every run. The renderer holds a real xterm buffer that
 * would answer exactly; the main process cannot read it synchronously. Recorded as U372.
 *
 * AND THIS UNIT MADE THAT WINDOW WIDER, which the change was recorded as a one-sided widening
 * (round-2 gate-validator, MEDIUM-3). `tailLines` 24 → 80 was reasoned about for the WRITE GATE,
 * where reading more can only refuse more. For THIS caller it also means a dismissed overlay stays
 * classifiable across 80 non-blank lines instead of 24 — U372's condition, 3.3× wider. The blast
 * radius is what keeps it a diagnostic issue and not a pin: these reads only run when the MCP
 * session is NOT connected, i.e. on an already-failing pane, and `trackObservation` still resets on
 * the first poll whose window no longer classifies. It is recorded here rather than left for a
 * reader to derive from the constant.
 *
 * EXIT PATHS. Every classified state is re-derived on every poll from a fresh window, and a poll
 * whose window no longer classifies RESETS the observation (`trackObservation`) — so an overlay that
 * clears lets the same run continue to READY instead of pinning the worker. A classification must
 * also be seen on `CONFIRM_POLLS` consecutive reads before it becomes the run's verdict, so one
 * transient line cannot terminate a run.
 *
 * Dependencies are injected for the same reason `pane-writer.js` injects its own: `main.js` cannot be
 * required in a test (U338), so everything that can be got wrong lives here where it can be driven,
 * and `main.js` keeps only the bindings.
 */
const {
  classifyProviderScreen, occurrenceCount, plainScreen, structuredProviderFailure,
} = require("./provider-readiness");
const { traitsFor } = require("./provider-traits");
const { sessionEstablished } = require("./sovereign-control-server");
const { observedReadinessEvidence } = require("./readiness-evidence");

/** Poll cadence for both loops. Unchanged from the audited code — this unit changes what is read and
 *  in what order, not how often. */
const POLL_MS = 250;

/** How many consecutive bounded reads must agree before a screen classification becomes a verdict.
 *  One is a glimpse; the shipped code acted on a glimpse of a 256 KB buffer. */
const CONFIRM_POLLS = 2;

/** Tail bounds for the classification window. `tailBytes` bounds the raw PTY slice (escape sequences
 *  included, since the bound is applied before normalisation) and so bounds the COST of every poll;
 *  `tailLines` is the semantic bound — one screen of what survives normalisation, which is what "the
 *  pane is showing this" means. Both bound how far BACK a verdict may reach, never how much the
 *  buffer holds.
 *
 *  `tailLines` was 24 until 19.4-followon, and the round-1 validator of that unit measured what that
 *  cost once the U328 WRITE GATE started reading this same window: `main.js` spawns panes at
 *  `rows: spec.rows || 30` and the renderer then fits them LARGER, so a 24-line window is smaller
 *  than the screen it claims to be, and a full-screen repaint drawing a trust modal at row 5 of 30
 *  put a LIVE modal outside the only window allowed to see it — writable, where the whole-buffer read
 *  it replaced refused. 80 covers the 30-row spawn default with margin. It does NOT cover every pane,
 *  and the ROW count is only half of what crops: the row count of a maximized pane on this host has
 *  never been measured, and the round-2 validator measured the OTHER half on the spawn default
 *  itself — a 30-row full-screen repaint with per-cell SGR colouring is 32,596 raw bytes, twice
 *  `tailBytes`, so the tail holds the bottom half of ONE frame and a live modal at row 5 of a 30-row
 *  pane is written into. (Its calibration sweep: at 4–40 SGR runs per line and 100–240 columns a
 *  frame stays ≤14,580 B and the modal is correctly refused, so the trigger is DENSE styling — a
 *  syntax-highlighted diff view reaches it.) Both halves are [[U395]], recorded rather than rounded
 *  off, and a row-aware bound alone does not close it: at the default geometry the row bound is
 *  already sufficient and the byte budget is what drops the frame. */
const TAIL_BYTES = 16384;
const TAIL_LINES = 80;

const UNREADABLE_WINDOW = Object.freeze({
  answerable: false, text: "", reason: "the pane holds no readable stream buffer",
});

/** The last `max` NON-BLANK lines of a normalised screen ([[U380]], closed by the unit that bounds
 *  the U328 gate's own read — the owner that row named).
 *
 *  WHY IT CHANGED. `plainScreen` strips escape sequences without collapsing what they leave behind,
 *  so a provider that repaints emits runs of blank lines. Counting them spent the bound on nothing:
 *  a modal that IS the current screen could sit at line 30 of a 24-line window, invisible to the
 *  only instrument allowed to state a worker's condition, and the run would report a bare
 *  `mcp_readiness_timeout` for a pane whose screen said exactly what was wrong. Blank lines carry no
 *  classifiable text, so dropping them cannot HIDE anything: this strictly widens what the window
 *  can see, in the fail-closed direction for both callers (readiness classifies more, and the write
 *  gate — which reads through this same function since 19.4-followon — refuses more).
 *
 *  It was NOT done in the 19.4 round-2 remediation, deliberately, because it is a change to what
 *  gets classified and [[U371]] was reverted for smuggling exactly that into a review repair. Its
 *  own unit, its own test, its own receipt: this is that unit. */
function lastLines(text, max) {
  const lines = String(text).split(/\r?\n/);
  if (!Number.isFinite(max)) return lines.join("\n");
  const kept = [];
  for (let i = lines.length - 1; i >= 0 && kept.length < max; i -= 1) {
    if (lines[i].trim()) kept.push(lines[i]);
  }
  return kept.reverse().join("\n");
}

/**
 * A bounded, fail-closed reader over a pane's ring buffer. `bufferFor(paneId)` returns the pane's
 * `RingBuffer` or null; nothing here ever calls `snapshot()`.
 */
function createScreenWindow({ bufferFor, tailBytes = TAIL_BYTES, tailLines = TAIL_LINES }) {
  function bufferOf(paneId) {
    let buffer = null;
    try { buffer = bufferFor(paneId); } catch { return null; }
    if (!buffer || typeof buffer.sliceFrom !== "function"
      || !Number.isInteger(buffer.totalWritten)) return null;
    return buffer;
  }

  /** The stream position to start watching from, or null when this pane cannot be watched at all.
   *  A null mark makes every later read UNANSWERABLE rather than unbounded. */
  function mark(paneId) {
    const buffer = bufferOf(paneId);
    return buffer ? buffer.totalWritten : null;
  }

  /** The exact region from stream position `from` to the end, or `answerable: false`. `maxLines`
   *  keeps the last N lines of it after normalisation. Never widens, never falls back. */
  function region(paneId, from, maxLines) {
    const buffer = bufferOf(paneId);
    if (!buffer) return { ...UNREADABLE_WINDOW };
    if (!Number.isInteger(from) || from < 0) {
      return { answerable: false, text: "", reason: "no stream position was available for this pane" };
    }
    const at = buffer.totalWritten;
    let slice = null;
    try { slice = buffer.sliceFrom(from); } catch { slice = null; }
    if (slice === null) {
      return {
        answerable: false, text: "", from, at,
        reason: "the bounded window is no longer held exactly by the pane buffer",
      };
    }
    const plain = plainScreen(slice.toString("utf8"));
    return {
      answerable: true, from, at, bytes: slice.length,
      text: Number.isFinite(maxLines) ? lastLines(plain, maxLines) : plain,
    };
  }

  /** WHAT THE PANE IS SHOWING NOW: the tail of the stream, bounded in bytes and then in lines. This
   *  is the only window a classification may read. By default it deliberately does NOT start at a
   *  readiness run's mark — a modal drawn before the run began and still up emits nothing afterwards,
   *  and a window that starts after it reports an empty screen for a pane that is plainly stuck.
   *
   *  `notBefore` is the exception, and it is only for callers who have just WRITTEN: inside a turn we
   *  have provoked the pane, so anything the provider has to say about our prompt lands after that
   *  mark, and text from before it is transcript rather than answer. Passing it NARROWS the window
   *  (it is a max against the tail floor), so it can never widen how far back a verdict reaches. */
  const read = (paneId, { maxBytes = tailBytes, maxLines = tailLines, notBefore = null } = {}) => {
    const buffer = bufferOf(paneId);
    if (!buffer) return { ...UNREADABLE_WINDOW };
    const floor = Math.max(buffer.dropped, buffer.totalWritten - maxBytes);
    return region(paneId, Number.isInteger(notBefore) ? Math.max(floor, notBefore) : floor, maxLines);
  };

  /** The whole region since a mark, line-unbounded: for counting OUR OWN nonce, which may be
   *  separated from the provider's answer by more output than a tail holds, and which must not be
   *  satisfiable by an earlier run's copy. Same fail-closed slice. */
  const since = (paneId, from) => region(paneId, from, Infinity);

  return { mark, read, since };
}

/**
 * The order, as a pure function. Returns which signal answered and what it said; `screen_consulted`
 * is part of the answer because "we never looked at the transcript" is the property under test.
 */
function orderedProviderSignal({
  provider = null, processState = "running", exitCode = null, mcpConnected = false,
  window = null, classify = classifyProviderScreen,
} = {}) {
  // 1. THE PROCESS. An exit code is the strongest signal a process ever emits, and a transcript may
  //    not demote it (`frontier_provider_recon.py:44-49`). A worker that is gone is `process_exit`
  //    with its code, never `AUTH_REQUIRED` because the word "login" is somewhere in its scrollback.
  if (processState !== "running") {
    return {
      source: "process_exit", process_state: processState,
      exit_code: Number.isInteger(exitCode) ? exitCode : null,
      exited_ok: exitCode === 0, setup: null, screen_consulted: false,
    };
  }
  // 2. STRUCTURED PROVIDER SIGNAL. A connected Sovereign MCP session is the provider telling us,
  //    through its own protocol, that it is up. This check was BELOW the screen scrape and was
  //    therefore short-circuited by it — the reorder is the fix, not a reordering of taste.
  if (mcpConnected === true) {
    return { source: "mcp_connection", connected: true, setup: null, screen_consulted: false };
  }
  // 3. SCREEN TEXT, and only now. `window` may be a THUNK, and callers on the readiness path pass
  //    one: an argument evaluated before the branch that uses it would mean a healthy worker's
  //    transcript is still read on every poll, and "the screen was never consulted" is the property
  //    under test — a test can only see it if the read genuinely does not happen.
  if (typeof window === "function") window = window();
  //    An unanswerable window yields NO classification — never a wider read (U329's whole point),
  //    and never a fabricated state.
  if (!window || window.answerable !== true) {
    return {
      source: "screen_unanswerable", setup: null, screen_consulted: true,
      reason: (window && window.reason) || "no window was offered",
    };
  }
  return {
    source: "screen_text", setup: classify(provider, window.text) || null, screen_consulted: true,
    window_bytes: window.bytes ?? null, window_from: window.from ?? null,
  };
}

/**
 * Consecutive-agreement tracking, and the exit path. A poll that classifies nothing returns null,
 * which is what lets a dismissed overlay stop being the worker's state inside the same run.
 */
function trackObservation(previous, setup) {
  if (!setup) return null;
  if (previous && previous.state === setup.state) {
    return { ...previous, setup, polls: previous.polls + 1 };
  }
  return { state: setup.state, setup, polls: 1 };
}

const confirmed = (observation, confirmPolls = CONFIRM_POLLS) =>
  Boolean(observation && observation.polls >= confirmPolls);

/** The readiness challenge: the prompt we type, and the reply that proves a provider composed it.
 *
 *  U385 — THE REPLY MAY NOT APPEAR IN THE PROMPT. The first version asked the provider to "reply
 *  exactly <token>" and promoted the worker on the SECOND occurrence of that token, reasoning that
 *  the first was the pane's echo of what we typed. On a real ConPTY that reasoning is false: a
 *  terminal RESIZE (`ESC[8;7;65t`) makes ConPTY repaint the screen and re-emit the same line, so the
 *  token reaches two occurrences from the echo ALONE. Measured, not theorised — the 19.4 round-3
 *  in-Electron receipt returned READY on a pane that had answered nothing (token occurrences 2,
 *  answer marks 0), reproduced 3/3. Raising the threshold is not a fix: a second repaint defeats
 *  `>= 3` exactly as the first defeated `>= 2`.
 *
 *  So the reply is INSTRUCTED IN WORDS and never quoted — two fragments the provider must join. No
 *  echo of the prompt and no repaint THAT RE-EMITS ITS TEXT can contain the joined string, so an
 *  occurrence is the provider speaking. `waitForTurn` additionally refuses to write a prompt that
 *  contains its own answer, because such a prompt cannot tell the two apart and a readiness check
 *  that cannot is worse than none.
 *
 *  THE BOUND, stated because the first version of this comment claimed an absolute the code does not
 *  have (round-4 reviewers, [[U393]]): `plainScreen` in `provider-readiness.js` DELETES CSI/OSC
 *  sequences without substituting anything, where it replaces C0 controls with a space. A
 *  DIFFERENTIAL repaint that re-emitted `${head}`, then cursor addressing, then `${tail}`, while
 *  skipping the 41 characters of instruction between them, would therefore normalize to the joined
 *  string. (39 was the number this comment carried until [[U394]]; the separator was then MEASURED —
 *  the count had dropped the two delimiting spaces.) Not observed: across six in-Electron runs the
 *  echo count reached 2 and 3 while the answer count stayed 1 every time, because the repaints
 *  re-emitted whole lines. What defends this in PRODUCTION is
 *  not the screen at all — `toolSucceeded` below is a real count of `get_worker_status` calls
 *  reaching the MCP server, and no repaint can fabricate one.
 *
 *  Fixed text otherwise, deliberately: it lands inside the window this run classifies, so anything
 *  variable in it (an objective, a proposition) would be classifying us against ourselves — which is
 *  exactly U329's second failure mode. `worker-readiness.test.js` pins that this template classifies
 *  clean for every provider. */
/** The stamp that makes each challenge unlike every challenge before it, in this process.
 *
 *  U385, round 4 — THE FRESHNESS IS LOAD-BEARING AND WAS RESTING ON THE CLOCK ALONE. The scheme
 *  above says "one occurrence is the provider speaking", and that is true of the prompt we just
 *  typed; it is NOT true of an earlier run's answer, which is still in the ring and still on the
 *  visible screen. Readiness runs a second time on a pane when the conductor asks for a worker on a
 *  provider that already has a live one (`main.js` `controlSpawnWorker`'s duplicate branch — there is
 *  no periodic re-run, and the first run is the only other caller), and the repaint this unit exists
 *  for re-emits whatever the screen holds AFTER the new run's mark. If two challenges are equal, a
 *  redraw of run N's answer satisfies run N+1 — U385 one level up.
 *
 *  The call site used `io.now().toString(36)` alone, so the property held only because the clock
 *  happened to move between runs, and nothing anywhere asserted it: the gate-validator's round-4
 *  probe froze that stamp and all 928 tests still passed. A sequence the process itself increments
 *  makes non-repetition structural — true at any clock resolution rather than at this host's — and
 *  the two tests named in [[U392]] are what would break if it were removed.
 *
 *  NOT claimed (round-4 auditor, [[U393]]): that two challenges on ONE pane can collide in
 *  production. Turn 2's stamp is minted only after turn 1 returns, and the write path awaits
 *  `PROVIDER_PASTE_SETTLE_MS` (500 ms by default, and `intervalMs` refuses a non-positive override),
 *  so the same-millisecond case is not reachable there. The sequence is defence against a property
 *  resting on the clock at all — which is what the validator's probe falsified — not against a
 *  measured production collision. */
let challengeSequence = 0;
const challengeStamp = (now) =>
  `${Number(now).toString(36)}${(challengeSequence += 1).toString(36)}`;

const readinessChallenge = (nodeId, turn, stamp) => {
  const head = `SOVEREIGN_READY_${turn}_${stamp}`;
  const tail = `SOVEREIGN_TAIL_${stamp}`;
  return {
    head,
    tail,
    expected: `${head}${tail}`,
    prompt: `Readiness check only. Call the Sovereign get_worker_status tool for node ${nodeId}, `
      + `then reply with a single word: the fragment ${head} written immediately before the `
      + `fragment ${tail}, with nothing at all between them. Do not call any other tool.`,
  };
};

function createWorkerReadiness(io) {
  const confirmPolls = Number.isInteger(io.confirmPolls) ? io.confirmPolls : CONFIRM_POLLS;
  // `main.js` binds the shell log in; the first version of this module never called it, so every
  // readiness decision happened with no line anywhere (invariant 27). Optional, because a caller
  // that supplies no log gets silence rather than a crash.
  const log = (message) => { if (typeof io.log === "function") io.log(message); };

  function failure(record, stage, terminalState = "STALLED", extra = {}) {
    const operations = io.operationState(record.nodeId) || { last: null };
    return {
      ...structuredProviderFailure({
        provider: record.chrome && record.chrome.provider,
        model: record.chrome && record.chrome.model_slug,
        nodeId: record.nodeId, stage,
        lastSuccessfulMcpOperation: operations.last && operations.last.ok
          ? operations.last.operation : record.lastSuccessfulMcpOperation,
        lastProgressTimestamp: record.lastProgressAt,
        providerTerminalState: terminalState,
        leaseState: record.leaseId ? "active" : "not_applicable",
        processState: record.state,
      }),
      ...extra,
    };
  }

  /** One readiness turn: our nonce goes out, and its return is judged by structured signals plus our
   *  OWN token — never by a keyword scrape that runs first. */
  async function waitForTurn(record, challenge, deadline) {
    // FAIL CLOSED before anything is typed (U385): if the prompt contains the reply it asks for,
    // then a repaint of our own keystrokes is byte-identical to the provider answering, and no
    // count over this pane can separate them. Such a turn is not run at all — it is not that the
    // check would be weak, it is that its result would mean nothing.
    if (String(challenge.prompt).includes(challenge.expected)) {
      log(`readiness ${record.paneId}: refusing to ask — the prompt contains its own answer`);
      return { ok: false, stage: "readiness_challenge_unsound" };
    }
    // Taken BEFORE anything else: the echo of our prompt and the provider's answer both land after
    // it, so the count below is of THIS turn's occurrences and needs no baseline subtraction, and
    // the in-turn classification window is floored here (U373).
    const mark = io.window.mark(record.paneId);
    const baseline = io.operationCount(record.nodeId, "get_worker_status");
    let observation = null;
    let lastWindowReason = null;
    // THE U328 WRITE GATE owns whether a keystroke may enter this pane, and since 19.4-followon it
    // answers that from the SAME bounded window used below. What it still may NOT do is state the
    // worker's condition: its refusal means "not yet", so we wait for it to clear, and while we
    // wait the bounded window is what gets to say what is wrong. A refusal that never clears is a
    // stall we report as one, with the gate's own reason attached — never as a provider verdict.
    // The two instruments now read the same region and will usually agree; keeping them separate is
    // what stops "we could not type" from being rendered as "the provider is broken" on the day
    // they do not (the gate's own denylist is wider — [[U363]]'s affordance families).
    let wrote = false;
    let withheld = null;
    while (!wrote) {
      // THE PROCESS, FIRST, ON EVERY POLL. The first version of this loop classified with the
      // `record` the turn began with, so a worker that DIED while its write was withheld was still
      // decided by its screen — and its structured failure asserted `process_state: "running"` and
      // `exit_code: null` for a process that had exited. Both mandatory reviewers found it
      // independently at the round-2 review: the directive row's first clause, inverted inside the
      // remediation written for its second. The sibling loop below has always refreshed; this one
      // now does, and the exit is reported by its code exactly as it is there.
      const live = io.record(record.paneId);
      if (live.state !== "running") {
        return {
          ok: false, stage: "process_exited_during_readiness",
          exit_code: Number.isInteger(live.exitCode) ? live.exitCode : null,
        };
      }
      const refusal = io.writeRefusal(record.paneId);
      if (!refusal) {
        wrote = await io.writePrompt(record.paneId, challenge.prompt);
        if (!wrote) return { ok: false, stage: "readiness_prompt_delivery" };
        break;
      }
      withheld = {
        state: refusal.state || null, reason: refusal.reason || null,
        terminal_state: refusal.terminal_state || null,
      };
      const held = orderedProviderSignal({
        provider: record.chrome && record.chrome.provider,
        processState: live.state, exitCode: live.exitCode, mcpConnected: false,
        window: () => io.window.read(record.paneId),
      });
      observation = trackObservation(observation, held.setup);
      if (confirmed(observation, confirmPolls)) {
        log(`readiness ${record.paneId}: write withheld and the bounded window confirms `
          + `${observation.setup.state}`);
        return { ok: false, stage: "provider_setup", setup: observation.setup };
      }
      if (io.now() >= deadline) {
        log(`readiness ${record.paneId}: the write gate withheld this turn for the whole `
          + `deadline (${withheld.reason || "no reason given"}) and no bounded window confirmed it`);
        return { ok: false, stage: "readiness_prompt_withheld", write_withheld: withheld };
      }
      await io.sleep(POLL_MS);
    }
    observation = null;
    while (io.now() < deadline) {
      const live = io.record(record.paneId);
      // 1. the process
      if (live.state !== "running") {
        return {
          ok: false, stage: "process_exited_during_readiness",
          exit_code: Number.isInteger(live.exitCode) ? live.exitCode : null,
        };
      }
      // 2. structured: the tool call the prompt asked for actually reached the MCP server, and our
      //    own nonce came back. Judged BEFORE any classification, so a worker that has ANSWERED is
      //    never demoted by a word in its transcript (the negative control).
      const toolSucceeded = io.operationCount(record.nodeId, "get_worker_status") > baseline;
      const own = io.window.since(record.paneId, mark);
      // The expected reply is a string the prompt CANNOT contain (U385), so ONE occurrence is the
      // provider having composed it — not our own echo, and not a repaint that re-emits our line
      // (the header states the one repaint shape that is not excluded, and why `toolSucceeded`
      // above is what actually defends this in production). An unanswerable window cannot confirm
      // it, and does not guess — it waits, and the deadline reports the stall.
      const answers = own.answerable ? occurrenceCount(own.text, challenge.expected) : null;
      if (!own.answerable) lastWindowReason = own.reason || null;
      if (toolSucceeded && answers !== null && answers >= 1) {
        return { ok: true, tool_succeeded: true, answer_occurrences: answers };
      }
      // 3. only now: a bounded read of what the pane is showing, floored at THIS TURN'S mark. The
      //    negative control is what forces the floor: a connected worker that takes two seconds to
      //    answer is polled eight times first, and without the floor a "usage limit" line twenty
      //    lines up in its transcript becomes its verdict ~500 ms in — the audited pin, restored
      //    through the back door. What the provider draws in answer to our prompt is after the mark.
      const signal = orderedProviderSignal({
        provider: record.chrome && record.chrome.provider,
        processState: live.state, exitCode: live.exitCode,
        mcpConnected: false,        // this turn exists BECAUSE the connection is already up; the
                                    // question here is whether the provider can answer, so the
                                    // screen is the only signal left and is read as the last one.
        window: () => io.window.read(record.paneId, { notBefore: mark }),
      });
      observation = trackObservation(observation, signal.setup);
      if (confirmed(observation, confirmPolls)) {
        return { ok: false, stage: "provider_setup", setup: observation.setup };
      }
      await io.sleep(POLL_MS);
    }
    return {
      ok: false, stage: "readiness_response_timeout",
      window_unanswerable: lastWindowReason,
    };
  }

  /**
   * The full readiness run for one worker pane. Returns `{ready, state, ...}` and leaves the pane's
   * operational state and structured failure recorded through `io.setOperationalState`.
   */
  async function run(paneId) {
    // Nothing the pane emitted before this moment is evidence about what it is doing now. This one
    // line is what un-sticks a dismissed overlay across runs, and what stops the operator's own
    // echoed objective from classifying the worker that was told to work on it.
    const mark = io.window.mark(paneId);
    let record = io.record(paneId);
    const initialMcp = io.mcpState(record.nodeId);
    record = io.setOperationalState(paneId, "MCP_CONNECTING", {
      readiness: {
        ...observedReadinessEvidence({
          record,
          processIdentity: typeof io.processIdentity === "function"
            ? io.processIdentity(paneId) : undefined,
          mcpState: initialMcp,
          nodeRegistered: record.nodeAttested === true,
        }),
        harmless_mcp_call: false,
        readiness_responses: 0, window_mark: mark,
      },
    });
    const mcpDeadline = io.now() + io.mcpTimeoutMs();
    let observation = null;
    let connected = false;
    let lastWindowReason = null;
    while (io.now() < mcpDeadline) {
      record = io.record(paneId);
      const signal = orderedProviderSignal({
        provider: record.chrome && record.chrome.provider,
        processState: record.state,
        exitCode: record.exitCode,
        // SESSION ESTABLISHED, not "fresh" (19.7, gate-validator round 1 BLOCKING-1). 19.7 gave
        // `connectionState` a staleness window, and binding this to `=== "connected"` meant a
        // worker that HAD connected but had been quiet longer than the window never reached its
        // challenge at all: `run()` fell through to the timeout below and wrote a durable STALLED
        // onto a pane nothing had been typed into — the U329 defect class, re-created inside the
        // unit written to avoid it. Readiness is the PROVOCATION: the challenge it types is
        // answered by a real MCP call, which re-freshens the session. What it needs to know is
        // whether this node has ever reached the gateway. Whether it did so RECENTLY is the
        // assignment gate's question, and it stays there (`control/assignment-gate.js`).
        mcpConnected: sessionEstablished(io.mcpState(record.nodeId)),
        window: () => io.window.read(paneId),
      });
      if (signal.source === "process_exit") {
        // Exit code first, and it is RECORDED: a worker that died is reported as the process it was,
        // with its code, rather than as whatever its last screenful happened to contain.
        const structured = failure(record, "process_startup", "FAILED", {
          exit_code: signal.exit_code, decided_by: "process_exit",
        });
        io.setOperationalState(paneId, "FAILED", { structuredFailure: structured });
        return { ready: false, state: "FAILED", failure: structured, decided_by: "process_exit" };
      }
      if (signal.source === "mcp_connection") { connected = true; break; }
      // "I cannot see" is not "nothing is wrong" (invariant 27): the reason is carried to whatever
      // failure this run ends in, instead of being dropped for a bare timeout.
      if (signal.source === "screen_unanswerable") lastWindowReason = signal.reason || null;
      observation = trackObservation(observation, signal.setup);
      if (confirmed(observation, confirmPolls)) {
        const setup = observation.setup;
        const structured = failure(record, "provider_setup", setup.terminal_state, {
          decided_by: "screen_text_bounded_window",
        });
        io.setOperationalState(paneId, setup.state, {
          structuredFailure: structured,
          readiness: {
            ...(record.readiness || {}), provider_terminal_state: setup.terminal_state,
            reason: setup.reason, decided_by: "screen_text_bounded_window",
          },
        });
        return { ready: false, state: setup.state, failure: structured,
          decided_by: "screen_text_bounded_window" };
      }
      await io.sleep(POLL_MS);
    }
    if (!connected && !sessionEstablished(io.mcpState(record.nodeId))) {
      const structured = failure(record, "mcp_readiness_timeout", "STALLED",
        { decided_by: "mcp_readiness_timeout", window_unanswerable: lastWindowReason });
      io.setOperationalState(paneId, "STALLED", { structuredFailure: structured });
      return { ready: false, state: "STALLED", failure: structured };
    }

    // 19.6, [[U386]](c): how many turns readiness needs is a DECLARED trait of the provider, read
    // through the descriptor, not `provider === "grok_build" ? 2 : 1` written here. An undeclared
    // provider gets the generic one turn — the same value the old expression's `: 1` gave it, now
    // by a rule that is enumerable and testable rather than by falling off the end of a ternary.
    const requiredTurns = traitsFor(record.chrome && record.chrome.provider).readiness_turns;
    const readiness = {
      ...(record.readiness || {}),
      ...observedReadinessEvidence({
        record,
        processIdentity: typeof io.processIdentity === "function"
          ? io.processIdentity(paneId) : undefined,
        mcpState: io.mcpState(record.nodeId),
        nodeRegistered: record.nodeAttested === true,
      }),
      readiness_responses: 0, harmless_mcp_call: false,
    };
    for (let turn = 1; turn <= requiredTurns; turn += 1) {
      const challenge = readinessChallenge(record.nodeId, turn, challengeStamp(io.now()));
      const result = await waitForTurn(record, challenge, io.now() + io.responseDeadlineMs());
      if (!result.ok) {
        // Every structured failure below reports the process it was: `failure()` reads
        // `record.state` and `record.exitCode`, and the record this loop holds predates the turn.
        // Reporting `process_state: "running"` beside `decided_by: "process_exit"` and an exit code
        // — which is what the unrefreshed record produced — is a record contradicting itself
        // (invariant 27), so the fields are re-read here before anything is written.
        record = io.record(paneId);
        if (result.setup) {
          const structured = failure(record, result.stage, result.setup.terminal_state,
            { decided_by: "screen_text_bounded_window" });
          io.setOperationalState(paneId, result.setup.state, {
            structuredFailure: structured,
            readiness: { ...readiness, provider_terminal_state: result.setup.terminal_state,
              reason: result.setup.reason },
          });
          return { ready: false, state: result.setup.state, failure: structured };
        }
        const stage = requiredTurns > 1 && turn === requiredTurns
          ? "final_readiness_response" : result.stage;
        // A withheld write is reported as what it is: we could not ASK. It is never promoted to a
        // provider terminal state — the rule is unchanged; its original reason (the gate read a whole
        // scrollback) retired when the gate was bounded, and what stands now is that the gate answers
        // a different question, with a wider denylist (U373, U363).
        // A label names the instrument that decided. `readiness_prompt_delivery` — the gate
        // refusing between the pre-check and the submit key, or a dead PTY handle — used to fall
        // through to `readiness_deadline`, naming a deadline that had not elapsed. The reason the
        // gate gave is still lost on that path because `writePanePrompt` collapses the refusal
        // record to a boolean (U361 owns that); the label at least stops asserting a cause.
        const decidedBy = result.stage === "process_exited_during_readiness" ? "process_exit"
          : result.stage === "readiness_prompt_withheld" ? "write_gate_withheld"
            : result.stage === "readiness_prompt_delivery" ? "write_not_delivered"
              : result.stage === "readiness_challenge_unsound" ? "challenge_unsound"
                : "readiness_deadline";
        // U386(b), invariant 27: a process that EXITED is FAILED — exactly as the MCP-connection
        // loop above renders the identical condition. Reporting it STALLED because the exit landed
        // inside a turn described the worker by OUR timing rather than by its state, and hung an
        // "alive but unresponsive" badge on a dead process. One condition, one rendering.
        const terminal = result.stage === "process_exited_during_readiness" ? "FAILED" : "STALLED";
        const structured = failure(record, stage, terminal, {
          exit_code: Number.isInteger(result.exit_code) ? result.exit_code : null,
          decided_by: decidedBy,
          window_unanswerable: result.window_unanswerable || null,
          write_withheld: result.write_withheld || null,
        });
        io.setOperationalState(paneId, terminal, {
          structuredFailure: structured, readiness: { ...readiness, readiness_responses: turn - 1 },
        });
        return { ready: false, state: terminal, failure: structured };
      }
      readiness.readiness_responses = turn;
      readiness.harmless_mcp_call = true;
    }
    // The readiness challenge is itself a gateway call in production, so a stale session should
    // normally be fresh again here. Re-read it instead of converting "a challenge passed" into the
    // different claim "the session is connected". A check double that does not freshen stays false.
    const finalMcp = io.mcpState(record.nodeId);
    if (finalMcp && typeof finalMcp.state === "string") {
      readiness.mcp_connected = finalMcp.state === "connected";
    }
    record = io.setOperationalState(paneId, "READY", { readiness, structuredFailure: null });
    return { ready: true, state: "READY", readiness: record.readiness };
  }

  return { run, waitForTurn };
}

module.exports = {
  createScreenWindow, createWorkerReadiness, orderedProviderSignal, trackObservation, confirmed,
  lastLines, readinessChallenge, challengeStamp, POLL_MS, CONFIRM_POLLS, TAIL_BYTES, TAIL_LINES,
};
