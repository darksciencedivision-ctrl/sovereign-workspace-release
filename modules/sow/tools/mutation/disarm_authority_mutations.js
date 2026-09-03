"use strict";
/**
 * Falsification harness for the Phase 17C `.disarm-authority` fixes (U178, U181, U185, U182, U180).
 *
 * Same contract as `pane_input_bypass_mutations.js`: apply one known removal of a guard, run ONLY the
 * test file that is supposed to see it, record whether the suite goes red, restore the file
 * BYTE-IDENTICALLY, and exit non-zero if any mutation stays green or any restore does not reproduce
 * the original hash. A guard that has never been shown to fail is not a guard.
 *
 * Run from the repo root: `node tools/mutation/disarm_authority_mutations.js`
 * (or `npm run test:falsify:authority` from apps/desktop).
 *
 * It writes to product files, so the originals are held in memory and restored from `finally` and
 * from the signal/exception paths. It lives outside every declared product path.
 */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");

const REPO = path.resolve(__dirname, "..", "..");
const DESKTOP = path.join(REPO, "apps", "desktop");
const LOCK = path.join(__dirname, ".disarm-authority.lock");

const AUTHORITY = path.join(DESKTOP, "voice", "turn-authority.js");
const POLICY = path.join(DESKTOP, "voice", "policy-bytes.js");
const MIC = path.join(DESKTOP, "selfcheck", "voice-mic-selfcheck.js");
const WRITE = path.join(DESKTOP, "voice", "conductor-write.js");
const INDICATOR = path.join(REPO, "terminal", "compositor", "voice-indicator.js");

/**
 * Each mutation: the file it edits, a `find`/`replace` pair that must apply EXACTLY ONCE, and the
 * suite that must go red. `cwd` is the package the suite belongs to.
 */
const MUTATIONS = [
  {
    id: "U178-A", what: "the ended turn stops denying tools (the defect itself)",
    file: AUTHORITY, test: ["test/voice-turn-authority.test.js"], cwd: DESKTOP,
    find: "const restricted = Boolean(this._pending || this._active || this._ended);",
    replace: "const restricted = Boolean(this._pending || this._active);",
  },
  {
    id: "U178-B", what: "the disarm clears the turn outright instead of ending it",
    file: AUTHORITY, test: ["test/voice-turn-authority.test.js"], cwd: DESKTOP,
    find: "    this._ended = active\n      ? { turn_id: turnId, session_id: active.session_id || null, "
      + "ended_at: this._now(), source: key }\n      : null;",
    replace: "    this._ended = null;",
  },
  {
    id: "U178-C", what: "the ended state is never released, so the operator's own prompts stay denied",
    file: AUTHORITY, test: ["test/voice-turn-authority.test.js"], cwd: DESKTOP,
    find: "      if (this._ended) {\n        const ended = this._ended;\n        this._ended = null;",
    replace: "      if (false) {\n        const ended = this._ended;",
  },
  {
    id: "U178-D", what: "the chrome goes blank while the denial is still running",
    file: INDICATOR, test: ["test/voice-indicator.test.js"], cwd: path.join(REPO, "terminal"),
    find: "  const endedDenying = !restricted && t.tools_denied === true;",
    replace: "  const endedDenying = false;",
  },
  {
    id: "U181-A", what: "policy bytes are verified once and never again",
    file: POLICY, test: ["test/policy-bytes.test.js"], cwd: DESKTOP,
    find: "      if (current !== hash) changed.push(file);",
    replace: "      if (false) changed.push(file);",
  },
  {
    id: "U181-B", what: "an unverified policy is not a refusal",
    file: AUTHORITY, test: ["test/policy-bytes.test.js", "test/voice-turn-authority.test.js"], cwd: DESKTOP,
    find: "    const unverified = this._policyVerified();\n    if (unverified) return failClosedHookResult(event, unverified);",
    replace: "    this._policyVerified();",
  },
  {
    id: "U181-C", what: "a verifier that throws is treated as consent",
    file: AUTHORITY, test: ["test/voice-turn-authority.test.js"], cwd: DESKTOP,
    find: "      verdict = { ok: false, reason: `the policy bytes could not be read: ${(e && e.message) || e}` };",
    replace: "      verdict = { ok: true };",
  },
  {
    id: "U182", what: "the audit grows without bound again",
    file: AUTHORITY, test: ["test/voice-turn-authority.test.js"], cwd: DESKTOP,
    find: "    while (this.audit.length > this._auditLimit) {",
    replace: "    while (false) {",
  },
  {
    id: "U180", what: "the delivery claims a submission the vendor never reported",
    file: WRITE, test: ["test/conductor-write.test.js"], cwd: DESKTOP,
    find: "           submission_basis: \"vendor_reported\",",
    replace: "",
  },
  {
    id: "U179", what: "the manual-mode pane is trusted on vendor chrome alone again",
    file: WRITE, test: ["test/conductor-write.test.js"], cwd: DESKTOP,
    // ANCHOR RESTORED. This mutation had gone quiet: its `find` was the single-line form
    // `{ supervisorBoundary: supervisorEnforcedBoundary(readBoundary()) });`, and LOCAL-01 F-3
    // (39079f6, "the Conductor seat is agnostic") added the local-conductor disjunct, wrapping the
    // expression onto two lines. The harness reported it honestly — "its anchor matched 0 times in
    // conductor-write.js" — and kept exiting non-zero, but the PROOF was no longer being taken:
    // Guard 3's re-read could have been deleted and this suite would not have noticed.
    //
    // The mutation's intent is unchanged, which is what makes it worth repairing rather than
    // dropping. Guard 1 has already checked the boundary; Guard 3 RE-READS it because the
    // authority service can stop between the two, and a manual-mode pane with no live restriction
    // is exactly what `paneAcceptsTypedText` refuses. Replacing the whole re-read with `true`
    // restores the defect — the pane trusted on vendor chrome alone — across BOTH boundary kinds,
    // so the repaired anchor grades the frontier and local paths together rather than silently
    // grading only the half that existed when it was written.
    find: "    { supervisorBoundary: supervisorEnforcedBoundary(readBoundary())\n"
      + "        || localNonExecutingBoundary(readBoundary()) });",
    replace: "    { supervisorBoundary: true });",
  },
  {
    id: "U185", what: "the second fixture caller can reach the OS synthesizer unguarded",
    file: MIC, test: ["test/selfcheck-guards.test.js"], cwd: DESKTOP,
    find: "    if (!process.env.SHELL_SELFCHECK) {\n      resolve({ ok: false, error: \"refusing to "
      + "synthesize outside a self-check run (I-V2/D-VOICE-02)\" });\n      return;\n    }\n",
    replace: "",
  },
];

let lockFd;
try {
  lockFd = fs.openSync(LOCK, "wx");
} catch (e) {
  if (e.code === "EEXIST") {
    console.error(`another run holds ${LOCK}. If none is running, the files below may be MUTATED:`);
    for (const f of new Set(MUTATIONS.map((m) => m.file))) console.error(`  ${f}`);
    process.exit(3);
  }
  throw e;
}

const ORIGINAL = new Map();
for (const file of new Set(MUTATIONS.map((m) => m.file))) ORIGINAL.set(file, fs.readFileSync(file));
const hashOf = (buf) => crypto.createHash("sha256").update(buf).digest("hex").toUpperCase();

function restoreAll() {
  for (const [file, bytes] of ORIGINAL) fs.writeFileSync(file, bytes);
}
process.on("SIGINT", () => { restoreAll(); try { fs.unlinkSync(LOCK); } catch { /* gone */ } process.exit(130); });

let failures = 0;
try {
  for (const m of MUTATIONS) {
    const src = ORIGINAL.get(m.file).toString("utf8");
    const hits = src.split(m.find).length - 1;
    if (hits !== 1) {
      console.error(`SKIPPED ${m.id}: its anchor matched ${hits} times in ${path.basename(m.file)} — `
        + "the mutation no longer describes the code it was written against");
      failures += 1;
      continue;
    }
    fs.writeFileSync(m.file, src.replace(m.find, m.replace));
    const run = spawnSync(process.execPath, ["--test", ...m.test], { cwd: m.cwd, encoding: "utf8" });
    restoreAll();
    const caught = run.status !== 0;
    console.log(`${caught ? "CAUGHT " : "GREEN  "} ${m.id.padEnd(7)} ${m.what}`);
    if (!caught) failures += 1;
  }
} finally {
  restoreAll();
  try { fs.closeSync(lockFd); fs.unlinkSync(LOCK); } catch { /* already gone */ }
}

let restoreFailed = false;
for (const [file, bytes] of ORIGINAL) {
  const now = fs.readFileSync(file);
  const ok = now.equals(bytes);
  if (!ok) restoreFailed = true;
  console.log(`restored ${path.relative(REPO, file)} SHA-256 ${hashOf(now)} — `
    + `${ok ? "BYTE-IDENTICAL" : "DIFFERENT — RESTORE FAILED"}`);
}
if (failures || restoreFailed) {
  console.error(`${failures} mutation(s) survived or could not be applied`);
  process.exit(1);
}
console.log(`ALL ${MUTATIONS.length} MUTATIONS CAUGHT`);
