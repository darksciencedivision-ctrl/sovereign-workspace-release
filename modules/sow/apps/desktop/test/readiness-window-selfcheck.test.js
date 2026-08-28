"use strict";
/**
 * Phase 19 unit 19.4 — the U329 in-Electron receipt's own falsifiability, for the READINESS RUN.
 *
 * A self-check is evidence only if it can FAIL. `PHASE19_4_READINESS_WINDOW_SELFCHECK*.json` is the
 * D-P16-0 receipt this unit closes on, and the checkpoint recorded that its legs drove the window
 * and the ordering function but never `createWorkerReadiness.run()`. Legs F/G/H now do; this file
 * drives the REAL check function against a simulated runtime and proves those legs go red on the
 * defects they exist to catch — a gate that refuses nothing, a window that reads the whole buffer
 * after all, a pane that never answers, and a write path that never delivers.
 *
 * WHAT THIS FILE CANNOT DO, and it is the honest half: the defect the round-1 reviewers found lived
 * INSIDE `control/worker-readiness.js` (a gate refusal promoted to the worker's provider state), and
 * no ctx double can re-introduce it. `tools/mutation/readiness_signal_mutations.js` owns that class
 * — it splices the defect back into the module and requires `worker-readiness.test.js` to go red —
 * and `readiness-window-wiring.test.js` owns the third question, whether `main.js` hands this check
 * its production bindings rather than lookalikes. Three files, three questions; none of them is
 * sufficient alone and this comment exists so no reader mistakes one for all three.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

// Receipts are written at module load-time paths; keep every run of this file out of the evidence
// directory (the receipt-path override exists for exactly this, 18B review round 1).
const RECEIPT_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "u329-selfcheck-"));
process.env.SHELL_SELFCHECK_RECEIPT_DIR = RECEIPT_DIR;
const {
  runReadinessWindowSelfCheck, RECEIPT_PATH,
} = require("../selfcheck/readiness-window-selfcheck");
const { createScreenWindow, TAIL_LINES, TAIL_BYTES } = require("../control/worker-readiness");
const { createPaneWriter, paneScreenFromWindow } = require("../control/pane-writer");
const { RingBuffer } = require("../../../terminal/session/ring-buffer");

const AUTH_LINE = "you are not signed in. sign in to continue";
const TRUST_LINE = "do you trust the contents of this project";
const TOOL_MENU = "Do you want to proceed?";
/** The fake pane obeys the readiness instruction the way the real pane's script does (U385): it
 *  reads the two fragments out of what was submitted and writes them back JOINED. Nothing here asks
 *  `worker-readiness.js` what it expects — a pane that answered with the module's own string would
 *  agree with it by construction, which is the defect this scheme exists to make impossible. */
const FRAGMENTS_RE = new RegExp(
  "the fragment (SOVEREIGN_READY_[0-9]+_[a-z0-9]+) written immediately before "
  + "the fragment (SOVEREIGN_TAIL_[a-z0-9]+)");

/**
 * A simulated runtime. The pane buffers are REAL `RingBuffer`s and the write gate is the REAL
 * `createPaneWriter`, because those are the two things the legs are asserting about; what is faked
 * is Electron (a window whose `executeJavaScript` answers) and the PTY (a "pane" that prints what
 * its command line says it prints, and answers a submitted readiness token if it is the echo pane).
 *
 * `flaws` re-introduces one defect at a time, which is what makes the assertions below falsifiable
 * rather than self-confirming.
 */
function fakeRuntime(flaws = {}) {
  const buffers = new Map();
  const echoPanes = new Set();
  const pending = new Map();
  const chrome = new Map();
  const records = new Map();
  const identities = new Map();
  const killed = [];
  let seq = 0;

  const bufferFor = (paneId) => buffers.get(paneId) || null;
  const window = createScreenWindow({ bufferFor });
  const readinessWindow = flaws.wholeBufferWindow
    ? {
      mark: window.mark,
      since: window.since,
      // The audited read, restored: everything the pane ever said, presented as answerable.
      read: (paneId) => {
        const buffer = bufferFor(paneId);
        if (!buffer) return { answerable: false, text: "", reason: "no buffer" };
        return { answerable: true, from: 0, at: buffer.totalWritten,
          bytes: buffer.size, text: buffer.snapshot().toString("utf8") };
      },
    }
    : window;

  const manager = {
    registry: {
      has: (paneId) => buffers.has(paneId),
      get: (paneId) => {
        if (!buffers.has(paneId)) throw new Error(`unknown session ${paneId}`);
        return { buffer: buffers.get(paneId) };
      },
    },
    processIdentity: (paneId) => identities.get(paneId) || null,
    write: (paneId, data) => {
      const buffer = buffers.get(paneId);
      if (!buffer || flaws.writePathAlwaysFails) return false;
      if (data === "\r") {
        const line = pending.get(paneId) || "";
        pending.set(paneId, "");
        buffer.push("\r\n");
        const match = FRAGMENTS_RE.exec(line);
        if (echoPanes.has(paneId) && match && !flaws.paneNeverAnswers) {
          if (flaws.paneOnlyRepaints) {
            // U385's mechanism, reproduced without a ConPTY: the pane says nothing of its own and
            // the terminal redraws what we typed. Under the previous scheme this reached READY.
            for (let i = 0; i < 4; i += 1) buffer.push(`${line}\r\n`);
          } else {
            buffer.push(`${match[1]}${match[2]}\r\n`);
            buffer.push("SOVEREIGN_U329_ANSWER\r\n");
          }
        }
        return true;
      }
      pending.set(paneId, (pending.get(paneId) || "") + data);
      buffer.push(data);                               // the pane echoes what was typed
      return true;
    },
  };

  const writer = createPaneWriter({
    // The gate reads the SAME window object the check drives (U373 residual): main.js's binding,
    // so the `wholeBufferWindow` flaw below reaches the gate as well as the state machine.
    paneScreen: paneScreenFromWindow(readinessWindow),
    providerFor: (paneId) => (chrome.get(paneId) || {}).provider || null,
    write: (paneId, data) => manager.write(paneId, data),
    sleep: async () => {},
    pasteSettleMs: () => 0,
    submitConfirmMs: () => 0,
    log: () => {},
    conductorTarget: () => null,
    workerPaneFor: () => null,
  });

  const launcher = {
    record: (paneId) => ({ paneId, state: "unstarted", exitCode: null, nodeId: null,
      chrome: null, readiness: null, ...(records.get(paneId) || {}) }),
    updateRecord: (paneId, patch) => {
      const next = { ...launcher.record(paneId), ...patch, paneId };
      records.set(paneId, next);
      return { ...next };
    },
  };

  const ctx = {
    isSupervised: () => true,
    readinessWindow,
    sessionManager: () => manager,
    workerLauncher: () => launcher,
    paneWriteRefusalFor: (paneId) => (flaws.gateNeverRefuses ? null : writer.refusalFor(paneId)),
    writePanePrompt: async (paneId, prompt) => (await writer.writePrompt(paneId, prompt)).written,
    setWorkerOperationalState: (paneId, state, patch) => {
      const record = launcher.updateRecord(paneId, { operationalState: state, ...patch });
      chrome.set(paneId, { ...(chrome.get(paneId) || record.chrome || {}), node_state: state });
      return record;
    },
    killSession: (id) => killed.push(id),
    log: () => {},
    createPaneWithSession: ({ args }) => {
      const paneId = `pane-${++seq}`;
      const buffer = new RingBuffer(256 * 1024);
      buffers.set(paneId, buffer);
      identities.set(paneId, { pid: 1000 + seq, generation: 1 });
      const command = String((args || []).join(" "));
      buffer.push("SOVEREIGN_U329_PANE_READY\r\n");
      if (command.includes(AUTH_LINE)) {
        buffer.push(`${AUTH_LINE}\r\n`);
        for (let i = 1; i <= 120; i += 1) buffer.push(`SOVEREIGN_U329_OVERWRITE ${i}\r\n`);
      }
      if (command.includes(TRUST_LINE)) buffer.push(`${TRUST_LINE}\r\n`);
      if (command.includes(TOOL_MENU)) buffer.push(`${TOOL_MENU}\r\n> 1. Yes\r\n  2. No\r\n`);
      if (command.includes("Read-Host")) echoPanes.add(paneId);
      return paneId;
    },
    win: {
      webContents: {
        executeJavaScript: async (code) => {
          if (code.includes("hasTerm")) return true;
          const call = /window\.sovereign\.input\((.*)\)$/s.exec(code.trim());
          if (call) {
            const [paneId, data] = JSON.parse(`[${call[1]}]`);
            const buffer = buffers.get(paneId);
            if (buffer) {
              buffer.push(data.replace(/\r$/, "\r\n"));
              const printed = /'([^']+)'/.exec(data);
              if (printed) buffer.push(`${printed[1]}\r\n`);   // the pane runs what was typed
            }
            return true;
          }
          return null;
        },
      },
    },
  };
  return { ctx, killed, buffers };
}

const legsOf = (receipt) => Object.fromEntries(
  Object.entries(receipt.legs).map(([name, leg]) => [name, leg.ok === true]));

test("the healthy runtime passes every leg, including the three readiness-run legs", async () => {
  const { ctx, killed } = fakeRuntime();
  const receipt = await runReadinessWindowSelfCheck(ctx);
  assert.equal(receipt.error, null, `check errored: ${receipt.error}`);
  assert.deepEqual(legsOf(receipt), {
    buried_overlay_is_not_current_state: true,
    current_modal_still_classifies: true,
    exit_code_and_structured_signals_first: true,
    nonce_window_is_exact_or_nothing: true,
    sessionless_pane_unanswerable: true,
    mention_in_scrollback_does_not_withhold_a_healthy_workers_prompt: true,
    clean_pane_is_written_to_and_reaches_ready: true,
    bounded_window_speaks_while_the_write_is_withheld: true,
    unrecognised_permission_menu_is_refused: true,
  });
  assert.equal(receipt.ok, true);
  assert.equal(receipt.live_exchanges, 0);
  // D-LOOP-1: every pane this check opened is killed inside it.
  assert.equal(killed.length, receipt.panes.length);
  assert.deepEqual(receipt.sessions_killed_in_unit, killed);
  assert.ok(fs.existsSync(RECEIPT_PATH), "the check must write its receipt");
  // U373's residual, INVERTED at 19.4-followon and asserted in its new direction: this leg required
  // `ready: false` for two units, and the day the gate's own read was bounded it had to go red — so
  // the receipt could not silently keep describing a stall that no longer happens.
  const legF = receipt.legs.mention_in_scrollback_does_not_withhold_a_healthy_workers_prompt;
  assert.equal(legF.gate_refusal_state, null, "the gate must permit a pane whose SCREEN is clean");
  assert.equal(legF.whole_buffer_verdict_on_this_pane, "AUTH_REQUIRED",
    "the scenario is only meaningful while the whole-buffer read would still refuse");
  assert.equal(legF.ready, true);
  assert.equal(legF.prompts_delivered, 2, "grok owes two readiness turns and both were delivered");
  // Leg H turns on BOTH instruments being bounded: the auth line 120 lines up this pane's scrollback
  // may appear in neither the gate's answer nor the run's verdict.
  const legH = receipt.legs.bounded_window_speaks_while_the_write_is_withheld;
  assert.equal(legH.gate_refusal_state, "WORKSPACE_TRUST_REQUIRED");
  assert.equal(legH.run_state, "WORKSPACE_TRUST_REQUIRED");
  assert.equal(legH.buried_auth_state_reported, false);
  // Leg I is U363's verdict half, and its whole evidential value is the DISAGREEMENT: the
  // provider-state classifier says nothing about this screen and the write is refused anyway.
  const legI = receipt.legs.unrecognised_permission_menu_is_refused;
  assert.equal(legI.classifier_verdict, null);
  assert.equal(legI.gate_refusal_terminal_state, "PANE_AWAITING_OPERATOR_DECISION");
  assert.equal(legI.prompts_delivered, 0);
});

test("a gate that refuses nothing fails the two legs that are about a refusal", async () => {
  // Leg F is NOT one of them, and saying so is the honest half: since 19.4-followon leg F requires
  // the gate to PERMIT, so a gate that permits everything passes it. H and I are what hold the
  // refusal property, which is why the verdict leg was added in the same unit that bounded the read.
  const { ctx } = fakeRuntime({ gateNeverRefuses: true });
  const receipt = await runReadinessWindowSelfCheck(ctx);
  assert.equal(receipt.ok, false);
  assert.equal(receipt.legs.bounded_window_speaks_while_the_write_is_withheld.ok, false);
  assert.equal(receipt.legs.unrecognised_permission_menu_is_refused.ok, false);
});

test("a window that reads the whole buffer after all fails the run legs, not only the window leg",
  async () => {
    const { ctx } = fakeRuntime({ wholeBufferWindow: true });
    const receipt = await runReadinessWindowSelfCheck(ctx);
    assert.equal(receipt.ok, false);
    assert.equal(receipt.legs.buried_overlay_is_not_current_state.ok, false);
    // …and the run legs go red for their own reasons. F: the gate is bound to this same window, so
    // an unbounded read refuses on the scrollback mention and the healthy worker's prompt is
    // withheld again — the audited pin, restored, and this is the leg that names it.
    const legF = receipt.legs.mention_in_scrollback_does_not_withhold_a_healthy_workers_prompt;
    assert.equal(legF.ok, false);
    assert.equal(legF.gate_refusal_state, "AUTH_REQUIRED");
    assert.equal(legF.ready, false);
    // H: the buried auth line becomes the verdict on a pane whose screen is a trust modal.
    const legH = receipt.legs.bounded_window_speaks_while_the_write_is_withheld;
    assert.equal(legH.ok, false);
    assert.equal(legH.buried_auth_state_reported, true);
  });

test("a pane that never answers fails the READY leg (a run cannot reach READY on nothing)",
  async () => {
    const { ctx } = fakeRuntime({ paneNeverAnswers: true });
    const receipt = await runReadinessWindowSelfCheck(ctx);
    assert.equal(receipt.ok, false);
    const leg = receipt.legs.clean_pane_is_written_to_and_reaches_ready;
    assert.equal(leg.ok, false);
    assert.notEqual(leg.run_state, "READY");
  });

test("U385: a pane that only REPAINTS our own prompt fails the READY leg, however many times it "
  + "redraws", async () => {
  // The defect the 19.4 round-3 run found on a real ConPTY, in the check that has to be able to see
  // it. Leg G is this unit's positive control; when the prompt quoted the reply it asked for, a
  // repaint satisfied it and the leg went green on a silent pane. It must now go red.
  const { ctx } = fakeRuntime({ paneOnlyRepaints: true });
  const receipt = await runReadinessWindowSelfCheck(ctx);
  assert.equal(receipt.ok, false);
  const leg = receipt.legs.clean_pane_is_written_to_and_reaches_ready;
  assert.equal(leg.ok, false);
  assert.notEqual(leg.run_state, "READY");
  assert.equal(leg.answer_occurrences_on_the_real_pane, 0,
    "the pane composed nothing; only our own line was redrawn");
  assert.ok(leg.prompt_echo_occurrences_on_the_real_pane >= 2,
    "the scenario did not reproduce: the prompt was not redrawn");
});

test("U385: the leg records that the reply it counts is absent from the prompt that asked for it",
  async () => {
    const { ctx } = fakeRuntime();
    const receipt = await runReadinessWindowSelfCheck(ctx);
    const leg = receipt.legs.clean_pane_is_written_to_and_reaches_ready;
    assert.equal(leg.expected_answer_absent_from_the_prompt, true);
    assert.ok(leg.answer_occurrences_on_the_real_pane >= 1);
  });

test("a write path that delivers nothing fails the READY leg", async () => {
  const { ctx } = fakeRuntime({ writePathAlwaysFails: true });
  const receipt = await runReadinessWindowSelfCheck(ctx);
  assert.equal(receipt.ok, false);
  assert.equal(receipt.legs.clean_pane_is_written_to_and_reaches_ready.ok, false);
});

test("a runtime that exposes no production readiness bindings fails before it drives a run",
  async () => {
    const { ctx } = fakeRuntime();
    delete ctx.setWorkerOperationalState;
    const receipt = await runReadinessWindowSelfCheck(ctx);
    assert.equal(receipt.ok, false);
    assert.match(String(receipt.error), /production readiness bindings/);
    assert.equal(receipt.legs.withheld_write_is_not_a_provider_verdict, undefined);
  });

test("the receipt enumerates EVERY binding the check owns, not just the two easy ones", async () => {
  const { ctx } = fakeRuntime();
  const receipt = await runReadinessWindowSelfCheck(ctx);
  assert.match(receipt.finding, /createWorkerReadiness\.run\(\)/);
  assert.doesNotMatch(receipt.finding, /is not driven in Electron/);
  // The round-2 review found the disclosure undercounting itself: "the two named SIMULATED" while
  // six bindings and a seeded record were the check's. Each name is pinned, so a future binding
  // that quietly joins the list cannot leave the sentence stale.
  const note = receipt.scope_note_readiness_run;
  for (const name of ["mcpState", "operationCount", "operationState", "mcpTimeoutMs",
    "responseDeadlineMs", "now", "sleep", "log", "SEEDED"]) {
    assert.ok(note.includes(name), `the scope note must disclose ${name}`);
  }
  assert.deepEqual(Object.keys(receipt.seeded_launch_record.constant_fields).sort(),
    ["exitCode", "nodeAttested", "operationalState", "readiness", "state", "structuredFailure",
    ],
    "the seeded record is stated verbatim, because those values are assignments and not signals");
  for (const seeded of Object.values(receipt.seeded_launch_record.per_pane)) {
    assert.equal(seeded.supervised, true);
    assert.ok(Number.isInteger(seeded.pid));
    assert.ok(Number.isInteger(seeded.sessionGeneration));
  }
});

// Round 3 found the round-2 repair had reached the scope note and NOT the headline `finding`, which
// still said two bindings were simulated "and everything else is the shipped object" while six and a
// seeded record were the check's. The sentence is now generated from CHECK_OWNED_BINDINGS; this test
// is what stops it being written by hand again.
//
// Round 4 found the generated sentence undercounting ITSELF: the list collapsed `now/sleep/log` into
// one entry, so a sentence whose whole purpose is to count what it counts said six where eight
// bindings were the check's (U393 MINOR-4 — U384's finding at lower amplitude). One entry per
// binding now, and this count is the pin that keeps it that way: a future collapse reddens here.
test("the HEADLINE sentence counts the same bindings the scope note enumerates", async () => {
  const { ctx } = fakeRuntime();
  const receipt = await runReadinessWindowSelfCheck(ctx);
  assert.ok(Array.isArray(receipt.check_owned_bindings));
  assert.equal(receipt.check_owned_bindings.length, 8);
  for (const binding of receipt.check_owned_bindings) {
    assert.ok(!binding.includes("/"),
      `"${binding}" collapses more than one binding into one entry, which is what makes the `
      + "generated count understate itself");
  }
  assert.doesNotMatch(receipt.finding, /everything else is the shipped object/,
    "a universal that the scope note contradicts is the undercount wearing a disclosure's clothes");
  assert.ok(receipt.finding.includes(String(receipt.check_owned_bindings.length)),
    "the headline must state how many bindings are the check's");
  for (const binding of receipt.check_owned_bindings) {
    const name = binding.split(" ")[0];
    assert.ok(receipt.finding.includes(name), `the headline must name ${name}`);
    assert.ok(receipt.scope_note_readiness_run.includes(name),
      `the scope note must name ${name}`);
  }
});

// Round-2 spec-auditor, MINOR-4: the headline's binding count and its `legs F/G/H/I` clause are
// pinned above, but the two clauses that DISCLOSE WHAT THE GATE CANNOT SEE were pinned by nothing —
// the newest and most safety-relevant sentences in the artifact could be deleted with the whole
// suite green. A disclosure nothing grades is a disclosure that lasts until someone tidies it.
test("the headline's OWN LIMITS survive: the residual permission screens and the window's two "
  + "bounds are pinned, in the units the code actually uses", async () => {
  const { ctx } = fakeRuntime();
  const receipt = await runReadinessWindowSelfCheck(ctx);
  assert.match(receipt.finding, /three of the ten permission screens/,
    "U363's residual is the reason 'refuses a modal' is not a universal — it may not go quiet");
  // The bounds are stated as NUMBERS, from the constants, not as identifier names: a receipt is
  // read where the source is not, and `TAIL_LINES` resolves to nothing in a JSON file.
  assert.ok(receipt.finding.includes(`last ${TAIL_LINES} non-blank lines`),
    "the line bound must appear as its value");
  assert.ok(receipt.finding.includes(`last ${TAIL_BYTES} bytes`),
    "the byte bound must appear as its value, because it is the half that bites first");
  assert.match(receipt.finding, /U395/, "and it must name the row that owns the gap");
  assert.doesNotMatch(receipt.finding, /TAIL_LINES|TAIL_BYTES/,
    "an unresolved identifier in a shipped receipt discloses nothing to its reader");
});

// MAJOR-2: nodeId and chrome were seeded and undisclosed, and chrome.provider/model_slug are what
// every structured failure these legs produce reports as `provider` and `model`.
test("the receipt publishes the launch record of every pane a RUN is driven on, AS SEEDED, chrome "
  + "and nodeId included — and says which panes have none",
async () => {
  const { ctx } = fakeRuntime();
  const receipt = await runReadinessWindowSelfCheck(ctx);
  // The round-1 validator of 19.4-followon: the generated sentence said "each pane's launch record
  // is SEEDED" while `panes` is A/B/G/H/I and `per_pane` is F/G/H/I — pane B has no record at all.
  // The error was in the safe direction (claiming MORE simulation than there is) and it is still a
  // receipt sentence that does not match the receipt (U394 MINOR-4, closed here).
  const runLegs = Object.keys(receipt.seeded_launch_record.per_pane).sort();
  assert.ok(receipt.finding.includes("legs F/G/H/I"),
    "the headline must name which panes are seeded, not imply all of them are");
  assert.ok(receipt.finding.includes("panes A and B"),
    "…and which are not");
  assert.deepEqual(runLegs, ["F", "G", "H", "I"]);
  for (const leg of runLegs) {
    const seeded = receipt.seeded_launch_record.per_pane[leg];
    assert.ok(seeded.nodeId, `leg ${leg} must disclose the seeded nodeId`);
    assert.ok(seeded.chrome && seeded.chrome.provider && seeded.chrome.model_slug,
      `leg ${leg} must disclose the seeded chrome the structured failure reports as provider/model`);
    assert.equal(seeded.state, "running");
  }
  // The disclosure is the record, not a copy of it that can drift.
  assert.equal(receipt.seeded_launch_record.per_pane.F.chrome.provider, "grok_build");
  assert.equal(receipt.seeded_launch_record.per_pane.G.chrome.provider, "claude_code");
  // …and the panes the headline says are NOT seeded really are not.
  assert.deepEqual(receipt.panes.map((p) => p.pane), ["A", "B", "G", "H", "I"]);
  assert.equal(receipt.seeded_launch_record.per_pane.B, undefined);
});
