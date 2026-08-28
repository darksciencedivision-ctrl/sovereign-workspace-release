# Round 9 Evidence Packet

## Delta
- P1 IDs: P1-ws-isolation, P1-insight-recovery
- Commit: (HEAD)
- Files changed: app.py, tests/test_v1_2_1_ws_isolation.py (new)
- Functions changed: Hub (ClientConnection registry, non-blocking enqueue broadcast, yield-once-before-evict policy, _sender task w/ 10s timeout, 1013 disconnects); ws_endpoint lifecycle; InsightManager (INSIGHT_INSTALLED_TTL_S=30 re-probe, counters queued/completed/cancelled/dropped/unavailable, stats()); /ready exposes insight stats when panel enabled

## Root Cause
Sequential per-client awaits let one stalled socket block every broadcast including generation tokens. Insight availability was cached forever INCLUDING transient negatives.

## Implementation
send() = enqueue-only; contention path yields once to let the sender drain before declaring a client too slow (protects healthy peers during bursts - defect caught by this round's own measured test: first implementation evicted the healthy client at exactly QUEUE_MAX=256). Overflow/wedge/timeout => counted disconnect code 1013. Sender owns socket writes under timeout.

## Tests Added or Modified
6 tests incl MEASURED: BROADCAST_300_ELAPSED=0.0031s with slow peer present (old design: indefinite block on message #1); overflow eviction count+code; wedged-socket sender timeout; insight negative->complete TTL recovery proving second probe; counter instrumentation; reset-drain counting.

## Verification
narrow 6/6; full suite 156 passed / 0 failed in 43.28s; lifecycle PASS @1.048s clean shutdown; diff clean.

## Performance Impact
measured: broadcast fanout now O(enqueue) ~3ms for 300 events x2 clients vs old O(n_slow) blocking.
expected: generation token path no longer coupled to weakest client.

## Security Impact
improvement: slowloris-style WebSocket consumers cannot stall the debate loop or exhaust server memory (bounded queues).
residual: eviction is per-connection; an attacker cycling connections still costs accept/handshake work (loopback-only exposure mitigates).

## Open P0
0. P1 remaining: P1-logs (+ Phase 7 heuristics cluster).

## Scope Control
Hub/insight internals only; routes/UI untouched; single-process invariant intact.

## Completion Effect
Phase 6b complete. Phase 6 remains P1-logs; then Phase 7 heuristics, Phase 8 context/perf, verification gates and distillation.