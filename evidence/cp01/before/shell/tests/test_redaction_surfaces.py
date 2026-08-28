"""
H-8 four-surface sentinel test (R3-7, §7.6.1).

fixture_noisy.py emits the sentinel in every supported form. After it exits, the sentinel must be
absent from ALL FOUR surfaces:
  1. the /api/logs/<id> response
  2. the in-memory ring buffer object
  3. the startup-test JSON record
  4. every file under evidence/ modified during the test

The shell is driven through its real HTTP surface with the real handler, using a fixture module.
No real module is launched (directive section 0.1(4)).
"""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from shell.src.logring import LogRing
from shell.src.server import ShellAPIHandler
from shell.src.states import ModuleRunner
from shell.src.supervisor import JobSupervisor
from shell.tests._harness import WORKSPACE, fixture, free_port, python_exe, wait_until

SENTINEL = "SWS_SENTINEL_7f3a9c"
EVIDENCE = os.path.join(WORKSPACE, "evidence")


def snapshot_evidence(*roots):
    """{path: mtime_ns} for every file under each evidence root.

    Surface 4 covers BOTH the workspace evidence tree and the temp evidence root the tests
    redirect startup records into (G4-2). Watching only the workspace tree would make the
    assertion vacuous once the record moved.
    """
    out = {}
    for root in (roots or (EVIDENCE,)):
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                p = os.path.join(dirpath, name)
                try:
                    out[p] = os.stat(p).st_mtime_ns
                except OSError:
                    pass
    return out


class TestRedactionFourSurfaces(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sws-h8-")
        # G4-2: fixture startup records go to a temp evidence root so synthetic output never
        # lands in the operator's evidence/startup-tests/.
        self.evidence_root = os.path.join(self.tmp, "evidence")
        os.makedirs(os.path.join(self.evidence_root, "startup-tests"), exist_ok=True)
        self._prev_root = os.environ.get("SWS_EVIDENCE_ROOT")
        os.environ["SWS_EVIDENCE_ROOT"] = self.evidence_root
        self.sup = JobSupervisor()
        self.ring = LogRing()
        self.server = None

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        try:
            self.sup.close()
        except Exception:
            pass
        if self._prev_root is None:
            os.environ.pop("SWS_EVIDENCE_ROOT", None)
        else:
            os.environ["SWS_EVIDENCE_ROOT"] = self._prev_root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _adapter(self):
        return {
            "id": "noisy",
            "display_name": "Noisy fixture",
            "description": "H-8 sentinel emitter",
            "state_class": "runnable",
            "root": self.tmp,
            "runtime_writes": [],
            "launch": {
                "cwd": self.tmp,
                "argv": [python_exe(), "-B", fixture("fixture_noisy.py")],
                "env_allowlist": ["SYSTEMROOT", "PATH", "TEMP", "TMP"],
                "env_set": {"PYTHONDONTWRITEBYTECODE": "1"},
            },
            # The fixture prints and exits, so process_window readiness resolves to
            # FAILED(EXIT) quickly. The record and the logs are what this test is about.
            "readiness": {"kind": "process_window", "timeout_s": 5, "poll_ms": 250},
            "identity": {"kind": "process_image", "expected_image": python_exe()},
            "open": {"kind": "none"},
            "stop": {"kind": "job_object", "grace_s": 1},
            "_adapter_hash": "0" * 64,
        }

    def test_sentinel_absent_from_all_four_surfaces(self):
        adapter = self._adapter()
        runner = ModuleRunner("noisy", adapter, self.sup, self.ring)

        ShellAPIHandler.supervisor = self.sup
        ShellAPIHandler.adapters = {"noisy": adapter}
        ShellAPIHandler.states = {"noisy": runner}
        ShellAPIHandler.log_rings = {"noisy": self.ring}
        ShellAPIHandler.selftest = False
        self.server = ThreadingHTTPServer(("127.0.0.1", free_port()), ShellAPIHandler)
        port = self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        before = snapshot_evidence(EVIDENCE, self.evidence_root)
        t_start = time.time()

        data = json.dumps({"id": "noisy"}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:{}/api/startup-test".format(port), data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Origin", "http://127.0.0.1:{}".format(port))
        req.add_header("X-CSRF-Nonce", ShellAPIHandler.csrf.nonce)
        with urllib.request.urlopen(req, timeout=60) as resp:
            record = json.loads(resp.read().decode())

        # The fixture really did run and really did emit.
        self.assertTrue(
            wait_until(lambda: "fixture_noisy done" in self.ring.read(), 15),
            "fixture output never reached the ring buffer; the test would be vacuous")

        # ---- surface 2: the ring buffer object -----------------------------
        ring_text = self.ring.read()
        self.assertNotIn(SENTINEL, ring_text, "SURFACE 2 (ring buffer) leaked the sentinel")
        self.assertGreaterEqual(
            ring_text.count("[REDACTED]"), 10,
            "expected at least 10 redactions in the ring, got {}".format(
                ring_text.count("[REDACTED]")))

        # ---- surface 1: the /api/logs/<id> response -------------------------
        with urllib.request.urlopen(
                "http://127.0.0.1:{}/api/logs/noisy".format(port), timeout=15) as resp:
            api_body = resp.read().decode()
        self.assertNotIn(SENTINEL, api_body, "SURFACE 1 (/api/logs) leaked the sentinel")
        self.assertGreaterEqual(api_body.count("[REDACTED]"), 10)

        # ---- surface 3: the startup-test JSON record ------------------------
        self.assertNotIn(SENTINEL, json.dumps(record),
                         "SURFACE 3 (startup-test response) leaked the sentinel")
        record_path = record.get("_record_path")
        self.assertTrue(record_path and os.path.isfile(record_path),
                        "startup-test record was not written: {}".format(record_path))
        with open(record_path, "r", encoding="utf-8") as f:
            record_text = f.read()
        self.assertNotIn(SENTINEL, record_text,
                         "SURFACE 3 (startup-test JSON on disk) leaked the sentinel")
        self.assertGreaterEqual(
            record_text.count("[REDACTED]"), 10,
            "the persisted record should contain the redacted log lines")

        # ---- surface 4: every evidence/ file modified during the test -------
        after = snapshot_evidence(EVIDENCE, self.evidence_root)
        touched = [p for p, m in after.items()
                   if p not in before or before[p] != m]
        self.assertTrue(touched, "no evidence file was written; surface 4 would be vacuous")
        leaked = []
        for p in touched:
            try:
                with open(p, "rb") as f:
                    if SENTINEL.encode() in f.read():
                        leaked.append(p)
            except OSError:
                pass
        self.assertEqual(leaked, [],
                         "SURFACE 4 (evidence files) leaked the sentinel: {}".format(leaked))
        self.assertGreater(time.time() - t_start, 0)

        # Control assertions: the noise really was in the stream and really was neutralised.
        self.assertNotIn("\x1b[", ring_text, "ANSI CSI sequences must be stripped")
        self.assertNotIn("\x00", ring_text, "NUL bytes must be removed")
        self.assertIn("after-nul", ring_text, "content around the NUL must survive")

    def test_long_line_is_bounded(self):
        """The 10 KB line must be truncated to the 4 KB per-line cap (§7.3 item 4)."""
        ring = LogRing()
        ring.write(b"Y" * 10240 + b"\n")
        for line in ring.read().split("\n"):
            self.assertLessEqual(len(line), 4096 + 3, "line exceeded the 4 KB cap")


if __name__ == "__main__":
    unittest.main()
