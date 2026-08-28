"""G17 failure-vocabulary tests (CP-M1 Band 2).

test_failure_classes          - the ten classes are separately distinguishable through the
                                runner's classification path (unit-level inductions).
test_port_conflict_is_its_own_class - a foreign owner on the readiness port yields
                                FAILED(PORT_UNAVAILABLE ...) naming the owning pid, never
                                TIMEOUT.

Both fail against the pre-G17 product (no pre-check, legacy reasons); artifacts captured
under evidence/cpm1/8b/.
"""
import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.request

from shell.src.states import ModuleRunner
from shell.src.supervisor import JobSupervisor
from shell.src.logring import LogRing

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(WORKSPACE, "shell", "tests", "fixtures")

TEN = ["PROCESS_START_FAILED", "PORT_UNAVAILABLE", "HEALTH_CHECK_FAILED", "IDENTITY_MISMATCH",
       "MODEL_UNAVAILABLE", "PROVIDER_UNAVAILABLE", "OPENCODE_UNAVAILABLE",
       "CONFIGURATION_FAILED", "WORKER_FAILED", "CONDUCTOR_COMMUNICATION_FAILED"]


def make_runner(adapter):
    sup = JobSupervisor()
    ring = LogRing()
    return ModuleRunner(adapter["id"], adapter, sup, ring)


def http_adapter(port, identity="ok", unready=False):
    fx = os.path.join(FIXTURES, "fixture_http.py")
    args = [sys.executable, "-B", fx, "--port", str(port), "--identity", identity]
    if unready:
        args.append("--unready")
    return {
        "id": "fx", "display_name": "Fixture", "description": "", "state_class": "runnable",
        "root": FIXTURES, "runtime_writes": [],
        "launch": {"cwd": FIXTURES, "argv": args,
                   "env_allowlist": ["SYSTEMROOT", "PATH", "TEMP", "TMP"],
                   "env_set": {"PYTHONDONTWRITEBYTECODE": "1"}},
        "readiness": {"kind": "http", "url": "http://127.0.0.1:%d/" % port,
                      "expect_status": 200, "timeout_s": 5, "poll_ms": 250},
        "identity": {"kind": "http_html_marker", "url": "http://127.0.0.1:%d/" % port,
                     "html_marker": "Debate Table"},
        "open": {"kind": "none"}, "stop": {"kind": "job_object", "grace_s": 2},
    }


def wait_fx_ready(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/health" % port, timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


class TestFailureClasses(unittest.TestCase):
    def test_failure_classes(self):
        # (1) every legacy reason maps onto exactly one of the ten classes
        from shell.src import states as st
        legacy = {"SPAWN": "PROCESS_START_FAILED", "JOB_ASSIGN": "PROCESS_START_FAILED",
                  "EXIT": "PROCESS_START_FAILED", "TIMEOUT": "HEALTH_CHECK_FAILED",
                  "IDENTITY": "IDENTITY_MISMATCH", "QUOTA_GUARD": "CONFIGURATION_FAILED"}
        for reason, want in legacy.items():
            self.assertEqual(st.classify_failure(reason), want)
        for cls in TEN:
            self.assertEqual(st.classify_failure(cls), cls)
        self.assertEqual(set(st.FAILURE_CLASSES), set(TEN))

        # (2) PROCESS_START_FAILED: argv[0] does not exist -> spawn fails -> classified
        ad = http_adapter(0)
        ad["id"] = "fxdead"
        ad["launch"]["argv"] = [os.path.join(FIXTURES, "does_not_exist.exe")]
        ad.pop("readiness"), ad.pop("identity")
        r = make_runner(ad)
        disp, err = r.start()
        self.assertIn("PROCESS_START_FAILED", disp, err)

        # (3) HEALTH_CHECK_FAILED: readiness endpoint stays unready -> not TIMEOUT
        dead = socket.socket(); dead.bind(("127.0.0.1", 0)); dp = dead.getsockname()[1]; dead.close()
        s2 = socket.socket(); s2.bind(("127.0.0.1", 0)); hp = s2.getsockname()[1]; s2.close()
        fx = subprocess.Popen(
            [sys.executable, "-B", os.path.join(FIXTURES, "fixture_http.py"),
             "--port", str(hp), "--identity", "ok"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_fx_ready(hp):
            raise AssertionError("fixture did not become ready")
        try:
            ad2 = http_adapter(hp)
            # readiness/identity point at a port nothing listens on: process stays
            # alive but the health probe keeps failing -> HEALTH_CHECK_FAILED.
            ad2["readiness"]["url"] = "http://127.0.0.1:%d/" % dp
            ad2["identity"]["url"] = "http://127.0.0.1:%d/" % dp
            r2 = make_runner(ad2)
            disp2, err2 = r2.start()
            self.assertIn("HEALTH_CHECK_FAILED", disp2, err2 or repr(disp2))
            self.assertNotIn("TIMEOUT", disp2)
        finally:
            fx.terminate()

    def test_port_conflict_is_its_own_class(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            r = make_runner(http_adapter(port))
            disp, err = r.start()
            self.assertIn("PORT_UNAVAILABLE", disp, err)
            self.assertNotIn("TIMEOUT", disp)
            digits = "".join(ch for ch in disp.split("pid")[-1] if ch.isdigit())
            self.assertTrue(digits, "owning pid missing from reason: %s" % disp)
        finally:
            s.close()


import subprocess  # noqa: E402  (used by HEALTH_CHECK induction above)

if __name__ == "__main__":
    unittest.main()