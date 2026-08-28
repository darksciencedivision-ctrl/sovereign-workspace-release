"use strict";
/**
 * Credential-name env scrub for shell-side child processes — Phase 17C `.mic` (closes **U136**).
 *
 * THE GAP THIS CLOSES. Every GOVERNED launch path (`worker-spawn.js`, the conductor launch) scrubs its
 * child environment through the ticket's `env_scrub_names`, minted Python-side. But the shell also
 * spawns local `py -3.12` DIAGNOSTIC children — the voice probe, its self-check's reference probe, the
 * capture emitter — and those were handed `{...process.env}` verbatim. The voice path in particular
 * crosses into the WSL VM via `wsl.exe`, where `WSLENV` can carry named host variables across; a
 * credential-bearing variable in the build shell's environment had no business making that trip.
 *
 * §2.2 is absolute about credentials, so the boundary is applied by DEFAULT rather than argued about
 * per call site. These children need PATH, TEMP, locale and the `SOW_*` knobs — nothing secret.
 *
 * DRIFT IS THE REAL RISK, not the rule itself. This is a second copy of a classifier whose authority
 * is `adapters/frontier/claude_code.is_credential_env_key`; a copy that quietly fell behind a new
 * provider prefix would scrub less than the governed path while looking identical. So the three name
 * lists are PINNED to the Python source by `apps/desktop/test/env-scrub.test.js`, which parses them out
 * of `claude_code.py` and fails if either side gains an entry the other lacks — the same technique that
 * pins the probe budgets across the two languages.
 */
const path = require("path");

//: MIRRORED from adapters/frontier/claude_code.py — pinned by apps/desktop/test/env-scrub.test.js.
const CREDENTIAL_ENV_KEYS = [
  "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
  "ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL", "AWS_BEARER_TOKEN_BEDROCK",
  "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
  "GOOGLE_APPLICATION_CREDENTIALS",
];
const CREDENTIAL_KEY_PREFIXES = ["ANTHROPIC_", "AWS_", "GOOGLE_", "CLAUDE_CODE_"];
const CREDENTIAL_KEY_SUBSTRINGS = ["TOKEN", "SECRET", "API_KEY", "APIKEY", "PASSWORD"];

//: Where the Python authority lives, so the pinning test does not hard-code a path twice.
const PYTHON_SOURCE = path.resolve(__dirname, "..", "..", "..", "adapters", "frontier", "claude_code.py");

/**
 * Fail-closed classifier: is `name` a credential/endpoint/secret-bearing variable?
 * Exactly the Python rule — exact match, provider prefix, or secret-token substring, case-insensitive.
 */
function isCredentialEnvKey(name) {
  const up = String(name || "").toUpperCase();
  if (!up) return false;
  if (CREDENTIAL_ENV_KEYS.includes(up)) return true;
  if (CREDENTIAL_KEY_PREFIXES.some((p) => up.startsWith(p))) return true;
  return CREDENTIAL_KEY_SUBSTRINGS.some((t) => up.includes(t));
}

/**
 * A child environment with every credential-bearing name REMOVED. Non-secret variables (PATH, TEMP,
 * proxies, locale, the `SOW_*` budgets) are preserved so the child still runs.
 * @param {object} baseEnv defaults to `process.env`
 * @returns {{env: object, scrubbed: string[]}} the env, and the NAMES removed (names only — a value is
 *   never returned, logged, or carried into a receipt)
 */
function scrubCredentialEnv(baseEnv) {
  const src = baseEnv || process.env;
  const env = {};
  const scrubbed = [];
  for (const key of Object.keys(src)) {
    if (isCredentialEnvKey(key)) { scrubbed.push(key); continue; }
    env[key] = src[key];
  }
  return { env, scrubbed };
}

/** `scrubCredentialEnv` plus explicit overrides applied AFTER the scrub, refusing any that is itself
 *  a credential name — so a caller cannot reintroduce through `extra` what the scrub just removed. */
function childEnv(extra = {}, baseEnv) {
  const { env, scrubbed } = scrubCredentialEnv(baseEnv);
  const refused = [];
  for (const [k, v] of Object.entries(extra || {})) {
    if (isCredentialEnvKey(k)) { refused.push(k); continue; }
    env[k] = v;
  }
  return { env, scrubbed, refused };
}

module.exports = {
  isCredentialEnvKey,
  scrubCredentialEnv,
  childEnv,
  CREDENTIAL_ENV_KEYS,
  CREDENTIAL_KEY_PREFIXES,
  CREDENTIAL_KEY_SUBSTRINGS,
  PYTHON_SOURCE,
};
