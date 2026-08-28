# DECISIONS — Debate Table v1.2.1-hardening

Only genuine product/engineering decisions are recorded here. Routine narration lives in round packets.

## D-2026-08-23-01 — Hardening worktree is a git-initialized copy; pristine install stays untouched
The located baseline (`D:/Product Software/Production Workspace/modules/debate`) is an installed production copy, not a git repository (provenance in `BUILD-INFO.json` / `INSTALL-PROVENANCE.json`; upstream commit `d7be3357…`). The loop procedure requires per-round `git status`/`git diff` and independent rollback (§8.1, §8.3). Decision: copy the tree byte-exactly into `dev/v1.2.1-hardening/worktree`, `git init`, and commit the verified baseline as the root commit (`43ab217`). The original directory is hash-locked (`BASELINE-SHA256.json`, 36 files) and never edited. All hardening rounds occur in the worktree; final release is staged fresh from it via allowlist.

## D-2026-08-23-02 — Interpreter selection for tests and runtime verification
Two interpreters exist: system CPython 3.14.6 (matches `BUILD-INFO.python_version_tested` and lockfile header) with full web stack + pytest 9.1.1, and `.venv` CPython 3.12.10 (operator install venv) which lacks pytest. Installed versions match `requirements.lock.txt` pins exactly (fastapi 0.139.0, starlette 1.3.1, uvicorn 0.51.0, httpx 0.28.1). Decision: use system CPython 3.14.6 for all test/verification runs to match recorded provenance; note that the operator-facing bootstrap uses its own venv logic and remains untouched.

## D-2026-08-23-03 — P0 register authority
No standalone adversarial-review document exists on disk. Decision: the directive text (§11–18, §37) is treated as the authoritative enumeration of P0-02..P0-20. No "P0-01" is invented despite the numbering gap; if the Director's original review surfaces, the register will be reconciled at that point.

## D-2026-08-23-04 — Evidence area location
All ledgers, evidence packets, probes, and later release artifacts live under `D:/Product Software/Production Workspace/dev/v1.2.1-hardening/release-evidence/`, outside any production ZIP, per §3.

## D-2026-08-23-05 — Missing-file config stays lenient this round
Round 1 scoped fail-closed semantics to PARSE CORRUPTION only (ConfigurationError on invalid JSON / non-object root / unreadable file). A missing config.json retains its pre-existing behavior pending P0-04, where the canonical resolver defines absence explicitly. Recorded so silence here is not read as oversight.

## D-2026-08-23-06 — Source edits are binary-safe Python only
PowerShell 5.1 Get-Content without -Encoding decoded UTF-8 sources as ANSI during Round 1's first implementation attempt, corrupting every non-ASCII byte (caught by test_v1_logic em-dash assertion; root-caused; files restored from git HEAD). All subsequent source modifications MUST go through Python read_text/write_bytes with explicit utf-8. Evidence: ROUND-1-EVIDENCE-PACKET.md.

## D-2026-08-23-07 — Round tool scripts live at release-evidence/rounds/r1-tools/
A wrong relative base briefly created dev/release-evidence outside the designated evidence tree; consolidation deleted those copies. All patch application is reproducible from git history; going forward every evidence artifact is written via absolute path under release-evidence/.

## D-2026-08-23-08 — Rotation/anchor cadence follows COMPLETED turns; display numbering unchanged
state.turn remains the per-topic attempt/display counter (UI continuity, smoke expectations); rotation and anchor cadence key off the new topic-scoped completed_turns. The microphone rotates after skipped attempts so a failing seat cannot stall the table; it simply does not advance completed counters.

## D-2026-08-23-09 — Disagreement markers narrowed to explicit phrases; bare however/but/challenge/incorrect/doubt removed
Baseline snapshot D1 measured these singletons saturating every 4-turn window (breaker fired 0/53) and proved removing but+however alone recovers only 9.4%. The consensus-breaker is now meaningful rather than pretended. v1_logic OFF-path fixture re-keyed to an explicit phrase under the AC-02 documented exception.

## D-2026-08-23-10 — min_turn_chars retired (S17.4 option 2)
Inert since v1.1 across two directive cycles. Enforcement at default 120 would silently reclassify many legitimate short fixture/live turns as skips, colliding with AC-02 preservation; removal is the honest sanctioned choice. Loader tolerates the key as unknown for operator leftovers.

## D-2026-08-23-11 — No dependency changes for v1.2.1-hardening (S18.4)
Installed fastapi/starlette/uvicorn/httpx/websockets/anyio match requirements.lock.txt pins byte-for-byte (verified during Phase 0 against the running interpreter). Upgrading solely to chase versions would invalidate the recorded baseline without a demonstrated defect; hostile E2E and real-Ollama gates will re-validate the pinned stack instead.
