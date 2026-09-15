"""CR-006 (normal shutdown must attempt graceful termination), CR-007 (dead entries reaped),
CR-010 (log-sink failure must not stop pipe draining) — shell Windows Job supervisor.

Windows-only: exercises the real supervisor against real child processes.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

if sys.platform != "win32":
    pytest.skip("supervisor is Windows-only", allow_module_level=True)

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SHELL_SRC = RELEASE_ROOT / "shell" / "src"
if str(SHELL_SRC) not in sys.path:
    sys.path.insert(0, str(SHELL_SRC))

import supervisor  # noqa: E402


def _spawn(sup, mid, code, tmp_path, log_ring=None):
    return sup.spawn(mid, [sys.executable, "-c", code], str(tmp_path), dict(os.environ),
                     log_ring=log_ring)


def _wait_dead(ph, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if not ph.is_alive():
            return True
        time.sleep(0.02)
    return False


# -- CR-007 ----------------------------------------------------------------
def test_cr007_dead_entries_reaped_and_do_not_exhaust_max(tmp_path):
    sup = supervisor.JobSupervisor(max_processes=2)
    try:
        a = _spawn(sup, "a", "import sys; sys.exit(0)", tmp_path)
        b = _spawn(sup, "b", "import sys; sys.exit(0)", tmp_path)
        assert _wait_dead(a) and _wait_dead(b)
        # Two DEAD entries still occupy the dict. Before the fix, admission counted them and this
        # spawn failed with "Max 2 managed processes reached". Now they are reaped first.
        c = _spawn(sup, "c", "import time; time.sleep(5)", tmp_path)
        assert c.is_alive()
        assert "a" not in sup.get_pids() and "b" not in sup.get_pids()
        assert sup.process_count == 1
    finally:
        sup.close()


def test_cr007_respawn_same_module_after_death_is_allowed(tmp_path):
    sup = supervisor.JobSupervisor(max_processes=2)
    try:
        a1 = _spawn(sup, "a", "import sys; sys.exit(0)", tmp_path)
        assert _wait_dead(a1)
        a2 = _spawn(sup, "a", "import time; time.sleep(5)", tmp_path)  # must not be blocked
        assert a2.is_alive() and a2.pid != a1.pid
    finally:
        sup.close()


# -- CR-006 ----------------------------------------------------------------
_COOP_CHILD = """
import sys, os, threading
sys.path.insert(0, r"{shell_src}")
import graceful
done = threading.Event()
graceful.install_shutdown_watcher(done.set)
sys.exit(0 if done.wait(30) else 3)
"""


def test_cr006_stop_all_gracefully_stops_a_cooperating_module(tmp_path):
    sup = supervisor.JobSupervisor(max_processes=2)
    try:
        ph = _spawn(sup, "coop", _COOP_CHILD.format(shell_src=str(SHELL_SRC)), tmp_path)
        # let the child install its watcher
        time.sleep(1.0)
        assert ph.is_alive()
        records = sup.stop_all(total_grace_s=10)
        rec = next(r for r in records if r["module_id"] == "coop")
        assert rec["graceful"] is True and rec["forced"] is False
        assert rec["exit_code"] == 0  # exited itself, not TerminateJobObject's code 1
    finally:
        sup.close()


def test_cr006_stop_all_forces_a_noncooperating_module(tmp_path):
    sup = supervisor.JobSupervisor(max_processes=2)
    try:
        # No shutdown watcher: ignores the event and CTRL_BREAK; only force can stop it.
        ph = _spawn(sup, "stubborn", "import time; time.sleep(60)", tmp_path)
        time.sleep(0.3)
        records = sup.stop_all(total_grace_s=1)
        rec = next(r for r in records if r["module_id"] == "stubborn")
        assert rec["forced"] is True
        assert not ph.is_alive()
    finally:
        sup.close()


# -- CR-010 ----------------------------------------------------------------
# -- CR-008 ----------------------------------------------------------------
def test_cr008_handle_list_failure_fails_closed(tmp_path, monkeypatch):
    sup = supervisor.JobSupervisor(max_processes=2)
    try:
        # Simulate the explicit handle-inheritance list failing to install. The old code fell back
        # to a plain STARTUPINFO with bInheritHandles still TRUE (broadened inheritance); the fix
        # refuses the launch instead.
        monkeypatch.setattr(supervisor.kernel32, "UpdateProcThreadAttribute",
                            lambda *a, **k: 0)
        with pytest.raises(supervisor.SupervisorError):
            _spawn(sup, "x", "import time; time.sleep(5)", tmp_path)
        assert sup.process_count == 0 and "x" not in sup.get_pids()
        # supervisor state is intact: a normal spawn still works after the refusal
        monkeypatch.undo()
        ok = _spawn(sup, "ok", "import time; time.sleep(5)", tmp_path)
        assert ok.is_alive()
    finally:
        sup.close()


# -- CR-009 ----------------------------------------------------------------
def test_cr009_resume_thread_failure_fails_closed(tmp_path, monkeypatch):
    sup = supervisor.JobSupervisor(max_processes=2)
    try:
        monkeypatch.setattr(supervisor.kernel32, "ResumeThread", lambda *a, **k: 0xFFFFFFFF)
        with pytest.raises(supervisor.SupervisorError):
            _spawn(sup, "y", "import time; time.sleep(5)", tmp_path)
        assert sup.process_count == 0 and "y" not in sup.get_pids()
    finally:
        sup.close()


class _ThrowingRing:
    """A LogRing whose sink always fails. The pump must keep draining the pipe regardless."""
    def __init__(self):
        self.writes = 0

    def write(self, _data):
        self.writes += 1
        raise RuntimeError("sink down")

    def flush(self):
        raise RuntimeError("sink down")


def test_cr010_child_keeps_draining_when_log_sink_fails(tmp_path):
    sup = supervisor.JobSupervisor(max_processes=2)
    ring = _ThrowingRing()
    try:
        # ~2 MB of output, far beyond the OS pipe buffer (~64 KB). If draining stopped when the
        # sink raised, the child would block on a full pipe and never exit.
        code = "import sys\nfor _ in range(2000): sys.stdout.write('x'*1000+'\\n')\nsys.exit(0)"
        ph = _spawn(sup, "chatty", code, tmp_path, log_ring=ring)
        assert _wait_dead(ph, timeout=15.0), "child blocked on a full pipe (draining stopped)"
        assert ph.exit_code == 0
        # let the pump record the sink failures before we assert health
        time.sleep(0.3)
        health = sup.log_health("chatty")
        assert health["degraded"] is True and health["sink_errors"] >= 1
        assert ring.writes >= 1
    finally:
        sup.close()
