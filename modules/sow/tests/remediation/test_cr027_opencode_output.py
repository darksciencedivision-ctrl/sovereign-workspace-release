"""CR-027 — the OpenCode driver must not buffer unbounded child output.

Runs a real child that emits far more than the retained tail; peak retained bytes must stay
bounded while the tool-event count stays exact.
"""
from __future__ import annotations

import os
import sys

import pytest

from adapters.coding.opencode import driver  # resolved via the sow root on sys.path (conftest)


@pytest.mark.skipif(sys.platform != "win32", reason="driver uses taskkill; runner is Windows-only")
def test_cr027_bounded_tail_with_exact_event_count(tmp_path):
    n = 200_000  # ~6 MB of stdout, far beyond the 256 KiB retained tail
    code = (
        "import sys\n"
        f"for _ in range({n}):\n"
        "    sys.stdout.write('{\"type\":\"tool\",\"name\":\"read\"}\\n')\n"
        "sys.stdout.flush()\n"
    )
    outcome = driver.subprocess_runner(
        [sys.executable, "-c", code], cwd=str(tmp_path), env=dict(os.environ), timeout=120.0)

    assert outcome.returncode == 0 and outcome.timed_out is False
    # Every stdout line is a tool event and all are counted even though only a tail is retained.
    assert outcome.event_count == n
    # Retained tails are bounded regardless of how much the child emitted (memory safety).
    assert len(outcome.stdout) <= driver._STREAM_TAIL_BYTES + 4096, len(outcome.stdout)
    # The tail is a real suffix of the stream (last lines preserved).
    assert outcome.stdout.rstrip().endswith('{"type":"tool","name":"read"}')


def test_cr027_event_predicates():
    assert driver._is_tool_event_json_line('{"type":"tool","name":"read"}') is True
    assert driver._is_tool_event_json_line("not json") is False
    assert driver._count_stderr_markers("→ Bash cmd\n" * 3) == 3


def test_cr027_bounded_tail_helper_stays_bounded_and_is_a_suffix():
    tail = driver._BoundedTail(10)
    for chunk in ("abcd", "efgh", "ijkl"):
        tail.feed(chunk)
    text = tail.text()
    # Bounded (never exceeds cap) and a real suffix of the full stream (earliest whole chunks are
    # dropped first — amortized O(1), which is what keeps a multi-GB stream cheap).
    assert len(text) <= 10
    assert "abcdefghijkl".endswith(text)
    assert text.endswith("ijkl")
    # a single oversized chunk is trimmed to the cap
    tail2 = driver._BoundedTail(5)
    tail2.feed("0123456789")
    assert tail2.text() == "56789"
