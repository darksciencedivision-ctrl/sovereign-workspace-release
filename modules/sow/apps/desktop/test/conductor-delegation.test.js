"use strict";
/**
 * EPC-03 L5-3/L5-4 — the conductor injects a prompt and reads the answer back.
 *
 * The gap this closes was measurable: the existing `assign_task` path writes a task into a pane
 * and waits for that worker to call `publish_candidate` over MCP. A local pane running
 * `ollama run llama3.2:3b` is a bare REPL with no Sovereign tools, so a local worker was
 * assignable and could never complete an assignment — completion was defined as a call it cannot
 * make.
 *
 * Run against a REAL `RingBuffer` through the REAL screen window, because what is being tested is
 * a composition: mark the stream, write through the gate, wait for quiet, read back bounded and
 * redacted. Stubbing any part of it would test the model of it.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { RingBuffer } = require("../../../terminal/session/ring-buffer");
const { createScreenWindow } = require("../control/worker-readiness");
const {
  delegateToPane, delegationPrompt, DELEGATION_SCHEMA,
} = require("../control/conductor-delegation");

const TASK = { task_id: "t-1", objective: "Name three risks in the release plan",
  expected_output: "three bullets" };

/** A pane that answers `reply` a moment after it is written to. */
function fakePane({ reply = "1. one\n2. two\n3. three\n", accept = true,
  refusal = null, replyAfter = 1 } = {}) {
  const ring = new RingBuffer(256 * 1024);
  ring.push(Buffer.from("$ ollama run llama3.2:3b\n>>> ", "utf8"));
  const window = createScreenWindow({ bufferFor: () => ring });
  let clock = 0;
  let writes = 0;
  let ticks = 0;
  return {
    ring,
    writes: () => writes,
    io: {
      window,
      now: () => clock,
      sleep: async (ms) => {
        clock += ms;
        ticks += 1;
        if (accept && replyAfter !== null && ticks === replyAfter) ring.push(Buffer.from(reply, "utf8"));
      },
      writePrompt: async (_paneId, body) => {
        if (!accept) return { written: false, refused: refusal, residue_possible: false };
        writes += 1;
        ring.push(Buffer.from(`${body}\n`, "utf8"));
        return { written: true, refused: null, residue_possible: false };
      },
      log: () => {},
    },
  };
}

test("a delegated task is written to the pane and its answer read back", async () => {
  const pane = fakePane();
  const result = await delegateToPane(pane.io,
    { paneId: "pane-1", nodeId: "worker-pane-1", task: TASK, quietMs: 2000, pollMs: 1000 });
  assert.equal(result.schema, DELEGATION_SCHEMA);
  assert.equal(result.delivered, true);
  assert.equal(result.answered, true);
  assert.equal(pane.writes(), 1);
  assert.match(result.candidate.content, /1\. one/);
});

test("the prompt does not tell a local REPL to call tools it does not have", () => {
  // `taskPrompt` instructs the worker to use publish_progress / send_message / publish_candidate.
  // A model told to call a missing tool NARRATES calling it, which is worse than either outcome.
  const prompt = delegationPrompt(TASK);
  assert.ok(!/publish_candidate|publish_progress|send_message/.test(prompt), prompt);
  assert.match(prompt, /Answer directly and completely in this terminal/);
  assert.match(prompt, /Name three risks/);
});

test("the read is bounded to what the pane emitted AFTER the prompt", async () => {
  // An earlier run's answer sitting in the scrollback must not satisfy this turn. That is the
  // exact defect `RingBuffer.sliceFrom` exists to close, and the mark is how this path inherits it.
  const pane = fakePane({ reply: "FRESH ANSWER\n" });
  pane.ring.push(Buffer.from("STALE ANSWER FROM AN EARLIER RUN\n", "utf8"));
  const result = await delegateToPane(pane.io,
    { paneId: "pane-1", nodeId: "w-1", task: TASK, quietMs: 2000, pollMs: 1000 });
  assert.match(result.candidate.content, /FRESH ANSWER/);
  assert.ok(!result.candidate.content.includes("STALE ANSWER"), result.candidate.content);
});

test("a pane with no readable stream position is refused, not read unbounded", async () => {
  const io = { window: createScreenWindow({ bufferFor: () => null }), sleep: async () => {},
    writePrompt: async () => { throw new Error("should never be reached"); } };
  const result = await delegateToPane(io, { paneId: "pane-1", nodeId: "w-1", task: TASK });
  assert.equal(result.delivered, false);
  assert.match(result.reason, /no readable stream position/);
});

test("a write the GATE refused is surfaced, never retried around", async () => {
  // The U328 modal gate refuses a write when the pane is showing something a keystroke would
  // answer. A conductor's prompt is not exempt from a gate the operator's own voice is subject to.
  const pane = fakePane({ accept: false,
    refusal: { reason: "pane is showing a numbered permission selection", terminal_state: null } });
  const result = await delegateToPane(pane.io, { paneId: "pane-1", nodeId: "w-1", task: TASK });
  assert.equal(result.delivered, false);
  assert.equal(pane.writes(), 0);
  assert.match(result.refused.reason, /permission selection/);
  assert.match(result.reason, /gate refused/);
});

test("a pane that never answers times out honestly instead of holding the turn open", async () => {
  const pane = fakePane({ replyAfter: null });
  const result = await delegateToPane(pane.io,
    { paneId: "pane-1", nodeId: "w-1", task: TASK, timeoutMs: 5000, pollMs: 1000, quietMs: 2000 });
  assert.equal(result.delivered, true);
  assert.equal(result.answered, false);
  assert.equal(result.candidate, null);
  assert.match(result.reason, /no readable output within the delegation window/);
});

test("it waits for the pane to go QUIET before calling the output an answer", async () => {
  // A local model streams tokens. "Output appeared" is not "the model is done", and reading on the
  // first byte would publish half a sentence as a candidate.
  const ring = new RingBuffer(256 * 1024);
  ring.push(Buffer.from(">>> ", "utf8"));
  const window = createScreenWindow({ bufferFor: () => ring });
  let clock = 0;
  let ticks = 0;
  const io = {
    window, now: () => clock,
    sleep: async (ms) => {
      clock += ms;
      ticks += 1;
      // Stream four chunks, one per poll, then stop.
      if (ticks >= 2 && ticks <= 5) ring.push(Buffer.from(`chunk-${ticks} `, "utf8"));
    },
    writePrompt: async () => ({ written: true, refused: null, residue_possible: false }),
  };
  const result = await delegateToPane(io,
    { paneId: "pane-1", nodeId: "w-1", task: TASK, timeoutMs: 60_000, pollMs: 1000, quietMs: 3000 });
  assert.equal(result.answered, true);
  // Every chunk is present: the read did not fire on the first one.
  for (const n of [2, 3, 4, 5]) {
    assert.match(result.candidate.content, new RegExp(`chunk-${n}`));
  }
});

test("the pane's echo of OUR OWN prompt is not read as its answer", async () => {
  // A real defect, found by the timeout test above rather than by inspection: the pane echoes what
  // we wrote, so a pane that never answered still looked answered, and the delegation published
  // its own prompt back as the worker's candidate. `pane-writer.withoutOwnEcho` already solves
  // this for the write gate and is reused rather than reimplemented — a second echo exclusion
  // would drift, and then the gate and the reader would disagree about what the pane said.
  const pane = fakePane({ reply: "ACTUAL ANSWER\n" });
  const result = await delegateToPane(pane.io,
    { paneId: "pane-1", nodeId: "w-1", task: TASK, quietMs: 2000, pollMs: 1000 });
  assert.match(result.candidate.content, /ACTUAL ANSWER/);
  assert.ok(!result.candidate.content.includes("Name three risks in the release plan"),
    `the prompt echo survived into the candidate:\n${result.candidate.content}`);
  assert.ok(!result.candidate.content.includes("SOVEREIGN TASK t-1"),
    result.candidate.content);
});

test("a candidate the shell READ is never dressed as one the node ASSERTED", async () => {
  // The honesty line of L5-4. A reviewer must be able to tell a node's own claim from a screen
  // read, because only the first is the node speaking.
  const pane = fakePane();
  const result = await delegateToPane(pane.io,
    { paneId: "pane-1", nodeId: "w-1", task: TASK, quietMs: 2000, pollMs: 1000 });
  assert.equal(result.candidate.self_published, false);
  assert.equal(result.candidate.source, "observed_pane_output");
  assert.match(result.candidate.note, /Weaker evidence than a node's own publication/);
});

test("a secret in the answer is redacted before it becomes a candidate", async () => {
  const secret = "sk-ant-api03-BBBBBBBBBBBBBBBBBBBBBBBBBBBB";
  const pane = fakePane({ reply: `here is the key: ${secret}\n` });
  const result = await delegateToPane(pane.io,
    { paneId: "pane-1", nodeId: "w-1", task: TASK, quietMs: 2000, pollMs: 1000 });
  assert.ok(!result.candidate.content.includes(secret), result.candidate.content);
  assert.ok(result.candidate.redactions >= 1);
});

test("a delegation never throws — a fault becomes a record, not an exception", async () => {
  const io = {
    window: createScreenWindow({ bufferFor: () => new RingBuffer(1024) }),
    sleep: async () => {},
    writePrompt: async () => { throw new Error("PTY handle is gone"); },
  };
  const result = await delegateToPane(io, { paneId: "pane-1", nodeId: "w-1", task: TASK });
  assert.equal(result.delivered, false);
  assert.match(result.reason, /PTY handle is gone/);
});

test("a missing pane or task produces a record rather than a crash", async () => {
  for (const args of [{}, { paneId: "pane-1" }, { task: TASK }]) {
    const result = await delegateToPane({ sleep: async () => {} }, args);
    assert.equal(result.delivered, false);
    assert.equal(result.schema, DELEGATION_SCHEMA);
  }
});
