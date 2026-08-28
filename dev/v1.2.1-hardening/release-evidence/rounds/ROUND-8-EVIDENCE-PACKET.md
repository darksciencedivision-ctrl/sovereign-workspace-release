# Round 8 Evidence Packet

## Delta
- P1 IDs: P1-httpx-lifespan, P1-health, P1-ready
- Commit: (HEAD)
- Files changed: app.py, tests/test_v1_2_1_health_ready.py (new)
- Functions changed: _acquire_client/close_http_client added; ollama_chat + installed_models use shared keepalive client; lifespan creates/closes it; new GET /health and GET /ready; timeout constants CHAT/MODELS/READY_HTTP_TIMEOUT

## Implementation notes
Test transport seam preserved: injected transports still get an ephemeral client. /ready probes installed_models (monkeypatchable), reports endpoint_class, per-seat installed flags, missing list incl conditional extractor, orchestrator counters (completed/skipped), http_client_active; never emits prompts/interjections (asserted by test). Status codes: 200 ready; 503 degraded/unavailable.

## Tests Added or Modified
7 tests: health schema/liveness; ready-ready; ready-unreachable 503 w/ error_type; degraded missing-model listing; no-leak assertion against state.interject; lifespan create->close of shared client across TestClient context; host-guard interplay for the new routes.

## Verification
narrow 7/7; full suite 150 passed / 0 failed in 42.35s; lifecycle PASS @1.043s boot + clean shutdown + ws snapshot; diff clean.

## Performance Impact
measured: suite wall time grew from added tests only; per-request connection reuse now available on real paths (keepalive) - tokens/sec effect to be captured in Phase 8/10 metrics rather than claimed here.
expected: fewer TCP handshakes per turn vs baseline per-call clients.

## Security Impact
improvement: readiness gives operators an honest dependency view without secrets; timeouts centralized.
new surface: two read-only endpoints behind existing Host guard (proven); no CORS added.
residual: /ready performs an Ollama probe per call - cheap at operator cadence; not intended for aggressive external polling (loopback-only exposure mitigates).

## Open P0
0. P1 remaining: P1-logs, P1-ws-isolation, P1-insight-recovery (+ Phase 7 heuristics).

## Scope Control
Endpoints are additive read-onlys; client lifecycle confined to lifespan; no architecture change.

## Completion Effect
Phase 6a complete: S16.1/S16.2/S16.4 satisfied with regression locks.