"""Append-only, hash-chained node event log (Plan section 7-P2; invariant 12).

One JSONL file; every row carries a contiguous monotonic `seq` and a sha256 chained over
the previous row's hash — order and in-file integrity are machine-verifiable after the
fact (`verify_file`). Known limit (recorded, spec-audit F8): verify_file cannot detect
TAIL TRUNCATION (a chain cut clean at a row boundary stays valid); cross-checks like the
soak's spawn/exit pairing are the compensating control until an external head anchor
exists. There is no update or delete API by construction. Appends are serialized under a
lock and fsynced before returning, so an acknowledged event survives a crash.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _row_hash(prev_hash: str, row_without_hash: dict[str, Any]) -> str:
    canonical = json.dumps(row_without_hash, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    rows: int
    problems: list[str]


class AppendOnlyEventLog:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._seq = 0
        self._prev_hash = GENESIS
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            result = verify_file(self._path)
            if not result.ok:
                raise ValueError(f"refusing to append to a corrupt event log: {result.problems}")
            self._seq = result.rows
            if result.rows:
                with self._path.open("r", encoding="utf-8") as fh:
                    last = None
                    for line in fh:
                        if line.strip():
                            last = line
                    assert last is not None
                    self._prev_hash = json.loads(last)["hash"]
        self._fh = self._path.open("a", encoding="utf-8", newline="\n")

    @property
    def path(self) -> Path:
        return self._path

    def append(self, kind: str, node_id: str | None = None, incarnation: int | None = None, **data: Any) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            row: dict[str, Any] = {
                "seq": self._seq,
                "ts": time.time(),
                "kind": kind,
                "node_id": node_id,
                "incarnation": incarnation,
                "data": data,
                "prev_hash": self._prev_hash,
            }
            row["hash"] = _row_hash(self._prev_hash, {k: v for k, v in row.items() if k != "prev_hash"})
            self._fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())
            self._prev_hash = row["hash"]
            return row

    def close(self) -> None:
        with self._lock:
            self._fh.close()


def verify_file(path: Path) -> VerifyResult:
    """Independent completeness + order check: contiguous seq, intact hash chain."""
    problems: list[str] = []
    prev_hash = GENESIS
    expected_seq = 0
    rows = 0
    with Path(path).open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            rows += 1
            expected_seq += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"line {lineno}: unparseable ({exc})")
                break
            if row.get("seq") != expected_seq:
                problems.append(f"line {lineno}: seq {row.get('seq')} != expected {expected_seq}")
            if row.get("prev_hash") != prev_hash:
                problems.append(f"line {lineno}: chain break (prev_hash mismatch)")
            recomputed = _row_hash(prev_hash, {k: v for k, v in row.items() if k not in ("prev_hash", "hash")})
            if row.get("hash") != recomputed:
                problems.append(f"line {lineno}: hash mismatch (row tampered)")
            prev_hash = row.get("hash", prev_hash)
    return VerifyResult(ok=not problems, rows=rows, problems=problems)
