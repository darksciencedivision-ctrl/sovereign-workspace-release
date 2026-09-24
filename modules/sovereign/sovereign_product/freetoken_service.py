from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

from system_manifest import find_sovereign_root

from .freetoken_supervisor import FreeTokenSupervisor, FreeTokenSupervisorConfig
from .paths import resolve_runtime_dir
from .state_migration import ensure_state_home
from .runtime_contracts import RuntimeControlError
from .runtime_registry import freetoken_installation


SCHEMA_VERSION = 1
DEFAULT_PORT = 1919
# WS-0.4: FreeToken runtime env, executable, CUDA home and model locations are resolvable from
# the environment, with the historical build-host paths demoted to last-resort defaults. The
# executable and CUDA home derive from the env root unless overridden individually.
_FALLBACK_ENV = Path(
    r"D:\SOVEREIGN_SYSTEM\migration_evidence\opencode_grok46_20260910\freetoken_env_rebuild"
)
DEFAULT_ENV = Path(os.environ.get("SOVEREIGN_FREETOKEN_ENV") or _FALLBACK_ENV)
DEFAULT_EXE = Path(
    os.environ.get("SOVEREIGN_FREETOKEN_EXE") or (DEFAULT_ENV / "Scripts" / "ft.exe")
)
DEFAULT_CUDA_HOME = Path(
    os.environ.get("SOVEREIGN_FREETOKEN_CUDA_HOME")
    or (DEFAULT_ENV / "Lib" / "site-packages" / "nvidia" / "cu13")
)
DEFAULT_MODEL = Path(
    os.environ.get("SOVEREIGN_FREETOKEN_MODEL")
    or r"D:\SOVEREIGN_SYSTEM\migration_evidence\opencode_grok46_20260910\models\Qwen3-0.6B"
)
MOE_MODEL = Path(
    os.environ.get("SOVEREIGN_FREETOKEN_MOE_MODEL")
    or r"D:\SOVEREIGN_SYSTEM\migration_evidence\opencode_grok46_20260910\models\gpt-oss-20b"
)


def service_dir(root: Path) -> Path:
    return resolve_runtime_dir(root) / "freetoken_supervisor"


def state_path(root: Path) -> Path:
    return service_dir(root) / "state.json"


def env_path(root: Path) -> Path:
    return service_dir(root) / "consumer.env"


def autostart_path(root: Path) -> Path:
    return service_dir(root) / "AUTOSTART"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_consumer_env(root: Path, base_url: str) -> None:
    env_path(root).write_text(
        "\n".join(
            [
                "SOVEREIGN_INFERENCE_BACKEND=freetoken",
                f"SOVEREIGN_FREETOKEN_BASE_URL={base_url}",
                f"SOVEREIGN_FREETOKEN_ENV={DEFAULT_ENV}",
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
        raise RuntimeControlError("freetoken supervisor state is not an object")
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

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
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
    import socket

    with socket.socket() as sock:
        return sock.connect_ex((host, port)) == 0


def autostart_enabled(root: Path) -> bool:
    return autostart_path(root).is_file()


def _enable_autostart(root: Path) -> None:
    path = autostart_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n", encoding="utf-8")


def _disable_autostart(root: Path) -> None:
    path = autostart_path(root)
    if path.is_file():
        path.unlink()


def _model_and_args(profile: str) -> tuple[Path, tuple[str, ...], int, float]:
    selected = str(profile or "qwen3-0.6b").strip().lower()
    if selected in {"gpt-oss-20b", "moe", "moe-offload"}:
        return (
            MOE_MODEL,
            (
                "--moe-strategy",
                "offload",
                "--disable-moe-prefill-overlap",
                "--moe-cache-size",
                "32",
                "--kv-reserve-tokens",
                "256",
            ),
            512,
            0.9,
        )
    return (DEFAULT_MODEL, (), 2048, 0.35)


def build_supervisor(root: Path, *, port: int, profile: str) -> FreeTokenSupervisor:
    runtime = freetoken_installation()
    model, extra, max_seq, memory_ratio = _model_and_args(profile)
    executable = runtime.executable if Path(runtime.executable).is_file() else str(DEFAULT_EXE)
    return FreeTokenSupervisor(
        FreeTokenSupervisorConfig(
            executable=executable,
            model_path=str(model),
            host="127.0.0.1",
            port=port,
            work_dir=str(service_dir(root)),
            extra_args=extra,
            ready_timeout_seconds=240.0,
            cuda_home=str(DEFAULT_CUDA_HOME),
            served_model_name=model.name,
            memory_ratio=memory_ratio,
            max_seq_len=max_seq,
            max_running_requests=1,
        )
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
        "profile": state.get("profile"),
        "started_at": state.get("process_started_at"),
        "autostart": autostart_enabled(root),
    }


def cmd_start(root: Path, *, port: int = DEFAULT_PORT, profile: str = "qwen3-0.6b") -> dict[str, Any]:
    current = cmd_status(root)
    if current.get("running"):
        raise RuntimeControlError(
            f"freetoken already running as PID {current['pid']} at {current.get('base_url')}"
        )
    if port_open("127.0.0.1", port):
        raise RuntimeControlError(f"loopback port {port} is occupied")
    from .gpu_occupancy import claim_gpu, release_gpu

    # SW-07: claim, construction, startup and publication share ONE rollback scope, so a failure at
    # any step releases the GPU claim owned by this attempt and tears down a child that did start.
    claim = claim_gpu(root, "freetoken")
    supervisor: FreeTokenSupervisor | None = None
    try:
        supervisor = build_supervisor(root, port=port, profile=profile)
        supervisor.start()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "pid": supervisor.pid,
            "process_started_at": _utc_now(),
            "host": "127.0.0.1",
            "port": port,
            "base_url": supervisor.base_url,
            "executable": supervisor.config.executable,
            "model_path": supervisor.config.model_path,
            "profile": profile,
            "work_dir": str(service_dir(root)),
        }
        write_state(root, payload)
        write_consumer_env(root, supervisor.base_url)
    except Exception:
        if supervisor is not None:
            try:
                supervisor.stop()
            except Exception:
                pass
        release_gpu(root, "freetoken")
        raise
    return {"started": True, **payload, "ready": True, "gpu": claim}


def cmd_stop(root: Path, *, disable_autostart: bool = True) -> dict[str, Any]:
    from .gpu_occupancy import release_gpu

    state = read_state(root)
    if state is None:
        if disable_autostart:
            _disable_autostart(root)
        release_gpu(root, "freetoken")
        return {"stopped": False, "reason": "no state file"}
    pid = int(state.get("pid") or 0)
    supervisor = build_supervisor(
        root,
        port=int(state.get("port") or DEFAULT_PORT),
        profile=str(state.get("profile") or "qwen3-0.6b"),
    )
    supervisor.pid = pid
    supervisor.process = _LiveProcess(pid)
    supervisor.stop()
    path = state_path(root)
    if path.is_file():
        path.unlink()
    if disable_autostart:
        _disable_autostart(root)
    release_gpu(root, "freetoken")
    return {
        "stopped": True,
        "pid": pid,
        "port_open": port_open("127.0.0.1", int(state.get("port") or DEFAULT_PORT)),
        "pid_alive": pid_alive(pid),
    }


def cmd_recover(root: Path, *, profile: str | None = None) -> dict[str, Any]:
    state = read_state(root) or {}
    selected = profile or str(state.get("profile") or "qwen3-0.6b")
    stopped = cmd_stop(root, disable_autostart=False)
    started = cmd_start(root, profile=selected)
    return {"recovered": True, "stop": stopped, "start": started}


def cmd_ensure(root: Path, *, port: int = DEFAULT_PORT, profile: str = "qwen3-0.6b") -> dict[str, Any]:
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

    owner = gpu_owner(root)
    if owner == "llama.cpp":
        # FreeToken was intentionally stopped so the other engine could acquire
        # the GPU. Recovery loops must not immediately restart it; an explicit
        # start (cmd_start / ensure_runtime) transitions ownership deliberately.
        return {
            **status,
            "ensured": False,
            "already_running": False,
            "reason": "gpu owned by llama.cpp; intentional stop preserved",
        }
    started = cmd_start(root, port=port, profile=profile)
    return {"ensured": True, "already_running": False, **started}


def ensure_runtime(
    root: Path | None = None,
    *,
    workload: str | None = None,
    profile: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    """On-demand FreeToken activation for a designated workload.

    Resolves the configured profile (workload designation -> explicit profile
    argument -> selection file default), starts the supervisor when needed
    (GPU ownership transition included), and returns the routing base_url.
    Callers never need temporary shell variables or a manual server launch.
    """

    from .backend_selection import resolve_freetoken_port, resolve_freetoken_profile
    from .gpu_occupancy import gpu_owner

    resolved_root = find_sovereign_root(str(root) if root is not None else None)
    selected_profile = (
        str(profile).strip()
        if profile and str(profile).strip()
        else resolve_freetoken_profile(resolved_root, workload)
    )
    selected_port = int(port or resolve_freetoken_port(resolved_root, workload) or DEFAULT_PORT)
    status = cmd_status(resolved_root)
    if status.get("running"):
        running_profile = str(status.get("profile") or "").strip()
        if not running_profile or running_profile == selected_profile:
            return {
                "started_now": False,
                "profile": running_profile or selected_profile,
                "pid": status.get("pid"),
                "base_url": str(status.get("base_url") or f"http://127.0.0.1:{selected_port}"),
                "gpu_owner": gpu_owner(resolved_root),
            }
        # Profile switch: deliberate stop of owned runtime, then start the
        # designated profile (cmd_start re-claims GPU ownership).
        cmd_stop(resolved_root, disable_autostart=False)
    started = cmd_start(resolved_root, port=selected_port, profile=selected_profile)
    return {
        "started_now": True,
        "profile": selected_profile,
        "pid": started.get("pid"),
        "base_url": str(started.get("base_url") or f"http://127.0.0.1:{selected_port}"),
        "gpu": started.get("gpu"),
    }


def cmd_install_persistence(root: Path) -> dict[str, Any]:
    directory = service_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    write_consumer_env(root, f"http://127.0.0.1:{DEFAULT_PORT}")
    return {
        "installed": True,
        "autostart": autostart_enabled(root),
        "note": "FreeToken does not take logon GPU ownership; llama.cpp remains the local default. Enable AUTOSTART to recover this runtime.",
        "env": str(DEFAULT_ENV),
        "executable": str(DEFAULT_EXE),
        **cmd_status(root),
    }


def cmd_enable_autostart(root: Path) -> dict[str, Any]:
    _enable_autostart(root)
    return {"autostart": True, **cmd_status(root)}


def cmd_disable_autostart(root: Path) -> dict[str, Any]:
    _disable_autostart(root)
    return {"autostart": False, **cmd_status(root)}


class _LiveProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        return None if pid_alive(self.pid) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sovereign_product.freetoken_service")
    parser.add_argument("--root", default=None)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--profile", default=None)
    parser.add_argument(
        "--workload",
        default=None,
        help="named workload from runtime/backend_selection.json (profile/port designation)",
    )
    parser.add_argument(
        "command",
        choices=(
            "start",
            "stop",
            "status",
            "recover",
            "ensure",
            "ensure-runtime",
            "install-persistence",
            "enable-autostart",
            "disable-autostart",
        ),
    )
    args = parser.parse_args(argv)
    root = find_sovereign_root(args.root)
    ensure_state_home(root)  # SW-25: copy legacy install-tree state across once
    profile = args.profile or "qwen3-0.6b"
    commands = {
        "start": lambda: cmd_start(root, port=args.port, profile=profile),
        "stop": lambda: cmd_stop(root),
        "status": lambda: cmd_status(root),
        "recover": lambda: cmd_recover(root, profile=args.profile),
        "ensure": lambda: cmd_ensure(root, port=args.port, profile=profile),
        "ensure-runtime": lambda: ensure_runtime(
            root,
            workload=args.workload,
            profile=args.profile,
            port=args.port or None,
        ),
        "install-persistence": lambda: cmd_install_persistence(root),
        "enable-autostart": lambda: cmd_enable_autostart(root),
        "disable-autostart": lambda: cmd_disable_autostart(root),
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
