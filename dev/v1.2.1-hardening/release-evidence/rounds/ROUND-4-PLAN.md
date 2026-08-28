# ROUND-4-PLAN

## Problem
WS accepts any origin pre-accept; HTTP/ws accept arbitrary Host headers; state-changing POSTs lack cross-site defenses.

## Root cause
No ASGI entry guard exists; handshake/trust decisions were left to route handlers (i.e., nobody).

## Change surface
- debate/config_policy.py: LOOPBACK_ORIGINS helper build_allowed_origins(port) -> {http://127.0.0.1:p, http://localhost:p, http://[::1]:p}.
- app.py: new pure functions validate_host(headers, port)->bool and classify_ws_origin(origin_header, allowed)->"ok"|"absent"|"foreign"; ASGI middleware installed via app.add_middleware(BaseHTTPMiddleware subclass? NO - use raw @app.middleware("http") style is BaseHTTPMiddleware anyway; for WS coverage implement raw ASGI wrapper class LoopbackGuard mounted by wrapping app) enforcing: Host rule on all scopes; WS origin rule pre-accept (close 1008 when foreign); POST mutation rules (403 JSON {"error":...}).
- DEFAULTS["allow_originless_ws_clients"]=True with bool coercion.
- tests/test_v1_2_1_control_plane.py (new): direct unit calls into guard functions + live ASGI behavior through TestClient-style httpx ASGITransport incl websocket connect for foreign/ok/absent origins.

## Non-change surface
Route handlers, hub, stream logic, UI, bootstrap.

## Tests first (AC-03 floor items #24 #25 #26)
T1 foreign WS Origin https://evil.example -> connection closed/rejected BEFORE snapshot (no snapshot message received)
T2 invalid Host evil.example:8700 on GET / -> 421; on WS scope -> rejected
T3 valid loopback hosts accepted (127.0.0.1:port, localhost:port)
T4 foreign-origin POST /api/pause -> 403; Sec-Fetch-Site=cross-site -> 403 even with matching Origin absent
T5 same-origin POST /api/pause -> 200 ok:true
T6 originless python WS client still connects (non-browser policy)
T7 absent-origin POST from non-browser (plain httpx) still allowed (mutations are browser-defended only)

## Failure modes
Starlette TestClient quirks vs real uvicorn (mitigate: lifecycle probe rerun + existing smoke suite covers real server path); ::1 bracket forms.

## Rollback
Revert single commit (middleware additive).

## Acceptance
T1..T7 green; full suite green (109+new); lifecycle PASS.

This delta moves the Distillery Module closer to completion by closing P0-10, P0-11 and P0-12 and adding regression tests for foreign WebSocket Origin, invalid Host, and foreign-origin mutation requests.
