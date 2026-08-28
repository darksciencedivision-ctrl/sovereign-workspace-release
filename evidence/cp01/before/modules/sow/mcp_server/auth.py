"""Per-node authentication for the MCP server (Plan section 9.5).

This is AUTHENTICATION (who is calling), not AUTHORIZATION (what they may do — that is the
control plane's policy, I-M2). Sovereign issues a random bearer token per node at spawn and
maps it to an Identity. The MCP server verifies the token to obtain the identity, then hands
that identity to the policy for every decision. Tokens are opaque; they never encode rights.
"""
from __future__ import annotations

import secrets
import threading

from control_plane.policy import Identity


class CredentialStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_token: dict[str, Identity] = {}

    def issue(self, node_id: str, role: str, project_id: str) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._by_token[token] = Identity(node_id=node_id, role=role, project_id=project_id)
        return token

    def verify(self, token: str) -> Identity | None:
        with self._lock:
            return self._by_token.get(token)

    def revoke(self, token: str) -> None:
        with self._lock:
            self._by_token.pop(token, None)
