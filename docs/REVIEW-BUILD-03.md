# REVIEW — SWS-UI-001 v1.2, REM-01 Gate 4 Resubmission (Round 3)

| Field | Value |
|---|---|
| Reviewed | `Production Workspace\` after the Round-2 resubmission, 2026-08-21 ~17:15Z |
| Reviewer | Claude (Research Validator / Reviewer) |
| Verdict | **Gate 4 PASS.** Gates 2, 3 PASS (unchanged). Gates 0, 1 STOP (operator signature still absent). Gate 5 may begin. |

## Verified on disk

| Item | Evidence | Result |
|---|---|---|
| G4-1 fs-watch covers the suite | `fs-watch.txt`: window `17:09:10Z .. 17:10:16Z`, 66 s, 0 events; `test-run.txt`: started `17:09:10.16Z`, `Ran 116 tests in 65.868s`, `OK` | `FACT` window brackets the whole run; artifact produced by the README command |
| G4-1 regression guard | `_fswatch.py:49-217`: `SHRINK_THRESHOLD = 0.5`, returns `("refused", …)`; 5 tests in `TestFsWatchOverwriteGuard` | `FACT` present and tested. `INTERPRETATION` The 50 % rule is the right call — "refuse anything shorter" would have frozen the artifact at the slowest run. |
| G4-2 fixture records out of evidence | `evidence/startup-tests/` listing; `SWS_EVIDENCE_ROOT` redirect; H-8 surface-4 now snapshots both roots | `FACT` no `noisy-*.json` remain; the surface-4 assertion was kept non-vacuous |
| G4-3 H-4 | `h4-dom.txt`; `test_frontend.py` 5 tests | `FACT` six sink patterns, 0 hits over 901 lines, empty allowlist; no inline script/handlers/style; `<script>` round-trip served as JSON + nosniff and assigned via `textContent`. The artifact correctly states that `json.dumps` does not entity-encode `<`; the claim is bounded to what is proven. |
| Ledger integrity | `GATE-LEDGER.json` | `FACT` 81/81 full hashes; reviewer `PASS` on Gates 2–3 preserved verbatim; no `PASS` without reviewer attribution; Gate 4 submitted as `CANDIDATE` |
| Protected sources | builder reports three `fc /b` exit 0 after this round | `ASSUMPTION` not re-read this round; Gate 5 closes with fresh manifests, which is the next independent check |

## Builder conduct this round

`FACT` Re-ran §1 first and left `DECISIONS.md` untouched (hash still `bb911905…`). Disclosed the root cause of G4-1 as its own action. Updated only the Gate 4 key and asserted the other six unchanged before writing. Closing claim line present. No deviations to adjudicate.

## What Gate 5 requires (unchanged from v1.2 §9 / REM-01 R4)

Real startup tests for SOVEREIGN and Debate Table (SOW is already done via the selfcheck path); honest terminal states with JSON records; screenshots of each card, the Distillery `NOT_STARTED` card, and the shell beside the SOVEREIGN UI; final protected-source manifests and git `.body` comparison. `FAILED(PRECHECK:…)` for SOVEREIGN without the required Ollama models is acceptable evidence.

`RECOMMENDATION` Gate 6 cannot be reached with Gates 0/1 at STOP. Sign `DECISIONS.md` before or during Gate 5 so the chain is complete when the reviewer reads the final package.
