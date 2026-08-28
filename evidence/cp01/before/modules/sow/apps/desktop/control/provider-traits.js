"use strict";
/**
 * Phase 19 unit 19.6 — declared provider traits (I-SC1: selection and behaviour by DESCRIPTOR,
 * never by name in the control flow).
 *
 * WHAT THIS REPLACES. Three runtime decisions were inline vendor comparisons:
 *
 *   * `worker-readiness.js`  — `provider === "grok_build" ? 2 : 1` readiness turns ([[U386]](c));
 *   * `pane-writer.js`       — `providerFor(paneId) === "openai_codex_cli"` submit-confirm Enter;
 *   * `provider-readiness.js` — three provider-scoped screen rules ([[U393]] MINOR-1).
 *
 * Each was CORRECT for the vendor it named. The defect is what happened to every provider it did
 * not: it fell off the end of an `if` and got behaviour nobody chose, in a file whose reviewers had
 * no list to check. A fifth provider is a row here, and the runtime never learns its name.
 *
 * WHAT THIS IS NOT. It is not an allowlist. `traitsFor` answers for EVERY provider id — an
 * undeclared one gets `GENERIC_TRAITS`, which is the behaviour that works without provider
 * knowledge (one readiness turn, one Enter, no provider-scoped screen rules). Nothing here can
 * refuse a provider: refusal is the governor's and the launch ticket's, and it stays there
 * (invariant 7 — this module holds no authority, only description).
 *
 * The vendor STRINGS do not disappear, and pretending otherwise would be the dishonest version of
 * this fix: "press Enter to continue" on a Grok onboarding overlay is a fact about Grok's TUI and
 * has to be written down somewhere. I-SC1's requirement is that the runtime consult a descriptor
 * rather than branch on a name — one table, enumerable, testable, with a default that serves the
 * unknown provider instead of ignoring it.
 */

/** Provider-scoped screen rules. Universal rules (auth, workspace trust, MCP permission) are NOT
 *  here — they belong to `provider-readiness.js` and apply to every provider, declared or not. */
const RULE = (id, pattern, state, terminalState, reason) => Object.freeze({
  id, pattern, state, terminal_state: terminalState, reason,
});

const GROK_RULES = Object.freeze([
  RULE("grok_auth_instruction", /run\s+[`'"]?grok login/i,
    "AUTH_REQUIRED", "AUTH_REQUIRED", "provider authentication is unresolved"),
  // Order is load-bearing and was load-bearing when these were inline: both patterns can match one
  // screen, and an exhausted subscription is not an onboarding overlay.
  RULE("grok_usage_limit",
    /(?:reached|exceeded).{0,40}(?:grok build )?usage limit|usage limit.{0,40}(?:try again|supergrok)/i,
    "PROVIDER_SETUP_REQUIRED", "USAGE_LIMIT",
    "Grok Build usage limit is currently exhausted"),
  RULE("grok_onboarding_overlay",
    /(connectors?\s+(?:setup|available)|what['’]?s new|update available|press enter to continue|try grok)/i,
    "PROVIDER_SETUP_REQUIRED", "AWAITING_PROVIDER_SETUP",
    "Grok promotional/onboarding/connector overlay is active"),
]);

const ANTIGRAVITY_RULES = Object.freeze([
  RULE("antigravity_planning_ui",
    /\bplan\b[^\n]{0,80}\bgemini\b|planning mode|review plan|approve plan/i,
    "PROVIDER_SETUP_REQUIRED", "AWAITING_PROVIDER_SETUP",
    "Antigravity is still in provider planning UI"),
]);

/** The traits every provider has until it declares otherwise. An undeclared provider is SERVED by
 *  these, not refused: one readiness turn, a single submit key, no provider-scoped screen rules. */
const GENERIC_TRAITS = Object.freeze({
  provider_id: null,
  declared: false,
  /** How many challenge/response turns readiness requires before promoting to READY. */
  readiness_turns: 1,
  /** Does the provider's composer confirm a multi-character paste with an extra Enter? */
  submit_confirm_enter: false,
  /** Provider-scoped `classifyProviderScreen` rules, consulted in order, after the universal ones. */
  screen_rules: Object.freeze([]),
});

const declare = (providerId, traits) => Object.freeze({
  ...GENERIC_TRAITS, ...traits, provider_id: providerId, declared: true,
});

const DECLARED = Object.freeze({
  claude_code: declare("claude_code", {}),
  openai_codex_cli: declare("openai_codex_cli", {
    // Codex confirms a multi-character paste with the first Enter and submits with the next one.
    submit_confirm_enter: true,
  }),
  grok_build: declare("grok_build", {
    // Grok answers the first prompt of a session with its own greeting; readiness needs a second
    // exchange before a response proves the session is serving requests.
    readiness_turns: 2,
    screen_rules: GROK_RULES,
  }),
  google_antigravity: declare("google_antigravity", { screen_rules: ANTIGRAVITY_RULES }),
});

/** Traits for any provider id. Never throws, never returns null: an unknown id is a provider this
 *  build has no knowledge of, which is a reason to use generic behaviour, not to fail. */
function traitsFor(providerId) {
  if (typeof providerId !== "string" || !providerId) return GENERIC_TRAITS;
  return Object.prototype.hasOwnProperty.call(DECLARED, providerId)
    ? DECLARED[providerId] : GENERIC_TRAITS;
}

/** The declared ids, for tests and for evidence that enumerates what this build knows. */
const declaredProviderIds = () => Object.keys(DECLARED);

module.exports = { traitsFor, declaredProviderIds, GENERIC_TRAITS };
