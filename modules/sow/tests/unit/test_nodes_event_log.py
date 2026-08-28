"""Phase 2: append-only hash-chained event log (invariant 12; order + completeness)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.nodes import AppendOnlyEventLog, verify_file


def test_appends_are_contiguous_and_verifiable(tmp_path: Path) -> None:
    log = AppendOnlyEventLog(tmp_path / "events.jsonl")
    for i in range(50):
        log.append("transition", node_id="n1", incarnation=1, frm="READY", to="ASSIGNED", i=i)
    log.close()
    result = verify_file(tmp_path / "events.jsonl")
    assert result.ok, result.problems
    assert result.rows == 50


def test_tampered_row_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = AppendOnlyEventLog(path)
    for i in range(5):
        log.append("spawn", node_id=f"n{i}", incarnation=1)
    log.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[2])
    row["node_id"] = "attacker"
    lines[2] = json.dumps(row, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_file(path)
    assert not result.ok
    assert any("hash mismatch" in p for p in result.problems)


def test_deleted_row_breaks_the_chain(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = AppendOnlyEventLog(path)
    for i in range(5):
        log.append("spawn", node_id=f"n{i}", incarnation=1)
    log.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_file(path)
    assert not result.ok


def test_reopen_continues_seq_and_chain(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = AppendOnlyEventLog(path)
    log.append("spawn", node_id="n1", incarnation=1)
    log.close()
    log2 = AppendOnlyEventLog(path)
    row = log2.append("exit", node_id="n1", incarnation=1, exit_code=0, expected=True)
    log2.close()
    assert row["seq"] == 2
    assert verify_file(path).ok


def test_reopen_refuses_corrupt_log(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = AppendOnlyEventLog(path)
    log.append("spawn", node_id="n1", incarnation=1)
    log.close()
    content = path.read_text(encoding="utf-8").replace('"n1"', '"nX"')
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="corrupt"):
        AppendOnlyEventLog(path)


def test_no_update_or_delete_api() -> None:
    assert not hasattr(AppendOnlyEventLog, "update")
    assert not hasattr(AppendOnlyEventLog, "delete")
    assert not hasattr(AppendOnlyEventLog, "rewrite")
