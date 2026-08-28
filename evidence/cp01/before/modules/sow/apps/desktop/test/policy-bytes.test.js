"use strict";
/**
 * Phase 17C `.disarm-authority` (U181) — the boundary's own bytes live in the supervised child's
 * writable workspace, and were hashed once at launch.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const fs = require("node:fs");

const { ConductorPolicyBytes } = require("../voice/policy-bytes");
const { SupervisorVoiceTurnAuthority } = require("../voice/turn-authority");

const HOOK = "D:/repo/tools/live/voice_turn_boundary.js";
const MODULE = "D:/repo/apps/desktop/voice/turn-authority.js";

function disk(initial) {
  const files = { ...initial };
  return {
    files,
    readFile: (file) => {
      if (!(file in files)) throw new Error("ENOENT");
      return Buffer.from(files[file], "utf8");
    },
  };
}

test("a policy file rewritten under the running session refuses the next dispatch", () => {
  const d = disk({ [HOOK]: "original hook", [MODULE]: "original module" });
  const policy = new ConductorPolicyBytes({ files: [HOOK, MODULE], readFile: d.readFile });
  assert.equal(policy.pin().ok, true);
  assert.equal(policy.verify().ok, true);

  // the attended CLI rewrites the transport it is supposed to be constrained by
  d.files[HOOK] = "original hook // and an early return";
  const v = policy.verify();
  assert.equal(v.ok, false);
  assert.deepEqual(v.changed, [HOOK]);
  assert.match(v.reason, /changed under the running session/);

  // …and the module the hook requires counts as the boundary too
  d.files[HOOK] = "original hook";
  assert.equal(policy.verify().ok, true);
  d.files[MODULE] = "module.exports = {};";
  assert.equal(policy.verify().ok, false);
});

test("an unreadable policy file is a refusal, not an absence of evidence", () => {
  const d = disk({ [HOOK]: "hook" });
  const policy = new ConductorPolicyBytes({ files: [HOOK], readFile: d.readFile });
  assert.equal(policy.pin().ok, true);
  delete d.files[HOOK];
  const v = policy.verify();
  assert.equal(v.ok, false);
  assert.match(v.reason, /unreadable at dispatch/);
  // …and a file that cannot be read at PIN time refuses the launch rather than pinning nothing
  const fresh = new ConductorPolicyBytes({ files: [HOOK], readFile: d.readFile });
  assert.equal(fresh.pin().ok, false);
  assert.equal(fresh.verify().pinned, false);
});

test("bytes that changed between the launch ticket and the spawn are refused, never adopted", () => {
  const d = disk({ [HOOK]: "the authorized hook" });
  const policy = new ConductorPolicyBytes({ files: [HOOK], readFile: d.readFile });
  const wrong = policy.pin({ [HOOK]: "f".repeat(64) });
  assert.equal(wrong.ok, false);
  assert.match(wrong.reason, /between the launch ticket and the spawn/);
  assert.equal(policy.state().pinned, false, "a refused pin must not become the baseline");
  // the ticket's own hash of the same bytes pins cleanly
  const right = new ConductorPolicyBytes({ files: [HOOK], readFile: d.readFile });
  const hash = require("node:crypto").createHash("sha256").update("the authorized hook").digest("hex");
  assert.equal(right.pin({ [HOOK]: hash.toUpperCase() }).ok, true);
});

test("with nothing pinned the check says so, and never claims a boundary it has not seen", () => {
  const policy = new ConductorPolicyBytes({ files: [HOOK], readFile: disk({}).readFile });
  const v = policy.verify();
  assert.equal(v.ok, true);
  assert.equal(v.pinned, false);
  assert.match(v.reason, /no governed conductor launch/);
  assert.equal(policy.state().hashes, null);
});

test("the authority service refuses every authority-bearing event while the policy is unverified", () => {
  const d = disk({ [HOOK]: "hook" });
  const policy = new ConductorPolicyBytes({ files: [HOOK], readFile: d.readFile });
  policy.pin();
  const authority = new SupervisorVoiceTurnAuthority({
    token: "c".repeat(64),
    verifyPolicy: () => policy.verify(),
  });
  const armed = authority.arm("speak");
  d.files[HOOK] = "rewritten by the attended CLI";
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "UserPromptSubmit", session_id: "s", prompt: armed.payload },
  }).output.decision, "block");
  assert.equal(authority.handle({
    token: authority.token,
    input: { hook_event_name: "PreToolUse", session_id: "s", tool_name: "Bash" },
  }).output.hookSpecificOutput.permissionDecision, "deny");
  assert.ok(authority.snapshot().audit.some((r) => r.event === "policy_bytes_unverified"));
});

test("the files main pins are the ones that actually carry the boundary", () => {
  // Not a mock: the real paths must exist, and the hook must really require the module — a pin over a
  // file the transport does not use would verify bytes nobody executes.
  const repo = path.resolve(__dirname, "..", "..", "..");
  const hook = path.join(repo, "tools", "live", "voice_turn_boundary.js");
  const mod = path.join(repo, "apps", "desktop", "voice", "turn-authority.js");
  for (const f of [hook, mod]) assert.ok(fs.existsSync(f), `${f} is missing`);
  assert.match(fs.readFileSync(hook, "utf8"), /require\(\s*"\.\.\/\.\.\/apps\/desktop\/voice\/turn-authority"\s*\)/);
  const real = new ConductorPolicyBytes({ files: [hook, mod] });
  assert.equal(real.pin().ok, true);
  assert.equal(real.verify().ok, true);
});
