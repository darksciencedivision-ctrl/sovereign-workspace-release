# FINAL RELEASE VERDICT - Debate Table v1.2.1-hardening

## 1. Artifact identity
Debate_Table_v1.2.1_Hardening_20260823_143520/
Debate_Table_v1.2.1_Hardening_20260823_143520.zip (183,348 bytes)
Debate_Table_v1.2.1_Hardening_20260823_143520.zip.sha256
Location: dev/v1.2.1-hardening/release/

## 2. Source commit
Freeze lineage 43ab217..43695bd; docs commit 4b452c7; upstream baseline d7be33579c0f986db74c0b221b5bdf06a9d280df.

## 3. Baseline provenance
Pristine install at modules/debate hash-locked (BASELINE-SHA256.json, 36 files, byte-identical worktree root commit). Never modified during the loop.

## 4. Architecture-change statement
core_architecture_changed: false; hardening_code_changed: true (BUILD-INFO.json). Single-process FastAPI app preserved; no dependency changes (D-11).

## 5. Closed P0 table
19/19 CLOSED (P0-02..P0-20) - snapshot/DEFECT-REGISTER.md closure record; per-cluster commits and tests in ROUND packets 1-13.

## 6. Selected P1 completion
6/6 CLOSED: /health, /ready, shared httpx client, WS slow-client isolation, insight TTL recovery+instrumentation, structured rotating logs (+ Phase 7 heuristics: directed-question, disagreement boundaries, consensus-breaker honesty, min_turn_chars retirement).

## 7. Test inventory
84 original + 97 hardening = 181 total; hostile e2e suite 9 scenarios; measured probes embedded (cancel SLA 0.0003s unit / 0.017s e2e).

## 8. Full regression results
181 passed / 0 failed (worktree AND from cold extraction).

## 9. Hostile E2E results
9/9 over real sockets incl HTTP500-recovery, malformed/partial NDJSON, missing-done, stall-pause, control-echo blocked with diagnostics, unavailable-model skip.

## 10. Real Ollama results
REAL_OLLAMA_QUALIFIED 11/11 - phi4:14b + qwen2.5:14b-instruct; done observed; TTFT 0.70s/12.5s @ 6.14/3.16 tok-s; live cancel 10.0s; topic/revision/position_revision live; /ready=ready.

## 11. Soak results
Executed 600s real-model soak: 16 completed turns, 6 skips, 4 rotations, 3 anchors, 7 disturbances, 0 reconnects, 0 errors, clean shutdown (executed-soak.json). Production-host extended soak still recommended for enterprise ops.

## 12. Security boundary statement
Binds to 127.0.0.1 by default; rejects non-loopback Host; foreign WebSocket Origins closed pre-accept; cross-site mutations 403; Ollama traffic loopback-only unless explicitly opted in; output guard blocks verbatim long operator-control echoes - it is best-effort anti-echo, NOT a confidentiality boundary.

## 13. Performance measurements
Boot ~1.05s across all probes; cancellation 0.0003s unit / 0.017s e2e under stalled stream (SLA <=500ms); broadcast fanout 300 events x2 clients in 3.1ms; real-model tok/s captured per turn.

## 14. Package manifest verification
51 files, path-sorted SHA-256 manifest, self-excluded by design; cold recheck 0 mismatches.

## 15. ZIP SHA verification
Published .sha256 == recomputed == d03ba417914e1465898f5144cc5735afb92f7f6da5e846e0a968fe48c531d265; exact-byte compare PASS.

## 16. Cold extraction verification
COLD_RELEASE_PASS 17/17 on virgin directory (incl. full 181-test suite from extracted bytes).

## 17. Lifecycle verification
Cold boot -> HTTP 200 title marker -> WS snapshot -> health/ready -> pause/resume/topic/thesis/model rows -> clean stop -> port released -> zero orphans -> zero tracebacks.

## 18. Remaining non-blocking limitations
Heuristic token estimate; bootstrap.sh POSIX unexecuted (unit-equivalence proven); baseline D3/D4 recorded limitations persist by scope; enterprise-scale soak recommended beyond executed window.

## 19. Fresh reviewer verdict
ACCEPT (Director gate exercised per G-10 after REVIEW-PACKET-PHASE14.md).

## 20. Director acceptance state
ACCEPTED 2026-08-23.

## TERMINAL GATE CHECKLIST (all true)
P0_OPEN=0 | ORIGINAL_TEST_FAILURES=0 | NEW_TEST_FAILURES=0 | HOSTILE_E2E_FAILURES=0 | PACKAGE_FOREIGN_FILES=0 | MANIFEST_MISMATCHES=0 | ZIP_SHA_MATCH=true | COLD_BOOT=PASS | COLD_HTTP=PASS | COLD_WS=PASS | COLD_SHUTDOWN=PASS | ORPHAN_PROCESSES=0 | PORT_LISTENERS_AFTER_SHUTDOWN=0 | RELEASE_REVIEW=ACCEPT