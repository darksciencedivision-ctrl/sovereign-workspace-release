from __future__ import annotations

from collections import defaultdict, deque

from distillery.common import ContractError, sha256_value


def _validate_lineage_nodes(nodes: list[dict]) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            raise ContractError("lineage node must be an object")
        sample_id = node.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id:
            raise ContractError("lineage node requires non-empty string sample_id")
        for field in ("derived_from", "source_ids"):
            value = node.get(field, [])
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                raise ContractError(f"lineage node {sample_id} has malformed {field}")
        if not isinstance(node.get("shard_hash"), str) or not node.get("shard_hash"):
            raise ContractError(f"lineage node {sample_id} requires non-empty string shard_hash")


def _reject_illegal_cycles(nodes: list[dict]) -> None:
    parents = {node["sample_id"]: set(node.get("derived_from", [])) for node in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for child_id in sorted(parents):
        for parent in sorted(parents[child_id]):
            children[parent].append(child_id)
    pending = {child_id: len(parent_ids) for child_id, parent_ids in parents.items()}
    frontier = deque(sorted(child_id for child_id, count in pending.items() if count == 0))
    while frontier:
        current = frontier.popleft()
        for child in sorted(children.get(current, ())):
            pending[child] -= 1
            if pending[child] == 0:
                frontier.append(child)
    cyclic = sorted(child_id for child_id, count in pending.items() if count > 0)
    if cyclic:
        raise ContractError(f"lineage contains illegal cycle involving: {cyclic}")


def exclude(source_id: str, nodes: list[dict], *, lineage_snapshot_hash: str) -> dict:
    if not source_id or not lineage_snapshot_hash:
        raise ContractError("source_id and immutable lineage snapshot hash are required")
    _validate_lineage_nodes(nodes)
    by_id = {node["sample_id"]: node for node in nodes}
    if len(by_id) != len(nodes):
        raise ContractError("lineage contains duplicate sample IDs")
    children: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        for parent in node.get("derived_from", []):
            if parent not in by_id:
                raise ContractError(f"dangling lineage edge: {node['sample_id']} -> {parent}")
            children[parent].add(node["sample_id"])
    _reject_illegal_cycles(nodes)
    roots = {node["sample_id"] for node in nodes if node["sample_id"] == source_id or source_id in node.get("source_ids", [])}
    queue = deque(sorted(roots))
    excluded = set(roots)
    while queue:
        for child in sorted(children[queue.popleft()]):
            if child not in excluded:
                excluded.add(child)
                queue.append(child)
    remaining = [node for node in nodes if node["sample_id"] not in excluded]
    if any(excluded.intersection(node.get("derived_from", [])) for node in remaining):
        raise ContractError("rebuild manifest would contain residual excluded ancestry")
    body = {
        "lineage_snapshot_hash": lineage_snapshot_hash,
        "excluded_source": source_id,
        "excluded_sample_ids": sorted(excluded),
        "remaining_sample_ids": sorted(node["sample_id"] for node in remaining),
        "remaining_shard_hashes": sorted({node["shard_hash"] for node in remaining}),
    }
    return {**body, "manifest_hash": sha256_value(body)}


def e7_acceptance() -> dict:
    nodes = [
        {"sample_id": "x-root", "source_ids": ["TEST_CLIENT_X"], "derived_from": [], "shard_hash": "sx1"},
        {"sample_id": "x-child", "source_ids": [], "derived_from": ["x-root"], "shard_hash": "sx2"},
        {"sample_id": "x-grandchild", "source_ids": [], "derived_from": ["x-child"], "shard_hash": "sx3"},
        {"sample_id": "y-root", "source_ids": ["TEST_CLIENT_Y"], "derived_from": [], "shard_hash": "sy1"},
        {"sample_id": "y-child", "source_ids": [], "derived_from": ["y-root"], "shard_hash": "sy2"},
    ]
    first = exclude("TEST_CLIENT_X", nodes, lineage_snapshot_hash=sha256_value(nodes))
    second = exclude("TEST_CLIENT_X", nodes, lineage_snapshot_hash=sha256_value(nodes))
    assertions = {
        "x_direct_removed": "x-root" in first["excluded_sample_ids"],
        "x_descendants_removed": {"x-child", "x-grandchild"}.issubset(first["excluded_sample_ids"]),
        "excluded_hashes_absent": not {"sx1", "sx2", "sx3"}.intersection(first["remaining_shard_hashes"]),
        "y_retained": {"y-root", "y-child"}.issubset(first["remaining_sample_ids"]),
        "idempotent": first == second,
    }
    return {"passed": all(assertions.values()), "assertions": assertions, "manifest": first}
