"use strict";
/**
 * W-32 — the two-stage credential scrub, with the ticket-name guard BETWEEN the stages.
 *
 * The ordering is the unit. Operator ruling:
 *
 *   shell env
 *     -> [1] scrubbedLaunchEnv(ticket, env)      injectable, UNCHANGED pure fold
 *     -> [2] ticket-name leftover guard          REFUSE; stays BEFORE the classifier
 *     -> [3] credential-classifier scrub         non-injectable; NODE_PATH and family
 *     -> [4] classifier assertion on the FINAL child env   REFUSE
 *     -> child
 *
 * WHY NOT ONE SCRUBBER. Both collapses were considered and are forbidden, because both kill a live
 * guard rather than merely being untidy:
 *
 *   - Making `scrubbedLaunchEnv` itself the classifier breaks what it PROVES. Its contract is "drop
 *     the ticket-declared names and NOTHING ELSE", and `conductor-launch-selfcheck.js:138-143`
 *     publishes a receipt on exactly that claim. A union still computes that field true (its probe
 *     is PATH/KEEP_ME, neither classifier-positive) while the claim became false — the receipt would
 *     lie.
 *   - Cleaning credentials BEFORE the injected scrub sees them makes the fault-injection guard
 *     toothless. `worker-spawn.js:109-111` declares the scrub injectable for one reason: a caller
 *     that injects a weaker scrub must TRIP the leftover check at `:303`. If the classifier tidies
 *     up first, the guard can never fire.
 *
 * Stage 4 exists because stage 3 running is not the same fact as the child being clean, and the
 * review found that distinction being lost elsewhere ("measured in the wrong process").
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { createWorkerPaneLauncher } = require("../picker/worker-spawn");
const { SHELL_MINTED_CAPABILITY_NAMES } = require("../conductor/launch-source");

const MAIN = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");
const slice = (source, from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start > 0 && end > start, `could not locate ${from} … ${to}`);
  return source.slice(start, end);
};
const executableOnly = (region) =>
  region.replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n");

const CHROME = { governed: true, interactive: true, role: "worker", provider: "ollama",
  model_slug: "qwen3:8b", adapter: "ollama_local", locality: "local", model_label: "Qwen3 8B" };

function ticket() {
  return {
    authorized: true,
    launch: {
      argv: ["ollama", "run", "qwen3:8b"], executable: "C:/bin/ollama.exe",
      cwd: "C:/workspace", interactive: true, one_shot: false,
      env_scrub_names: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"], env_credential_scrubbed: true,
    },
    chrome: CHROME,
    identity: { node_id: "worker-pane-2", permission_profile_id: "pp-worker-reasoning",
      session_id: "pane-2#1.1", pane_id: "pane-2", subscription_ref: "sub-ollama" },
    lease: { lease_id: "lease-1", durable: true, in_use: 1, allowance: 2,
      subscription_ref: "sub-ollama", session_id: "pane-2#1.1" },
    subscription_governed: true, residency: null,
  };
}

const SELECTION = { option: { provider: "ollama", label: "qwen3:8b", adapter: "ollama_local",
  locality: "local", available: true, roles: ["reasoning"] }, role: "reasoning", mode: "attended" };

function harness(opts = {}) {
  const calls = { spawns: [], releases: [] };
  const launcher = createWorkerPaneLauncher({
    repoRoot: "C:/repo",
    holderPid: 4242,
    baseEnv: opts.baseEnv || { PATH: "C:/bin", KEEP_ME: "k" },
    isSupervised: () => true,
    hasLiveSession: () => false,
    ...(opts.scrubEnv ? { scrubEnv: opts.scrubEnv } : {}),
    augmentSpawnEnv: opts.augmentSpawnEnv
      || ((env) => ({ ...env, SOVEREIGN_CONTROL_PORT: "3210", SOVEREIGN_CONTROL_TOKEN: "opaque" })),
    sourceTicket: async () => ({ ok: true, ticket: ticket() }),
    releaseTerminal: async (sid) => { calls.releases.push(sid); return { ok: true, released: true }; },
    spawnSession: (args) => { calls.spawns.push(args); return { pid: 111, generation: 1 }; },
    processIdentity: () => ({ pid: 111, generation: 1 }),
    attestSpawn: async () => ({ ok: true }),
  });
  return { launcher, calls };
}

const childEnvOf = (calls) => calls.spawns[0].spec.env;

// ---- 1. the guard fires BEFORE the classifier can clean up the evidence -----------------------

test("W-32 (1) NEGATIVE: a weak injected ticket scrub is REFUSED by the leftover guard", async () => {
  // The injected scrub drops nothing. ANTHROPIC_API_KEY is ticket-declared AND classifier-positive,
  // which is exactly what makes this test discriminating: if the classifier ran first it would
  // remove the name, the ticket guard would find nothing, stage 4 would pass, and the spawn would
  // SUCCEED. A successful launch here means the stages were collapsed.
  const { launcher, calls } = harness({
    baseEnv: { PATH: "C:/bin", ANTHROPIC_API_KEY: "planted-not-real" },
    scrubEnv: (_ticket, base) => ({ ...base }),
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false, "a child env carrying a ticket-declared credential must not spawn");
  assert.match(String(res.reason), /credential scrub left/,
    "the refusal must come from the TICKET-name guard. Any other refusal means the classifier "
    + "reached the environment first and the fault-injection guard is dead");
  assert.equal(calls.spawns.length, 0, "no process may be created");
});

// ---- 2-4. normal execution ---------------------------------------------------------------------

test("W-32 (2) the ticket-declared credentials are removed on the normal path", async () => {
  const { launcher, calls } = harness({
    baseEnv: { PATH: "C:/bin", KEEP_ME: "k", ANTHROPIC_API_KEY: "x", OPENAI_API_KEY: "y" },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, true);
  const env = childEnvOf(calls);
  assert.ok(!("ANTHROPIC_API_KEY" in env) && !("OPENAI_API_KEY" in env));
});

test("W-32 (3) NEGATIVE: stage 3 removes what NO ticket declares — NODE_PATH and family, mixed case", async () => {
  // None of these is in `env_scrub_names`, so stage 1 cannot touch them. They reach the child unless
  // the classifier stage exists. NODE_PATH is the name this unit adds to the authority.
  const { launcher, calls } = harness({
    baseEnv: {
      PATH: "C:/bin", KEEP_ME: "k",
      NODE_PATH: "C:/evil/modules",          // redirects require() in an npm-installed Node CLI
      NODE_OPTIONS: "--require C:/evil.js",  // injects a module into the child
      NODE_EXTRA_CA_CERTS: "C:/proxy.pem",   // trusts an interception proxy
      node_path: "C:/evil/lower",            // Windows: the same variable to the OS
      Xai_Api_Key: "mixed-case-planted",
    },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  // Named, because there are TWO ways this goes red and a reader must be able to tell them apart:
  // stage 3 missing entirely means stage 4 refuses the launch here (defence in depth doing its
  // job), while stage 3 present but incomplete lets a name through to the per-name checks below.
  assert.equal(res.launched, true,
    `the classifier stage must remove NODE_PATH and family before the child is spawned `
    + `(refused instead: ${res.reason || "no reason given"})`);
  const env = childEnvOf(calls);
  for (const name of ["NODE_PATH", "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS", "node_path", "Xai_Api_Key"]) {
    assert.ok(!(name in env), `${name} reached the child environment`);
  }
});

test("W-32 (4) benign names survive — a scrub that empties the env proves nothing", async () => {
  const { launcher, calls } = harness({
    baseEnv: { PATH: "C:/bin", KEEP_ME: "k", USERPROFILE: "C:/Users/op" },
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, true);
  const env = childEnvOf(calls);
  assert.equal(env.PATH, "C:/bin");
  assert.equal(env.KEEP_ME, "k");
  assert.equal(env.USERPROFILE, "C:/Users/op");
  // The capability the SHELL mints for this child is not an inherited credential and must survive.
  assert.equal(env.SOVEREIGN_CONTROL_TOKEN, "opaque");
});

// ---- 6. the assertion examines the environment ACTUALLY handed to the child --------------------

test("W-32 (6) NEGATIVE: stage 4 refuses a credential injected AFTER the scrub stages", async () => {
  // A compromised or buggy augmenter is the only way a classifier-positive name can appear after
  // stage 3. If stage 4 measured an intermediate env instead of the real one, this would spawn.
  const { launcher, calls } = harness({
    baseEnv: { PATH: "C:/bin" },
    augmentSpawnEnv: (env) => ({ ...env, SOVEREIGN_CONTROL_TOKEN: "opaque", XAI_API_KEY: "injected" }),
  });
  const res = await launcher.launchWorkerPane({ paneId: "pane-2", selection: SELECTION });
  assert.equal(res.launched, false, "a credential in the FINAL child env must refuse the spawn");
  assert.match(String(res.reason), /credential-classified/,
    "the refusal must name the classifier stage, not the ticket stage");
  assert.equal(calls.spawns.length, 0);
});

test("W-32 (6b) the shell-minted capability set is enumerated and narrow, not 'whatever was added'", () => {
  // Exempting everything the augmenter added would make the test above impossible to fail, which is
  // the U367 shape: a guard that cannot fire. The exemption is a NAMED list, the same way
  // PRESERVED_PROVIDER_CONFIG_KEYS exempts GROK_SANDBOX on recorded evidence.
  assert.ok(Array.isArray(SHELL_MINTED_CAPABILITY_NAMES));
  assert.ok(SHELL_MINTED_CAPABILITY_NAMES.includes("SOVEREIGN_CONTROL_TOKEN"));
  // The conductor's voice authority mints four names that all match the AUTH substring; without
  // them a Claude-hook conductor launch would be refused by its own shell.
  for (const n of ["SOW_VOICE_AUTH_HOST", "SOW_VOICE_AUTH_PORT", "SOW_VOICE_AUTH_TOKEN",
    "SOW_VOICE_AUTH_SCHEMA"]) {
    assert.ok(SHELL_MINTED_CAPABILITY_NAMES.includes(n), `${n} is minted by the shell and must be exempt`);
  }
  assert.ok(SHELL_MINTED_CAPABILITY_NAMES.length <= 8, "this list is an exemption, not a policy system");
});

// ---- the conductor path gets the same ordering -------------------------------------------------

test("W-32 the CONDUCTOR path has the ticket guard, and it sits before the classifier", () => {
  const region = executableOnly(slice(MAIN, "let env = scrubbedLaunchEnv(ticket, process.env);",
    "const session = manager.spawn({"));
  assert.match(region, /ticketScrubLeftovers/,
    "the conductor path had NO leftover assertion at all — the worker path's guard was never ported");
  assert.match(region, /scrubCredentialEnv/, "the conductor path must apply the classifier stage");
  assert.ok(region.indexOf("ticketScrubLeftovers") < region.indexOf("scrubCredentialEnv"),
    "the ticket guard must run BEFORE the classifier, or the classifier cleans up the evidence the "
    + "guard exists to find");
});

test("W-32 the conductor's stage 4 runs on the env it actually spawns with", () => {
  const region = executableOnly(slice(MAIN, "let env = scrubbedLaunchEnv(ticket, process.env);",
    "const session = manager.spawn({"));
  // Both minting steps must precede the assertion, or it is measuring an intermediate.
  assert.ok(region.indexOf("sovereignControl.childEnv") < region.lastIndexOf("credentialNamesIn"),
    "stage 4 must come after the shell mints the child's capabilities, or it is not examining the "
    + "environment handed to the child");
});
