"""Debate evidence manager (Plan §19.2, §19.3; prohibited drift: model votes are not evidence).

Validates that every assertion's citations resolve to REAL MCP entries. Resolution is not
entailment: a resolvable citation is REFERENCE_RESOLVED, never SUPPORTED. This component
does not claim that a cited source supports, proves, verifies, or entails the assertion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CitationCheck:
    ref: str
    resolves: bool


class EvidenceManager:
    def __init__(self, resolver: Callable[[str], bool]) -> None:
        """resolver(ref) -> True if the ref resolves to a real MCP entry/artifact."""
        self._resolves = resolver

    def check_refs(self, evidence_refs: list[str]) -> list[CitationCheck]:
        return [CitationCheck(r, bool(self._resolves(r))) for r in evidence_refs]

    def classify_assertion(self, position: str, evidence_refs: list[str]) -> dict[str, Any]:
        """Return citation-resolution only. Assertion text is unused for the verdict."""
        del position  # retained at the caller for audit; not an entailment input
        checks = self.check_refs(evidence_refs)
        resolving = [c.ref for c in checks if c.resolves]
        return {
            "reference_resolved": bool(resolving),
            "resolving_refs": resolving,
            "unresolved_refs": [c.ref for c in checks if not c.resolves],
            "status": "REFERENCE_RESOLVED" if resolving else "UNRESOLVED",
            "legacy_supported_field_removed": True,
        }


def mcp_resolver(mcp_reader: Any) -> Callable[[str], bool]:
    """Build a resolver over an MCP client: a ref resolves if it's a readable memory entry
    (m-...) or a stored artifact (sha256:...). Failures resolve to False (fail closed)."""
    def _resolve(ref: str) -> bool:
        try:
            if ref.startswith("sha256:"):
                mcp_reader.call("get_artifact", artifact_id=ref)
                return True
            if ref.startswith("m-"):
                base = ref.split("@", 1)[0]
                return mcp_reader.call("get_head", entry_id=base) is not None
        except Exception:
            return False
        return False
    return _resolve
