"use strict";

/** Mutation-quality checks for the live Sovereign orchestration boundary. */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..", "..");
const LOCK = path.join(__dirname, ".orchestration-mutation.lock");
// Re-pinned at 19.3 (U328). Two pins were STALE and this harness has therefore been exiting 3 —
// unrunnable, and silently so, because nothing in the ordinary suite checks these the way
// `selfcheck-guards` checks the `pane:input` harness. `mcp_server/collaboration_service.py` went
// stale at 19.2 (U326 routed its inline checks through `control_plane/policy.py`) and `main.js` at
// 19.3. O3's anchor moved WITH the rule: the cross-task recipient check now lives at
// `control_plane/policy.py`, so O3 mutates it there — which is the point of the delegation, and a
// mutation still aimed at the vacated line would have proved nothing.
// `main.js` re-pinned once more at 19.3's close (the `system-pane-write` self-check branch and its
// two ctx bindings); O1–O5's anchors were re-read against those bytes and re-run CAUGHT.
// Re-pinned again at 19.4's close for one added self-check ctx binding
// (`setWorkerOperationalState`); O1–O5's anchors sit in the control handlers and the readiness
// state, none of which those bytes touch, and all five were re-read and re-run CAUGHT.
const PINS = {
  // Unit 19.9 (U338): O1/O11 moved with their executable decisions into application-control.js;
  // O12/O14 moved with the operator-facing projection into operational-state.js. Their tests now
  // call those require-able modules behaviorally, so main.js is no longer a circular source pin.
  // Re-pinned at 19.4's U385 fix: main.js changed by ONE COMMENT (U386(f)), no statement moved, and
  // every anchor below re-counted as present exactly once and re-run CAUGHT. Re-pinned again at
  // 19.4-followon: two lines (the write gate's screen reader is bound to the bounded window, U373's
  // residual, and the require line that names it). O1-O5 anchor in the control handlers and the
  // readiness state; none of those bytes moved. All five re-read and re-run CAUGHT.
  // Re-pinned at 19.6 ([[U331]]/[[U425]](b)): main.js replaced the conductor-readiness vendor pin
  // with a `conductorAdmission` call and hoisted the pane provider resolver to a const;
  // collaboration_service.py changed by DOCSTRING bytes only (the abort docstring now scopes the
  // synthesis-gate claim to the tool path that actually provides it). O1-O5's anchors sit in the
  // control handlers, the readiness state and the debate/candidate write paths — none of those
  // bytes moved. All five re-read against the new bytes and re-run CAUGHT.
  // Re-pinned at 19.10 after spawn_worker stopped using a vendor alias/default gate and now
  // consumes an exact available option returned by list_models. O1's governed-launch anchor and
  // O11's assignment-refusal anchor remain unique; both are re-run behaviorally below.
  // Re-pinned at W-01 (R-01, SOW remediation programme): the three notify handlers gained an
  // identifier SHAPE check on the ids they interpolate into a peer's prompt, and a recipient
  // scope drawn from `liveWorkerRecords`/`chromeFor`/`conductorNodeId` (no new io dependency,
  // and deliberately not `fetchOperationalState`, which spawns py -3.12 per notify). O1's
  // governed-launch anchor and O11's assignment-refusal anchor were re-read against the new
  // bytes and did not move; both are re-run below. O15/O16 GRADE the two new constraints.
  // Re-pinned at W-12: the duplicate-worker lookup now keys on provider AND model, matching
  // the picker lookup three lines above it. O1/O11/O15/O16 anchors were re-read against the
  // new bytes and none moved; O17 GRADES the model half.
  "apps/desktop/control/application-control.js": "21DA3C9F1D14DC5F6CE9555822840B8EC71D2011441B962424F33C4173C23213",
  // Re-pinned after this suite had been REFUSING TO RUN, which is the part worth recording.
  // `operational-state.js` moved in exactly one commit since the previous pin — e2e8e55 ("C0
  // suite: reconcile CP-M1 source and assertions"), a two-line ADDITIVE change that adds
  // `created_utc` and `backend` to the operator-facing projection object in
  // `createOperationalState`. No statement moved and no key was removed, so O12's and O14's
  // anchors are untouched; both are re-read against the new bytes and re-run CAUGHT below.
  //
  // From e2e8e55 onward the whole suite exited 3 on the hash mismatch rather than running. That
  // fail-closed refusal is correct — a mutation harness that ran against unverified bytes would
  // be worse — but it is not `npm test`, so nothing surfaced that this proof had stopped being
  // taken for a two-line comment-free edit made many commits ago.
  "apps/desktop/control/operational-state.js": "1AE8E8616448C8D23A9169DBCE357AF945C9F0664EACEE32D06DC9B4621BC059",
  // Re-pinned at 19.7 (U334/U335): `sovereign-control-server.js` gained the bounded `stop()` and the
  // staleness window on `connectionState`; `main.js` gained the assignment gate's binding, the
  // teardown-time gateway stop and the inspector's honest `ok`. O2 anchors on the bearer check
  // (`const identity = this.identityFor(bearer(req));`) — one line, unmoved, still present exactly
  // once — and O1/O3–O5 anchor in the control handlers, the policy module and the write paths, none
  // of which those bytes touch. Every row re-read against the new bytes and re-run CAUGHT. Both
  // pins moved AGAIN inside 19.7's round-1 repair (`sessionEstablished`, the shutdown 503, the
  // status fields, O11's anchor `    if (refusal) {` — which is now load-bearing and is verified
  // unique before the run, as every anchor is).
  // Re-pinned at 19.7's round-3 repairs: the 503-window comment now NAMES the receipt its measured
  // number came from (spec-auditor round 2, MINOR-2). Re-pinned AGAIN at round 4/3, for two more
  // comment corrections in the same file: the receipt count was wrong in the sentence that fixed the
  // attribution, and `stop()`'s doc block still carried the unqualified "never rendered as success"
  // that §3 of the evidence had already scoped (spec-auditor round 3, MEDIUM-1 / MINOR-2).
  // Comment bytes only, both times — verified by the round-4 validator, which stripped every
  // line-comment from both blob versions and got identical non-comment hashes. No statement moved;
  // O2's bearer-check anchor and O7/O8's `stop()` anchors were re-read against the new bytes, each
  // present exactly once, and re-run CAUGHT. `main.js`, `operational-source.js` and
  // `assignment-gate.js` did NOT move for any of these rounds — their pins below are unchanged, and
  // that is the evidence for the claim that no product behaviour changed after round 3.
  // Re-pinned at 19.9 after the no-server result gained the universal waited/timeout shape and the
  // quit verdict began consuming `closed`; O2/O6/O7/O8 remain on the same executable statements.
  // Re-pinned at U458 for W-40 (`8c5422f`), which added the Origin/Host validation and the
  // bind-time allowed-host set to this file and did NOT re-pin here. THE HARNESS HAS BEEN
  // UNRUNNABLE SINCE — it threw on the stale pin before reaching a single row, so every Tier-3 unit
  // after W-40 that believed it had orchestration falsification had none. Recorded at [[U461]].
  // O2/O6/O7/O8 anchor in this file; all four were re-read against the new bytes and are present
  // exactly once, and all four are re-run CAUGHT below. A pin refreshed without re-reading its
  // anchors is worse than a stale one: it reports CAUGHT for rows aimed at lines that moved.
  "apps/desktop/control/sovereign-control-server.js": "63918111F1C9CE7E674E65765646616F6F16BE3FFD8B973FFC6DBACC7ACC1A4A",
  // Re-pinned again inside 19.6, for the spec-audit round-1 repair: a FOURTH site of the
  // unqualified synthesis-gate sentence, in the MODULE comment at the top of this file. Comment
  // bytes only; O3/O4 anchor in executable lines and did not move. Re-run CAUGHT.
  // Re-pinned at 19.10 after synthesis contribution/hash completeness moved inside the task write
  // fence. O4's bounded-debate anchor is unchanged and is re-run against these exact bytes.
  // Re-pinned at W-16: the synthesis binding validation is no longer gated on
  // `contribution_bindings is not None`, so publication-time integrity is enforced by the
  // write fence rather than by caller convention. Rows anchoring in this file were re-read
  // against the new bytes and none moved; the invariant itself is graded by
  // tools/mutation/_op19_5_write_path_mutations.py row W16.
  // Re-pinned at W-05: the operational lifecycle gained a frozen transition table and a
  // terminal COMPLETED with no outbound edges, plus D-5's candidate freeze. O4's anchor was
  // re-read against the new bytes and did not move; the invariants are graded by
  // tools/mutation/_op19_5_write_path_mutations.py rows W05a/W05b.
  // Re-pinned at C-1 (SOW remediation loop v2): W-59 and W-61 edited this file after
  // W-16's last re-pin (the debate gate inside record_synthesis; the budget disclosure
  // at open_debate) and neither re-ran this harness, so it refused before any row
  // ([[U461]]'s class again). All 21 row anchors were re-read against these bytes before
  // re-pinning; each is present exactly once, O4's bounded-debate line did not move, and
  // every row is re-run CAUGHT below.
  "mcp_server/collaboration_service.py": "12B389F5303B8B0DDB72B582C989FC37222FDB104A696A66A44E8EF6467D05A3",
  // Re-pinned at 19.6, and NOT for anything 19.6 did: `control_plane/policy.py` last moved at
  // `44c2abf` (19.5's final spec-audit repair to `authorize_debate_abort`'s docstring) and this
  // harness was not re-run after it, so the pin arrived here stale — a small debt of that
  // unit's last round, recorded rather than quietly overwritten. `git diff 916056e..HEAD --
  // control_plane/policy.py` is docstring bytes only (14 added, 4 removed, all inside one
  // triple-quoted block); O3/O4's anchors are executable lines and did not move. Re-run CAUGHT.
  "control_plane/policy.py": "712CDC071155F7461E76257AAA733A38661744CCE75DA724813FD05005FF1ABC",
  // Re-pinned at W-32: `worker-spawn.js` gained the classifier stage and the stage-4 assertion, and
  // the `augmentSpawnEnv` call MOVED below both — it mints capabilities whose names are
  // classifier-positive, so minting before the scrub would have deleted the capability the launch
  // just granted. O5's anchor is that exact line; it was re-read against the new bytes and is
  // present exactly ONCE, and its meaning is unchanged (it still skips capability injection, just
  // from a later point). No other anchor in this file touches the scrub region. O18/O19 are new and
  // grade the ordering. Previous pin: 515B14FE...97F311D68.
  // Re-pinned for e2e8e55's G22 governed replacement, the one SUBSTANTIVE change among this
  // batch. The "pane must be free" branch no longer refuses every occupied pane outright: an
  // unconfirmed click now takes a NAMED soft refusal (`replacement-requires-confirmation`), and a
  // click carrying `selection.replaceConfirmed === true` tears the prior session down through the
  // injected `endLiveSession` primitive, waits bounded for the record to release, then falls
  // through to a fresh launch. The mutations anchored here (O1's governed-launch site, and the
  // refusal-path graders below) sit on the lease/supervision checks BEFORE that branch and on the
  // refuse() shape itself, neither of which moved; all are re-read against the new bytes and
  // re-run CAUGHT below.
  //
  // Worth recording about e2e8e55: it DID update `pane_input_bypass_mutations.js` in the same
  // commit and did not update this file or `system_pane_write_mutations.js`. That is why
  // `test:falsify` kept passing while these two silently stopped running — the drift was not
  // uniform neglect, it was one mutation harness re-pinned and two forgotten.
  "apps/desktop/picker/worker-spawn.js": "F3B405126424D1A0B55CB3D95E03CCF5FC3CFCDF78218F7432EDED6238A90C55",
  // Added at 19.7 with O6–O11, which mutate them.
  // Re-pinned for ddcb87b (EPC-01), a THREE-LINE substitution and nothing else: the hardcoded
  // `"py"` executable and `["-3.12"]` argument list are now read from the shared
  // `../python-runtime` helper (`defaultPython()` / `defaultPythonArgs()`), so one module decides
  // which interpreter the product spawns. No branch, no ordering and no spawn site moved — the
  // same `spawn(...)` call on the same line receives the same values by a different name. The
  // mutations anchored in this file grade the reader's fail-closed parse, which is downstream of
  // the spawn; both re-read against the new bytes and re-run CAUGHT below.
  "apps/desktop/inspector/operational-source.js": "5CC901D81C9892223D34BF1FE21292B48540E345A2F43875C937F490307663F0",
  // Added at U458 (the W-41 corrective) with O20/O21, which mutate it. This file is one half of a
  // TWO-SIDED protocol: W-41 hardened `control_plane/ipc/envelope.py` and left this mirror signing
  // `payload` alone, so both halves passed their own tests while the channel was dead in both
  // directions. Both rows below are graded by the CROSS-LANGUAGE test deliberately — a grader that
  // only asks the Node side whether it agrees with itself is the exact blindness that let the
  // regression ship.
  "apps/desktop/ipc/envelope.js": "CD6DC13E3DBA234F9084A51C26374C8FA4B78AC122D542169D17EE7F136D67B1",
  // Re-pinned at 19.9 after the duplicated established-state strings were replaced by the shared
  // predicate and the U436 comment was brought up to date; O10 still mutates the stale refusal.
  "apps/desktop/control/assignment-gate.js": "6E75ACD79D79231BA13A533C87C5E957A4948D67FE6600A18F702434F0AECB37",
};

const rows = [
  { id: "O1", what: "conductor bypasses the shared in-app worker launcher",
    file: "apps/desktop/control/application-control.js",
    find: "    const res = await io.spawnFromSelection({ option, role: \"reasoning\", mode: \"attended\", targetPaneId: null });",
    replace: "  const res = { launched: false, error: \"mutated external launch\" };",
    expect: "spawn_worker behaviorally routes through the shared governed launcher and readiness",
    cmd: "node", args: ["--test", "apps/desktop/test/application-control.test.js"] },
  { id: "O2", what: "the application-control bearer check is disabled",
    file: "apps/desktop/control/sovereign-control-server.js",
    find: "    const identity = this.identityFor(bearer(req));",
    replace: "    const identity = this.identityFor(bearer(req)) || { node_id: \"forged\", role: \"conductor\", project_id: \"proj\" };",
    expect: "opaque node credentials bind tool calls to the issued identity",
    cmd: "node",
    args: ["--test", "apps/desktop/test/sovereign-control-server.test.js"] },
  { id: "O3", what: "cross-task recipients are accepted",
    file: "control_plane/policy.py",
    find: "        if not set(recipient_node_ids).issubset(participants):",
    replace: "        if False and not set(recipient_node_ids).issubset(participants):",
    expect: "test_progress_lifecycle_and_cross_task_access_fail_closed",
    cmd: "py", args: ["-3.12", "-m", "pytest", "-q", "tests/remediation/test_orchestration_policy_boundaries.py"] },
  // Re-anchored at 19.6. The round ceiling moved INSIDE the `mutate_operational_debate` fence at
  // 19.5 (`5d56e19`: a rule that reads record CONTENT must be evaluated against the row read in the
  // transaction, not against a snapshot), so it is now `current["max_rounds"]` one indent deeper.
  // The harness was not re-run in that unit and this anchor has been dead since — the reason this
  // re-anchoring is 19.6's work and not a 19.6 change. Same rule, same mutation, still CAUGHT.
  { id: "O4", what: "bounded debate rounds are no longer bounded",
    file: "mcp_server/collaboration_service.py", find: "            if round_no > current[\"max_rounds\"]:",
    replace: "            if False and round_no > current[\"max_rounds\"]:",
    expect: "test_bounded_debate_preserves_evidence_and_dissent",
    cmd: "py", args: ["-3.12", "-m", "pytest", "-q", "tests/remediation/test_orchestration_policy_boundaries.py"] },
  { id: "O5", what: "worker processes lose their node-scoped MCP environment",
    file: "apps/desktop/picker/worker-spawn.js",
    find: "    env = augmentSpawnEnv(env, { ticket, paneId: pid, sessionId, identity });",
    replace: "    env = env; // mutation: skip Sovereign MCP capability injection",
    expect: "the Python-issued worker identity receives node-scoped MCP control env before spawn",
    cmd: "node", args: ["--test", "apps/desktop/test/worker-spawn.test.js"] },
  // ---- 19.7 (U334/U335/U336): each of the three defects, restored, and graded ------------------
  // Written with the unit, because this phase's recurring finding is a guard nothing grades.
  // O6–O10 are the AUDITED behaviour put back — not invented mutations — so a row of those five
  // that survives means the shipped code has returned to what the cold audit found. O11–O14 are a
  // different and weaker claim, and the distinction is kept because it is the difference between
  // "the audit's defect is back" and "a review round's repair is gone": each of those four restores
  // a state that existed only between review rounds of this unit (spec-auditor round 3, MEDIUM-2).
  { id: "O6", what: "any last-seen timestamp counts as a live MCP session again (the U335 defect)",
    file: "apps/desktop/control/sovereign-control-server.js",
    find: "    const fresh = age !== null && age <= this._staleAfterMs;",
    replace: "    const fresh = true; // mutation: silence is evidence of life again",
    expect: "a node's connection state carries the AGE of its evidence and goes stale, not connected",
    cmd: "node", args: ["--test", "apps/desktop/test/sovereign-control-server.test.js"] },
  { id: "O7", what: "a stop() that outlived its budget is reported as a clean close",
    file: "apps/desktop/control/sovereign-control-server.js",
    find: "        closed: false, was_listening: true, forced, timed_out: true,",
    replace: "        closed: true, was_listening: true, forced, timed_out: false,",
    expect: "a socket that survives the destroy still ends the wait, reported as the timeout it was",
    cmd: "node", args: ["--test", "apps/desktop/test/sovereign-control-server.test.js"] },
  { id: "O8", what: "the halfway connection destroy is removed, so a held socket owns the quit path",
    file: "apps/desktop/control/sovereign-control-server.js",
    find: "          if (typeof server.closeAllConnections === \"function\") server.closeAllConnections();",
    replace: "          void server; // mutation: nothing is destroyed, the budget just expires",
    expect: "an open connection is destroyed inside the budget instead of holding the quit path open",
    cmd: "node", args: ["--test", "apps/desktop/test/sovereign-control-server.test.js"] },
  { id: "O9", what: "an unreadable orchestration feed is shaped as an empty one again (the U336 defect)",
    file: "apps/desktop/inspector/operational-source.js",
    find: "      tasks: null, messages: null, debates: null, summary: null, nodes,",
    replace: "      tasks: [], messages: [], debates: [], nodes,\n      summary: { task_count: 0, message_count: 0, debate_count: 0, open_debate_count: 0 },",
    expect: "an unreadable feed carries NO counts",
    cmd: "node", args: ["--test", "apps/desktop/test/operational-source.test.js"] },
  // Relabelled at 19.7's round-1 repair: this row mutates the GATE MODULE only, and its old name
  // ("the U335 half main.js calls") claimed the caller. The caller is O11, which is the row the
  // validator's surviving mutation asked for.
  { id: "O10", what: "the assignment gate stops consulting the node's own MCP evidence",
    file: "apps/desktop/control/assignment-gate.js",
    find: "  if (state === \"stale\") {",
    replace: "  if (false && state === \"stale\") { // mutation: a silent node is task-ready again",
    expect: "a READY pane over a node that has gone silent is REFUSED",
    cmd: "node", args: ["--test", "apps/desktop/test/assignment-gate.test.js"] },
  // The gate-validator's round-1 mutation, verbatim: the gate is still called and its answer still
  // read, but the ONE verdict this unit exists to honour is filtered out at the call site. It
  // survived everything except the whole-file SHA pin — which is re-pinned every unit, so it was
  // one re-pin away from surviving entirely (round 1, MAJOR-2).
  { id: "O11", what: "the application-control caller ignores the assignment gate's MCP verdict",
    file: "apps/desktop/control/application-control.js",
    find: "      if (refusal) {\n        io.log(`control: assignment to ${nodeId} refused",
    replace: "      if (refusal && refusal.code !== \"mcp_unverified\") {\n        io.log(`control: assignment to ${nodeId} refused",
    expect: "assignment preflights every owner before the first pane write",
    cmd: "node", args: ["--test", "apps/desktop/test/application-control.test.js"] },
  // O12/O13 are the gate-validator's round-3 findings turned into rows: both repairs were REACHABLE
  // behaviour and both were graded by nothing but this file's whole-file SHA pin, which every unit
  // re-pins. A pin that is re-pinned is a change detector, not a grader — O11's story, twice more.
  { id: "O12", what: "the operator's dispatch sentence stops naming MCP-unverified workers",
    file: "apps/desktop/control/operational-state.js",
    find: "      + `${unverified ? ` (${unverified} MCP-unverified)` : \"\"}`\n",
    replace: "      // mutation: `N READY` counts unverified sessions silently again\n",
    expect: "U335: the sentence an operator reads names the workers nothing has verified",
    cmd: "node", args: ["--test", "apps/desktop/test/runtime-honesty-wiring.test.js"] },
  { id: "O13", what: "an emitter's own ok/available overwrite the inspector call's verdict again",
    file: "apps/desktop/inspector/operational-source.js",
    find: "    return { ...feed, ok: true, available: true, nodes };",
    replace: "    return { ok: true, available: true, ...feed, nodes }; // mutation: the feed wins",
    expect: "an emitter cannot overwrite the call's verdict about itself",
    cmd: "node", args: ["--test", "apps/desktop/test/operational-source.test.js"] },
  // The round-4 validator's own decoy, verbatim: O12's clause commented out at the END of a live
  // line, which `executableOnly` (whole-line and block comments only) did not see. The pin strips
  // trailing comments now; this row is what keeps that true.
  { id: "O14", what: "the MCP-unverified clause is commented out at the end of a live line",
    file: "apps/desktop/control/operational-state.js",
    find: "      + `${unverified ? ` (${unverified} MCP-unverified)` : \"\"}`\n",
    replace: "      + `${false ? \"\" : \"\"}` // + `${unverified ? ` (${unverified} MCP-unverified)` : \"\"}`\n",
    expect: "U335: the sentence an operator reads names the workers nothing has verified",
    cmd: "node", args: ["--test", "apps/desktop/test/runtime-honesty-wiring.test.js"] },
  // ---- W-01 / R-01: the notify handlers' caller-authored payload ------------------------------
  // `notify_message` is HTTP-reachable and carries no role check BY DESIGN (the MCP server calls it
  // on behalf of the sending node, usually a worker). Both halves of what replaced that missing
  // check are graded here, because a constraint that is only described is the O11 story again.
  { id: "O15", what: "the notify identifiers go back to being interpolated unchecked",
    file: "apps/desktop/control/application-control.js",
    find: "    requireSovereignIds(\"notify_message_identifiers\", {\n      message_id: message.message_id, task_id: message.task_id,\n      sender_node_id: message.sender_node_id,\n    });\n",
    replace: "",
    expect: "a worker cannot author the text that reaches the conductor's pane",
    cmd: "node", args: ["--test", "apps/desktop/test/application-control.test.js"] },
  // ---- W-32: the two-stage scrub, and the ORDERING is what these grade ------------------------
  // Both mutations are collapses a future simplifier would find attractive, and both restore a real
  // bypass. They exist because the ordering is invisible in the code's shape: two scrubbers with a
  // guard between them looks like something that wants tidying, and tidying it is the defect.
  { id: "O18", what: "the classifier is hoisted AHEAD of the ticket leftover guard",
    file: "apps/desktop/picker/worker-spawn.js",
    find: "    let env = scrubEnv(ticket, baseEnv);",
    replace: "    let env = scrubCredentialEnv(scrubEnv(ticket, baseEnv));",
    // `expect` must appear in the FAILING suite's output, not describe it. With the classifier
    // hoisted, the ticket-declared credential is cleaned before the guard looks, the guard finds
    // nothing, and the spawn SUCCEEDS — so the assertion that trips is the refusal that did not
    // happen.
    expect: "a child env carrying a ticket-declared credential must not spawn",
    cmd: "node", args: ["--test", "apps/desktop/test/credential-scrub-stages.test.js"] },
  { id: "O19", what: "the classifier-wide second stage is deleted",
    file: "apps/desktop/picker/worker-spawn.js",
    find: "    env = scrubCredentialEnv(env);\n",
    replace: "",
    // Deleting stage 3 lets the classifier-only family through; no ticket declares NODE_PATH, so
    // stage 1 cannot catch it. STAGE 4 then refuses the launch — defence in depth working — so the
    // assertion that trips is the one about the launch proceeding, not the per-name check. That is
    // the honest grading target: the mutation is caught by the OTHER stage, and this records which.
    expect: "the classifier stage must remove NODE_PATH and family before the child is spawned",
    cmd: "node", args: ["--test", "apps/desktop/test/credential-scrub-stages.test.js"] },
  { id: "O16", what: "notify_message delivers to every recipient the caller names",
    file: "apps/desktop/control/application-control.js",
    find: "    const recipients = scopedRecipients(io, \"notify_message_recipients\",\n      message.recipient_node_ids, message.task_id);",
    replace: "    const recipients = message.recipient_node_ids || [];",
    expect: "a worker cannot deliver to a node outside the notify's own task",
    cmd: "node", args: ["--test", "apps/desktop/test/application-control.test.js"] },
  // W-12: the picker lookup three lines above the duplicate check has always keyed on provider AND
  // model; the duplicate check keyed on the provider alone, so model B while model A was live
  // returned {duplicate:true} and handed the conductor the wrong model's node, reported ready.
  { id: "O17", what: "duplicate-worker matching goes back to provider-only",
    file: "apps/desktop/control/application-control.js",
    find: "    const duplicate = io.liveWorkerRecords().find((r) => r.chrome\n      && r.chrome.provider === provider && r.chrome.model_slug === modelId);",
    replace: "    const duplicate = io.liveWorkerRecords().find((r) => r.chrome && r.chrome.provider === provider);",
    expect: "a same-provider DIFFERENT-model spawn is not reported as a duplicate",
    cmd: "node", args: ["--test", "apps/desktop/test/application-control.test.js"] },
  // U458: the W-41 corrective. O20 restores the exact regression — the Node mirror signing `payload`
  // alone while Python signs the whole envelope. Note it leaves `canonicalEnvelope` intact and
  // correct: the serializer was never wrong, the INPUT handed to it was, which is why the byte-level
  // vector alone would not catch this row and the HMAC comparison is the grader.
  { id: "O20", what: "the Node mirror goes back to signing the payload alone (the U458 regression)",
    file: "apps/desktop/ipc/envelope.js",
    find: "  return crypto.createHmac(\"sha256\", key).update(canonicalEnvelope(envelope)).digest(\"hex\");",
    replace: "  return crypto.createHmac(\"sha256\", key).update(canonicalPayload(envelope.payload)).digest(\"hex\");",
    expect: "the two implementations disagree on the HMAC of the fixed vector",
    cmd: "py", args: ["-3.12", "-m", "pytest", "-q", "tests/remediation/test_orchestration_envelope_parity.py"] },
  // O21 grades the freshness rule this corrective ADDED to the Node side. A rule that cannot fail is
  // not a rule: without this row, deleting the window comparison would leave every test green
  // because a permanently-fresh reader still agrees with Python about everything else.
  { id: "O21", what: "the Node freshness window stops bounding anything (always fresh)",
    file: "apps/desktop/ipc/envelope.js",
    find: "  return Math.abs(reference - stamped) <= windowS * 1000;",
    replace: "  return true;",
    expect: "python says fresh=False and node says fresh=True",
    cmd: "py", args: ["-3.12", "-m", "pytest", "-q", "tests/remediation/test_orchestration_envelope_parity.py"] },
];

const hash = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex").toUpperCase();
let lock;
try { lock = fs.openSync(LOCK, "wx"); }
catch (e) { console.error(`mutation lock unavailable: ${e.message}`); process.exit(3); }

let failures = 0;
try {
  for (const [rel, pin] of Object.entries(PINS)) {
    const actual = hash(fs.readFileSync(path.join(ROOT, rel)));
    if (actual !== pin) throw new Error(`${rel} is ${actual}, expected pinned ${pin}`);
  }
  for (const row of rows) {
    const file = path.join(ROOT, row.file);
    const original = fs.readFileSync(file);
    const source = original.toString("utf8");
    if (source.split(row.find).length !== 2) throw new Error(`${row.id} anchor is not unique`);
    try {
      fs.writeFileSync(file, source.replace(row.find, row.replace), "utf8");
      const result = spawnSync(row.cmd, row.args, { cwd: ROOT, encoding: "utf8", timeout: 30000 });
      const output = `${result.stdout || ""}\n${result.stderr || ""}`;
      if (result.status === 1 && output.includes(row.expect)) {
        console.log(`CAUGHT  ${row.id}  ${row.what}`);
      }
      else {
        failures += 1;
        console.error(`SURVIVED/SETUP-FAIL  ${row.id}  exit=${result.status} `
          + `expected=${JSON.stringify(row.expect)}  ${row.what}`);
      }
    } finally {
      fs.writeFileSync(file, original);
      if (hash(fs.readFileSync(file)) !== hash(original)) throw new Error(`${row.id} restore diverged`);
    }
  }
} catch (e) {
  failures += 1;
  console.error(e.message);
} finally {
  try { fs.closeSync(lock); } catch { /* already closed */ }
  try { fs.unlinkSync(LOCK); } catch { /* absent */ }
}

if (failures) process.exit(1);
// The count is derived, not typed: a row added without its number being updated used to print a
// sentence that undercounted its own evidence.
console.log(`ALL ${rows.length} ORCHESTRATION MUTATIONS CAUGHT; every file restored BYTE-IDENTICALLY`);
