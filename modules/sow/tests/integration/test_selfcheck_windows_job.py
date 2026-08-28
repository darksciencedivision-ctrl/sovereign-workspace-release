"""Windows Job Object ownership for packaged Electron self-checks (U157)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time

import pytest

from tests.host_prerequisites import NODE, WINDOWS, requires


REPO = Path(__file__).resolve().parents[2]
HOST = REPO / "apps" / "desktop" / "selfcheck" / "windows-job-host.py"


def _pid_exists(pid: int) -> bool:
    probe = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


@requires(WINDOWS, NODE)          # Windows Job Object packaged-self-check proof
def test_job_host_waits_for_a_detached_descendant_after_launcher_exit() -> None:
    """The adversarial U157 shape: root exits before the first external inventory."""
    script = (
        "const {spawn}=require('child_process');"
        "const c=spawn(process.execPath,['-e','setTimeout(()=>{},350)'],"
        "{detached:true,stdio:'ignore'});"
        "c.unref();console.log(JSON.stringify({child:c.pid}));"
    )
    started = time.monotonic()
    proc = subprocess.run(
        ["py", "-3.12", str(HOST), "--timeout-ms", "5000", "--", "node", "-e", script],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    elapsed = time.monotonic() - started

    assert proc.returncode == 0, proc.stderr
    child_pid = int(json.loads(proc.stdout.splitlines()[0])["child"])
    assert elapsed >= 0.25
    assert not _pid_exists(child_pid)


@requires(WINDOWS, NODE)          # Windows Job Object packaged-self-check proof
def test_job_host_timeout_reaps_a_detached_descendant() -> None:
    script = (
        "const {spawn}=require('child_process');"
        "const c=spawn(process.execPath,['-e','setTimeout(()=>{},60000)'],"
        "{detached:true,stdio:'ignore'});"
        "c.unref();console.log(JSON.stringify({child:c.pid}));"
    )
    proc = subprocess.run(
        ["py", "-3.12", str(HOST), "--timeout-ms", "250", "--", "node", "-e", script],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    child_pid = int(json.loads(proc.stdout.splitlines()[0])["child"])
    assert proc.returncode == 124, proc.stderr
    assert not _pid_exists(child_pid)
