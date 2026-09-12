"""R01 / R02 — a Start must not launch after an acknowledged Stop, and a poll observation must
not overwrite an operation that took ownership while the poll's probe was in flight.

Both are driven deterministically against a real ModuleRunner and a fake supervisor; no real
process is spawned and no timing is relied on.
"""
import os
import sys
import unittest

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if WS not in sys.path:
    sys.path.insert(0, WS)

from shell.src import probe as probe_mod  # noqa: E402
from shell.src import states  # noqa: E402


class _FakePh:
    pid = os.getpid()

    def is_alive(self):
        return True


class _FakeSupervisor:
    def __init__(self):
        self.spawns = []
        self.stops = []
        self._procs = {}

    def spawn(self, module_id, argv, cwd, env, log_ring=None):
        self.spawns.append(module_id)
        ph = _FakePh()
        self._procs[module_id] = ph
        return ph

    def stop(self, module_id, grace_s):
        self.stops.append((module_id, grace_s))
        self._procs.pop(module_id, None)

    def get_process(self, module_id):
        return self._procs.get(module_id)


def _adapter(kind="process_window"):
    return {
        "id": "m",
        "display_name": "Fixture",
        "state_class": "runnable",
        "launch": {"argv": ["x"], "cwd": "."},
        "readiness": {"kind": kind, "timeout_s": 1, "poll_ms": 10,
                      "url": "http://127.0.0.1:65535/"},
        "identity": {"kind": "process_image"},
        "stop": {"grace_s": 1},
    }


class TestStartAfterStopIsRefused(unittest.TestCase):
    def test_stop_between_admission_and_worker_prevents_the_spawn(self):
        """R01: the server claims the operation (begin_start -> STARTING) synchronously, then a
        worker runs start(op). A Stop landing in that gap must supersede so the worker spawns
        nothing — the exact sequence that previously acknowledged Stop and then launched."""
        sup = _FakeSupervisor()
        runner = states.ModuleRunner("m", _adapter(), sup)

        op = runner.begin_start()                 # synchronous admission (server handler)
        self.assertEqual(runner.state, states.STARTING)

        self.assertEqual(runner.stop(), states.STOPPED)   # Stop in the gap

        display, err = runner.start(op=op)        # the queued worker finally runs
        self.assertEqual(sup.spawns, [], "no process may be spawned after an acknowledged Stop")
        self.assertEqual(runner.state, states.STOPPED)
        self.assertIn("superseded", err)

    def test_a_normal_admitted_start_still_spawns(self):
        """Positive control: with no intervening Stop, start(op) proceeds to spawn."""
        sup = _FakeSupervisor()
        runner = states.ModuleRunner("m", _adapter(), sup)
        op = runner.begin_start()
        runner.start(op=op)
        self.assertEqual(sup.spawns, ["m"], "an uninterrupted admitted start must spawn once")


class TestPollDoesNotOverwriteAnOperation(unittest.TestCase):
    def test_probe_external_drops_its_observation_when_a_start_takes_ownership(self):
        """R02: while _probe_external's HTTP probe is in flight, a Start takes ownership. The
        poll's EXTERNAL/FAILED observation must be dropped, leaving the start's STARTING intact."""
        sup = _FakeSupervisor()
        runner = states.ModuleRunner("m", _adapter(kind="http"), sup)
        runner.state = states.STOPPED

        original = probe_mod.http_probe

        def racing_probe(*_a, **_k):
            # A concurrent Start claims the module mid-probe (advances the operation counter).
            runner.begin_start()
            return True, 0.0, ""

        probe_mod.http_probe = racing_probe
        runner._identity = lambda cfg, ph: (True, "")   # force the EXTERNAL branch
        try:
            runner._probe_external()
        finally:
            probe_mod.http_probe = original

        self.assertEqual(runner.state, states.STARTING,
                         "the poll observation overwrote a start that owned the module")


if __name__ == "__main__":
    unittest.main(verbosity=2)
