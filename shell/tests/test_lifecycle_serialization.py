"""
SWS-CORRECTIVE-01 workstream 1.3 - module lifecycle serialisation (L3).

Each test drives a real ModuleRunner and blocks the slow part of `start()` on a threading
event rather than a sleep, so the interleaving under test is the one the test names.

The reproduction the directive records is `test_cancel_during_readiness_cannot_publish_ready`:
`cancel()` sets STOPPED while an outstanding `start()` is inside its readiness probe, and the
stale `start()` then publishes READY over the operator's cancellation.
"""
import threading
import time
import unittest

from shell.src.states import FAILED, READY, STARTING, STOPPED, ModuleRunner


class _FakeProcess:
    def __init__(self, pid=4242):
        self.pid = pid
        self.job_handle = None
        self._alive = True

    def is_alive(self):
        return self._alive

    def die(self):
        self._alive = False


class _FakeSupervisor:
    """Records spawn/stop calls and lets a test block inside spawn."""

    def __init__(self, spawn_gate=None):
        self.spawned = []
        self.stopped = []
        self._procs = {}
        self._spawn_gate = spawn_gate
        self.lock = threading.Lock()

    def spawn(self, module_id, argv, cwd, env, log_ring=None):
        if self._spawn_gate is not None:
            self._spawn_gate.wait(10)
        proc = _FakeProcess(pid=5000 + len(self.spawned))
        with self.lock:
            self.spawned.append(module_id)
            self._procs[module_id] = proc
        return proc

    def stop(self, module_id, grace_s=5):
        with self.lock:
            self.stopped.append(module_id)
            proc = self._procs.pop(module_id, None)
        if proc is not None:
            proc.die()

    def get_process(self, module_id):
        with self.lock:
            return self._procs.get(module_id)


def _adapter(tmp="."):
    return {
        "id": "fix",
        "display_name": "Fixture",
        "state_class": "runnable",
        "root": tmp,
        "runtime_writes": [],
        "launch": {
            "cwd": tmp,
            "argv": ["fixture-runtime-that-need-not-exist"],
            "env_allowlist": [],
            "env_set": {},
        },
        # `process_window` keeps the probe off the network; the tests override it anyway.
        "readiness": {"kind": "process_window", "timeout_s": 30, "poll_ms": 10},
        "identity": {"kind": "process_image", "expected_image": "x"},
        "open": {"kind": "none"},
        "stop": {"kind": "job_object", "grace_s": 1},
        "_adapter_hash": "0" * 64,
    }


class _GatedRunner(ModuleRunner):
    """A runner whose readiness and identity probes are driven by explicit events."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.in_readiness = threading.Event()
        self.release_readiness = threading.Event()
        self.readiness_result = (True, 0.01, "")
        self.in_identity = threading.Event()
        self.release_identity = threading.Event()
        self.identity_result = (True, "")

    def _readiness(self, cfg, ph, since):
        self.in_readiness.set()
        self.release_readiness.wait(10)
        return self.readiness_result

    def _identity(self, cfg, ph):
        self.in_identity.set()
        self.release_identity.wait(10)
        return self.identity_result


class LifecycleSerialisationTests(unittest.TestCase):
    def setUp(self):
        self.sup = _FakeSupervisor()
        self.runner = _GatedRunner("fix", _adapter(), self.sup)
        self.threads = []
        self.extra_runners = []

    def tearDown(self):
        # Never leave a gated worker parked on an event.
        for runner in [self.runner] + self.extra_runners:
            runner.release_readiness.set()
            runner.release_identity.set()
        for t in self.threads:
            t.join(10)
            self.assertFalse(t.is_alive(), "a worker thread outlived the test")

    def _start_async(self, runner=None):
        runner = runner or self.runner
        box = {}

        def work():
            try:
                box["result"] = runner.start()
            except Exception as exc:  # noqa: BLE001 - recorded, then asserted on
                box["error"] = exc

        t = threading.Thread(target=work, daemon=True)
        self.threads.append(t)
        t.start()
        return box

    # -- L3: the recorded reproduction -------------------------------------
    def test_cancel_during_readiness_cannot_publish_ready(self):
        """cancel() during the readiness probe wins; the stale start() must not set READY."""
        self._start_async()
        self.assertTrue(self.runner.in_readiness.wait(10), "start() never reached readiness")
        self.assertEqual(self.runner.state, STARTING)

        self.assertEqual(self.runner.cancel(), STOPPED)

        # The outstanding start() now completes with a *successful* probe result.
        self.runner.release_readiness.set()
        self.runner.release_identity.set()
        for t in self.threads:
            t.join(10)

        self.assertEqual(
            self.runner.state, STOPPED,
            "a cancelled start published {} over the operator cancellation".format(
                self.runner.display))

    def test_cancel_before_spawn_never_spawns(self):
        """A cancel that lands before CreateProcess must stop the start, not race it."""
        gate = threading.Event()
        sup = _FakeSupervisor(spawn_gate=gate)
        runner = _GatedRunner("fix", _adapter(), sup)
        self.extra_runners.append(runner)
        self._start_async(runner)

        # Wait until start() has published STARTING, then cancel while spawn is gated.
        deadline = time.time() + 10
        while runner.state != STARTING and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(runner.state, STARTING)
        runner.cancel()
        gate.set()
        runner.release_readiness.set()
        runner.release_identity.set()
        for t in self.threads:
            t.join(10)

        self.assertEqual(runner.state, STOPPED)
        self.assertEqual(sup.spawned, [], "a cancelled start spawned a process anyway")

    def test_cancelled_start_does_not_publish_failed(self):
        """A stale failure must not overwrite the cancellation either."""
        self._start_async()
        self.assertTrue(self.runner.in_readiness.wait(10))
        self.runner.cancel()
        self.runner.readiness_result = (False, 1.0, "probe timed out")
        self.runner.release_readiness.set()
        for t in self.threads:
            t.join(10)
        self.assertEqual(self.runner.state, STOPPED)

    def test_cancelled_start_does_not_stop_a_later_instance(self):
        """The superseded operation must not terminate the process a later start owns."""
        self._start_async()
        self.assertTrue(self.runner.in_readiness.wait(10))
        self.runner.cancel()

        # A second, current start on the same supervisor: a stale stop() would reach its
        # process if ownership were bound to the module id alone.
        second = _GatedRunner("fix", _adapter(), self.sup)
        self.extra_runners.append(second)
        second.release_readiness.set()
        second.release_identity.set()
        second.start()
        self.assertEqual(second.state, READY)
        live = self.sup.get_process("fix")
        self.assertIsNotNone(live)

        # Now let the *old* operation finish with a failing probe. It must not stop "fix".
        self.runner.readiness_result = (False, 1.0, "stale timeout")
        self.runner.release_readiness.set()
        for t in self.threads:
            t.join(10)
        self.assertTrue(live.is_alive(),
                        "a superseded start terminated the process a later start owns")
        self.assertEqual(second.state, READY)

    def test_simultaneous_starts_create_one_owned_process(self):
        """Two concurrent start() calls must not both spawn."""
        runner = _GatedRunner("fix", _adapter(), self.sup)
        runner.release_readiness.set()
        runner.release_identity.set()
        self.extra_runners.append(runner)
        barrier = threading.Barrier(2)
        errors = []

        def work():
            barrier.wait(10)
            try:
                runner.start()
            except ValueError:
                pass  # a refused second start is the correct outcome
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=work, daemon=True) for _ in range(2)]
        self.threads.extend(threads)
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.sup.spawned), 1,
                         "simultaneous starts created {} owned processes".format(
                             len(self.sup.spawned)))

    def test_stop_during_startup_is_terminal(self):
        """stop() while STARTING behaves as a cancellation, not a no-op."""
        self._start_async()
        self.assertTrue(self.runner.in_readiness.wait(10))
        self.runner.stop()
        self.runner.release_readiness.set()
        self.runner.release_identity.set()
        for t in self.threads:
            t.join(10)
        self.assertEqual(self.runner.state, STOPPED)

    def test_poll_does_not_erase_a_terminal_failure(self):
        """A useful FAILED cause survives a poll that merely finds no managed process."""
        self.runner._set(FAILED, "HEALTH_CHECK_FAILED: readiness probe not satisfied")
        self.runner.poll()
        self.assertEqual(self.runner.state, FAILED)
        self.assertIn("HEALTH_CHECK_FAILED", self.runner.reason)


if __name__ == "__main__":
    unittest.main()
