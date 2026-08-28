"use strict";
/**
 * Falsification harness for U329 — the ORDER of a worker's readiness signals and the WINDOW the
 * weakest of them may read (Phase 19 unit 19.4).
 *
 * The audited code decided a live provider's state by keyword-matching `buffer.snapshot()` before it
 * consulted the MCP connection, and the suite that covered it asserted only positive cases: every
 * classification it could make was tested, and nothing tested that a HEALTHY worker is left alone.
 * That is the shape of a guard nobody has ever seen fail. So each way back to the audited behaviour
 * is spliced into `apps/desktop/control/worker-readiness.js` here, and the behavioural suite is
 * required to go RED for every one.
 *
 * Run from the repo root: `node tools/mutation/readiness_signal_mutations.js`
 * (or `npm run test:falsify:readiness` from `apps/desktop`).
 *
 * It writes to a product file, so the original is held in memory and restored from a `finally` and
 * from the signal/exception paths too. It shares `.mutation.lock` with the other harnesses because
 * `system_pane_write_mutations.js` also mutates this module (M4/M6 followed the U328 rule into it),
 * so the two can never read each other's mutated bytes as a baseline.
 */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..", "..");
const DESKTOP = path.join(ROOT, "apps", "desktop");
const LOCK = path.join(__dirname, ".mutation.lock");

const MODULE = "apps/desktop/control/worker-readiness.js";
const SUITE = ["--test", "test/worker-readiness.test.js"];

/** The tree these mutations were read against and shown to be caught on. A run that adopted whatever
 *  is on disk as its baseline would restore a bypass faithfully and print success over it. */
// Re-pinned at 19.4's U385 fix: the readiness CHALLENGE replaces the quoted token (the prompt no
// longer contains the reply it asks for, and a turn whose prompt does is refused), and a mid-turn
// exit is rendered FAILED like every other exit (U386(b)). R19-R21 grade exactly those three.
// Every earlier mutation was re-read against the new bytes: R3/R10/R11 moved with the lines they
// anchor on and are re-stated above; R1-R2, R4-R9 and R12-R18 anchor on lines this change does not
// touch. The previous pin was 222B9C43E4B19CE27E23E2716C5D689248E747006E2C64B8CCA0AA371DEF93E0.
// Re-pinned TWICE at round 4: once for `challengeStamp` and the call site it feeds (U392 — R22/R23
// are that repair's own graders), and once for the comment repairs the round-4 auditor's MAJOR
// required (U393), which moved bytes in the header and at the answer-count site. R3/R10/R11 anchor
// on the count and the promotion condition, neither of which changed; every other anchor is
// untouched. Intermediate pins: 8D565FE3...D75C939, then CA9B0D95...A00F063F.
// Re-pinned at 19.4-followon, for a behaviour change this time: `lastLines` keeps the last N
// NON-BLANK lines ([[U380]] — a repaint's blank lines were spending the bound on nothing), the U373
// residual paragraph in the header is rewritten because the gate's read is now bounded, and the
// comment count corrected to the MEASURED 41 characters ([[U394]]). R4/R5/R13/R14 anchor on the
// window's floor and its bounds, none of which moved; R24 and R25 are new and grade this unit's two
// additions. Previous pin: B526A830...A2D74E3C.
// Re-pinned at that unit's round-1 review: TAIL_LINES 24 -> 80 (the validator measured that a
// 24-line window is SMALLER than the 30-row pane the shell spawns, so a live modal at the top of a
// full-screen repaint was outside the only window allowed to see it, [[U395]]), plus the prose that
// says so. R4/R5/R13/R14 anchor on the floor and the bounds; R5's anchor is the constant and moved
// with it. R26 is new. Re-pinned once more at the same unit's round-1 spec-audit, for one comment
// whose stated reason had retired with the gate's whole-buffer read; no anchor moved, all re-run
// CAUGHT. Previous pins: F70F2800...D558E0FB, then B4F57BD7...DAE0FD28.
// Re-pinned at the same unit's ROUND-2 review, comment bytes only: the `TAIL_LINES` note dropped an
// unmeasured claim about a maximized pane and gained the byte half the validator measured at the
// SPAWN DEFAULT ([[U400]]); the WHAT-THIS-DOES-NOT-DO paragraph records that 24 -> 80 also widened
// [[U372]]'s window 3.3x; the call-site paragraph records the conductor-label half of [[U401]]. No
// anchor moved — R5's is the constant's VALUE, which did not change. Previous pin:
// E8231B00...B84CCACA6.
// Re-pinned at 19.6 ([[U386]](c)): ONE statement moved — the readiness-turn count is read from the
// provider's DECLARED trait (`control/provider-traits.js`) instead of `provider === "grok_build"
// ? 2 : 1` — plus its require line and the comment above it. R1-R5 anchor in the ordering rule,
// the window bound and the exit-code path; none of those bytes moved. All re-run CAUGHT.
// Re-pinned at 19.8 (U337/U437(e)): readiness now seeds and refreshes process/node/MCP fields from
// exact observers and omits the six unmeasured readiness claims. The classifier, challenge, bounded
// window and turn-count statements R1-R26 mutate are unchanged; every row was re-run CAUGHT.
// Re-pinned at 19.10 after the second-turn-only failure label became a descriptor-sized final-turn
// label. Signal ordering, bounded-window and answer grading anchors R1-R26 are unchanged.
const PINS = { [MODULE]: "494E01FBF6881F1EA4E840A73EBCC78FE061F96D0D3ED85459CBDA47EE878037" };

/** [id, description, ...[find, replace] edits] */
const MUTATIONS = [
  // ---- the ORDER --------------------------------------------------------------------------------
  ["R1", "an exited process is classified from its transcript again (the inverted recon rule)",
    ['  if (processState !== "running") {\n', '  if (false) {\n']],
  ["R2", "the screen is consulted before the MCP connection (the audited order, restored)",
    ["  if (mcpConnected === true) {\n"
      + '    return { source: "mcp_connection", connected: true, setup: null, screen_consulted: false };\n'
      + "  }\n", ""]],
  ["R3", "the readiness turn classifies before it checks whether the worker ANSWERED",
    ["      if (toolSucceeded && answers !== null && answers >= 1) {\n"
      + "        return { ok: true, tool_succeeded: true, answer_occurrences: answers };\n"
      + "      }\n", ""]],

  // ---- the WINDOW -------------------------------------------------------------------------------
  ["R4", "the classification window goes back to the whole retained buffer (U329's shipped defect)",
    ["    return region(paneId, Number.isInteger(notBefore) ? Math.max(floor, notBefore) : floor, maxLines);",
      "    return region(paneId, buffer.dropped, Infinity);"]],
  ["R5", "the line bound is dropped, so a screen means everything still held",
    ["const TAIL_LINES = 80;", "const TAIL_LINES = Infinity;"]],
  ["R6", "an unanswerable window is reported as a clean screen instead of as unanswerable",
    ["      return {\n"
      + "        answerable: false, text: \"\", from, at,\n"
      + '        reason: "the bounded window is no longer held exactly by the pane buffer",\n'
      + "      };",
      '      return { answerable: true, text: "", from, at, bytes: 0 };']],
  ["R7", "an unanswerable window classifies anyway, on whatever text it was handed",
    ["  if (!window || window.answerable !== true) {\n"
      + "    return {\n"
      + '      source: "screen_unanswerable", setup: null, screen_consulted: true,\n'
      + '      reason: (window && window.reason) || "no window was offered",\n'
      + "    };\n"
      + "  }\n", ""]],

  // ---- 19.4-followon: U380's blank lines, and the mark floor nothing graded ---------------------
  ["R24", "the line bound counts BLANK lines again, so a repaint evicts a modal that is on screen",
    ["  const kept = [];\n"
      + "  for (let i = lines.length - 1; i >= 0 && kept.length < max; i -= 1) {\n"
      + "    if (lines[i].trim()) kept.push(lines[i]);\n"
      + "  }\n"
      + '  return kept.reverse().join("\\n");',
      '  return lines.slice(Math.max(0, lines.length - max)).join("\\n");']],
  // The round-5 gate-validator's V4: the nonce window's floor is the mark, and nothing reddened when
  // it was replaced by a read from the start of the stream — so an answer already on the screen when
  // the turn began could be counted as the answer to it.
  ["R25", "the nonce window loses its mark floor, so an EARLIER reply already on the screen counts",
    ["      const own = io.window.since(record.paneId, mark);",
      "      const own = io.window.since(record.paneId, 0);"]],

  // The round-1 review's fourth surviving probe: deleting `.reverse()` returns the window's lines in
  // reverse screen order, and 939 tests stayed green. Order is load-bearing — the affordance pattern
  // for a numbered menu requires "1. Yes" BEFORE "2. No" — so this turns a refusal into a write.
  ["R26", "the window returns its lines in reverse screen order",
    ['  return kept.reverse().join("\\n");', '  return kept.join("\\n");']],

  // ---- the EXIT PATH ----------------------------------------------------------------------------
  ["R8", "an observation never resets, so a cleared screen keeps its old verdict (sticky state)",
    ["function trackObservation(previous, setup) {\n  if (!setup) return null;",
      "function trackObservation(previous, setup) {\n  if (!setup) return previous;"]],
  ["R9", "one glimpse of a screen is a verdict again",
    ["const CONFIRM_POLLS = 2;", "const CONFIRM_POLLS = 1;"]],

  // ---- the NONCE, which is what promotes a worker to READY ---------------------------------------
  ["R10", "readiness is counted on a fragment the PROMPT ITSELF CONTAINS, so the pane's echo of our "
    + "own keystrokes is an answer again",
    ["      const answers = own.answerable ? occurrenceCount(own.text, challenge.expected) : null;",
      "      const answers = own.answerable ? occurrenceCount(own.text, challenge.head) : null;"]],
  ["R11", "the tool-call requirement is dropped: the answer alone is enough",
    ["      if (toolSucceeded && answers !== null && answers >= 1) {",
      "      if (answers !== null && answers >= 1) {"]],

  // ---- U373: THE WRITE GATE'S REFUSAL, WHICH IS NOT BOUNDED, DECIDING A WORKER'S STATE -----------
  // Both mandatory reviewers found this independently at the 19.4 gate: `writeRefusal` is the U328
  // gate, which reads the WHOLE retained buffer, so promoting its refusal to a provider verdict put
  // the audited pin back on a path no test in the unit could see (the harness stubbed the binding).
  ["R12", "the write gate's whole-buffer refusal is the worker's state again (the 19.4 gate defect)",
    ["      const refusal = io.writeRefusal(record.paneId);\n"
      + "      if (!refusal) {",
      "      const refusal = io.writeRefusal(record.paneId);\n"
      + '      if (refusal) return { ok: false, stage: "provider_setup", setup: refusal };\n'
      + "      if (!refusal) {"]],
  ["R13", "the in-turn classification window loses its floor, so a mention in the transcript "
    + "classifies a worker that is merely slow to answer",
    ["        window: () => io.window.read(record.paneId, { notBefore: mark }),",
      "        window: () => io.window.read(record.paneId),"]],
  ["R14", "the floor WIDENS the window instead of narrowing it",
    ["    return region(paneId, Number.isInteger(notBefore) ? Math.max(floor, notBefore) : floor, maxLines);",
      "    return region(paneId, Number.isInteger(notBefore) ? Math.min(floor, notBefore) : floor, maxLines);"]],
  ["R15", "a withheld prompt is reported as a provider verdict rather than as a stall",
    ['          : result.stage === "readiness_prompt_withheld" ? "write_gate_withheld"',
      '          : result.stage === "readiness_prompt_withheld" ? "screen_text_bounded_window"']],
  // ---- the ROUND-2 defect: the withheld loop read a record from before the turn -----------------
  ["R16", "the withheld-write loop stops refreshing the launch record, so a worker that DIES while "
    + "the gate withholds is classified by its screen (the round-2 BLOCKING finding)",
    ["      const live = io.record(record.paneId);\n"
      + '      if (live.state !== "running") {\n',
      "      const live = record;\n"
      + "      if (false) {\n"]],
  ["R17", "the turn's structured failure reports the process the record held BEFORE the turn, so a "
    + "dead worker is recorded as running beside its own exit code",
    ["        record = io.record(paneId);\n        if (result.setup) {",
      "        if (result.setup) {"]],
  ["R18", "a delivery the gate refused is labelled a deadline that never elapsed",
    ['          : result.stage === "readiness_prompt_delivery" ? "write_not_delivered"\n',
      '          : result.stage === "readiness_prompt_delivery" ? "readiness_deadline"\n']],

  // ---- U385: THE PROMPT THAT CONTAINED ITS OWN ANSWER, AND THE REPAINT THAT SATISFIED IT ---------
  // Found by the RUN, not by a reviewer: a ConPTY resize repaints the screen and re-emits our own
  // prompt, so a count of a token the prompt SPELLS OUT reaches two with the pane silent. R19 grades
  // the fail-closed guard (a prompt containing its answer is never typed); R20 removes the guard too,
  // which is the shipped defect exactly and must redden the repaint control; R10 above is its third
  // form. Each is one edit against the ORIGINAL bytes, so they do not compose.
  ["R19", "the prompt quotes the literal reply again, and the guard is expected to refuse it",
    ["    prompt: `Readiness check only. Call the Sovereign get_worker_status tool for node ${nodeId}, `\n"
      + "      + `then reply with a single word: the fragment ${head} written immediately before the `\n"
      + "      + `fragment ${tail}, with nothing at all between them. Do not call any other tool.`,\n",
      "    prompt: `Readiness check only. Call the Sovereign get_worker_status tool for node ${nodeId}, `\n"
      + "      + `then reply exactly ${head}${tail}. Do not call any other tool.`,\n"]],
  ["R20", "U385's shipped defect, whole: the prompt quotes its own answer AND the guard that refuses "
    + "such a prompt is gone, so a repaint of our keystrokes is READY",
    ["    prompt: `Readiness check only. Call the Sovereign get_worker_status tool for node ${nodeId}, `\n"
      + "      + `then reply with a single word: the fragment ${head} written immediately before the `\n"
      + "      + `fragment ${tail}, with nothing at all between them. Do not call any other tool.`,\n",
      "    prompt: `Readiness check only. Call the Sovereign get_worker_status tool for node ${nodeId}, `\n"
      + "      + `then reply exactly ${head}${tail}. Do not call any other tool.`,\n"],
    ["    if (String(challenge.prompt).includes(challenge.expected)) {\n", "    if (false) {\n"]],

  // ---- U386(b): one physical condition, one rendering --------------------------------------------
  ["R21", "a worker that died DURING a turn is rendered STALLED again — the same exit the loop above "
    + "calls FAILED, renamed by our timing",
    ['        const terminal = result.stage === "process_exited_during_readiness" ? "FAILED" : "STALLED";',
      '        const terminal = "STALLED";']],

  // ---- U392: THE CALL SITE THAT SUPPLIES THE FRESHNESS -------------------------------------------
  // The round-4 gate-validator froze the challenge stamp and ran the WHOLE desktop suite: 928/928
  // green. `readinessChallenge` is pinned pure and correct while what it is handed was asserted
  // nowhere — this unit's recurring shape (U373, U379, the round-2 BLOCKING finding), a fourth time.
  // R22 is the validator's own probe, kept: an unchanging challenge means run N's answer, redrawn
  // after run N+1's mark, satisfies run N+1. R23 removes only the SEQUENCE, leaving the clock: on
  // this host it reddens the behavioural test too (a run returns when its pane answers, so both fell
  // inside one millisecond), but that is this host's timing and not a property — the same-instant
  // test is what grades it at any speed. Two mutations because there are two distinct claims.
  ["R22", "the readiness challenge stops being fresh, so an EARLIER run's answer still on the screen "
    + "is this run's answer (the validator's round-4 probe)",
    ["      const challenge = readinessChallenge(record.nodeId, turn, challengeStamp(io.now()));",
      '      const challenge = readinessChallenge(record.nodeId, turn, "fixedstamp");']],
  ["R23", "freshness goes back to resting on the clock alone, so two challenges minted in the same "
    + "millisecond are identical",
    ["const challengeStamp = (now) =>\n"
      + "  `${Number(now).toString(36)}${(challengeSequence += 1).toString(36)}`;",
      "const challengeStamp = (now) => `${Number(now).toString(36)}`;"]],
];

const hash = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex").toUpperCase();
const abs = (rel) => path.join(ROOT, rel);
const REPIN = process.argv.includes("--repin");

let lockFd;
try {
  lockFd = fs.openSync(LOCK, "wx");
} catch (e) {
  if (e.code === "EEXIST") {
    console.error(`another mutation run holds ${LOCK}. If none is running, the product files may be `
      + "MUTATED — check them against the pins before deleting the lock.");
    process.exit(3);
  }
  throw e;
}

const ORIGINAL = Object.fromEntries(Object.keys(PINS).map((rel) => [rel, fs.readFileSync(abs(rel))]));
const restoreFiles = () => {
  for (const [rel, bytes] of Object.entries(ORIGINAL)) fs.writeFileSync(abs(rel), bytes);
};
const release = () => { try { fs.unlinkSync(LOCK); } catch { /* already released */ } };
const restore = () => { restoreFiles(); release(); };
for (const sig of ["SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"]) {
  process.on(sig, () => { restore(); process.exit(130); });
}
for (const fatal of ["uncaughtException", "unhandledRejection"]) {
  process.on(fatal, (e) => { restore(); console.error(e); process.exit(2); });
}

let failures = 0;
if (REPIN) {
  release();
  for (const rel of Object.keys(PINS)) console.log(`${hash(ORIGINAL[rel])}  ${rel}`);
  process.exit(0);
}

for (const [rel, pin] of Object.entries(PINS)) {
  const actual = hash(ORIGINAL[rel]);
  if (actual !== pin) {
    restore();
    console.error(`${rel} is ${actual}, not the pinned ${pin} — refusing to run.`);
    console.error("Either a run was interrupted, or the file legitimately changed and PINS must be "
      + "updated by someone who re-read these mutations against it (`--repin` prints the hashes).");
    process.exit(3);
  }
}

const runSuite = () => spawnSync(process.execPath, SUITE, { cwd: DESKTOP, encoding: "utf8" }).status === 0;

try {
  console.log(`base ${MODULE} SHA-256 ${hash(ORIGINAL[MODULE])}`);
  console.log(`clean tree ${SUITE[1]}: ${runSuite() ? "GREEN (expected)" : "RED — broken before any mutation"}`);

  for (const [id, what, ...edits] of MUTATIONS) {
    let mutated = ORIGINAL[MODULE].toString("utf8");
    for (const [from, to] of edits) {
      const at = mutated.indexOf(from);
      if (at === -1) throw new Error(`${id}: anchor not found: ${JSON.stringify(from.slice(0, 70))}`);
      if (mutated.indexOf(from, at + 1) !== -1) {
        throw new Error(`${id}: anchor is not unique: ${JSON.stringify(from.slice(0, 70))}`);
      }
      mutated = mutated.slice(0, at) + to + mutated.slice(at + from.length);
    }
    fs.writeFileSync(abs(MODULE), mutated);
    const syntax = spawnSync(process.execPath, ["--check", abs(MODULE)], { cwd: DESKTOP, encoding: "utf8" });
    const green = runSuite();
    restoreFiles();
    const ok = !green && syntax.status === 0;
    if (!ok) failures += 1;
    console.log(`${ok ? "CAUGHT " : "MISSED "} ${id}  ${what}`
      + `${syntax.status === 0 ? "" : `  [SYNTAX ERROR — mutation invalid: ${(syntax.stderr || "").split("\n")[2]}]`}`);
  }
} catch (e) {
  failures += 1;
  console.error(e.message);
} finally {
  restore();
}

for (const rel of Object.keys(PINS)) {
  const after = hash(fs.readFileSync(abs(rel)));
  console.log(`restored ${rel} SHA-256 ${after} — ${after === hash(ORIGINAL[rel]) ? "BYTE-IDENTICAL" : "MISMATCH"}`);
  if (after !== hash(ORIGINAL[rel])) failures += 1;
}
console.log(failures === 0 ? `ALL ${MUTATIONS.length} READINESS-SIGNAL MUTATIONS CAUGHT` : `${failures} PROBLEM(S)`);
process.exit(failures === 0 ? 0 : 1);
