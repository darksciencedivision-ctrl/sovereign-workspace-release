"""
H-7 (rate limit, process cap), H-9 (shell exit ownership), H-10 layer 2 (spawn-time quota guard).
R3-6.

The 429 test runs the real ShellAPIHandler in-process against a fixture-backed ModuleRunner. That
gives the genuine HTTP surface and the genuine rate-limit code path without launching any real
module, which directive section 0.1(4) forbids.
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from shell.src import supervisor as sup_mod
from shell.src.adapter import compile_adapter, load_all_adapters
from shell.src.logring import LogRing
from shell.src.server import START_RATE_LIMIT_S, ShellAPIHandler
from shell.src.states import ModuleRunner, QuotaGuardError, build_env, check_quota_guard
from shell.src.supervisor import JobSupervisor, SupervisorError
from shell.tests._harness import (
    fixture, free_port, pid_alive, python_exe, start_shell, stop_shell, wait_until)
from shell.tests.test_states import make_adapter


class TestRateLimitAndCap(unittest.TestCase):
    """H-7: one Start per module per 2 s; at most 4 managed processes."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sws-h7-")
        self.sup = JobSupervisor()
        self.port = free_port()
        self.server = None

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        try:
            self.sup.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _serve_with_fixture_module(self):
        """Real handler, real socket, one fixture module. Nothing real is launched."""
        fixture_port = free_port()
        adapter = make_adapter(self.tmp, fixture_port, extra_args=("--unready",), timeout_s=5)
        runner = ModuleRunner("fix", adapter, self.sup, LogRing())

        ShellAPIHandler.supervisor = self.sup
        ShellAPIHandler.adapters = {"fix": adapter}
        ShellAPIHandler.states = {"fix": runner}
        ShellAPIHandler.log_rings = {"fix": LogRing()}
        ShellAPIHandler.selftest = False

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), ShellAPIHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return runner

    def _post_start(self):
        port = self.server.server_port
        data = json.dumps({"id": "fix"}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:{}/api/start".format(port), data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Origin", "http://127.0.0.1:{}".format(port))
        req.add_header("X-CSRF-Nonce", ShellAPIHandler.csrf.nonce)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_second_start_within_2s_returns_429(self):
        self._serve_with_fixture_module()
        first_status, _ = self._post_start()
        self.assertEqual(first_status, 200, "first Start should be accepted")
        second_status, body = self._post_start()
        self.assertEqual(second_status, 429, "second Start within 2s must be rate limited: " + body)
        self.assertLessEqual(START_RATE_LIMIT_S, 2.0)

    def test_fifth_concurrent_managed_process_refused(self):
        env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
               "PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}
        argv = [python_exe(), "-B", fixture("fixture_sleeper.py")]
        for i in range(4):
            pid_file = os.path.join(self.tmp, "s{}.pid".format(i))
            self.sup.spawn("m{}".format(i), argv + [pid_file], self.tmp, env)
        self.assertEqual(self.sup.process_count, 4)
        with self.assertRaises(SupervisorError) as ctx:
            self.sup.spawn("m4", argv + [os.path.join(self.tmp, "s4.pid")], self.tmp, env)
        self.assertIn("Max 4", str(ctx.exception))
        self.assertEqual(self.sup.process_count, 4)


class TestH9ShellExitOwnership(unittest.TestCase):
    """H-9: shell exit stops only Job-owned processes; EXTERNAL is never touched."""

    def test_shell_exit_leaves_external_fixture_alive(self):
        port = free_port()
        external = subprocess.Popen(
            [python_exe(), "-B", fixture("fixture_http.py"), "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            def up():
                try:
                    urllib.request.urlopen(
                        "http://127.0.0.1:{}/health".format(port), timeout=1)
                    return True
                except OSError:
                    return False
            self.assertTrue(wait_until(up, 15), "external fixture never came up")

            proc, shell_port, _nonce = start_shell()
            self.assertTrue(pid_alive(external.pid))
            stop_shell(proc)
            self.assertTrue(wait_until(lambda: proc.poll() is not None, 10))

            time.sleep(0.5)
            self.assertTrue(
                pid_alive(external.pid),
                "H-9 violated: shell exit killed a process it did not own")
        finally:
            if external.poll() is None:
                external.kill()
                external.wait(timeout=10)


class TestH10QuotaGuardLayer2(unittest.TestCase):
    """H-10 layer 2: the compiled env is asserted immediately before CreateProcessW."""

    def setUp(self):
        self.sup = JobSupervisor()
        self.original_create = sup_mod.kernel32.CreateProcessW
        self.calls = []

    def tearDown(self):
        sup_mod.kernel32.CreateProcessW = self.original_create
        try:
            self.sup.close()
        except Exception:
            pass

    def _compiled_sow(self):
        adapters = load_all_adapters()
        self.assertIn("sow", adapters)
        sow = adapters["sow"]
        self.assertNotIn("error", sow, "sow adapter must compile: {}".format(sow.get("reason")))
        return sow

    def test_layer1_static_guard_rejects_adapter_without_flag(self):
        """H-10 layer 1: a sow adapter lacking the flag is a CONFIG_ERROR at compile."""
        raw = json.load(open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "modules", "sow.json"), encoding="utf-8"))
        raw["launch"]["env_set"].pop("SOW_CONDUCTOR_AUTOLAUNCH", None)
        from shell.src.adapter import AdapterError
        with self.assertRaises(AdapterError) as ctx:
            compile_adapter(raw)
        self.assertIn("H-10", str(ctx.exception))

    def test_compiled_sow_records_quota_guard(self):
        sow = self._compiled_sow()
        self.assertEqual(sow["quota_guard"],
                         {"required": True, "autolaunch_value": "0"})

    def test_mutated_env_aborts_before_createprocess(self):
        """Mutate env_set AFTER compile; the spawn path must abort before CreateProcessW."""
        sow = self._compiled_sow()

        def spy(*args, **kwargs):
            self.calls.append(args)
            return 0
        sup_mod.kernel32.CreateProcessW = spy

        # Post-compile mutation: exactly the tamper H-10 layer 2 exists to catch.
        sow["launch"]["env_set"]["SOW_CONDUCTOR_AUTOLAUNCH"] = "1"

        env = build_env(sow)
        with self.assertRaises(QuotaGuardError):
            check_quota_guard("sow", env)
        self.assertEqual(self.calls, [],
                         "CreateProcessW must not be reached when the guard fails")

        runner = ModuleRunner("sow", sow, self.sup)
        display, err = runner.start()
        self.assertEqual(display, "FAILED(QUOTA_GUARD)", err)
        self.assertEqual(self.calls, [],
                         "CreateProcessW must not be reached via ModuleRunner.start either")

    def test_guard_passes_with_correct_value(self):
        sow = self._compiled_sow()
        env = build_env(sow)
        record = check_quota_guard("sow", env)
        self.assertEqual(record,
                         {"required": True, "autolaunch_value": "0",
                          "verified_before_spawn": True})


if __name__ == "__main__":
    unittest.main()
