from __future__ import annotations

import random
import unittest

from distillery.common import ContractError
from exclusion import exclude


def node(sample_id: str, parents: list[str] | None = None, sources: list[str] | None = None) -> dict:
    return {"sample_id": sample_id, "derived_from": parents or [], "shard_hash": "h-" + sample_id, "source_ids": sources or []}


class MalformedLineageTests(unittest.TestCase):
    def test_non_dict_node_fails_closed(self) -> None:
        with self.assertRaises(ContractError):
            exclude("src", ["not-a-node"], lineage_snapshot_hash="s")

    def test_missing_or_empty_sample_id_fails_closed(self) -> None:
        with self.assertRaises(ContractError):
            exclude("src", [{"shard_hash": "h"}], lineage_snapshot_hash="s")
        with self.assertRaises(ContractError):
            exclude("src", [node("")], lineage_snapshot_hash="s")

    def test_malformed_derived_from_fails_closed(self) -> None:
        bad = node("a")
        bad["derived_from"] = "b"
        with self.assertRaises(ContractError):
            exclude("src", [bad], lineage_snapshot_hash="s")
        bad2 = node("a")
        bad2["derived_from"] = [7]
        with self.assertRaises(ContractError):
            exclude("src", [bad2], lineage_snapshot_hash="s")

    def test_missing_shard_hash_fails_closed(self) -> None:
        incomplete = {"sample_id": "a", "derived_from": []}
        with self.assertRaises(ContractError):
            exclude("src", [incomplete], lineage_snapshot_hash="s")


class CyclePolicyTests(unittest.TestCase):
    def test_self_loop_rejected(self) -> None:
        nodes = [node("a", ["a"], ["src"]), node("b")]
        with self.assertRaises(ContractError):
            exclude("src", nodes, lineage_snapshot_hash="s")

    def test_two_node_cycle_rejected(self) -> None:
        nodes = [node("a", ["b"], ["src"]), node("b", ["a"])]
        with self.assertRaises(ContractError):
            exclude("src", nodes, lineage_snapshot_hash="s")

    def test_cycle_disconnected_from_source_still_rejected(self) -> None:
        clean = [node("root", [], ["src"]), node("leaf", ["root"])]
        cyclic = [node("x", ["y"]), node("y", ["x"])]
        with self.assertRaises(ContractError):
            exclude("src", clean + cyclic, lineage_snapshot_hash="s")

    def test_cycle_upstream_of_excluded_root_rejected(self) -> None:
        nodes = [node("m1", ["m2"]), node("m2", ["m1"]), node("root", ["m1"], ["src"])]
        with self.assertRaises(ContractError):
            exclude("src", nodes, lineage_snapshot_hash="s")

    def test_diamond_dag_is_legal(self) -> None:
        nodes = [node("top"), node("l", ["top"]), node("r", ["top"]), node("bottom", ["l", "r"], ["src"])]
        manifest = exclude("src", nodes, lineage_snapshot_hash="s")
        self.assertEqual(set(manifest["excluded_sample_ids"]), {"bottom"})
        self.assertEqual(set(manifest["remaining_sample_ids"]), {"top", "l", "r"})


class SeededPurgePropertyTests(unittest.TestCase):
    def test_random_forests_satisfy_purge_invariants(self) -> None:
        for seed in range(50):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                size = rng.randint(3, 24)
                nodes = [node(f"n{index}") for index in range(size)]
                for index in range(1, size):
                    count = min(index, rng.randint(0, 3))
                    nodes[index]["derived_from"] = sorted(f"n{p}" for p in rng.sample(range(index), count))
                source_bearers = rng.sample(nodes, rng.randint(1, max(1, size // 4)))
                for bearer in source_bearers:
                    bearer["source_ids"] = ["SOURCE_X"]
                snapshot = str(sorted(n["sample_id"] for n in nodes))
                first = exclude("SOURCE_X", nodes, lineage_snapshot_hash=snapshot)
                second = exclude("SOURCE_X", nodes, lineage_snapshot_hash=snapshot)
                excluded = set(first["excluded_sample_ids"])
                remaining = set(first["remaining_sample_ids"])
                all_ids = {n["sample_id"] for n in nodes}
                self.assertEqual(first, second)
                self.assertEqual(excluded | remaining, all_ids)
                self.assertFalse(excluded & remaining)
                children: dict[str, list[str]] = {n["sample_id"]: [] for n in nodes}
                for n in nodes:
                    for parent in n["derived_from"]:
                        children[parent].append(n["sample_id"])
                tainted = [n for n in nodes if "SOURCE_X" in n["source_ids"]]
                frontier = [t["sample_id"] for t in tainted]
                closure = set()
                while frontier:
                    current = frontier.pop()
                    if current in closure:
                        continue
                    closure.add(current)
                    frontier.extend(children[current])
                self.assertEqual(closure, excluded)
                self.assertEqual(first["manifest_hash"], second["manifest_hash"])

    def test_single_node_mutation_changes_manifest_hash(self) -> None:
        nodes_a = [node("r", [], ["src"]), node("c", ["r"])]
        nodes_b = [node("r", [], ["src"]), node("c", [])]
        ma = exclude("src", nodes_a, lineage_snapshot_hash="s")
        mb = exclude("src", nodes_b, lineage_snapshot_hash="s")
        self.assertNotEqual(ma["manifest_hash"], mb["manifest_hash"])


if __name__ == "__main__":
    unittest.main()
