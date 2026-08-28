# ROUND-9 OBSERVE+PLAN (Phase 6b - concurrency resilience P1s)

HEAD: 397de9c | Cluster: P1-ws-isolation, P1-insight-recovery

## Observations
1. Hub.send (app.py:485-495) awaits each client sequentially - one slow/stalled WebSocket delays every broadcast INCLUDING generation token emission (on_public path). P0-class UX hazard, P1 per contract.
2. ws_endpoint registers raw WebSocket in hub.clients; no queue, no send timeout; discard-on-exception only.
3. InsightManager.installed cached forever incl. NEGATIVE result from a transient installed_models() failure (1092, 1149-1153) - violates S16.6.
4. No instrumentation of queued/completed/cancelled/dropped/unavailable for insight pipeline.
5. Existing tests only monkeypatch hub.send - signature preserved by plan; nothing reads hub.clients externally except ws_endpoint.

## Plan
### Change surface
1. New ClientConnection (bounded queue 256) + Hub rewrite: register/unregister, non-blocking enqueue broadcast with explicit overflow policy = count + async disconnect (close code 1013), per-client sender task with SEND timeout 10s; broadcast_dropped_total counter. Constants CLIENT_QUEUE_MAX/CLIENT_SEND_TIMEOUT_S monkeypatchable.
2. ws_endpoint: register conn + start sender; finally unregister+join sender.
3. InsightManager: INSIGHT_INSTALLED_TTL_S=30 re-probe gate on self.installed (transient negative recovers); counters dict {queued,completed,cancelled,dropped,unavailable}; reset() counts drained as dropped; enqueue counts queued(+evicted dropped); _extract/_unavailable/preempt update counters; stats() accessor surfaced in /ready when manager present.
### Non-change surface
Route handlers, guard, output guard, orchestrator logic, UI.
### Tests first (tests/test_v1_2_1_ws_isolation.py)
T1 MEASURED isolation: fast+slow stub clients, 300 broadcasts complete <1s, fast receives all, slow disconnected after overflow (old design would stall on msg #1)
T2 overflow disconnect increments broadcast_dropped_total and closes with 1013
T3 wedged socket: sender send-timeout disconnects (constant patched to 0.05s)
T4 insight negative->recovery via TTL re-probe (patched TTL 0.05s)
T5 insight counters increment across queued/complete/unavailable/dropped paths
T6 reset drains queue counting drops

## Acceptance
T1-T6 green w/ printed timings; full suite green; lifecycle PASS. Single-commit rollback.
This delta advances Phase 6 by closing P1-ws-isolation and P1-insight-recovery with measured regression locks.