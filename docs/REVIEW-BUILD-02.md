# REVIEW — SWS-UI-001 v1.2, REM-01 Execution (Round 2)

| Field | Value |
|---|---|
| Reviewed | `Production Workspace\` after REM-01 R1–R3 (builder: Claude Code), 2026-08-21 ~05:30Z |
| Reviewer | Claude (Research Validator / Reviewer), separate session |
| Method | Direct read of evidence files, ledger, source, and stage reports on disk. Independent re-execution of the test suite was not possible from this session (no Windows runtime); the shipped `test-run.txt` was inspected for completeness and the command that produced it checked against the README. |
| Verdict | **Gate 2 PASS. Gate 3 PASS. Gate 4 CANDIDATE — returned with three small items.** Gates 0/1 remain STOP pending the operator's signature. |

---

## 1. Governance

`FACT[chat transcript]` The operator instructed the builder to execute without stopping at stage gates. That is within the operator's authority; the stage pauses were process controls, not evidence requirements. `FACT[docs/DECISIONS.md sha256 bb911905…]` The builder did not sign anything on the operator's behalf; Gates 0/1 are recorded `STOP` with `authorized_by: null`. That is the correct handling and the reverse of Round 1.

`RECOMMENDATION` When the operator signs `DECISIONS.md`, add one line recording that REM-01 stage pauses were waived by operator instruction on 2026-08-21, so the ledger's jump from R1 to R3 in one session is explained by an authorization rather than by drift.

## 2. Verified on disk

| Claim | Evidence read | Result |
|---|---|---|
| Suite ends `OK`, 105 tests | `evidence/test-run.txt` last lines | `FACT` confirmed; zero FAIL/ERROR lines |
| Ledger: no `PASS`, no `not hashed`, full hashes | `GATE-LEDGER.json` | `FACT` 73/73 hashes are 64-hex; no builder `PASS` |
| Protected sources unchanged | three `manifest-diff-*.txt` | `FACT` `FC: no differences encountered` ×3, exit 0 |
| H-1 loopback bind | `h1-listen.txt` | `FACT` `127.0.0.1` only |
| H-2 exact Host/Origin, no CORS | `server.py:76-112` | `FACT` both headers required and exact; `MAX_BODY=16384`; no `Access-Control-*` |
| H-5 canonical containment | `adapter.py:4,34,51-80` | `FACT` `GetFinalPathNameByHandleW` + `commonpath`, case-folded; remaining `startswith` calls are UNC/device *rejection* pre-checks, which §7.6 permits |
| H-6 Job Object | `h6-jobobject.txt`, `supervisor.py:6-17,131-148` | `FACT` 5/5 containment tests pass incl. grandchild breakaway refusal and crash-kill; argtypes declared; both breakaway flags unset |
| H-8 four surfaces | `h8-sentinel.txt` | `FACT` 12 sentinel occurrences in raw → 0 after ingest; four-surface test OK |
| H-10 two layers + real SOW run | `startup-tests/sow-20260821T052050.534Z.json` | `FACT` `quota_guard.verified_before_spawn: true`; `SHELL_SELFCHECK` in env keys; READY via receipt in 17.0 s; identity `process_image` PASS |
| H-11 zero deps | `deps-proof.txt` | `FACT` four-part proof present; both isolated forms load 0 site-packages modules |
| ADR-004 encoded in adapter | `shell/modules/sow.json` | `FACT` `startup_test` block with receipt path under `${root}/docs/evidence/receipts/` (builder corrected the directive's wrong path and cited `pane-io-selfcheck.js:26-28`) |
| Debate instance clean | `phase2-debate-verify.txt` | `FACT` folder removed after hash-verifying all 9 files identical to the protected originals; manifest re-verification present |
| Git state unchanged | `sow-git-body-semantic.txt` | `FACT` HEAD, 3 status entries, diff payload sha `dcafc063…`, empty cached diff all equal |

## 3. Builder deviations — adjudicated

| Deviation | Disposition |
|---|---|
| Did not raise `PROTECTED_GIT_STATE_CHANGED` on `fc /b` mismatch; wrote a semantic analysis instead | **Accepted.** The Phase-0 `.body` was reconstructed from a capture with BOM, CRLF, two extra sections, and PowerShell error text. Raising STOP would have asserted a falsehood. The directive is amended (§5) so bodies are normalized before comparison. |
| Bypassed stage stops | **Accepted** — operator-instructed. |
| `/api/shell` → used existing `/api/shell-info` rather than add an endpoint | **Accepted.** Directive error; correct refusal under §0.1(7). |
| `-I -S -m shell.src` → two isolated forms with `__file__`-derived path bootstrap | **Accepted.** Directive error (`-I` drops `sys.path[0]`); the proof's intent is met. |
| Rewrote `supervisor.py`, `server.py`, `startup_test.py` rather than editing | **Accepted** with the reasons given in the R3 report (handle truncation, missing output capture, `TerminateProcess` on a nonexistent attribute). Nine real defects fixed; each is named. |

## 4. Items before Gate 4 PASS

| # | Finding | Evidence | Fix |
|---|---|---|---|
| G4-1 | `evidence/hardening/fs-watch.txt` on disk records window `05:26:44Z .. 05:26:44Z` and was written at 05:26:44Z — **after** the suite finished (05:25:27Z). The R3 report claims window `05:24:23Z .. 05:25:27Z`. The artifact was overwritten by a later single-test run and no longer proves H-12 for the suite. | `fs-watch.txt` header; report §R3-9 | Regenerate by running only the README test command; make `test_zz_evidence` refuse to overwrite an artifact whose window is shorter than the suite's, or write per-run files. |
| G4-2 | Twelve `noisy-*.json` fixture records sit in `evidence/startup-tests/`. Evidence for real modules is now mixed with test output. | directory listing | Tests write startup records to a `tempfile` evidence root; delete the twelve files; keep the two `sow-*.json`. |
| G4-3 | H-4 has no test and no artifact (builder disclosed this). | R3 report §1 | Add `test_frontend.py`: grep `shell/static/*.js` for `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval(`, `new Function`, `document.write`; assert zero hits outside a documented allowlist; render one log line containing `<script>` through the API and assert it is returned JSON-escaped. Artifact `evidence/hardening/h4-dom.txt`. |

Carried forward, not blocking: `npm ci` reports two high-severity advisories in the SOW dependency tree. Not the shell's dependencies (HC-1 forbids touching the module's lockfile); record in BUILD-REPORT risks.

## 5. Directive amendments (reviewer, recorded here; directive file updated)

- R2-5: compare `.body` files after normalizing to LF, stripping BOM, and restricting to the four named sections; raise `PROTECTED_GIT_STATE_CHANGED` only if HEAD, status entries, or diff payload hashes differ.
- R3-8: the isolated-interpreter proof is satisfied by `-I -S -B <abs path to __main__.py>` or `-E -S -B -m shell.src`; the `-I … -m` form is withdrawn.
- R3-11: receipt path is `${root}/docs/evidence/receipts/PHASE16A_SELFCHECK.json`.
- `/api/shell` → `/api/shell-info`.

## 6. Ledger

Reviewer has written `PASS` for Gates 2 and 3 with `evaluated_by: reviewer`, retained `CANDIDATE` for Gate 4 with the three items above as the note, and annotated Gates 0/1. Gate 4 will be set `PASS` on a second CANDIDATE submission that resolves G4-1…G4-3 and ships a fresh `test-run.txt`. Gate 5 may then begin.
