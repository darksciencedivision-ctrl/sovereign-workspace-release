"use strict";
/**
 * Phase 17C `.mic` — the shell-side credential scrub for diagnostic children (closes **U136**).
 *
 * The load-bearing test here is the LAST one: this JS classifier is a second copy of a rule whose
 * authority is `adapters/frontier/claude_code.is_credential_env_key`, and a copy that fell behind a new
 * provider prefix would scrub less than the governed launch path while looking identical to a reader.
 * So the three name lists are parsed out of the Python source and compared — the same technique that
 * pins the probe budgets across the two languages.
 */
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const {
  isCredentialEnvKey, scrubCredentialEnv, childEnv,
  CREDENTIAL_ENV_KEYS, CREDENTIAL_KEY_PREFIXES, CREDENTIAL_KEY_SUBSTRINGS, PYTHON_SOURCE,
} = require("../voice/env-scrub");

test("classifies exact credential keys, provider prefixes and secret substrings", () => {
  for (const k of CREDENTIAL_ENV_KEYS) assert.ok(isCredentialEnvKey(k), k);
  assert.ok(isCredentialEnvKey("ANTHROPIC_SOMETHING_NEW"), "an unknown var under a provider prefix");
  assert.ok(isCredentialEnvKey("AWS_PROFILE"));
  assert.ok(isCredentialEnvKey("CLAUDE_CODE_ANYTHING"));
  assert.ok(isCredentialEnvKey("MY_GITHUB_TOKEN"));
  assert.ok(isCredentialEnvKey("some_api_key"), "case-insensitive");
  assert.ok(isCredentialEnvKey("DB_PASSWORD"));
  assert.ok(isCredentialEnvKey("CLIENT_SECRET"));
});

test("leaves the variables a python child actually needs", () => {
  for (const k of ["PATH", "TEMP", "TMP", "SYSTEMROOT", "LANG", "HTTPS_PROXY", "WSLENV",
                   "SOW_NEMO_PROBE_TIMEOUT_S", "SOW_NEMO_TRANSCRIBE_TIMEOUT_S", "SOW_WSL_DISTRO"]) {
    assert.equal(isCredentialEnvKey(k), false, k);
  }
  assert.equal(isCredentialEnvKey(""), false);
  assert.equal(isCredentialEnvKey(undefined), false);
});

test("scrubCredentialEnv removes the names and reports which — never a value", () => {
  const { env, scrubbed } = scrubCredentialEnv({
    PATH: "C:\\bin", ANTHROPIC_API_KEY: "sk-secret", GITHUB_TOKEN: "ghp-secret", LANG: "en_US",
  });
  assert.deepEqual(Object.keys(env).sort(), ["LANG", "PATH"]);
  assert.deepEqual(scrubbed.sort(), ["ANTHROPIC_API_KEY", "GITHUB_TOKEN"]);
  assert.equal(JSON.stringify(scrubbed).includes("secret"), false, "names only — no value is ever returned");
});

test("childEnv applies overrides AFTER the scrub and refuses one that reintroduces a credential", () => {
  const { env, scrubbed, refused } = childEnv(
    { SOW_NEMO_PROBE_TIMEOUT_S: "300", ANTHROPIC_API_KEY: "sk-sneaked-back" },
    { PATH: "C:\\bin", ANTHROPIC_API_KEY: "sk-secret" },
  );
  assert.equal(env.SOW_NEMO_PROBE_TIMEOUT_S, "300");
  assert.equal("ANTHROPIC_API_KEY" in env, false, "the scrub cannot be undone through `extra`");
  assert.deepEqual(scrubbed, ["ANTHROPIC_API_KEY"]);
  assert.deepEqual(refused, ["ANTHROPIC_API_KEY"]);
});

test("the JS name lists are PINNED to the Python authority (drift would scrub less, silently)", () => {
  const src = fs.readFileSync(PYTHON_SOURCE, "utf8");
  const tupleOf = (name) => {
    const m = new RegExp(`${name}[^=]*=\\s*\\(([\\s\\S]*?)\\)`).exec(src);
    assert.ok(m, `could not find ${name} in ${PYTHON_SOURCE}`);
    return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
  };
  assert.deepEqual(tupleOf("_CREDENTIAL_ENV_KEYS").sort(), [...CREDENTIAL_ENV_KEYS].sort());
  assert.deepEqual(tupleOf("_CREDENTIAL_KEY_PREFIXES").sort(), [...CREDENTIAL_KEY_PREFIXES].sort());
  assert.deepEqual(tupleOf("_CREDENTIAL_KEY_SUBSTRINGS").sort(), [...CREDENTIAL_KEY_SUBSTRINGS].sort());
});

test("the pin also covers the RULE SHAPE, not only the data", () => {
  // Pinning the three lists catches a new NAME on either side. It does not catch a new FAMILY: if the
  // Python authority grew a fourth rule (a suffix match, a regex), this JS copy would scrub strictly
  // less while all three list assertions still passed — silently weaker on the boundary that reaches
  // WSL. So the classifier's body is pinned to the three families it is allowed to consult.
  const src = fs.readFileSync(PYTHON_SOURCE, "utf8");
  const body = /def is_credential_env_key\(name: str\) -> bool:([\s\S]*?)\ndef /.exec(src);
  assert.ok(body, "could not locate is_credential_env_key");
  const referenced = [...body[1].matchAll(/_CREDENTIAL_[A-Z_]+/g)].map((m) => m[0]);
  assert.deepEqual([...new Set(referenced)].sort(),
    ["_CREDENTIAL_ENV_KEYS", "_CREDENTIAL_KEY_PREFIXES", "_CREDENTIAL_KEY_SUBSTRINGS"],
    "the Python classifier consults a family this JS mirror does not implement");
});
