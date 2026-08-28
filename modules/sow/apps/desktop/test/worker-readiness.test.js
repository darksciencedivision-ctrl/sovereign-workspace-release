"use strict";
/**
 * Phase 19 unit 19.4 — U329: exit codes first, a bounded window, and the NEGATIVE CONTROL that did
 * not exist.
 *
 * The cold audit's finding B4, in one sentence: a live provider's state was decided by keyword-
 * matching the whole retained ring buffer, on a still-running process, BEFORE the MCP connection
 * check. `provider-readiness.test.js` asserted every positive case and nothing asserted that a
 * HEALTHY worker stays READY — so the sticky-overlay bug, the self-inflicted false positive (the
 * shell writes the operator's objective into the pane verbatim) and the instrument disagreement in
 * `FINAL_THREE_NODE_ORCHESTRATION_ACCEPTANCE.json` all lived under a green suite.
 *
 * The window tests drive the REAL `RingBuffer` from `terminal/session/`, not a double: `sliceFrom`'s
 * null-on-unanswerable is the whole mechanism, and a fake that returned a string would test the
 * mechanism away.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const {
  createScreenWindow, createWorkerReadiness, orderedProviderSignal, trackObservation,
  readinessChallenge, challengeStamp, lastLines, TAIL_BYTES, TAIL_LINES,
} = require("../control/worker-readiness");
const { modalAffordance } = require("../control/modal-affordance");
const { classifyProviderScreen } = require("../control/provider-readiness");
const { createPaneWriter, paneScreenFromWindow } = require("../control/pane-writer");
const { RingBuffer } = require("../../../terminal/session/ring-buffer");

const AUTH_TEXT = "You are not signed in. Run `grok login` to continue.\r\n";
const TRUST_TEXT = "Do you trust the contents of this project?\r\n  1. Yes, I trust this folder\r\n";
const CLEAN = "sovereign> ready\r\n";

/**
 * What a provider that OBEYED the readiness instruction says back (U385).
 *
 * The prompt no longer quotes the reply it wants — it names two fragments and asks for them joined —
 * so this helper does what the provider does: reads the instruction, and composes the answer. It is
 * deliberately NOT `readinessChallenge(...).expected`: a harness that answered with the module's own
 * string would still pass if the prompt and the expectation drifted apart, which is the one thing
 * this scheme exists to prevent.
 */
const ANSWER_RE = new RegExp(
  "the fragment (SOVEREIGN_READY_[0-9]+_[a-z0-9]+) written immediately before "
  + "the fragment (SOVEREIGN_TAIL_[a-z0-9]+)");
function answerTo(prompt) {
  const m = ANSWER_RE.exec(String(prompt || ""));
  assert.ok(m, `the readiness prompt did not name its two fragments: ${prompt}`);
  return m[1] + m[2];
}

// ---------------------------------------------------------------------------------------------
// 1. THE ORDER
// ---------------------------------------------------------------------------------------------

test("a process that has exited is decided by its exit code, and its transcript is never read", () => {
  let read = 0;
  const signal = orderedProviderSignal({
    provider: "grok_build", processState: "exited", exitCode: 0,
    mcpConnected: false,
    window: () => { read += 1; return { answerable: true, text: AUTH_TEXT }; },
  });
  assert.equal(signal.source, "process_exit");
  assert.equal(signal.exit_code, 0);
  assert.equal(signal.exited_ok, true);
  assert.equal(signal.setup, null);
  assert.equal(signal.screen_consulted, false);
  // The rule from frontier_provider_recon.py:44-49 is not "we prefer the exit code" — it is that
  // the transcript is not consulted at all. A read that happened would falsify that.
  assert.equal(read, 0, "an exited process must not have its screen scraped");
});

test("a nonzero exit is still the exit code, not the words on the screen", () => {
  const signal = orderedProviderSignal({
    processState: "release_pending", exitCode: 3,
    window: { answerable: true, text: AUTH_TEXT },
  });
  assert.equal(signal.source, "process_exit");
  assert.equal(signal.exit_code, 3);
  assert.equal(signal.exited_ok, false);
  assert.equal(signal.setup, null);
});

test("a connected MCP session answers before the screen, and the screen is not read", () => {
  let read = 0;
  const signal = orderedProviderSignal({
    provider: "grok_build", processState: "running", mcpConnected: true,
    window: () => { read += 1; return { answerable: true, text: TRUST_TEXT }; },
  });
  assert.equal(signal.source, "mcp_connection");
  assert.equal(signal.setup, null);
  assert.equal(signal.screen_consulted, false);
  assert.equal(read, 0, "the connection check must not be short-circuited by a classification");
});

test("an unanswerable window classifies nothing — it never widens to a bigger read", () => {
  const signal = orderedProviderSignal({
    provider: "grok_build", processState: "running", mcpConnected: false,
    window: { answerable: false, text: "", reason: "trimmed" },
  });
  assert.equal(signal.source, "screen_unanswerable");
  assert.equal(signal.setup, null);
  assert.equal(signal.reason, "trimmed");
});

test("screen text is consulted last, and still classifies when it is the only signal", () => {
  const signal = orderedProviderSignal({
    provider: "grok_build", processState: "running", mcpConnected: false,
    window: { answerable: true, text: AUTH_TEXT, bytes: 52, from: 10 },
  });
  assert.equal(signal.source, "screen_text");
  assert.equal(signal.setup.state, "AUTH_REQUIRED");
  assert.equal(signal.screen_consulted, true);
  assert.equal(signal.window_bytes, 52);
});

test("an observation resets the moment a window stops classifying (the exit path)", () => {
  let obs = trackObservation(null, { state: "AUTH_REQUIRED" });
  assert.equal(obs.polls, 1);
  obs = trackObservation(obs, { state: "AUTH_REQUIRED" });
  assert.equal(obs.polls, 2);
  assert.equal(trackObservation(obs, null), null, "a cleared screen must clear the observation");
});

// ---------------------------------------------------------------------------------------------
// 2. THE WINDOW (real RingBuffer)
// ---------------------------------------------------------------------------------------------

function pane(capacity = 256 * 1024) {
  const buffer = new RingBuffer(capacity);
  return { buffer, window: createScreenWindow({ bufferFor: () => buffer }) };
}

test("the classification window is the TAIL — old scrollback stops classifying once a screen of "
  + "output has been drawn over it", () => {
  const p = pane();
  p.buffer.push(AUTH_TEXT);                         // an overlay, long since dismissed…
  p.buffer.push("clean line\r\n".repeat(400));      // …and a screen redrawn over it
  const w = p.window.read("pane-1");
  assert.equal(w.answerable, true);
  assert.ok(!/not signed in/i.test(w.text), "buried scrollback is not what the pane is showing");
  assert.equal(classifyProviderScreen("grok_build", w.text), null);
});

test("a modal that is what the pane is showing NOW classifies — including one drawn before we "
  + "started watching, which is the common case", () => {
  const p = pane();
  p.buffer.push("banner\r\n".repeat(50));
  p.buffer.push(TRUST_TEXT);                        // drawn at spawn, nothing after it
  const w = p.window.read("pane-1");
  assert.equal(classifyProviderScreen("grok_build", w.text).state, "WORKSPACE_TRUST_REQUIRED");
});

test("the tail is bounded in bytes and in lines, so a verdict cannot reach back through a "
  + "256 KB scrollback", () => {
  const p = pane();
  p.buffer.push("filler line\r\n".repeat(4000));
  const w = p.window.read("pane-1");
  assert.ok(w.bytes <= TAIL_BYTES, `tail window was ${w.bytes} bytes`);
  assert.ok(w.text.split("\n").length <= TAIL_LINES + 1, "the line bound is what a screen means");
});

test("the nonce window is exact or it is nothing: a region the buffer no longer holds is "
  + "UNANSWERABLE, never a wider read", () => {
  const p = pane(64);                               // tiny, so the front is trimmed immediately
  const mark = p.window.mark("pane-1");
  p.buffer.push("x".repeat(40));
  p.buffer.push("y".repeat(200));                   // trims past the mark
  const w = p.window.since("pane-1", mark);
  assert.equal(w.answerable, false);
  assert.equal(w.text, "");
  assert.match(w.reason, /no longer held exactly/);
});

test("a mark that points past the stream is unanswerable (a fabricated or stale position)", () => {
  const p = pane();
  p.buffer.push(CLEAN);
  assert.equal(p.window.since("pane-1", 9_999_999).answerable, false);
  assert.equal(p.window.since("pane-1", null).answerable, false);
  assert.equal(p.window.since("pane-1", -1).answerable, false);
});

test("the nonce window spans the whole run, however chatty the provider was", () => {
  const p = pane();
  const mark = p.window.mark("pane-1");
  p.buffer.push("TOKEN_X\r\n");
  p.buffer.push("chatter\r\n".repeat(4000));        // far past the tail bound
  p.buffer.push("TOKEN_X\r\n");
  const w = p.window.since("pane-1", mark);
  assert.equal(w.answerable, true);
  assert.equal(w.text.split("TOKEN_X").length - 1, 2);
});

test("U380: BLANK lines drawn by a repaint cannot evict a modal that is genuinely on screen", () => {
  // The round-2 spec-auditor's finding, as a test. `plainScreen` strips escape sequences without
  // collapsing what they leave behind, so a repainting provider emits runs of blank lines. Counting
  // them spent the line bound on nothing: the modal below sits more than TAIL_LINES of blank lines
  // up, and the only instrument allowed to state a worker's condition could not see it. The run then
  // reported a bare `mcp_readiness_timeout` for a pane whose screen said exactly what was wrong.
  const p = pane();
  p.buffer.push(TRUST_TEXT);
  // The blank count is TIED TO THE BOUND rather than written out: it was 30 against a 24-line
  // bound, and when the round-1 review of 19.4-followon raised the bound to 80 the fixture
  // silently stopped clearing it — the first assertion passed with R24 spliced in, and only the
  // second still graded it. That is the U367 class, inside the test written to prevent it.
  p.buffer.push("\r\n".repeat(TAIL_LINES + 6));   // a repaint's worth of blanks, and nothing else
  const w = p.window.read("pane-1");
  assert.equal(w.answerable, true);
  assert.equal(classifyProviderScreen("grok_build", w.text).state, "WORKSPACE_TRUST_REQUIRED",
    "blank lines carry no classifiable text and may not consume the line bound");
  // …and the bound itself still holds: what is kept is the last TAIL_LINES lines WITH text on them.
  const q = pane();
  q.buffer.push("line A\r\n\r\n".repeat(100));
  const wq = q.window.read("pane-1");
  const kept = wq.text.split("\n");
  assert.ok(kept.length <= TAIL_LINES, `the line bound still binds: ${kept.length} lines`);
  assert.ok(kept.every((line) => line.trim()), "a blank line in the window is a wasted line");
});

test("U396/V7: the window preserves SCREEN ORDER — the classifiers read a screen, not a bag of "
  + "lines", () => {
  // The round-1 validator of 19.4-followon deleted `lastLines`'s `.reverse()` and ran the whole
  // desktop suite: 939 green. Order is load-bearing and was pinned nowhere. Measured, not argued:
  // `/\b[1-9]\.\s*yes\b[\s\S]{0,80}?\b[1-9]\.\s*no\b/` requires "1. Yes" BEFORE "2. No", so a
  // reversed window turns one of the ten validator permission screens from refused into written-into.
  const p = pane();
  p.buffer.push("Apply these changes to 3 files?\r\n  1. Yes, apply\r\n  2. No, keep planning\r\n");
  const w = p.window.read("pane-1");
  assert.equal(w.answerable, true);
  const lines = w.text.split("\n");
  assert.ok(lines.indexOf("Apply these changes to 3 files?") < lines.findIndex((l) => /1\. Yes/.test(l)),
    "the window must present the pane's lines in the order the pane drew them");
  assert.ok(modalAffordance(w.text), "…which is what lets an affordance spanning two lines be seen");
  // and the direct property, so a future window implementation cannot pass by accident
  assert.equal(lastLines("first\nsecond\nthird", 2), "second\nthird");
  assert.equal(lastLines("a\n\n\nb\nc", 2), "b\nc");
});

test("a pane with no buffer is unanswerable, never an empty screen that classifies clean", () => {
  const w = createScreenWindow({ bufferFor: () => null });
  assert.equal(w.mark("pane-1"), null);
  assert.equal(w.read("pane-1").answerable, false);
  assert.equal(w.since("pane-1", 0).answerable, false);
  const throwing = createScreenWindow({ bufferFor: () => { throw new Error("gone"); } });
  assert.equal(throwing.read("pane-1").answerable, false);
});

// ---------------------------------------------------------------------------------------------
// 3. THE STATE MACHINE
// ---------------------------------------------------------------------------------------------

/**
 * A worker pane harness. The ring buffer is real; `emit` is what the provider prints. Screen reads
 * are counted in TWO buckets, because the difference is the property: `classificationReads` is the
 * denylist scrape (which a healthy worker must never pay), `nonceReads` is us counting our own
 * token, which is not a scrape of the provider's words.
 */
function harness(opts = {}) {
  const buffer = new RingBuffer(opts.capacity || 256 * 1024);
  const st = {
    buffer,
    states: [],
    record: {
      paneId: "pane-2", nodeId: "node-w", state: opts.processState || "running",
      exitCode: opts.exitCode === undefined ? null : opts.exitCode,
      chrome: { provider: opts.provider || "claude_code", model_slug: "m" },
      nodeAttested: true, readiness: null, leaseId: "lease-1", supervised: true,
      pid: 4567, sessionGeneration: 2,
    },
    mcp: opts.mcp === undefined ? "connected" : opts.mcp,
    operations: 0,
    writes: [],
    refusal: opts.refusal || null,
    classificationReads: 0,
    nonceReads: 0,
    ticks: 0,
    logs: [],
  };
  const window = createScreenWindow({ bufferFor: () => buffer });
  const io = {
    now: () => Date.now(),
    sleep: async () => { st.ticks += 1; if (opts.onTick) opts.onTick(st); },
    window: {
      mark: (paneId) => window.mark(paneId),
      // the options MUST be forwarded: `main.js` binds the window object itself, so a counting
      // wrapper that dropped them would test a window the shell does not use (it hid the in-turn
      // floor for one round of this unit, and every mutation against the floor read as CAUGHT).
      read: (paneId, options) => { st.classificationReads += 1; return window.read(paneId, options); },
      since: (paneId, from) => { st.nonceReads += 1; return window.since(paneId, from); },
    },
    record: () => ({ ...st.record }),
    processIdentity: () => ({ pid: 4567, generation: 2 }),
    setOperationalState: (paneId, state, patch) => {
      st.states.push(state);
      st.record = { ...st.record, operationalState: state, ...patch };
      return { ...st.record };
    },
    mcpState: () => ({ state: st.mcp }),
    operationCount: () => st.operations,
    operationState: () => ({ last: null }),
    writeRefusal: () => st.refusal,
    writePrompt: async (paneId, prompt) => {
      st.writes.push(prompt);
      if (opts.acceptWrites === false) return false;
      buffer.push(prompt);                       // the pane echoes what we typed…
      if (opts.answer !== false) {
        const answer = answerTo(prompt);
        if (opts.onPrompt) opts.onPrompt(st, answer, prompt);
        else { st.operations += 1; buffer.push(`\r\n${answer}\r\n`); }   // …then answers
      }
      return true;
    },
    mcpTimeoutMs: () => (opts.mcpTimeoutMs === undefined ? 2000 : opts.mcpTimeoutMs),
    responseDeadlineMs: () => (opts.responseDeadlineMs === undefined ? 2000 : opts.responseDeadlineMs),
    log: (m) => st.logs.push(m),
  };
  // `io` is returned so a test can replace one binding with the PRODUCTION one (U373): the object
  // is captured by reference, so a later assignment is what the readiness run actually calls.
  return { st, io, readiness: createWorkerReadiness(io) };
}

test("NEGATIVE CONTROL: a healthy connected worker whose transcript mentions 'not signed in' and "
  + "'usage limit' stays READY, and its screen is never scraped", async () => {
  const h = harness();
  // exactly U329's scenario: the words are in the scrollback, from an overlay the operator already
  // dismissed and from the objective this shell itself typed into the pane.
  h.st.buffer.push(AUTH_TEXT);
  h.st.buffer.push("investigate why we keep hitting the usage limit on Grok\r\n");
  h.st.buffer.push("Grok Build usage limit reached — try again later\r\n");
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  assert.equal(result.state, "READY");
  assert.deepEqual(h.st.states, ["MCP_CONNECTING", "READY"]);
  assert.equal(result.readiness.process_supervised, true);
  assert.equal(result.readiness.node_registered, true);
  assert.equal(result.readiness.mcp_connected, true);
  for (const unobserved of ["provider_authenticated", "workspace_accepted", "mcp_discovered",
    "identity_validated", "permission_resolved"]) {
    assert.equal(unobserved in result.readiness, false, `${unobserved} must be absent`);
  }
  assert.equal(h.st.classificationReads, 0,
    "a worker answering over a connected MCP session must not have its transcript classified");
});

test("NEGATIVE CONTROL, second form: the words arrive DURING the run and the answer still wins",
  async () => {
    const h = harness({
      mcp: "connected",
      onPrompt: (st, token) => {
        st.buffer.push(AUTH_TEXT);                    // the provider prints it mid-turn…
        st.operations += 1;
        st.buffer.push(`\r\n${token}\r\n`);           // …and answers on the same poll
      },
    });
    const result = await h.readiness.run("pane-2");
    assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  });

test("an exited worker is FAILED by its exit code, with the code recorded and no classification",
  async () => {
    const h = harness({ processState: "exited", exitCode: 0, mcp: "disconnected" });
    h.st.buffer.push(AUTH_TEXT);
    const result = await h.readiness.run("pane-2");
    assert.equal(result.state, "FAILED");
    assert.equal(result.decided_by, "process_exit");
    assert.equal(result.failure.exit_code, 0);
    assert.equal(result.failure.provider_terminal_state, "FAILED");
    assert.notEqual(result.failure.provider_terminal_state, "AUTH_REQUIRED");
    assert.equal(h.st.classificationReads, 0);
  });

// 19.7, gate-validator round 1 BLOCKING-1: the staleness window this unit added must not reach into
// readiness. A worker whose session is `stale` HAS connected; readiness exists to provoke it, and
// its challenge is answered by a real MCP call. Binding this path to freshness meant the run never
// typed anything and wrote a durable STALLED onto a healthy pane — U329's defect, restored by the
// unit written to remove it.
test("a STALE session still gets its readiness challenge — provocation, not classification", async () => {
  const h = harness({ mcp: "stale" });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  assert.equal(h.st.writes.length, 1, "the challenge must be typed, not skipped");
  assert.equal(h.st.classificationReads, 0, "and no screen may be scraped on the way there");
});

// The SECOND `sessionEstablished` call site — the post-deadline check — which no existing test
// reached, because with a fixed `mcp` the polling loop above it always breaks first (round-2
// validator, MEDIUM-A: reverting that line to `=== "connected"` restored BLOCKING-1 and the whole
// suite still passed). It is only evaluated when the state CHANGES across the deadline, which is
// exactly the case it exists for: a worker that connects late and has gone quiet by the time we look.
test("a worker whose session is read only AFTER the deadline is not written off as STALLED", async () => {
  // An mcp deadline of 0 means the polling loop never executes its body, so the post-loop check is
  // the ONLY reader of the session state — which is what makes this line, and not its sibling
  // above, the one under test. (Racing a timer against the deadline was the first attempt and it
  // decided nothing: the two reads are microseconds apart.)
  const h = harness({ mcp: "stale", mcpTimeoutMs: 0 });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  assert.ok(!h.st.states.includes("STALLED"),
    "a session that exists must never be written off by the post-deadline check");
  assert.equal(h.st.writes.length, 1, "and it must still be provoked, not classified");
});

test("a session that has NEVER connected is still refused — the window did not widen that", async () => {
  const h = harness({ mcp: "configured", mcpTimeoutMs: 700 });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, false);
  assert.equal(result.state, "STALLED");
  assert.equal(h.st.writes.length, 0);
});

test("a modal that is really up, on consecutive bounded reads, is still reported", async () => {
  const h = harness({ mcp: "disconnected", mcpTimeoutMs: 5000 });
  h.st.buffer.push(TRUST_TEXT);
  const result = await h.readiness.run("pane-2");
  assert.equal(result.state, "WORKSPACE_TRUST_REQUIRED");
  assert.equal(result.decided_by, "screen_text_bounded_window");
  assert.equal(result.failure.provider_terminal_state, "WORKSPACE_TRUST_REQUIRED");
});

test("a DISMISSED overlay does not pin a working worker — the audited bug, from its own scenario",
  async () => {
    // Grok's promo overlay, dismissed, its bytes still in the buffer, provider fully functional.
    // Under the shipped code every readiness pass re-read them and NEVER REACHED the connection
    // check, so the worker could not leave PROVIDER_SETUP_REQUIRED without a fresh pane.
    const h = harness({ provider: "grok_build", mcp: "connected" });
    h.st.buffer.push("What's New — Connectors available. Press Enter to continue\r\n");
    const result = await h.readiness.run("pane-2");
    assert.equal(result.ready, true, `expected READY, got ${result.state}`);
    assert.equal(h.st.classificationReads, 0, "a talking provider's screen is not evidence");
  });

test("a classified state has an exit path: the overlay clears mid-run and the SAME run continues",
  async () => {
    const h = harness({
      provider: "grok_build", mcp: "disconnected", mcpTimeoutMs: 5000,
      onTick: (st) => {
        if (st.ticks === 1) st.buffer.push("clean output\r\n".repeat(400));   // redrawn over it
        if (st.ticks === 2) st.mcp = "connected";
      },
    });
    h.st.buffer.push("What's New — Connectors available. Press Enter to continue\r\n");
    const result = await h.readiness.run("pane-2");
    assert.equal(result.ready, true, `expected READY, got ${result.state}`);
    assert.ok(h.st.classificationReads > 0, "this path DOES read the screen — that is why it matters");
  });

test("the MCP connection is consulted even when the screen would classify", async () => {
  const h = harness({ provider: "grok_build", mcp: "connected" });
  h.st.buffer.push(TRUST_TEXT);
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  assert.equal(h.st.classificationReads, 0);
});

test("MCP that never connects is a timeout, named as one", async () => {
  const h = harness({ mcp: "disconnected", mcpTimeoutMs: 700 });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.state, "STALLED");
  assert.equal(result.failure.stage, "mcp_readiness_timeout");
});

test("the U328 write gate still gates the readiness prompt — and its refusal is no longer the "
  + "worker's state (U373)", async () => {
  const h = harness({ refusal: { state: "MCP_PERMISSION_REQUIRED",
    terminal_state: "MCP_PERMISSION_REQUIRED", reason: "Sovereign MCP permission is unresolved" } });
  const result = await h.readiness.run("pane-2");
  // The gate reads the WHOLE retained buffer (that is deliberate — invariant 1 — and unchanged
  // here). What changed at the 19.4 gate review is that its answer states whether we may TYPE, not
  // what the provider is: a refusal we never got past is a stall, carrying the gate's reason.
  assert.equal(result.state, "STALLED");
  assert.equal(result.failure.stage, "readiness_prompt_withheld");
  assert.equal(result.failure.write_withheld.state, "MCP_PERMISSION_REQUIRED");
  assert.notEqual(result.failure.decided_by, "screen_text_bounded_window");
  assert.equal(h.st.writes.length, 0, "nothing may be typed into a pane the gate refused");
});

test("a readiness turn whose window cannot be answered fails CLOSED, and says which", async () => {
  // capacity below the prompt's own length: the nonce window is trimmed the moment it is written,
  // so `since()` answers null. A shell that fell back to a wider read would call this READY.
  const h = harness({ capacity: 64, responseDeadlineMs: 700 });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, false);
  assert.equal(result.state, "STALLED");
  assert.equal(result.failure.stage, "readiness_response_timeout");
  assert.match(String(result.failure.window_unanswerable), /no longer held exactly/);
});

test("the pane's ECHO of our own prompt is not an answer to it", async () => {
  // The prompt is drawn into the pane the moment we type it. Readiness is the provider composing
  // the reply the instruction describes; accepting anything the prompt itself put on the screen
  // would make every pane that renders our keystrokes READY.
  const h = harness({
    responseDeadlineMs: 700,
    onPrompt: (st) => { st.operations += 1; },        // the tool call happens; nothing answers
  });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, false);
  assert.equal(result.failure.stage, "readiness_response_timeout");
});

test("U385 NEGATIVE CONTROL: a ConPTY REPAINT of our own prompt is not an answer, however many "
  + "times it redraws", async () => {
  // The defect this replaces, measured on a real pane by the 19.4 round-3 receipt: the prompt asked
  // the provider to "reply exactly <token>" and the run promoted on the SECOND occurrence of that
  // token, reasoning that the first was the pane's echo. A terminal RESIZE (`ESC[8;7;65t`) makes
  // ConPTY repaint the screen and re-emit the same line, so the token reached two occurrences with
  // the pane having said nothing — READY on a silent worker. Threshold-raising is not a fix, which
  // is why this control repaints FOUR times: under the old rule `>= 2` and `>= 3` both promote.
  const h = harness({
    responseDeadlineMs: 900,
    onPrompt: (st, answer, prompt) => {
      st.operations += 1;                             // the tool call did happen
      for (let i = 0; i < 4; i += 1) st.buffer.push(`\r\n${prompt}\r\n`);   // …and ConPTY redrew
    },
  });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, false,
    "a repaint of our own prompt was accepted as the provider answering (U385)");
  assert.equal(result.failure.stage, "readiness_response_timeout");
});

test("U385: the readiness prompt cannot contain the reply it asks for — for any node, turn or "
  + "stamp", () => {
  // The property the scheme rests on, asserted directly: whatever the prompt puts on the screen,
  // the expected string is not in it, so ONE occurrence is the provider having composed it — with
  // the single exception the product file states and [[U393]] retracted this sentence's absolute
  // for: a DIFFERENTIAL repaint re-emitting head, cursor addressing and tail while skipping the 41
  // characters between them normalises to the joined string. Not observed in six in-Electron runs;
  // what defends the promotion in production is the MCP tool-call count, which no repaint fabricates.
  for (const [nodeId, turn, stamp] of [
    ["node-w", 1, "abc"], ["node-w", 2, "0"], ["n", 11, "kzz9q1"],
    ["SOVEREIGN_READY_1_abc", 1, "abc"],          // a node named after a fragment changes nothing
  ]) {
    const c = readinessChallenge(nodeId, turn, stamp);
    assert.equal(c.expected, `${c.head}${c.tail}`);
    assert.ok(!c.prompt.includes(c.expected),
      `the prompt for ${nodeId}/${turn}/${stamp} contains its own answer`);
    assert.ok(c.prompt.includes(c.head) && c.prompt.includes(c.tail),
      "the provider cannot compose an answer out of fragments it was not given");
  }
});

test("U385: a challenge whose prompt DOES contain its answer is never written — the turn fails "
  + "closed", async () => {
  // The guard, exercised through the run: `waitForTurn` is given a challenge of the old shape and
  // must refuse to ask at all, because on such a prompt an echo and an answer are the same bytes.
  const h = harness();
  const unsound = { head: "H", tail: "T", expected: "SOVEREIGN_READY_1_x",
    prompt: "reply exactly SOVEREIGN_READY_1_x" };
  const result = await h.readiness.waitForTurn(
    { paneId: "pane-2", nodeId: "node-w", chrome: { provider: "claude_code" } },
    unsound, Date.now() + 2000);
  assert.equal(result.ok, false);
  assert.equal(result.stage, "readiness_challenge_unsound");
  assert.equal(h.st.writes.length, 0, "an unsound challenge must not reach the pane");
});

test("U385 round 4: an EARLIER run's answer, repainted into this run's window, is not this run's "
  + "answer", async () => {
  // The gate-validator's round-4 MAJOR, as a test. "One occurrence is proof" is true of the prompt
  // we just typed and FALSE of a previous run's reply, which is still in the ring and still on the
  // visible screen — and readiness re-runs on every pane that is not READY (`main.js` :2437). So:
  // run 1 answers and goes READY; run 2 is answered by NOBODY, and the pane merely redraws what run
  // 1 said, four times, after run 2's mark. Run 2 must not be promoted by it.
  //
  // This is the CALL SITE, which is where this unit's defects keep living: `readinessChallenge` was
  // already pinned pure and correct while the freshness of what it was handed was asserted nowhere.
  // Freezing that stamp (mutation R22) leaves all other tests green and reddens exactly this one.
  const h = harness({
    responseDeadlineMs: 900,
    onPrompt: (st, answer) => {
      st.operations += 1;                                  // the tool call happens on BOTH runs
      if (st.firstAnswer === undefined) {
        st.firstAnswer = answer;
        st.buffer.push(`\r\n${answer}\r\n`);               // run 1: a real reply
      } else {
        for (let i = 0; i < 4; i += 1) st.buffer.push(`\r\n${st.firstAnswer}\r\n`);  // run 2: a redraw
      }
    },
  });
  const first = await h.readiness.run("pane-2");
  assert.equal(first.ready, true, `run 1 should be READY, got ${first.state}`);
  const second = await h.readiness.run("pane-2");
  assert.equal(second.ready, false,
    "run 1's answer, redrawn after run 2's mark, was accepted as run 2 answering");
  assert.equal(second.failure.stage, "readiness_response_timeout");
  assert.notEqual(h.st.writes[1], h.st.writes[0],
    "two readiness runs on one pane must not ask the same question");
});

test("U385 round 4: the same instant, twice, still yields two different challenges", () => {
  // Why the sequence exists rather than the clock alone. Measured, not assumed: splicing R23 (the
  // sequence deleted, the clock kept) reddens BOTH this test and the behavioural one above — a run
  // returns as soon as its pane answers, not when its deadline expires, so on this host both runs
  // fell inside one millisecond and collided. That is the point and also why it may not be relied
  // on: the behavioural test catches R23 by the grace of THIS host's timing, and would go green on a
  // slower one. This test cannot: it hands `challengeStamp` the same instant twice, deliberately, so
  // clock-only freshness fails here at any speed.
  //
  // What this test does NOT claim (round-4 auditor, U393): that one pane's two turns can collide in
  // production. They cannot — turn 2's stamp is minted after turn 1 returns, and the write path
  // awaits a 500 ms paste settle. The property under test is that freshness does not rest on the
  // clock AT ALL, which is what the validator's frozen-stamp probe falsified.
  const a = challengeStamp(1_000_000);
  const b = challengeStamp(1_000_000);          // the identical instant, deliberately
  assert.notEqual(a, b, "two challenges minted in the same millisecond were identical");
  const ca = readinessChallenge("node-w", 1, a);
  const cb = readinessChallenge("node-w", 1, b);
  assert.notEqual(ca.expected, cb.expected);
  assert.ok(!cb.prompt.includes(ca.expected),
    "the second prompt carries the first's expected answer — a redraw of run 1 would satisfy run 2");
});

test("U394/V4: the nonce window is floored at THIS TURN'S mark — an answer already on the screen "
  + "when the turn began is not an answer to it", async () => {
  // The round-5 gate-validator's coverage gap, as a test: `since(paneId, mark)` was the mark floor
  // the whole scheme rests on, and nothing reddened when it was replaced by a read from position 0.
  // Driven through `waitForTurn` so the challenge can be planted on the screen BEFORE the mark is
  // taken — which is the only way to tell the floor apart from the string search it wraps.
  const h = harness({ mcp: "connected", responseDeadlineMs: 700,
    onPrompt: (st) => { st.operations += 1; } });        // the tool call happens; nobody answers
  const challenge = {
    head: "SOVEREIGN_READY_1_planted", tail: "SOVEREIGN_TAIL_planted",
    expected: "SOVEREIGN_READY_1_plantedSOVEREIGN_TAIL_planted",
    prompt: "Readiness check only. Reply with the fragment SOVEREIGN_READY_1_planted written "
      + "immediately before the fragment SOVEREIGN_TAIL_planted, with nothing between them.",
  };
  h.st.buffer.push(`\r\n${challenge.expected}\r\n`);     // …left over from an earlier run
  const result = await h.readiness.waitForTurn(
    { paneId: "pane-2", nodeId: "node-w", chrome: { provider: "claude_code" } },
    challenge, Date.now() + 700);
  assert.equal(result.ok, false,
    "a reply that was already on the screen before we asked was accepted as the answer");
  assert.equal(result.stage, "readiness_response_timeout");
});

test("U394/V8: the two turns of ONE run ask two different questions", async () => {
  // Turn-level freshness, which the cross-run test above does not cover: grok owes two turns, and if
  // both carried the same stamp then turn 1's reply — still on the screen, and repainted by ConPTY
  // as this unit measured six times over — would satisfy turn 2 (U385, one level down).
  const h = harness({ provider: "grok_build", mcp: "connected" });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  assert.equal(h.st.writes.length, 2);
  assert.notEqual(h.st.writes[1], h.st.writes[0], "one run's two turns asked the same question");
  const firstAnswer = answerTo(h.st.writes[0]);
  assert.ok(firstAnswer && !h.st.writes[1].includes(firstAnswer),
    "turn 2's prompt carries turn 1's expected answer — a redraw of turn 1 would satisfy it");
});

test("an answer with no MCP tool call behind it is not readiness", async () => {
  const h = harness({
    responseDeadlineMs: 700,
    onPrompt: (st, answer) => { st.buffer.push(`\r\n${answer}\r\n`); },   // answer, no operation
  });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, false);
  assert.equal(result.failure.stage, "readiness_response_timeout");
});

test("U386(b): a worker that dies mid-turn reports the exit, with its code, as FAILED", async () => {
  // Invariant 27. A process that exited is FAILED — which is how the MCP-connection loop above has
  // always rendered the identical condition. Rendering it STALLED because the exit happened to land
  // inside a readiness turn described the worker by OUR timing rather than by its state, and put a
  // "stalled" (alive, unresponsive) badge on a dead process. The two paths now agree.
  const h = harness({
    responseDeadlineMs: 2000,
    onPrompt: (st) => { st.record = { ...st.record, state: "exited", exitCode: 9 }; },
  });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.state, "FAILED");
  assert.deepEqual(h.st.states, ["MCP_CONNECTING", "FAILED"]);
  assert.equal(result.failure.stage, "process_exited_during_readiness");
  assert.equal(result.failure.exit_code, 9);
  assert.equal(result.failure.decided_by, "process_exit");
  assert.equal(result.failure.provider_terminal_state, "FAILED");
});

test("grok still owes two readiness turns", async () => {
  const h = harness({ provider: "grok_build" });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  assert.equal(h.st.writes.length, 2);
  assert.equal(result.readiness.readiness_responses, 2);
});

test("the readiness prompt itself classifies clean for every provider", () => {
  // It lands inside the window this run classifies. Anything variable in it (an objective, a debate
  // proposition) would be U329's self-inflicted false positive, restored.
  const prompt = readinessChallenge("node-w", 1, "abc").prompt;
  for (const provider of ["claude_code", "openai_codex_cli", "grok_build", "google_antigravity"]) {
    assert.equal(classifyProviderScreen(provider, prompt), null, `classified for ${provider}`);
  }
});

// ---------------------------------------------------------------------------------------------
// 5. U373 — THE GATE MAY SAY "NOT YET"; IT MAY NOT SAY WHAT THE WORKER IS
//
// The 19.4 gate review found the negative control above true of this module and FALSE of the
// shell: `writeRefusal` was bound to a U328 write gate that read `buffer.snapshot()` — the whole
// retained scrollback — so a healthy connected worker whose transcript merely MENTIONED "not signed
// in" was still reported AUTH_REQUIRED, and the audited pin survived the reorder that existed to
// remove it. Both mandatory reviewers found it independently, with their own spellings. Past tense:
// 19.4-followon bounded that read, which is what the test below now asserts.
//
// These tests wire the PRODUCTION `createPaneWriter` refusal into readiness, exactly as
// `main.js` does, so a fix that only holds against a stubbed `writeRefusal` fails here.
// ---------------------------------------------------------------------------------------------

/** The real pane-writer refusal over a real ring buffer — `main.js`'s binding, not a double.
 *
 *  The screen reader is now `paneScreenFromWindow` over `createScreenWindow`, which is what `main.js`
 *  builds and hands BOTH the gate and this state machine (U373 residual, unit 19.4-followon). Until
 *  that unit this helper hand-rolled `{ readable: true, text: buffer.snapshot() }` — and that is
 *  precisely why the test below could assert a residual that the production binding no longer has:
 *  a "production" helper that reimplements the binding grades the double, not the shell. */
function productionWriteRefusal(buffer, provider) {
  const writer = createPaneWriter({
    paneScreen: paneScreenFromWindow(createScreenWindow({ bufferFor: () => buffer })),
    providerFor: () => provider,
    log: () => {},
    write: () => true,
    sleep: async () => {},
    pasteSettleMs: () => 0,
    submitConfirmMs: () => 0,
    conductorTarget: () => null,
    workerPaneFor: () => null,
  });
  return (paneId) => writer.refusalFor(paneId);
}

test("THE NEGATIVE CONTROL, END TO END, THROUGH THE PRODUCTION WRITE GATE: a healthy connected "
  + "worker whose SCROLLBACK mentions an auth failure reaches READY (U373 residual closed)", async () => {
  const h = harness({ provider: "grok_build", mcp: "connected", responseDeadlineMs: 2000 });
  // the operator's own note, and an overlay they dismissed an hour ago — both still in the buffer
  h.st.buffer.push("operator note: earlier today this node was not signed in; that is fixed\r\n");
  // Tied to the constant, never a literal: the 24 → 80 raise silently broke a sibling fixture in
  // this same unit ([[U367]]'s class), so a fixture whose whole job is to exceed the bound reads the
  // bound (round-2 spec-auditor, MEDIUM-4).
  h.st.buffer.push(CLEAN.repeat(TAIL_LINES + 40));    // a full screen redrawn over it, and then some
  h.io.writeRefusal = productionWriteRefusal(h.st.buffer, "grok_build");
  // THE GATE PERMITS, because a mention forty screens back is not what the pane is SHOWING. This is
  // the assertion that inverted at 19.4-followon: it read "the write gate must still see the whole
  // buffer" while the directive's own negative control (`OP-13.1`: U329 must not pin a healthy
  // worker) could not hold end-to-end.
  assert.equal(h.io.writeRefusal("pane-2"), null,
    "the gate reads the pane's current screen; a mention in the scrollback is not a modal");
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  assert.equal(result.state, "READY");
  assert.equal(h.st.writes.length, 2,
    "the prompts this worker stalled on for two units are delivered — two, because grok owes two "
    + "readiness turns, and a run that delivered one and promoted anyway would be a different bug");
});

test("U373: the gate STILL refuses when the modal is what the pane is showing NOW — bounding the "
  + "read did not open it", async () => {
  // The other direction of the same change, because a gate that reads less is a gate that refuses
  // less, and this is the half that must not have moved.
  const h = harness({ provider: "claude_code", mcp: "connected", responseDeadlineMs: 700 });
  h.st.buffer.push("operator note: nothing interesting\r\n");
  h.st.buffer.push(TRUST_TEXT);                       // …and this is the current screen
  h.io.writeRefusal = productionWriteRefusal(h.st.buffer, "claude_code");
  assert.ok(h.io.writeRefusal("pane-2"), "a modal on the current screen must still refuse");
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, false);
  assert.equal(h.st.writes.length, 0, "not one byte into a pane showing a modal");
});

test("U363 THROUGH THE PRODUCTION WRITE GATE: a permission modal the READINESS classifier does not "
  + "recognise still withholds the prompt, and is never rendered as a provider verdict", async () => {
  // The two instruments deliberately disagree: `classifyProviderScreen` returns null for a numbered
  // tool-approval menu (nine of the 19.3 validator's ten screens), while the widened write-gate
  // verdict refuses it. So this leg can only be produced by the gate — and the worker must still be
  // reported as "we could not ask", never as a provider state nobody measured (U373's rule).
  const modal = "Allow this tool to run?\r\n> 1. Yes\r\n  2. No\r\n";
  assert.equal(classifyProviderScreen("claude_code", modal), null,
    "if the classifier learns this shape, this test is measuring something else");
  const h = harness({ provider: "claude_code", mcp: "connected", responseDeadlineMs: 700 });
  h.st.buffer.push(modal);
  h.io.writeRefusal = productionWriteRefusal(h.st.buffer, "claude_code");
  const gate = h.io.writeRefusal("pane-2");
  assert.equal(gate.terminal_state, "PANE_AWAITING_OPERATOR_DECISION");
  const result = await h.readiness.run("pane-2");
  assert.equal(result.state, "STALLED");
  assert.equal(result.failure.stage, "readiness_prompt_withheld");
  assert.equal(result.failure.decided_by, "write_gate_withheld");
  assert.equal(result.failure.write_withheld.terminal_state, "PANE_AWAITING_OPERATOR_DECISION",
    "the gate's own words are kept where an operator can read them");
  assert.equal(h.st.writes.length, 0);
});

test("U373: a write the gate withholds for the whole deadline is a STALL, reported as one with the "
  + "gate's reason — never a provider verdict read off a scrollback", async () => {
  const h = harness({
    mcp: "connected",
    responseDeadlineMs: 700,
    refusal: {
      state: "AUTH_REQUIRED",
      reason: "the screen may be showing a sign-in prompt",
      terminal_state: "AUTH_REQUIRED",
    },
  });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.state, "STALLED", "a withheld question is not an answer about the provider");
  assert.equal(result.failure.stage, "readiness_prompt_withheld");
  assert.equal(result.failure.decided_by, "write_gate_withheld");
  assert.equal(result.failure.write_withheld.reason, "the screen may be showing a sign-in prompt");
  assert.equal(h.st.writes.length, 0);
});

test("U373 EXIT PATH: a refusal that clears is written to, and the worker reaches READY in the SAME "
  + "run", async () => {
  const h = harness({
    mcp: "connected",
    responseDeadlineMs: 4000,
    refusal: { state: "WORKSPACE_TRUST_REQUIRED", reason: "a trust modal may be up" },
    onTick: (st) => { if (st.ticks >= 2) st.refusal = null; },
  });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
  assert.equal(h.st.writes.length, 1);
});

test("U379: a worker that DIES while the gate withholds is reported by its exit code, not by the "
  + "modal on its screen", async () => {
  // The round-2 defect, from its own scenario: the withheld-write loop classified with the record
  // the turn began with, so the strongest signal a process ever emits was not consulted for the
  // whole deadline while the weakest one decided. Both mandatory reviewers found it independently.
  const h = harness({
    mcp: "connected",
    responseDeadlineMs: 4000,
    refusal: { state: "AUTH_REQUIRED", reason: "the screen may be showing a sign-in prompt" },
    // The process dies after the first poll. The screen has SEEN the modal once by then and needs
    // one more agreeing read to make it the verdict — so with the stale record the second poll
    // confirms `WORKSPACE_TRUST_REQUIRED` and the exit is never consulted, which is the defect.
    onTick: (st) => { st.record = { ...st.record, state: "exited", exitCode: 137 }; },
  });
  h.st.buffer.push(TRUST_TEXT);              // …and the screen would happily classify
  const result = await h.readiness.run("pane-2");
  assert.equal(result.state, "FAILED");       // U386(b): an exit is an exit, whenever it lands
  assert.equal(result.failure.stage, "process_exited_during_readiness");
  assert.equal(result.failure.decided_by, "process_exit",
    "a dead process is decided by its exit, never by what its last screenful contained");
  assert.equal(result.failure.exit_code, 137);
  assert.notEqual(result.state, "WORKSPACE_TRUST_REQUIRED");
});

test("U379: a structured failure reports the process it ACTUALLY was — the fields are read live, "
  + "not from the record the turn began with", async () => {
  const h = harness({
    mcp: "connected",
    responseDeadlineMs: 4000,
    onPrompt: (st) => { st.record = { ...st.record, state: "exited", exitCode: 9 }; },
  });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.failure.decided_by, "process_exit");
  assert.equal(result.failure.exit_code, 9);
  assert.equal(result.failure.process_state, "exited",
    "a record claiming `process_state: running` beside an exit code contradicts itself");
});

test("U379: a delivery the gate refused is not labelled as a deadline that never elapsed", async () => {
  const h = harness({ mcp: "connected", responseDeadlineMs: 4000, acceptWrites: false });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.failure.stage, "readiness_prompt_delivery");
  assert.equal(result.failure.decided_by, "write_not_delivered");
});

test("U373: while a write is withheld the BOUNDED window still gets to state what is wrong",
  async () => {
    const h = harness({
      mcp: "connected",
      responseDeadlineMs: 4000,
      refusal: { state: "AUTH_REQUIRED", reason: "the screen may be showing a sign-in prompt" },
    });
    h.st.buffer.push(TRUST_TEXT);                 // what the pane is ACTUALLY showing now
    const result = await h.readiness.run("pane-2");
    assert.equal(result.state, "WORKSPACE_TRUST_REQUIRED",
      "the bounded window decides, not the gate's refusal - two instruments, two questions");
    assert.equal(result.failure.decided_by, "screen_text_bounded_window");
  });

test("U329 NEGATIVE CONTROL, DELAYED ANSWER: a connected worker that takes several polls to answer "
  + "is not classified by a mention twenty lines up its transcript", async () => {
  const h = harness({
    mcp: "connected",
    responseDeadlineMs: 6000,
    // the provider is healthy and simply slow: eight polls pass before the nonce comes back, and
    // its transcript already held the words. Without the turn's own floor the tail classifies at
    // poll 2 — the audited pin, back through the answer wait.
    onPrompt: (st, token) => { st.pending = token; },
    onTick: (st) => {
      if (st.ticks === 8 && st.pending) {
        st.operations += 1;
        st.buffer.push(`\r\n${st.pending}\r\n`);
        st.pending = null;
      }
    },
  });
  h.st.buffer.push(AUTH_TEXT);                    // the words the directive names, as transcript
  h.st.buffer.push(CLEAN.repeat(3));
  const result = await h.readiness.run("pane-2");
  assert.equal(result.ready, true, `expected READY, got ${result.state}`);
});

test("U329 DELAYED ANSWER, the other direction: a modal drawn IN ANSWER to our prompt still "
  + "classifies", async () => {
  const h = harness({
    mcp: "connected",
    responseDeadlineMs: 6000,
    onPrompt: (st) => { st.buffer.push(TRUST_TEXT); },     // after the mark: this IS the answer
  });
  const result = await h.readiness.run("pane-2");
  assert.equal(result.state, "WORKSPACE_TRUST_REQUIRED");
});
