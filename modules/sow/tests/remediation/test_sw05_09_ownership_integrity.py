"""SW-05..SW-09 — GPU-lock ownership, process identity, and model integrity (system-review 2026-09-22).

Failure-injection tests written alongside the fixes; there were none before. Each pins the bug the
review found:
  SW-05 two threads must not both enter one GPU transition lock,
  SW-06 a timed-out contender must not delete a foreign lock,
  SW-07 a failed supervisor build must release the GPU claim,
  SW-08 a stale/reused PID must not be adopted as running nor terminated,
  SW-09 a present blob whose bytes do not match the digest must not be "verified".
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import gpu_occupancy as gpu  # noqa: E402
from sovereign_product import supervisor_service as ss  # noqa: E402
from sovereign_product import runtime_registry as rr  # noqa: E402


# -- SW-05 -----------------------------------------------------------------
def test_sw05_two_threads_never_overlap_in_one_transition_lock(tmp_path):
    inside = {"now": 0, "max": 0}
    guard = threading.Lock()
    start = threading.Barrier(2)

    def worker():
        start.wait()
        with gpu.transition_lock(tmp_path, "llama.cpp"):
            with guard:
                inside["now"] += 1
                inside["max"] = max(inside["max"], inside["now"])
            time.sleep(0.2)
            with guard:
                inside["now"] -= 1

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert inside["max"] == 1, "two threads held the GPU transition lock at once"


def test_sw05_same_thread_is_still_reentrant(tmp_path):
    with gpu.transition_lock(tmp_path, "llama.cpp"):
        with gpu.transition_lock(tmp_path, "llama.cpp"):  # nested claim on the same thread
            pass  # must not deadlock


# -- SW-06 -----------------------------------------------------------------
def test_sw06_timed_out_contender_does_not_delete_a_foreign_lock(tmp_path, monkeypatch):
    lock = gpu.lock_path(tmp_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text('{"owner": "someone-else", "token": "FOREIGN"}', encoding="utf-8")
    monkeypatch.setattr(gpu, "LOCK_WAIT_SECONDS", 0.0)     # zero budget -> immediate timeout
    monkeypatch.setattr(gpu, "LOCK_STALE_SECONDS", 1e9)    # never treat the foreign lock as stale

    with pytest.raises(gpu.RuntimeControlError):
        with gpu.transition_lock(tmp_path, "llama.cpp"):
            pass
    assert lock.is_file(), "a timed-out contender deleted the foreign lock"
    assert "FOREIGN" in lock.read_text(encoding="utf-8"), "the foreign lock was overwritten"


# -- SW-07 -----------------------------------------------------------------
def test_sw07_failed_supervisor_build_releases_the_gpu_claim(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise ss.RuntimeControlError("llama.cpp server binary not found")

    monkeypatch.setattr(ss, "build_supervisor", boom)
    # a free high port so the pre-build port check passes
    with pytest.raises(ss.RuntimeControlError):
        ss.cmd_start(tmp_path, port=17931)
    assert gpu.gpu_owner(tmp_path) is None, "GPU claim leaked after a failed supervisor build"


# -- SW-08 -----------------------------------------------------------------
def _spawn_benign() -> "tuple[int, object]":
    import subprocess
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    time.sleep(0.3)
    return proc.pid, proc


def test_sw08_stale_pid_is_not_adopted_or_terminated(tmp_path):
    pid, proc = _spawn_benign()
    try:
        # State claims this benign PID is our supervisor, but with a WRONG creation-time token.
        ss.write_state(tmp_path, {
            "schema_version": ss.SCHEMA_VERSION, "pid": pid,
            "pid_create_filetime": 1,  # cannot match the benign process's real creation time
            "process_started_at": "2000-01-01T00:00:00Z",
            "host": "127.0.0.1", "port": 17932, "base_url": "http://127.0.0.1:17932",
            "executable": "x", "work_dir": str(tmp_path), "detach": True,
        })
        status = ss.cmd_status(tmp_path)
        assert status["pid_alive"] is True
        assert status["pid_owned"] is False and status["running"] is False, \
            "a live but unowned PID was reported as our running runtime"

        stopped = ss.cmd_stop(tmp_path, disable_autostart=False)
        assert stopped["stopped"] is False and stopped["pid_owned"] is False
        assert ss.pid_alive(pid), "cmd_stop terminated an unrelated process from stale PID state"
    finally:
        proc.terminate()


# -- SW-09 -----------------------------------------------------------------
def test_sw09_present_blob_with_wrong_bytes_is_not_verified(tmp_path, monkeypatch):
    bad = tmp_path / "blob"
    bad.write_bytes(b"these are not the model weights")
    monkeypatch.setattr(rr, "blob_path", lambda digest: bad)  # every declared blob -> wrong bytes

    registry = rr.build_production_registry()
    artifacts = list(registry.artifacts.values()) if hasattr(registry, "artifacts") else []
    if not artifacts:  # registry shape guard: pull from the public accessor if present
        artifacts = [registry.artifact(a) for a in getattr(registry, "artifact_ids", lambda: [])()]
    assert artifacts, "no artifacts built"
    for art in artifacts:
        assert art.integrity != "verified", f"{art.identity} verified on wrong bytes"
        assert art.verified_hash is None, f"{art.identity} carries a verified_hash on wrong bytes"
