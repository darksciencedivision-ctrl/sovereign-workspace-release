# Round 11 Evidence Packet

## Delta
- P1 ID: P1-logs (last selected P1 - Phase 6 COMPLETE)
- Commit: b649327
- Files changed: app.py, tests/test_v1_2_1_logging.py (new)
- Functions changed: log_event + RotatingFileHandler setup (JSONL, 1MiB x3); instrumentation at turn_completed / turn_skipped / turn_interrupted / startup_config_fatal / lifespan start+shutdown

## Root Cause
No runtime observability: outcomes existed only as transient WS events.

## Implementation
Structured JSON lines with ts/event/topic_epoch/turn/seat/model/outcome/completion_state/ttft/duration/word_count. Prompts and interjections are never passed to log_event (leak-tested). DEBATE_LOG_DIR env override for operators/tests; default ROOT/logs.
Self-caught during full-suite verification: logging block was defined after the CONFIG load site, so the startup-fatal handler hit a NameError before emitting FATAL/exit-2 (14 config-rejection tests failed). Fixed by relocating the block above the configuration load; all green.

## Tests Added or Modified
4 tests: required-field JSONL on completion; skip-reason logged; rotation bounds (maxBytes/backupCount); interjection-payload non-leak.

## Verification
narrow 4/4; FULL SUITE 166 passed / 0 failed in 45.87s; lifecycle PASS @1.055s clean shutdown; diff clean. Live log sample verified from real boot probe.

## Performance Impact
measured: one formatted json.dumps per lifecycle event (turn-rate cadence) - negligible; suite unchanged beyond new tests.
expected: none adverse on hot streaming path (no per-token logging by design).

## Security Impact
improvement: auditable outcome trail without secret-bearing payloads; leak assertion locks the boundary.
residual: log file itself is local plaintext at operator-controlled path.

## Open P0/P1
P0: 0. P1 selected: ALL CLOSED (health/ready/httpx/ws-isolation/insight-recovery/logs).

## Scope Control
Logging additive; hot path untouched; single-process invariant intact.

## Completion Effect
Phase 6 fully complete (S16.1-S16.6). Remaining before gates: Phase 8 model-context/performance items, then Phases 9-14 verification and distillation.