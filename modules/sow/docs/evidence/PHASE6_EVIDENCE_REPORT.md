# PHASE 6 EVIDENCE REPORT — Multi-Model & Local Adapters
Autonomous loop iteration 7 · 2026-07-17Z · gate: `gate/phase-6`

## Objective
≥3 backends behind capability descriptors per Buildout Directive §5 Phase 6 / Plan §7-P6:
a coding node and ≥1 local reasoning model plus the conductor path; capability-based
selection demonstrably by descriptor, not name; offline roster with benchmark evidence.
Loop scope: mock-frontier + coding node (OpenCode+Ollama if detected else mock) + local
reasoning (Ollama if detected else mock). Live subscription + R8 ToS out of scope by
prohibition §2.4 (deferred-live, not failures).

## Source state
Tags through `gate/phase-5`; freeze `--check` clean throughout. `next_step: phase-6`.

## Host detection (detection only — no install/pull, recorded)
- **Ollama daemon UP** on 127.0.0.1:11434 with 40+ models, including the plan's offline
  defaults: `qwen3:8b/14b`, `qwen2.5:7b/14b-instruct` (reasoning, D-COND-02),
  `qwen2.5-coder:7b/32b`, `qwen3-coder:30b` (coding, D-CODEX-03).
- **OpenCode** binary present on host.

## Files
- **Work commit `756e92c7`:** `adapters/detect.py`, `adapters/base/backend.py`,
  `adapters/model_adapter.py`, `adapters/roster.py`, `adapters/{frontier,coding}/__init__.py`,
  `tools/benchmark/phase6_probe.py`, 2 test files, `docs/evidence/PHASE6_ROSTER_PROBE.json`.
- **Remediation commit `085ac924`:** F1–F4 fixes + regression tests.

## Exit criteria — met, mapped to code + test
- **≥3 backends behind one contract:** `build_roster()` → `local_reasoning` (worker_reasoning,
  local, offline-eligible), `coding_node` (worker_coding_specialist, local), `mock_frontier`
  (worker_reasoning, frontier, NOT offline-eligible). All three run behind the single
  `ModelWorkerAdapter`; integration test drives each end-to-end (context from MCP → local gate
  → CANDIDATE publish).
- **Selection by descriptor, not name (I-SC1):** the resolver filters on capability +
  requirements (tool_use/structured_output/min_context/**harness_class**/locality/offline
  eligibility) and ranks; concrete model names live only in `roster.py`/`OllamaBackend`, never
  in task definitions (node@1.0 `capability_descriptor` has `additionalProperties:false` — no
  field a name could occupy). Tests prove: coding task → coding_node (only 'coding' node);
  128k-context reasoning → mock_frontier (by min_context); air-gapped → frontier excluded →
  local; air-gapped+128k → no node (queued). Each would fail an order/name-based resolver.
- **Real local backend, honest mock/real split:** deterministic suite forces `allow_live=False`
  (all mock, no network); the **live smoke** (`skipif` daemon absent) drove real
  `qwen2.5:7b-instruct` to produce a governed artifact through the full MCP path
  (content-addressed, retrievable, non-mock). Validator independently re-ran the live smoke.
- **Benchmark evidence (offline roster):** `docs/evidence/PHASE6_ROSTER_PROBE.json` — real
  latencies (reasoning `qwen2.5:14b-instruct` 4.66s; coder `qwen2.5-coder:7b` 14.91s cold),
  honestly scoped as a **light probe**; the full Track E/R9/R10 campaign (multi-task suites,
  tool-call reliability, long-context, VRAM sizing, 24B+ scale path) is deferred (GPU-heavy,
  out of the loop's compute budget) → U18/U19.

## Independent review (standard-stakes: validator + spec-auditor)
- **gate-validator: PASS_WITH_RESERVATIONS.** Ran the suite (220) + the live smoke itself
  (real generation confirmed); verified I-SC1 selection genuinely descriptor-driven (each test
  would fail a broken resolver), mock/real honesty, deferred-live honesty, benchmark real +
  scoped, scope/freeze clean, no invariant drift, OllamaBackend credential-free. Reservations
  R1 (benchmark_score placeholder inert → full Track E outstanding) and R2 (R8 deferred) —
  carried.
- **spec-auditor: FINDINGS 1 MAJOR / 2 MINOR / 4 NOTE**, invariant posture CLEAN (I-SC1,
  CANDIDATE-only, naked-launch, no-credentials, no SSRF, side-effect-free detection, no
  premature Phase 7). Dispositions:
  - **F1 MAJOR — FIXED:** coding_node advertised a `coding_tui` harness it doesn't drive.
    Now honest (harness_class=null, direct local coder, notes explain OpenCode deferral) AND
    the resolver enforces harness_class (a harness-requiring task fails closed instead of
    mis-routing). Pinned by two tests.
  - **F2 MINOR — FIXED:** `pick_model` exact-tag match wins over family-prefix (no oversized
    same-family binding; I-22 tier).
  - **F3 MINOR — FIXED:** backend transport/decode errors + empty output → structured
    `{published:False, backend_error}` (symmetric with local-gate-fail), no scheduling-loop
    crash. Pinned by a broken-backend test.
  - **F4 NOTE — FIXED:** `register_roster` validates descriptors against the frozen node@1.0
    sub-schema.
  - F5/F6/F7 NOTE — recorded: static capability claims unverified until Track E (U19);
    lexicographic tie-break is on role names not vendor names (fine); local gate is structural
    (same as P4/5).

## Substitutions (loop directive §6)
Mock backends for the deterministic suite; a real detected local Ollama model for the live
smoke + benchmark probe (permitted local use). Frontier is mock (live subscription out of
scope). OpenCode harness detected but its programmatic drive deferred (interactive TUI) —
coding node is a direct local coder today, advertised honestly.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: U18 (benchmark ranking placeholder), U19 (new: full Track E offline-roster
  freeze + static-capability verification deferred, GPU-heavy), R8 subscription deferred-live,
  OpenCode programmatic drive deferred (→ still I-CH1-shaped, adapter contract ready).

## Gate verdict
**PASS.** ≥3 backends behind one contract with genuinely descriptor-driven selection (I-SC1);
a real local model proven end-to-end via the opt-in live smoke; the one capability-honesty
MAJOR (coding-node harness overclaim) fixed with resolver enforcement + tests before closure;
deferred-live items recorded honestly, not as failures. 224/224 tests.

## Commits
Work `756e92c7` → remediation `085ac924` → this evidence/register commit (tagged `gate/phase-6`).

## Next phase
`phase-7` — Debate Service: reusable, any authorized node may request; ≤5 rounds, early stop,
dissent preserved, per-debate token budget + cost governor; caller authorization via the
broker. §2.8 debate acceptance tests incl. non-conductor caller + budget-exhaustion cutoff.
Also the natural home to address U15 (approver≠author / no node solely judges its own work).
