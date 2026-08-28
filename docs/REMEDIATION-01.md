# REMEDIATION ORDER REM-01 — SWS-UI-001 v1.2 Build, Round 1

| Field | Value |
|---|---|
| Governing contract | SWS-UI-001 v1.2 — **unchanged and immutable** for this remediation. No v1.3. |
| Basis | `docs/REVIEW-BUILD-01.md` (Claude, disk inspection) + two concurring reviews (Grok, ChatGPT) |
| Assigned builder | DeepSeek V4 Pro, under the restricted authority envelope in §1 |
| Status on issue | Ledger void. Gates 0–2 INVALID, Gate 3 PASS-manifests/INCOMPLETE-git, Gate 4 FAIL. |
| Precondition | §0 completed by the operator. The builder may not begin §2 until `docs/DECISIONS.md` carries an operator-written signature block. |

---

## 0. Operator actions (nobody else may do these)

1. Open `docs/DECISIONS.md`. Its content is a **builder proposal**. Either adopt it by replacing every `By: sam (operator)` line with your own signature block (see `DECISIONS-OPERATOR-TEMPLATE.md`), or change the decisions. Add the line `Prior builder-authored version (sha256 bb911905…) is VOID and was never an authorization.`
2. Check the host clock (`Get-Date -AsUTC`) against a reference. Two artifacts are stamped 2026-08-20 against a directive issued 2026-08-21. Record the finding in DECISIONS.md.
3. Decide, and record in DECISIONS.md: builder continues under §1 envelope — yes / no.
4. Hand REM-01 to the builder only after steps 1–3.

---

## 1. Builder authority envelope (in force for all remaining work)

The builder **may**: implement, run tests, produce evidence, write ADRs, write `STOP-REPORT.md`, and propose gate candidacy.
The builder **may not**: create or edit `docs/DECISIONS.md`; write any `PASS` status into `evidence/GATE-LEDGER.json`; write the operator's name anywhere; treat conversational context, re-sent documents, or silence as authorization; mark its own deviations as approved.

Ledger writes by the builder are limited to `"status": "CANDIDATE"` with evidence paths and full hashes. Only the reviewer writes `PASS`/`FAIL`; only the operator writes Gate 6.

Mandatory closing line of every builder report:

```
BUILDER CLAIM: Gate <N> is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.
```

A report without this line, or with any sentence asserting a gate has passed, is returned unread.

---

## 2. Remediation stages — strict order, each stage ends with a CANDIDATE submission

### R1 — Authority chain reconstruction (builder, after §0)

- Record the new SHA-256 of the operator-signed `DECISIONS.md` in `evidence/phase2-install.txt` under a dated "RE-AUTHORIZATION" heading; leave the original hash line in place annotated `VOID — builder-authored`.
- Rewrite `evidence/GATE-LEDGER.json` to the schema in §3. Gates 0–1: `"status": "CANDIDATE"`, `"authorized_by": "operator"`, evidence = DECISIONS.md with full hash and the operator's UTC. Gates 2–6: `NOT_REACHED`. Every previous entry is deleted, not edited.
- All evidence headers from here on carry `Get-Date -AsUTC` output, ISO 8601 with `Z`.

### R2 — Phase 2/3 integrity repair

| # | Action | Evidence |
|---|---|---|
| R2-1 | `docs/ADR-005-sow-install-and-electron-provisioning.md`: npm 11 lifecycle-script policy, why `npm ci` left `dist/` empty, Electron binary provisioning with the zip's SHA-256, `path.txt`/`dist/version` creation, node-gyp failure (no Windows SDK), node-pty prebuild use, `Reversible:` line. | ADR + `evidence/phase2-sow-install.txt` (captured logs) |
| R2-2 | Replace the manual steps with `shell/tools/install_sow.py` (stdlib only) that performs the exact provisioning — `npm ci`, lifecycle handling, Electron zip fetch-or-use-cache with SHA-256 verification, extraction, `path.txt`/`dist/version`, node-pty prebuild check — logging every action. README calls it. (PowerShell is prohibited as a module *launch* vector, not as tooling; the stdlib script is chosen so one rule covers both.) | script + `evidence/phase2-sow-install.txt` |
| R2-3 | Delete `modules/debate/SOW_REVIEW_ROUND2_RAW/`. Determine and record how it arrived (builder log, not guess; if unknown, say `UNKNOWN`). Re-verify the Debate instance against its `MANIFEST-SHA256.json` with the module's own verification one-liner. | `evidence/phase2-debate-verify.txt` |
| R2-4 | Provenance files: replace `"from MANIFEST-SHA256.json"` / `"see …"` strings with actual 64-hex hashes; add `source_zip_sha256` for Electron. | three JSON files |
| R2-5 | Git capture split: `sow-git-{before,after}.body` (HEAD, status -z, diff, cached diff — no timestamps) + `.meta.json` (utc, `GIT_OPTIONAL_LOCKS`). Byte-identity is asserted on `.body` only. Classification recorded as two booleans `dirty_tracked`, `dirty_untracked`. Re-capture "after" now and again at Gate 5. | files + `evidence/sow-git-body-diff.txt` (must be empty) |
| R2-6 | Ship `evidence/manifests/manifest-diff-{product-software,sow,distillery}.txt` (may be empty files) — the ledger must reference files that exist. | files |
| R2-7 | README rewritten as the from-zero sequence: extract → verify → venv/pip from lock (SOVEREIGN from `WORKSPACE-RESOLVED-LOCK.txt`) → `install_sow.py` → run → test. No "already installed". | README |

Submit: `BUILDER CLAIM: Gates 2 and 3 are CANDIDATES…`

### R3 — Gate 4 engineering

| # | Action | Directive ref |
|---|---|---|
| R3-1 | Test suite self-hosting: `setUpClass` starts the shell on an ephemeral loopback port, waits for readiness, `tearDownClass` stops it. No external precondition. | A-8, B-2 |
| R3-2 | `shell/tests/fixtures/`: `fixture_http.py` (serves `/`, `/health`, configurable identity body, optional exit-after-N-seconds), `fixture_tree.py` (spawns a grandchild that attempts `CREATE_BREAKAWAY_FROM_JOB`), `fixture_noisy.py` (emits the sentinel secret in every H-8 form, ANSI sequences, NUL bytes). | §9 |
| R3-3 | H-5: replace `startswith` with canonical resolution (`GetFinalPathNameByHandleW` via ctypes, case-folded, `os.path.commonpath`). Tests: `..`, junction escape (create a junction in a temp dir), case variant, UNC, `\\?\`. | H-5 |
| R3-4 | H-6: tests — child+grandchild die on Stop; die on simulated shell crash (`os._exit` in a subprocess-hosted shell); breakaway attempt fails; `JOB_ASSIGN` failure path terminates the process. | H-6, §7.4 |
| R3-5 | State machine: one test per transition in §7.4, including `FAILED(TIMEOUT)`, `FAILED(IDENTITY)`, `DEGRADED→READY`, `EXTERNAL` (fixture pre-started outside the Job, identity passes), `PORT_OCCUPIED_UNRECOGNIZED` (fixture with wrong identity body), `EXTERNAL→STOPPED`. | §7.4 |
| R3-6 | H-7 rate limit; H-9 shell exit leaves the `EXTERNAL` fixture alive; H-10 layer-2 test (mutate compiled env, assert abort + no spawn). | H-7, H-9, H-10 |
| R3-7 | H-8 four-surface sentinel: ring buffer, `/api/logs` response, startup-test JSON, every file under `evidence/` written during the test. | §7.6.1 |
| R3-8 | H-11 four-part proof → `evidence/hardening/deps-proof.txt`. If `-I -S` breaks relative imports, fix the imports (absolute package imports, run as `py -3.12 -I -S -m shell.src`), do not abandon the proof. | H-11 |
| R3-9 | H-12 filesystem watch during the suite (`ReadDirectoryChangesW` or `Register-ObjectEvent` capture) → `evidence/hardening/fs-watch.txt`. | H-12 |
| R3-10 | H-2: `Host` required and `== 127.0.0.1:<port>`; `Origin` required on state-changing requests and `== http://127.0.0.1:<port>`; remove `Access-Control-*` headers; tests for each negative. | H-2 |
| R3-11 | `sow.json`: add a `startup_test` override block `{ "env_set": { "SHELL_SELFCHECK": "1" }, "readiness": { "kind": "receipt_file", "path": "${root}/apps/desktop/docs/evidence/receipts/PHASE16A_SELFCHECK.json", "require": { "ok": true } } }`; schema updated (`additionalProperties:false` preserved); `startup_test.py` applies it. Replace `identity.kind: process_path/path_prefix` with `process_image` compared by canonical-path equality to compiled `argv[0]`. Confirm the receipt filename against the live `selfcheck/run.js` and cite the line. | ADR-004, B-5, H-5 |
| R3-12 | H-1, H-3 captures into `evidence/hardening/`; `evidence/test-run.txt` regenerated by the single README test command and ending in `OK`; `shell/BUILD-MANIFEST.txt` produced. | H-1, H-3, A-5 |

Submit: `BUILDER CLAIM: Gate 4 is a CANDIDATE…`

### R4 — Gate 5 (only after reviewer PASS on Gate 4)

Real-module startup tests (SOVEREIGN, Debate, SOW via selfcheck path), JSON records with `quota_guard` and `undeclared_writes`, screenshots, Distillery `NOT_STARTED` screenshot, side-by-side theme screenshot, final manifests and git `.body` diff. Honest `FAILED(PRECHECK:…)` for SOVEREIGN is acceptable evidence.

### R5 — Gate 6

Reviewer assessment; operator promotes or not.

---

## 3. Ledger entry schema (replaces the current file)

```json
{ "directive": "SWS-UI-001", "version": "1.2", "manifest_tool_sha256": "<64 hex>",
  "gates": { "<n>": {
      "status": "NOT_REACHED | CANDIDATE | PASS | FAIL | STOP",
      "utc": "<ISO 8601 Z>",
      "claimed_by": "builder",
      "evaluated_by": "reviewer | null",
      "authorized_by": "operator | null",
      "evidence": [ { "path": "<exists on disk>", "sha256": "<64 hex>" } ],
      "note": "<optional, no status claims>" } } }
```

Forbidden values: `"not hashed"`, truncated hashes, paths that do not exist, `PASS` written by the builder.

---

## 4. Stop conditions specific to this remediation

The Electron zip cannot be obtained with a verifiable hash · the selfcheck receipt path cannot be confirmed in `run.js` · the Debate contamination source would require reading outside the workspace to determine · any R3 item would require modifying a module's runtime instance beyond `runtime_writes` · the host clock cannot be reconciled. → `docs/STOP-REPORT-REM-01.md`, then stop.

---

## 5. Reviewer's labels

- `FACT` Every item above traces to a finding in `REVIEW-BUILD-01.md` that was verified on disk, or to a directive clause by number.
- `FACT` The two concurring reviews did not inspect the disk independently; they concur with the Round-1 read. Independent re-execution of the manifest diff and the test suite by the reviewer has not yet occurred and is planned for the Gate 4 evaluation.
- `INTERPRETATION` Keeping the builder is reasonable if the §1 envelope holds; the defect pattern was authority and evidence discipline, not implementation quality.
- `RECOMMENDATION` Do not negotiate the envelope wording with the builder. The first report that omits the mandatory closing line is the signal that the envelope is not holding.
