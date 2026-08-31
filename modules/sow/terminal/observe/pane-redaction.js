"use strict";
/**
 * Redaction for pane output that is about to be shown to a MODEL (product code, terminal/).
 *
 * EPC-03 L4-2. The directive's D-4 says observation is "the raw bounded pane stream" and that
 * "`LogRing` already strips ANSI, control characters and redacts". Two of those three are true.
 * Measured: the bounded reader is `createScreenWindow` in `apps/desktop/control/worker-readiness.js`,
 * it normalises through `plainScreen` (`apps/desktop/control/provider-readiness.js:12`), and
 * `plainScreen` strips OSC sequences, CSI sequences and control characters. It redacts NOTHING.
 * Every `scrub`/`redact` in this module tree is ENVIRONMENT scrubbing — keeping credentials out of
 * a child process — not output scrubbing. There was no output redactor to reuse.
 *
 * That was contained until now, because the window's only consumers were a pattern classifier and
 * a write gate: the text was matched against regexes inside one process and thrown away. Layer 4
 * changes the consumer to a language model, which means the text gets written into a prompt, and a
 * prompt gets logged, cached and carried into evidence artifacts on disk. The same bytes acquire a
 * completely different exposure the moment their destination changes, so the redactor arrives with
 * the change of destination rather than after it.
 *
 * WHAT THIS IS NOT. It is a net, not a proof. Pattern redaction cannot guarantee that no secret
 * ever passes: a credential with no recognisable prefix, sitting on a line with no recognisable
 * label, is indistinguishable from ordinary text. Nothing downstream may describe an observation
 * as safe BECAUSE it was redacted. What it can honestly claim is what it reports: how many spans
 * of which kinds it removed, so a caller can see the net working rather than assume it.
 *
 * WHY MARKERS, NOT DELETION. A removed span is replaced with `[REDACTED:kind]`. A silent gap is
 * worse than a visible one for this consumer in particular: a model reading `export KEY=` followed
 * by nothing will happily invent what belongs there, and an operator reading the same window
 * cannot tell redaction from truncation.
 */

/** Each rule: a name, a pattern, and how much of the match survives.
 *
 *  Ordered deliberately. Private-key BLOCKS run first because their body would otherwise be eaten
 *  piecewise by the base64 rules and leave a mangled half-block; URL credentials run before the
 *  bare-token rules so `https://user:pw@host` is redacted as one credential rather than two. */
const RULES = Object.freeze([
  Object.freeze({
    kind: "private_key",
    // The whole armoured block, header to footer, however long. A key is the one thing where
    // leaving a "recognisable prefix" for context is itself the disclosure.
    pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
    replace: () => "[REDACTED:private_key]",
  }),
  Object.freeze({
    kind: "url_credentials",
    // scheme://user:secret@host — the password half only; the host is operationally useful and
    // the username is usually already visible elsewhere in the pane.
    pattern: /\b([a-z][a-z0-9+.-]*:\/\/[^\s:/@]+):([^\s@/]+)@/gi,
    replace: (_m, prefix) => `${prefix}:[REDACTED:url_credentials]@`,
  }),
  Object.freeze({
    kind: "jwt",
    pattern: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
    replace: () => "[REDACTED:jwt]",
  }),
  Object.freeze({
    kind: "api_key",
    // Vendor-prefixed keys. These are the ones a paste or an accidental echo actually produces,
    // and the prefixes are published by the vendors precisely so they can be recognised.
    pattern: new RegExp(
      "\\b("
      + "sk-ant-[A-Za-z0-9_-]{16,}"
      + "|sk-[A-Za-z0-9_-]{20,}"
      + "|gh[pousr]_[A-Za-z0-9]{20,}"
      + "|github_pat_[A-Za-z0-9_]{20,}"
      + "|xox[baprs]-[A-Za-z0-9-]{10,}"
      + "|AKIA[0-9A-Z]{16}"
      + "|ASIA[0-9A-Z]{16}"
      + "|AIza[A-Za-z0-9_-]{30,}"
      + "|hf_[A-Za-z0-9]{20,}"
      + "|glpat-[A-Za-z0-9_-]{16,}"
      + "|[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"
      + "|npm_[A-Za-z0-9]{30,}"
      + "|dop_v1_[a-f0-9]{32,}"
      + ")", "g"),
    replace: () => "[REDACTED:api_key]",
  }),
  Object.freeze({
    kind: "bearer_token",
    // HTTP auth schemes only, and `[ \t]` rather than `\s` so the rule cannot reach across a
    // NEWLINE. The first draft used `(bearer|token|basic)\s+`, and a pane showing
    //     $ echo $TOKEN
    //     sk-ant-api03-...
    // matched "TOKEN" + newline + the key: the secret was removed, but labelled `bearer_token`
    // and reported on the wrong line. A redaction whose own ACCOUNT of itself is wrong defeats
    // the receipt this module exists to produce, so the rule is bounded to a single line. It also
    // runs after `api_key`, so a vendor-prefixed key behind `Bearer ` keeps its true kind.
    pattern: /\b(bearer|basic)[ \t]+([A-Za-z0-9_\-.+/=]{12,})/gi,
    replace: (_m, scheme) => `${scheme} [REDACTED:bearer_token]`,
  }),
  Object.freeze({
    kind: "secret_assignment",
    // The `env` / `set` / `export` shape: a name that says secret, then a value. The NAME survives
    // - knowing that ANTHROPIC_API_KEY is set is operationally useful and is not the secret.
    pattern: /\b([A-Za-z_][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|SESSION_ID)[A-Za-z0-9_]*)(\s*[:=]\s*)(?:"[^"\n]{4,}"|'[^'\n]{4,}'|[^\s"'\n]{4,})/gi,
    replace: (_m, name, sep) => `${name}${sep}[REDACTED:secret_assignment]`,
  }),
]);

const KINDS = Object.freeze(RULES.map((r) => r.kind));

/**
 * Redact `text`. Returns `{ text, redactions, kinds }`.
 *
 * `redactions` is the number of spans removed and `kinds` the sorted distinct kinds, both so a
 * caller can REPORT the net's activity instead of asserting its completeness. Never throws: this
 * sits between a live pane and a model, and a redactor that can fail open is worse than useless.
 * Non-string input yields empty text rather than a coerced object.
 *
 * `rules` exists so the FAIL-CLOSED branch below can be exercised. No product caller passes it,
 * and it defaults to `RULES` (as does an empty or non-array argument, so it cannot be used to turn
 * redaction off). The seam is here because a branch that cannot be reached is a branch nobody has
 * checked, and this particular branch is the difference between withholding a pane's output and
 * handing a model the unredacted text as if it had been cleaned. A mutation run found exactly
 * that: "the redactor fails OPEN when a rule errors" SURVIVED, because nothing could make a rule
 * error.
 */
function redactPaneText(text, rules = RULES) {
  if (typeof text !== "string" || text === "") {
    return { text: "", redactions: 0, kinds: [] };
  }
  let out = text;
  let count = 0;
  const kinds = new Set();
  for (const rule of (Array.isArray(rules) && rules.length ? rules : RULES)) {
    try {
      out = out.replace(rule.pattern, (...args) => {
        count += 1;
        kinds.add(rule.kind);
        return rule.replace(...args);
      });
    } catch {
      // A rule that somehow fails must not take the whole redaction with it, and must not let the
      // unredacted text through as if it had been cleaned. Fail CLOSED on that rule's behalf.
      return {
        text: `[REDACTION FAILED - pane output withheld (rule: ${rule.kind})]`,
        redactions: count, kinds: [...kinds].sort(), failed: rule.kind,
      };
    }
  }
  return { text: out, redactions: count, kinds: [...kinds].sort() };
}

module.exports = { redactPaneText, REDACTION_KINDS: KINDS };
