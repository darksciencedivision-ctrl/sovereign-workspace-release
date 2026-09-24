from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
import json
import secrets
import socket
import subprocess
import sys
import time

import requests

from .runtime_contracts import RuntimeControlError, RuntimeInventory, validate_loopback_origin
from .runtime_registry import RuntimeRegistry, ServingProfile


CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


@dataclass(frozen=True)
class SupervisorConfig:
    executable: str
    host: str = "127.0.0.1"
    port: int = 18082
    models_max: int = 1
    work_dir: str = ""
    extra_args: tuple[str, ...] = ()
    ready_timeout_seconds: float = 60.0
    api_key: str | None = None
    detach: bool = False


class LlamaCppSupervisor:
    def __init__(
        self,
        config: SupervisorConfig,
        registry: RuntimeRegistry,
        *,
        popen: Callable[..., Any] = subprocess.Popen,
        request_session: requests.Session | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if config.host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeControlError("supervisor must bind loopback only")
        self.config = config
        self.registry = registry
        self._popen = popen
        self._session = request_session or requests.Session()
        if request_session is None:
            self._session.trust_env = False
        self._monotonic = monotonic
        self._sleep = sleep
        self.api_key = config.api_key or secrets.token_hex(16)
        self.base_url = validate_loopback_origin(f"http://{config.host}:{config.port}")
        self.process: Any | None = None
        self.pid: int | None = None
        self.preset_path: Path | None = None
        self.log_path: Path | None = None
        self._log_handle: Any | None = None
        self._job = None
        work = Path(config.work_dir) if config.work_dir else Path.cwd() / "runtime_supervisor"
        self.work_dir = work

    def render_preset(self, profiles: Mapping[str, ServingProfile] | None = None) -> str:
        items = list((profiles or self.registry.profiles).values())
        if not items:
            raise RuntimeControlError("no serving profiles to start")
        lines = ["version = 1", "[*]"]
        for profile in items:
            lines.append(f"[{profile.engine_id}]")
            lines.append(f"model = {Path(profile.model_path).as_posix()}")
            lines.append(f"ctx-size = {profile.context_configured}")
            lines.append(f"n-gpu-layers = {profile.n_gpu_layers}")
            lines.append(f"parallel = {profile.parallel}")
            lines.append("webui = 0")
            if profile.embeddings:
                lines.append("embeddings = true")
            if profile.batch_size is not None:
                lines.append(f"batch-size = {profile.batch_size}")
            if profile.ubatch_size is not None:
                lines.append(f"ubatch-size = {profile.ubatch_size}")
            if profile.engine_id != profile.model_id:
                lines.append(f"alias = {profile.model_id}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def command(self, preset_path: Path) -> list[str]:
        args = [
            self.config.executable,
            "--models-preset",
            str(preset_path),
            "--models-max",
            str(self.config.models_max),
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
            "--no-webui",
            "--offline",
            "--cors-origins",
            "localhost",
            "--api-key",
            self.api_key,
        ]
        args.extend(self.config.extra_args)
        return args

    def start(self) -> None:
        if self.process is not None and getattr(self.process, "poll", lambda: None)() is None:
            raise RuntimeControlError("supervisor already owns a running process")
        self._assert_port_free()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.preset_path = self.work_dir / "models.ini"
        self.log_path = self.work_dir / "llama-server.log"
        self.preset_path.write_text(self.render_preset(), encoding="utf-8")
        command = self.command(self.preset_path)
        self._log_handle = self.log_path.open("w", encoding="utf-8")
        kwargs: dict[str, Any] = {
            "cwd": str(self.work_dir),
            "stdout": self._log_handle,
            "stderr": subprocess.STDOUT,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        self.process = self._popen(command, **kwargs)
        self.pid = int(getattr(self.process, "pid"))
        self._job = None if self.config.detach else _assign_job(self.pid)
        try:
            deadline = self._monotonic() + self.config.ready_timeout_seconds
            while self._monotonic() < deadline:
                if getattr(self.process, "poll", lambda: None)() is not None:
                    raise RuntimeControlError("llama.cpp supervisor process exited during start")
                if self.ready():
                    return
                self._sleep(0.25)
            raise RuntimeControlError("llama.cpp supervisor did not become ready")
        except Exception:
            self.stop()
            raise

    def ready(self) -> bool:
        if self.process is None or getattr(self.process, "poll", lambda: 0)() is not None:
            return False
        try:
            response = self._call("GET", "/models")
        except (RuntimeControlError, requests.RequestException, OSError, TimeoutError):
            return False
        return int(getattr(response, "status_code", 0)) == 200

    def inventory(self) -> RuntimeInventory:
        payload = self._json("GET", "/models")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise RuntimeControlError("inventory payload missing data")
        registered = []
        loaded = []
        for entry in rows:
            if not isinstance(entry, Mapping):
                continue
            identity = str(entry.get("id") or "").strip()
            if not identity:
                continue
            registered.append(identity)
            status = entry.get("status")
            value = status.get("value") if isinstance(status, Mapping) else status
            if str(value).strip().lower() in {"loaded", "loading", "busy"}:
                if str(value).strip().lower() == "loaded":
                    loaded.append(identity)
        available = tuple(self.registry.aliases.keys())
        return RuntimeInventory(
            registered=tuple(registered),
            available=available,
            loaded=tuple(loaded),
            raw=payload,
        )

    def load(self, model: str) -> dict[str, Any]:
        engine_id = self.registry.engine_id(model)
        return self._json("POST", "/models/load", {"model": engine_id})

    def unload(self, model: str) -> dict[str, Any]:
        engine_id = self.registry.engine_id(model)
        current = self.inventory()
        if engine_id not in current.loaded:
            return {"success": True, "already_unloaded": True, "model": engine_id}
        return self._json("POST", "/models/unload", {"model": engine_id})

    def switch(self, model: str, *, timeout_seconds: float = 60.0) -> dict[str, Any]:
        engine_id = self.registry.engine_id(model)
        accepted = self.load(model)
        deadline = self._monotonic() + timeout_seconds
        latest = self.inventory()
        while self._monotonic() < deadline:
            latest = self.inventory()
            if engine_id not in latest.loaded:
                self._sleep(0.25)
                continue
            if self.config.models_max == 1 and set(latest.loaded) != {engine_id}:
                self._sleep(0.25)
                continue
            return {"success": True, "loaded": latest.loaded, "accepted": accepted}
        raise RuntimeControlError(f"switch to {engine_id} did not reach loaded state")

    def inspect_context(self, model: str) -> dict[str, Any]:
        engine_id = self.registry.engine_id(model)
        return self._json("GET", f"/props?model={engine_id}")

    def logs(self) -> str:
        if self.log_path is None or not self.log_path.is_file():
            return ""
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def stop(self) -> None:
        process = self.process
        if process is None:
            return
        pid = getattr(process, "pid", None)
        poll = getattr(process, "poll", lambda: 0)
        if poll() is None:
            if sys.platform == "win32" and pid is not None:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                terminate = getattr(process, "terminate", None)
                if callable(terminate):
                    terminate()
            wait = getattr(process, "wait", None)
            if callable(wait):
                try:
                    wait(timeout=15)
                except Exception:
                    kill = getattr(process, "kill", None)
                    if callable(kill):
                        kill()
        self.process = None
        self.pid = None
        self._job = None
        if self._log_handle is not None:
            close = getattr(self._log_handle, "close", None)
            if callable(close):
                close()
            self._log_handle = None

    def recover(self) -> None:
        self.stop()
        self.start()

    def _assert_port_free(self) -> None:
        with socket.socket() as sock:
            if sock.connect_ex((self.config.host, self.config.port)) == 0:
                raise RuntimeControlError(
                    f"loopback port {self.config.port} is occupied"
                )

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _call(
        self,
        method: str,
        path: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> requests.Response:
        try:
            return self._session.request(
                method,
                f"{self.base_url}{path}",
                json=None if json_body is None else dict(json_body),
                headers=self._headers(),
                timeout=(5.0, 30.0),
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise RuntimeControlError(f"supervisor request failed: {exc}") from exc

    def _json(
        self,
        method: str,
        path: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._call(method, path, json_body)
        if 300 <= int(response.status_code) < 400:
            raise RuntimeControlError("supervisor redirects are not permitted")
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            body = getattr(getattr(exc, "response", None), "text", "") or ""
            raise RuntimeControlError(f"supervisor HTTP error: {exc}: {body[:500]}") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeControlError("supervisor returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeControlError("supervisor payload must be an object")
        return payload


def _assign_job(pid: int) -> Any:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        JobObjectExtendedLimitInformation = 9
        if not kernel32.SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.CloseHandle(job)
            return None
        PROCESS_ALL_ACCESS = 0x1F0FFF
        handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not handle:
            kernel32.CloseHandle(job)
            return None
        assigned = kernel32.AssignProcessToJobObject(job, handle)
        kernel32.CloseHandle(handle)
        if not assigned:
            kernel32.CloseHandle(job)
            return None
        return job
    except Exception:
        return None
