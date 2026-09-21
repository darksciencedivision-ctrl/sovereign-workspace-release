from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from typing import Any

from system_manifest import find_sovereign_root

from .runtime_contracts import RuntimeControlError
from .runtime_registry import (
    build_operational_registry,
    llama_cpp_installation,
)
from .runtime_supervisor import LlamaCppSupervisor, SupervisorConfig

SCHEMA_VERSION = 1
DEFAULT_PORT = 18080
WATCH_INTERVAL_SECONDS = 5.0
TASK_WATCH = "SOVEREIGN_LlamaCppSupervisor_Watch"
TASK_ENSURE = "SOVEREIGN_LlamaCppSupervisor_Ensure"
RUN_VALUE_NAME = "SOVEREIGN_LlamaCppSupervisor"
STARTUP_VBS_NAME = "SOVEREIGN_LlamaCppSupervisor.vbs"
# WS-0.4: the llama.cpp server binary is locatable without editing code. Precedence:
#   1. SOVEREIGN_LLAMACPP_SERVER_EXE (explicit path to llama-server.exe),
#   2. <SOVEREIGN_LLAMA_SUPERVISOR_ROOT>/runtime/llama.cpp/current/llama-server.exe,
#   3. the historical build-host path (last-resort default, portable only on the build host).
# The supply-chain hash pin is preserved. An operator who supplies their own vetted binary may
# override its expected hashes TOGETHER with it via SOVEREIGN_LLAMACPP_SERVER_SHA256 /
# SOVEREIGN_LLAMACPP_IMPL_SHA256; otherwise the built-in vetted hashes still apply, so a swapped
# binary that does not match is still rejected.
_FALLBACK_EXE = Path(
    r"D:\Product Software\Production Workspace\runtime\llama.cpp\current\llama-server.exe"
)


def _resolve_default_exe() -> Path:
    explicit = os.environ.get("SOVEREIGN_LLAMACPP_SERVER_EXE")
    if explicit:
        return Path(explicit)
    base = os.environ.get("SOVEREIGN_LLAMA_SUPERVISOR_ROOT")
    if base:
        return Path(base) / "runtime" / "llama.cpp" / "current" / "llama-server.exe"
    return _FALLBACK_EXE


DEFAULT_EXE = _resolve_default_exe()
EXE_HASH = os.environ.get(
    "SOVEREIGN_LLAMACPP_SERVER_SHA256",
    "E25313077D8ED57A838C475CE2F3D31422881212CAF2DDAC2C18385E5E49AE69",
)
IMPL_HASH = os.environ.get(
    "SOVEREIGN_LLAMACPP_IMPL_SHA256",
    "8AFC4644F8A8FB6E143B64FFB43542EF4796358D240296FD8E2109CD5C421251",
)
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008


def service_dir(root: Path) -> Path:
    return root / "runtime" / "llamacpp_supervisor"


def state_path(root: Path) -> Path:
    return service_dir(root) / "state.json"


def key_path(root: Path) -> Path:
    return service_dir(root) / "api_key"


def env_path(root: Path) -> Path:
    return service_dir(root) / "consumer.env"


def cutover_path(root: Path) -> Path:
    return service_dir(root) / "CUTOVER"


def autostart_path(root: Path) -> Path:
    return service_dir(root) / "AUTOSTART"


def watch_pid_path(root: Path) -> Path:
    return service_dir(root) / "watch.pid"


def venv_python(root: Path, *, windowless: bool = False) -> Path:
    name = "pythonw.exe" if windowless and sys.platform == "win32" else "python.exe"
    return root / ".venv" / "Scripts" / name


def load_or_create_key(root: Path) -> str:
    path = key_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_hex(16)
    path.write_text(value + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return value


def write_consumer_env(root: Path, base_url: str, api_key: str) -> None:
    env_path(root).write_text(
        "\n".join(
            [
                "SOVEREIGN_INFERENCE_BACKEND=llama.cpp",
                f"SOVEREIGN_LLAMA_CPP_BASE_URL={base_url}",
                f"SOVEREIGN_LLAMA_CPP_API_KEY={api_key}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def read_state(root: Path) -> dict[str, Any] | None:
    path = state_path(root)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeControlError("supervisor state is not an object")
    return payload


def write_state(root: Path, payload: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def port_open(host: str, port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex((host, port)) == 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_binary(exe: Path) -> None:
    """WS-0.4 (audit B1): actually ENFORCE the hash pin before launch, not merely record it.

    The expected hashes come from EXE_HASH / IMPL_HASH, which resolve from
    SOVEREIGN_LLAMACPP_SERVER_SHA256 / SOVEREIGN_LLAMACPP_IMPL_SHA256 when set (so an operator
    running their own binary pins ITS hash — Provision-Workspace.ps1 does this automatically) and
    otherwise fall back to the built-in vetted values. Either way a binary whose bytes do not match
    the expected digest is refused before any process starts. The sibling implementation DLL is
    checked only when it is present, so builds that do not ship it are not falsely blocked.
    """
    actual = _sha256_file(exe).lower()
    if actual != EXE_HASH.strip().lower():
        raise RuntimeControlError(
            f"llama.cpp server binary at {exe} failed hash verification "
            f"(expected {EXE_HASH.strip().lower()}, got {actual}). Refusing to launch. If this is "
            "intentionally your own build, set SOVEREIGN_LLAMACPP_SERVER_SHA256 to its digest "
            "(Provision-Workspace.ps1 -LlamaCppExe pins it for you)."
        )
    impl = exe.with_name("llama-server-impl.dll")
    if impl.is_file():
        actual_impl = _sha256_file(impl).lower()
        if actual_impl != IMPL_HASH.strip().lower():
            raise RuntimeControlError(
                f"llama.cpp implementation DLL at {impl} failed hash verification "
                f"(expected {IMPL_HASH.strip().lower()}, got {actual_impl}). Refusing to launch. "
                "Set SOVEREIGN_LLAMACPP_IMPL_SHA256 to its digest if this build is intentional."
            )


def build_supervisor(root: Path, *, port: int, api_key: str) -> LlamaCppSupervisor:
    # WS-0.4: fail with a clear, actionable message when the server binary is not present, rather
    # than an opaque launch failure. The binary is provisioned per machine (not shipped): point the
    # operator at the resolution knobs and the provisioning script.
    if not DEFAULT_EXE.is_file():
        raise RuntimeControlError(
            "llama.cpp server binary not found at "
            f"{DEFAULT_EXE}. It is provisioned per machine, not shipped. Run "
            "Provision-Workspace.ps1, or set SOVEREIGN_LLAMACPP_SERVER_EXE (or "
            "SOVEREIGN_LLAMA_SUPERVISOR_ROOT) in workspace.env to your llama-server.exe."
        )
    # WS-0.4 (audit B1): enforce the hash pin at the launch path, before the process is built.
    _verify_binary(DEFAULT_EXE)
    runtime = llama_cpp_installation(
        executable=DEFAULT_EXE,
        hashes={"llama-server.exe": EXE_HASH, "llama-server-impl.dll": IMPL_HASH},
    )
    registry = build_operational_registry(runtime=runtime)
    return LlamaCppSupervisor(
        SupervisorConfig(
            executable=str(DEFAULT_EXE),
            host="127.0.0.1",
            port=port,
            models_max=1,
            work_dir=str(service_dir(root)),
            ready_timeout_seconds=90,
            api_key=api_key,
            detach=True,
        ),
        registry,
    )


def cmd_status(root: Path) -> dict[str, Any]:
    state = read_state(root)
    if state is None:
        return {"running": False, "reason": "no state file"}
    pid = int(state.get("pid") or 0)
    host = str(state.get("host") or "127.0.0.1")
    port = int(state.get("port") or DEFAULT_PORT)
    alive = pid_alive(pid)
    listening = port_open(host, port)
    return {
        "running": bool(alive and listening),
        "pid": pid,
        "pid_alive": alive,
        "port_open": listening,
        "base_url": state.get("base_url"),
        "started_at": state.get("process_started_at"),
        "cutover": cutover_path(root).is_file(),
    }


def cmd_start(root: Path, *, port: int = DEFAULT_PORT) -> dict[str, Any]:
    current = cmd_status(root)
    if current.get("running"):
        raise RuntimeControlError(
            f"supervisor already running as PID {current['pid']} at {current.get('base_url')}"
        )
    if port_open("127.0.0.1", port):
        raise RuntimeControlError(f"loopback port {port} is occupied")
    api_key = load_or_create_key(root)
    from .gpu_occupancy import claim_gpu, release_gpu

    claim = claim_gpu(root, "llama.cpp")
    supervisor = build_supervisor(root, port=port, api_key=api_key)
    try:
        supervisor.start()
    except Exception:
        release_gpu(root, "llama.cpp")
        raise
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pid": supervisor.pid,
        "process_started_at": _utc_now(),
        "host": "127.0.0.1",
        "port": port,
        "base_url": supervisor.base_url,
        "executable": str(DEFAULT_EXE),
        "work_dir": str(service_dir(root)),
        "detach": True,
    }
    write_state(root, payload)
    write_consumer_env(root, supervisor.base_url, api_key)
    cutover_path(root).write_text("llama.cpp\n", encoding="utf-8")
    _enable_autostart(root)
    watch = _spawn_watch(root, port=port)
    return {"started": True, **payload, "ready": True, "watch": watch, "gpu": claim}


def cmd_stop(root: Path, *, disable_autostart: bool = True) -> dict[str, Any]:
    _stop_watch_process(root)
    state = read_state(root)
    if state is None:
        if disable_autostart:
            _disable_autostart(root)
        return {"stopped": False, "reason": "no state file"}
    pid = int(state.get("pid") or 0)
    api_key = load_or_create_key(root)
    supervisor = build_supervisor(root, port=int(state.get("port") or DEFAULT_PORT), api_key=api_key)
    supervisor.pid = pid
    supervisor.process = _LiveProcess(pid)
    try:
        supervisor.unload("qwen3:8b")
    except Exception:
        pass
    supervisor.stop()
    path = state_path(root)
    if path.is_file():
        path.unlink()
    if disable_autostart:
        _disable_autostart(root)
    from .gpu_occupancy import release_gpu

    release_gpu(root, "llama.cpp")
    return {
        "stopped": True,
        "pid": pid,
        "port_open": port_open("127.0.0.1", int(state.get("port") or DEFAULT_PORT)),
        "pid_alive": pid_alive(pid),
    }


def cmd_recover(root: Path) -> dict[str, Any]:
    persist = persistence_installed(root)
    stopped = cmd_stop(root, disable_autostart=False)
    started = cmd_start(root)
    if persist:
        _spawn_watch(root, port=int(started.get("port") or DEFAULT_PORT))
    return {"recovered": True, "stop": stopped, "start": started}


def enable_cutover(root: Path) -> dict[str, Any]:
    status = cmd_status(root)
    if not status.get("running"):
        raise RuntimeControlError("refusing cutover; supervisor is not running")
    cutover_path(root).write_text("llama.cpp\n", encoding="utf-8")
    return {**cmd_status(root), "cutover": True}


def disable_cutover(root: Path) -> dict[str, Any]:
    path = cutover_path(root)
    if path.is_file():
        path.unlink()
    return {"cutover": False, **cmd_status(root)}


def _enable_autostart(root: Path) -> None:
    path = autostart_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n", encoding="utf-8")


def _disable_autostart(root: Path) -> None:
    path = autostart_path(root)
    if path.is_file():
        path.unlink()


def autostart_enabled(root: Path) -> bool:
    return autostart_path(root).is_file()


def _read_watch_pid(root: Path) -> int:
    path = watch_pid_path(root)
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return 0
    if isinstance(payload, dict):
        try:
            return int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _watch_alive(root: Path) -> bool:
    pid = _read_watch_pid(root)
    return pid_alive(pid)


def _stop_watch_process(root: Path) -> dict[str, Any]:
    pid = _read_watch_pid(root)
    path = watch_pid_path(root)
    killed = False
    if pid > 0 and pid != os.getpid() and pid_alive(pid):
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                check=False,
            )
        else:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        killed = True
    if path.is_file():
        path.unlink()
    return {"watch_stopped": killed, "watch_pid": pid}


def _clear_stale_state(root: Path) -> None:
    status = cmd_status(root)
    if status.get("running"):
        return
    path = state_path(root)
    if path.is_file() and not status.get("pid_alive"):
        path.unlink()


def cmd_ensure(root: Path, *, port: int = DEFAULT_PORT) -> dict[str, Any]:
    status = cmd_status(root)
    if status.get("running"):
        return {"ensured": True, "already_running": True, **status}
    if not autostart_enabled(root):
        return {
            **status,
            "ensured": False,
            "already_running": False,
            "reason": "autostart disabled",
        }
    from .gpu_occupancy import gpu_owner

    if gpu_owner(root) == "freetoken":
        # FreeToken intentionally holds the GPU. The watcher must not restart
        # llama.cpp underneath it (cmd_start would force-stop freetoken via the
        # GPU claim). Bounded recovery resumes on the next iteration after
        # freetoken releases ownership; explicit cmd_start still transitions.
        return {
            **status,
            "ensured": False,
            "already_running": False,
            "reason": "gpu owned by freetoken; restart deferred until release",
        }
    if port_open("127.0.0.1", port) and not status.get("pid_alive"):
        raise RuntimeControlError(
            f"loopback port {port} is occupied by an unrelated process"
        )
    _clear_stale_state(root)
    started = cmd_start(root, port=port)
    return {"ensured": True, "already_running": False, **started}


def cmd_watch(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    interval: float = WATCH_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    should_continue: Callable[[], bool] | None = None,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    existing = _read_watch_pid(root)
    if existing and existing != os.getpid() and pid_alive(existing):
        raise RuntimeControlError(f"watch already running as PID {existing}")
    watch_pid_path(root).parent.mkdir(parents=True, exist_ok=True)
    watch_pid_path(root).write_text(
        json.dumps({"pid": os.getpid(), "started_at": _utc_now()}, indent=2),
        encoding="utf-8",
    )
    iterations = 0
    last: dict[str, Any] = {}
    keep_going = should_continue or (lambda: True)
    log_path = service_dir(root) / "watch.log"
    try:
        while keep_going():
            last = cmd_ensure(root, port=port)
            iterations += 1
            line = json.dumps(
                {
                    "utc": _utc_now(),
                    "iteration": iterations,
                    "ensured": last.get("ensured"),
                    "running": last.get("running") or last.get("started"),
                    "pid": last.get("pid"),
                }
            )
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            if max_iterations is not None and iterations >= max_iterations:
                break
            sleep(interval)
    finally:
        if _read_watch_pid(root) == os.getpid() and watch_pid_path(root).is_file():
            watch_pid_path(root).unlink()
    return {"watched": True, "iterations": iterations, "last": last}


def _task_exists(name: str) -> bool:
    completed = subprocess.run(
        ["schtasks", "/Query", "/TN", name],
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.returncode == 0


def persistence_installed(root: Path) -> bool:
    return _run_key_present() and _startup_vbs_path().is_file()


def _python_for_tasks(root: Path, *, windowless: bool) -> Path:
    candidate = venv_python(root, windowless=windowless)
    if candidate.is_file():
        return candidate
    fallback = venv_python(root, windowless=False)
    if fallback.is_file():
        return fallback
    return Path(sys.executable)


def render_watch_task_xml(root: Path, *, port: int = DEFAULT_PORT) -> str:
    python = _python_for_tasks(root, windowless=True)
    arguments = (
        f'-m sovereign_product.supervisor_service --root "{root}" --port {port} watch'
    )
    return _task_xml(
        description="Sovereign llama.cpp supervisor watchdog. Starts at logon and restarts llama-server after process failure.",
        command=str(python),
        arguments=arguments,
        working_directory=str(root),
        logon=True,
        repetition=None,
        execution_limit="PT0S",
        restart_count=3,
    )


def render_ensure_task_xml(root: Path, *, port: int = DEFAULT_PORT) -> str:
    python = _python_for_tasks(root, windowless=False)
    arguments = (
        f'-m sovereign_product.supervisor_service --root "{root}" --port {port} ensure'
    )
    return _task_xml(
        description="Sovereign llama.cpp supervisor ensure. Relaunches llama-server within one minute if the watchdog is absent.",
        command=str(python),
        arguments=arguments,
        working_directory=str(root),
        logon=False,
        repetition="PT1M",
        execution_limit="PT2M",
        restart_count=0,
    )


def _task_xml(
    *,
    description: str,
    command: str,
    arguments: str,
    working_directory: str,
    logon: bool,
    repetition: str | None,
    execution_limit: str,
    restart_count: int,
) -> str:
    if logon:
        trigger = """    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>"""
    else:
        trigger = f"""    <TimeTrigger>
      <Repetition>
        <Interval>{repetition}</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>"""
    restart = ""
    if restart_count > 0:
        restart = f"""
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>{restart_count}</Count>
    </RestartOnFailure>"""
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{description}</Description>
  </RegistrationInfo>
  <Triggers>
{trigger}
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>{execution_limit}</ExecutionTimeLimit>
    <Priority>7</Priority>{restart}
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{working_directory}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _register_task(name: str, xml_path: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        ["schtasks", "/Create", "/TN", name, "/XML", str(xml_path), "/F"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode == 0:
        return True, ""
    detail = (completed.stderr or completed.stdout or "").strip()
    return False, detail


def _delete_task(name: str) -> None:
    subprocess.run(
        ["schtasks", "/Delete", "/TN", name, "/F"],
        capture_output=True,
        check=False,
        text=True,
    )


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _startup_vbs_path() -> Path:
    return _startup_dir() / STARTUP_VBS_NAME


def _run_key_command(root: Path, *, port: int) -> str:
    # The Run key has no reliable working-directory contract.  Launch the
    # repository's hardened PowerShell entry point so it establishes the
    # package import path before invoking the module.
    launcher = root / "Start-LlamaCppSupervisor.ps1"
    return (
        f'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass '
        f'-File "{launcher}" -Root "{root}" -Port {port}'
    )


def _set_run_key(command: str) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command)


def _delete_run_key() -> None:
    if sys.platform != "win32":
        return
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        return


def _run_key_present() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        return False
    return bool(str(value or "").strip())


def _write_startup_vbs(root: Path, *, port: int) -> Path:
    python = _python_for_tasks(root, windowless=True)
    command = (
        f'"{python}" -m sovereign_product.supervisor_service '
        f'--root "{root}" --port {port} watch'
    )
    escaped = command.replace('"', '""')
    content = (
        "' Sovereign llama.cpp supervisor watchdog\n"
        "Option Explicit\n"
        "Dim sh\n"
        "Set sh = CreateObject(\"WScript.Shell\")\n"
        f'sh.CurrentDirectory = "{str(root).replace(chr(34), chr(34) + chr(34))}"\n'
        f'sh.Run "{escaped}", 0, False\n'
    )
    path = _startup_vbs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="ascii")
    return path


def _spawn_watch(root: Path, *, port: int = DEFAULT_PORT) -> dict[str, Any]:
    if _watch_alive(root):
        return {"spawned": False, "already_running": True, "watch_pid": _read_watch_pid(root)}
    lock_path = service_dir(root) / "watch.spawn.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if _watch_alive(root):
                return {
                    "spawned": False,
                    "already_running": True,
                    "watch_pid": _read_watch_pid(root),
                }
            time.sleep(0.1)
        try:
            lock_path.unlink()
        except OSError:
            pass
        if _watch_alive(root):
            return {
                "spawned": False,
                "already_running": True,
                "watch_pid": _read_watch_pid(root),
            }
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(lock_fd, str(os.getpid()).encode("ascii"))
    os.close(lock_fd)
    python = _python_for_tasks(root, windowless=True)
    log_path = service_dir(root) / "watch.spawn.log"
    handle = log_path.open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "cwd": str(root),
        "stdout": handle,
        "stderr": subprocess.STDOUT,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        [
            str(python),
            "-m",
            "sovereign_product.supervisor_service",
            "--root",
            str(root),
            "--port",
            str(port),
            "watch",
        ],
        **kwargs,
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if _watch_alive(root):
                return {
                    "spawned": True,
                    "already_running": False,
                    "watch_pid": _read_watch_pid(root),
                }
            time.sleep(0.1)
        return {"spawned": True, "already_running": False, "watch_pid": int(process.pid)}
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def cmd_install_persistence(root: Path, *, port: int = DEFAULT_PORT) -> dict[str, Any]:
    directory = service_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    watch_xml = directory / "task_watch.xml"
    ensure_xml = directory / "task_ensure.xml"
    watch_xml.write_text(render_watch_task_xml(root, port=port), encoding="utf-16")
    ensure_xml.write_text(render_ensure_task_xml(root, port=port), encoding="utf-16")
    watch_ok, watch_err = _register_task(TASK_WATCH, watch_xml)
    ensure_ok, ensure_err = _register_task(TASK_ENSURE, ensure_xml)
    _set_run_key(_run_key_command(root, port=port))
    startup = _write_startup_vbs(root, port=port)
    _enable_autostart(root)
    ensured = cmd_ensure(root, port=port)
    watch = _spawn_watch(root, port=port)
    return {
        "installed": True,
        "logon_launcher": RUN_VALUE_NAME,
        "logon_launcher_path": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        "startup_vbs": str(startup),
        "failure_launcher": "watch process cmd_ensure loop",
        "scheduled_task_watch": watch_ok,
        "scheduled_task_watch_error": watch_err,
        "scheduled_task_ensure": ensure_ok,
        "scheduled_task_ensure_error": ensure_err,
        "ensure": ensured,
        "watch": watch,
        **cmd_persistence_status(root),
    }


def cmd_uninstall_persistence(root: Path) -> dict[str, Any]:
    _delete_task(TASK_WATCH)
    _delete_task(TASK_ENSURE)
    _delete_run_key()
    startup = _startup_vbs_path()
    if startup.is_file():
        startup.unlink()
    _stop_watch_process(root)
    _disable_autostart(root)
    return {"installed": False, **cmd_persistence_status(root)}


def cmd_persistence_status(root: Path) -> dict[str, Any]:
    watch_pid = _read_watch_pid(root)
    return {
        "logon_launcher": RUN_VALUE_NAME,
        "logon_launcher_present": _run_key_present(),
        "startup_vbs": str(_startup_vbs_path()),
        "startup_vbs_present": _startup_vbs_path().is_file(),
        "failure_launcher": "watch process cmd_ensure loop",
        "scheduled_task_watch_present": _task_exists(TASK_WATCH),
        "scheduled_task_ensure_present": _task_exists(TASK_ENSURE),
        "autostart": autostart_enabled(root),
        "watch_pid": watch_pid,
        "watch_alive": pid_alive(watch_pid),
        "persistent": persistence_installed(root),
        "supervisor": cmd_status(root),
    }


class _LiveProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        return None if pid_alive(self.pid) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sovereign_product.supervisor_service")
    parser.add_argument("--root", default=None)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "command",
        choices=(
            "start",
            "stop",
            "status",
            "recover",
            "ensure",
            "watch",
            "install-persistence",
            "uninstall-persistence",
            "persistence-status",
            "cutover-enable",
            "cutover-disable",
        ),
    )
    args = parser.parse_args(argv)
    root = find_sovereign_root(args.root)
    commands = {
        "start": lambda: cmd_start(root, port=args.port),
        "stop": lambda: cmd_stop(root),
        "status": lambda: cmd_status(root),
        "recover": lambda: cmd_recover(root),
        "ensure": lambda: cmd_ensure(root, port=args.port),
        "watch": lambda: cmd_watch(root, port=args.port),
        "install-persistence": lambda: cmd_install_persistence(root, port=args.port),
        "uninstall-persistence": lambda: cmd_uninstall_persistence(root),
        "persistence-status": lambda: cmd_persistence_status(root),
        "cutover-enable": lambda: enable_cutover(root),
        "cutover-disable": lambda: disable_cutover(root),
    }
    payload = commands[args.command]()
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeControlError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
