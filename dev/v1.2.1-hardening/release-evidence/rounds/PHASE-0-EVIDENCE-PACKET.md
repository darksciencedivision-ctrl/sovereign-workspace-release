# PHASE 0 EVIDENCE PACKET - Baseline Lock and Comprehension

Round: 0 (Phase 0) | Date: 2026-08-23 | Worker: Ox Alpha (opencode)
Worktree HEAD after baseline commit: 43ab217 (branch master, repo created for this effort)

## 1. Source tree identification (S10.1)

- Pristine baseline path: D:/Product Software/Production Workspace/modules/debate
- Kind: installed enterprise production copy, NOT a git repo
- Upstream provenance: commit d7be33579c0f986db74c0b221b5bdf06a9d280df, branch master (BUILD-INFO.json)
- Built 2026-08-11T20:11:29-05:00 on CPython 3.14.6; BUILD-INFO records pytest 84 passed / 0 failed
- Install source zip sha256: 29b364b075e55b4ac5e66cd1399145838dfca691d82c4500253d4ece36742f93 (INSTALL-PROVENANCE.json)
- Files excl .venv: 36 (all release-relevant; no caches pre-run)
- Hardening worktree: dev/v1.2.1-hardening/worktree (git init; root commit is byte-exact copy)

## 2. SOW exclusion proof (STEP 2)

- INSTALL-PROVENANCE.json records contamination_removed: modules/debate/SOW_REVIEW_ROUND2_RAW (9 files); instance verified 34 files / 0 mismatches against content manifest.
- Live scan of all 36 release-relevant files for SOW_REVIEW|sovereign: only (a) the provenance record itself and (b) tests/archive_phase0.py referencing audit/sovereign_inventory.md - a non-collected archive harness outside the 84 collected tests.
- Foreign tree modules/sow sits outside the application directory; unreferenced by runtime or tests.

## 3. Baseline hash lock (S10.2)

release-evidence/baseline/BASELINE-SHA256.json: 36 entries (path,size,sha256), excludes .venv/__pycache__/.pytest_cache. Worktree fidelity: 36 verified, 0 mismatches.

## 4. Baseline test suite (S10.3)

python -m pytest tests -q on pristine baseline, CPython 3.14.6:
RESULT: 84 passed in 15.78s - matches frozen expectation exactly. Evidence: baseline/phase0-pytest.txt. Test caches removed afterwards; original restored to pristine state.

## 5. Baseline boot/lifecycle (S10.4)

Probe: lifecycle/baseline_boot_probe.py; result: lifecycle/phase0-baseline-boot.json
- Port 8700 bind loopback-only: PASS (pre-check confirmed no prior listener)
- HTTP GET / : PASS, status 200, boot 1.077s
- Frontend recognizable: PASS (<title>Debate Table</title> present)
- WebSocket /ws: PASS, connected; first message type = snapshot
- Shutdown: PASS; zero port listeners remain; zero orphan app processes
Notes: forced-terminate exit code 1 is documented pre-existing CTRL_BREAK behavior carried in v1.2 register. An initial probe failure was root-caused to a bug in the probe script itself (wrong parents[] index gave child cwd without app.py -> interpreter exit 2); probe fixed, then two consecutive clean passes recorded.

## 6. Environment facts relevant to later gates

- Ollama 0.32.14 reachable at loopback; configured models present: phi4:14b, qwen2.5:14b-instruct, extractor dolphin-llama3:8b => REAL_OLLAMA_QUALIFICATION gate UNBLOCKED.
- Installed versions match requirements.lock.txt pins exactly: fastapi 0.139.0, starlette 1.3.1, uvicorn 0.51.0, httpx 0.28.1, websockets 16.1, anyio 4.14.1.

## 7. Comprehension artifact (S10.5) and ledgers (STEP 6)

comprehension.json: goal, terminal artifacts, P0 register P0-02..P0-20 each with required semantics (no P0-01 exists anywhere in contract text - numbering gap recorded, none invented), phase mapping, G-01..G-10 prohibitions, AC-03 regression floor, hostile E2E scenario list, purity + integrity chain, reviewer-independence rule, stop condition, Round-1 target.
OPEN-ITEMS.json (19 P0 open), ROUND-LEDGER.jsonl (round 0), DECISIONS.md (D-01..D-04), RISKS.md (R-01..R-04).

## LOCAL VERDICT

LOCAL_PASS for Phase 0 scope: all five baseline gates reproduced with evidence; no production code edited; comprehension artifact complete.
Per G-10 this is a worker-proposed verdict only. Cold review packet follows.

## REVIEW_PACKET (cold review input, per S8.7/S10.5)

Inputs provided to reviewer (and nothing persuasive beyond them):
1. Frozen contract: directive sections 2-4, 10, 36-37 (held by Director).
2. comprehension.json
3. BASELINE-SHA256.json
4. phase0-pytest.txt, lifecycle/phase0-baseline-boot.json, lifecycle/baseline_boot_probe.py
5. DECISIONS.md, RISKS.md, OPEN-ITEMS.json, ROUND-LEDGER.jsonl

Reviewer questions:
Q1 Does comprehension.json misstate any frozen-contract requirement?
Q2 Is treating directive text as authoritative P0 register (absence of standalone review doc) acceptable?
Q3 Any Phase 0 gate evidence insufficient or non-reproducible?

Gate status: AWAITING_EXTERNAL_REVIEW
