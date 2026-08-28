from __future__ import annotations

from pathlib import Path

from distillery.common import ContractError, sha256_value, write_new_json
from source_admission import assert_admitted


REQUIRED_SAMPLE_FIELDS = {
    "sample_id", "source_trace_id", "content", "content_hash", "channel", "harness", "provider",
    "teacher_of_record", "source_revision", "source_admission_class", "generation_depth",
    "seed_trace_ids", "seed_ref", "derived_from", "validator_results", "labels", "client_tag",
    "trace_fit_version", "normalizer_version", "created_at",
}


def seal_shard(samples: list[dict], output_dir: str | Path, admission_snapshot: dict, *, internal_use_authorized: bool = False) -> dict:
    if not samples:
        raise ContractError("cannot seal an empty shard")
    snapshot_index = {
        (row["provider"], row["teacher_or_model_id"], row["revision"]): row["use_class"]
        for row in admission_snapshot.get("sources", [])
    }
    clients: set[str] = set()
    sample_ids: set[str] = set()
    for sample in samples:
        missing = REQUIRED_SAMPLE_FIELDS - sample.keys()
        if missing:
            raise ContractError(f"sample missing fields: {sorted(missing)}")
        if sample["sample_id"] in sample_ids:
            raise ContractError(f"duplicate sample_id: {sample['sample_id']}")
        sample_ids.add(sample["sample_id"])
        clients.add(sample["client_tag"])
        if sample["content_hash"] != sha256_value(sample["content"]):
            raise ContractError(f"content hash mismatch for {sample['sample_id']}")
        key = (sample["provider"], sample["teacher_of_record"], sample["source_revision"])
        snap_class = snapshot_index.get(key, "UNKNOWN")
        if sample["source_admission_class"] != snap_class:
            raise ContractError(f"sample admission does not match immutable snapshot: {sample['sample_id']}")
        assert_admitted(snap_class, internal_use_authorized=internal_use_authorized)
        if not isinstance(sample["generation_depth"], int) or not 0 <= sample["generation_depth"] <= 2:
            raise ContractError("generation depth must be 0..2")
        if sample["channel"] == "CH2" and sample["generation_depth"] < 1:
            raise ContractError("CH2 must identify synthetic generation depth")
        if sample["channel"] == "CH-M" and sample.get("labels", {}).get("volatile"):
            raise ContractError("volatile facts cannot enter CH-M")
    if len(clients) != 1:
        raise ContractError("shards must be client-homogeneous")
    payload = sorted(samples, key=lambda item: item["sample_id"])
    body = {
        "schema_version": "1.1",
        "client_tag": next(iter(clients)),
        "sample_count": len(payload),
        "sample_ids": [item["sample_id"] for item in payload],
        "content_hashes": [item["content_hash"] for item in payload],
        "payload_hash": sha256_value(payload),
        "source_admission_snapshot_hash": admission_snapshot.get("snapshot_hash"),
    }
    manifest = {**body, "shard_hash": sha256_value(body)}
    destination = Path(output_dir) / manifest["shard_hash"]
    write_new_json(destination / "payload.json", payload)
    write_new_json(destination / "manifest.json", manifest)
    return manifest
