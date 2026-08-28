# Round 5 Evidence Packet

## Delta
- P0/P1 IDs: P0-13, P0-14
- Commit: 1647267
- Files changed: app.py, tests/test_v1_2_1_stream_protocol.py (new)
- Functions changed: ollama_chat streaming loop rebuilt as concurrent race + non-streaming branch races interrupt event + optional transport seam; new StreamProtocolError/StreamIncomplete/STREAM_INACTIVITY_SECONDS; _tracked/_consume_task hygiene; _emit_skip_turn extracted; run_turn classifies protocol_error/protocol_incomplete; generate_topic/refresh_anchor interruptible with re-raise; orchestrator first-topic interruption guard

## Root Cause
P0-13: no done_seen tracking - EOF fell through to success. P0-14: interruption polled only BETWEEN lines so a stalled upstream made pause wait out the 600s timeout; non-streaming calls uncancellable; topic/anchor broad excepts would swallow TurnInterrupted.

## Implementation
Per-chunk race: next-line vs interrupt-event vs inactivity timer (30s), timer reset per line. Malformed NDJSON -> StreamProtocolError(snippet). EOF without done -> StreamIncomplete. Metrics record done_seen/stream_protocol/interrupt_reason. Non-streaming POST races send against the event. Protocol faults become turn_skipped reasons protocol_error / protocol_incomplete. Startup first-topic interruption falls back rather than killing the loop.

## Tests Added or Modified
9 tests incl MEASURED probes: pause-during-stall CANCEL_LATENCY=0.0003s (SLA <=500ms met by ~3 orders); inactivity fires at configured floor (0.06s @ 0.05); non-stream cancel 0.0001s; missing-done EOF; malformed NDJSON; empty-with-done returns ""; HTTP 500 unchanged.
Self-caught during verification: cross-loop Event binding pollution (per-test fresh Event fixture; product stays single-loop per G-08); sync consumption of just-cancelled tasks raised InvalidStateError (moved to creation-time done-callbacks).

## Verification
narrow 9/9; full suite 127 passed / 0 failed in 30.00s (84 original preserved); lifecycle PASS @1.061s boot with clean shutdown; git diff --check clean.

## Performance Impact
measured: boot unchanged; per-line adds two task creations - no measurable regression in suite beyond added tests; real-model throughput captured later in Phase 8/10.

## Security Impact
improvement: truncated/malformed upstream responses can no longer masquerade as completed turns; silent streams cannot wedge the loop past operator cancel. residual: continuation call remains non-interruptible (short bounded call) - documented.

## Open P0
7 remaining: P0-06..P0-09, P0-15, P0-19, P0-20

## Scope Control
Exceptions+race live inside existing generation layer; routes/UI untouched; single-process invariant intact.

## Completion Effect
Phase 3 exit gate satisfied: done-success, missing-done rejection, malformed classification, measured stall cancellation, topic cancellation, full regression green.