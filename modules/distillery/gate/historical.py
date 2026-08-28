from __future__ import annotations

import json
import math
from pathlib import Path

from distillery.common import ContractError, sha256_value, utc_now


REQUIRED = {"suite_version", "bundle_id", "n", "mean", "dispersion", "ci_metadata", "promotion_time"}


def _validate_item_results(row: dict) -> None:
    item_results = row.get("item_results")
    if item_results is None:
        return
    if not isinstance(item_results, dict) or not item_results:
        raise ContractError("item_results must be a non-empty object of item_id -> numeric value")
    for item_id, value in item_results.items():
        if not isinstance(item_id, str) or not item_id:
            raise ContractError("item_results keys must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ContractError(f"item_results[{item_id!r}] must be a finite number")


class HistoricalBestStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append_promotion_run(self, row: dict) -> None:
        missing = REQUIRED - row.keys()
        if missing or not row["promotion_time"] or row["n"] < 1:
            raise ContractError(f"invalid historical promotion row; missing={sorted(missing)}")
        _validate_item_results(row)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({**row, "recorded_at": utc_now()}, sort_keys=True, allow_nan=False) + "\n")

    def records(self, suite_version: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [row for row in rows if suite_version is None or row["suite_version"] == suite_version]

    def reference_vector(self, suite_version: str, item_ids: list[str]) -> dict:
        """Per-item historical reference vector drawn from ONE governed promotion run.

        Hard invariant (G2_WORK_ITEMS.md GR-9): the vector is never constructed as
        per-item maxima across checkpoints or runs; per-item maxima would synthesize
        a model that never existed. The governing bundle is selected exactly as in
        reference(); within it, the latest single promotion run that carries EVERY
        requested item supplies all values. Anything less fails closed.
        """
        if not suite_version:
            raise ContractError("suite_version is required")
        if not item_ids or any(not isinstance(item_id, str) or not item_id for item_id in item_ids) or len(set(item_ids)) != len(item_ids):
            raise ContractError("reference_vector requires unique non-empty string item_ids")
        grouped: dict[str, list[dict]] = {}
        for row in self.records(suite_version):
            grouped.setdefault(row["bundle_id"], []).append(row)
        aggregates = []
        for bundle_id in sorted(grouped):
            rows = grouped[bundle_id]
            if len(rows) < 2:
                continue
            total_n = sum(row["n"] for row in rows)
            aggregates.append({"bundle_id": bundle_id, "mean": sum(row["mean"] * row["n"] for row in rows) / total_n, "n": total_n})
        if not aggregates:
            raise ContractError("historical best requires at least two promotion-time runs for a bundle")
        governed = max(aggregates, key=lambda item: (item["mean"], item["n"]))
        supplier: dict | None = None
        for row in sorted(grouped[governed["bundle_id"]], key=lambda entry: (entry["promotion_time"], entry.get("recorded_at", ""))):
            item_results = row.get("item_results") or {}
            for item_id in item_ids:
                if item_id in item_results:
                    raw = item_results[item_id]
                    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
                        raise ContractError(f"stored promotion record carries invalid item result {item_id!r}")
            if all(item_id in item_results for item_id in item_ids):
                supplier = row
        if supplier is None:
            raise ContractError(
                f"governed bundle {governed['bundle_id']!r} has no single run covering items {sorted(item_ids)}; "
                "composite stitching across runs is forbidden"
            )
        values = [float(supplier["item_results"][item_id]) for item_id in item_ids]
        bindings = {
            item_id: {
                "value": float(supplier["item_results"][item_id]),
                "bundle_id": supplier["bundle_id"],
                "promotion_time": supplier["promotion_time"],
                "supply_rule": "SINGLE_GOVERNED_RUN_NO_COMPOSITE",
            }
            for item_id in item_ids
        }
        body = {"suite_version": suite_version, "governing_bundle": governed["bundle_id"], "supplier_promotion_time": supplier["promotion_time"], "item_ids": list(item_ids), "values": values, "bindings": bindings}
        return {**body, "reference_vector_hash": sha256_value(body)}


    def reference(self, suite_version: str) -> dict:
        grouped: dict[str, list[dict]] = {}
        for row in self.records(suite_version):
            grouped.setdefault(row["bundle_id"], []).append(row)
        aggregates = []
        for bundle_id, rows in grouped.items():
            if len(rows) < 2:
                continue
            total_n = sum(row["n"] for row in rows)
            aggregates.append({"bundle_id": bundle_id, "mean": sum(row["mean"] * row["n"] for row in rows) / total_n, "n": total_n, "promotion_run_count": len(rows), "max_single_run_ignored": max(row["mean"] for row in rows)})
        if not aggregates:
            raise ContractError("historical best requires at least two promotion-time runs for a bundle")
        return max(aggregates, key=lambda item: (item["mean"], item["n"]))
