# Round 12 Evidence Packet - Phase 8 complete

## Delta
- Phase: 8 (model context + performance hardening)
- Commit: d0bf63e
- Files changed: debate/model_capabilities.py (new), app.py, tests/test_v1_2_1_model_budget.py (new)
- Functions changed: new CapabilityRegistry/capabilities_from_window/estimate_tokens/extract_context_length; _capability_client_factory bridge; turn_prompt rewritten to priority-section assembly with _apply_prompt_budget ladder (shed oldest in-window turns -> drop whole sections P9..P6; priorities <6 untouchable); run_turn computes caps+budget, records decisions per attempt + prompt_budget_applied log events; tokens_per_second derived on done frame; /ready seats expose context_window+qualification

## Root cause addressed
No model-context awareness and no budget discipline existed; oversized prompts would silently overflow smaller models' windows. Perf metrics lacked derived throughput.

## Implementation notes
Context windows discovered at runtime via /api/show (largest *.context_length) with conservative 8192 fallback - no model-family hard-coding (S18.1). Budget estimate ~4 chars/token, deterministic. Degradation ladder verified by probe: shed-count vs window offset semantics pinned by tests.

## Tests Added or Modified
6 tests: fallback caps; discovery seam; tiny-budget drop order (args dropped, anchor retained, header+newest kept); older-shed ladder with window-offset semantics (contiguous survivors); tokens/sec derivation; /ready capability rows.

## Verification
narrow 6/6; FULL SUITE 172 passed / 0 failed in 48.36s; lifecycle PASS @1.051s clean shutdown; diff clean.

## Performance Impact
measured: none adverse; est overhead one section-sort + char counts per turn.
expected: fewer context overflows on small-window models; tokens/sec now observable per attempt for Phase 10 qualification.

## Security Impact
improvement: budget telemetry makes silent truncation auditable; no new surface.
residual: token estimate is heuristic (documented), not tokenizer-exact.

## Open work
Phase 8 S18.4 dependency decision recorded (D-11): NO dependency changes - installed stack matches requirements.lock.txt pins exactly (verified Phase 0); revisit only if later gates demand.

## Completion Effect
All engineering phases (1-8) now complete. Remaining: Phase 9 system regression lock artifact, Phase 10 real-Ollama qualification (models present), Phase 11 soak, Phases 12-14 distillation + cold test + fresh review.