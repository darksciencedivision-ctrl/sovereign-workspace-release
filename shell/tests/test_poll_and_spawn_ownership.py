"""F-013 / F-014 — a poll cannot overwrite an operation that took ownership mid-poll, and the
supervisor refuses to spawn over a module that already has a live process.

F-013: poll() read state unlocked and published FAILED("EXIT") unconditionally, so a Restart that
landed between the poll's observation and its write had its fresh STARTING clobbered by the stale
FAILED. poll() now snapshots the operation generation and publishes every transition through
_observe_set, which drops the write when ownership changed.

F-014: JobSupervisor.spawn assigned self._processes[module_id] = ph over any existing entry, so a
second spawn (via the F-013 race, or a start whose readiness failed after spawn) orphaned the first
live process. spawn now refuses when a live handle already exists.
"""
import os
import sys
import time
import unittest

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if WS not in sys.path:
    sys.path.insert(0, WS)

from shell.src import states  # noqa: E402


class _FakeSupervisor:
    def __init__(self):
        self.stops = []
        self._procs = {}

    def spawn(self, module_id, argv, cwd, env, log_ring=None):
        self._procs[module_id] = _FakePh()
        return self._procs[module_id]

    def stop(self, module_id, grace_s):
        self.stops.append((module_id, grace_s))
        self._procs.pop(module_id, None)

    def get_process(self, module_id):
        return self._procs.get(module_id)


class _FakePh:
    pid = os.getpid()

    def is_alive(self):
        return True


def _adapter():
    return {
        "id": "m", "display_name": "Fixture", "state_class": "runnable",
        "launch": {"argv": ["x"], "cwd": "."},
        "readiness": {"kind": "process_window", "timeout_s": 1, "poll_ms": 10,
                      "url": "http://127.0.0.1:65535/"},
        "identity": {"kind": "process_image"}, "stop": {"grace_s": 1},
    }


class PollDoesNotOverwriteAnInFlightRestart(unittest.TestCase):
    def test_a_restart_landing_mid_poll_is_not_clobbered_by_failed_exit(self) -> None:
        sup = _FakeSupervisor()
        runner = states.ModuleRunner("m", _adapter(), sup)
        runner.state = states.READY

        class _RacingPh:
            pid = 4321

            def __init__(self, r):
                self._r = r
                self._calls = 0

            def is_alive(self_inner):
                self_inner._calls += 1
                if self_inner._calls == 1:
                    # A Restart lands between poll's snapshot and its FAILED("EXIT") write:
                    # stop the old process, then claim a fresh start (STARTING).
                    self_inner._r.stop()
                    self_inner._r.begin_start()
                return False

        sup._procs["m"] = _RacingPh(runner)
        runner.poll()
        self.assertEqual(runner.state, states.STARTING,
                         "poll's FAILED(EXIT) overwrote a Restart that took ownership mid-poll")

    def test_a_genuinely_dead_process_still_transitions_to_failed(self) -> None:
        # Positive control: with no racing operation, a dead process is reported FAILED.
        sup = _FakeSupervisor()
        runner = states.ModuleRunner("m", _adapter(), sup)
        runner.state = states.READY

        class _DeadPh:
            pid = 999

            def is_alive(self):
                return False

        sup._procs["m"] = _DeadPh()
        runner.poll()
        self.assertEqual(runner.state, states.FAILED)
        self.assertEqual(runner.reason, "EXIT")


_CHILD = "import time\ntime.sleep(60)\n"


@unittest.skipUnless(sys.platform == "win32", "JobSupervisor is Windows-only")
class SpawnRefusesToReplaceALiveProcess(unittest.TestCase):
    def test_a_second_spawn_for_a_live_module_is_refused(self) -> None:
        import tempfile
        from shell.src.supervisor import JobSupervisor, SupervisorError

        tmp = tempfile.mkdtemp(prefix="f014-")
        child = os.path.join(tmp, "child.py")
        with open(child, "w", encoding="utf-8") as f:
            f.write(_CHILD)
        sup = JobSupervisor(max_processes=4)
        try:
            sup.spawn("m", [sys.executable, child], tmp, dict(os.environ))
            time.sleep(0.5)
            with self.assertRaises(SupervisorError) as ctx:
                sup.spawn("m", [sys.executable, child], tmp, dict(os.environ))
            self.assertIn("already has a live managed process", str(ctx.exception))
        finally:
            sup.close()
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
