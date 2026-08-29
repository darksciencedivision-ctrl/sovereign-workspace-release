"use strict";
/**
 * Falsification harness for `apps/desktop/test/voice-disarm-wiring.test.js` (U175).
 *
 * A guard that has never been shown to fail is not a guard. This applies each known bypass of the
 * `pane:input` → voice-turn-release property to `main.js`, runs ONLY the wiring test file, records
 * whether the suite goes red, and restores `main.js` BYTE-IDENTICALLY after every one. It exits
 * non-zero if any mutation stays green, if a mutation is not valid JavaScript, or if the restore
 * does not reproduce the original hash.
 *
 * Run from the repo root: `node tools/mutation/pane_input_bypass_mutations.js`.
 *
 * It writes to a product file, so the original bytes are held in memory and restored from a `finally`
 * and from the signal/exception paths as well — an interrupted run must not leave `main.js` mutated.
 * It lives outside every declared product path (see the receipt's `source.product_paths`) so that
 * running it changes nothing a packaged receipt covers.
 */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");

const DESKTOP = path.resolve(__dirname, "..", "..", "apps", "desktop");
const MAIN = path.join(DESKTOP, "main.js");
const LOCK = path.join(__dirname, ".mutation.lock");

/**
 * The baseline this harness may run against, pinned as a constant.
 *
 * Without it the check at the end is circular: `ORIGINAL` is whatever was on disk at start, so a run
 * begun on an ALREADY-mutated tree (a previous run hard-killed, or two runs at once) adopts the
 * mutation as its baseline, restores it faithfully, and prints BYTE-IDENTICAL over a bypass still
 * sitting in a product file. Update this deliberately when `main.js` legitimately changes — that is
 * the point: the value is a claim about which tree these mutations were shown to be caught on.
 */
// Re-pinned at 17E `.review-fixes`: main.js changed by ONE edit — the session-approval log path is
// isolated under SHELL_SELFCHECK (spec-audit F9), which touches no pane:input, no supervision gate
// and no delivery path these mutations target. Each mutation was re-read against the new tree and
// re-run: all CAUGHT.
// Re-pinned at 18B `.scope`: main.js changed by ONE edit — a new pure helper `providerAllowance()`
// and the launch-chrome field that calls it, so a 1-terminal subscription is not displayed with the
// global ceiling of 2 (OP-12 §12). Every anchor these mutations splice against is untouched and
// still unique (`pane:input` handler body and top, `function makeWindow() {`,
// `handleOperatorResumeInput`, `conductorVoiceAuthority`, `clearConductorInputResidue`), and the
// edit adds no call to any release sink and no path out of the input handler. Each mutation was
// re-read against the new tree and re-run: all CAUGHT, restore BYTE-IDENTICAL.
// Re-pinned at 18B `.picker`: main.js changed by THREE edits, all self-check plumbing — a `require`
// of `selfcheck/op12-picker-selfcheck`, one `SHELL_SELFCHECK === "op12-picker"` arm in the kind
// ladder, and one branch in the receipt selector. All three sit inside the `SHELL_SELFCHECK` block
// that the product path never enters; none adds a call to any release sink, any relay, or any path
// out of the `pane:input` handler. Every anchor these mutations splice against was re-counted
// against the new tree and is still present exactly ONCE (`IN_HANDLER`, `HANDLER_TOP`,
// `makeWindow`, `handleOperatorResumeInput(event, input)`, the real disarm,
// `clearConductorInputResidue`, and the four `pane:*` handlers X1–X4 target). Each mutation was
// re-read against the new tree and re-run: all CAUGHT, restore BYTE-IDENTICAL. The `.picker` work
// commit b05b9ef changed main.js WITHOUT re-running this harness, so the ordinary suite went red on
// the stale pin — which is exactly the U186 test doing its job.
//
// The pin is the hash of the file with the LF endings `.gitattributes` pins (`* text=auto eol=lf`),
// i.e. the COMMITTED blob. b05b9ef's editor also rewrote the worktree copy CRLF, which `git status`
// cannot see (it normalises text files before comparing) but which changes this hash AND breaks
// every splice anchor below, since they are written with `\n`. The worktree copy was restored to the
// committed bytes before re-pinning. A CRLF working copy going red here is correct: this harness
// cannot mutate a file whose anchors it cannot find (U274).
// Re-pinned at 18C `.close`: main.js changed by THREE edits, the same self-check-plumbing class as
// `.picker` — a `require` of `selfcheck/op12-acceptance-selfcheck`, one
// `SHELL_SELFCHECK === "op12-acceptance"` arm in the kind ladder, and one branch at the head of the
// receipt selector. Two of the three sit inside the `SHELL_SELFCHECK` block the product path never
// enters; the `require` is module-top-level and DOES run on every product launch, exactly as the
// other twenty self-check requires above it do — the module has no load-time side effect beyond
// further requires main.js has already made. (The first version of this note claimed all three were
// inside the block, which was false for the require — gate-validator MINOR-11.) None of the three
// adds a call to any release sink, any relay, or any path out of the `pane:input` handler.
// A FOURTH edit followed in the same unit — one `mainLogFile: mainProcessLogger.file` field on the
// self-check ctx object, so the §17 credential scan reads the sink the logger owns instead of an env
// var. Also inside the `SHELL_SELFCHECK` block, also no new path out of the input handler.
// Anchors re-counted against the new tree: `function makeWindow() {` ×1,
// `handleOperatorResumeInput(event, input)` ×2 (declaration + the `before-input-event` call, as
// before), `clearConductorInputResidue` ×4, and the `pane:*` handlers X1–X4 target all still present.
// Each mutation was re-read against the new tree and re-run: all CAUGHT, restore BYTE-IDENTICAL.
// Worktree copy verified to carry zero CR bytes before re-pinning (U274).
// Re-pinned again at 18D `.close`: THREE edits, the same self-check-plumbing class as 18C's — a
// `require` of `selfcheck/op18d-registration-selfcheck` (module-top-level, runs on every product
// launch, no load-time side effect beyond further requires main.js has already made), one
// `SHELL_SELFCHECK === "op18d-registration"` arm in the kind ladder, and one branch at the head of
// the receipt selector. The last two sit inside the `SHELL_SELFCHECK` block the product path never
// enters. None adds a call to any release sink, any relay, or any path out of the `pane:input`
// handler. Anchors re-counted against the new tree: `function makeWindow() {` ×1,
// `handleOperatorResumeInput(event, input)` ×2, `clearConductorInputResidue` ×4, the `pane:input`
// handler and its `return manager.write(id, data);` tail ×1 each — all present and unmoved. Every
// mutation re-read against the new tree and re-run: all CAUGHT, restore BYTE-IDENTICAL. Worktree
// copy verified to carry zero CR bytes before re-pinning (U274).
// Re-pinned for provider-agnostic conductor selection. The edits resolve the selected conductor
// adapter before launch, expose a pre-launch selection IPC intent, and branch provider-specific
// permission setup; they do not add a voice release sink or bypass `pane:input` supervision. The
// mutation anchors remain unique and the harness below is re-run against these exact bytes.
// Re-pinned for live Sovereign MCP orchestration. The edits add the authenticated application
// gateway, governed worker control handlers, and operational Inspector reads. They do not alter the
// pane:input handler or add a voice-release sink. The three mutation anchors above were re-counted
// against this file (one each) before running the harness; all mutations must still go RED below.
// Re-pinned after live acceptance hardened worker MCP readiness and refreshed assignment/exit chrome.
// Those edits remain outside pane:input and the authority-release sinks; all splice anchors below
// remain unique. This harness is re-run against these exact bytes before the checkpoint is committed.
// Re-pinned for final operational readiness and deadline enforcement. The added readiness probes,
// MCP operation tracking, peer/debate deadlines, and structured failure states do not alter the
// pane:input handler or any voice-authority release sink. Every splice anchor below was re-read
// against this exact file and remains present in its expected unique context.
// Re-pinned after the live TUI paste/submit race increased only `writePanePrompt`'s bounded settle
// interval. That function is downstream of authenticated app delivery and outside pane:input and
// every release sink; the mutation anchors remain unchanged and unique.
// Re-pinned after the same live finding established Codex needs a provider-specific second Enter
// to confirm then submit a pasted prompt. This remains inside `writePanePrompt`; it does not change
// pane:input or voice-authority release behavior, and all mutation anchors remain unique.
// Re-pinned after normal Electron quit gained the same bounded `manager.shutdown` wait already used
// by self-check teardown. The new code is in app lifecycle handlers, not pane:input or any voice
// release sink; all mutation anchors were re-read and remain unique.
// Re-pinned at 19.3 (U328). main.js changed by FOUR edits, all on the SYSTEM→pane direction this
// harness does not cover: a `require` of `control/pane-writer`, the `createPaneWriter` io + the
// `paneWriteRefusalFor` helper, `writePanePrompt`/`notifyNode` reduced to delegations, and a
// pre-check added to `runConductorReadiness` and `waitForWorkerReadinessTurn`. The OPERATOR→pane
// path is untouched: no new call to any voice release sink, no new path out of the `pane:input`
// handler, and the handler itself is byte-identical. The edits do add a THIRD `manager.write(` site
// (the pane-writer io), which none of these anchors matches — `IN_HANDLER` is the handler's own
// `return manager.write(id, data);` line and was re-counted as present exactly ONCE, as were
// `HANDLER_TOP`, `function makeWindow() {`, `handleOperatorResumeInput(event, input)`,
// `clearConductorInputResidue`, and the four `pane:*` handlers X1–X4 target. The new direction has
// its own harness (`tools/mutation/system_pane_write_mutations.js`), which shares this lock file
// because both mutate main.js. Every mutation below was re-read against the new tree and re-run:
// all CAUGHT, restore BYTE-IDENTICAL. Worktree copy verified to carry zero CR bytes (U274).
// Re-pinned again at 19.3's close for the `system-pane-write` self-check branch and its two ctx
// bindings: those bytes add no `pane:*` handler, no voice release sink and no fourth `manager.write(`
// site, so every anchor below was re-counted as still present exactly once and re-run CAUGHT.
// Re-pinned at 19.4's close for ONE added self-check ctx binding (`setWorkerOperationalState`, the
// production operational-state writer the in-Electron readiness-run legs need). Those bytes sit
// inside the SHELL_SELFCHECK ctx literal: they add no `pane:*` handler, no voice-authority release
// sink and no `manager.write(` site, and every anchor below was re-counted as present exactly once
// — which this harness re-checks itself, since it refuses to splice a non-unique anchor — and
// re-run: all CAUGHT, restore BYTE-IDENTICAL.
// Re-pinned at 19.4's U385 fix for a COMMENT-ONLY change to main.js (U386(f): the self-check ctx
// comment said the check supplies "its own MCP session state" when it supplies six bindings and a
// seeded launch record). No statement moved, no `pane:*` handler, voice-release sink or
// `manager.write(` site was added or removed, and every anchor below was re-counted as present
// exactly once — which this harness re-checks itself, since it refuses to splice a non-unique
// anchor — and re-run: all CAUGHT, restore BYTE-IDENTICAL.
// Re-pinned at 19.4-followon for a TWO-LINE change to main.js: the U328 write gate's screen reader
// is now bound to the shell's bounded window (`paneScreenFromWindow(readinessWindow)`, U373's
// residual) and the require line above it names that export. The OPERATOR->pane direction is
// untouched — no `pane:*` handler, no voice-release sink and no `manager.write(` site was added or
// removed — and every anchor below was re-counted as present exactly once (which this harness
// re-checks itself, since it refuses to splice a non-unique anchor) and re-run: all CAUGHT, restore
// BYTE-IDENTICAL. The note trail stopped at U386(f) while main.js had changed twice more (U393's
// comment repair at `fedbc4e`, then this); that gap is [[U394]] MINOR-5 and this line closes it.
// Re-pinned at 19.6 ([[U331]]) for a TWO-EDIT change to main.js, neither on the operator->pane
// direction these mutations guard: conductor readiness now asks `conductorAdmission(descriptor)`
// instead of comparing a provider id and a model slug, and the pane provider resolver is hoisted
// to a const so the in-Electron descriptor check is handed the same function the writer uses.
// Every anchor below was re-read against the new bytes; every mutation re-run CAUGHT.
// Re-pinned at 19.8 (U337/U437(e)). main.js gained orchestration self-check routing and readiness
// observation wiring only; no operator→pane handler, voice-release sink, or manager.write site was
// added, removed, or moved. Every mutation anchor below was re-counted unique and re-run CAUGHT.
// Re-pinned at 19.9 after orchestration decisions moved into require-able modules and shutdown
// completion began reading both bounded server outcomes. The pane:input handler and every P1-P36
// anchor are unchanged; the full harness was re-run and restored main.js byte-identically.
// Re-pinned at 19.10 after model-probe capability stopped being asserted and the launch ticket's
// descriptor was cross-checked against the readiness feed. Both edits are in conductor launch
// orchestration, not pane:input or a voice-release sink. Every mutation below was re-read against
// these exact bytes and must be re-run CAUGHT before this pin is accepted.
// Re-pinned at W-18a: main.js gained `unhandledRejection`/`uncaughtException` handlers that run
// the terminal-releasing teardown, and `completeNormalQuit` gained a `faultKind` so a faulted
// exit cannot report success. No mutation in this file anchors on those bytes; every anchor was
// re-read against them and re-run CAUGHT.
// Re-pinned at W-29 (Tier 3): main.js changed by THREE edits, all at the pane-CREATION boundary --
// `sanitizeRendererSpec` became an allow-list driven by a new frozen `RENDERER_SPEC_ALLOWED_KEYS`,
// the `pane:new` handler now supplies a credential-scrubbed env, and the `launch-source` require
// line gained `scrubCredentialEnv`. None of it touches the pane:input handler, the before-input
// path, any disarm sink, or any release site these mutations target. Every anchor was re-read
// against the new bytes and re-counted as present exactly once (`IN_HANDLER`, `HANDLER_TOP`,
// `AFTER_RESUME`, `BEFORE_INPUT`, `REAL_DISARM`, the four `pane:*` handlers X1-X4 target -- note
// X1-X4 are pane:focus/maximize/resize/close, NOT pane:new -- and `clearConductorInputResidue` at
// its four sites). W-29's own graded rows are P28/P29 in system_pane_write_mutations.js, which
// supports a per-row suite; this harness grades every row with the single voice-disarm wiring suite,
// which cannot see a pane-creation defect and would report a mis-aimed row as MISSED.
// Re-pinned again at W-30, same tier: main.js gained a `navigationIsPermitted` predicate
// immediately BEFORE `function makeWindow() {` -- which is this harness's `AFTER_RESUME` anchor --
// and a `setWindowOpenHandler` + `will-navigate` pair before `win.loadFile(`. AFTER_RESUME was
// re-counted after the insertion and is present exactly ONCE: text was added before the anchor, not
// a second copy of it. The `will-navigate` listener calls `event.preventDefault()` and is a
// NAVIGATION path; it adds no release sink, no relay, and no path out of the pane:input handler, so
// no mutation here changes meaning. All anchors re-read and re-run CAUGHT.
// Re-pinned a third time at W-32: the CONDUCTOR launch path gained the ticket-name leftover guard
// it never had, the classifier stage, and the stage-4 assertion on the env it actually spawns with.
// All three sit inside `launchConductor`, which no mutation here targets; the pane:input handler,
// the before-input path and every disarm sink are untouched. All anchors re-read and re-run CAUGHT.
// Previous pins: B7E081E3...E6CFDA3A, 4A047A48...2A4FD325, then 6C98BF6B...54012983.
// Re-pinned a fourth time at W-35: main.js redacts the `--settings` PROFILE out of the live
// conductor log line (it was reproduced verbatim into the durable log AND mirrored to the
// renderer console) and passes a validated fallback log path. Both edits are inside
// `launchConductor` and the logger construction; no pane:input path, no disarm sink, no PTY
// write site, no readiness path. All anchors re-read and re-run CAUGHT.
// Re-pinned a fifth time at W-37: `spawnFromSelection` now hands `refuseSelection` the LIVE
// picker enumeration so it corroborates a selection instead of believing it. One call site,
// inside the picker spawn path; no pane:input path, no disarm sink, no PTY write site, no
// readiness path. All anchors re-read and re-run CAUGHT.
// Re-pinned a sixth time at W-39: the voice-residue decision LEFT the `pane:input` handler for
// `before-input-event`, because pane:input carries the terminal replies the child elicits. The
// handler now reaches exactly `manager.write`. `REAL_DISARM` was RE-ANCHORED (operatorKeyKind
// hoisted to a const so the residue branch can reuse the classification) -- bytes changed,
// meaning unchanged, N4 re-read and re-run CAUGHT. A12 is new and restores the removed defect.
// Re-pinned at W-64 (SOW loop v3): main.js changed by ADDITIVE edits only - the
// layout-reconstruct require gained resumePaneSeq, and did-finish-load now seeds paneSeq
// above every id the persisted recovery snapshot holds, right after the structural
// conductor mint. No pane:input path, voice-release sink or PTY write site moved.
// Worktree copy verified zero CR bytes before re-pinning (U274). Previous pin:
// DA9C7CA3...859F4.
// Re-pinned at B3-1 (H-1, SWS-REM-DIR-20260828 R2) for a COMMENT-ONLY change to main.js:
// the RENDERER_SPEC_ALLOWED_KEYS doc block gained an H-1 closure note (session-manager now
// takes a pre-spawn admission verdict, so the allow-list is defense in depth). No statement
// moved, no `pane:*` handler, voice-release sink, disarm path or `manager.write(` site was
// added or removed, and every anchor below was re-read against the new bytes and re-counted
// as present exactly once (`IN_HANDLER`, `HANDLER_TOP`, `AFTER_RESUME`, `BEFORE_INPUT`,
// `REAL_DISARM`, `function clearConductorInputResidue(why) {`, and the four `pane:*`
// handlers X1-X4 target) — which this harness re-checks itself, since it refuses to splice
// a non-unique anchor. Worktree copy verified to carry zero CR bytes before re-pinning
// (U274). Harness re-run against these exact bytes: all CAUGHT, restore BYTE-IDENTICAL.
// Re-pinned at CONVERGE-01 C0 after reconciling the already-evidenced CP-M1 Band 3/4 source bytes
// (`pane:create-empty`, execution selection, governed replacement, and conductor text surface).
// Those additions restore product paths the committed tests already guard; none changes the
// pane:input handler, voice-residue decision, or release sinks targeted below. Every mutation was
// re-read against the reconciled tree and is re-run before this pin is accepted.
const PINNED_BASELINE = "8B6EA9A678DBE7F6A19C03761C8CD41978D933EC865978081171FD0CDCE425EA";

let lockFd;
try {
  lockFd = fs.openSync(LOCK, "wx");   // exclusive: a second concurrent run must not read run one's bytes
} catch (e) {
  if (e.code === "EEXIST") {
    console.error(`another run holds ${LOCK}. If none is running, main.js may be MUTATED — check it `
      + `against ${PINNED_BASELINE} before deleting the lock.`);
    process.exit(3);
  }
  throw e;
}

const ORIGINAL = fs.readFileSync(MAIN);
const BASE_HASH = crypto.createHash("sha256").update(ORIGINAL).digest("hex").toUpperCase();
if (BASE_HASH !== PINNED_BASELINE) {
  fs.unlinkSync(LOCK);
  console.error(`main.js is ${BASE_HASH}, not the pinned baseline ${PINNED_BASELINE} — refusing to run.`);
  console.error("Either the file is still mutated from an interrupted run, or it legitimately changed "
    + "and PINNED_BASELINE must be updated by someone who re-read these mutations against it.");
  process.exit(3);
}
const SRC = ORIGINAL.toString("utf8");

const IN_HANDLER = "    return manager.write(id, data);\n  });";
const HANDLER_TOP = '  ipcMain.handle("pane:input", (_e, id, data) => {';
const AFTER_RESUME = "function makeWindow() {";
const BEFORE_INPUT = "    handleOperatorResumeInput(event, input);";
// RE-ANCHORED at W-39, and re-read rather than re-hashed. `operatorKeyKind(input)` was hoisted into
// a `const kind` because the residue decision that moved onto this path needs the same
// classification, so the disarm call's bytes changed while its MEANING did not. N4's intent is
// unchanged — "the disarm removed from handleOperatorResumeInput" — and its replacement still
// leaves valid JS, because `operatorKeyKind` is still referenced by the hoisted const above it.
// Previous anchor: `{ key_kind: operatorKeyKind(input) }`.
const REAL_DISARM = '    conductorVoiceAuthority.disarm("electron_main_before_input_event", { key_kind: kind });';

const inHandler = (line) => [IN_HANDLER, `    ${line}\n${IN_HANDLER}`];

const MUTATIONS = [
  // the validator's own R-2a residual and its multi-hop relatives
  ["M1  direct indirect call (R-2a)", inHandler('handleOperatorResumeInput({ preventDefault() {} }, { type: "keyDown", key: "a" });')],
  ["M2  two-hop top-level wrapper", [AFTER_RESUME,
    "function sneakyResume() { handleOperatorResumeInput({ preventDefault() {} }, { type: \"keyDown\", key: \"a\" }); }\n\n"
    + AFTER_RESUME], inHandler("sneakyResume();")],
  ["M15 three-hop chain", [AFTER_RESUME,
    "function hopA() { handleOperatorResumeInput({ preventDefault() {} }, { type: \"keyDown\", key: \"a\" }); }\n"
    + "function hopB() { hopA(); }\n\n" + AFTER_RESUME], inHandler("hopB();")],
  // direct sinks, all four release methods
  ["M3  direct .disarm", inHandler('conductorVoiceAuthority.disarm("electron_main_before_input_event", {});')],
  ["M4  direct .reset", inHandler('conductorVoiceAuthority.reset("bytes", { source: "node_pty_exit" });')],
  ["M5  direct .cancel (validator R-2)", inHandler('conductorVoiceAuthority.cancel("t", "r");')],
  ["M5b direct .stop (auditor F4)", inHandler("conductorVoiceAuthority.stop();")],
  // the auditor's F1: a relay declared INSIDE registerIpc, beside captureFromRef
  ["F1  nested relay inside registerIpc", [HANDLER_TOP,
    '  function endTurnFromPane() { handleOperatorResumeInput({ preventDefault() {} }, { type: "keyDown", key: "a" }); }\n'
    + HANDLER_TOP], inHandler("endTurnFromPane();")],
  // indirection the deny-list could never see
  ["M6  alias variable", inHandler('const f = handleOperatorResumeInput; f({ preventDefault() {} }, { type: "keyDown", key: "a" });')],
  ["M7  object property", inHandler('const o = { go: handleOperatorResumeInput }; o.go({ preventDefault() {} }, { type: "keyDown", key: "a" });')],
  ["M9  deferred via bind", inHandler('setImmediate(handleOperatorResumeInput.bind(null, { preventDefault() {} }, { type: "keyDown", key: "a" }));')],
  ["M8  eval by name", inHandler('eval("handleOperatorResumeInput")({ preventDefault() {} }, { type: "keyDown", key: "a" });')],
  ["M14 eval by concatenation (auditor F3)", inHandler('eval("conductorVoiceAuthority" + ".disarm(\\"electron_main_before_input_event\\", {})");')],
  ["M16 computed member call", inHandler('conductorVoiceAuthority["dis" + "arm"]("electron_main_before_input_event", {});')],
  // second review pass: the forms that beat the FIRST allow-list
  ["FA1 optional call on the sink", inHandler('conductorVoiceAuthority.reset?.("bytes", { source: "node_pty_exit" });')],
  ["FA2 optional call on the relay", inHandler('handleOperatorResumeInput?.({ preventDefault() {} }, { type: "keyDown", key: "a" });')],
  ["FA3 optional call on stop", inHandler("conductorVoiceAuthority.stop?.();")],
  ["FA4 optional member then call", inHandler('conductorVoiceAuthority?.cancel("t", "r");')],
  ["FB  tagged template call", inHandler("conductorVoiceAuthority.reset`node_pty_exit`;")],
  ["FC  relay inside a ${} substitution", [AFTER_RESUME,
    'function fmtRelay() { conductorVoiceAuthority.reset("bytes", { source: "node_pty_exit" }); return ""; }\n\n'
    + AFTER_RESUME], inHandler("clearConductorInputResidue(`${fmtRelay()}`);")],
  ["G   release inside an ALLOW-LISTED callee", ["function clearConductorInputResidue(why) {",
    'function clearConductorInputResidue(why) {\n  conductorVoiceAuthority.cancel("pane_bytes", "transitive");']],
  ["E   shadow-rebind an audited name", inHandler(
    'const clearConductorInputResidue = handleOperatorResumeInput; clearConductorInputResidue({ preventDefault() {} }, { type: "keyDown", key: "a" });')],
  ["RES2 expression-bodied arrow with an object-literal decoy", [
    '  ipcMain.handle("pane:input", (_e, id, data) => {',
    '  ipcMain.handle("pane:input", (_e, id, data) => ({\n'
    + "    a: operatorInputResolvesResidue, b: clearConductorInputResidue, c: manager.write,\n"
    + "    d: (() => { conductorVoiceAuthority.stop(); return manager.write(id, data); })(),\n"
    + "  }));\n"
    + '  ipcMain.handle("pane:input#unused", (_e, id, data) => {'],
  ],
  // third review pass, validator BLOCKER-3: a release that is not a CALL. None of these appends an
  // audit row, so no receipt leg and no `RELEASE_SINK` scan can see one.
  ["S1  direct field write", inHandler("conductorVoiceAuthority._active = null; conductorVoiceAuthority._pending = null;")],
  ["S2  delete the fields", inHandler("delete conductorVoiceAuthority._active; delete conductorVoiceAuthority._pending;")],
  ["S3  computed field write", inHandler('conductorVoiceAuthority["_act" + "ive"] = null;')],
  ["S4  local alias, then write", inHandler("const a = conductorVoiceAuthority; a._active = null; a._pending = null;")],
  ["S5  module-scope alias, then release", [AFTER_RESUME,
    "const authAlias = conductorVoiceAuthority;\n\n" + AFTER_RESUME],
    inHandler('authAlias.disarm("electron_main_before_input_event", {});')],
  ["S6  the service passed out as a value", [AFTER_RESUME,
    "function leak(auth) { auth._active = null; }\n\n" + AFTER_RESUME],
    inHandler("leak(conductorVoiceAuthority);")],
  // third review pass, validator RESERVATION-1: the same relay, one channel over. Each of these left
  // the wiring suite AND all 522 desktop tests green before this round.
  ["X1  relay moved to pane:focus", ['ipcMain.handle("pane:focus", (_e, id) => { panes.focus(id);',
    'ipcMain.handle("pane:focus", (_e, id) => { handleOperatorResumeInput({ preventDefault() {} }, { type: "keyDown", key: "a" }); panes.focus(id);']],
  ["X2  direct disarm on pane:maximize", ['ipcMain.handle("pane:maximize", (_e, id) => { panes.maximize(id);',
    'ipcMain.handle("pane:maximize", (_e, id) => { conductorVoiceAuthority.disarm("electron_main_before_input_event", {}); panes.maximize(id);']],
  ["X3  nested relay reached from pane:resize", [HANDLER_TOP,
    '  function endTurnNextDoor() { handleOperatorResumeInput({ preventDefault() {} }, { type: "keyDown", key: "a" }); }\n'
    + HANDLER_TOP], ['ipcMain.handle("pane:resize", (_e, id, cols, rows) => {',
    'ipcMain.handle("pane:resize", (_e, id, cols, rows) => {\n    endTurnNextDoor();']],
  ["X4  field write on pane:close", ['ipcMain.handle("pane:close", (_e, id) => {',
    'ipcMain.handle("pane:close", (_e, id) => { conductorVoiceAuthority._active = null;']],
  // the wiring the tests must also protect from removal
  ["N3  before-input-event stops calling the handler", [BEFORE_INPUT, "    void event; void input;"]],
  ["N4  the disarm removed from handleOperatorResumeInput", [REAL_DISARM, "    void operatorKeyKind;"]],
  // auditor F5: an `async function` after the handler used to widen the boundary window
  // W-39: the defect this unit removed, restored. `pane:input` carries the terminal replies the
  // CHILD elicits (xterm.js emits onData for a DA/CPR answer), so clearing the voice residue here
  // lets a supervised CLI lift the block that stops two spoken sentences being submitted as one
  // prompt the operator never said. The graded suite catches it through the `PANE_INPUT_MAY_CALL`
  // allow-list, which W-39 narrowed to `manager.write` alone — so this row and that allow-list are
  // the same guard seen from two sides, and neither is load-bearing without the other.
  ["A12 the residue is cleared from pane:input again (the child-reachable channel)",
    inHandler('clearConductorInputResidue("mutation: cleared from the channel the child can reach");')],
  ["F5  disarm hidden behind an async function", [AFTER_RESUME,
    'async function laterThing() { conductorVoiceAuthority.disarm("electron_main_operator_chord", {}); }\n\n'
    + AFTER_RESUME]],
];

function run() {
  const r = spawnSync(process.execPath, ["--test", "test/voice-disarm-wiring.test.js"],
    { cwd: DESKTOP, encoding: "utf8" });
  return r.status === 0;
}

// The lock is released ONCE, when this process is finished with `main.js` — not after each mutation.
// Unlinking it inside the loop (the first form) meant the exclusion held for mutation 1 and for nothing
// after it, so a second run could start mid-loop and read a mutated file as its baseline. It would then
// refuse on PINNED_BASELINE, which is the fail-closed direction, but the exclusivity this file claims
// has to be real (spec-audit F10).
const restoreFile = () => fs.writeFileSync(MAIN, ORIGINAL);
const release = () => { try { fs.unlinkSync(LOCK); } catch { /* already released */ } };
const restore = () => { restoreFile(); release(); };
// Windows raises SIGBREAK on Ctrl+Break and SIGHUP when the console closes; neither was covered.
for (const sig of ["SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"]) {
  process.on(sig, () => { restore(); process.exit(130); });
}
for (const fatal of ["uncaughtException", "unhandledRejection"]) {
  process.on(fatal, (e) => { restore(); console.error(e); process.exit(2); });
}

let failures = 0;
try {
  console.log(`base main.js SHA-256 ${BASE_HASH}`);
  console.log(`clean tree: ${run() ? "GREEN (expected)" : "RED — the suite is broken before any mutation"}`);

  for (const [name, ...edits] of MUTATIONS) {
    let mutated = SRC;
    for (const [from, to] of edits) {
      const at = mutated.indexOf(from);
      if (at === -1) throw new Error(`${name}: anchor not found: ${JSON.stringify(from.slice(0, 60))}`);
      if (mutated.indexOf(from, at + 1) !== -1) {
        throw new Error(`${name}: anchor is not unique: ${JSON.stringify(from.slice(0, 60))}`);
      }
      mutated = mutated.slice(0, at) + to + mutated.slice(at + from.length);
    }
    fs.writeFileSync(MAIN, mutated);
    const syntax = spawnSync(process.execPath, ["--check", "main.js"], { cwd: DESKTOP, encoding: "utf8" });
    const green = run();
    restoreFile();
    const ok = !green && syntax.status === 0;
    if (!ok) failures += 1;
    console.log(`${ok ? "CAUGHT " : "MISSED "} ${name}`
      + `${syntax.status === 0 ? "" : "  [SYNTAX ERROR — mutation invalid: " + syntax.stderr.split("\n")[2] + "]"}`);
  }
} finally {
  restore();
}

const after = crypto.createHash("sha256").update(fs.readFileSync(MAIN)).digest("hex").toUpperCase();
console.log(`restored main.js SHA-256 ${after} — ${after === BASE_HASH ? "BYTE-IDENTICAL" : "MISMATCH"}`);
if (after !== BASE_HASH) failures += 1;
console.log(failures === 0 ? "ALL MUTATIONS CAUGHT" : `${failures} PROBLEM(S)`);
process.exit(failures === 0 ? 0 : 1);
