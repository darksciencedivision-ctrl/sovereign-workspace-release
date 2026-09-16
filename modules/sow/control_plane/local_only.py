"""Central runtime policy for the Sovereign Workspace deployment.

The product is deployed in local-only mode.  Keeping this decision in one small, dependency-free
module prevents a picker or a secondary spawn route from accidentally re-enabling a commercial
provider when the live-operation file is absent.
"""
from __future__ import annotations

LOCAL_ONLY_MODE = True

COMMERCIAL_FRONTIER_ADAPTERS = frozenset({
    "claude_code",
    "openai_codex_cli",
    "grok_build",
    "google_antigravity",
})

LOCAL_ONLY_REASON = "commercial frontier cloud providers are disabled by the local-only policy"


def frontier_disabled(adapter_id: object) -> bool:
    return LOCAL_ONLY_MODE and adapter_id in COMMERCIAL_FRONTIER_ADAPTERS
