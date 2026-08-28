from __future__ import annotations

import unittest

from corpus import (
    REQUIRED_SCAN_CATEGORIES,
    SCRUB_POLICY_VERSION,
    admit_example,
    redact_text,
    scan_text,
    verify_corpus_admission_record,
)
from distillery.common import ContractError, sha256_value
from exclusion import exclude
from source_admission import (
    AdmissionClass,
    AdmissionRegistry,
    SourceKey,
    lineage_id,
)

SYNTHETIC_API_KEY = "sk-synthetic000000000000000000"
SYNTHETIC_PASSWORD = "password=hunter2sensitive"
SYNTHETIC_EMAIL = "person@example.internal"
SYNTHETIC_HOSTNAME = "build-agent.example.corp"
SYNTHETIC_PATH = "C:\\Users\\synthetic\\notes"


def make_registry_and_snapshot(revoked: bool = False):
    registry = AdmissionRegistry()
    key = SourceKey("provider.example", "teacher-a", "rev-1")
    registry.transition(key, AdmissionClass.ELIGIBLE, evidence_ref="terms-v1", decision_authority="operator")
    if revoked:
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
    return registry, key, registry.snapshot("run-corpus")


def raw_content() -> str:
    return (
        "Recovery procedure: rotate the key sk-synthetic000000000000000000, "
        "email person@example.internal on build-agent.example.corp, "
        "logs under C:\\Users\\synthetic\\notes, password=hunter2sensitive."
    )


def example(content: str | None = None) -> dict:
    payload = content if content is not None else raw_content()
    return {
        "sample_id": "example-1",
        "content": payload,
        "channel": "CH1",
        "provider": "provider.example",
        "teacher_of_record": "teacher-a",
        "source_revision": "rev-1",
        "client_tag": "CLIENT_A",
        "created_at": "2026-08-23T00:00:00Z",
    }


class CorpusAdmissionTests(unittest.TestCase):
    def test_positive_admission_redacts_all_categories(self) -> None:
        registry, key, snapshot = make_registry_and_snapshot()
        record = admit_example(example(), snapshot, client_scope="CLIENT_A", admission_registry=registry)
        self.assertEqual(record["scrub_policy_version"], SCRUB_POLICY_VERSION)
        categories = {finding["category"] for finding in record["scan_findings"]}
        self.assertEqual(categories, set(REQUIRED_SCAN_CATEGORIES))
        self.assertEqual(record["redactions_applied"], len(record["scan_findings"]))
        verify_corpus_admission_record(record)
        self.assertIn(lineage_id(key), record["deletion_lineage_ids"])
        self.assertIn("CLIENT:CLIENT_A", record["deletion_lineage_ids"])
        self.assertEqual(record["retention"], "DURABLE_PROCEDURE")
        self.assertFalse(record["retrieval_only"])

    def test_clean_durable_procedure_admits_with_zero_findings(self) -> None:
        registry, _key, snapshot = make_registry_and_snapshot()
        clean = example("Always re-run the failing test before declaring the fix done.")
        clean["content_hash"] = sha256_value(clean["content"])
        record = admit_example(clean, snapshot, client_scope="CLIENT_A", admission_registry=registry)
        self.assertEqual(record["scan_findings"], [])
        self.assertEqual(record["redactions_applied"], 0)
        verify_corpus_admission_record(record)

    def test_mutable_environment_fact_is_retrieval_only_ephemeral(self) -> None:
        registry, _key, snapshot = make_registry_and_snapshot()
        volatile = example("The staging gateway build-agent.example.corp is currently green.")
        record = admit_example(
            volatile, snapshot, client_scope="CLIENT_A", admission_registry=registry, mutable_environment_fact=True
        )
        self.assertTrue(record["retrieval_only"])
        self.assertEqual(record["retention"], "EPHEMERAL_TRACE")

    def test_unknown_source_fails_closed(self) -> None:
        _registry, _key, snapshot = make_registry_and_snapshot()
        stranger = example()
        stranger.update({"provider": "other", "teacher_of_record": "x", "source_revision": "r"})
        with self.assertRaises(ContractError):
            admit_example(stranger, snapshot, client_scope="CLIENT_A", admission_registry=_registry)

    def test_revoked_source_and_stale_eligibility_evidence_fail(self) -> None:
        registry, key, _stale = make_registry_and_snapshot()
        stale_snapshot = registry.snapshot("pre-revocation")
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        fresh_snapshot = registry.snapshot("post-revocation")
        with self.assertRaises(ContractError):
            admit_example(example(), stale_snapshot, client_scope="CLIENT_A", admission_registry=registry)
        with self.assertRaises(ContractError):
            admit_example(example(), fresh_snapshot, client_scope="CLIENT_A", admission_registry=registry)

    def test_stale_snapshot_rejected_when_registry_supplied(self) -> None:
        registry, key, snapshot = make_registry_and_snapshot()
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        with self.assertRaises(ContractError):
            admit_example(example(), snapshot, client_scope="CLIENT_A", admission_registry=registry)

    def test_forged_snapshot_body_fails_integrity(self) -> None:
        _registry, _key, snapshot = make_registry_and_snapshot()
        forged = {**snapshot, "sources": [], "snapshot_hash": "forged"}
        with self.assertRaises(ContractError):
            admit_example(example(), forged, client_scope="CLIENT_A", admission_registry=_registry)

    def test_tampered_persisted_record_fails_validation(self) -> None:
        registry, _key, snapshot = make_registry_and_snapshot()
        record = admit_example(example(), snapshot, client_scope="CLIENT_A", admission_registry=registry)
        tampered = {**record, "redactions_applied": 0}
        with self.assertRaises(ContractError):
            verify_corpus_admission_record(tampered)
        stripped = {key: value for key, value in record.items() if key != "scan_findings"}
        with self.assertRaises(ContractError):
            verify_corpus_admission_record(stripped)

    def test_client_scope_violation_and_bad_input_hash_fail(self) -> None:
        registry, _key, snapshot = make_registry_and_snapshot()
        outsider = example()
        outsider["client_tag"] = "CLIENT_B"
        with self.assertRaises(ContractError):
            admit_example(outsider, snapshot, client_scope="CLIENT_A", admission_registry=registry)
        bad_hash = example()
        bad_hash["content_hash"] = "0" * 64
        with self.assertRaises(ContractError):
            admit_example(bad_hash, snapshot, client_scope="CLIENT_A", admission_registry=registry)

    def test_non_string_content_and_unknown_scan_category_fail(self) -> None:
        registry, _key, snapshot = make_registry_and_snapshot()
        with self.assertRaises(ContractError):
            admit_example({"sample_id": "x", "content": 42}, snapshot, client_scope="CLIENT_A", admission_registry=registry)
        with self.assertRaises(ContractError):
            scan_text("text", categories=("NOT_A_CATEGORY",))

    def test_redaction_placeholder_hides_secret_but_binds_hash(self) -> None:
        redacted, findings = redact_text(raw_content())
        self.assertNotIn(SYNTHETIC_API_KEY, redacted)
        self.assertNotIn("hunter2sensitive", redacted)
        self.assertNotIn(SYNTHETIC_EMAIL, redacted)
        self.assertNotIn(SYNTHETIC_HOSTNAME.lower(), redacted.lower())
        self.assertNotIn("synthetic\\notes", redacted)
        self.assertGreaterEqual(len(findings), 5)
        self.assertEqual(scan_text(redacted, categories=("API_KEY", "CREDENTIAL")), [])

    def test_deletion_lineage_connects_to_exclusion_purge(self) -> None:
        registry, key, snapshot = make_registry_and_snapshot()
        record = admit_example(example(), snapshot, client_scope="CLIENT_A", admission_registry=registry)
        nodes = [
            {"sample_id": record["example_id"], "source_ids": list(record["deletion_lineage_ids"][:1]), "derived_from": [], "shard_hash": "sx"},
        ]
        manifest = exclude(lineage_id(key), nodes, lineage_snapshot_hash=sha256_value(nodes))
        self.assertIn(record["example_id"], manifest["excluded_sample_ids"])

    def test_missing_provenance_fields_fail(self) -> None:
        registry, _key, snapshot = make_registry_and_snapshot()
        incomplete = example()
        del incomplete["teacher_of_record"]
        with self.assertRaises(ContractError):
            admit_example(incomplete, snapshot, client_scope="CLIENT_A", admission_registry=registry)


if __name__ == "__main__":
    unittest.main()
