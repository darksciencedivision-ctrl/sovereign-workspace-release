# Round 4 Evidence Packet

## Delta
- P0/P1 IDs: P0-10, P0-11, P0-12
- Commit: 1b3e038
- Files changed: debate/control_plane_guard.py (new), app.py, tests/test_v1_2_1_control_plane.py (new)
- Functions changed: new LoopbackControlPlaneGuard ASGI middleware (installed via add_middleware with live CONFIG reference); build_allowed_origins/_host_is_permitted/_origin_permitted; DEFAULTS.allow_originless_ws_clients=True + coercion

## Root Cause
Trust decisions were absent at the ASGI entry: ws.accept() ran for any origin, Host was never inspected, and POST routes had no cross-site defense.

## Implementation
Raw ASGI middleware polices both scopes pre-dispatch. Host must be loopback hostname with matching port (421/close otherwise). WS foreign Origin closed code 1008 BEFORE accept; absent Origin allowed only under explicit allow_originless_ws_clients=true (documented non-browser exception - browsers cannot suppress Origin). Mutations (/api/* POST except read-only /api/models) reject Sec-Fetch-Site=cross-site or non-permitted Origin with 403 JSON. No CORS middleware exists or was added.

## Tests Added or Modified
9 tests: invalid hosts x3 forms + wrong-port host -> 421; valid loopback hosts x3 -> 200; foreign-origin pause -> 403; cross-site sec-fetch pause -> 403; same-origin 200 + originless non-browser 200; foreign WS origin disconnected before any snapshot; allowed-origin WS receives snapshot; originless tooling WS receives snapshot.
Test-harness iterations (httpx ASGITransport async API, TestClient receive_json signature) were test-side only.

## Verification
- narrow: 9/9 control-plane tests
- full suite: 118 passed / 0 failed in 30.36s (84 original preserved)
- hostile probe: real-server lifecycle PASS (http 200 @1.065s, python websockets client - no Origin - receives snapshot, clean shutdown, zero orphans) proving the guard does not break the legitimate local path
- diff hygiene clean

## Performance Impact
- measured: boot 1.065s unchanged; per-request header dict scan O(n<=20)
- expected: negligible
- unknown: none

## Security Impact
- improvement: snapshot no longer served to evil.example; DNS-rebinding-style Host confusion blocked; foreign/cross-site browser mutations blocked
- new attack surface: none (middleware narrows behavior); bypass requires a browser that suppresses Origin AND Sec-Fetch-Site on cross-site POST - not a modern browser behavior
- residual risk: non-browser local processes remain trusted by design under default flag; operators can set allow_originless_ws_clients=false to harden further (tooling then must send permitted Origin)

## Residual Risk
None new; documented flag semantics to be included in PRODUCTION-README during Phase 12.

## Open P0
9 remaining: P0-06..P0-09 (output guard cluster), P0-13..P0-15, P0-19, P0-20

## Scope Control
Middleware is additive and self-contained; route handlers untouched; UI untouched.

## Completion Effect
Phase 2 exit gate satisfied: valid local UI verified working (lifecycle), foreign WS rejected, foreign mutation rejected, static/GET unaffected, full regression green.