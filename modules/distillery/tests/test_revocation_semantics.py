from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curation import seal_shard
from distillery.common import ContractError
from exclusion import exclude, sha256_value
from source_admission import (
    AdmissionClass,
    AdmissionEvent,
    AdmissionRegistry,
    SourceKey,
    assert_admitted,
    assert_seed_admitted,
    assert_snapshot_matches_registry,
    lineage_id,
)

ROOT = Path(__file__).resolve().parents[1]


def make_registry() -> tuple[AdmissionRegistry, SourceKey]:
    registry = AdmissionRegistry()
    key = SourceKey("provider.example", "teacher-a", "rev-1")
    registry.transition(key, AdmissionClass.ELIGIBLE, evidence_ref="terms-v1", decision_authority="operator")
    return registry, key


def lineage_nodes(source_lineage_id: str) -> list[dict]:
    root = {"sample_id": "root", "source_ids": [source_lineage_id], "derived_from": [], "shard_hash": "s0"}
    child = {"sample_id": "child", "source_ids": [], "derived_from": ["root"], "shard_hash": "s1"}
    grandchild = {"sample_id": "grandchild", "source_ids": [], "derived_from": ["child"], "shard_hash": "s2"}
    unrelated = {"sample_id": "other-root", "source_ids": ["OTHER"], "derived_from": [], "shard_hash": "t0"}
    other_child = {"sample_id": "other-child", "source_ids": [], "derived_from": ["other-root"], "shard_hash": "t1"}
    return [root, child, grandchild, unrelated, other_child]


class RevocationSemanticsTests(unittest.TestCase):
    def test_revoke_requires_admitted_source(self) -> None:
        registry = AdmissionRegistry()
        unknown_key = SourceKey("p", "m", "r0")
        with self.assertRaises(ContractError):
            registry.revoke(unknown_key, evidence_ref="e", decision_authority="op")

    def test_rejected_source_cannot_be_revoked_again_or_readmitted(self) -> None:
        registry, key = make_registry()
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        with self.assertRaises(ContractError):
            registry.revoke(key, evidence_ref="again", decision_authority="op")
        with self.assertRaises(ContractError):
            registry.transition(key, AdmissionClass.ELIGIBLE, evidence_ref="old-eligibility-evidence", decision_authority="op")

    def test_training_and_seeding_admission_fail_after_revocation(self) -> None:
        registry, key = make_registry()
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        use_class = registry.current(key).value
        self.assertEqual(use_class, "REJECTED")
        with self.assertRaises(ContractError):
            assert_admitted(use_class)
        with self.assertRaises(ContractError):
            assert_seed_admitted(use_class)

    def test_stale_pre_revocation_snapshot_cannot_admit_future_shards(self) -> None:
        registry, key = make_registry()
        stale = registry.snapshot("run-stale")
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        with self.assertRaises(ContractError):
            assert_snapshot_matches_registry(stale, registry)

    def test_current_snapshot_matches_and_carries_revocation(self) -> None:
        registry, key = make_registry()
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        fresh = registry.snapshot("run-fresh")
        assert_snapshot_matches_registry(fresh, registry)
        self.assertEqual(fresh["revoked_source_ids"], [lineage_id(key)])
        self.assertEqual(
            [row["use_class"] for row in fresh["sources"] if row["provider"] == key.provider],
            ["REJECTED"],
        )

    def test_snapshot_events_record_revocation_reason(self) -> None:
        registry, key = make_registry()
        event = registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        self.assertEqual(event.reason, "revoked")
        snapshot = registry.snapshot("run-events")
        self.assertTrue(any(row.get("reason") == "revoked" for row in snapshot["events"]))

    def test_exclusion_identifies_revoked_descendants(self) -> None:
        registry, key = make_registry()
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        nodes = lineage_nodes(lineage_id(key))
        manifest = exclude(lineage_id(key), nodes, lineage_snapshot_hash=sha256_value(nodes))
        self.assertIn("root", manifest["excluded_sample_ids"])
        self.assertIn("child", manifest["excluded_sample_ids"])
        self.assertIn("grandchild", manifest["excluded_sample_ids"])
        self.assertIn("other-root", manifest["remaining_sample_ids"])

    def test_stale_snapshot_sealing_mechanics_and_freshness_gate(self) -> None:
        """Seal trusts the snapshot blob it is handed; revocation enforcement is the
        mandatory caller-side freshness gate, which fails closed on stale state."""
        registry, key = make_registry()
        stale = registry.snapshot("run-before-revocation")
        sample = {
            "sample_id": "sample-1",
            "source_trace_id": "trace-1",
            "content": "payload",
            "content_hash": sha256_value("payload"),
            "channel": "CH1",
            "harness": "h",
            "provider": key.provider,
            "teacher_of_record": key.teacher_or_model_id,
            "source_revision": key.revision,
            "source_admission_class": "ELIGIBLE",
            "generation_depth": 0,
            "seed_trace_ids": [],
            "seed_ref": None,
            "derived_from": [],
            "validator_results": {},
            "labels": {},
            "client_tag": "CLIENT_A",
            "trace_fit_version": "1",
            "normalizer_version": "1",
            "created_at": "2026-01-01T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest = seal_shard([sample], directory, stale)
            self.assertEqual(manifest["source_admission_snapshot_hash"], stale["snapshot_hash"])
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        with self.assertRaises(ContractError):
            assert_snapshot_matches_registry(stale, registry)
        assert_snapshot_matches_registry(registry.snapshot("run-current"), registry)

    def test_revocation_survives_persistence_reload(self) -> None:
        registry, key = make_registry()
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        snapshot = registry.snapshot("run-persisted")
        reloaded = AdmissionRegistry(AdmissionEvent(**row) for row in snapshot["events"])
        self.assertEqual(reloaded.current(key), AdmissionClass.REJECTED)
        self.assertEqual(reloaded.revoked_keys(), (key,))
        with self.assertRaises(ContractError):
            reloaded.transition(key, AdmissionClass.ELIGIBLE, evidence_ref="old-eligibility-evidence", decision_authority="operator")
        assert_snapshot_matches_registry(snapshot, reloaded)


if __name__ == "__main__":
    unittest.main()
