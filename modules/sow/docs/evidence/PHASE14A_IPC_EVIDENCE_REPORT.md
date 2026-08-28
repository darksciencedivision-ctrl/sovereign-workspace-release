# PHASE 14A SUB-STEP EVIDENCE — Authenticated Loopback IPC (D-IPC-01)
Autonomous loop iteration 15 · 2026-07-18Z · sub-step `phase-14a.ipc` · **no gate tag yet**
(the `gate/phase-14a` high-stakes gate closes only when all 14A sub-steps land; this report
covers the first, headless-testable sub-step and closes decision D-IPC-01).

## Objective
Deliver the foundational leg of Phase 14A (directive §9 track 14A): the **authenticated
loopback IPC** between the desktop shell and the existing control plane, with schema-validated
envelopes — the piece the directive names "D-IPC-01 activates". This is the deterministic,
governance-bearing backbone every later 14A sub-step (terminal canvas, tiling, inspector,
recovery) rides on, and it is fully verifiable in a headless, non-interactive session (no GUI).

## D-IPC-01 verdict (closed this sub-step)
**Loopback WebSocket carrying schema-validated envelopes** — the Architecture Plan v1.0.1 §5
recommendation, adopted as the default per operator-delegation (ruling 2026-07-16; disposition
was DEFERRED-to-product-UI-phase, completion audit F1). WebSocket (not the MCP transport's raw
NDJSON, U6) because the shell's connecting side is a Chromium/Node process for which WebSocket
is native. Implemented as a hand-rolled **RFC 6455 server on the Python stdlib** — no pip
(prohibition §2.7), exactly as the MCP transport was hand-rolled for the same reason.

## Source state
Tags through `gate/phase-13` + `build/complete` + `audit/completion-20260718`; `next_step:
phase-14a`; no `gate/phase-14a`. State/tags agree (reconciled: `last_commit` refreshed from the
stale phase-13 hash — intervening commits were loop-runner fixes, not work units). Freeze set
untouched; `docs/canonical/` not modified.

## Files (work commit)
- `control_plane/ipc/wsframe.py` — minimal RFC 6455 codec + handshake (stdlib): masking
  asymmetry enforced (server requires masked inbound, client requires unmasked), 126/127 length
  paths, control frames (close/ping→auto-pong), `MAX_MESSAGE` pre-buffer bound (F6), EOF→WsClosed.
- `control_plane/ipc/envelope.py` — `envelope@1.0` schema validation (Draft7 + FormatChecker
  against `schemas/message.schema.json`) **and the missing hmac-sha256(payload) compute/verify
  pair** (constant-time `hmac.compare_digest`); canonicalization = sorted-key compact UTF-8.
- `control_plane/ipc/gateway.py` — `IpcGateway` + `IpcCredentialStore` (token+per-node HMAC key)
  + `ControlSurface` protocol with `EchoControlSurface` (diagnostic) and `McpControlSurface`
  (bridge to the running MCP server). Authenticate → bind identity → verify integrity → forward.
- `control_plane/ipc/client.py` — stdlib reference `IpcClient` (the Node/Chromium shell mirrors
  this contract); fail-closed `IpcDisconnected`/`IpcIntegrityError`, verifies response integrity.
- `control_plane/ipc/run_gateway.py` — separate-process entry point (`IPC_PORT=` handshake,
  optional `IPC_TOKEN=`/`IPC_KEY=` bootstrap), 127.0.0.1-only, echo or `--mcp-*` bridge surface.
- Tests: `tests/unit/test_ipc_wsframe.py` (12), `tests/unit/test_ipc_envelope.py` (10),
  `tests/integration/test_ipc_gateway.py` (6, real subprocesses).

## Exit criteria for the sub-step — met, mapped to code + test
- **Loopback WebSocket, real RFC 6455:** accept-key verified against the RFC §1.3 worked
  example; framing exercised over a real `socket.socketpair()` across 0/5/125/126/200/65535/
  65536/70000-byte payloads; binds 127.0.0.1 only.
- **Per-node authentication, fail-closed:** unknown credential → connection dropped, not served
  (`test_bad_credential_is_closed_fail_closed`, pins reason `authentication failed`).
- **Schema-validated envelopes (TB-2):** only objects passing `validate_structure` reach the
  surface; malformed → close (`test_malformed_envelope_is_closed_fail_closed`, pins
  `envelope failed schema`). Unit tests cover missing field / bad integrity pattern / additional
  property / bad payload_schema pattern.
- **Integrity actually computed + verified:** `hmac` appears nowhere in the pre-existing tree
  (validator-corroborated); tampered payload / wrong key → rejected (unit + integration, latter
  pins `integrity check failed`). Constant-time compare.
- **Identity binding (anti-spoof):** valid credential + mismatched `from_node` → rejected
  (`test_identity_spoof_is_closed_fail_closed`, pins `identity mismatch`).
- **Bridge to the EXISTING control plane:** `test_bridge_to_existing_control_plane_mcp` spawns
  three real processes (MCP server → IPC gateway `--mcp-*` → `IpcClient`), sends `{"op":"health"}`,
  and receives the MCP server's own health verdict back through the gateway.
- **No authorization logic in the gateway (I-7/I-M2 analogue):** authenticate-then-forward only;
  `SovereignPolicy` is not imported; `role`/`scope` are carried, never used for a decision.

## Independent review (both run pre-commit, on the completed sub-step)
- **gate-validator: PASS_WITH_RESERVATIONS.** All 8 checked criteria met with reproduced
  command output; full suite `364 passed`. Confirmed each fail-closed negative test is
  load-bearing (removing the matching gateway check would serve the request or raise a different
  exception). Reservations (non-blocking): (R1) negative tests didn't pin close reason →
  **FIXED** (reasons now pinned); (R2) no external-interface negative test (loopback established
  by code + tests); (R3) plaintext loopback + app-layer HMAC, no TLS — matches the D-IPC-01
  recommendation, appropriate for 127.0.0.1; (R4) validated pre-commit per the two-commit
  convention.
- **spec-auditor: CLEAN on all load-bearing invariants** (I-7/I-M2, TB-2, fail-closed,
  determinism, no last-write-wins, offline honesty). MINOR notes: (M1) `McpControlSurface`
  docstring overstated per-node identity flow → **FIXED** (docstring now states the honest
  limitation — one MCP credential for all IPC nodes, read-only-only, per-node broker required
  before write ops; tracked as a 14A follow-up → new U25); (M2) bootstrap role defaults to
  `operator` — no effect (role unenforced here) and semantically the shell IS the operator
  console; recorded, not changed; (M3) close-code ladder doc mismatch → **FIXED**. Integrity
  covers `payload` only, matching the schema; routing metadata is not cryptographically
  tamper-proof but spoofing still requires the per-node token+key (noted, not a defect).

## Substitutions (loop directive §6)
- **GUI verification deferred, not faked.** This sub-step is pure control-plane/transport code
  with no window to render, so it is fully verified headlessly. The remaining 14A sub-steps
  (Electron canvas, tiling, inspector) that DO have a rendered surface will follow the Phase 1
  substitution pattern (headless logic tests for pure algorithms + an operator Windows run for
  the actual window); recorded now so no later iteration overclaims a GUI it cannot observe here.

## Deviations / carried
- **ruff unavailable** (pip out of scope, prohibition §2.7) — code is typed, stdlib-first,
  `py -3.12` byte-compiles clean; imported and exercised by the full suite.
- **Canonical interpreter** is `py -3.12` (Python 3.12.10, D-LANG-01); bare `python` on host is
  3.14 and lacks jsonschema — recorded so future iterations and the validator use `py -3.12`.
- **U25 (new):** IPC→MCP per-node credential broker required before `McpControlSurface` (or any
  IPC bridge) may carry write ops; today the bridge is read-only under one MCP credential.

## Sub-step verdict
**PASS (sub-step).** Authenticated loopback WebSocket IPC with schema-validated, integrity-
checked envelopes; fail-closed on bad auth / bad schema / bad integrity / spoofed identity /
malformed bytes / disconnect; real bridge proven to the existing MCP control plane; no
authorization logic in the transport. 34 new tests; **364/364** suite green; both independent
reviewers favorable with all actionable findings fixed pre-commit. **D-IPC-01 CLOSED.**
`gate/phase-14a` is NOT tagged — the phase gate (mandatory high-stakes gate-validator) awaits
the remaining 14A sub-steps.

## Commits
Work `7eb96e3` → this evidence/register commit (carries the work hash) → loop-state commit.
**No gate tag** (sub-step; `gate/phase-14a` awaits the remaining 14A sub-steps).

## Next
`phase-14a.shell` — Electron main/preload + xterm.js/node-pty terminal canvas in `apps/desktop`
+ `terminal/`, pane create/destroy, ConPTY sessions supervised by the real Node Runtime, and a
Node IPC client mirroring `control_plane/ipc/client.py`. Then `.tiling` (Plan §10.2, headless
JS logic tests), `.inspector`, `.recovery`; the `gate/phase-14a` high-stakes gate closes when
all land.
