"""Phase 3A Sovereign MCP shared-memory foundation (MVP-foundational).

Access/transport only — authorization lives in control_plane.policy (I-M2). Provides the
loopback server, per-node auth, memory lifecycle service over the SQLite/CAS store,
immutable append + CAS head pointers with explicit conflict records (D-MCP-03), and a
fail-closed client.

Exports are lazily resolved via __getattr__ so that importing the pure `mcp_server.lifecycle`
module (which control_plane.policy depends on) does not pull in `server` -> `policy` and
create an import cycle.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "CredentialStore", "MemoryService", "MemoryServiceError",
    "McpClient", "McpDisconnected", "McpError", "MCPServer",
]

_LAZY = {
    "CredentialStore": ("mcp_server.auth", "CredentialStore"),
    "MemoryService": ("mcp_server.memory_service", "MemoryService"),
    "MemoryServiceError": ("mcp_server.memory_service", "MemoryServiceError"),
    "McpClient": ("mcp_server.protocol", "McpClient"),
    "McpDisconnected": ("mcp_server.protocol", "McpDisconnected"),
    "McpError": ("mcp_server.protocol", "McpError"),
    "MCPServer": ("mcp_server.server", "MCPServer"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        import importlib
        module_name, attr = _LAZY[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
