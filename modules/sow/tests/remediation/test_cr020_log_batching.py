"""CR-020 — the persistent log sink must batch flushes instead of flushing every line."""
from __future__ import annotations

import sys
from pathlib import Path

RELEASE_ROOT = Path(__file__).resolve().parents[4]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))

from shell.src.logs import RotatingLineSink  # noqa: E402


def test_cr020_flush_calls_far_below_line_count(tmp_path):
    sink = RotatingLineSink(str(tmp_path / "m.log"))
    n = 10_000
    for i in range(n):
        sink.write_line(f"line {i} some diagnostic content here")
    # Before the fix this was one flush per line (n flushes). Batching makes it a small fraction.
    assert sink.flush_calls < n // 20, f"{sink.flush_calls} flushes for {n} lines is not batched"
    sink.close()


def test_cr020_all_lines_durable_after_close(tmp_path):
    path = tmp_path / "m.log"
    sink = RotatingLineSink(str(path))
    n = 5_000
    for i in range(n):
        sink.write_line(f"row-{i}")
    sink.close()  # explicit flush+fsync at the lifecycle boundary
    # Every line is on disk despite batched flushing during writes.
    text = path.read_bytes().decode("utf-8")
    lines = [ln for ln in text.splitlines() if ln]
    assert len(lines) == n
    assert lines[0] == "row-0" and lines[-1] == f"row-{n - 1}"


def test_cr020_explicit_flush_is_durable(tmp_path):
    path = tmp_path / "m.log"
    sink = RotatingLineSink(str(path))
    sink.write_line("only-line")
    sink.flush()  # evidence boundary: must be readable now, before close
    assert "only-line" in path.read_bytes().decode("utf-8")
    sink.close()
