"""
H-4 regression — shell/src/server.py must import FAILED (SWS-REM-DIR-20260828 R2 B1-3).

Pre-fix defect: server.py:26 imported ModuleRunner, EXTERNAL, READY, DEGRADED, STARTING but not
FAILED, while _start_worker's except path executed runner._set(FAILED, ...). A runner whose
start() raised therefore produced a secondary NameError instead of recording
FAILED(PROCESS_START_FAILED) — the thread died with the runner stuck in STARTING.

Contract under test:
  1. server exposes the FAILED constant (the import exists);
  2. _start_worker records FAILED + PROCESS_START_FAILED when start() raises;
  3. a real ModuleRunner whose start() raises BEFORE CreateProcessW ends FAILED with zero
     spawn attempts — no NameError, no orphan process.

Fail-before: tests 1 and 2/3 fail (missing attribute / NameError). Pass-after: all green.
"""
import unittest

from shell.src import server
from shell.src import states


class _RecordingRaisingRunner:
    """Duck-typed runner: start() raises; _publish records the transition (R01: the worker now
    publishes a failure through the operation so it cannot overwrite a superseding Stop)."""

    def __init__(self):
        self.state = states.STOPPED
        self.reason = ""
        self.transitions = []

    @property
    def display(self):
        return self.state

    def start(self, op=None):
        raise RuntimeError("boom")

    def _publish(self, op, state, reason=""):
        self.state = state
        self.reason = reason
        self.transitions.append((state, reason))
        return True


class _NoSpawnSupervisor:
    """Supervisor stub that fails loudly if spawn is ever reached."""

    def __init__(self):
        self.spawn_calls = []

    def spawn(self, *args, **kwargs):
        self.spawn_calls.append((args, kwargs))
        raise AssertionError("spawn must not be reached when start() raises first")

    def stop(self, *args, **kwargs):
        pass


class StartWorkerFailureContract(unittest.TestCase):
    def test_failed_constant_is_imported_into_server(self):
        self.assertTrue(hasattr(server, "FAILED"),
                        "server.py must import FAILED (H-4)")
        self.assertEqual(server.FAILED, states.FAILED)

    def test_raising_start_records_failed_not_nameerror(self):
        runner = _RecordingRaisingRunner()
        # Pre-fix this call raised NameError: name 'FAILED' is not defined.
        server.ShellAPIHandler._start_worker(runner, op=1)
        self.assertEqual(runner.state, states.FAILED)
        self.assertEqual(len(runner.transitions), 1)
        self.assertTrue(runner.reason.startswith("PROCESS_START_FAILED:"),
                        runner.reason)
        self.assertIn("boom", runner.reason)

    def test_real_runner_fails_before_spawn_with_no_orphan(self):
        sup = _NoSpawnSupervisor()
        adapter = {
            "id": "broken",
            "display_name": "Broken fixture",
            "description": "start() raises before CreateProcessW",
            "state_class": "runnable",
            "launch": {"cwd": "."},  # no argv -> KeyError inside start()
            "readiness": {"kind": "none"},
        }
        runner = states.ModuleRunner("broken", adapter, sup)
        op = runner.begin_start()
        server.ShellAPIHandler._start_worker(runner, op)
        self.assertEqual(runner.state, states.FAILED)
        self.assertTrue(runner.reason.startswith("PROCESS_START_FAILED:"),
                        runner.reason)
        self.assertEqual(sup.spawn_calls, [],
                         "no process may be spawned, therefore no orphan")


if __name__ == "__main__":
    unittest.main(verbosity=2)
