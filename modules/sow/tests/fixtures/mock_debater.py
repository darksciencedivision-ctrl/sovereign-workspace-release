"""Deterministic mock debater (test fixture). Stands in for a model participant so the Debate
Service mechanics (rounds, budget, dissent, evidence) are exercised without live inference.
Configurable to converge on a shared position after N rounds, to hold a fixed dissenting
position forever, and to cite valid or invalid evidence."""
from __future__ import annotations

from typing import Any


class MockDebater:
    def __init__(self, node_id: str, position: str, *, converge_to: str | None = None,
                 converge_after: int | None = None, evidence_refs: list[str] | None = None) -> None:
        self.node_id = node_id
        self._position = position
        self._converge_to = converge_to
        self._converge_after = converge_after
        self._evidence_refs = evidence_refs or []

    def argue(self, topic: str, round_no: int, transcript: list[dict[str, Any]]) -> dict[str, Any]:
        position = self._position
        if self._converge_to is not None and self._converge_after is not None and round_no >= self._converge_after:
            position = self._converge_to
        return {"position": position, "evidence_refs": list(self._evidence_refs)}
