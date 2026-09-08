"use strict";
/**
 * SW-JOURNAL-002-A3 items 3+4 (F-46a/b/c): terminal chrome is trimmed at capture, every
 * removal is counted and declared, and a content-free observation is recorded honestly
 * (append-only history) but stays out of the conductor's view.
 *
 * Measured defect: the session projection stored 1,944 braille spinner characters and 103
 * copies of the REPL's idle prompt line — 52% of all stored answer bytes were the terminal
 * drawing itself, and 5 observations were nothing but chrome, rendered to the conductor as
 * answers. The trim rules match ONLY:
 *   (i)   runs of two or more of the ten measured "dots" spinner frames (adjacent or
 *         CR/space/tab-separated; a newline ends a run; a LONE frame is model text);
 *   (ii)  an echoed prefix matching EXACTLY the text this application wrote to that pane;
 *   (iii) the exact idle prompt line, whole, in leading runs at the start of a display line
 *         (behind at most carriage returns, which redraw the same line).
 * Everything else — including model text containing ">>>" or a lone braille frame, and a
 * near-miss echo — stays untouched. Over-keeping is the safe failure here; the counts make
 * every removal visible either way.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const Module = require("node:module");
const J = require("../control/workspace-journal");
const V = require("../control/conductor-view");
const D = require("../control/conductor-delegation");

const IDLE = J.IDLE_PROMPT_LINE;
const F = J.SPINNER_FRAMES; // "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
const trim = (text, writtenPrompt) => J.trimPaneChrome(text, { writtenPrompt });
const profile = (n) => ({ available: true, num_ctx: n, reserved_prompt_tokens: 0,
  reserved_response_tokens: 0, chars_per_token: 1, total_max_chars: n, max_observation_chars: n });

function setup(t, api = J) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "sow-chrome-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "install"));
  const rows = [];
  const store = { append: async (e) => rows.push(structuredClone(e)),
    entries: async ({ sessionId, limit }) =>
      (sessionId ? rows.filter(e => e.session_id === sessionId) : rows.toReversed()).slice(0, limit) };
  const journal = api.createWorkspaceJournal({ store, stateRoot: path.join(root, "state"),
    installRoot: path.join(root, "install"), sessionId: "session-test",
    now: () => "2026-09-06T00:00:00Z" });
  return { root, rows, store, journal };
}
const entry = (extra = {}) => ({ node_id: "node-2", pane_id: "pane-2", model: "test-model",
  objective: "compare facts", task_id: "task-1", status: "answered", prompt: "question",
  answer: "answer", self_published: false, source: J.SOURCE, ...extra });

// ---------------------------------------------------------------- trimPaneChrome rules

test("F-46b: spinner runs are removed and counted; a lone frame is model text and stays", () => {
  const run = trim(F[0] + F[1] + F[2] + F[3]);
  assert.equal(run.text, "");
  assert.equal(run.spinner_chars, 4);
  assert.equal(run.removed_chars, 4);
  assert.deepEqual(run.chrome_kinds, ["spinner"]);
  const crSeparated = trim(F[0] + "\r" + F[1] + "\r" + F[2] + "\r");
  assert.equal(crSeparated.text, "");
  assert.equal(crSeparated.spinner_chars, 3, "CR between frames is a redraw, not content");
  const lone = trim("a " + F[0] + " b");
  assert.equal(lone.text, "a " + F[0] + " b", "a single frame stays");
  assert.equal(lone.spinner_chars, 0);
  const inWords = trim("The character " + F[0] + " is braille");
  assert.equal(inWords.text, "The character " + F[0] + " is braille");
  const glued = trim(F[0] + "REAL");
  assert.equal(glued.text, F[0] + "REAL", "one frame glued to text is not a run");
  assert.equal(glued.spinner_chars, 0);
  const empty = trim("");
  assert.deepEqual({ ...empty, chrome_kinds: [] }, { text: "", spinner_chars: 0, idle_lines: 0,
    echoed_prefix_chars: 0, removed_chars: 0, chrome_kinds: [] });
});

test("F-46b: a newline ends a spinner run — trimming never joins two lines", () => {
  const t = trim(F[0] + "\n" + F[1]);
  assert.equal(t.text, F[0] + "\n" + F[1]);
  assert.equal(t.spinner_chars, 0, "LF-separated frames are two lines of content, not a run");
  assert.equal(trim("one\ntwo").text, "one\ntwo");
});

test("F-46c: the idle prompt line is removed only whole, exact, and leading on its line", () => {
  assert.equal(trim(IDLE).text, "");
  assert.equal(trim(IDLE).idle_lines, 1);
  const stacked = trim(IDLE + "\n" + IDLE + "\nREAL");
  assert.equal(stacked.text, "\n\nREAL");
  assert.equal(stacked.idle_lines, 2);
  const concatenated = trim(IDLE + IDLE); // the measured repaint shape: no newline between
  assert.equal(concatenated.text, "");
  assert.equal(concatenated.idle_lines, 2);
  const crRepaint = trim("\r" + IDLE); // CR redraw of the same line
  assert.equal(crRepaint.text, "");
  assert.equal(crRepaint.idle_lines, 1);
  const midLine = trim("see " + IDLE + " inline");
  assert.equal(midLine.text, "see " + IDLE + " inline", "mid-line text is the model's, not chrome");
  assert.equal(midLine.idle_lines, 0);
  const indented = trim("  " + IDLE);
  assert.equal(indented.text, "  " + IDLE, "spaces are content; only CRs precede a repaint");
  assert.equal(indented.idle_lines, 0);
  const nearMiss = trim(">>> Send messages (/? for help)");
  assert.equal(nearMiss.text, ">>> Send messages (/? for help)", "an inexact string is not the prompt line");
  assert.equal(nearMiss.idle_lines, 0);
});

test("F-46c: an echoed prefix is removed only on an exact match to what we wrote", () => {
  const exact = trim("PROMPT-BODY\r" + IDLE + "\nANSWER", "PROMPT-BODY");
  assert.equal(exact.text, "\nANSWER");
  assert.equal(exact.echoed_prefix_chars, "PROMPT-BODY".length);
  assert.equal(exact.idle_lines, 1);
  assert.deepEqual(exact.chrome_kinds, ["idle_prompt", "echoed_prompt"]);
  // A capture that begins with the written prompt followed by MORE pane output still removes
  // exactly the written part: startsWith matched the authored text itself, character for
  // character, and what follows it is the pane's own.
  const followed = trim("PROMPT-BODY?\nANSWER", "PROMPT-BODY");
  assert.equal(followed.text, "?\nANSWER");
  assert.equal(followed.echoed_prefix_chars, "PROMPT-BODY".length);
  // A capture that differs INSIDE the prompt's extent is a near-miss: nothing is removed.
  const nearMiss = trim("PROMPT-BODX\nANSWER", "PROMPT-BODY");
  assert.equal(nearMiss.text, "PROMPT-BODX\nANSWER", "near-miss echo stays: exact or nothing");
  assert.equal(nearMiss.echoed_prefix_chars, 0);
  const absent = trim("OTHER\nANSWER", "PROMPT-BODY");
  assert.equal(absent.text, "OTHER\nANSWER");
  assert.equal(absent.echoed_prefix_chars, 0);
  // The measured ollama shape: the REPL wraps long input and inserts "... " continuations.
  // A wrapped echo is NOT an exact prefix; it honestly stays rather than being guessed at.
  const written = "word ".repeat(20).trim();
  const wrapped = written.slice(0, 20) + "\n... " + written.slice(20) + "\nANSWER";
  const w = trim(wrapped, written);
  assert.equal(w.text, wrapped);
  assert.equal(w.echoed_prefix_chars, 0);
});

test("F-46b: the combined shape from the measured capture reduces to just the content", () => {
  const body = "SOVEREIGN TASK t-1 Objective: report the sum Answer directly.";
  const raw = body + "\r" + F[0] + "\r" + F[1] + "\r" + F[2] + "\r" + IDLE + "\n" + IDLE
    + "\nREAL-CONTENT";
  const t = trim(raw, body);
  assert.equal(t.text, "\n\nREAL-CONTENT");
  assert.equal(t.spinner_chars, 3);
  assert.equal(t.idle_lines, 2);
  assert.equal(t.echoed_prefix_chars, body.length);
  assert.equal(t.removed_chars, raw.length - t.text.length, "the count is exact");
  assert.deepEqual(t.chrome_kinds, ["spinner", "idle_prompt", "echoed_prompt"]);
});

// ---------------------------------------------------------------- observe() at capture

test("F-46a: observe() marks a chrome-only pane content-free, recorded and declared", async (t) => {
  const x = setup(t);
  const chromeOnly = F[0] + "\r" + F[1] + "\r" + F[2] + "\r" + IDLE + "\n" + IDLE;
  const rows = await x.journal.observe(
    { read: () => ({ answerable: true, text: chromeOnly, at: 1 }) },
    [{ pane_id: "pane-2", node_id: "node-2", model: "m" }], 2000);
  const e = rows[0].entry;
  assert.equal(e.status, "observed", "it is still an observation — append-only history");
  assert.equal(e.content_free, true);
  assert.equal(e.answer.trim(), "");
  assert.equal(e.answer, "\n",
    "the newline between two removed idle lines is a line boundary; trimming never joins lines");
  assert.equal(e.chrome_removed, chromeOnly.length - e.answer.length, "every removal is counted");
  assert.deepEqual(e.chrome_kinds, ["idle_prompt", "spinner"]);
  assert.match(e.reason, /content-free observation: only terminal chrome was captured/);
  assert.match(e.reason, /spinner_chars=3/);
  assert.match(e.reason, /idle_lines=2/);
  assert.equal(e.self_published, false);
  assert.equal(e.source, J.SOURCE);
  assert.equal(e.redactions, 0);
  // The stored row carries the same declarations.
  assert.equal(x.rows[0].content_free, true);
  assert.equal(x.rows[0].chrome_removed, chromeOnly.length - e.answer.length);
});

test("F-46a: a content-free observation stays out of the conductor's view; real rows stay in", async (t) => {
  const x = setup(t);
  const chromeOnly = F[0] + F[1] + "\r" + IDLE;
  await x.journal.observe({ read: (paneId) => paneId === "pane-2"
      ? { answerable: true, text: chromeOnly, at: 1 }
      : { answerable: true, text: "REAL WORKER ANSWER", at: 1 } },
    [{ pane_id: "pane-2", node_id: "node-2", model: "m" },
      { pane_id: "pane-3", node_id: "node-3", model: "m" }], 2000);
  const entries = await x.journal.entries();
  const contentFree = entries.find(e => e.pane_id === "pane-2");
  const real = entries.find(e => e.pane_id === "pane-3");
  assert.equal(contentFree.content_free, true);
  const v = V.composeView("what did they all say", entries, profile(8000));
  assert.ok(!v.entry_ids.includes(contentFree.event_id));
  assert.ok(v.entry_ids.includes(real.event_id));
  assert.match(v.view, /REAL WORKER ANSWER/);
  assert.doesNotMatch(v.view, new RegExp(F[0]), "no spinner frame reaches the conductor");
  assert.equal(v.state, "attached");
});

test("F-46a: a pane with content is never marked content-free; its chrome is still declared", async (t) => {
  const x = setup(t);
  await x.journal.observe({ read: () => ({ answerable: true,
      text: F[0] + F[1] + F[2] + "REAL ANSWER 42", at: 1 }) },
    [{ pane_id: "pane-2", node_id: "node-2", model: "m" }], 2000);
  const e = x.rows[0];
  assert.equal(e.content_free, undefined, "the mark exists only when the content does not");
  assert.equal(e.answer, "REAL ANSWER 42");
  assert.equal(e.chrome_removed, 3);
  assert.deepEqual(e.chrome_kinds, ["spinner"]);
  assert.equal(e.reason, "");
});

test("F-46c: observe() matches the echoed prefix against the prompt this application wrote", async (t) => {
  const x = setup(t);
  await x.journal.record(entry({ node_id: "conductor", pane_id: "pane-2", model: "m",
    status: "prompt_written", prompt: "EXACT-WRITTEN-BODY", answer: "" }));
  const rawText = "EXACT-WRITTEN-BODY\r" + F[0] + F[1] + "\r" + IDLE + "\nTHE-WORKER-ANSWER";
  await x.journal.observe({ read: () => ({ answerable: true, text: rawText, at: 1 }) },
    [{ pane_id: "pane-2", node_id: "node-2", model: "m" }], 2000);
  const e = x.rows[1];
  assert.equal(e.answer, "\nTHE-WORKER-ANSWER");
  assert.equal(e.content_free, undefined);
  assert.deepEqual(e.chrome_kinds, ["echoed_prompt", "idle_prompt", "spinner"]);
  assert.equal(e.chrome_removed, rawText.length - e.answer.length, "the count is exact");

  // A near-miss capture is NOT the prompt we wrote: it stays, and nothing is declared.
  const y = setup(t);
  await y.journal.record(entry({ node_id: "conductor", pane_id: "pane-2", model: "m",
    status: "prompt_written", prompt: "AAA-BODY", answer: "" }));
  await y.journal.observe({ read: () => ({ answerable: true,
      text: "AAA-BODX\r" + F[0] + F[1] + "\nREST-OF-ANSWER", at: 1 }) },
    [{ pane_id: "pane-2", node_id: "node-2", model: "m" }], 2000);
  const n = y.rows[1];
  assert.ok(n.answer.startsWith("AAA-BODX"), "the near-miss echo honestly stays");
  assert.ok(!n.chrome_kinds.includes("echoed_prompt"));
});

test("F-46a: an unreadable pane is never trimmed and never marked content-free", async (t) => {
  const x = setup(t);
  await x.journal.observe({ read: () => ({ answerable: false, reason: "pane unavailable" }) },
    [{ pane_id: "pane-3", node_id: "node-3", model: "m" }], 300);
  const e = x.rows[0];
  assert.equal(e.status, "unreadable");
  assert.equal(e.content_free, undefined);
  assert.equal(e.chrome_removed, undefined);
  assert.doesNotMatch(e.reason, /content-free/);
  assert.match(e.reason, /pane unavailable/);
});

test("F-46a: content-free marks project into the markdown and keep every older byte stable", async (t) => {
  const x = setup(t);
  const plain = J.prepareEntry(entry(), "session-test", () => "2026-09-06T00:00:00Z");
  // A pre-A3 entry renders with NO trace of the new fields — old projections stay identical.
  assert.doesNotMatch(J.renderSession([plain], "session-test"), /content_free|chrome_removed|chrome_kinds/);
  await x.journal.observe({ read: () => ({ answerable: true, text: F[0] + F[1] + IDLE, at: 1 }) },
    [{ pane_id: "pane-2", node_id: "node-2", model: "m" }], 2000);
  const { file } = await x.journal.project();
  const md = fs.readFileSync(file, "utf8");
  assert.match(md, /content_free: true/);
  assert.match(md, /chrome_removed: \d+/);
  assert.match(md, /chrome_kinds/);
  assert.match(md, /self_published: false/);
  const before = fs.readFileSync(file);
  await x.journal.project();
  assert.deepEqual(fs.readFileSync(file), before, "repeat rendering is byte-stable");
});

// ---------------------------------------------------------------- delegation path

function delegationIO(x, paneTextFor) {
  let clock = 0, writtenBody = null;
  const io = { journal: x.journal, now: () => clock, sleep: async (ms) => { clock += ms; },
    log: () => {},
    window: { mark: () => 0, read: () => ({ answerable: true, text: paneTextFor(writtenBody), at: 1 }) },
    writePrompt: async (paneId, body) => { writtenBody = body; return { written: true }; } };
  return { io, writtenBody: () => writtenBody };
}
const delegationOptions = { paneId: "pane-2", nodeId: "node-2", model: "test-model",
  task: { task_id: "t-chrome", objective: "report the sum" },
  timeoutMs: 200, pollMs: 1, quietMs: 2, maxChars: 4000 };

test("F-46b/c: the delegation answer strips chrome and the entry declares every removal", async (t) => {
  const x = setup(t);
  const paneText = (body) => body + "\r" + F[0] + "\r" + F[1] + "\r" + F[2] + "\r" + IDLE
    + "\n" + IDLE + "\nFINAL-WORKER-ANSWER 42";
  const { io } = delegationIO(x, paneText);
  const result = await D.delegateToPane(io, delegationOptions);
  assert.equal(result.answered, true);
  assert.equal(result.candidate.content, "FINAL-WORKER-ANSWER 42");
  assert.equal(result.candidate.self_published, false);
  assert.equal(result.candidate.source, "observed_pane_output");
  assert.equal(result.chrome.spinner_chars, 3);
  assert.equal(result.chrome.idle_lines, 2);
  assert.ok(result.chrome.echoed_prefix_chars > 0, "the exact echo of our own prompt is declared");
  const e = x.rows.find(r => r.status === "answered");
  assert.equal(e.answer, "FINAL-WORKER-ANSWER 42", "what is stored as the answer IS the answer");
  assert.equal(e.chrome_removed, result.chrome.removed_chars);
  assert.deepEqual(e.chrome_kinds, ["echoed_prompt", "idle_prompt", "spinner"]);
  assert.equal(e.self_published, false);
  assert.equal(e.source, J.SOURCE);
});

test("F-46b: a spinner-only pane is NOT answered — a braille blob is not read as an answer", async (t) => {
  const x = setup(t);
  const paneText = (body) => body + "\r" + F.split("").map(c => c + "\r").join("") + IDLE + "\n" + IDLE;
  const { io } = delegationIO(x, paneText);
  const result = await D.delegateToPane(io, delegationOptions);
  assert.equal(result.answered, false);
  assert.equal(result.candidate, null);
  assert.equal(result.reason, "the pane produced no readable output within the delegation window");
  const e = x.rows.find(r => r.status === "unreadable" && r.answer !== undefined
    && !r.prompt.includes("SOVEREIGN"));
  assert.equal(e.answer.trim(), "");
  for (const frame of F) assert.ok(!e.answer.includes(frame), "no spinner frame is stored");
  assert.ok(e.chrome_kinds.includes("spinner"));
  assert.ok(e.chrome_removed > 0);
});

test("F-46c: model text that merely resembles chrome is never trimmed in the answer path", async (t) => {
  const x = setup(t);
  const paneText = (body) => body + "\nThe braille dot " + F[0] + " alone, and >>> marks, are model text.\nSecond line stays.";
  const { io } = delegationIO(x, paneText);
  const result = await D.delegateToPane(io, delegationOptions);
  assert.equal(result.answered, true);
  assert.equal(result.candidate.content,
    "The braille dot " + F[0] + " alone, and >>> marks, are model text.\nSecond line stays.");
  assert.equal(result.chrome.spinner_chars, 0);
  assert.equal(result.chrome.idle_lines, 0);
  assert.deepEqual(result.chrome.chrome_kinds, ["echoed_prompt"],
    "only the exact echo of our own prompt was removed");
});

// ---------------------------------------------------------------- mutation controls

test("F-46a mutation control: restoring raw capture un-marks the content-free observation", async (t) => {
  const filename = require.resolve("../control/workspace-journal");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = "? trimPaneChrome(text, { writtenPrompt: authored })";
  assert.ok(source.includes(anchor), "the capture-time trim anchor must exist");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor,
    "? { text, spinner_chars: 0, idle_lines: 0, echoed_prefix_chars: 0, removed_chars: 0, chrome_kinds: [] }"),
    filename);
  const check = async (api) => {
    const x = setup(t, api);
    await x.journal.observe({ read: () => ({ answerable: true, text: F[0] + F[1] + IDLE, at: 1 }) },
      [{ pane_id: "pane-2", node_id: "node-2", model: "m" }], 2000);
    assert.equal(x.rows[0].content_free, true, "chrome-only capture must be marked content-free");
  };
  await check(J);
  await assert.rejects(() => check(mutant.exports),
    "without the capture-time trim the content-free mark disappears — the tests above are decisive");
  assert.equal(fs.readFileSync(filename, "utf8"), source);
});

test("F-46b mutation control: skipping the trim in the answer path reads the spinner as an answer", async (t) => {
  const filename = require.resolve("../control/conductor-delegation");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = "    const chrome = trimPaneChrome(observation.text, { writtenPrompt: body });";
  assert.ok(source.includes(anchor), "the answer-path trim anchor must exist");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor,
    "    const chrome = { text: observation.text, spinner_chars: 0, idle_lines: 0, echoed_prefix_chars: 0, removed_chars: 0, chrome_kinds: [] };"),
    filename);
  const check = async (api) => {
    const x = setup(t);
    const paneText = (body) => body + "\r" + F[0] + "\r" + F[1] + "\r" + IDLE;
    const { io } = delegationIO(x, paneText);
    const result = await api.delegateToPane(io, delegationOptions);
    assert.equal(result.answered, false, "a spinner-only pane must not count as answered");
  };
  await check(D);
  await assert.rejects(() => check(mutant.exports),
    "without the trim the braille blob reads as an answer — the test above is decisive");
  assert.equal(fs.readFileSync(filename, "utf8"), source);
});

test("F-46a mutation control: removing the view exclusion spends budget on content-free rows", () => {
  const filename = require.resolve("../control/conductor-view");
  const source = fs.readFileSync(filename, "utf8");
  const anchor = "  return e.content_free !== true;";
  assert.ok(source.includes(anchor), "the content-free view exclusion anchor must exist");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor, "  return true;"), filename);
  const contentFree = J.prepareEntry(entry({ status: "observed", answer: "",
    reason: "content-free observation", content_free: true, chrome_removed: 40,
    chrome_kinds: ["idle_prompt", "spinner"] }), "session-test", () => "2026-09-06T00:00:00Z");
  const real = J.prepareEntry(entry({ pane_id: "pane-3", node_id: "node-3",
    answer: "REAL ANSWER" }), "session-test", () => "2026-09-06T00:01:00Z");
  const check = (api) => {
    const v = api.composeView("what did they all say", [contentFree, real], profile(8000));
    assert.ok(!v.entry_ids.includes(contentFree.event_id),
      "a content-free row must not ride into the conductor's view");
    assert.ok(v.entry_ids.includes(real.event_id));
  };
  check(V);
  assert.throws(() => check(mutant.exports),
    "without the exclusion the content-free row re-enters the view — the test above is decisive");
  assert.equal(fs.readFileSync(filename, "utf8"), source);
});
