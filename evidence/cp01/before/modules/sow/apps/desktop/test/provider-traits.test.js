"use strict";
/**
 * Phase 19 unit 19.6 — I-SC1 in the RUNTIME: provider behaviour is DECLARED, not branched on.
 *
 * Three inline `provider === "<vendor>"` branches decided runtime behaviour before this unit:
 * `worker-readiness.js:595` (grok needs two readiness turns), `pane-writer.js:308` (codex needs a
 * second Enter), and three classification rules in `provider-readiness.js`. Each was correct for
 * the vendor it named and invisible to everything else — [[U386]](c) and [[U393]] MINOR-1.
 *
 * The point of the table is NOT that vendor names disappear: a Grok overlay string is a fact about
 * Grok and lives somewhere. It is that the RUNTIME asks a descriptor what to do and an undeclared
 * provider gets working generic behaviour instead of falling off the end of an `if`. These tests
 * pin the two halves that matter: the declared traits still describe the shipped vendors exactly,
 * and an unknown provider is SERVED (generic), never refused and never silently given another
 * vendor's rules.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { traitsFor, GENERIC_TRAITS, declaredProviderIds } = require("../control/provider-traits");
const { classifyProviderScreen } = require("../control/provider-readiness");

test("an undeclared provider gets generic traits, not a refusal and not another vendor's rules", () => {
  for (const unknown of ["mistral_cli", "", null, undefined, 0, {}]) {
    const t = traitsFor(unknown);
    assert.equal(t.declared, false, `${String(unknown)} must not be declared`);
    assert.equal(t.readiness_turns, 1);
    assert.equal(t.submit_confirm_enter, false);
    assert.deepEqual(t.screen_rules, []);
  }
  assert.equal(GENERIC_TRAITS.readiness_turns, 1);
});

test("the declared table reproduces every vendor behaviour the inline branches had", () => {
  assert.equal(traitsFor("grok_build").readiness_turns, 2, "U386(c): grok's two-turn readiness");
  assert.equal(traitsFor("openai_codex_cli").submit_confirm_enter, true, "codex's confirm Enter");
  assert.equal(traitsFor("claude_code").submit_confirm_enter, false);
  assert.equal(traitsFor("claude_code").readiness_turns, 1);
  assert.equal(traitsFor("google_antigravity").readiness_turns, 1);
  assert.deepEqual(declaredProviderIds().slice().sort(),
    ["claude_code", "google_antigravity", "grok_build", "openai_codex_cli"]);
});

test("traits are frozen — a caller cannot edit the shipped rules for every later caller", () => {
  const t = traitsFor("grok_build");
  assert.throws(() => { t.readiness_turns = 9; }, TypeError);
  assert.throws(() => { t.screen_rules.push({}); }, TypeError);
  assert.equal(traitsFor("grok_build").readiness_turns, 2);
});

test("classification: universal rules apply to EVERY provider, declared or not", () => {
  for (const provider of ["grok_build", "claude_code", "mistral_cli", null]) {
    assert.equal(classifyProviderScreen(provider, "You are not signed in").state, "AUTH_REQUIRED");
    assert.equal(classifyProviderScreen(provider, "Do you trust the contents of this project?").state,
      "WORKSPACE_TRUST_REQUIRED");
    assert.equal(
      classifyProviderScreen(provider, "Sovereign MCP: approve this tool?").state,
      "MCP_PERMISSION_REQUIRED");
  }
});

test("classification: a provider-scoped rule fires for its provider and for no other", () => {
  const grokLimit = "You have reached your Grok Build usage limit";
  assert.equal(classifyProviderScreen("grok_build", grokLimit).terminal_state, "USAGE_LIMIT");
  assert.equal(classifyProviderScreen("google_antigravity", grokLimit), null);
  assert.equal(classifyProviderScreen("mistral_cli", grokLimit), null);

  const agyPlan = "Review plan before Gemini continues";
  assert.equal(classifyProviderScreen("google_antigravity", agyPlan).terminal_state,
    "AWAITING_PROVIDER_SETUP");
  assert.equal(classifyProviderScreen("grok_build", agyPlan), null);

  const grokOverlay = "What's new — press Enter to continue";
  assert.equal(classifyProviderScreen("grok_build", grokOverlay).terminal_state,
    "AWAITING_PROVIDER_SETUP");
  assert.equal(classifyProviderScreen("openai_codex_cli", grokOverlay), null);
});

test("classification: grok's usage-limit rule is still consulted BEFORE its overlay rule", () => {
  // Both patterns match this screen. Order decided the verdict when the branches were inline and it
  // decides it now: an exhausted subscription is not an onboarding overlay.
  const both = "You have exceeded your usage limit. Press Enter to continue.";
  assert.equal(classifyProviderScreen("grok_build", both).terminal_state, "USAGE_LIMIT");
  assert.deepEqual(traitsFor("grok_build").screen_rules.map((r) => r.id),
    ["grok_auth_instruction", "grok_usage_limit", "grok_onboarding_overlay"]);
});

test("the Grok login instruction is provider-scoped, not universal", () => {
  assert.equal(classifyProviderScreen("grok_build", "Run `grok login` to continue").state,
    "AUTH_REQUIRED");
  assert.equal(classifyProviderScreen("claude_code", "Run `grok login` to continue"), null);
  assert.equal(classifyProviderScreen("mistral_cli", "Run `grok login` to continue"), null);
});

test("a screen matching BOTH a universal and a scoped rule classifies as the universal one", () => {
  // The precedence 19.6 introduced by construction (universal rules first, then the provider's).
  // Nothing pinned it, and the module header makes it a behaviour claim — spec-auditor MINOR-2.
  // A pane that is not signed in AND shows a usage-limit line is unauthenticated first: that is the
  // state the operator must act on, and it is true of every provider rather than of one.
  const both = "You are not signed in. You have also exceeded your usage limit, try again later.";
  assert.equal(classifyProviderScreen("grok_build", both).state, "AUTH_REQUIRED");
  assert.equal(classifyProviderScreen("google_antigravity",
    "Do you trust the contents of this project? Review plan before Gemini continues").state,
  "WORKSPACE_TRUST_REQUIRED");
});

test("a clean screen classifies null for every provider — the negative control (U329's rule)", () => {
  for (const provider of ["grok_build", "openai_codex_cli", "google_antigravity", "mistral_cli"]) {
    assert.equal(classifyProviderScreen(provider, "sovereign> ready\r\nbuild complete\r\n"), null);
  }
});
