"""
§7.4 state machine — one test per transition (R3-5).

Every test drives a real fixture process through the real ModuleRunner. The adapter is built in
a temp directory with argv[0] pointing at the running interpreter's absolute .exe.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from shell.src.logring import LogRing
from shell.src.states import (
    DEGRADED, EXTERNAL, FAILED, PORT_OCCUPIED_UNRECOGNIZED, READY, STOPPED, ModuleRunner)
from shell.src.supervisor import JobSupervisor
from shell.tests._harness import fixture, free_port, pid_alive, python_exe, wait_until


def make_adapter(root, port, identity="ok", timeout_s=15, extra_args=(), poll_ms=250):
    argv = [python_exe(), "-B", fixture("fixture_http.py"),
            "--port", str(port), "--identity", identity]
    argv.extend(str(a) for a in extra_args)
    required = ["status", "product_version"] if identity == "ok" else ["status", "product_version"]
    return {
        "id": "fix",
        "display_name": "Fixture",
        "description": "state machine fixture",
        "state_class": "runnable",
        "root": root,
        "runtime_writes": [],
        "launch": {
            "cwd": root,
            "argv": argv,
            "env_allowlist": ["SYSTEMROOT", "PATH", "TEMP", "TMP"],
            "env_set": {"PYTHONDONTWRITEBYTECODE": "1"},
        },
        "readiness": {"kind": "http", "url": "http://127.0.0.1:{}/health".format(port),
                      "expect_status": 200, "timeout_s": timeout_s, "poll_ms": poll_ms},
        "identity": {"kind": "http_json", "url": "http://127.0.0.1:{}/health".format(port),
                     "required_keys": required},
        "open": {"kind": "browser", "url": "http://127.0.0.1:{}/".format(port)},
        "stop": {"kind": "job_object", "grace_s": 2},
        "_adapter_hash": "0" * 64,
    }


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sws-states-")
        self.sup = JobSupervisor()
        self.ring = LogRing()
        self.port = free_port()
        self.external = None

    def tearDown(self):
        try:
            self.sup.close()
        except Exception:
            pass
        if self.external is not None and self.external.poll() is None:
            self.external.kill()
            self.external.wait(timeout=10)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def runner(self, **kw):
        adapter = make_adapter(self.tmp, self.port, **kw)
        return ModuleRunner("fix", adapter, self.sup, self.ring)

    def start_external(self, identity="ok"):
        """Start a fixture OUTSIDE the supervisor and its Job."""
        self.external = subprocess.Popen(
            [python_exe(), "-B", fixture("fixture_http.py"),
             "--port", str(self.port), "--identity", identity],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import urllib.error
        import urllib.request

        def up():
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:{}/health".format(self.port), timeout=1)
                return True
            except urllib.error.HTTPError:
                return True   # 503 still means the port is occupied
            except OSError:
                return False
        self.assertTrue(wait_until(up, 15), "external fixture never came up")


class TestManagedTransitions(_Base):

    def test_starting_to_ready(self):
        r = self.runner()
        self.assertEqual(r.state, STOPPED)
        display, err = r.start()
        self.assertEqual(display, READY, err)

    def test_starting_to_failed_exit(self):
        """Process exits before readiness.

        --exit-after alone is not enough: the fixture would answer /health during its first
        second and reach READY. --unready holds readiness off so the exit is what the runner
        observes, which is the transition under test.
        """
        r = self.runner(timeout_s=15, extra_args=("--unready", "--exit-after", "1"))
        display, _ = r.start()
        self.assertEqual(display,
                         "FAILED(PROCESS_START_FAILED: exited before ready)")

    def test_starting_to_failed_timeout(self):
        """Readiness deadline expires while the process is still alive."""
        r = self.runner(timeout_s=5, extra_args=("--unready",))
        t0 = time.time()
        display, _ = r.start()
        self.assertEqual(display,
                         "FAILED(HEALTH_CHECK_FAILED: readiness probe not satisfied)")
        self.assertGreaterEqual(time.time() - t0, 4.5, "should have waited out the deadline")

    def test_starting_to_failed_identity(self):
        """Readiness passes, identity fails, process is then terminated."""
        r = self.runner(identity="wrong")
        display, _ = r.start()
        self.assertIn("FAILED(IDENTITY_MISMATCH", display)
        self.assertIsNone(self.sup.get_process("fix"),
                          "the process must be stopped after an identity failure")

    def test_ready_to_degraded_to_ready(self):
        flag = os.path.join(self.tmp, "degrade.flag")
        r = self.runner(extra_args=("--degrade-flag", flag))
        self.assertEqual(r.start()[0], READY)

        with open(flag, "w", encoding="utf-8") as f:
            f.write("1")
        self.assertTrue(wait_until(lambda: r.poll() == DEGRADED, 15),
                        "READY -> DEGRADED did not happen")
        self.assertEqual(r.state, DEGRADED)

        os.remove(flag)
        self.assertTrue(wait_until(lambda: r.poll() == READY, 15),
                        "DEGRADED -> READY did not happen")
        self.assertEqual(r.state, READY)

    def test_ready_to_failed_exit(self):
        r = self.runner()
        self.assertEqual(r.start()[0], READY)
        pid = self.sup.get_process("fix").pid
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        self.assertTrue(wait_until(lambda: not pid_alive(pid), 10))
        self.assertEqual(r.poll(), "FAILED(EXIT)")

    def test_ready_to_stopped(self):
        r = self.runner()
        self.assertEqual(r.start()[0], READY)
        self.assertEqual(r.stop(), STOPPED)

    def test_starting_to_stopped_via_cancel(self):
        """STARTING -> STOPPED when the operator cancels."""
        r = self.runner(timeout_s=15, extra_args=("--unready",))
        r._set("STARTING")
        self.assertEqual(r.cancel(), STOPPED)


class TestExternalTransitions(_Base):

    def test_external_detected_start_refused_open_enabled(self):
        self.start_external(identity="ok")
        r = self.runner()
        self.assertEqual(r.poll(), EXTERNAL)
        allowed, status, _msg = r.can_start()
        self.assertFalse(allowed, "Start must be refused while an external instance owns the port")
        self.assertEqual(status, 409)
        self.assertTrue(r.can_open(), "Open must be enabled in EXTERNAL")

    def test_port_occupied_unrecognized(self):
        self.start_external(identity="wrong")
        r = self.runner()
        self.assertEqual(r.poll(), "FAILED({})".format(PORT_OCCUPIED_UNRECOGNIZED))
        self.assertEqual(r.state, FAILED)
        self.assertEqual(r.reason, PORT_OCCUPIED_UNRECOGNIZED)
        allowed, status, _ = r.can_start()
        self.assertFalse(allowed)
        self.assertEqual(status, 409)

    def test_external_stays_external_on_reprobe(self):
        self.start_external(identity="ok")
        r = self.runner()
        self.assertEqual(r.poll(), EXTERNAL)
        self.assertEqual(r.poll(), EXTERNAL)

    def test_external_to_stopped(self):
        self.start_external(identity="ok")
        r = self.runner()
        self.assertEqual(r.poll(), EXTERNAL)
        self.external.kill()
        self.external.wait(timeout=10)
        self.assertTrue(wait_until(lambda: r.poll() == STOPPED, 20),
                        "EXTERNAL -> STOPPED did not happen after the endpoint was released")

    def test_port_occupied_unrecognized_to_stopped(self):
        self.start_external(identity="wrong")
        r = self.runner()
        self.assertEqual(r.poll(), "FAILED({})".format(PORT_OCCUPIED_UNRECOGNIZED))
        self.external.kill()
        self.external.wait(timeout=10)
        self.assertTrue(wait_until(lambda: r.poll() == STOPPED, 20))

    def test_h9_shell_exit_leaves_external_alive(self):
        """H-9: stopping the shell's view of an EXTERNAL module never touches the process."""
        self.start_external(identity="ok")
        r = self.runner()
        self.assertEqual(r.poll(), EXTERNAL)
        pid = self.external.pid
        r.stop()
        self.assertEqual(r.state, STOPPED)
        time.sleep(0.5)
        self.assertTrue(pid_alive(pid),
                        "H-9 violated: an externally started process was killed")


class TestNotStartedAndConfigError(unittest.TestCase):

    def test_distillery_is_not_started(self):
        from shell.src.adapter import load_all_adapters
        adapters = load_all_adapters()
        self.assertIn("distillery", adapters)
        r = ModuleRunner("distillery", adapters["distillery"], None)
        self.assertEqual(r.state, "NOT_STARTED")
        allowed, status, _ = r.can_start()
        self.assertFalse(allowed)
        self.assertEqual(status, 400)

    def test_config_error_adapter(self):
        r = ModuleRunner("bad", {"error": "CONFIG_ERROR", "reason": "bad json"}, None)
        self.assertEqual(r.state, "CONFIG_ERROR")
        self.assertEqual(r.display, "CONFIG_ERROR(bad json)")


if __name__ == "__main__":
    unittest.main()
