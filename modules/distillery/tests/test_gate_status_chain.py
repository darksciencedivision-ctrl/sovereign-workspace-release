from __future__ import annotations

import json
import random
import unittest
from pathlib import Path

from distillery.common import ContractError
from gate.status_chain import content_sha256, parse_gate_status_file, parse_gate_status_record, resolve_current

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "runs/HG-3/CURRENT_STATUS.json"
SUPERSEDED_PATHS = ("runs/HG-3/summary.json", "runs/HG-3/manifest.json")
EFFECTIVE_STATUS = "BLOCKED_HARDWARE_CAPACITY"


def repo_records() -> tuple[list[dict], dict[str, bytes], set[str]]:
    current_raw = json.loads(CURRENT.read_text(encoding="utf-8"))
    current = parse_gate_status_file(CURRENT)
    records = [current]
    contents: dict[str, bytes] = {}
    locator_to_record: dict[str, str] = {}
    for edge in current["supersedes"]:
        path = ROOT / edge["path"]
        record_id = edge["record_id"]
        raw = path.read_text(encoding="utf-8")
        document = json.loads(raw)
        if record_id.endswith("#hard_gates.HG-3"):
            status = document["hard_gates"]["HG-3"]
            recorded_at = document.get("validated_at") or "2026-01-01T00:00:00Z"
        else:
            status = document["status"]
            recorded_at = "2026-01-01T00:00:00Z"
        records.append(
            parse_gate_status_record(
                {
                    "record_id": record_id,
                    "gate": "HG-3",
                    "status": status,
                    "recorded_at": recorded_at,
                    "supersedes": [],
                }
            )
        )
        contents[record_id] = raw.encode("utf-8")
        locator_to_record[record_id] = record_id
    return records, contents, {current["record_id"]}


class GateStatusChainTests(unittest.TestCase):
    def test_repo_records_resolve_to_hardware_capacity_regardless_of_order(self) -> None:
        records, contents, trusted = repo_records()
        for seed in range(6):
            with self.subTest(seed=seed):
                shuffled = list(records)
                random.Random(seed).shuffle(shuffled)
                resolved = resolve_current(shuffled, contents=contents, trusted_record_ids=trusted)
                self.assertEqual(resolved["gates"]["HG-3"]["status"], EFFECTIVE_STATUS)
                self.assertEqual(resolved["gates"]["HG-3"]["record_id"], "HG3-CURRENT-STATUS-001")

    def test_resolution_does_not_depend_on_timestamps(self) -> None:
        records, _, _ = repo_records()
        aged_current = [dict(record, recorded_at="2020-01-01T00:00:00Z") if record["record_id"] == "HG3-CURRENT-STATUS-001" else record for record in records]
        resolved = resolve_current(aged_current)
        self.assertEqual(resolved["gates"]["HG-3"]["status"], EFFECTIVE_STATUS)

    def test_removing_current_record_fails_closed(self) -> None:
        records, contents, _ = repo_records()
        trimmed = [record for record in records if record["record_id"] != "HG3-CURRENT-STATUS-001"]
        with self.assertRaises(ContractError):
            resolve_current(trimmed, contents=contents)

    def test_all_superseded_fails_closed(self) -> None:
        base = [
            {"record_id": "a", "gate": "HG-3", "status": "X", "recorded_at": "2026-01-01T00:00:00Z",
             "supersedes": [{"record_id": "b", "record_sha256": "0" * 64}]},
            {"record_id": "b", "gate": "HG-3", "status": "Y", "recorded_at": "2026-01-01T00:00:00Z", "supersedes": []},
            {"record_id": "c", "gate": "HG-3", "status": "Z", "recorded_at": "2026-01-01T00:00:00Z", "supersedes": []},
            {"record_id": "d", "gate": "HG-9", "status": "W", "recorded_at": "2026-01-01T00:00:00Z",
             "supersedes": [{"record_id": "e", "record_sha256": "1" * 64}]},
            {"record_id": "e", "gate": "HG-9", "status": "V", "recorded_at": "2026-01-01T00:00:00Z", "supersedes": []},
        ]
        with self.assertRaises(ContractError):
            resolve_current(base)

    def test_dangling_supersedes_edge_fails(self) -> None:
        record = {
            "record_id": "solo", "gate": "HG-3", "status": "S", "recorded_at": "2026-01-01T00:00:00Z",
            "supersedes": [{"record_id": "ghost", "record_sha256": "a" * 64}],
        }
        with self.assertRaises(ContractError):
            resolve_current([record])

    def test_cycle_fails(self) -> None:
        records = [
            {"record_id": "a", "gate": "HG-3", "status": "X", "recorded_at": "2026-01-01T00:00:00Z",
             "supersedes": [{"record_id": "b", "record_sha256": "0" * 64}]},
            {"record_id": "b", "gate": "HG-3", "status": "Y", "recorded_at": "2026-01-01T00:00:00Z",
             "supersedes": [{"record_id": "c", "record_sha256": "0" * 64}]},
            {"record_id": "c", "gate": "HG-3", "status": "Z", "recorded_at": "2026-01-01T00:00:00Z",
             "supersedes": [{"record_id": "a", "record_sha256": "0" * 64}]},
        ]
        with self.assertRaises(ContractError):
            resolve_current(records)

    def test_tampered_superseded_content_fails(self) -> None:
        records, contents, trusted = repo_records()
        tampered = dict(contents)
        victim = "runs/HG-3/summary.json#hard_gates.HG-3"
        tampered[victim] = tampered[victim].replace(b"BLOCKED_PRELOAD", b"BLOCKED_PRELOAD ") + b"\n"
        with self.assertRaises(ContractError):
            resolve_current(records, contents=tampered, trusted_record_ids=trusted)

    def test_duplicate_record_ids_fail(self) -> None:
        records, contents, _ = repo_records()
        clone = dict(records[0])
        with self.assertRaises(ContractError):
            resolve_current(records + [clone], contents=contents)

    def test_malformed_timestamps_fail(self) -> None:
        for bad in (None, "", "not-a-time", "2026-01-01T00:00:00"):
            with self.subTest(bad=bad):
                with self.assertRaises(ContractError):
                    parse_gate_status_record(
                        {"record_id": "r", "gate": "HG-3", "status": "S", "recorded_at": bad, "supersedes": []}
                    )

    def test_missing_required_fields_fail(self) -> None:
        with self.assertRaises(ContractError):
            parse_gate_status_record({"record_id": "r", "gate": "HG-3"})

    def test_forged_effective_record_outside_trust_anchors_fails(self) -> None:
        records, contents, trusted = repo_records()
        forged = parse_gate_status_record(
            {
                "record_id": "forged-current",
                "gate": "HG-3",
                "status": "PASS_MEASURED",
                "recorded_at": "2026-08-23T00:00:00Z",
                "decision_authority": "attacker",
                "supersedes": [
                    {"record_id": "HG3-CURRENT-STATUS-001", "record_sha256": content_sha256(CURRENT.read_bytes())}
                ],
            }
        )
        with self.assertRaises(ContractError):
            resolve_current(records + [forged], contents=contents, trusted_record_ids=trusted)

    def test_trust_anchor_set_restores_legitimate_replacement_path(self) -> None:
        records, contents, _ = repo_records()
        successor = parse_gate_status_record(
            {
                "record_id": "HG3-CURRENT-STATUS-002",
                "gate": "HG-3",
                "status": "MEASURED_LADDER_COMPLETE",
                "recorded_at": "2027-01-01T00:00:00Z",
                "decision_authority": "future accepted authority",
                "supersedes": [
                    {"record_id": "HG3-CURRENT-STATUS-001", "record_sha256": content_sha256(CURRENT.read_bytes())}
                ],
            }
        )
        expanded_trust = {"HG3-CURRENT-STATUS-001", "HG3-CURRENT-STATUS-002"}
        resolved = resolve_current(records + [successor], contents={**contents, "HG3-CURRENT-STATUS-001": CURRENT.read_bytes()}, trusted_record_ids=expanded_trust)
        self.assertEqual(resolved["gates"]["HG-3"]["status"], "MEASURED_LADDER_COMPLETE")

    def test_schema_validates_canonical_record(self) -> None:
        from validators import structured_output

        result = structured_output(CURRENT.read_text(encoding="utf-8"), json.loads((ROOT / "schema/gate_status_record.json").read_text(encoding="utf-8")))
        self.assertTrue(result.passed, result.failures)


if __name__ == "__main__":
    unittest.main()