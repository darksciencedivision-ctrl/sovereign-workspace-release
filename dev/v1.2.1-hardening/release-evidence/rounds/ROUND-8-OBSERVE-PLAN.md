# ROUND-8 OBSERVE+PLAN (Phase 6a - lifecycle & observability P1s)

HEAD: b5783b6 | Open P0: 0 | Cluster: P1-httpx-lifespan, P1-health, P1-ready

## Observations
- Per-call httpx.AsyncClient at app.py:659-660 (chat, Timeout(600,c10)) and 791-792 (models, Timeout(15,c5)); no shared keepalive connection pool; no centralized timeout policy.
- lifespan (1557-1573) starts/stops insight worker + orchestrator; natural owner for process-lifetime client.
- No /health or /ready endpoints exist.
- Guard treats GET as read-only -> new endpoints need no mutation logic; Host/Origin guard still applies (desired).

## Plan
### Change surface
1. app.py constants: CHAT_HTTP_TIMEOUT/MODELS_HTTP_TIMEOUT/READY_HTTP_TIMEOUT; _http_client=None; _STARTED_MONOTONIC; _BUILD_VERSION from BUILD-INFO.json (utf-8-sig, fallback "unknown").
2. _acquire_client(timeout, transport=None) asynccontextmanager: yields shared client when available and no injected transport (test seam preserved); else ephemeral.
3. ollama_chat + installed_models switch to _acquire_client (one-line changes each).
4. lifespan startup: _http_client = AsyncClient(CHAT_HTTP_TIMEOUT); finally: aclose + None (after orchestrator join so in-flight streams finish first).
5. GET /health: {status:"ok", version, uptime_seconds, config_loaded:true, generation_active} per S16.1.
6. GET /ready: probes installed_models via READY_HTTP_TIMEOUT-backed call path (monkeypatchable seam unchanged); reports ollama reachability + endpoint_class, per-seat installed flags, missing list incl extractor when insight_panel, orchestrator state summary (status/paused/topic_epoch/completed_public_turns/skipped_turns), http_client_active. No secrets/prompts/interjections. 200 when reachable&complete ("ready"); 503 otherwise ("degraded"/"unavailable").
### Non-change surface
Guard semantics, existing routes/handlers, hub, UI, bootstrap scripts.
### Tests first (tests/test_v1_2_1_health_ready.py)
T1 /health schema+200+uptime>=0+config_loaded true
T2 /ready all-models-present -> 200 ready, endpoint_class loopback, missing []
T3 /ready unreachable -> 503 unavailable, reachable false
T4 /ready missing seat model -> degraded + missing list names model
T5 TestClient lifespan context creates then closes _http_client
T6 response contains no prompt/interjection keys
T7 both endpoints pass Host guard with permitted host (regression of R4 interplay)

## Acceptance
T1..T7 green; full suite green; lifecycle probe PASS. Rollback single revert.
This delta advances Phase 6 by closing P1-httpx-lifespan, P1-health, P1-ready and adding their regression tests.