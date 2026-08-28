"use strict";
/**
 * Phase 19 unit 19.6 — [[U331]]: conductor readiness derives from the DESCRIPTOR.
 *
 * THE DEFECT. `apps/desktop/main.js` failed conductor readiness unless
 * `provider_id === "openai_codex_cli" && model_id === "gpt-5.6-sol"`, with the reason string
 * *"conductor readiness requires exact OpenAI/Codex gpt-5.6-sol selection"*. Commit `3587cbd`
 * ("generalize provider-agnostic conductor selection") generalized the SELECTION layer and the
 * Electron readiness layer then re-pinned it, disclosed nowhere. Two consequences the cold audit
 * recorded: `control_plane/conductor/registry.py` resolves `claude_code`/`fable-5` whenever the
 * gitignored `config/live_operation.json` is absent — so any clone without the operator's local
 * switch spawns the RECORDED selection successfully and then fails readiness forever with a message
 * that reads like a configuration error — and conductor succession onto a different backend, a
 * **Phase 15D exit criterion**, is unreachable. Invariant 3: the conductor is an interface plus a
 * runtime selection, never a vendor default.
 *
 * WHAT REPLACES IT, and what these tests pin. Admission asks the descriptor four questions that are
 * true of a conductor of ANY provider: is it a conductor, does it name a provider and a model, is
 * it registered, is it conductor-capable. What it may never do again is refuse a descriptor the
 * selection layer, the registry and the governed spawn path all accepted, because of the two strings
 * it happens to carry.
 *
 * Unit 19.10 closes the absence asymmetry: missing role/registration/capability is refused, and the
 * feed descriptor must agree with the launch ticket that authorized the process.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const {
  conductorAdmission, conductorDescriptorsAgree, AGREEMENT_FIELDS,
} = require("../control/conductor-admission");

const CODEX = Object.freeze({
  role: "conductor", provider_id: "openai_codex_cli", adapter_id: "openai_codex_cli",
  model_id: "gpt-5.6-sol", display_name: "ChatGPT 5.6 Sol", registered: true,
  conductor_capable: true, permission_profile_id: "pp-conductor-pane", readiness_turns: 1,
});
const FABLE = Object.freeze({
  role: "conductor", provider_id: "claude_code", adapter_id: "claude_code",
  model_id: "fable-5", display_name: "Claude Fable 5", registered: true, conductor_capable: true,
  permission_profile_id: "pp-conductor-pane", readiness_turns: 1,
});

test("U331: the fable-5 selection the registry resolves by default is ADMITTED", () => {
  // The exact descriptor `load_runtime_conductor_descriptor` returns when no host live-operation
  // preference exists — the case that failed readiness permanently before this unit.
  const verdict = conductorAdmission(FABLE);
  assert.equal(verdict.ok, true);
  assert.equal(verdict.provider_id, "claude_code");
  assert.equal(verdict.model_id, "fable-5");
  assert.equal(verdict.decided_by, "conductor_descriptor");
});

test("U331: the previously-pinned pair is still admitted — this is a widening, not a swap", () => {
  assert.equal(conductorAdmission(CODEX).ok, true);
});

// NOTE the scope, corrected after the spec-auditor's MINOR-1: these pairs are objects THIS TEST
// wrote, and three of them are not registered pairs in `control_plane/conductor/registry.py` (which
// mints only codex/gpt-5.6-sol, claude/fable-5, claude/opus-4.8). The property under test is this
// module's — it does not refuse on the name — NOT that a conductor can be launched on any of them:
// the registry bounds what can be minted, and `conductor/launch-source.js` refuses a ticket whose
// provider has no verified containment profile.
test("U331: admission does not refuse a descriptor for the name it carries", () => {
  for (const [provider, model] of [["claude_code", "opus-4.8"], ["grok_build", "grok-code"],
    ["google_antigravity", "gemini-3-pro"], ["ollama_local", "qwen3:8b"]]) {
    const verdict = conductorAdmission({ ...FABLE, provider_id: provider, model_id: model });
    assert.equal(verdict.ok, true, `${provider}/${model} must be admissible`);
    assert.equal(verdict.provider_id, provider);
  }
});

test("no vendor name and no model slug appears in an admission refusal", () => {
  const refusals = [conductorAdmission(null), conductorAdmission({ role: "conductor" }),
    conductorAdmission({ ...FABLE, registered: false }),
    conductorAdmission({ ...FABLE, conductor_capable: false }),
    conductorAdmission({ ...FABLE, role: "worker" })].map((v) => v.reason);
  for (const reason of refusals) {
    for (const vendorish of ["codex", "openai", "gpt-5", "claude", "fable", "grok", "gemini"]) {
      assert.ok(!reason.toLowerCase().includes(vendorish),
        `refusal reason must not name a vendor: ${reason}`);
    }
  }
});

test("fail closed: no descriptor at all is a FAILED readiness with a reason that says so", () => {
  for (const missing of [null, undefined, {}, "conductor", 7]) {
    const verdict = conductorAdmission(missing);
    assert.equal(verdict.ok, false);
    assert.equal(verdict.state, "FAILED");
    assert.match(verdict.reason, /unresolved|incomplete/i);
  }
});

test("fail closed: a descriptor missing its provider or its model is incomplete, not admitted", () => {
  assert.equal(conductorAdmission({ ...FABLE, provider_id: "" }).ok, false);
  assert.equal(conductorAdmission({ ...FABLE, model_id: "  " }).ok, false);
  assert.equal(conductorAdmission({ ...FABLE, provider_id: null }).ok, false);
  assert.match(conductorAdmission({ ...FABLE, model_id: "" }).reason, /model/i);
  assert.match(conductorAdmission({ ...FABLE, provider_id: "" }).reason, /provider/i);
});

test("fail closed: a descriptor for another role is not a conductor descriptor", () => {
  const verdict = conductorAdmission({ ...FABLE, role: "worker" });
  assert.equal(verdict.ok, false);
  assert.match(verdict.reason, /conductor/i);
});

test("fail closed: unregistered or not conductor-capable is refused — the registry's own verdict", () => {
  assert.equal(conductorAdmission({ ...FABLE, registered: false }).ok, false);
  assert.equal(conductorAdmission({ ...FABLE, conductor_capable: false }).ok, false);
  // Absent (rather than false) is not a refusal: an absent key is the absence of EVIDENCE, not the
  // registry's negative verdict, at a layer that can only decline to promote a session it did not
  // admit. Every conductor descriptor in this product comes from `registry.py`, which stamps both
  // `True`, so this case is a rule rather than an observed producer (spec-auditor MEDIUM-2).
  const sparse = { role: "conductor", provider_id: "claude_code", model_id: "fable-5" };
  assert.equal(conductorAdmission(sparse).ok, false);
  // …and the same convention for an ABSENT role, asserted here rather than only described in the
  // header, because that is where the two drafts of it went wrong (spec-auditor MAJOR-2).
  assert.equal(conductorAdmission({ provider_id: "claude_code", model_id: "fable-5" }).ok, false);
});

test("admission carries the provider's declared readiness turns, so the conductor pane is not "
  + "the one place a provider trait stops applying", () => {
  assert.equal(conductorAdmission(FABLE).readiness_turns, 1);
  assert.equal(conductorAdmission({ ...FABLE, provider_id: "grok_build", readiness_turns: 2 }).readiness_turns, 2);
});

test("the launch ticket and readiness feed must describe the same conductor", () => {
  assert.equal(conductorDescriptorsAgree(FABLE, { ...FABLE }), true);
  for (const patch of [{ provider_id: "openai_codex_cli" }, { model_id: "opus-4.8" },
    { adapter_id: "other" }, { permission_profile_id: "pp-other" }, { role: "worker" }]) {
    assert.equal(conductorDescriptorsAgree(FABLE, { ...FABLE, ...patch }), false,
      JSON.stringify(patch));
  }
  assert.equal(conductorDescriptorsAgree(FABLE, null), false);
});

// ---- W-17: an agreement set that omits a behaviour-driving field ---------------------------------
// AGREEMENT_FIELDS froze role/provider_id/adapter_id/model_id/permission_profile_id and left out
// `readiness_turns` -- which IS behaviour-driving: `conductorAdmission` reads it (:62-63) and
// `conductor-readiness.js:29` loops `for (turn = 1; turn <= admission.readiness_turns; ...)`. Its
// value is 1 by default and 2 for grok_build. So a feed descriptor carrying a different
// readiness_turns than the launch ticket authorized still "agreed", and the readiness gate could
// run a different number of turns than was authorized.

test("W-17: a feed descriptor differing only in readiness_turns is refused", () => {
  assert.equal(conductorDescriptorsAgree(FABLE, { ...FABLE, readiness_turns: 2 }), false,
    "readiness_turns decides how many turns the readiness gate runs, so a feed that disagrees "
    + "about it can run a different gate than the launch ticket authorized");
  assert.equal(conductorDescriptorsAgree({ ...FABLE, readiness_turns: 2 }, FABLE), false,
    "…in both directions");
});

test("W-17: an ABSENT readiness_turns still agrees with an explicit 1", () => {
  // Absent MEANS one turn -- the same normalization `conductorAdmission` already applies at :62-63.
  // Comparing raw values would make a descriptor minted before the field existed disagree with an
  // identical one that spells it out, which is a refusal with no behaviour behind it.
  const withoutTurns = { ...FABLE };
  delete withoutTurns.readiness_turns;
  assert.equal(conductorDescriptorsAgree(withoutTurns, FABLE), true);
  assert.equal(conductorDescriptorsAgree(FABLE, withoutTurns), true);
  assert.equal(conductorDescriptorsAgree(withoutTurns, { ...FABLE, readiness_turns: 2 }), false);
});

test("W-17: every behaviour-driving descriptor field is an agreement field", () => {
  // The general rule this unit encodes: A FIELD THAT CHANGES BEHAVIOUR IS AN AGREEMENT FIELD.
  // Enumerated here rather than narrated, so adding a new behaviour-driving field without adding
  // it to AGREEMENT_FIELDS fails instead of quietly widening what "the same conductor" means.
  const BEHAVIOUR_DRIVING = Object.freeze([
    "role",                    // which node this is at all
    "provider_id",             // which subscription and which CLI
    "adapter_id",              // which adapter contract governs it
    "model_id",                // which slug the CLI is asked for
    "permission_profile_id",   // which permission profile the process runs under
    "readiness_turns",         // how many turns the readiness gate runs
  ]);
  for (const key of BEHAVIOUR_DRIVING) {
    assert.ok(AGREEMENT_FIELDS.includes(key),
      `${key} drives behaviour but is not in AGREEMENT_FIELDS, so a feed may disagree about it`);
  }
});

test("the admitted verdict reports the SELECTION SOURCE the descriptor carries, and says so "
  + "honestly when the descriptor carries none", () => {
  assert.equal(conductorAdmission(FABLE).selection_source, "unstated");
  assert.equal(
    conductorAdmission({ ...FABLE, selection_source: "recorded_default_selection" }).selection_source,
    "recorded_default_selection");
  assert.equal(
    conductorAdmission({ ...FABLE, selection_source: "live_operation_preference" }).selection_source,
    "live_operation_preference");
});
