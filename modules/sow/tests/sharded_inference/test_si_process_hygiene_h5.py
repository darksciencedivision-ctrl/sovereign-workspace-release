"""H5: stopping the llama.cpp supervisor leaves no orphans and no stale plan report.

Found in the 2026-09-28 audit: ``supervisor_service stop`` rebuilt the whole supervisor just to kill
it. The build needs the llama-server binary (when it was gone, the build raised, the kill was
silently skipped and ``stopped: true`` was reported with llama-server still running) and re-ran
the GPU/RAM planner against the VRAM the running model occupies, overwriting hybrid_plans.json
with "refused" plans that /v1/health (H2) would then report. Now the stop kills the owned process
TREE directly (router plus per-model servers), plans nothing, and removes the plan report.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product import supervisor_service as ss  # noqa: E402

STATE_ENV_KEYS = ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_WORKSPACE_STATE",
                  "SOVEREIGN_ROOT")

# A stand-in router: it starts one child (a per-model server) and prints the child's PID.
ROUTER = ("import subprocess, sys, time\n"
          "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
          "print(child.pid, flush=True)\n"
          "time.sleep(120)\n")


@pytest.fixture
def bare_root(monkeypatch, tmp_path):
    for key in STATE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    root = tmp_path / "install"
    root.mkdir()
    return root


def _gone(pid: int, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not ss.pid_alive(pid):
            return True
        time.sleep(0.2)
    return False


def test_h5_stop_kills_the_whole_tree_without_the_binary_and_plans_nothing(bare_root,
                                                                          monkeypatch):
    router = subprocess.Popen([sys.executable, "-c", ROUTER], stdout=subprocess.PIPE, text=True)
    child = int(router.stdout.readline())
    try:
        ss.write_state(bare_root, {
            "schema_version": ss.SCHEMA_VERSION, "pid": router.pid,
            "pid_create_filetime": ss.pid_create_filetime(router.pid),
            "process_started_at": "2026-09-28T00:00:00Z", "host": "127.0.0.1",
            "port": 17933, "base_url": "http://127.0.0.1:17933", "executable": "x",
            "work_dir": str(ss.service_dir(bare_root)), "detach": True,
        })
        plans = ss.service_dir(bare_root) / "hybrid_plans.json"
        plans.write_text(json.dumps({"qwen3:30b-a3b": {"applied": True, "context": 32768}}),
                         encoding="utf-8")
        # the binary is gone, and planning must not run at all during a stop
        monkeypatch.setattr(ss, "DEFAULT_EXE", bare_root / "missing" / "llama-server.exe")

        def no_planning(*args, **kwargs):
            raise AssertionError("stop must not re-plan the GPU/RAM split")

        monkeypatch.setattr(LW, "apply_hybrid_plans", no_planning)
        assert ss.cmd_status(bare_root)["pid_owned"] is True

        stopped = ss.cmd_stop(bare_root, disable_autostart=False)
        assert stopped["stopped"] is True and stopped["pid_owned"] is True
        assert _gone(router.pid), "the router was left running"
        assert _gone(child), "a per-model child was orphaned"
        assert not plans.exists(), "a stopped supervisor's plan report was left for health"
        assert not ss.state_path(bare_root).exists()
    finally:
        for pid in (router.pid, child):
            if ss.pid_alive(pid):
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                               check=False) if sys.platform == "win32" else None
        router.stdout.close()
        router.wait(timeout=10)


def test_h5_an_exited_process_is_not_alive_while_its_handle_is_open():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)  # exited; the Popen object still holds its handle
    assert ss.pid_alive(proc.pid) is False
    running = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert ss.pid_alive(running.pid) is True
    finally:
        running.kill()
        running.wait(timeout=10)
