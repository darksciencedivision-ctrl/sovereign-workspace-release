# PHASE 0 EVIDENCE REPORT — Canonical freeze & repo foundation
**Date:** 2026-07-16 · **Builder:** Claude (Fable 5) in Cowork, staged-gated authorization
(operator "build it", 2026-07-16) · **Format:** Buildout Directive §6

## Objective
Execute Phase 0 per Buildout Directive §5 and Plan §15: verify and freeze the canonical
set, create the isolated repo with guardrails, freeze the @1.0 schemas, seed registers,
declare conductor files + write authority, produce the freeze manifest. No product code.

## Source state
Handoff bundle at `D:\multi model terminal app\` — all 21 files verified against
`MANIFEST.sha256` (hash+size exact, 0 mismatches) before any write. Build source
confirmed: Architecture Plan v1.0.1_UTF8 `8C9B7240…3300022` (0 mojibake sequences);
original v1.0 `668089B5…E199E48F` re-hashed **after** Phase 0 writes — byte-identical,
untouched. ChatGPT v3.0 manifest self-hashes verified; provenance chain to the v2.3
archive hash confirmed.

## Files created (60 tracked files in work commit)
`docs/canonical/` (11, byte-identical copies — hashes re-verified on copy);
`schemas/` (12 × @1.0 + README); `conductor/` (12 × DRAFT v0.1);
`docs/registers/` (2); `docs/THREAT_MODEL.md`; `docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md`;
`docs/PHASE0_FREEZE_MANIFEST.json`; `.claude/` (settings.json, hooks/guard.py, 2 agents);
`CLAUDE.md`; `README.md`; `tools/manifest/compute_manifest.py`;
`tests/unit/test_schemas.py`; scaffolding dirs with `.gitkeep`.

## Commands run & test results
- `python -m pytest tests/ -q` → **34 passed** (12 schema-compile, 12 valid-instance,
  8 invalid-instance rejections incl. debate rounds >5, worker self-canonize status,
  unsigned envelope, non-deny default stance; 2 structural).
- `python tools/manifest/compute_manifest.py` → manifest written;
  `freeze_integrity_sha256 = 696F2276629F9AC4D037480AE145AF4A23ED5DF402E3960EC27EA62F96F57E1C`;
  `--check` → no drift.
- `python -m py_compile` on guard hook + manifest tool → clean.

## Performance measurements
Not applicable to Phase 0 (documentation/schema phase). First measured phase is P1.

## Deviations from plan (all recorded, none semantic)
1. **Schema `$id` namespace:** `https://sovereign.local/schemas/<name>@1.0` instead of a
   custom `sovereign://` scheme — Python's URI resolution (jsonschema 3.2/urljoin)
   mishandles unknown schemes for internal `#/definitions` refs. Runtime MCP **resource**
   namespace `sovereign://…` (Plan §9.5) is unaffected. Schema mechanics only.
2. **Repo location:** inside the mounted handoff folder (only persistent location
   available to the build session); isolation from other Sovereign repos is structural
   (they are not mounted).
3. **Environment (register E1–E3):** mount corrupts git lock/rename → git-dir kept
   sandbox-local, `.git/` mirrored by plain copy after gate commits + `git fsck`;
   sandbox Python 3.10 (target 3.12 unaffected at P0); P1 metrics require operator's
   Windows run.
4. **Two-commit gate convention:** work commit → evidence report commit (carries the work
   hash) → tag on the evidence commit, so the report can record a real hash.

## Unresolved issues
U1–U12 seeded, all OPEN except U8 (first pass done). PENDING-OPERATOR decisions recorded
with owning gates: I-D1/I-D2 + D-COWORK-02 (this freeze), D-UI-01 (after P1), D-LANG-01,
D-PERSIST-01 (provisional defaults recorded), D-MCP-03 (P3A), D-IPC-01.

## Gate verdict — self-check: PASS (7/7) · operator signature: OUTSTANDING
| Criterion (Directive §5-P0) | Check | Result |
|---|---|---|
| Canonical artifacts located; paths/sizes/sha256/encodings recorded | freeze manifest `contents` | ✅ |
| Building from `8C9B7240…`; `668089B5…` preserved untouched | re-hash after writes | ✅ byte-identical |
| Isolated repo + CLAUDE.md + .claude config/hooks | G4 listing | ✅ |
| Conductor files + @1.0 schemas (12) | G2/G5; 34 tests | ✅ |
| Decision + unresolved registers; threat model | G5 | ✅ |
| Test scaffolding | pytest green | ✅ |
| **No product code** | G3/G7: only manifest tool, guard hook, tests; impl dirs empty | ✅ |

Per Plan §15 the Phase 0 **exit** gate is operator-reserved: **signature on
`docs/PHASE0_FREEZE_MANIFEST.json`** (instructions inside the file). Ratification of
I-D1/I-D2 + D-COWORK-02 may accompany it. Build proceeds to Phase 1 (spike is throwaway
tooling, not product UI) with the signature surfaced as outstanding; nothing after Phase 1
proceeds without it.

## Commit
Work commit: `bcd2c4ff2cabca10e4f2512e5a2f1c8a9a8f5b35` — evidence commit (this file)
tagged `gate/phase-0`.

## Next phase
Phase 1 — terminal compositor spike (`tools/spike_compositor/`): Electron + xterm.js +
node-pty rig, ≥6 ConPTY sessions, metrics + kill criteria. Sandbox delivers rig +
headless tests; **operator runs the measured spike on the Windows host**; gate =
operator ratifies D-UI-01.

---
## ERRATA (appended 2026-07-16, after independent gate-validator review)

- **E-1 (validator F1 — gate criterion 8 FAIL, now remediated):** the original freeze
  manifest included `docs/registers/*.md` in the frozen integrity set. Registers are
  append-only by design and legitimately change at every gate; the gate-commit's register
  append therefore broke `--check` at the very commit tagged `gate/phase-0`, and the
  signature the operator was being asked to provide would have covered a self-invalidating
  manifest. Fix: `compute_manifest.py` rescoped — registers + evidence reports moved to a
  `mutable_audit_files` section (hashes recorded for visibility, excluded from
  `freeze_integrity_sha256`; frozen-set drift still hard-fails, negative-tested).
  Manifest regenerated: **new freeze_integrity_sha256 =
  `198B319BA86394AE993ECDB9DECC71EC8991802DB5443587B8E45B4C47B12F4E`** — this is the value
  the operator signs. Corrected state tagged `gate/phase-0.1`; the original `gate/phase-0`
  tag is retained as history, not deleted.
- **E-2 (validator F3):** "60 tracked files" was wrong. Actual work-commit tree: 110
  tracked files (53 content + 57 `.gitkeep` placeholders).
