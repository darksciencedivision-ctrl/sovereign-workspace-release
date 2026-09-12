"""R37 — the shared research executor admits one run at a time.

ResearchExecutor is a single shared instance and carries per-run state on itself: the cancel and
interrupt callbacks, the active-time base and start, and the progress callback. Two runs on it at
once clobber one another -- run B's cancel replaces run A's, B's timing resets A's, B steals A's
progress events. Until that state moves into a per-run context, run() enforces single-run
admission: a concurrent second run is refused (ResearchAlreadyRunning) instead of corrupting the
first, so run A's callbacks, timing and progress stay A's.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.paths import (  # noqa: E402
    ROOT_MARKER,
    ROOT_MARKER_CONTENT,
    resolve_product_paths,
)
from sovereign_product.research import ResearchAlreadyRunning, ResearchExecutor  # noqa: E402


class SingleRunAdmission(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r37-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        root = self.tmp / "install"
        root.mkdir()
        (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        (root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
        state = self.tmp / "external-state"
        paths = resolve_product_paths(
            root, state_dir=state, approved_roots=(state,), create=True)

        class _Client:  # a model client that exposes generate() but is never called here
            def generate(self, **kwargs):
                raise AssertionError("no generation should occur in an admission test")

        self.executor = ResearchExecutor(paths, _Client())

    def test_a_concurrent_run_is_refused_while_one_is_in_flight(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        a_result = {}

        # Run A holds the admission lock while it is "in flight" (blocked here). It also records the
        # per-run state that a concurrent B would otherwise clobber.
        def blocking_admitted(*args, **kwargs):
            self.executor._cancel = lambda: "A-cancel"
            self.executor._active_started = 111.0
            self.executor._progress = lambda *a, **k: "A-progress"
            entered.set()
            release.wait(5)
            return "A-done"

        self.executor._run_admitted = blocking_admitted  # type: ignore[assignment]

        thread_a = threading.Thread(
            target=lambda: a_result.setdefault(
                "value", self.executor.run("ra", "objective A", model="m:1")))
        thread_a.start()
        self.assertTrue(entered.wait(5), "run A never entered its admitted body")

        # While A is in flight, B is refused -- it never runs, so it cannot touch A's state.
        with self.assertRaises(ResearchAlreadyRunning):
            self.executor.run("rb", "objective B", model="m:1")

        # A's per-run state is exactly what A set; B did not reset timing or steal the callback.
        self.assertEqual(self.executor._cancel(), "A-cancel")
        self.assertEqual(self.executor._active_started, 111.0)
        self.assertEqual(self.executor._progress(), "A-progress")

        release.set()
        thread_a.join(5)
        self.assertEqual(a_result.get("value"), "A-done")

    def test_the_lock_is_released_after_a_run_so_the_next_run_is_admitted(self) -> None:
        calls = []
        self.executor._run_admitted = lambda *a, **k: calls.append(a[0]) or "ok"  # type: ignore
        self.assertEqual(self.executor.run("r1", "o", model="m:1"), "ok")
        # A second, sequential run must be admitted (the lock did not leak).
        self.assertEqual(self.executor.run("r2", "o", model="m:1"), "ok")
        self.assertEqual(calls, ["r1", "r2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
