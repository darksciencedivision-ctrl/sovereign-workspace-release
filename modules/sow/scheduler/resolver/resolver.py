"""Capability resolver (Plan §9.7; I-SC1).

Resolves a task's capability requirement to a node by DESCRIPTOR — filter by hard
requirements, then rank. Vendor/model names never enter this path (invariant: no hard-coded
vendor names where a descriptor belongs). Under an active deployment profile, ineligible
nodes are filtered out (offline excludes non-offline-eligible nodes, I-D2). If nothing
qualifies, the resolver returns a NoNode result carrying the reason (surfaced, never silent).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scheduler.capability_registry.registry import CapabilityRegistry, RegisteredNode


@dataclass(frozen=True)
class Resolution:
    node_id: str | None
    rationale: str
    ranked: tuple[tuple[str, float], ...] = ()  # (node_id, score) for the trace

    @property
    def resolved(self) -> bool:
        return self.node_id is not None


def _meets(node: RegisteredNode, req: dict[str, Any], profile_airgapped: bool) -> tuple[bool, str]:
    capability = req.get("capability")
    reqs = req.get("requirements", {})
    node_caps = {c.get("capability"): c for c in node.capabilities}
    if capability not in node_caps:
        return False, f"lacks capability {capability!r}"
    provided = node_caps[capability].get("requirements", {})
    if reqs.get("tool_use") and not provided.get("tool_use"):
        return False, "requires tool_use"
    if reqs.get("structured_output") and not provided.get("structured_output"):
        return False, "requires structured_output"
    if reqs.get("min_context", 0) > provided.get("min_context", 0):
        return False, f"needs >= {reqs['min_context']} ctx, has {provided.get('min_context', 0)}"
    req_harness = reqs.get("harness_class")
    if req_harness:  # a non-null harness requirement must be provided by the node (fail closed)
        if provided.get("harness_class") != req_harness:
            return False, f"requires harness_class {req_harness!r}, node provides {provided.get('harness_class')!r}"
    locality = reqs.get("locality", "any")
    if locality == "local_only" and node.locality != "local":
        return False, "requires local_only"
    if profile_airgapped and not node.offline_profile_eligible:
        return False, "not offline-eligible under air-gapped profile"
    return True, "meets requirements"


class CapabilityResolver:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def resolve(self, capability_req: dict[str, Any], *, profile_airgapped: bool = False) -> Resolution:
        eligible: list[tuple[RegisteredNode, str]] = []
        rejected: list[str] = []
        for node in self._registry.all_nodes():
            ok, why = _meets(node, capability_req, profile_airgapped)
            (eligible if ok else rejected).append((node, why) if ok else f"{node.node_id}: {why}")
        if not eligible:
            return Resolution(None, f"no node meets {capability_req.get('capability')!r} "
                                    f"requirements; rejected: {rejected}")
        # rank: prefer higher benchmark, then lower load, then local cost class
        def score(entry: tuple[RegisteredNode, str]) -> float:
            n = entry[0]
            return n.benchmark_score - 0.1 * n.active_tasks - (0.05 if n.cost_class == "subscription" else 0.0)
        # rank by score desc, then node_id asc as a STABLE tie-break (not registration order)
        eligible.sort(key=lambda e: (-score(e), e[0].node_id))
        ranked = tuple((n.node_id, round(score((n, w)), 4)) for n, w in eligible)
        winner = eligible[0][0]
        return Resolution(winner.node_id,
                          f"resolved {capability_req.get('capability')!r} to {winner.node_id} by descriptor "
                          f"(score-ranked, {len(eligible)} eligible)", ranked)
