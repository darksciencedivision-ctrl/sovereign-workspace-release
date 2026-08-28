# Round 13 Evidence Packet - AC-04 hostile E2E floor COMPLETE

## Delta
- Phase: AC-04 completion (tests only; zero product code changes)
- Commit: 43695bd
- Files changed: tests/mock_ollama.py, tests/test_v1_2_1_hostile_e2e.py (new)
- Mock additions: stream modes http_500 / malformed_ndjson / partial_frame / no_done / stall_pause / echo_control (echoes the ACTUAL OPERATOR NOTE from the received prompt) / short_echo / model_404; control endpoints chat_failure/{n} and echo_payload

## Coverage vs AC-04 floor (17 scenarios)
Full-stack e2e NEW: HTTP 500 -> generation_error skip then recovery-to-completed-turn; malformed NDJSON -> protocol_error; partial frame -> protocol_error; missing done -> protocol_incomplete; deliberate stall + operator pause (MEASURED E2E_PAUSE_CANCEL=0.017s); long private-control echo blocked with CONTROL_TEXT_LEAK_BLOCKED diagnostics while clean speech completes the turn; unavailable-model 404 skip; chat-failure window recovery.
Previously proven full-stack: valid stream + reasoning-channel + empty-retry (test_smoke), continuation request, cancellation semantics. Unit-level with production components: reasoning-tag variants, short-control false positive, slow WS consumer isolation (R9 measured), cancellation SLA (R5 measured 0.3ms).
No mocked test bypasses the path it claims to validate: every new scenario runs real subprocess app+mock over real sockets.

## Tests Added or Modified
9 e2e tests. Two self-caught scenario defects fixed during red phase: (1) echo mode initially echoed a payload the app never held -> corrected to derive from the actual OPERATOR NOTE in the received prompt so the anti-echo loop is genuinely exercised end to end; (2) dead placeholder code removed.

## Verification
hostile suite 9/9 (-s measured print); FULL SUITE 181 passed / 0 failed in 86.23s; app/mock stderr traceback-free assertions inside fixture.

## Performance Impact
suite wall time +~40s from subprocess stacks; product runtime untouched.

## Security Impact
improvement: leak-block and protocol classification now proven through the real broadcast path, not just units.
residual: none new.

## Completion Effect
AC-04 satisfied. AC-01..AC-03, AC-08..AC-10 evidence complete; remaining contract items are process gates (Phase 9 lock artifact, 10 real-Ollama, 11 soak, 12-14 distillation/cold/review).