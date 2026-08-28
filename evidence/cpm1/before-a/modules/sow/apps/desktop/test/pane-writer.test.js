"use strict";
/**
 * Phase 19 unit 19.3 — U328: nothing the SYSTEM writes may reach a pane that might be showing a
 * provider modal.
 *
 * The cold audit found `writePanePrompt` typing into panes blind. `controlAssignTask` gates its
 * assignment on the worker's operational state, but `notifyNode` (every peer message, every debate
 * turn, every deadline notice) and `runConductorReadiness` did not — and the conductor pane is the
 * one the operator converses in (OP-8). A trust or permission modal is a numbered menu whose
 * highlighted option is the permissive one, so the bytes that matter are not the prompt body but
 * the CARRIAGE RETURN behind it: that keystroke ANSWERS the modal. Invariant 1 says the operator
 * holds final authority; D-P18-13 says a provider's own accept mode is not operator approval. The
 * acceptance standard is therefore not "unlikely to answer a modal" but UNABLE to.
 *
 * The voice path (`voice/conductor-write.js`) has had this guard since 17C ("an open permission
 * prompt receives NOTHING"). This is the same property for the direction nobody guarded.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const {
  paneWriteRefusal, createPaneWriter, paneScreenFromWindow, paneProviderResolver,
} = require("../control/pane-writer");
const { createScreenWindow, TAIL_LINES } = require("../control/worker-readiness");
const { PROVIDER_STATES } = require("../control/provider-readiness");
const { RingBuffer } = require("../../../terminal/session/ring-buffer");

const TRUST_MODAL = "Do you trust the contents of this project?\r\n  1. Yes, I trust this folder\r\n  2. No\r\n";
const AUTH_MODAL = "You are not signed in. Run `grok login` to continue.\r\n";
const MCP_MODAL = "Permission required: allow this tool from the Sovereign MCP server?\r\n  1. Yes\r\n";
const GROK_OVERLAY = "What's New — Connectors available. Press Enter to continue";
const CLEAN = "[1m❯ [0m ready\r\n";

/** A pane harness: records every byte the writer attempts, and lets a test change the screen
 *  between the body write and the submit key — which is the window a modal really opens in.
 *  `screen` and `readable` both accept an ARRAY consumed one entry per READ (the last entry holds
 *  thereafter), because a pane that dies mid-write changes both, and a flag that cannot change
 *  between the body and the Enter cannot express the case the Enter exists to be withheld in. */
function harness(opts = {}) {
  const st = {
    screens: Array.isArray(opts.screen) ? opts.screen.slice() : [opts.screen === undefined ? CLEAN : opts.screen],
    readables: Array.isArray(opts.readable) ? opts.readable.slice() : [opts.readable !== false],
    writes: [],
    logs: [],
    reads: 0,
    acceptWrites: opts.acceptWrites !== false,
    provider: opts.provider === undefined ? "grok_build" : opts.provider,
    workerPanes: opts.workerPanes || { "node-w": "pane-2" },
    conductor: opts.conductor === undefined ? { nodeId: "node-c", paneId: "pane-1" } : opts.conductor,
  };
  const io = {
    paneScreen: () => {
      st.reads += 1;
      const at = (arr) => arr[Math.min(st.reads - 1, arr.length - 1)];
      return { readable: at(st.readables), text: at(st.screens) };
    },
    providerFor: () => st.provider,
    write: (paneId, data) => { st.writes.push([paneId, data]); return st.acceptWrites; },
    sleep: async () => {},
    pasteSettleMs: () => 0,
    submitConfirmMs: () => 0,
    log: (m) => st.logs.push(m),
    conductorTarget: () => st.conductor,
    workerPaneFor: (nodeId) => st.workerPanes[nodeId] || null,
  };
  return { st, writer: createPaneWriter(io), io };
}

// ---- the pure decision -------------------------------------------------------------------------

test("a modal screen refuses, a clean screen allows", () => {
  for (const [screen, state] of [
    [TRUST_MODAL, "WORKSPACE_TRUST_REQUIRED"],
    [AUTH_MODAL, "AUTH_REQUIRED"],
    [MCP_MODAL, "MCP_PERMISSION_REQUIRED"],
    [GROK_OVERLAY, "PROVIDER_SETUP_REQUIRED"],
  ]) {
    const r = paneWriteRefusal({ provider: "grok_build", screenReadable: true, screen });
    assert.ok(r, `${state} must refuse the write`);
    assert.strictEqual(r.state, state);
    assert.ok(typeof r.reason === "string" && r.reason.length > 0, "a refusal must carry a reason");
  }
  assert.strictEqual(paneWriteRefusal({ provider: "grok_build", screenReadable: true, screen: CLEAN }), null);
});

// ---- U363: the verdict half, and exactly how far it goes ---------------------------------------
// The 19.3 gate-validator built ten realistic permission screens and ran them past this module with
// `screenReadable: true`. NINE were written into. That probe is reproduced here verbatim in shape,
// as the falsification for the widened verdict — and the three that STILL survive are asserted too,
// because a residual that is only narrated is a residual nobody re-checks.
const VALIDATOR_SCREENS = Object.freeze([
  ["claude tool permission", "Do you want to proceed?\r\n❯ 1. Yes\r\n  2. Yes, and don't ask again\r\n  3. No\r\n", true],
  ["file edit permission", "Do you want to make this edit to main.js?\r\n❯ 1. Yes\r\n  2. No\r\n", true],
  ["generic confirmation", "Overwrite the existing file? (y/N) ", true],
  ["antigravity apply change", "Apply these changes to 3 files?\r\n  1. Yes, apply\r\n  2. No, keep planning\r\n", true],
  ["host key fingerprint", "The authenticity of host 'build-01' can't be established.\r\n"
    + "Do you want to continue connecting?\r\n", true],
  ["tool approval without the words sovereign or mcp",
    "Allow this tool to run?\r\n> 1. Yes\r\n  2. No\r\n", true],
  ["workspace trust (the one screen 19.3 already refused)",
    "Do you trust the contents of this project?\r\n  1. Yes, I trust this folder\r\n", true],
  // …and the three this shell still cannot see. Each is a shape no pattern in
  // `control/modal-affordance.js` was ever OBSERVED matching, and the list was moved from
  // `voice/pane-state.js` unchanged rather than extended by guesswork — inventing vendor wording is
  // how a gate comes to look stronger than it is. They are U363's remaining surface.
  ["codex y/a/n approval", "Allow command `rm -rf build`? (y = yes, a = always, n = no) ", false],
  ["elevation password prompt", "Password for Administrator: ", false],
  ["a bare numbered menu", "Choose a profile:\r\n  1. Default\r\n  2. Restricted\r\n", false],
]);

test("U363: the write gate refuses the permission screens 19.3 wrote into — seven of the "
  + "validator's ten, with the other three asserted as the residual", () => {
  const refusedNow = [];
  for (const [label, screen, mustRefuse] of VALIDATOR_SCREENS) {
    // provider `null` deliberately: these must refuse on the shared rules, not because a particular
    // provider's phrase family happened to fire.
    const r = paneWriteRefusal({ provider: null, screenReadable: true, screen });
    assert.strictEqual(Boolean(r), mustRefuse,
      `${label}: expected ${mustRefuse ? "a refusal" : "no refusal (recorded residual)"}, got `
      + `${r ? r.terminal_state : "null"}`);
    if (r) {
      refusedNow.push(label);
      assert.ok(typeof r.reason === "string" && r.reason.length > 0);
      assert.ok(/PANE_AWAITING_OPERATOR_DECISION|WORKSPACE_TRUST_REQUIRED/.test(r.terminal_state),
        `${label}: a modal refusal must name itself, got ${r.terminal_state}`);
    }
  }
  assert.strictEqual(refusedNow.length, 7, "the count is the claim; it may not drift silently");
});

// The one BEHAVIOUR change the round-1 spec-audit asked for, ungraded until the round-2
// gate-validator deleted it and watched all 942 tests stay green (its MAJOR-1). The excerpt in a
// refusal reason is PROVIDER-CONTROLLED text, the numbered-menu pattern matches ACROSS a newline,
// and that reason is interpolated into a single-line shell log (`pane-writer.js`) and into the
// conductor's operator-visible chrome. Un-collapsed, a model's own output forges a second log line
// and a second chrome line — it writes the record that is supposed to be watching it.
test("U363: a refusal reason is ONE line, whatever the provider drew — the excerpt is collapsed "
  + "before it reaches a log, a chrome string or a structured failure", () => {
  const twoLine = "Run this command?\r\n\x1b[32m  1. Yes\x1b[0m\r\n  2. No\r\n";
  const r = paneWriteRefusal({ provider: null, screenReadable: true, screen: twoLine });
  assert.ok(r, "the two-line menu must refuse in the first place, or this grades nothing");
  assert.strictEqual(r.terminal_state, "PANE_AWAITING_OPERATOR_DECISION");
  assert.doesNotMatch(r.reason, /[\r\n]/,
    `a provider may not put a newline into a refusal reason — got ${JSON.stringify(r.reason)}`);
  // The match really did span the newline: proving the collapse had something to do.
  assert.match(r.reason, /1\. Yes 2\. No/,
    "the excerpt must still show both lines of what it refused, joined — legible, not verbatim");

  // And it is BOUNDED. A provider that repaints a screen's worth of text into one match may not
  // spend the log line, the chrome string and the IPC envelope on it.
  const flood = `Proceed? ${"x".repeat(4000)}\r\n  1. Yes\r\n  2. No\r\n`;
  const big = paneWriteRefusal({ provider: null, screenReadable: true, screen: flood });
  assert.ok(big, "the flooded screen must still refuse");
  assert.doesNotMatch(big.reason, /[\r\n]/);
  assert.ok(big.reason.length < 400,
    `a refusal reason may not carry a screen's worth of provider text — got ${big.reason.length}`);
});

test("U363: an authority-expanding mode banner refuses too — a provider's accept-mode is not "
  + "operator approval (D-P18-13)", () => {
  for (const banner of ["bypass permissions on", "accept edits on"]) {
    const r = paneWriteRefusal({ provider: "claude_code", screenReadable: true,
      screen: `❯ ready\r\n  ${banner}  · ? for shortcuts\r\n` });
    assert.ok(r, `"${banner}" must refuse`);
    assert.strictEqual(r.terminal_state, "PANE_AUTHORITY_EXPANDING_MODE");
  }
});

test("U396/V8: the modal refusal's own STATE is pinned, not just the fact that it refuses", () => {
  // The round-1 validator of this unit changed the refusal's `state` to "BUSY" and all 939 tests
  // stayed green. It still refuses, so this is observability rather than authority — but `state` is
  // what `runConductorReadiness` puts in the conductor's chrome and what `write_withheld.state`
  // reports to an operator, and a value nothing asserts is a value that can drift into a lie.
  const prompt = paneWriteRefusal({ provider: null, screenReadable: true,
    screen: "Do you want to proceed?\r\n❯ 1. Yes\r\n  2. No\r\n" });
  assert.deepStrictEqual(
    { state: prompt.state, terminal_state: prompt.terminal_state },
    { state: "PROVIDER_SETUP_REQUIRED", terminal_state: "PANE_AWAITING_OPERATOR_DECISION" });
  const mode = paneWriteRefusal({ provider: null, screenReadable: true,
    screen: "❯ ready\r\n  bypass permissions on\r\n" });
  assert.deepStrictEqual(
    { state: mode.state, terminal_state: mode.terminal_state },
    { state: "PROVIDER_SETUP_REQUIRED", terminal_state: "PANE_AUTHORITY_EXPANDING_MODE" });
  assert.ok(PROVIDER_STATES.includes(prompt.state),
    "callers write this into a node's operational state, so it must be one of the real ones");
});

test("U396/V5: the affordance is judged on the WHOLE window the gate was given, not a slice of it", () => {
  // The validator narrowed the affordance read to the last 200 characters and the suite stayed
  // green. On a real pane a modal is followed by its own footer chrome, so "only look at the end"
  // is a bypass with a plausible-sounding justification.
  const modal = "Do you want to proceed?\r\n❯ 1. Yes\r\n  2. No\r\n";
  const trailing = "  · ? for shortcuts\r\n".repeat(30);        // ~630 characters of footer
  const r = paneWriteRefusal({ provider: null, screenReadable: true, screen: modal + trailing });
  assert.ok(r, "a modal 600 characters above the last line is still the modal that is up");
  assert.strictEqual(r.terminal_state, "PANE_AWAITING_OPERATOR_DECISION");
});

test("U363: the widened verdict does not refuse ordinary provider output", () => {
  // The cost of a denylist is false refusals, and a gate that refuses everything is a mute shell.
  // These are the shapes a working provider actually prints while it is answering.
  for (const screen of [
    CLEAN,
    "❯ ready\r\n  · ? for shortcuts\r\n",
    "Here are the three options I considered:\r\n  1. Rewrite the loader\r\n  2. Patch the caller\r\n",
    "SOVEREIGN_READY_1_k3x9SOVEREIGN_TAIL_k3x9\r\n",
    "the test suite passed: 930 tests, 0 failures\r\n",
  ]) {
    assert.strictEqual(paneWriteRefusal({ provider: "claude_code", screenReadable: true, screen }),
      null, `ordinary output must not be refused: ${JSON.stringify(screen.slice(0, 40))}`);
  }
});

test("U363: the classifier's provider-state families still win when a screen carries both", () => {
  // "not signed in" beside "press enter to continue" is an authentication problem, and that is what
  // the operator needs told. Both refuse; the ORDER decides which reason is reported.
  const r = paneWriteRefusal({ provider: "grok_build", screenReadable: true,
    screen: "You are not signed in.\r\nPress Enter to continue\r\n" });
  assert.strictEqual(r.state, "AUTH_REQUIRED");
});

test("an UNREADABLE screen refuses — absence of evidence is not consent", () => {
  // Fail closed on ambiguity (Buildout Directive §4). A pane whose screen this shell cannot read is
  // a pane whose modal state it cannot rule out, and the write it wanted to make is a keystroke.
  const r = paneWriteRefusal({ provider: "grok_build", screenReadable: false, screen: "" });
  assert.ok(r, "an unreadable screen must refuse");
  assert.strictEqual(r.terminal_state, "PANE_SCREEN_UNREADABLE");
  assert.strictEqual(paneWriteRefusal({}).terminal_state, "PANE_SCREEN_UNREADABLE",
    "the default — no argument at all — must also refuse");
  // …and `screenReadable` must be the literal true, not merely truthy-by-accident
  assert.ok(paneWriteRefusal({ screenReadable: "yes", screen: CLEAN }),
    "only an explicit boolean true may open the gate");
});

// ---- the write path ----------------------------------------------------------------------------

test("THE FINDING: not one byte reaches a pane showing a trust modal", async () => {
  const { st, writer } = harness({ screen: TRUST_MODAL });
  const r = await writer.writePrompt("pane-2", "Readiness check only. Reply exactly TOKEN.");
  assert.strictEqual(r.written, false);
  assert.ok(r.refused, "the refusal must be returned, not swallowed");
  assert.strictEqual(r.refused.state, "WORKSPACE_TRUST_REQUIRED");
  assert.deepStrictEqual(st.writes, [], "not one character, and above all not the Enter");
  assert.ok(st.logs.some((m) => /REFUSED/.test(m)), "a withheld write must be observable (invariant 27)");
});

test("THE SHARP EDGE: a modal that opens AFTER the body write still never gets the Enter", async () => {
  // The submit key is the byte that answers a numbered menu. Checking only before the body leaves
  // exactly the window a provider modal opens in — the CLI draws its permission prompt in response
  // to what was just pasted.
  const { st, writer } = harness({ screen: [CLEAN, MCP_MODAL, MCP_MODAL] });
  const r = await writer.writePrompt("pane-2", "some assignment");
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.refused.state, "MCP_PERMISSION_REQUIRED");
  assert.deepStrictEqual(st.writes.map(([, d]) => d), ["some assignment"],
    "the body may already be out, but the submit key must be withheld");
  assert.strictEqual(r.residue_possible, true,
    "a withheld submit leaves the body in the input box — the caller must be told");
});

test("the codex second Enter is gated too, not only the first", async () => {
  // The screens are consumed one per READ, and U364's echo-settle look adds one before the submit
  // check, so the modal is scripted one position later. It is the same scenario: clean when the body
  // goes out, a modal by the time the confirm Enter would.
  const { st, writer } = harness({
    provider: "openai_codex_cli", screen: [CLEAN, CLEAN, CLEAN, TRUST_MODAL],
  });
  const r = await writer.writePrompt("pane-2", "assignment");
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.refused.state, "WORKSPACE_TRUST_REQUIRED");
  assert.deepStrictEqual(st.writes.map(([, d]) => d), ["assignment", "\r"],
    "the confirm Enter is a keystroke like any other and must be refused");
});

test("the clean path is unchanged: body, settle, Enter — and Codex gets its second", async () => {
  const plain = harness();
  assert.strictEqual((await plain.writer.writePrompt("pane-2", "hello")).written, true);
  assert.deepStrictEqual(plain.st.writes, [["pane-2", "hello"], ["pane-2", "\r"]]);

  const codex = harness({ provider: "openai_codex_cli" });
  assert.strictEqual((await codex.writer.writePrompt("pane-1", "hello")).written, true);
  assert.deepStrictEqual(codex.st.writes.map(([, d]) => d), ["hello", "\r", "\r"]);
});

test("19.6: a provider this build has never declared gets ONE Enter, by a stated rule", async () => {
  // The old form was `providerFor(paneId) === "openai_codex_cli"`, so every other provider — the
  // three shipped ones and any future one — got single-Enter behaviour by falling off the end of an
  // `if`. It is now the declared generic trait, which is the same behaviour and a checkable one.
  for (const provider of ["mistral_cli", "claude_code", "grok_build", "google_antigravity"]) {
    const h = harness({ provider });
    assert.strictEqual((await h.writer.writePrompt("pane-2", "hello")).written, true);
    assert.deepStrictEqual(h.st.writes.map(([, d]) => d), ["hello", "\r"],
      `${provider} must submit with exactly one Enter`);
  }
});

test("the pane's own echo of our prompt cannot classify the pane against us", async () => {
  // The body we just wrote is echoed back into the screen we then read. A prompt that quotes a
  // structured failure ("provider authentication is unresolved") would otherwise refuse its own
  // submit key forever. Our bytes are excluded; a REAL modal in the same screen still refuses.
  const prompt = "Worker stalled. Structured failure: not signed in";
  const echoOnly = harness({ screen: [CLEAN, `${CLEAN}${prompt}`] });
  assert.strictEqual((await echoOnly.writer.writePrompt("pane-2", prompt)).written, true,
    "our own echoed bytes are not a modal");

  const alsoModal = harness({ screen: [CLEAN, `${CLEAN}${prompt}\r\n${TRUST_MODAL}`] });
  const r = await alsoModal.writer.writePrompt("pane-2", prompt);
  assert.strictEqual(r.written, false, "a real modal beside our echo still refuses");
  assert.strictEqual(r.refused.state, "WORKSPACE_TRUST_REQUIRED");
});

test("the echo the REAL ConPTY produces is excluded — escapes and wrapping and all (U360)", async () => {
  // What the first version of this got wrong, and what only the runtime could show: the screen is
  // `buffer.snapshot()`, the RAW PTY stream. PSReadLine colours the line it echoes, so escape
  // sequences land INSIDE the echoed body, and the terminal wraps it wherever the column runs out.
  // An exact-substring exclusion finds nothing to remove, the echo classifies against us, and the
  // notice's own submit key is withheld — measured in
  // PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.close_20260810T111123Z.json, leg B.
  const prompt = "Write-Output 'yes, proceed NODE-7'";
  const coloured = "[93mWrite-Output[0m [36m'yes, pro\r\nceed NODE-7'[0m";
  const { writer } = harness({ screen: [CLEAN, `${CLEAN}${coloured}`] });
  assert.strictEqual((await writer.writePrompt("pane-2", prompt)).written, true,
    "a coloured, wrapped echo of our own body is still our own body");

  // …and the exclusion is not a blanket: a real modal arriving in the same screen still refuses.
  const alsoModal = harness({ screen: [CLEAN, `${CLEAN}${coloured}\r\n${TRUST_MODAL}`] });
  const r = await alsoModal.writer.writePrompt("pane-2", prompt);
  assert.strictEqual(r.written, false, "tolerance toward our echo is not tolerance toward a modal");
  assert.strictEqual(r.refused.state, "WORKSPACE_TRUST_REQUIRED");
});

test("withoutOwnEcho removes our body's character sequence, wherever it occurs", () => {
  // Named for what it does, not for what would be nicer: the removal is by PATTERN, not by
  // provenance, so a screen region that is not our echo but matches the sequence goes with it. The
  // last assertion pins that widening rather than asserting it away (review MAJOR-1).
  const { withoutOwnEcho } = require("../control/pane-writer");
  assert.match(withoutOwnEcho("a[31mb[0mc", null), /^abc$/,
    "with no body of ours, the screen is only normalised");
  assert.strictEqual(withoutOwnEcho("xx hello xx", "hello").includes("hello"), false);
  assert.strictEqual(withoutOwnEcho("xx h e l\r\nl o xx", "hello").includes("h e l"), false,
    "whitespace and wrapping between the characters of our own echo");
  const kept = withoutOwnEcho("do you trust the contents of this project", "hello");
  assert.match(kept, /do you trust the contents of this project/,
    "a screen that is not our body survives untouched");
  // …and the bound that is NOT enforced, pinned here so a reader learns it from the suite rather
  // than from a live pane: a body equal to the modal's own words erases those words.
  const erased = withoutOwnEcho(`echo
${TRUST_MODAL}`, "do you trust the contents of this project");
  assert.strictEqual(/do you trust the contents of this project/i.test(erased), false,
    "U360: removal is by pattern, not by provenance — recorded, not claimed otherwise");
});

test("a pane with NO provider is gated by the provider-independent rules (review MAJOR-2)", async () => {
  // Every other test here runs with `provider: "grok_build"`, so a bypass reading
  // `if (provider === null) return null` survived the whole suite when the gate-validator spliced
  // it in. A pane with no provider is the COMMON case: `paneProviderResolver` answers null for any
  // pane that is not the conductor and carries no governed chrome.
  const { st, writer } = harness({ provider: null, screen: TRUST_MODAL });
  const r = await writer.writePrompt("pane-9", "a peer message");
  assert.strictEqual(r.written, false, "an unknown provider is not a reason to stop gating");
  assert.strictEqual(r.refused.state, "WORKSPACE_TRUST_REQUIRED");
  assert.deepStrictEqual(st.writes, [], "not one byte reached a pane showing a trust modal");

  const auth = harness({ provider: null, screen: AUTH_MODAL });
  assert.strictEqual((await auth.writer.writePrompt("pane-9", "x")).refused.state, "AUTH_REQUIRED");
  const mcp = harness({ provider: null, screen: MCP_MODAL });
  assert.strictEqual((await mcp.writer.writePrompt("pane-9", "x")).refused.state,
    "MCP_PERMISSION_REQUIRED");
  // the counter-case, so this test cannot pass by refusing everything:
  const clean = harness({ provider: null });
  assert.strictEqual((await clean.writer.writePrompt("pane-9", "x")).written, true);
});

test("a HALF-rendered echo of our own body does not withhold its own submit key (U364)", async () => {
  // Measured on a real ConPTY, twice, with opposite outcomes: the submit-key read can catch the
  // pane mid-render, and half of our own body is a fragment the exclusion cannot remove. Here the
  // screen shows a truncated echo first and the whole one afterwards; the write must wait for the
  // whole one rather than refuse itself.
  //
  // THE FRAGMENT MUST ITSELF CLASSIFY, and the first version of this fixture cut one character too
  // early — it stopped at "yes, pro", which `classifyProviderScreen`'s `/yes,? proceed/i` does not
  // match, so the half-rendered screen was CLEAN and the scenario this test is named for was never
  // constructed. It passed with the feature deleted; mutation P13 was graded CAUGHT by an unrelated
  // read-index shift in the codex test, and `echoIsWhole` could be replaced by `return true` with
  // the whole desktop suite green. Found by the round-2 gate-validator and spec-auditor together,
  // recorded as U367, and this is the fixture that discriminates.
  const prompt = "Write-Output 'yes, proceed NODE-7'";
  const half = `${CLEAN}Write-Output 'yes, proceed NOD`;   // classifies; not removable as a whole
  const whole = `${CLEAN}${prompt}`;
  const { st, writer } = harness({ screen: [CLEAN, half, half, half, whole] });
  assert.ok(paneWriteRefusal({ provider: "grok_build", screenReadable: true, screen: half }),
    "the fixture is only a fixture if the fragment really classifies — otherwise this test passes "
    + "with the settle wait deleted, which is exactly what U367 was");
  const r = await writer.writePrompt("pane-2", prompt);
  assert.strictEqual(r.written, true, "the settle window must outlast a partial render");
  assert.deepStrictEqual(st.writes.map(([, d]) => d), [prompt, "\r"]);
});

test("the PRE-BODY check may not exclude a body it has not written yet (round-2 MEDIUM)", async () => {
  // `refusalOn(paneId, null)` before the body, `refusalOn(paneId, prompt)` after it. The `null` is
  // load-bearing and was pinned by nothing: passing the prompt there would apply U360's tolerant
  // exclusion to a screen we have not touched, so a modal whose words our body happens to contain
  // would be erased BEFORE the first byte and body + Enter would both go out. The erasure itself is
  // real and already pinned in `withoutOwnEcho` above; this is the call that must not use it.
  const MODAL = "Do you trust the contents of this project?\r\n  1. Proceed\r\n  2. Cancel\r\n";
  const quoting = "Do you trust the contents of this project";
  const { st, writer } = harness({ screen: MODAL });
  const r = await writer.writePrompt("pane-2", quoting);
  assert.strictEqual(r.written, false, "our body is not yet on that screen, so nothing may be removed from it");
  assert.strictEqual(r.refused.state, "WORKSPACE_TRUST_REQUIRED");
  assert.deepStrictEqual(st.writes, [], "not one byte, and above all not the Enter");
});

test("a pane that becomes UNREADABLE while the body is in flight withholds the Enter", async () => {
  // The pre-body half of fail-closed-on-unreadable is pinned (P2, P3, P7). The submit half was not:
  // a live pane whose `buffer.snapshot()` starts throwing between the body and the Enter is a pane
  // whose modal state cannot be ruled out, and the carriage return is the byte that answers one.
  const { st, writer } = harness({ readable: [true, false], screen: CLEAN });
  const r = await writer.writePrompt("pane-2", "a peer message");
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.refused.terminal_state, "PANE_SCREEN_UNREADABLE");
  assert.strictEqual(r.residue_possible, true, "the body is already in the input box");
  assert.deepStrictEqual(st.writes.map(([, d]) => d), ["a peer message"], "the Enter is withheld");
  assert.ok(st.reads < 30, `the wait must stay bounded when the screen never becomes readable; ${st.reads} reads`);
});

test("the echo-settle wait is BOUNDED — a body that never renders still gets a verdict", async () => {
  // A provider that draws our body somewhere this shell cannot read must cost a settle window,
  // never a hang, and the verdict it then gets is the fail-closed one.
  const { st, writer } = harness({ screen: [CLEAN, TRUST_MODAL] });
  const r = await writer.writePrompt("pane-2", "a body that is never echoed");
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.refused.state, "WORKSPACE_TRUST_REQUIRED");
  assert.strictEqual(r.residue_possible, true);
  assert.ok(st.reads < 30, `the wait must be bounded; it read the screen ${st.reads} times`);
});

test("a dead PTY handle is reported as not-written, and is not dressed up as a refusal", async () => {
  const { writer } = harness({ acceptWrites: false });
  const r = await writer.writePrompt("pane-2", "hello");
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.refused, null, "a governed refusal and a dead handle are different facts");
});

test("an unreadable pane is refused before any write is attempted", async () => {
  const { st, writer } = harness({ readable: false });
  const r = await writer.writePrompt("pane-2", "hello");
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.refused.terminal_state, "PANE_SCREEN_UNREADABLE");
  assert.deepStrictEqual(st.writes, []);
});

// ---- notifyNode: the caller the audit named ------------------------------------------------------

test("notifyNode refuses into a modal and says which one, keeping its result shape", async () => {
  const { st, writer } = harness({ screen: MCP_MODAL });
  const r = await writer.notifyNode("node-w", "a peer message arrived");
  assert.deepStrictEqual(
    { node_id: r.node_id, pane_id: r.pane_id, written: r.written },
    { node_id: "node-w", pane_id: "pane-2", written: false });
  assert.match(r.refused, /Sovereign MCP permission/);
  assert.strictEqual(r.provider_terminal_state, "MCP_PERMISSION_REQUIRED");
  assert.deepStrictEqual(st.writes, []);
});

test("notifyNode routes the CONDUCTOR node to the conductor pane, and gates it identically", async () => {
  const modal = harness({ screen: TRUST_MODAL });
  const refused = await modal.writer.notifyNode("node-c", "worker stalled");
  assert.strictEqual(refused.pane_id, "pane-1");
  assert.strictEqual(refused.written, false);
  assert.deepStrictEqual(modal.st.writes, [],
    "the conductor pane is the pane the operator converses in — it is written to blind today (U328)");

  const clean = harness();
  const ok = await clean.writer.notifyNode("node-c", "worker stalled");
  assert.strictEqual(ok.written, true);
  assert.deepStrictEqual(clean.st.writes.map(([p]) => p), ["pane-1", "pane-1"]);
});

test("notifyNode with no live pane is a miss, not a write and not a refusal", async () => {
  const { st, writer } = harness();
  const r = await writer.notifyNode("node-unknown", "anything");
  assert.deepStrictEqual(
    { node_id: r.node_id, pane_id: r.pane_id, written: r.written },
    { node_id: "node-unknown", pane_id: null, written: false });
  assert.deepStrictEqual(st.writes, []);
});

test("a conductor node id is only the conductor pane while the conductor session is RUNNING", async () => {
  // `conductorTarget()` answers null when the session is not running; the node id must then fall
  // through to the worker lookup rather than resolving to a stale pane 1.
  const { st, writer } = harness({ conductor: null, workerPanes: {} });
  const r = await writer.notifyNode("node-c", "anything");
  assert.strictEqual(r.pane_id, null);
  assert.deepStrictEqual(st.writes, []);
});

// ---- the two bindings main.js supplies, kept OUT of main.js so they can be tested ---------------
// `main.js` cannot be required in a test (U338). Every line of the gate that could be got wrong
// therefore lives here, and main.js holds only the two calls that build these.

test("paneScreenFromWindow reads the BOUNDED window, and every unanswerable form is UNREADABLE", () => {
  // U373 residual: the gate's own read. This is `main.js`'s binding — the production
  // `createScreenWindow` over a real RingBuffer, the same object readiness classifies through — so a
  // regression to `buffer.snapshot()` cannot pass by satisfying a hand-rolled double.
  const buffer = new RingBuffer(256);
  // Both screen counts below are TIED to the constant. A literal is how the 24 → 80 raise silently
  // stopped a sibling fixture in this unit from building its own scenario (round-2 spec-auditor,
  // MEDIUM-4) — a fixture whose job is to sit outside the bound must read the bound.
  buffer.push(`${AUTH_MODAL}${CLEAN.repeat(TAIL_LINES + 40)}`);   // well past the line bound
  const window = createScreenWindow({ bufferFor: (id) => (id === "pane-2" ? buffer : null) });
  const read = paneScreenFromWindow(window);
  const screen = read("pane-2");
  assert.strictEqual(screen.readable, true);
  assert.ok(!/not signed in/i.test(screen.text),
    "the gate must read the pane's CURRENT screen, not the scrollback behind it");
  assert.ok(/ready/.test(screen.text), "…and it must actually read what the pane is showing");
  assert.strictEqual(read("pane-9").readable, false, "a pane with no buffer is unreadable");
  // a window that answers `answerable: false` (trimmed region, fabricated position, dead pane) and a
  // window that THROWS both fail closed, with the window's own reason carried where it has one
  const unanswerable = paneScreenFromWindow({
    read: () => ({ answerable: false, text: "", reason: "the bounded window is no longer held exactly" }),
  })("pane-2");
  assert.strictEqual(unanswerable.readable, false);
  assert.match(String(unanswerable.reason), /no longer held exactly/);
  assert.strictEqual(paneScreenFromWindow({ read: () => { throw new Error("gone"); } })("pane-2").readable,
    false, "a window that throws mid-read tells us nothing, and nothing is a refusal");
  assert.strictEqual(paneScreenFromWindow({ read: () => null })("pane-2").readable, false);
  // U396/V1: the gate's window must be the window's OWN, in BOUNDS and not only in object identity.
  // The validator narrowed the gate to `{maxBytes: 512, maxLines: 4}` — the same object, a quarter
  // of the screen — and all 939 tests stayed green, which is the drift the header calls impossible.
  const tall = new RingBuffer(256 * 1024);
  const upBy = TAIL_LINES - 20;
  tall.push(`${TRUST_MODAL}${CLEAN.repeat(upBy)}`);        // a modal `upBy` lines up, inside the bound
  const tallWindow = createScreenWindow({ bufferFor: () => tall });
  assert.strictEqual(paneScreenFromWindow(tallWindow)("pane-2").text, tallWindow.read("pane-2").text,
    "the gate must read exactly what the window reads — no narrower, no wider");
  assert.ok(paneWriteRefusal({ provider: "claude_code", screenReadable: true,
    screen: paneScreenFromWindow(tallWindow)("pane-2").text }),
  `a modal ${upBy} lines up a 30-row pane is still up, and the gate must still see it (U395)`);
  // …and the refusal that comes out of it is the UNREADABLE one, not a clean screen
  assert.strictEqual(
    paneWriteRefusal({ provider: "grok_build", ...read("pane-9"), screenReadable: false })
      .terminal_state, "PANE_SCREEN_UNREADABLE");
});

test("paneProviderResolver prefers the pane's own chrome and falls back to the conductor descriptor", () => {
  const chrome = new Map([["pane-2", { provider: "grok_build" }], ["pane-1", {}]]);
  const resolve = paneProviderResolver({
    chromeFor: (id) => chrome.get(id),
    conductorPaneId: () => "pane-1",
    conductorProvider: () => "claude_code",
  });
  assert.strictEqual(resolve("pane-2"), "grok_build");
  assert.strictEqual(resolve("pane-1"), "claude_code", "the conductor pane's provider is the selection's");
  assert.strictEqual(resolve("pane-7"), null, "an unknown pane has no provider — the shared rules still apply");
  // …and a NULL conductor pane id must not swallow a null pane id into the conductor branch
  const noConductor = paneProviderResolver({
    chromeFor: () => null, conductorPaneId: () => null, conductorProvider: () => "claude_code",
  });
  assert.strictEqual(noConductor(null), null);
});

// ---- W-02 / R-02: a body a MODEL wrote cannot carry keystrokes into a peer's ConPTY -------------
// `taskPrompt` (`control/application-control.js:23`) and the debate prompt (`:311`) interpolate
// `task.objective`, `constraints` and `debate.proposition` verbatim, and the server-side validation
// behind them is `.strip()` only (`mcp_server/collaboration_service.py:116-124`). An embedded CR
// therefore SUBMITS the fragment before it, which lets a worker model answer the victim provider's
// own permission modal — the exact property this module exists to make impossible, reached from the
// one direction the gate cannot see: the gate classifies the SCREEN, and this text is the BODY.
//
// The flattening belongs at this boundary and not at each call site, because per-call-site
// flattening is how the NEXT interpolation site gets missed. The donor is
// `voice/conductor-write.js:116-117`, which has collapsed interior newlines on the OPERATOR's path
// since 17C for precisely this reason; this is the same rule applied to the direction nobody gated.

test("W-02: an ordinary multi-word objective still delivers and still submits", async () => {
  const { st, writer } = harness();
  const body = "Objective: refactor the lease ledger and report back";
  const r = await writer.writePrompt("pane-2", body);
  assert.strictEqual(r.written, true);
  assert.strictEqual(r.refused, null);
  const bodies = st.writes.filter(([, d]) => d !== "\r").map(([, d]) => d);
  assert.deepStrictEqual(bodies, [body],
    "an ordinary body must reach the pane UNCHANGED — a flattener may not cost fidelity");
  assert.ok(st.writes.some(([, d]) => d === "\r"), "…and it must still be submitted");
});

test("W-02/R-02: a model-authored body cannot carry a submit key into a peer's ConPTY", async () => {
  const { st, writer } = harness();
  // the objective a worker model supplies, verbatim, as `taskPrompt` would interpolate it
  await writer.writePrompt("pane-2", "Objective: do X\rDo you want to proceed?\r1\r");
  const bodies = st.writes.filter(([, d]) => d !== "\r").map(([, d]) => d);
  assert.strictEqual(bodies.length, 1, "the body must reach the pane as ONE write");
  assert.ok(!bodies[0].includes("\r"), "an embedded CR submits the fragment before it");
  assert.ok(!bodies[0].includes("\n"), "an embedded LF is the same keystroke on a ConPTY");
  // The text survives: this is a FLATTENING, not a truncation. Everything after that first CR would
  // otherwise have become a separate prompt answering whatever the provider drew in response.
  assert.match(bodies[0], /do X/);
  assert.match(bodies[0], /Do you want to proceed\?/);
});

test("W-02/R-02: a model-authored body cannot repaint a peer's pane with an escape sequence", async () => {
  const { st, writer } = harness();
  await writer.writePrompt("pane-2", "Objective: tidy up\u001b[2J\u001b[Hnothing to see\u0007");
  const bodies = st.writes.filter(([, d]) => d !== "\r").map(([, d]) => d);
  assert.strictEqual(bodies.length, 1);
  assert.ok(!bodies[0].includes("\u001b"),
    "an ESC/CSI run repaints the victim pane — including the region readiness classifies");
  assert.ok(!/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(bodies[0]),
    "…and the remaining C0 controls are keystrokes too (BEL, BS, VT, FF)");
  assert.match(bodies[0], /tidy up/);
  assert.match(bodies[0], /nothing to see/);
});

test("W-02: the SUBMIT key is still a real carriage return — flattening a body may not disarm it", async () => {
  // This module's whole design is that the submit key is written SEPARATELY and gated separately
  // (see "WHY THE SUBMIT KEY IS CHECKED AGAIN"). A flattener that also swallowed the Enter would
  // turn every governed write into a silent no-op, which is the failure mode of the obvious fix.
  const { st, writer } = harness();
  await writer.writePrompt("pane-2", "plain body");
  assert.ok(st.writes.some(([, d]) => d === "\r"),
    "the submit key is not a body and must survive the body's flattening");
});
