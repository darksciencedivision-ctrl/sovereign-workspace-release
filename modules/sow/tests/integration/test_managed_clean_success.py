"""P-D2 regression: the Windows job-member can import its argv guard directly."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys

import pytest

from adapters.cmd_shim import CmdShimMetacharacter
from adapters.frontier.process_tree import run_managed_process


def _pid_exists(pid: int) -> bool:
    if os.name != "nt":
        return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


@pytest.mark.skipif(os.name != "nt", reason="Windows job-member regression")
def test_clean_managed_command_succeeds_and_hostile_cmd_shim_is_refused() -> None:
    result = run_managed_process(
        [sys.executable, "-c", "print('managed-clean-ok')"],
        timeout=10.0,
        env=dict(os.environ),
        stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "managed-clean-ok"
    assert result.spawned_pids
    assert all(not _pid_exists(pid) for pid in result.spawned_pids)

    hostile = r"C:\x\%COMSPEC%^&whoami"
    with pytest.raises(CmdShimMetacharacter) as caught:
        run_managed_process(
            [r"C:\x\probe.cmd", hostile],
            timeout=1.0,
            env=dict(os.environ),
            stdin=subprocess.DEVNULL,
        )
    assert "carrying cmd.exe metacharacters" in str(caught.value)
    assert repr(hostile) in str(caught.value)
