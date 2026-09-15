"""CR-011 — log clear must not race incremental secret redaction.

A secret split across two pipe chunks must never leak its suffix when an operator log clear
interleaves between the chunks.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

RELEASE_ROOT = Path(__file__).resolve().parents[4]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))

from shell.src.logring import LogRing  # noqa: E402

# A real bare-provider secret. Split so the SUFFIX, on its own, matches no redaction pattern.
_PREFIX = b"api_key=sk-ABCDEFGHIJ"
_SUFFIX = b"KLMNOPQRSTUVWX\n"
_SECRET_SUFFIX = "KLMNOPQRSTUVWX"


def test_cr011_clear_between_split_secret_chunks_does_not_leak_suffix():
    ring = LogRing()
    ring.write(_PREFIX)      # prefix held in the streaming carry, nothing emitted yet
    ring.clear()             # operator clears the log mid-stream
    ring.write(_SUFFIX)      # the secret completes on this chunk
    out = ring.read()
    assert _SECRET_SUFFIX not in out, f"leaked secret suffix: {out!r}"
    assert "[REDACTED]" in out, out


def test_cr011_clear_at_every_byte_boundary_never_leaks():
    full = b"api_key=sk-ABCDEFGHIJKLMNOPQRSTUVWX\n"
    tail_alnum = "KLMNOPQRSTUVWX"
    for split in range(1, len(full)):
        ring = LogRing()
        ring.write(full[:split])
        ring.clear()
        ring.write(full[split:])
        ring.flush()
        out = ring.read()
        # The full token must never survive; and the distinctive alnum tail must not appear bare.
        assert "sk-ABCDEFGHIJKLMNOPQRSTUVWX" not in out, (split, out)
        assert tail_alnum not in out, (split, out)


def test_cr011_concurrent_write_and_clear_stress():
    ring = LogRing()
    secret_line = b"password=sk-ZYXWVUTSRQPONMLKJIHGFEDCBA0\n"
    leaked: list[str] = []
    stop = threading.Event()

    def writer():
        # feed the secret one byte at a time, so a clear can land at any boundary
        for _ in range(200):
            for i in range(len(secret_line)):
                ring.write(secret_line[i:i + 1])
        stop.set()

    def clearer():
        while not stop.is_set():
            ring.clear()
            if any(bad in ring.read() for bad in ("ZYXWVUTSRQPONMLKJIHGFEDCBA0",)):
                leaked.append(ring.read())

    tw = threading.Thread(target=writer)
    tc = threading.Thread(target=clearer)
    tw.start(); tc.start()
    tw.join(); tc.join()
    ring.flush()
    assert not leaked, f"secret leaked under concurrency: {leaked[:2]}"
    assert "ZYXWVUTSRQPONMLKJIHGFEDCBA0" not in ring.read()
