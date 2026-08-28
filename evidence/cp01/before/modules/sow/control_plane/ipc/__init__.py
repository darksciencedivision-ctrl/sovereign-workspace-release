"""Shell <-> control-plane IPC (Plan section 5, row "Shell <-> control plane IPC";
decision D-IPC-01).

D-IPC-01 verdict (operator-delegation, ruling 2026-07-16): the shell <-> control-plane
transport is a **loopback WebSocket carrying schema-validated envelopes** — the canonical
plan's recommendation, adopted as the default. WebSocket (not raw NDJSON like the MCP
transport, U6) is chosen because the desktop shell's connecting side is a Chromium/Node
process for which WebSocket is the native client; a hand-rolled RFC 6455 server on the
Python stdlib keeps us inside the build's no-pip constraint (prohibition 2.7) exactly as the
MCP transport did.

Governance path proven here (this is the system under test, not the byte framing):
  - per-node AUTHENTICATION at the transport (bearer credential, fail-closed) — reused from
    the MCP credential pattern (mcp_server/auth.py); MCP holds no authority (I-M2) and
    neither does this gateway beyond authenticate-then-forward;
  - every message is an ``envelope@1.0`` (schemas/message.schema.json, Plan 9.2) — the ONLY
    control channel (TB-2); terminal text is never parsed as a command;
  - INTEGRITY: hmac-sha256(payload) verified against the per-connection shared key
    (fail-closed on mismatch); responses are signed the same way so the shell can verify
    the control plane;
  - fail-closed on bad auth, bad schema, bad integrity, oversized frame, or disconnect.
"""
