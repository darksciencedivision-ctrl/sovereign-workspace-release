"use strict";
/**
 * Phase 18E `.live.electron` — the LIVE acceptance receipt's rules, each with a way to go RED.
 *
 * The lesson these tests exist for is U296's, taken at 18D: a rule that runs only at in-Electron
 * emit time is a rule the ordinary suite cannot falsify, so weakening it leaves everything green
 * and the receipt keeps looking like evidence. Every test below starts from an observation that
 * PASSES and breaks exactly one thing.
 *
 * The live receipt needs this more than its siblings, not less: it is the one that will be read as
 * "both providers work", and the difference between that and "a terminal echoed" is entirely in
 * these rules.
 */
const test = require("node:test");
const assert = require("node:assert");

const {
  OP12_PROVIDERS, OP12_SUBSCRIPTION_REFS, OP12_EXECUTABLE, REQUIRED_OWED_KEYS, GENESIS_PREV_HASH,
  modelSlugInArgv, executableBasename,
  worldIsLiveOpen, paneRunsExactlyThisSelection, childEnvIsScrubbed, liveAnswerIsHonest,
  nodeRecordLifecycleIsComplete, appendOnlyChainIsIntact, owedLegsAreNamed,
  paneConsentGate, consentOutcomeIsHonest, repoUnchangedByTheRun, credentialSinkMap, sentinelPlan,
} = require("../selfcheck/op12-live-acceptance-verdict");
const { OWED } = require("../selfcheck/op12-live-acceptance-selfcheck");

// ---------------------------------------------------------------------------------------------
// the world
// ---------------------------------------------------------------------------------------------

const openWorld = () => ({
  authorized: true, register_row: "OP-12",
  providers: ["claude_code", "google_antigravity", "grok_build", "openai_codex_cli"],
});

test("an open switch naming both OP-12 providers is live", () => {
  const w = worldIsLiveOpen(openWorld());
  assert.equal(w.live, true);
  assert.deepEqual(w.op12_authorized.slice().sort(), OP12_PROVIDERS.slice().sort());
  assert.deepEqual(w.op12_denied, []);
});

test("an UNREADABLE authorization is never treated as live (fail closed)", () => {
  for (const bad of [null, undefined, {}, { providers: "grok_build" }, 7]) {
    const w = worldIsLiveOpen(bad);
    assert.equal(w.live, false, `${JSON.stringify(bad)} was read as live`);
    assert.equal(w.op12_authorized.length, 0);
    assert.match(w.reason, /could not be read|no OP-12 provider is live/);
  }
});

test("a switch that lists the providers but is OFF is not live", () => {
  // The code-pinned scope can populate `providers` while the operator's file says no. Reading the
  // list alone would call a DENIED world live — the exact inversion this receipt must not make.
  const w = worldIsLiveOpen({ ...openWorld(), authorized: false });
  assert.equal(w.live, false);
  assert.equal(w.op12_authorized.length, 0);
});

test("a PARTIAL world is not live, and names which provider is denied", () => {
  const w = worldIsLiveOpen({ ...openWorld(), providers: ["claude_code", "grok_build"] });
  assert.equal(w.live, false);
  assert.deepEqual(w.op12_authorized, ["grok_build"]);
  assert.deepEqual(w.op12_denied, ["google_antigravity"]);
  assert.match(w.reason, /google_antigravity/);
});

// ---------------------------------------------------------------------------------------------
// the exact provider + model
// ---------------------------------------------------------------------------------------------

const REPO = "D:\\repo";

function goodPane(overrides = {}) {
  const provider = overrides.provider || "grok_build";
  const option = { label: "grok-4.5", model_slug: "grok-4.5", ...(overrides.option || {}) };
  return {
    provider,
    option,
    launch: { launched: true },
    record: {
      state: "running", supervised: true, subscriptionGoverned: true,
      subscriptionRef: OP12_SUBSCRIPTION_REFS[provider], leaseId: "lease-abc",
      executable: `C:\\bin\\${OP12_EXECUTABLE[provider]}.exe`,
      argv: [OP12_EXECUTABLE[provider], "--cwd", REPO, "--permission-mode", "plan", "-m",
        option.model_slug],
      cwd: REPO,
      chrome: { governed: true, adapter: provider, model_label: option.label },
      ...(overrides.record || {}),
    },
    session: { state: "RUNNING", pid: 4242, ...(overrides.session || {}) },
    spawned: { file: `C:\\bin\\${OP12_EXECUTABLE[provider]}.exe`, cwd: REPO,
      ...(overrides.spawned || {}) },
    repoRoot: REPO,
    samePath: (a, b) => String(a || "").toLowerCase() === String(b || "").toLowerCase(),
  };
}

test("a real governed OP-12 pane on the selected model passes", () => {
  for (const provider of OP12_PROVIDERS) {
    const obs = goodPane({ provider, option: { label: "m", model_slug: "m" } });
    obs.record.argv = [OP12_EXECUTABLE[provider], "--model", "m"];
    obs.record.chrome.model_label = "m";
    const v = paneRunsExactlyThisSelection(obs);
    assert.ok(v.ok, `${provider}: ${v.reasons.join("; ")}`);
    assert.equal(v.model_slug_launched, "m");
  }
});

test("a pane running a DIFFERENT model than the operator selected is refused", () => {
  const obs = goodPane();
  obs.record.argv = ["grok", "-m", "grok-4.5-mini"];
  const v = paneRunsExactlyThisSelection(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /launched model "grok-4\.5-mini" while the operator's selection/);
});

test("a pane whose argv pins NO model is refused (an unpinned live call is not verified)", () => {
  const obs = goodPane();
  obs.record.argv = ["grok", "--cwd", REPO];
  const v = paneRunsExactlyThisSelection(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /carries no model id/);
});

test("a pane running the OTHER provider's binary is refused however the chrome is labelled", () => {
  const obs = goodPane();
  obs.record.executable = "C:\\bin\\agy.exe";
  obs.spawned.file = "C:\\bin\\agy.exe";
  const v = paneRunsExactlyThisSelection(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /basename is not "grok"/);
});

test("an observed node-pty spawn belonging to ANOTHER pane is refused", () => {
  const obs = goodPane();
  obs.spawned.file = "C:\\bin\\ollama.exe";
  const v = paneRunsExactlyThisSelection(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /is not this pane's binary/);
});

test("a frontier pane counted against the WRONG subscription resource is refused (U76)", () => {
  const obs = goodPane();
  obs.record.subscriptionRef = "sub-claude_code";
  const v = paneRunsExactlyThisSelection(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /two-bucket/);
});

test("a pane bound to a workspace other than the governed one is refused", () => {
  const obs = goodPane();
  obs.spawned.cwd = "C:\\somewhere\\else";
  const v = paneRunsExactlyThisSelection(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /ConPTY was started in/);
});

test("a badge naming a model the process is not running is refused (invariant 3/27)", () => {
  const obs = goodPane();
  obs.record.chrome.model_label = "grok-9 turbo";
  const v = paneRunsExactlyThisSelection(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /pane badge reads/);
});

test("a pane with no live session, or an unsupervised one, is refused", () => {
  for (const patch of [{ session: { state: "EXITED", pid: 1 } },
    { session: { state: "RUNNING", pid: 0 } },
    { record: { supervised: false } }]) {
    const v = paneRunsExactlyThisSelection(goodPane(patch));
    assert.equal(v.ok, false, JSON.stringify(patch));
  }
});

test("modelSlugInArgv reads `--model=x`, refuses a flag-shaped value, and ignores other flags", () => {
  assert.equal(modelSlugInArgv(["agy", "--model=gemini-3.6-flash-low"]), "gemini-3.6-flash-low");
  assert.equal(modelSlugInArgv(["grok", "-m", "--no-memory"]), null);
  assert.equal(modelSlugInArgv(["grok", "-m"]), null);
  assert.equal(modelSlugInArgv(["grok", "--mode", "plan"]), null);
  assert.equal(executableBasename("C:\\bin\\GROK.EXE "), "grok");
});

// ---------------------------------------------------------------------------------------------
// the child environment
// ---------------------------------------------------------------------------------------------

const goodEnv = () => ({
  spawned: { inheritedEnv: false, envKeys: ["PATH", "HOME", "TEMP"] },
  scrubNames: ["XAI_API_KEY", "GEMINI_API_KEY"],
});

test("a scrubbed child environment passes", () => {
  const v = childEnvIsScrubbed(goodEnv());
  assert.ok(v.ok, v.reasons.join("; "));
  assert.equal(v.scrub_count, 2);
});

test("a child that inherited the shell environment verbatim is refused", () => {
  const obs = goodEnv();
  obs.spawned.inheritedEnv = true;
  assert.equal(childEnvIsScrubbed(obs).ok, false);
});

test("a named var that SURVIVED into the child is refused, case-insensitively (U105)", () => {
  const obs = goodEnv();
  obs.spawned.envKeys = ["PATH", "Xai_Api_Key"];
  const v = childEnvIsScrubbed(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /still carries XAI_API_KEY/);
});

test("a credential-bearing NAME the ticket never listed is still refused in the child", () => {
  const obs = goodEnv();
  obs.scrubNames = ["SOMETHING_ELSE"];
  obs.spawned.envKeys = ["PATH", "GOOGLE_API_KEY"];
  const v = childEnvIsScrubbed(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /credential-bearing name GOOGLE_API_KEY/);
});

test("an EMPTY scrub list is refused — an absent name proves nothing about a removal", () => {
  const obs = goodEnv();
  obs.scrubNames = [];
  assert.equal(childEnvIsScrubbed(obs).ok, false);
});

test("a child that lost PATH is refused — emptying the environment is not scrubbing it", () => {
  const obs = goodEnv();
  obs.spawned.envKeys = ["HOME"];
  assert.equal(childEnvIsScrubbed(obs).ok, false);
});

test("an unobserved spawn is refused, never assumed clean", () => {
  assert.equal(childEnvIsScrubbed({ spawned: null, scrubNames: ["X"] }).ok, false);
});

// ---------------------------------------------------------------------------------------------
// the live answer
// ---------------------------------------------------------------------------------------------

const goodAnswer = () => ({
  falsifiable: true, absentBefore: true, echoed: true, submitted: true,
  answer: { seen: true, form: "prefixed" },
});

test("a falsifiable probe answered after submission is an honest live answer", () => {
  assert.ok(liveAnswerIsHonest(goodAnswer()).ok);
});

test("a CLI that said NOTHING is not a live response, however cleanly it exited (U310)", () => {
  const obs = goodAnswer();
  obs.answer = { seen: false, form: null };
  const v = liveAnswerIsHonest(obs);
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /U310/);
});

test("keystrokes that never arrived and a model that never answered fail SEPARATELY", () => {
  const noEcho = liveAnswerIsHonest({ ...goodAnswer(), echoed: false });
  const noAnswer = liveAnswerIsHonest({ ...goodAnswer(), answer: { seen: false, form: null } });
  assert.equal(noEcho.ok, false);
  assert.equal(noAnswer.ok, false);
  assert.notDeepEqual(noEcho.reasons, noAnswer.reasons);
});

test("a token already on screen before submission cannot satisfy the leg", () => {
  assert.equal(liveAnswerIsHonest({ ...goodAnswer(), absentBefore: false }).ok, false);
});

test("a probe that carries its own answer is refused", () => {
  assert.equal(liveAnswerIsHonest({ ...goodAnswer(), falsifiable: false }).ok, false);
});

test("an answer reported in an unrecognised form is refused", () => {
  assert.equal(liveAnswerIsHonest({ ...goodAnswer(), answer: { seen: true, form: "assumed" } }).ok,
    false);
});

// ---------------------------------------------------------------------------------------------
// the node record's life on the operator's durable log
// ---------------------------------------------------------------------------------------------

const NODE_KEY = "worker-pane-7";
const SESSION = "pane-7#900.1";
const UUID = "3ea5fd0b-4af6-5d57-80cb-f55157621f99";

function lifecycleRows(overrides = {}) {
  const rows = [
    { node_id: NODE_KEY, kind: "spawn", incarnation: 1, seq: 1, prev_hash: GENESIS_PREV_HASH,
      hash: "h1",
      data: { session_id: SESSION, adapter: "grok_build", adapter_schema_version: "node@1.1",
        node_record: { node_id: UUID, adapter: "grok_build" } } },
    { node_id: NODE_KEY, kind: "transition", incarnation: 1, seq: 2, prev_hash: "h1", hash: "h2",
      data: { frm: "SPAWNING", to: "READY", pid: 4242 } },
    { node_id: NODE_KEY, kind: "transition", incarnation: 1, seq: 3, prev_hash: "h2", hash: "h3",
      data: { frm: "READY", to: "TERMINATED" } },
    { node_id: NODE_KEY, kind: "exit", incarnation: 1, seq: 4, prev_hash: "h3", hash: "h4",
      data: { exit_code: 0, expected: true } },
  ];
  return overrides.mutate ? overrides.mutate(rows) : rows;
}

const lifecycleArgs = (rows) => ({ rows, nodeKey: NODE_KEY, sessionId: SESSION, recordUuid: UUID,
  pid: 4242 });

test("SPAWNING → READY(pid) → TERMINATED + exit for THIS session is a complete lifecycle", () => {
  const v = nodeRecordLifecycleIsComplete(lifecycleArgs(lifecycleRows()));
  assert.ok(v.ok, v.reasons.join("; "));
  assert.equal(v.incarnation, 1);
});

test("a spawn row for a DIFFERENT session is not this pane's record (U315's binding)", () => {
  const rows = lifecycleRows();
  rows[0].data.session_id = "pane-7#900.2";
  const v = nodeRecordLifecycleIsComplete(lifecycleArgs(rows));
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /0 spawn row/);
});

test("a record whose uuid is not the one the ticket reported is refused", () => {
  const rows = lifecycleRows();
  rows[0].data.node_record.node_id = "11111111-2222-3333-4444-555555555555";
  const v = nodeRecordLifecycleIsComplete(lifecycleArgs(rows));
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /about another record/);
});

test("a READY transition carrying another process's pid is refused", () => {
  const rows = lifecycleRows();
  rows[1].data.pid = 9999;
  const v = nodeRecordLifecycleIsComplete(lifecycleArgs(rows));
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /is about another process/);
});

test("a record never moved to READY, or never closed, is refused (D-LOOP-1)", () => {
  const noReady = lifecycleRows().filter((r) => !(r.kind === "transition" && r.data.to === "READY"));
  const noClose = lifecycleRows().filter((r) => r.kind !== "exit"
    && !(r.kind === "transition" && r.data.to === "TERMINATED"));
  assert.equal(nodeRecordLifecycleIsComplete(lifecycleArgs(noReady)).ok, false);
  const closed = nodeRecordLifecycleIsComplete(lifecycleArgs(noClose));
  assert.equal(closed.ok, false);
  assert.match(closed.reasons.join(" "), /TERMINATED/);
});

test("a record written under the FROZEN schema version is refused (OP-12.1 authorized @1.1)", () => {
  const rows = lifecycleRows();
  rows[0].data.adapter_schema_version = "node@1.0";
  assert.equal(nodeRecordLifecycleIsComplete(lifecycleArgs(rows)).ok, false);
});

test("two spawn rows for one session is refused — a record is written once (invariant 12)", () => {
  const rows = lifecycleRows();
  rows.push({ ...rows[0], seq: 5, prev_hash: "h4", hash: "h5", incarnation: 2 });
  assert.equal(nodeRecordLifecycleIsComplete(lifecycleArgs(rows)).ok, false);
});

test("an intact hash chain passes, and a broken link or a reordered seq does not", () => {
  const rows = lifecycleRows();
  assert.ok(appendOnlyChainIsIntact(rows).ok);
  const broken = lifecycleRows();
  broken[2].prev_hash = "h1";
  assert.equal(appendOnlyChainIsIntact(broken).ok, false);
  const reordered = lifecycleRows();
  reordered[3].seq = 9;
  assert.equal(appendOnlyChainIsIntact(reordered).ok, false);
  assert.equal(appendOnlyChainIsIntact(null).ok, false);
  assert.equal(appendOnlyChainIsIntact([]).ok, false);
});

// ---------------------------------------------------------------------------------------------
// what the live receipt still owes
// ---------------------------------------------------------------------------------------------

test("the SHIPPED owed block names every required leg with a reference", () => {
  const v = owedLegsAreNamed(OWED);
  assert.ok(v.ok, v.reasons.join("; "));
  for (const key of REQUIRED_OWED_KEYS) assert.ok(OWED[key], `OWED is missing ${key}`);
});

test("a missing owed leg, or one citing nothing lookuppable, is refused", () => {
  for (const key of REQUIRED_OWED_KEYS) {
    const dropped = { ...OWED };
    delete dropped[key];
    assert.equal(owedLegsAreNamed(dropped).ok, false, `dropping ${key} stayed green`);
    const vague = { ...OWED, [key]: "this is still owed, honestly" };
    assert.equal(owedLegsAreNamed(vague).ok, false, `an unreferenced ${key} stayed green`);
  }
});

// ---------------------------------------------------------------------------------------------
// the consent gate — the thing the FIRST live run actually hit
// ---------------------------------------------------------------------------------------------

// Both fixtures are the REAL pane text captured by the first live in-Electron run
// (PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json, 2026-08-02T06:35Z, ok:false), not an invention: the
// point of the rule is that THESE screens are recognised, so THESE screens are what it is tested on.
const GROK_TRUST_SCREEN = "Grok Build may run or modify contents in this directory, posing security"
  + " risks. Yes, proceed y No, quit n ⠀ ⠀⠀ Grok Build 0.2.118 Beta";
const AGY_TRUST_SCREEN = ".. Accessing workspace: D:\\repo Do you trust the contents of this "
  + "project? Antigravity CLI requires permission to read, edit, and execute files here. > Yes, I "
  + "trust this folder No, exit ↑/↓ Navigate · enter Confirm plan · Gemini 3.6 Flash · low";
const AGY_SIGNING_IN = "Welcome to the Antigravity CLI. You are currently not signed in. ⢯ "
  + "Signing in... ⡿";

test("each provider's OWN directory-trust screen is recognised, with an operator step", () => {
  const grok = paneConsentGate("grok_build", GROK_TRUST_SCREEN);
  assert.equal(grok.gate, "workspace_trust");
  assert.match(grok.operator_step, /grok/);
  assert.match(grok.operator_step, /invariant 1|§11/);
  const agy = paneConsentGate("google_antigravity", AGY_TRUST_SCREEN);
  assert.equal(agy.gate, "workspace_trust");
  assert.match(agy.operator_step, /agy/);
});

test("a trust screen wrapped across lines is still recognised (a TUI is not one line)", () => {
  const wrapped = GROK_TRUST_SCREEN.split(" ").join("\r\n");
  assert.equal(paneConsentGate("grok_build", wrapped).gate, "workspace_trust");
});

test("ONE phrase is not a gate — a model that merely SAID 'yes, proceed' is not a modal", () => {
  assert.equal(paneConsentGate("grok_build", "SUM=120 — yes, proceed if that helps").gate, null);
  assert.equal(paneConsentGate("google_antigravity", "Do you trust the contents of this project? "
    + "I cannot say.").gate, null);
});

test("a CLI reporting it is SIGNING IN is not reported as waiting on the operator", () => {
  // "not signed in" alone would invent an operator step the CLI is already discharging itself —
  // which is the same error as the one this family exists to end, pointing the other way.
  assert.equal(paneConsentGate("google_antigravity", AGY_SIGNING_IN).gate, null);
  assert.equal(paneConsentGate("google_antigravity", "You are currently not signed in.").gate,
    "sign_in");
});

test("one provider's gate is never read off the other's screen, and a blank pane is no gate", () => {
  assert.equal(paneConsentGate("grok_build", AGY_TRUST_SCREEN).gate, null);
  assert.equal(paneConsentGate("google_antigravity", GROK_TRUST_SCREEN).gate, null);
  for (const empty of [null, undefined, "", "   "]) {
    assert.equal(paneConsentGate("grok_build", empty).gate, null);
  }
  assert.equal(paneConsentGate("claude_code", GROK_TRUST_SCREEN).gate, null);
});

const gatedLeg = () => ({
  gate: "workspace_trust", operator_step: "run `grok` once yourself (invariant 1)",
  detected_before_typing: true, typed: false, submitted: false, answer_seen: false, ok: false,
});

test("an ungated leg is not a skip, and a gated leg that claims nothing is an honest skip", () => {
  const ungated = consentOutcomeIsHonest({ gate: null, ok: true });
  assert.ok(ungated.ok);
  assert.equal(ungated.skipped, false);
  const gated = consentOutcomeIsHonest(gatedLeg());
  assert.ok(gated.ok, gated.reasons.join("; "));
  assert.equal(gated.skipped, true);
});

test("a gated leg reported as PASSED is refused — a gate is not an answer", () => {
  const v = consentOutcomeIsHonest({ ...gatedLeg(), ok: true });
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /reported as PASSED/);
});

test("typing into a gate the check had ALREADY seen is refused (it spends live budget for nothing)", () => {
  const v = consentOutcomeIsHonest({ ...gatedLeg(), typed: true });
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /ALREADY seen/);
});

test("a gate that rose AFTER quiescence, with NOTHING typed, is an honest skip", () => {
  // `agy` did exactly this on the first live run: it settled on its sign-in screen and reached the
  // trust prompt only later. Unknowable is not dishonest — as long as no keystroke went in.
  const v = consentOutcomeIsHonest({ ...gatedLeg(), detected_before_typing: false, typed: false });
  assert.ok(v.ok, v.reasons.join("; "));
  assert.equal(v.skipped, true);
});

test("a gated leg that reports an ANSWER is refused — a modal did not produce one", () => {
  assert.equal(consentOutcomeIsHonest({ ...gatedLeg(), answer_seen: true }).ok, false);
});

test("a gated leg naming no operator step is refused — an owed leg needs an owner", () => {
  assert.equal(consentOutcomeIsHonest({ ...gatedLeg(), operator_step: "" }).ok, false);
});

test("a gate blamed AFTER a prompt that ECHOED is refused - a modal does not echo (U310)", () => {
  // The pane text a late gate is read out of is the whole buffer, scrollback included. An echoed
  // prompt proves the pane was a real prompt, so blaming stale trust text there would bury a
  // session that took the keystrokes and said nothing.
  // `typed:false, submitted:false` deliberately: with either of those the SIBLING rule also fires,
  // and a row that goes red because a different guard caught it has stopped measuring its own guard
  // (the iteration-116 lesson). This leg is refusable only by the echo rule.
  const v = consentOutcomeIsHonest({
    ...gatedLeg(), detected_before_typing: false, typed: false, submitted: false, echoed: true,
  });
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /ECHOED/);
  assert.match(v.reasons.join(" "), /U310/);
});

test("a late gate may not explain a leg that TYPED and never echoed (U310, spec-audit round 2)", () => {
  // This is the route both earlier versions left open, and the second one PINNED GREEN: the echo
  // guard needs an echo, and in the check submission only happens after one — so a leg that typed
  // into a pane that never rendered the prompt back could still be called an honest consent skip.
  // Typing is the act that creates the ambiguity, so typing is the key.
  const v = consentOutcomeIsHonest({
    ...gatedLeg(), detected_before_typing: false, typed: true, submitted: false, echoed: false,
  });
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /TYPED/);
  assert.match(v.reasons.join(" "), /U310/);
});

test("the typing key fails CLOSED on a non-boolean (gate-validator NIT-1)", () => {
  const v = consentOutcomeIsHonest({
    ...gatedLeg(), detected_before_typing: false, typed: 1, echoed: false,
  });
  assert.equal(v.ok, false, "`typed: 1` is not `=== true`, and a refusal that only fires on a "
    + "perfect boolean is a refusal a sloppy caller escapes");
});

test("a skip is only ever explained by a gate the matcher itself can produce", () => {
  const v = consentOutcomeIsHonest({ ...gatedLeg(), gate: "totally_made_up" });
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /no provider signature/);
  // and every id the signatures DO produce is accepted
  for (const id of ["workspace_trust", "sign_in"]) {
    assert.ok(consentOutcomeIsHonest({ ...gatedLeg(), gate: id }).ok);
  }
});

test("a single utterance that PARAPHRASES the modal still matches — the comment says so now (U323)", () => {
  // Not a fix, a pinned limitation: text matching cannot separate a modal from a model quoting one.
  // What keeps it out of the receipt is WHEN the gate is read (before anything is typed) and the
  // submission rule above, both of which are tested. If this ever stops matching, the docstring and
  // U323 are stale and should be re-read rather than silently trusted.
  const paraphrase = "Sure. If you meant: Grok Build may run or modify contents in this directory, "
    + "then yes, proceed.";
  assert.equal(paneConsentGate("grok_build", paraphrase).gate, "workspace_trust");
});

test("an OWED marker must cite a real id — `MENU42` is not one (gate-validator MINOR-3)", () => {
  const owed = {};
  for (const key of REQUIRED_OWED_KEYS) owed[key] = "owed, see U317";
  assert.ok(owedLegsAreNamed(owed).ok);
  owed[REQUIRED_OWED_KEYS[0]] = "MENU42 is not a citation";
  assert.equal(owedLegsAreNamed(owed).ok, false);
});

test("repo_unchanged_by_the_run needs CLEAN at both ends, not merely equal (gate-validator MEDIUM-4)", () => {
  const clean = { tracked_product_tree_clean: true, unexpected_untracked_product_files: [] };
  const dirty = { tracked_product_tree_clean: false, unexpected_untracked_product_files: [] };
  assert.ok(repoUnchangedByTheRun(clean, clean).ok);
  assert.equal(repoUnchangedByTheRun(dirty, dirty).ok, false, "two dirty readings agreed with each "
    + "other and the field called itself unchanged");
  assert.equal(repoUnchangedByTheRun(clean, dirty).ok, false);
  assert.equal(repoUnchangedByTheRun(clean,
    { ...clean, unexpected_untracked_product_files: ["apps/desktop/leaked.js"] }).ok, false);
});

test("a credential name the HOST already sets is skipped, never read and never overwritten", () => {
  // §2.2 / OP-12 §13 forbid reading one in the same breath as storing one, and the earlier version
  // captured whatever real value was there so it could restore it.
  const plan = sentinelPlan({ GEMINI_API_KEY: "a-real-one", PATH: "…" },
    ["XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"], 4242);
  assert.deepEqual(plan.skipped, ["GEMINI_API_KEY"]);
  assert.deepEqual(plan.planted, ["XAI_API_KEY", "GOOGLE_API_KEY"]);
  assert.equal(plan.sentinels.length, plan.planted.length, "a sentinel nobody planted cannot be "
    + "found, and scanning for it would inflate the scan");
  assert.ok(plan.sentinels.every((s) => s.includes("4242")));
  // an EMPTY value still counts as set — the host owns that name either way
  assert.deepEqual(sentinelPlan({ XAI_API_KEY: "" }, ["XAI_API_KEY"], 1).skipped, ["XAI_API_KEY"]);
  // and nothing is skipped on a clean host
  assert.deepEqual(sentinelPlan({}, ["XAI_API_KEY"], 1).planted, ["XAI_API_KEY"]);
});

test("the credential sinks include the two durable stores this run writes (spec-audit M-2)", () => {
  const sinks = credentialSinkMap({
    logFile: "C:\\logs\\main-process.log", logText: "nothing here",
    receiptName: "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_CLOSE.json", receiptPayload: "{}",
    nodeLogPath: "D:\\repo\\.sovereign_store\\nodes\\node_events.jsonl", nodeLogText: "{}",
    ledgerPath: "D:\\repo\\.sovereign_store\\leases\\terminal_leases.json", ledgerText: "{}",
    providers: OP12_PROVIDERS, transcripts: { grok_build: "screen", google_antigravity: "screen" },
  });
  const names = Object.keys(sinks);
  assert.equal(names.length, 4 + OP12_PROVIDERS.length);
  assert.ok(names.some((n) => /node_events\.jsonl \(the operator's durable node log\)/.test(n)));
  assert.ok(names.some((n) => /terminal_leases\.json \(the operator's durable lease ledger\)/.test(n)));
  // the receipt sink names the FILE that gets written, not a sibling this target once wrote
  assert.ok(names.some((n) => n.startsWith("PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_CLOSE.json")));
  // and the pane sink is named for what it is: a screen, not a transcript (U324)
  assert.ok(names.some((n) => /pane screen as rendered at teardown/.test(n)));
  // an unreadable sink stays null so the scanner fails closed rather than passing an empty read
  const unread = credentialSinkMap({ nodeLogPath: "n", ledgerPath: "l", providers: ["grok_build"] });
  assert.equal(Object.values(unread).every((v) => v === null), true);
});

test("a switch with NO `authorized` key is not live - unreadable is never consent", () => {
  const w = worldIsLiveOpen({ register_row: "OP-12",
    providers: ["claude_code", "google_antigravity", "grok_build", "openai_codex_cli"] });
  assert.equal(w.live, false);
  assert.equal(w.op12_authorized.length, 0);
});

test("a READY transition that did not come from SPAWNING is refused", () => {
  const rows = lifecycleRows();
  const ready = rows.find((r) => r.kind === "transition" && r.data && r.data.to === "READY");
  ready.data.frm = "ASSIGNED";
  const v = nodeRecordLifecycleIsComplete(lifecycleArgs(rows));
  assert.equal(v.ok, false);
  assert.match(v.reasons.join(" "), /not SPAWNING/);
});
