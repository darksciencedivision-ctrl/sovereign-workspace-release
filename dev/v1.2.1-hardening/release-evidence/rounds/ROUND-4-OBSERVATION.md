# ROUND-4-OBSERVATION

Round: 4
Current HEAD: d3b60dd (Phase 1 complete)
Working tree: clean
Selected defect cluster: P0-10 WebSocket Origin + P0-11 Host validation + P0-12 mutation-route protection
Open P0 before round: 12

## Affected surfaces

1. app.py:1389 ws_endpoint: `await ws.accept()` unconditionally - any origin receives the snapshot (P0-10).
2. No Host validation anywhere; app trusts whatever Host header arrives (P0-11). Single ASGI scope can police both http and websocket.
3. Mutation routes: /api/pause /api/resume /api/topic /api/brief /api/interject /api/seat_model /api/seat_thesis - all POST, no cross-origin defense (P0-12). GET /api/models is read-only.
4. CORS middleware: none configured - no wildcard exposure to remove; keep it that way.

## Policy design (documented honestly)

- Host: hostname must be in {127.0.0.1, localhost, ::1}; port must equal configured port or be absent. Violation -> 421 for http, close code 1008 for ws before accept.
- WS Origin: browsers cannot suppress Origin, so foreign-origin handshakes are rejected pre-accept. Absent Origin = non-browser client (operator tooling/tests); governed by explicit named policy allow_originless_ws_clients default true (loopback bind already gates local access) - documented as the authorized non-browser exception in the contract's language.
- Mutations: reject when Sec-Fetch-Site=cross-site OR (Origin present and not a permitted loopback origin matching host/port). Read-only endpoints untouched.

## Existing-behavior preservation check

tests/mock_ollama.py + test_smoke running_stack connect via python websockets WITHOUT Origin header -> preserved by the absent-origin allowance. Lifecycle probes same.

## Reason highest-priority

Phase 2 core; also prerequisite mental model for hostile E2E suite later (foreign-origin scenarios).
