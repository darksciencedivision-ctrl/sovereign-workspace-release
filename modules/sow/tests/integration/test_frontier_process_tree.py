"""Windows process-tree regression for the live Node-based frontier CLI boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from tests.host_prerequisites import NODE, WINDOWS, WSL, requires

from adapters.frontier.process_tree import run_managed_process


REPO = Path(__file__).resolve().parents[2]


def _pid_exists(pid: int) -> bool:
    probe = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
        capture_output=True, text=True, check=False)
    return probe.returncode == 0


@requires(WINDOWS, NODE)          # Windows Node process-tree proof
def test_ten_managed_live_cli_runs_track_and_reap_every_detached_node_descendant() -> None:
    script = (
        "const {spawn}=require('child_process');"
        "const c=spawn(process.execPath,['-e','setTimeout(()=>{},60000)'],"
        "{detached:true,stdio:'ignore'});"
        "c.unref();console.log(JSON.stringify({child:c.pid}));"
    )
    for _iteration in range(10):
        result = run_managed_process(
            ["node", "-e", script], timeout=10.0, env=dict(os.environ), stdin=subprocess.DEVNULL)
        child_pid = int(json.loads(result.stdout)["child"])

        assert result.returncode == 0
        assert child_pid in result.spawned_pids
        assert all(not _pid_exists(pid) for pid in result.spawned_pids)


def test_windows_runner_gates_the_target_until_after_job_assignment() -> None:
    """U158: assignment-after-spawn is structurally forbidden, not merely unlikely."""
    source = (REPO / "adapters" / "frontier" / "process_tree.py").read_text(encoding="utf-8")
    assert "_JOB_MEMBER_FLAG" in source
    assert "member_cmd" in source
    assert '"GO\\n" + (input_text or "")' in source
    assert source.index("job.assign(proc)") < source.index('"GO\\n" + (input_text or "")')
    assert "subprocess.Popen(\n            cmd," not in source


@requires(WINDOWS)                # Windows gated-member stdin proof
def test_windows_job_gate_preserves_supported_ascii_lf_text_for_the_target() -> None:
    """The WSL program seam is text-mode: pin its supported ASCII/LF payload, not arbitrary bytes."""
    payload = "PAYLOAD-123\nSECOND\n"
    result = run_managed_process(
        [
            sys.executable,
            "-c",
            "import json,sys; print(json.dumps(sys.stdin.read()))",
        ],
        timeout=10,
        env=dict(os.environ),
        stdin=subprocess.PIPE,
        input_text=payload,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == payload


def _marked_wsl_exists(marker: str) -> bool:
    probe = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "if (Get-CimInstance Win32_Process | "
                f"Where-Object {{ $_.Name -eq 'wsl.exe' -and $_.CommandLine -like '*{marker}*' }}) "
                "{ exit 0 } else { exit 1 }"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


@requires(WINDOWS, WSL)           # Windows outer-emitter-kill WSL process-tree proof
def test_killing_the_python_emitter_closes_its_job_and_reaps_wsl() -> None:
    """U158 quit path: killing py.exe must synchronously remove its owned wsl.exe."""
    marker = f"sow-u158-outer-kill-{uuid.uuid4().hex}"
    emitter_source = (
        "import os, subprocess;"
        "from adapters.frontier.process_tree import run_managed_process;"
        "run_managed_process("
        f"['wsl.exe','--','bash','-c','sleep 60 # {marker}'],"
        "timeout=60,env=dict(os.environ),stdin=subprocess.DEVNULL)"
    )
    emitter = subprocess.Popen(
        [sys.executable, "-c", emitter_source],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not _marked_wsl_exists(marker):
            time.sleep(0.05)
        assert _marked_wsl_exists(marker), "managed WSL child never became observable"

        emitter.kill()
        emitter.wait(timeout=5)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _marked_wsl_exists(marker):
            time.sleep(0.05)
        assert not _marked_wsl_exists(marker)
    finally:
        if emitter.poll() is None:
            emitter.kill()
            emitter.wait(timeout=5)


# ---- W-03 / A-2: the provider transcript is decoded, not guessed at ------------------------------
# `text=True` with no `encoding=` resolves to the host ANSI codepage (cp1252 here). An undefined
# byte kills subprocess's reader THREAD, and subprocess swallows that exception -- so the call
# returns exit 0 with the transcript GONE. Reproduced on this host before the repair: the plain
# `subprocess.run` shape yields `stdout=None`, and this managed boundary coerces the same loss to
# `""`, which is quieter rather than safer.


@requires(WINDOWS)                # Windows ANSI-codepage decode proof
def test_a_byte_undefined_in_the_ansi_codepage_never_empties_provider_output() -> None:
    child = ("import sys;sys.stdout.buffer.write(b'ok-\\x81-tail');"
             "sys.stdout.buffer.flush();sys.exit(0)")
    result = run_managed_process([sys.executable, "-c", child], timeout=60.0,
                                 env=dict(os.environ), stdin=subprocess.DEVNULL)
    assert result.returncode == 0
    assert isinstance(result.stdout, str)
    assert "ok-" in result.stdout and "-tail" in result.stdout, (
        "an undecodable byte must degrade to a replacement character, never empty the transcript")


@requires(WINDOWS)                # Windows UTF-8 fidelity proof
def test_ordinary_utf8_provider_output_survives_the_managed_boundary() -> None:
    """The other direction: pinning UTF-8 must not cost fidelity on ordinary provider text."""
    child = ("import sys;"
             "sys.stdout.buffer.write('caf\\u00e9 \\u2014 \\u65e5\\u672c\\u8a9e'.encode('utf-8'));"
             "sys.stdout.buffer.flush();sys.exit(0)")
    result = run_managed_process([sys.executable, "-c", child], timeout=60.0,
                                 env=dict(os.environ), stdin=subprocess.DEVNULL)
    assert result.returncode == 0
    assert "caf\u00e9" in result.stdout, result.stdout
    assert "\u2014" in result.stdout and "\u65e5\u672c\u8a9e" in result.stdout, result.stdout
