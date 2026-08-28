"""R-01 cold-start proof (CP-M1 Band 2 / G13).

test_cold_start_starts_nothing boots a shell and asserts that the FIRST observed /api/state
contains no module in STARTING or READY - i.e. nothing was started by shell action at boot.

Two targets, selected by env COLDSTART_TARGET:
  "product"   (default) - the real shell via tests._harness.start_shell. Must PASS.
  "autostart"           - fixtures/fixture_autostart_server.py, which starts its module at
                          boot. The same assertion must FAIL there; capturing that failure is
                          the fails-before artifact for G13.
"""
import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

from shell.tests._harness import WORKSPACE, _child_env, free_port, python_exe, stop_shell
from shell.tests._harness import start_shell

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
FIXTURE_SERVER = os.path.join(FIXTURES, "fixture_autostart_server.py")
TARGET = os.environ.get("COLDSTART_TARGET", "product")


def _first_state(base, timeout_s=15.0):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/state", timeout=3) as r:
                return json.loads(r.read().decode("utf-8")), None
        except Exception as e:
            last = e
            time.sleep(0.2)
    return None, last


class TestColdStart(unittest.TestCase):
    def test_cold_start_starts_nothing(self):
        if TARGET == "autostart":
            port = free_port()
            proc = subprocess.Popen(
                [python_exe(), "-B", FIXTURE_SERVER, "--port", str(port)],
                cwd=WORKSPACE, env=_child_env(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            base = "http://127.0.0.1:%d" % port
            try:
                deadline = time.time() + 10
                ready = False
                while time.time() < deadline:
                    line = proc.stdout.readline()
                    if "FIXTURE READY" in line:
                        ready = True
                        break
                    if proc.poll() is not None:
                        break
                self.assertTrue(ready, "autostart fixture did not become ready")
                state, err = _first_state(base)
            finally:
                pass
            self.assertIsNone(err, "state poll failed: %r" % err)
            started = sorted(
                mid for mid, rec in state["modules"].items()
                if rec.get("state") in ("STARTING", "READY"))
            proc.terminate()
            self.assertEqual(started, [],
                             "modules started by shell action at boot: %s" % started)
        else:
            proc, port, nonce = start_shell()
            base = "http://127.0.0.1:%d" % port
            try:
                state, err = _first_state(base)
                self.assertIsNone(err, "state poll failed: %r" % err)
                started = sorted(
                    mid for mid, rec in state["modules"].items()
                    if rec.get("state") in ("STARTING", "READY"))
                self.assertEqual(started, [],
                                 "modules started by shell action at boot: %s" % started)
            finally:
                stop_shell(proc)


if __name__ == "__main__":
    unittest.main()