from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from distillery.common import ContractError


REQUIRED_ROW_FIELDS = {"dataset_hashes", "source_admission_snapshot", "normalizer_version", "trace_fit_version", "training_config", "hardware", "peak_vram", "wall_clock", "card_window", "synthesis_tokens_per_day", "controlled_model_effect_results", "bundle_gate_results", "confidence_intervals", "promotion_decision"}


class ExperimentDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS experiments (run_id TEXT PRIMARY KEY, row_json TEXT NOT NULL)")

    def complete(self, run_id: str, row: dict) -> None:
        missing = REQUIRED_ROW_FIELDS - row.keys()
        null = [name for name in REQUIRED_ROW_FIELDS if row.get(name) is None]
        if missing or null:
            raise ContractError(f"training job cannot complete; missing={sorted(missing)}, null={sorted(null)}")
        try:
            with closing(sqlite3.connect(self.path)) as connection:
                with connection:
                    connection.execute("INSERT INTO experiments(run_id, row_json) VALUES (?, ?)", (run_id, json.dumps(row, sort_keys=True, allow_nan=False)))
        except sqlite3.IntegrityError as exc:
            raise ContractError("experiment completion row is immutable") from exc

    def get(self, run_id: str) -> dict:
        with closing(sqlite3.connect(self.path)) as connection:
            record = connection.execute("SELECT row_json FROM experiments WHERE run_id = ?", (run_id,)).fetchone()
        if record is None:
            raise ContractError(f"unknown experiment: {run_id}")
        return json.loads(record[0])
