"use strict";
/**
 * W-29 — the renderer must not choose the executable, and a default pane must not carry credentials.
 *
 * TWO defects, one boundary. Both were CONFIRMED on this host by the independent review (R-03/E-01):
 *
 *   (a) `sanitizeRendererSpec` was a DENY-list. It dropped `env` and `cwd` and let everything else
 *       through, so a renderer-supplied `file` and `args` reached `pty.spawn(file, args)` verbatim.
 *       Section 13.5(b) of the review sharpens why this is the highest-leverage desktop fix: the OS
 *       process is created at `session-manager.js:69` and `supervisor.admit(...)` is not called until
 *       `:101`, so a renderer-chosen executable is launched FIRST and judged SECOND — a supervision
 *       denial can only try to kill something already running. An allow-list is the only point where
 *       the choice can be refused before a process exists.
 *       [B3-1/H-1 status: session-manager now takes a pre-spawn admission verdict, so the
 *       launch-first-judge-second ordering described above is closed at that layer too; this
 *       allow-list remains the earliest guarantee.]
 *
 *   (b) The sanitiser was COUNTER-PROTECTIVE about environments. Deleting `env` is exactly what
 *       triggers `ptyFactory`'s `spec.env || { ...process.env }` fallback, so scrubbing the one
 *       governance field the renderer must not set handed the child the shell's ENTIRE environment,
 *       credentials included. Removing (a) without (b) leaves the worse half in place.
 *
 * WHY THE FIX SUPPLIES THE ENV AT THE `pane:new` BOUNDARY rather than inside `ptyFactory`'s
 * fallback. `lastPtySpawn.inheritedEnv` is `!spec.env`, and `childEnvIsScrubbed`
 * (`selfcheck/op12-live-acceptance-verdict.js:494`) reads `inheritedEnv === true` to mean "the §2.2
 * scrub was not applied at all"; `worker-spawn-selfcheck.js:299` publishes it as
 * `local_child_env_inherited_verbatim`. Scrubbing inside the fallback would leave that flag either
 * lying in a receipt or frozen true-for-nobody — a guard that can never fire, which is the [[U367]]
 * class the [[U446]] debt is already about. Supplying a scrubbed env at the boundary means an env
 * genuinely IS supplied, the flag keeps its own meaning, and the guard stays live for every path
 * that still supplies none.
 *
 * EVIDENCE STRENGTH, stated rather than implied. The `main.js` assertions are SOURCE PINS and are
 * the weaker half, for the reason `runtime-honesty-wiring.test.js` gives: `main.js` cannot be
 * required in a test ([[U338]]) because it pulls in electron. They run against an executable-only
 * view with comments blanked, so this file's own prose cannot satisfy them. The credential
 * classifier is the STRONGER half and is driven behaviourally through `conductor/launch-source.js`,
 * which is require-able.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { scrubCredentialEnv, isCredentialEnvName } = require("../conductor/launch-source");

const MAIN = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");

const slice = (source, from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start > 0 && end > start, `could not locate ${from} … ${to}`);
  return source.slice(start, end);
};

/** Whole-line and block comments removed — the same helper `runtime-honesty-wiring.test.js` uses,
 *  for the same reason: a pin that matches a phrase anywhere in the region is otherwise satisfied by
 *  the region's own prose. */
const executableOnly = (region) =>
  region.replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n");

// ---- (a) the renderer spec is an ALLOW-list ---------------------------------------------------

test("W-29 NEGATIVE: a renderer-supplied `file` and `args` cannot reach the pty spawn", () => {
  const region = executableOnly(slice(MAIN, "const RENDERER_SPEC_ALLOWED_KEYS", "let paneSeq"));

  // The allow-list is read out of the shipped bytes and asserted as DATA, not matched as prose.
  const literal = /const RENDERER_SPEC_ALLOWED_KEYS\s*=\s*Object\.freeze\(\[([^\]]*)\]\)/.exec(region);
  assert.ok(literal, "sanitizeRendererSpec must be driven by a named, frozen allow-list constant");
  const allowed = literal[1].split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);

  for (const forbidden of ["file", "args", "env", "cwd"]) {
    assert.ok(!allowed.includes(forbidden),
      `\`${forbidden}\` is in the renderer allow-list — a renderer that sets it chooses what the `
      + "host executes, or what the child inherits");
  }
  assert.ok(allowed.length > 0, "an empty allow-list would break every legitimate pane");

  // The sanitiser must BUILD from the allow-list. A deny-list that merely deletes more names is the
  // defect this unit closes: the next field added to a spec is permitted by default.
  assert.match(region, /for\s*\(const key of RENDERER_SPEC_ALLOWED_KEYS\)/,
    "the sanitiser must copy only allow-listed keys, not delete a fixed set of bad ones");
  assert.ok(!/delete\s+clean\.(env|cwd)/.test(region),
    "the deny-list deletions must be GONE, not kept alongside the allow-list — two mechanisms for "
    + "one decision is how the next field gets missed");
});

test("W-29 POSITIVE: the fields a renderer legitimately owns still survive", () => {
  const region = executableOnly(slice(MAIN, "const RENDERER_SPEC_ALLOWED_KEYS", "let paneSeq"));
  const literal = /const RENDERER_SPEC_ALLOWED_KEYS\s*=\s*Object\.freeze\(\[([^\]]*)\]\)/.exec(region);
  const allowed = literal[1].split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
  for (const field of ["title", "cols", "rows"]) {
    assert.ok(allowed.includes(field),
      `\`${field}\` is presentation the renderer owns; dropping it would break pane creation`);
  }
});

// ---- (b) the default pane's environment is scrubbed -------------------------------------------

test("W-29 NEGATIVE: the `pane:new` boundary supplies a scrubbed env, so no pane inherits verbatim", () => {
  const handler = executableOnly(slice(MAIN, 'ipcMain.handle("pane:new"', "\n  ipcMain.handle"));
  assert.match(handler, /scrubCredentialEnv\(process\.env\)/,
    "pane:new must hand the session an explicitly scrubbed environment. Without it, sanitising away "
    + "`env` triggers ptyFactory's `{ ...process.env }` fallback and the child inherits EVERYTHING — "
    + "the sanitiser makes the leak instead of closing it");
  assert.match(handler, /sanitizeRendererSpec\(spec\)/,
    "the renderer spec must still be sanitised — the env must not be reachable as an override");
  // Order matters: the governance-supplied env must not be overridable by a spread of the
  // renderer's own object placed after it.
  assert.ok(handler.indexOf("sanitizeRendererSpec(spec)") < handler.indexOf("scrubCredentialEnv"),
    "the scrubbed env must be applied AFTER the renderer spec, or a renderer key could overwrite it");
});

// ---- the classifier itself, driven behaviourally ----------------------------------------------

test("W-29 NEGATIVE: a credential-classified name never survives into a pane environment", () => {
  const shellEnv = {
    PATH: "C:\\Windows",
    USERPROFILE: "C:\\Users\\op",
    XAI_API_KEY: "planted-not-a-real-value",       // exact authority name
    GROK_API_KEY: "planted-not-a-real-value",      // exact authority name
    NODE_OPTIONS: "--require evil",                // injects into an npm-installed Node CLI
    NODE_EXTRA_CA_CERTS: "C:\\proxy.pem",          // trusts an interception proxy
    ANTIGRAVITY_SOMETHING: "x",                    // caught by PREFIX
    MY_SESSION_TOKEN: "x",                         // caught by SUBSTRING
    SOME_PASSWORD: "x",                            // caught by SUBSTRING
    IPC_KEY: "x",                                  // the shell's own control-channel material
  };
  const scrubbed = scrubCredentialEnv(shellEnv);

  for (const leaked of ["XAI_API_KEY", "GROK_API_KEY", "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS",
    "ANTIGRAVITY_SOMETHING", "MY_SESSION_TOKEN", "SOME_PASSWORD", "IPC_KEY"]) {
    assert.ok(!(leaked in scrubbed), `${leaked} survived into a pane environment`);
  }
  // A scrub that empties the environment proves nothing about the scrub — the same reasoning
  // `childEnvIsScrubbed` applies to PATH.
  assert.strictEqual(scrubbed.PATH, "C:\\Windows", "PATH must survive or no pane can run");
  assert.strictEqual(scrubbed.USERPROFILE, "C:\\Users\\op", "non-secret vars must survive");
  // Purity: the caller's object is never mutated.
  assert.ok("XAI_API_KEY" in shellEnv, "scrubCredentialEnv must not mutate its input");
});

test("W-29: the classifier is case-insensitive, as Windows env names are", () => {
  // U105's class: Windows treats env names case-insensitively while a plain object delete does not.
  assert.ok(isCredentialEnvName("xai_api_key"));
  assert.ok(isCredentialEnvName("My_Session_Token"));
  const scrubbed = scrubCredentialEnv({ PATH: "p", xai_api_key: "x", Some_Secret: "y" });
  assert.ok(!("xai_api_key" in scrubbed) && !("Some_Secret" in scrubbed),
    "a lower- or mixed-case credential name is the same variable to the OS");
});

test("W-29: GROK_SANDBOX is preserved, on recorded evidence rather than by analogy", () => {
  // The one documented exemption in the Python authority: `--sandbox <PROFILE>`'s env form. A
  // scrubber that removes the sandbox is not a safety feature (U265).
  assert.ok(!isCredentialEnvName("GROK_SANDBOX"),
    "GROK_SANDBOX is the containment lever the CLI exposes; stripping it downgrades the operator");
  assert.strictEqual(scrubCredentialEnv({ GROK_SANDBOX: "strict" }).GROK_SANDBOX, "strict");
});
