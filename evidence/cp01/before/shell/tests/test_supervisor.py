"""
H-6 — Windows Job Object containment (R3-4).

Four proofs:
  1. Stop kills the whole tree: root, child and grandchild.
  2. A hard shell crash (os._exit) kills the whole tree via KILL_ON_JOB_CLOSE.
  3. A grandchild that passes CREATE_BREAKAWAY_FROM_JOB stays inside the Job (IsProcessInJob).
  4. A failing AssignProcessToJobObject terminates the process and surfaces JOB_ASSIGN.
"""
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from shell.src import supervisor as sup_mod
from shell.src.states import ModuleRunner
from shell.src.supervisor import JobSupervisor, SupervisorError, pid_in_job
from shell.tests._harness import WORKSPACE, fixture, pid_alive, python_exe, wait_until

GRACE_S = 2


def _env():
    return {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


class TestJobObjectContainment(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sws-h6-")
        self.root_pid_file = os.path.join(self.tmp, "root.pid")
        self.child_pid_file = os.path.join(self.tmp, "child.pid")
        self.grand_pid_file = os.path.join(self.tmp, "grand.pid")
        self.sup = None

    def tearDown(self):
        if self.sup is not None:
            try:
                self.sup.close()
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read_pid(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip())

    def _spawn_tree(self):
        self.sup = JobSupervisor()
        argv = [python_exe(), "-B", fixture("fixture_tree.py"),
                self.root_pid_file, self.child_pid_file, self.grand_pid_file]
        ph = self.sup.spawn("tree", argv, os.path.dirname(fixture("fixture_tree.py")), _env())
        ok = wait_until(
            lambda: all(os.path.isfile(p) and os.path.getsize(p) > 0
                        for p in (self.root_pid_file, self.child_pid_file, self.grand_pid_file)),
            30)
        self.assertTrue(ok, "fixture tree did not report all three PIDs within 30s")
        pids = (self._read_pid(self.root_pid_file),
                self._read_pid(self.child_pid_file),
                self._read_pid(self.grand_pid_file))
        return ph, pids

    def test_stop_kills_child_and_grandchild(self):
        ph, pids = self._spawn_tree()
        for pid in pids:
            self.assertTrue(pid_alive(pid), "PID {} should be alive before stop".format(pid))

        t0 = time.time()
        self.sup.stop("tree", grace_s=GRACE_S)
        deadline = GRACE_S + 2
        ok = wait_until(lambda: not any(pid_alive(p) for p in pids), deadline)
        elapsed = time.time() - t0
        for pid in pids:
            self.assertFalse(pid_alive(pid),
                             "PID {} still alive {:.1f}s after stop".format(pid, elapsed))
        self.assertTrue(ok)

    def test_grandchild_breakaway_fails(self):
        """CREATE_BREAKAWAY_FROM_JOB must not let the grandchild escape the Job."""
        ph, pids = self._spawn_tree()
        grand = pids[2]
        self.assertTrue(pid_alive(grand))
        self.assertTrue(
            pid_in_job(grand, ph.job_handle),
            "grandchild {} escaped the per-module Job - breakaway succeeded".format(grand))
        self.assertTrue(
            pid_in_job(grand, self.sup.shell_job),
            "grandchild {} escaped the shell Job".format(grand))

    def test_shell_crash_kills_tree(self):
        """os._exit in the shell process must still take the whole tree down."""
        proc = subprocess.Popen(
            [python_exe(), "-B", fixture("crash_driver.py"),
             self.root_pid_file, self.child_pid_file, self.grand_pid_file],
            cwd=WORKSPACE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ok = wait_until(
            lambda: all(os.path.isfile(p) and os.path.getsize(p) > 0
                        for p in (self.root_pid_file, self.child_pid_file, self.grand_pid_file)),
            30)
        self.assertTrue(ok, "crash driver did not bring the tree up")
        pids = (self._read_pid(self.root_pid_file),
                self._read_pid(self.child_pid_file),
                self._read_pid(self.grand_pid_file))

        proc.wait(timeout=30)
        if proc.stdout is not None:
            proc.stdout.close()
        self.assertEqual(proc.returncode, 1, "driver should have exited via os._exit(1)")

        ok = wait_until(lambda: not any(pid_alive(p) for p in pids), 5)
        survivors = [p for p in pids if pid_alive(p)]
        # Never leave orphans behind if the assertion is about to fail.
        for p in survivors:
            subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
        self.assertEqual(survivors, [], "PIDs survived the shell crash: {}".format(survivors))
        self.assertTrue(ok)


class TestJobAssignFailure(unittest.TestCase):
    """H-6 / §7.4: assignment failure terminates the process and reports JOB_ASSIGN."""

    def setUp(self):
        self.sup = JobSupervisor()
        self.original = sup_mod.kernel32.AssignProcessToJobObject

    def tearDown(self):
        sup_mod.kernel32.AssignProcessToJobObject = self.original
        try:
            self.sup.close()
        except Exception:
            pass

    def _adapter(self):
        return {
            "id": "fix",
            "display_name": "Fixture",
            "description": "d",
            "state_class": "runnable",
            "root": WORKSPACE,
            "launch": {"cwd": WORKSPACE, "argv": [python_exe(), "-c", "import time;time.sleep(60)"],
                       "env_allowlist": ["SYSTEMROOT", "PATH"], "env_set": {}},
            "readiness": {"kind": "process_window", "timeout_s": 5, "poll_ms": 250},
            "identity": {"kind": "process_image", "expected_image": python_exe()},
            "open": {"kind": "none"},
            "stop": {"kind": "job_object", "grace_s": 1},
        }

    def test_spawn_raises_job_assign(self):
        sup_mod.kernel32.AssignProcessToJobObject = lambda job, proc: 0
        with self.assertRaises(SupervisorError) as ctx:
            self.sup.spawn("fix", [python_exe(), "-c", "import time;time.sleep(60)"],
                           WORKSPACE, _env())
        self.assertIn("JOB_ASSIGN", str(ctx.exception))
        self.assertEqual(self.sup.process_count, 0,
                         "a process that failed assignment must not be tracked")

    def test_runner_state_is_failed_job_assign(self):
        sup_mod.kernel32.AssignProcessToJobObject = lambda job, proc: 0
        runner = ModuleRunner("fix", self._adapter(), self.sup)
        display, err = runner.start()
        self.assertEqual(display, "FAILED(JOB_ASSIGN)", err)


if __name__ == "__main__":
    unittest.main()
