"""F-011 — the supervisor offers a graceful-shutdown channel, and the SQLite-writing modules adopt
it.

The live test spawns a real child through JobSupervisor: the child installs the canonical watcher
(shell/src/graceful) and, when the supervisor signals the shutdown event, writes a marker and exits
0 on its own — so stop() reports graceful=True, forced=False and never has to TerminateJobObject.
This is the mechanism a CREATE_NO_WINDOW child could not get from CTRL_BREAK.

Static pins assert the two module copies (which cannot import the shell package) stay in step with
the canonical helper.
"""
import os
import sys
import tempfile
import time
import unittest

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if WS not in sys.path:
    sys.path.insert(0, WS)

from shell.src import graceful  # noqa: E402

_CHILD = r'''
import os, sys, time
sys.path.insert(0, sys.argv[2])
from shell.src.graceful import install_shutdown_watcher
marker = sys.argv[1]
def _on_shutdown():
    with open(marker, "w", encoding="utf-8") as f:
        f.write("graceful")
    os._exit(0)
install_shutdown_watcher(_on_shutdown)
time.sleep(60)   # wait to be shut down; the test signals within its grace window
'''


class TestGracefulChannelUnit(unittest.TestCase):
    def test_shutdown_event_name_reads_the_env(self):
        self.assertEqual(graceful.shutdown_event_name({"SWS_SHUTDOWN_EVENT": "Local\\x"}), "Local\\x")
        self.assertIsNone(graceful.shutdown_event_name({}))

    def test_watcher_is_a_noop_without_an_event(self):
        self.assertIsNone(graceful.install_shutdown_watcher(lambda: None, env={}))


@unittest.skipUnless(sys.platform == "win32", "the graceful channel is a Windows named Event")
class TestGracefulChannelLive(unittest.TestCase):
    def test_stop_signals_the_event_and_the_child_exits_gracefully(self):
        from shell.src.supervisor import JobSupervisor

        tmp = tempfile.mkdtemp(prefix="sws-graceful-")
        child_py = os.path.join(tmp, "child.py")
        marker = os.path.join(tmp, "marker.txt")
        with open(child_py, "w", encoding="utf-8") as f:
            f.write(_CHILD)

        sup = JobSupervisor(max_processes=4)
        try:
            sup.spawn("gracefultest", [sys.executable, child_py, marker, WS], tmp, dict(os.environ))
            # Give the child a moment to import and open the event before we signal it. (The event
            # is manual-reset and created before the child starts, so even a signal that beat the
            # wait would be latched; this sleep only keeps the timing obvious.)
            time.sleep(1.5)
            record = sup.stop("gracefultest", grace_s=10)
            # Read the marker BEFORE cleanup removes the temp tree.
            marker_written = os.path.isfile(marker)
        finally:
            sup.close()
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertTrue(record["graceful"], f"child should have exited on the event: {record}")
        self.assertFalse(record["forced"], f"TerminateJobObject should not have been needed: {record}")
        self.assertTrue(marker_written, "the child's graceful-shutdown callback did not run")


class TestModuleAdoptionPins(unittest.TestCase):
    """The two SQLite writers carry their own watcher (they cannot import shell.src.graceful). Pin
    each copy to the canonical env-var name and the OpenEventW/SYNCHRONIZE wait, so a future
    divergence from shell/src/graceful is caught here."""

    def _read(self, *parts):
        with open(os.path.join(WS, *parts), "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read()

    def test_canonical_helper_defines_the_installer(self):
        t = self._read("shell", "src", "graceful.py")
        self.assertIn("def install_shutdown_watcher", t)
        self.assertIn("SWS_SHUTDOWN_EVENT", t)

    def test_tokencenter_adopts_the_channel(self):
        t = self._read("modules", "tokencenter", "piggybank.py")
        self.assertIn("SWS_SHUTDOWN_EVENT", t)
        self.assertIn("OpenEventW", t)
        self.assertIn("_install_shutdown_watcher(server.shutdown)", t)

    def test_sovereign_adopts_the_channel(self):
        t = self._read("modules", "sovereign", "sovereign_product", "server.py")
        self.assertIn("SWS_SHUTDOWN_EVENT", t)
        self.assertIn("OpenEventW", t)
        self.assertIn("service.close()", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
