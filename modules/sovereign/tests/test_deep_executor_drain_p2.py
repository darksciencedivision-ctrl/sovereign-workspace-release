"""R34 — the legacy DeepExecutor bounds its drain when a descendant keeps the pipes open.

After the parent process exits, a descendant can keep stdout/stderr open, so the reader threads
never see EOF and the drain loop waited forever -- past the configured timeout, because the tree
terminator was guarded by `process.poll() is None` and never fired once the parent had exited.
The loop now bounds the post-exit drain: once the parent is gone it waits a short grace, then
terminates the whole tree and stops.
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.executors import DeepExecutor  # noqa: E402


class _BlockingStream:
    """A pipe a descendant still holds: readline() blocks until released, so it never yields EOF."""

    def __init__(self, release: threading.Event) -> None:
        self._release = release

    def readline(self):
        self._release.wait(10)
        return ""  # EOF once released (test teardown), so the daemon reader can exit


class _ExitedProcess:
    """A process that has already exited (poll -> 0) but whose streams are held open elsewhere."""

    def __init__(self, release: threading.Event) -> None:
        self.pid = 4242
        self.stdout = _BlockingStream(release)
        self.stderr = _BlockingStream(release)

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


class DrainIsBounded(unittest.TestCase):
    def test_a_descendant_holding_the_pipes_does_not_hang_the_drain(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="r34-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / "cycle_runner_v3.py").write_text("# fixture\n", encoding="utf-8")
        release = threading.Event()
        self.addCleanup(release.set)   # let the daemon reader threads exit after the test
        terminated = []

        # A fast monotonic so the 5s post-exit grace is crossed in a few loop iterations.
        ticks = iter(range(0, 100_000, 3))
        executor = DeepExecutor(
            tmp,
            popen_factory=lambda *a, **k: _ExitedProcess(release),
            process_tree_terminator=lambda p: terminated.append(p),
            poll_interval=0.01,
            monotonic=lambda: float(next(ticks)),
        )

        done = threading.Event()
        result = {}

        def run():
            try:
                result["value"] = executor.execute("s1", "a topic", timeout_seconds=None)
            finally:
                done.set()

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        # It must RETURN (the bounded drain), not hang, well within the wall clock.
        self.assertTrue(done.wait(15), "DeepExecutor.execute hung on a descendant holding the pipes")
        self.assertTrue(terminated, "the process tree was never reclaimed after the parent exited")


if __name__ == "__main__":
    unittest.main(verbosity=2)
