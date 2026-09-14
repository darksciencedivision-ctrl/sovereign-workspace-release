"use strict";
/**
 * Falsification harness for U328 — the SYSTEM→PANE write gate (Phase 19 unit 19.3).
 *
 * `tools/mutation/pane_input_bypass_mutations.js` falsifies the OPERATOR→pane direction. Nothing
 * falsified the other one, which is why the cold audit found `notifyNode` and
 * `runConductorReadiness` typing into panes blind and no test went red. This is that harness.
 *
 * It splices each known bypass into the two files that carry the property — the gate itself
 * (`apps/desktop/control/pane-writer.js`, graded by its behavioural suite) and the call sites
 * (`apps/desktop/main.js`, graded by the wiring suite) — and requires the graded suite to go RED for
 * every one. A guard that has never been shown to fail is not a guard, and a source-shape assertion
 * that has never been shown to fail is worth even less.
 *
 * Run from the repo root: `node tools/mutation/system_pane_write_mutations.js`
 * (or `npm run test:falsify:panewrite` from `apps/desktop`).
 *
 * It writes to product files, so the originals are held in memory and restored from a `finally` and
 * from the signal/exception paths too — an interrupted run must not leave a bypass on disk. It
 * shares `.mutation.lock` with the `pane:input` harness because both mutate `main.js`, so the two
 * can never read each other's mutated bytes as a baseline.
 *
 * This file itself lives OUTSIDE every declared product path (the receipt's `source.product_paths`),
 * deliberately, so that running it changes nothing a packaged receipt covers — the same rule the
 * `pane:input` harness states, restated here because the round-2 gate-validator read the field name
 * and reasonably expected the harnesses to be inside it ([[U403]]).
 */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..", "..");
const DESKTOP = path.join(ROOT, "apps", "desktop");
const LOCK = path.join(__dirname, ".mutation.lock");

const WRITER = "apps/desktop/control/pane-writer.js";
const MAIN = "apps/desktop/main.js";
const CONDUCTOR_READINESS = "apps/desktop/control/conductor-readiness.js";
/** Unit 19.4 (U329) moved the readiness state machine out of `main.js`; two of this harness's
 *  mutations moved with it. `tools/mutation/readiness_signal_mutations.js` owns that module's OWN
 *  property (the order of its signals); these two stay here because they are U328's property. */
const READINESS = "apps/desktop/control/worker-readiness.js";
/** 19.4-followon round 2. The affordance families the gate's second half judges on live here, and
 *  until the round-2 gate-validator mutated them this file was on the invariant-1 decision path with
 *  no pin and no mutation of its own — the harness pinned the three files above and named this one's
 *  change in prose (see the twelfth re-pin note) without grading it. Its MAJOR-1 is P23/P24. */
const AFFORDANCE = "apps/desktop/control/modal-affordance.js";

/**
 * The trees these mutations were read against and shown to be caught on. Same contract as the
 * `pane:input` harness: a run that adopts whatever is on disk as its baseline would restore a
 * bypass faithfully and print success over it. Update deliberately, after re-reading the mutations
 * against the new bytes — the pin is a claim, not bookkeeping.
 *
 * Re-pinned at 19.3's close, for two reasons. `main.js` gained the `system-pane-write` self-check
 * branch and the two ctx bindings that hand the in-Electron receipt the PRODUCTION write path — no
 * mutation anchors on that dispatch and the three `manager.write(` sites are unchanged. And
 * `pane-writer.js`'s own-echo exclusion was REPAIRED after that receipt falsified it on the first
 * real ConPTY it met (U360), which moved P8's anchor and added P10 and P11 for the two halves of the
 * repair. Re-pinned once more at the round-1 review remediation (the honest header, the observable
 * regex fallback, the `residue_possible` shape) with **P12** added — the bypass the gate-validator
 * demonstrated surviving all 866 desktop tests, because every behavioural test happened to run with
 * a known provider.
 *
 * Re-pinned at the U364 echo-settle wait (`5ec4213`), which added P13 and P14 and moved the writer's
 * bytes; both were re-read against them and re-run CAUGHT.
 *
 * Re-pinned a fourth time at the ROUND-2 review remediation, which is the one worth reading: both
 * reviewers found that this harness's own U364 pair was ungraded (P13 CAUGHT by an unrelated
 * read-index shift, `echoIsWhole` replaceable by `return true` with every suite green), because the
 * fixture grading them never built the scenario it was named for. The repair is a fixture, not a
 * patch — the product code was correct throughout — plus **P15** (the predicate), **P16** (the
 * pre-body call's `null` argument, the fail-open direction of the U360 repair), **P17** (fail-closed
 * on an unreadable screen at the SUBMIT key, pinned before the body and nowhere after it) and
 * **M7** (a fourth PTY write site spelled `manager?.write(`, which the old counter could not see).
 * The ONLY product change in that remediation is a fallback logger on `pane-writer.js`'s
 * echo-completeness path, so **`main.js`'s pin did not move at that point**: a first attempt also
 * rewrote the two settle-interval constants to parse rather than coerce their env overrides, and
 * that was reverted — it is real (`Number("x")` is NaN, `setTimeout(NaN)` is 0 ms, and U364's wait
 * counts polls of that interval) but it is a behaviour change on the decision path, which is exactly
 * what a round-2 remediation may not smuggle in. It was carried as an OPEN register row (U371).
 * All 24 were re-read against the new bytes and re-run CAUGHT, restores byte-identical.
 *
 * **Re-pinned a fifth time at Phase 19 unit 19.4.** Three of the sentences above are now historical
 * and are kept rather than rewritten, because the register is not the only append-only thing here:
 * `main.js`'s pin DID move (the readiness state machine left it for `control/worker-readiness.js`),
 * U371 is CLOSED by that unit rather than carried, and `[READINESS]` moved twice — once for the
 * extraction, once for the 19.4 gate-review remediation that stopped the U328 gate's whole-buffer
 * refusal from becoming a worker's provider state (U373). M4/M6 were re-read against the new bytes:
 * both still anchor on the pre-write gate consultation, which the remediation kept and merely
 * stopped over-interpreting.
 *
 * **Re-pinned a sixth time at 19.4's close**, for `main.js` only and for one added self-check ctx
 * binding: `setWorkerOperationalState`, the production operational-state writer the in-Electron
 * readiness-run legs drive. Those bytes are inside the SHELL_SELFCHECK ctx literal — no new
 * `manager.write(` site, no change to `writePanePrompt`, `notifyNode` or the gate consultation
 * M1–M7 anchor on. Every `main.js` anchor was re-read against the new bytes and re-run CAUGHT.
 *
 * **And a seventh time, same close**, for `[READINESS]`: the round-2 review's BLOCKING finding put a
 * live launch-record read at the top of the withheld-write loop, gave the turn's structured failure
 * a live re-read before it reports a process, and gave a refused delivery its own `decided_by`.
 * M4/M6 anchor on the pre-write gate consultation — which that remediation keeps, and only stops
 * mis-reporting — and M8 anchors on the `writeRefusal` binding, which is unchanged. Both re-read
 * against the new bytes and re-run CAUGHT.
 *
 * **An eighth time, at 19.4's round-4 remediation**, for `[READINESS]` only: the round-4
 * gate-validator's MAJOR (U392) added a module-level `challengeStamp` above `readinessChallenge`,
 * swapped what the call site hands it, and exported it. M4 anchors on `io.writeRefusal(record.paneId)`
 * and M6 on that line together with the `challenge.prompt` write — neither byte moved, and no write
 * site was added or removed. Both re-read against the new bytes and re-run CAUGHT, restores
 * byte-identical.
 *
 * **A ninth time, same round**, for BOTH `main.js` and `[READINESS]`: the round-4 spec-auditor's
 * MAJOR (U393) required four comments to stop asserting an absolute the code does not have, and its
 * MINOR-4 required `main.js`'s self-check ctx comment to count each check-owned binding once. Every
 * byte moved is a comment; no statement, no `manager.write(` site and no gate consultation moved.
 * All anchors re-read against the new bytes and re-run CAUGHT.
 *
 * **A tenth time, at 19.4-followon**, and this one is a PROPERTY change rather than a re-read: the
 * gate's own screen read is now the shell's bounded window (U373's residual) and its verdict covers
 * the affordance families the 19.3 validator walked through it (U363's half). Every existing anchor
 * was re-read against the new bytes — P1-P17 anchor inside `refusalOn`, `echoIsWhole`, `writePrompt`
 * and `withoutOwnEcho`, none of which changed shape; M5's anchor is the `main.js` binding itself and
 * MOVED, so it is re-stated on the new binding and its replacement still spells the always-legible
 * reader the wiring suite refuses. **P18 and P19 are new**, and they are this unit's own graders:
 * the bounded read widened back to whatever it is handed, and the affordance verdict deleted.
 *
 * **An eleventh time, at that unit's round-1 review**, which is where **P20, P21 and P22** come
 * from: the gate-validator wrote eight mutations of its own and FIVE survived all 939 tests. Three
 * are here (the gate's window narrowed below the one it is supposed to SHARE; the affordance judged
 * on the last 200 characters only; the refusal's `state` changed to a value that is not what
 * happened); the fourth — screen ORDER, which turns one of the ten permission screens from refused
 * into written-into — is R26 in the readiness harness, where `lastLines` lives. The fifth
 * (`answerable !== true` vs `=== false`) is an equivalent mutant against the production window and
 * is recorded rather than graded. The same review raised `TAIL_LINES` 24 → 80, which moved
 * `[READINESS]` and `[WRITER]` again; every anchor was re-read against those bytes and re-run
 * CAUGHT. Intermediate pins: `[WRITER]` 617A04BE…3D18F8A9, `[READINESS]` F70F2800…D558E0FB.
 *
 * **A twelfth time, at the same unit's round-1 SPEC-AUDIT**, for comment bytes only in both files
 * (its MAJOR-1 and MEDIUMs 3/4/10: a header sentence that still said this gate reads the whole
 * buffer, a cost paragraph priced in 256 KB snapshots, a window description that omitted the byte
 * budget, and a rule whose stated reason had retired) plus the affordance excerpt collapsing
 * whitespace before it reaches a log line. No anchor moved: P21's anchor is the `modalAffordance(`
 * call, P22's is the `modalRefusal` head, P18/P20's are `paneScreenFromWindow`'s body and signature.
 * All re-read and re-run CAUGHT. Intermediate pins: `[WRITER]` BA977425…BCFCD936, `[READINESS]`
 * B4F57BD7…DAE0FD28.
 *
 * **A thirteenth time, at the same unit's round-2 GATE-VALIDATOR**, which read the sentence above —
 * "plus the affordance excerpt collapsing whitespace before it reaches a log line" — noticed that
 * naming a behaviour change in a re-pin note is not grading it, deleted the collapse, and watched
 * all 942 desktop tests stay green. It was the only behaviour change in that remediation and it was
 * on the invariant-1 path. `[AFFORDANCE]` is pinned from this run and P23/P24 grade both directions
 * of the loss (the excerpt un-collapsed, and the newline surviving a space-only collapse). The
 * lesson is this harness's own, one level up: a re-pin note that describes a change is a claim about
 * bytes, and a claim is not a guard.
 *
 * The same round-2 remediation moved `[WRITER]` and `[READINESS]` again, for COMMENT bytes only
 * (both reviewers' record-accuracy findings: the cost paragraph's first clause still priced a 256 KB
 * snapshot; the `TAIL_LINES` note claimed an unmeasured "maximized pane on this host" and omitted the
 * byte half the validator measured at the SPAWN DEFAULT, [[U400]]; the call-site paragraph named only
 * the narrowing half of what changed under the conductor promotion, [[U401]]; an orphaned JSDoc sat
 * above the wrong symbol). No anchor moved — every `find` string was re-read against the new bytes
 * and every mutation re-run CAUGHT.
 *
 * **A fourteenth time, at W-02 (R-02, SOW remediation programme).** `pane-writer.js` gained a body
 * FLATTENER at the write boundary: CR/LF collapse plus an escape-run and C0 strip, applied once in
 * `writePrompt` before the first byte reaches the PTY. Three anchors moved with it and were re-read
 * against the new bytes rather than merely re-hashed — P4, P13 and P17 all spell
 * `refusalOn(paneId, prompt)` inside `writePrompt`, which is now `body`, the bytes the pane actually
 * received. P16 keeps `prompt` in its REPLACEMENT deliberately: it injects the not-yet-written body
 * into the pre-body check, which is still the fail-open it was written to grade.
 *
 * **P25 and P26 are new**, and they exist because this file's thirteenth note is about precisely the
 * failure they prevent: a behaviour change on the invariant-1 decision path, described in a re-pin
 * note and not graded, deleted later with every test still green. The flattening is such a change,
 * so it is mutated in both halves rather than narrated.
 */
const PINS = {
  [WRITER]: "A517069E12D923605A34A76225D9E44F6359B4207275C9D9F2AA706D64560A07",
  // Re-pinned at 19.4's U385 fix. `main.js`: comment only (U386(f)) — no statement moved, and M7's
  // anchor (`if (!await writePanePrompt(conductorPaneId, prompt)) {`) is still present exactly once.
  // `worker-readiness.js`: the readiness CHALLENGE replaced the quoted token, so M6's anchor moved
  // with the write it guards (`challenge.prompt` rather than `readinessPrompt(...)`) and is restated
  // above; M4's anchor is untouched. Both re-run on the new bytes: CAUGHT, restore BYTE-IDENTICAL.
  // Re-pinned at 19.6 ([[U331]]). `main.js` changed by TWO edits on paths these
  // mutations do not touch: the conductor-readiness vendor pin became a `conductorAdmission`
  // call, and the pane provider resolver was hoisted to a const so the in-Electron descriptor
  // check can be handed the SAME function the write path uses. Every `find` string was re-read
  // against the new bytes and every mutation re-run CAUGHT, restoring byte-identically.
  // Re-pinned at 19.8 (U337/U437(e)). `main.js` gained self-check/readiness observation wiring and
  // `worker-readiness.js` replaced success literals with observer-derived evidence. No pane-write
  // gate, bounded-window, challenge, or writer statement mutated by M1-M8 moved; all re-run CAUGHT.
  // Re-pinned at 19.9: conductor readiness moved to the module pinned below; main.js keeps only
  // injected shell bindings. M1/M2/M5/M8 and the raw-write-site M7 remain on those bindings.
  // Re-pinned at 19.10 for descriptor agreement and honest unprobed model capability. Neither
  // change touches a pane-write binding; M1/M2/M5/M7/M8 are re-run against these bytes.
  // Re-pinned at W-18a with **P27** added: main.js had NO handler for either process-level
  // fault, so one missed `.catch()` exited the process on Node >= 15 without running the
  // cooperative `before-quit` teardown -- orphaning every provider CLI, each holding a durable
  // terminal whose holder_pid is the shell that just died skipping its release. M1/M2/M5/M7/M8
  // were re-read against the new bytes; none anchors on the teardown or the quit path.
  // Re-pinned at W-29 (Tier 3). `main.js` changed by THREE edits, all at the pane-CREATION boundary
  // and none on a write path: `sanitizeRendererSpec` became an allow-list driven by a new frozen
  // `RENDERER_SPEC_ALLOWED_KEYS`, the `pane:new` handler now supplies a scrubbed env, and the
  // `launch-source` require line gained `scrubCredentialEnv`. Every `main.js` anchor this file
  // splices against was re-read against the new bytes and re-counted as present exactly once --
  // M1/M2/M5/M8's writer bindings, M7's `createConductorReadiness` site and P27's fault handlers all
  // sit far from the edited region, and none of the three edits adds or removes a PTY write site.
  // P28/P29 are new and are this unit's own graders.
  // Re-pinned again at W-30, same tier: `main.js` gained a `navigationIsPermitted` predicate
  // immediately BEFORE `function makeWindow() {` and a `setWindowOpenHandler` + `will-navigate`
  // pair immediately before `win.loadFile(`. `function makeWindow() {` is an anchor
  // (pane_input_bypass's AFTER_RESUME) and was re-counted as present exactly ONCE after the
  // insertion -- text was added before it, not a second copy of it. No write path, no readiness
  // path and no PTY write site is touched. P30/P31 are new. Previous pins:
  // B7E081E3...E6CFDA3A, then 4A047A48...2A4FD325.
  // Re-pinned a third time at W-32: the conductor launch path gained its missing ticket-name
  // leftover guard, the classifier stage and the stage-4 assertion. All three are inside
  // `launchConductor`; M1/M2/M5/M8's writer bindings, M7's `createConductorReadiness` site and
  // P27's fault handlers are untouched, and no PTY write site is added or removed. Every anchor
  // re-read and re-run CAUGHT. Previous pin: 6C98BF6B...54012983.
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
  // layout-reconstruct require gained resumePaneSeq, and did-finish-load now seeds
  // paneSeq above every id the persisted recovery snapshot holds, immediately after
  // the structural conductor mint. No write path, disarm sink, readiness path or PTY
  // write site moved. Anchors re-read on the new bytes; re-run CAUGHT, restores
  // byte-identical. Previous pin: DA9C7CA3...859F4.
  //
  // Re-pinned after a MEASURED PERIOD OF SILENCE, which is the part worth recording. The previous
  // pin (526FBA8C) was the byte state at the import commit `cf50cde`, and `main.js` has since
  // moved in EIGHT commits: bf855e7 (admission-before-spawn), e2e8e55 (CP-M1 reconcile), 1397a14
  // (visible terminal cap), 39079f6 (agnostic Conductor seat), 029177e (receipts leave the tracked
  // tree), ddcb87b (EPC-01 distribution blockers), 30ca496 (delegation wiring) and 570a642 (the
  // operator objective reaching live worker panes). From the first of those onward this suite did
  // not run at all: it fail-closes on a hash mismatch and exits 3, and it is NOT part of
  // `npm test`, so nothing reported that a mutation proof had stopped being taken. The
  // fail-closed refusal did its job; what was missing was anyone re-pinning it.
  //
  // Re-read against the new bytes before this pin: every mutation in this file is re-run below and
  // every one is CAUGHT, each pinned file restoring BYTE-IDENTICAL — so no `find` anchor has been
  // orphaned by those eight commits, and no guard mutated here has stopped catching its defect. A
  // mutation whose anchor HAD gone stale would announce itself the way U179 does in
  // `disarm_authority_mutations.js`: "its anchor matched 0 times".
  // Re-pinned at SW-ORCH-001 F-21 (operator-authorized 2026-09-05): two field-name
  // corrections inside `runObjective` (the {ok,feed} wrapper unwrap and rec.nodeId). Both
  // are downstream of authenticated app delivery and touch no system-pane write path, no
  // modal gate and no anchor this harness splices against. Re-run against these exact
  // bytes below: all mutations CAUGHT, restore BYTE-IDENTICAL.
// Re-pinned for SW-JOURNAL-001 v1.2 F-28. Conversational delivery supplies a bounded store
// view through the existing guarded deliverConductorChat writer, with model attribution and
// a transcript notice. The response deadline binding is mutable because the existing loop
// extends it. No new PTY implementation, IPC channel or release call was added, so these
// edits cannot enter pane:input or any authority-release sink. Zero CR bytes; splice anchors
// re-counted: IN_HANDLER x1, HANDLER_TOP x1, makeWindow x1, resume-input CALL x1 (raw signature
// x2 including its declaration, unchanged from preimage), REAL_DISARM x1, residue name x4.
// Both harnesses must be re-run on these exact bytes; the pin alone asserts no outcome.
// Re-pinned for SW-JOURNAL-002 v1.1 F-32/F-35/F-36. runObjective now starts a new journal
// session on options.new_session, records the plan as conductor reasoning, and selects
// recipients from live worker panes rather than feed.assignments. Conversational delivery
// still uses retrieveAndDeliver + deliverConductorChat. No new PTY implementation, IPC
// channel or release call was added, so these edits cannot enter pane:input or any
// authority-release sink. Zero CR bytes; splice anchors re-counted: IN_HANDLER x1,
// HANDLER_TOP x1, makeWindow x1, resume-input CALL x1 (raw signature x2 including its
// declaration, unchanged from preimage), REAL_DISARM x1, residue name x4.
// Both harnesses must be re-run on these exact bytes; the pin alone asserts no outcome.
// Re-pinned for SW-JOURNAL-002-A1, narrowed to F-37/F-38. main.js now shares the
// measured roster/view accompaniment between typed and classified voice chat, retains each
// turn's view notice, and counts returned observed answers for the session roster. Delegation
// arguments/results and journal writers are unchanged. Chat still calls the existing guarded
// deliverConductorChat; no new PTY write, pane:input edge, or authority-release sink is added.
// Re-counted the actual anchor constants (each x1), residue name x4, and all splice sequences;
// verified zero CR bytes. Both harnesses must be run on these bytes with byte-identical restores.
  // Re-pinned for SW-CONDUCTOR-001. main.js gained objective addressing at the
  // selectObjectiveRecipients call site and conductor-bridge attach/detach around
  // launchConductorSession. Writes still go through writePanePrompt / paneWriteRefusalFor;
  // no new manager.write site, no new IPC, no modal-gate change. pane-writer.js,
  // conductor-readiness.js, worker-readiness.js and modal-affordance.js are unchanged.
  // Re-counted resume-input CALL x1 (bare signature x2); zero CR bytes. Both harnesses
  // must be run on these bytes with byte-identical restores.
  // Re-pinned at the 2026-09-14 release closeout. main.js changed in three committed remediation
  // packages after 8AB5E8BB (405eba1): F-128 (3b59c43) moved the G26 operator-text driver into
  // control/operator-text-driver.js; F-129/F-130 (50b3d28) passed the conductor pane id to
  // paneEmittedSince in handleOperatorText and made SHELL-LIVE-READY truthful; F-131 (cd3f559) moved
  // the recovery, approvals, capture and store paths out of the install tree into the state root.
  // None edits the pane:input handler, handleOperatorResumeInput, the before-input-event disarm,
  // makeWindow, clearConductorInputResidue or the pane:focus/maximize/resize/close handlers X1-X4
  // target; the diff was re-read against every anchor and main.js carries zero CR bytes (U274). The
  // pin was accepted only after this harness and pane_input_bypass_mutations.js were re-run on these
  // exact bytes with every mutation CAUGHT and every restore BYTE-IDENTICAL. Previous pin: C43A91A2...E31010B. M7's anchor is untouched.
  [MAIN]: "AF410B21D6E341A96A3F9AD7E18AA5BFE685CC0092024C41850E8C2BCCB65EDA",
  // Added at 19.9 with M3. Its suite drives a modal refusal and proves zero prompt writes,
  // replacing the old circular source-order assertion over main.js.
  [CONDUCTOR_READINESS]: "B264243DF664E5DD75EA4B582B51C386E973EF84FA9A80E4FDEC623F3EA21D49",
  // `worker-readiness.js` and `pane-writer.js` moved for ONE statement each: the readiness-turn
  // count and the submit-confirm decision are read from the declared provider traits
  // (`control/provider-traits.js`) instead of `provider === "<vendor>"` ([[U386]](c),
  // [[U393]] MINOR-1). M4/M6 and P1-P8's anchors are untouched; all re-run CAUGHT.
  // Re-pinned at 19.10 after only the final-turn failure label was generalized beyond two turns.
  // M4/M6 and the readiness mutation harness retain their executable anchors and are re-run.
  [READINESS]: "494E01FBF6881F1EA4E840A73EBCC78FE061F96D0D3ED85459CBDA47EE878037",
  // Pinned for the first time at 19.4-followon round 2 ([[U398]]). Its own bytes then moved once more
  // in the same remediation, for the header sentence recording [[U404]] and a re-wrap; the P23/P24
  // anchor (the `text:` line) is untouched and both were re-run CAUGHT against these bytes.
  [AFFORDANCE]: "3F0E3CBBFD821A1C83CEE784BDFDF06F17831EC73C64213ED1ED1423E65F56EA",
};

const WRITER_SUITE = ["--test", "test/pane-writer.test.js"];
const WIRING_SUITE = ["--test", "test/system-pane-write-wiring.test.js"];
const READINESS_SUITE = ["--test", "test/worker-readiness.test.js"];
const CONDUCTOR_READINESS_SUITE = ["--test", "test/conductor-readiness.test.js"];
// W-29's own grader. A row must be graded by a suite that can actually SEE its defect: the wiring
// suite above knows nothing about pane creation, so grading P28/P29 with it would report MISSED for
// an unrelated reason and read as a hole in the guard rather than a mis-aimed row.
const ALLOWLIST_SUITE = ["--test", "test/renderer-spec-allowlist.test.js"];
const NAVIGATION_SUITE = ["--test", "test/window-navigation-guard.test.js"];

/** [id, file, gradedBy, description, ...[find, replace] edits] */
const MUTATIONS = [
  // ---- the gate itself ------------------------------------------------------------------------
  ["P1", WRITER, WRITER_SUITE, "the gate never refuses anything",
    ["  function refusalOn(paneId, ownBody) {\n    const screen = io.paneScreen(paneId);",
      "  function refusalOn(paneId, ownBody) {\n    if (paneId) return null;\n    const screen = io.paneScreen(paneId);"]],
  ["P2", WRITER, WRITER_SUITE, "an unreadable screen is treated as consent",
    ["  if (screenReadable !== true) return { ...UNREADABLE };",
      '  if (screenReadable === "never") return { ...UNREADABLE };']],
  ["P3", WRITER, WRITER_SUITE, "any truthy value opens the gate (fail-open on a non-boolean)",
    ["  if (screenReadable !== true) return { ...UNREADABLE };",
      "  if (!screenReadable) return { ...UNREADABLE };"]],
  ["P4", WRITER, WRITER_SUITE, "only the body is gated — the submit key is not re-checked",
    ["      const now = refusalOn(paneId, body);", "      const now = null;"]],
  ["P5", WRITER, WRITER_SUITE, "the codex confirm Enter escapes the gate",
    ["      const beforeConfirm = await submit();\n      if (beforeConfirm) return beforeConfirm;\n", ""]],
  ["P6", WRITER, WRITER_SUITE, "notifyNode reaches the PTY directly instead of through writePrompt",
    ["    const result = await writePrompt(paneId, prompt);",
      '    const result = { written: io.write(paneId, prompt) && io.write(paneId, "\\r"),\n'
      + "      refused: null, residue_possible: false };"]],
  // Re-anchored at 19.4-followon. P7's subject — "a pane this shell cannot read is reported as
  // legible" — is unchanged; what moved is where that decision lives, from a session-registry lookup
  // in `paneScreenReader` to the bounded window's own failure paths. This is the throwing one; P18
  // takes the unanswerable one, which is the same fail-open with a different cause.
  ["P7", WRITER, WRITER_SUITE, "a window that throws mid-read is reported as a legible empty screen",
    ["    try { read = window.read(paneId, options); } catch { read = null; }",
      '    try { read = window.read(paneId, options); } catch { read = { answerable: true, text: "" }; }']],
  ["P8", WRITER, WRITER_SUITE, "the own-echo exclusion blanks the whole screen before the submit key",
    ["  if (!plainBody) return s;", '  if (!plainBody) return s;\n  return " ";']],
  // U360: the exclusion the in-Electron receipt falsified. Both halves of the repair are mutated —
  // a screen it stops normalising, and a body it stops matching across a wrap — because either one
  // alone restores the defect that shipped: a notice quoting modal text withholding its own Enter.
  ["P10", WRITER, WRITER_SUITE, "the exclusion goes back to exact-substring matching (no wrap tolerance)",
    ['    .map(escapeChar).join("\\\\s*");', '    .map(escapeChar).join("");']],
  ["P11", WRITER, WRITER_SUITE, "the screen is no longer normalised, so colouring hides our own echo",
    ["  const s = plainScreen(text);", '  const s = String(text || "");']],
  // Found by the 19.3 gate-validator, which spliced this in and watched all 866 desktop tests stay
  // green: every behavioural test ran with `provider: "grok_build"`, while `paneProviderResolver`
  // answers null for any pane that is not the conductor and carries no governed chrome — i.e. the
  // common case. The suite now gates a provider-less pane explicitly, and this keeps it that way.
  // Re-anchored at 19.4-followon: the same early return, one line higher, because the verdict gained
  // its affordance half below it (the provider-less pane must still be gated by BOTH halves — the
  // U363 screens in the suite run at `provider: null` for exactly this reason).
  ["P12", WRITER, WRITER_SUITE, "panes with no known provider stop being gated",
    ["  if (screenReadable !== true) return { ...UNREADABLE };\n  const state = classifyProviderScreen(provider, screen);",
      "  if (screenReadable !== true) return { ...UNREADABLE };\n"
      + "  if (provider === null || provider === undefined) return null;\n"
      + "  const state = classifyProviderScreen(provider, screen);"]],
  // U364: the submit-key read can catch the pane mid-render, and a FRAGMENT of our own body is not
  // removable by an exclusion that matches the whole of it. The wait deleted (the race returns), the
  // wait unbounded (a body a provider never echoes hangs the write instead of getting the fail-closed
  // verdict), and — added at round 2 as U367 — the predicate the wait turns on.
  //
  // P13 and P15 were BOTH survivors until round 2, and the reason is worth keeping: the U364 test's
  // fixture truncated its half-rendered echo one character before `classifyProviderScreen` matches,
  // so the screen it called "half-rendered" was clean and the test passed with the whole feature
  // deleted. P13 was graded CAUGHT by an unrelated read-index shift in the codex test. A mutation is
  // only as good as the fixture that grades it, and only a mutation run against a REPAIRED fixture
  // can tell you which of the two you have.
  ["P13", WRITER, WRITER_SUITE, "the echo-settle wait is deleted, so a half-rendered echo refuses itself",
    ["    for (let i = 0; i < ECHO_SETTLE_POLLS; i += 1) {\n"
      + "      if (refusalOn(paneId, body) === null || echoIsWhole(paneId, body)) break;\n"
      + "      await io.sleep(io.pasteSettleMs());\n    }\n", ""]],
  ["P14", WRITER, WRITER_SUITE, "the echo-settle wait loses its bound",
    ["const ECHO_SETTLE_POLLS = 8;", "const ECHO_SETTLE_POLLS = 100000;"]],
  ["P15", WRITER, WRITER_SUITE, "echoIsWhole always says the echo is complete, so the wait never waits",
    ["  function echoIsWhole(paneId, body) {\n    const screen = io.paneScreen(paneId);",
      "  function echoIsWhole(paneId, body) {\n    if (paneId) return true;\n    const screen = io.paneScreen(paneId);"]],
  // The OPPOSITE direction — echoIsWhole never answering true — is deliberately NOT mutated, and the
  // reason is a claim about the code rather than an omission: the loop breaks on `refusal === null ||
  // echoIsWhole(...)`, so a permanently-false predicate changes only how much of the bound a REFUSED
  // write spends before it refuses. Pinning it would pin latency and report it as safety.
  //
  // That claim had ONE dependency and this note said so in the future tense: the verdicts coincided
  // only because the signal was a whole-buffer `buffer.snapshot()` (U329), which is append-only — so
  // within the settle window a refusal was MONOTONE, and a later read could not turn a refusing
  // screen clean by losing text. **19.4-followon removed that dependency**: the gate now reads a
  // bounded tail, which CAN drop a modal out of view, at which point a permanently-false predicate
  // lets the loop poll on to a clean read and DELIVER where the real predicate would have broken
  // early and withheld. The condition this note set has therefore FIRED, and it is not graded here:
  // the mutation needs a fixture in which the modal leaves the window DURING the settle wait, which
  // is a test this unit did not write. Recorded as [[U397]] with an owner rather than left in the
  // future tense — the round-1 spec-auditor of 19.4-followon found the stale tense, and a harness
  // that states an obligation and then does not notice its own trigger is the U367 class again.
  //
  // The pre-body call's `null` argument, added at round 2: passing the prompt there would apply
  // U360's tolerant exclusion to a screen we have not written into yet, erasing a modal whose words
  // our own body contains BEFORE the first byte goes out. That is the fail-OPEN direction of the
  // U360 repair and nothing graded it.
  ["P16", WRITER, WRITER_SUITE, "the pre-body check excludes the body it has not written yet",
    ["    const before = refusalOn(paneId, null);", "    const before = refusalOn(paneId, prompt);"]],
  // Fail-closed-on-unreadable was pinned before the body (P2, P3, P7) and nowhere after it. A pane
  // whose buffer starts throwing between the body and the Enter is exactly the pane the Enter must
  // not reach.
  ["P17", WRITER, WRITER_SUITE, "a submit-time UNREADABLE refusal is downgraded and the Enter goes out",
    ["      const now = refusalOn(paneId, body);\n      if (now) {",
      "      const now = refusalOn(paneId, body);\n"
      + '      if (now && now.terminal_state !== "PANE_SCREEN_UNREADABLE") {']],
  // ---- W-02 / R-02: the body flattening, graded in both of its halves --------------------------
  // `taskPrompt` and the debate prompt interpolate `task.objective`, `constraints` and
  // `debate.proposition` verbatim, so an embedded CR SUBMITS the fragment before it and lets the
  // model that wrote the body answer the victim provider's own permission modal. The gate above
  // cannot see this: it classifies the SCREEN, and this is the BODY. P25 deletes the flattening
  // outright; P26 deletes only the CR/LF half, which is the plausible partial "fix" — an escape
  // strip alone leaves the keystroke that actually answers the modal.
  ["P25", WRITER, WRITER_SUITE, "the model-authored body reaches the PTY unflattened",
    ["    const body = flattenBody(prompt);", "    const body = prompt;"]],
  ["P26", WRITER, WRITER_SUITE, "only the escape runs are stripped, so an embedded CR still submits",
    ['    .replace(/[\\r\\n]+/g, " ")\n', ""]],
  // The opposite partial — deleting `.replace(ESCAPE_SEQUENCE, "")` and keeping the rest — is
  // deliberately NOT graded, and the reason is a claim about the code rather than an omission:
  // `RESIDUAL_CONTROLS` covers \u000e-\u001f, so ESC (0x1b) is still removed and no control
  // sequence reaches the PTY. What survives is the sequence's PAYLOAD as inert visible text
  // ("[2J"), which is a legibility defect and not the invariant-1 property this harness grades.
  // Pinning it would pin cosmetics and report it as safety.
  ["P9", WRITER, WRITER_SUITE, "the conductor node is routed to the conductor pane unconditionally",
    ["    const paneId = conductor && conductor.nodeId === nodeId\n      ? conductor.paneId : io.workerPaneFor(nodeId);",
      "    const paneId = conductor ? conductor.paneId : io.workerPaneFor(nodeId);"]],

  // ---- the call sites: main.js must still GO through the gate ------------------------------------
  ["M1", MAIN, WIRING_SUITE, "writePanePrompt reaches the PTY itself again (the audited shape)",
    ["  return (await paneWriter.writePrompt(paneId, prompt)).written;",
      "  if (!manager.write(paneId, prompt)) return false;\n"
      + "  await new Promise((resolve) => setTimeout(resolve, PROVIDER_PASTE_SETTLE_MS));\n"
      + '  return manager.write(paneId, "\\r");']],
  ["M2", MAIN, WIRING_SUITE, "notifyNode resolves its own pane and writes around the writer",
    ["  return paneWriter.notifyNode(nodeId, prompt);",
      "  const rec = workerRecordFor({ node_id: nodeId });\n"
      + "  return rec ? { node_id: nodeId, pane_id: rec.paneId,\n"
      + "    written: await writePanePrompt(rec.paneId, prompt) }\n"
      + "    : { node_id: nodeId, pane_id: null, written: false };"]],
  // Moved at 19.9 with the conductor state machine. This deletes the pre-check in the require-able
  // module, and the behavioral suite must observe a prompt write on the modal leg.
  ["M3", CONDUCTOR_READINESS, CONDUCTOR_READINESS_SUITE,
    "the conductor readiness prompt drops its pre-check",
    ["      const refusal = io.writeRefusal(io.paneId());\n"
      + "      if (refusal) {\n"
      + "        launch = { ...io.launch(), operationalState: refusal.state,\n"
      + "          reason: `conductor readiness withheld: ${refusal.reason}` };\n"
      + "        io.setLaunch(launch);\n"
      + "        io.push();\n"
      + "        return { ready: false, state: refusal.state, reason: launch.reason };\n"
      + "      }\n", ""]],
  // M4/M6 follow the rule into the module unit 19.4 moved it to (`control/worker-readiness.js`,
  // U329) and are graded BEHAVIOURALLY there — the readiness turn's pre-check is no longer a source
  // ordering in main.js but a state machine a test can drive, so these two now assert that a refused
  // pane receives NO BYTES rather than that two lines appear in a particular order. Same property,
  // stronger grading. What stays in main.js is the binding, and M8 mutates that.
  // Re-anchored at 19.4's gate-review remediation: the pre-check is now a WAIT (a refusal that
  // clears lets the same turn continue), and its answer no longer becomes the worker's state — but
  // it is still consulted before a single byte is typed, which is U328's property and this pair's.
  ["M4", READINESS, READINESS_SUITE, "the worker readiness turn drops its pre-check",
    ["      const refusal = io.writeRefusal(record.paneId);\n",
      "      const refusal = null;\n"]],
  ["M8", MAIN, WIRING_SUITE, "readiness is handed its own screen read instead of the production gate",
    ["  writeRefusal: (paneId) => paneWriteRefusalFor(paneId),", "  writeRefusal: () => null,"]],
  ["M5", MAIN, WIRING_SUITE, "the io claims every pane is legible (an inline reader main.js owns)",
    ["  paneScreen: paneScreenFromWindow(readinessWindow),",
      "  paneScreen: (paneId) => ({ readable: true,\n"
      + '    text: manager && manager.registry.has(paneId) ? manager.registry.get(paneId).buffer.snapshot() : "" }),']],
  // Round 2: the write-site counter matched the literal `manager.write(`, so a fourth site spelled
  // with optional chaining kept the count at three and left the wiring suite green — demonstrated by
  // the gate-validator. This is that bypass, and the counter now matches the identifier rather than
  // one spelling of it.
  //
  // The anchor is deliberately OUTSIDE `writePanePrompt` and `notifyNode`. Placed inside either, the
  // mutation is also caught by that function's own `doesNotMatch` guard, so it would grade "some
  // assertion in the wiring suite saw it" rather than "the counter saw it" — U367's lesson applied to
  // the mutation written in response to U367. `runConductorReadiness` carries no such guard (its
  // assertions are about ordering), so the counter is the only thing standing between this edit and
  // a green suite.
  // W-18a: the handlers themselves. Deleting them restores exactly the shipped defect -- a fault
  // exit that never reaches the release path -- and the wiring suite's shape assertions are what
  // stand between that edit and a green run.
  ["P27", MAIN, WIRING_SUITE, "the process-level fault handlers are deleted, so a fault strands every terminal",
    ['process.on("unhandledRejection", (reason) => exitOnUnrecoverableFault("unhandledRejection", reason));\n'
      + 'process.on("uncaughtException", (error) => exitOnUnrecoverableFault("uncaughtException", error));\n', ""]],
  ["M7", MAIN, WIRING_SUITE, "a fourth PTY write site, spelled so the old counter could not see it",
    ["const runConductorReadiness = createConductorReadiness({",
      'manager?.write(conductorPaneId, "\\r");\n'
      + "const runConductorReadiness = createConductorReadiness({"]],
  // ---- W-29: the two halves of the renderer-spec boundary ---------------------------------------
  // Two rows because the unit repaired TWO independently revertible properties. One row covering
  // both would go RED on either revert and could not tell them apart -- and the env half is the one
  // a reader is most likely to drop, because removing it looks like a simplification.
  ["P28", MAIN, ALLOWLIST_SUITE, "the renderer spec goes back to pass-through, so `file`/`args` reach pty.spawn",
    ["  for (const key of RENDERER_SPEC_ALLOWED_KEYS) {\n"
      + "    if (key in source) clean[key] = source[key];\n  }",
      "  Object.assign(clean, source);"]],
  ["P29", MAIN, ALLOWLIST_SUITE, "the boundary stops supplying an env, so the sanitiser re-opens the inherit-everything fallback",
    ["{ ...sanitizeRendererSpec(spec), env: scrubCredentialEnv(process.env) }",
      "sanitizeRendererSpec(spec)"]],
  // ---- W-30: the two navigation escapes, graded independently ----------------------------------
  // Separate rows for the same reason as P28/P29: they are two different Electron surfaces, and
  // `window.open` is the one most likely to be deleted as redundant by a reader who sees that the
  // app has no browsing surface -- which is true, and is not what the handler is protecting.
  ["P30", MAIN, NAVIGATION_SUITE, "window.open is allowed again, so a compromised renderer can open a real BrowserWindow",
    ['  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));\n', ""]],
  ["P31", MAIN, NAVIGATION_SUITE, "will-navigate observes the escape instead of cancelling it",
    ["    event.preventDefault();\n", ""]],
  // ---- 19.4-followon: the two halves this unit added -------------------------------------------
  ["P18", WRITER, WRITER_SUITE, "the bounded reader hands on whatever it was given, answerable or not",
    ["    if (!read || read.answerable !== true) {\n"
      + '      return { readable: false, text: "", reason: (read && read.reason) || null };\n'
      + "    }\n"
      + "    return { readable: true, text: read.text };",
      '    return { readable: true, text: (read && read.text) || "" };']],
  ["P19", WRITER, WRITER_SUITE, "the affordance verdict is deleted — an unrecognised modal is consent again",
    ["  const affordance = modalAffordance(plainScreen(screen));\n"
      + "  return affordance ? { ...modalRefusal(affordance) } : null;",
      "  return null;"]],
  // ---- 19.4-followon round 2: the ungraded behaviour change (gate-validator MAJOR-1) -------------
  // Both directions, because the space-only collapse is the plausible "fix" a later reader writes
  // when they decide `\s` was too broad — and it restores the whole defect, since the two-line
  // numbered-menu pattern matches ACROSS the newline and it is the NEWLINE that forges the log line.
  ["P23", AFFORDANCE, WRITER_SUITE, "the provider's excerpt travels into the reason verbatim",
    ['    text: winner.text.replace(/\\s+/g, " ").trim().slice(0, 120),', "    text: winner.text,"]],
  ["P24", AFFORDANCE, WRITER_SUITE, "only spaces are collapsed, so the newline survives into the log line",
    ['    text: winner.text.replace(/\\s+/g, " ").trim().slice(0, 120),',
      '    text: winner.text.replace(/[ \\t]+/g, " ").trim().slice(0, 120),']],
  // ---- the round-1 review's surviving probes, now graded ----------------------------------------
  ["P20", WRITER, WRITER_SUITE, "the gate's window is narrowed below the one it claims to share",
    ["function paneScreenFromWindow(window, options = {}) {",
      "function paneScreenFromWindow(window, options = { maxBytes: 512, maxLines: 4 }) {"]],
  ["P21", WRITER, WRITER_SUITE, "the affordance is judged on the last 200 characters only",
    ["  const affordance = modalAffordance(plainScreen(screen));",
      "  const affordance = modalAffordance(plainScreen(screen).slice(-200));"]],
  ["P22", WRITER, WRITER_SUITE, "the modal refusal reports a state that is not what happened",
    ['const modalRefusal = (affordance) => Object.freeze({\n  state: "PROVIDER_SETUP_REQUIRED",',
      'const modalRefusal = (affordance) => Object.freeze({\n  state: "BUSY",']],
  ["M6", READINESS, READINESS_SUITE, "the readiness pre-check is consulted AFTER the prompt is typed",
    ["      const refusal = io.writeRefusal(record.paneId);\n"
      + "      if (!refusal) {\n"
      + "        wrote = await io.writePrompt(record.paneId, challenge.prompt);\n",
      "      wrote = await io.writePrompt(record.paneId, challenge.prompt);\n"
      + "      const refusal = io.writeRefusal(record.paneId);\n"
      + "      if (!refusal) {\n"]],
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

const runSuite = (args) => spawnSync(process.execPath, args, { cwd: DESKTOP, encoding: "utf8" }).status === 0;

try {
  for (const rel of Object.keys(PINS)) console.log(`base ${rel} SHA-256 ${hash(ORIGINAL[rel])}`);
  for (const suite of [WRITER_SUITE, WIRING_SUITE, READINESS_SUITE]) {
    console.log(`clean tree ${suite[1]}: ${runSuite(suite) ? "GREEN (expected)" : "RED — broken before any mutation"}`);
  }

  for (const [id, rel, suite, what, ...edits] of MUTATIONS) {
    let mutated = ORIGINAL[rel].toString("utf8");
    for (const [from, to] of edits) {
      const at = mutated.indexOf(from);
      if (at === -1) throw new Error(`${id}: anchor not found in ${rel}: ${JSON.stringify(from.slice(0, 70))}`);
      if (mutated.indexOf(from, at + 1) !== -1) {
        throw new Error(`${id}: anchor is not unique in ${rel}: ${JSON.stringify(from.slice(0, 70))}`);
      }
      mutated = mutated.slice(0, at) + to + mutated.slice(at + from.length);
    }
    fs.writeFileSync(abs(rel), mutated);
    const syntax = spawnSync(process.execPath, ["--check", abs(rel)], { cwd: DESKTOP, encoding: "utf8" });
    const green = runSuite(suite);
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
console.log(failures === 0 ? `ALL ${MUTATIONS.length} SYSTEM→PANE MUTATIONS CAUGHT` : `${failures} PROBLEM(S)`);
process.exit(failures === 0 ? 0 : 1);
