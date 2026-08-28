from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from distillery.common import ContractError, utc_now


class TrainerCardLock:
    def __init__(self, path: str | Path, *, expected_gpu: str, minimum_free_vram_mib: int, probe: Callable[[], dict], drain_serving: Callable[[], None], restore_serving: Callable[[], None]) -> None:
        self.path = Path(path)
        self.expected_gpu = expected_gpu
        self.minimum_free_vram_mib = minimum_free_vram_mib
        self.probe = probe
        self.drain_serving = drain_serving
        self.restore_serving = restore_serving
        self.pre_snapshot: dict | None = None
        self.post_snapshot: dict | None = None

    def __enter__(self) -> "TrainerCardLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ContractError("exclusive trainer-card lock is already held") from exc
        try:
            os.write(descriptor, json.dumps({"pid": os.getpid(), "acquired_at": utc_now()}).encode())
        finally:
            os.close(descriptor)
        try:
            self.drain_serving()
            self.pre_snapshot = self.probe()
            self._validate_snapshot(self.pre_snapshot)
            return self
        except Exception:
            self._release()
            raise

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.post_snapshot = self.probe()
        self._release()

    def _validate_snapshot(self, snapshot: dict) -> None:
        if snapshot.get("gpu_identity") != self.expected_gpu:
            raise ContractError("GPU identity mismatch")
        if snapshot.get("free_vram_mib", -1) < self.minimum_free_vram_mib:
            raise ContractError("required free VRAM is unavailable")
        if snapshot.get("conflicting_compute_processes"):
            raise ContractError("unexpected conflicting GPU process")

    def _release(self) -> None:
        self.restore_serving()
        self.path.unlink(missing_ok=True)
