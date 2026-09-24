"""SW-18 (part c): the supported launcher reports owned vs attached at exit, and -StopInferenceOnExit
stops ONLY a supervisor this launch started.

Start-Shell.ps1 used to start the detached llama.cpp supervisor and say nothing about it at exit, so
"modules stop with the shell" was implied for a process the shell never owned. It now:

* prints the shell's teardown receipt (owned modules: graceful/forced; attached services: left
  running) - or says plainly that none was written this session;
* says the llama.cpp supervisor is left running (persistent, attached) and how to stop it;
* with -StopInferenceOnExit, stops it only if THIS launch started it and it is still provably that
  process (pid + SW-08 pid_owned); an already-running, restarted or foreign supervisor is untouched.

The two launcher functions are extracted from the shipped Start-Shell.ps1 through the PowerShell AST
and run against real receipts, a real (throwaway) venv and a stub supervisor CLI. The -Live clean-room
lane separately proves the supported-path shell observes a running service as ATTACHED and leaves it
running through teardown ('live-attached', 'live-attached-untouched').
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

if sys.platform != "win32":
    pytest.skip("Start-Shell.ps1 is Windows PowerShell", allow_module_level=True)

RELEASE_ROOT = Path(__file__).resolve().parents[4]
START_SHELL = RELEASE_ROOT / "Start-Shell.ps1"
RESOLVER = RELEASE_ROOT / "modules" / "sovereign" / "SovereignStatePaths.ps1"
GATE = RELEASE_ROOT / "tools" / "cleanroom" / "Test-CleanRoomBoot.ps1"

_LOAD_FUNCTIONS = textwrap.dedent(f"""
    $ErrorActionPreference = 'Stop'
    . '{RESOLVER}'
    $ast = [System.Management.Automation.Language.Parser]::ParseFile('{START_SHELL}', [ref]$null, [ref]$null)
    $wanted = @('Write-ShellTeardownReport', 'Stop-LaunchOwnedSupervisor')
    $fns = $ast.FindAll({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $wanted -contains $n.Name }}, $true)
    if (@($fns).Count -ne 2) {{ throw "launcher functions not found" }}
    foreach ($f in $fns) {{ Invoke-Expression $f.Extent.Text }}
""")


def _ps(body: str, tmp_path: Path, env: dict | None = None) -> str:
    script = tmp_path / "run.ps1"
    script.write_text(_LOAD_FUNCTIONS + textwrap.dedent(body), encoding="utf-8")
    run_env = {k: v for k, v in os.environ.items()
               if not k.startswith("SOVEREIGN_") and k != "PYTHONPATH"}
    run_env.update(env or {})
    proc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(script)], capture_output=True, text=True, env=run_env, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def _receipt(ws: Path, name: str, *, forced_contract_broken: bool = False) -> Path:
    logs = ws / "shell" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": 1, "kind": "sws-shell-teardown",
        "owned": [
            {"module_id": "sovereign", "graceful": True, "forced": False, "exit_code": 0,
             "graceful_contract": "shutdown_event", "graceful_contract_met": True},
            {"module_id": "debate", "graceful": not forced_contract_broken,
             "forced": forced_contract_broken, "exit_code": 1 if forced_contract_broken else 0,
             "graceful_contract": "shutdown_event",
             "graceful_contract_met": not forced_contract_broken},
        ],
        "attached": [{"module_id": "llamacpp", "observed_state": "ATTACHED",
                      "left_running": True, "stopped_by_shell": False,
                      "stop_hint": "Stop-LlamaCppSupervisor.ps1"}],
    }
    path = logs / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_sw18c_launcher_prints_owned_and_attached_from_this_sessions_receipt(tmp_path):
    ws = tmp_path / "ws"
    _receipt(ws, "teardown-20990101T000000000000Z.json", forced_contract_broken=True)
    out = _ps("""
        $script:launchStartedUtc = [DateTime]::UtcNow.AddMinutes(-5)
        Write-ShellTeardownReport *>&1 | Out-String
    """, tmp_path, {"SOVEREIGN_WORKSPACE_STATE": str(ws)})
    assert "owned    sovereign: stopped graceful (exit 0)" in out
    assert "owned    debate: stopped FORCED (exit 1) - graceful shutdown contract NOT met" in out
    assert "attached llamacpp: left running, not stopped by the shell." in out
    assert "Teardown receipt:" in out


def test_sw18c_launcher_does_not_pass_off_an_old_receipt_as_this_sessions(tmp_path):
    ws = tmp_path / "ws"
    stale = _receipt(ws, "teardown-20000101T000000000000Z.json")
    old = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
    os.utime(stale, (old, old))
    out = _ps("""
        $script:launchStartedUtc = [DateTime]::UtcNow
        Write-ShellTeardownReport *>&1 | Out-String
    """, tmp_path, {"SOVEREIGN_WORKSPACE_STATE": str(ws)})
    assert "No teardown receipt from this session" in out
    assert "owned    sovereign" not in out


@pytest.fixture(scope="module")
def fake_supervisor_root(tmp_path_factory):
    """A throwaway install root: a real venv python plus a stub supervisor CLI and Stop script."""
    root = tmp_path_factory.mktemp("sup root")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root / ".venv")],
                   check=True, timeout=120)
    pkg = root / "sovereign_product"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "supervisor_service.py").write_text(textwrap.dedent("""
        import os, sys
        if "status" in sys.argv:
            print(os.environ["FAKE_SUPERVISOR_STATUS"])
    """), encoding="utf-8")
    (root / "Stop-LlamaCppSupervisor.ps1").write_text(
        "param([string]$Root)\nSet-Content -LiteralPath (Join-Path $Root 'STOPPED') -Value 'x'\n",
        encoding="ascii")
    return root


@pytest.mark.parametrize("started_pid,status,should_stop", [
    ("$null", {"running": True, "pid": 4242, "pid_owned": True}, False),     # already running
    ("4242", {"running": True, "pid": 4242, "pid_owned": True}, True),       # ours, unchanged
    ("4242", {"running": True, "pid": 5151, "pid_owned": True}, False),      # restarted since
    ("4242", {"running": True, "pid": 4242, "pid_owned": False}, False),     # pid reused
    ("4242", {"running": False, "reason": "no state file"}, False),          # already gone
])
def test_sw18c_stop_inference_on_exit_stops_only_the_supervisor_this_launch_started(
        tmp_path, fake_supervisor_root, started_pid, status, should_stop):
    marker = fake_supervisor_root / "STOPPED"
    if marker.exists():
        marker.unlink()
    out = _ps(f"""
        $llamaSupervisorRoot = '{fake_supervisor_root}'
        $script:startedSupervisorPid = {started_pid}
        Stop-LaunchOwnedSupervisor *>&1 | Out-String
    """, tmp_path, {"FAKE_SUPERVISOR_STATUS": json.dumps(status)})
    assert marker.exists() is should_stop, out
    if should_stop:
        assert "stopped the llama.cpp supervisor this launch started (pid 4242)" in out
    else:
        assert "left untouched" in out


def test_sw18c_launcher_exit_path_reports_and_gates_the_stop():
    text = START_SHELL.read_text(encoding="utf-8-sig")
    assert "[switch] $StopInferenceOnExit" in text
    finally_block = text[text.rindex("finally {"):]
    assert "Write-ShellTeardownReport" in finally_block
    assert "if ($StopInferenceOnExit)" in finally_block and "Stop-LaunchOwnedSupervisor" in finally_block
    assert "llama.cpp supervisor left running: persistent service, attached" in finally_block
    # Whether THIS launch started the supervisor is recorded from the launcher's own output.
    assert "$supervisorDoc.started -eq $true" in text


def test_sw18c_live_gate_asserts_attached_observed_and_untouched():
    gate = GATE.read_text(encoding="utf-8")
    for step in ("'live-attached'", "'live-attached-untouched'"):
        assert step in gate
    assert all(b < 128 for b in gate.encode("utf-8"))


def test_sw18c_new_launcher_code_is_ascii():
    text = START_SHELL.read_text(encoding="utf-8-sig")
    start = text.index("# SW-18: owned vs attached at exit.")
    end = text.index("# Audit SW-01: start the llama.cpp supervisor ONLY")
    assert all(ord(ch) < 128 for ch in text[start:end])
