from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
import os
import subprocess
import sys
import time

import requests

from .runtime_contracts import RuntimeControlError, RuntimeInventory, validate_loopback_origin
from .runtime_supervisor import (
    CREATE_NEW_PROCESS_GROUP,
    CREATE_NO_WINDOW,
    _assign_job,
)


@dataclass(frozen=True)
class FreeTokenSupervisorConfig:
    executable: str
    model_path: str
    host: str = "127.0.0.1"
    port: int = 1919
    work_dir: str = ""
    extra_args: tuple[str, ...] = ()
    ready_timeout_seconds: float = 180.0
    cuda_home: str | None = None
    served_model_name: str | None = None
    memory_ratio: float = 0.35
    max_seq_len: int | None = 2048
    max_running_requests: int = 1
    dummy_weight: bool = False


class FreeTokenSupervisor:
    def __init__(
        self,
        config: FreeTokenSupervisorConfig,
        *,
        popen: Callable[..., Any] = subprocess.Popen,
        request_session: requests.Session | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if config.host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeControlError("supervisor must bind loopback only")
        self.config = config
        self._popen = popen
        self._session = request_session or requests.Session()
        if request_session is None:
            self._session.trust_env = False
        self._monotonic = monotonic
        self._sleep = sleep
        self.base_url = validate_loopback_origin(f"http://{config.host}:{config.port}")
        self.process: Any | None = None
        self.pid: int | None = None
        self.log_path: Path | None = None
        self._log_handle: Any | None = None
        self._job = None
        work = Path(config.work_dir) if config.work_dir else Path.cwd() / "runtime_freetoken"
        self.work_dir = work

    def command(self, model_path: str | None = None) -> list[str]:
        model = model_path or self.config.model_path
        name = self.config.served_model_name or Path(model).name
        args = [
            self.config.executable,
            "serve",
            "--model",
            model,
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
            "--cors-origins",
            "localhost",
            "--memory-ratio",
            str(self.config.memory_ratio),
            "--max-running-requests",
            str(self.config.max_running_requests),
            "--served-model-name",
            name,
        ]
        if self.config.max_seq_len is not None:
            args.extend(["--max-seq-len-override", str(self.config.max_seq_len)])
        if self.config.dummy_weight:
            args.append("--dummy-weight")
        args.extend(self.config.extra_args)
        return args

    def start(self) -> None:
        if self.process is not None and getattr(self.process, "poll", lambda: None)() is None:
            raise RuntimeControlError("supervisor already owns a running process")
        self._assert_port_free()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.work_dir / "freetoken-server.log"
        command = self.command()
        self._log_handle = self.log_path.open("w", encoding="utf-8")
        env = os.environ.copy()
        if self.config.cuda_home:
            env["CUDA_HOME"] = self.config.cuda_home
            env["CUDA_PATH"] = self.config.cuda_home
        kwargs: dict[str, Any] = {
            "cwd": str(self.work_dir),
            "stdout": self._log_handle,
            "stderr": subprocess.STDOUT,
            "env": env,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        self.process = self._popen(command, **kwargs)
        self.pid = int(getattr(self.process, "pid"))
        self._job = _assign_job(self.pid)
        try:
            deadline = self._monotonic() + self.config.ready_timeout_seconds
            while self._monotonic() < deadline:
                if getattr(self.process, "poll", lambda: None)() is not None:
                    raise RuntimeControlError("freetoken supervisor process exited during start")
                if self.ready():
                    return
                self._sleep(0.25)
            raise RuntimeControlError("freetoken supervisor did not become ready")
        except Exception:
            self.stop()
            raise

    def ready(self) -> bool:
        if self.process is None or getattr(self.process, "poll", lambda: 0)() is not None:
            return False
        if "API server is ready to serve" not in self.logs():
            return False
        try:
            response = self._call("GET", "/v1/models")
        except (RuntimeControlError, requests.RequestException, OSError, TimeoutError):
            return False
        return int(getattr(response, "status_code", 0)) == 200

    def inventory(self) -> RuntimeInventory:
        payload = self._json("GET", "/v1/models")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise RuntimeControlError("inventory payload missing data")
        loaded = []
        for entry in rows:
            if not isinstance(entry, Mapping):
                continue
            identity = str(entry.get("id") or "").strip()
            if identity:
                loaded.append(identity)
        return RuntimeInventory(
            registered=tuple(loaded),
            available=tuple(loaded),
            loaded=tuple(loaded),
            raw=payload,
        )

    def load(self, model: str) -> dict[str, Any]:
        current = self.inventory()
        if model in current.loaded:
            return {"success": True, "already_loaded": True, "model": model}
        raise RuntimeControlError("freetoken serves one process-resident model; restart to change")

    def unload(self, model: str) -> dict[str, Any]:
        raise RuntimeControlError("freetoken unload requires process stop")

    def switch(self, model_path: str, *, timeout_seconds: float = 180.0) -> dict[str, Any]:
        del timeout_seconds
        self.stop()
        self.config = FreeTokenSupervisorConfig(**{**self.config.__dict__, "model_path": model_path})
        self.start()
        return {"success": True, "loaded": self.inventory().loaded}

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
        import socket

        with socket.socket() as sock:
            if sock.connect_ex((self.config.host, self.config.port)) == 0:
                raise RuntimeControlError(f"loopback port {self.config.port} is occupied")

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
                headers={"Content-Type": "application/json", "Accept": "application/json"},
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
        except ValueError as exc:
            raise RuntimeControlError("supervisor returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeControlError("supervisor payload must be an object")
        return payload
