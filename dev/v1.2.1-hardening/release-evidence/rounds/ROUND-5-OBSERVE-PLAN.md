# ROUND-5-OBSERVATION

Round: 5 | HEAD: 1b3e038 | Open P0: 9
Cluster: P0-13 stream lifecycle + P0-14 cancellation race

## Findings

1. ollama_chat streaming loop (app.py ~600-655): NO done_seen tracking; EOF-without-done falls through to success return -> AC-10 violation (P0-13 core).
2. json.loads(line) at ~613 unguarded -> malformed NDJSON surfaces as generic JSONDecodeError -> classified generation_error instead of protocol error.
3. Interrupt checked only between lines (~609): stalled upstream = pause waits until 600s timeout (P0-14).
4. Non-streaming branch plain client.post - uncancellable; generate_topic (847)/refresh_anchor (888) call it without interruptible AND their broad `except Exception` would swallow TurnInterrupted anyway.
5. Startup topic (orchestrator:1321) unprotected: an interruption there would kill the orchestrator task silently.
6. Continuation call (1199) short non-streaming - leave non-interruptible this round.
7. No transport injection point in ollama_chat -> tests need minimal optional `transport=None` seam.
8. tc.classify already distinguishes truncated/budget states; Phase 4 will formalize TurnOutcome; this round wires protocol outcomes into turn_skipped reasons.

# ROUND-5-PLAN

## Change surface
- app.py exceptions: StreamProtocolError(detail), StreamIncomplete near TurnInterrupted; constant STREAM_INACTIVITY_SECONDS=30.0 (module global, monkeypatchable).
- ollama_chat: optional transport=None param; streaming loop rebuilt as concurrent race (next-line vs interrupt-event vs inactivity timer) with per-line reset; done_seen tracking; malformed line -> StreamProtocolError w/ snippet; EOF w/o done -> StreamIncomplete; metrics gain done_seen/stream_protocol/interrupt_reason; non-streaming branch races client.send against interrupt when interruptible=True.
- generate_topic + refresh_anchor: interruptible=True; except TurnInterrupted: raise placed ahead of broad excepts.
- orchestrator startup: first-topic guarded against TurnInterrupted -> fallback topic.
- run_turn: extract _emit_skip(seat,turn_number,model,reason,attempt_metrics); add StreamProtocolError->"protocol_error" and StreamIncomplete->"protocol_incomplete" catches before generic Exception.

## Non-change surface
OutputGuard/SentenceBuffer, hub, move selection, insight worker, bootstrap scripts, UI.

## Tests first (tests/test_v1_2_1_stream_protocol.py, httpx.MockTransport via new seam)
T1 normal stream ends with done -> text returned; metrics done_seen=True
T2 EOF without done -> StreamIncomplete
T3 malformed NDJSON -> StreamProtocolError (detail contains snippet)
T4 empty output WITH done -> "" returned (empty accounting stays Phase 4)
T5 stall-then-pause: first chunk then infinite hang; interrupt at ~50ms -> TurnInterrupted observed; measured cancel latency <=500ms recorded in test output
T6 inactivity: STREAM_INACTIVITY_SECONDS=0.05 monkeypatched, silent stream -> TurnInterrupted with interrupt_reason=inactivity
T7 non-streaming cancellable: slow POST + interrupt -> TurnInterrupted <500ms (generate_topic path, asserting NOT swallowed into fallback)
T8 HTTP 500 -> generic error path unchanged

## Failure modes
Iterator-task leak warnings (mitigate: consume cancelled task exceptions); TestClient-free pure-async tests keep this fast.

## Rollback
Single commit revert.

## Acceptance
T1-T8 green incl printed cancel-latency <=0.5s; full suite green (118+new); lifecycle PASS.

This delta moves the Distillery Module closer to completion by closing P0-13 and P0-14 and adding regression tests for missing-done EOF, malformed NDJSON, stalled-stream cancellation timing, topic-generation cancellation, and protocol-error classification.