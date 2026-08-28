from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from distillery.common import ContractError


ALLOWED_ITEM_STATUSES = {"UNASSESSED", "SELECTED_NEXT", "IN_PROGRESS", "CLOSED", "DEFERRED_EXTERNAL"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3", "P4"}
REQUIRED_LOOP_STATE_KEYS = {"loop_id", "iteration", "current_work_item", "last_successful_item", "checkpoint_timestamp"}
REQUIRED_PUNCH_KEYS = {"schema_version", "recorded_at", "items"}
REQUIRED_ITEM_KEYS = {"id", "title", "priority", "status"}
HEX40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
NULLABLE_STR_KEYS = (
    "current_phase",
    "terminal_disposition",
    "implementation_seal_commit",
    "evidence_commit",
    "verified_branch_head",
)


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be a parseable ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractError(f"{field} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def validate_loop_state(state: object) -> dict:
    if not isinstance(state, dict):
        raise ContractError("loop state must be an object")
    missing = REQUIRED_LOOP_STATE_KEYS - state.keys()
    if missing:
        raise ContractError(f"loop state missing keys: {sorted(missing)}")
    if isinstance(state["iteration"], bool) or not isinstance(state["iteration"], int) or state["iteration"] < 0:
        raise ContractError("loop state iteration must be a non-negative integer")
    for key in ("current_work_item", "last_successful_item"):
        value = state[key]
        if value is not None and (not isinstance(value, str) or not value):
            raise ContractError(f"loop state {key} must be null or a non-empty string")
    _parse_utc(state["checkpoint_timestamp"], "checkpoint_timestamp")
    for key in NULLABLE_STR_KEYS:
        if key in state:
            value = state[key]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ContractError(f"loop state {key} must be null or a non-empty string")
    for key in ("implementation_seal_commit", "evidence_commit", "verified_branch_head"):
        value = state.get(key)
        if value is not None and not HEX40_PATTERN.match(value):
            raise ContractError(f"loop state {key} must be null (unbound) or a full 40-hex commit sha")
    regression = state.get("last_full_regression")
    if regression is not None:
        if not isinstance(regression, dict):
            raise ContractError("loop state last_full_regression must be an object")
        measured = regression.get("measured_at_commit")
        if measured is not None and not (isinstance(measured, str) and HEX40_PATTERN.match(measured)):
            raise ContractError(
                "loop state last_full_regression.measured_at_commit must be null (unbound) or a full 40-hex commit sha"
            )
    for key in ("open_critical_findings", "open_high_findings"):
        if key in state:
            value = state[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractError(f"loop state {key} must be a non-negative integer")
    if state.get("terminal_verified_at") is not None:
        _parse_utc(state["terminal_verified_at"], "terminal_verified_at")
    return state


def validate_punch_list(document: object) -> dict:
    if not isinstance(document, dict):
        raise ContractError("punch list must be an object")
    missing = REQUIRED_PUNCH_KEYS - document.keys()
    if missing:
        raise ContractError(f"punch list missing keys: {sorted(missing)}")
    items = document["items"]
    if not isinstance(items, list) or not items:
        raise ContractError("punch list items must be a non-empty list")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ContractError("punch item must be an object")
        item_missing = REQUIRED_ITEM_KEYS - item.keys()
        if item_missing:
            raise ContractError(f"punch item missing keys: {sorted(item_missing)}")
        if item["status"] not in ALLOWED_ITEM_STATUSES:
            raise ContractError(f"invalid punch status: {item['status']!r}")
        if item["priority"] not in ALLOWED_PRIORITIES:
            raise ContractError(f"invalid punch priority: {item['priority']!r}")
        if item["id"] in seen:
            raise ContractError(f"duplicate punch item id: {item['id']}")
        seen.add(item["id"])
    _parse_utc(document["recorded_at"], "recorded_at")
    return document


def load_json(path: str | Path) -> dict:
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ContractError(f"missing state file: {target}") from None
    except UnicodeDecodeError as exc:
        raise ContractError(f"undecodable state file {target}: {exc}") from None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError(f"corrupt state file {target}: {exc}") from None


def _pid_alive(pid: int) -> bool:
    """Existence probe that never signals or terminates the target.

    Windows note: os.kill(pid, 0) does NOT probe there - any non-CTRL signal
    maps to TerminateProcess, so sys.platform routing is mandatory.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        ERROR_INVALID_PARAMETER = 87
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return kernel32.GetLastError() != ERROR_INVALID_PARAMETER
        exit_code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        kernel32.CloseHandle(handle)
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class StateFileLock:
    """Exclusive O_EXCL lock with deterministic stale-owner takeover.

    A lock left behind by a dead process is recovered; a lock held by a live
    process fails closed with an actionable error. Never auto-deletes a live
    competitor's lock.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def __enter__(self) -> "StateFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                self._handle_existing()
                continue
            try:
                os.write(descriptor, json.dumps({"pid": os.getpid(), "acquired_at": utc_now()}).encode())
            finally:
                os.close(descriptor)
            return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.path.unlink(missing_ok=True)

    def _handle_existing(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(payload.get("pid", -1))
        except (json.JSONDecodeError, ValueError, OSError):
            pid = -1
        if pid == -1 or not _pid_alive(pid):
            self.path.unlink(missing_ok=True)
            return
        raise ContractError(f"state file lock held by live pid {pid}: {self.path}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def update_json_atomically(path: str | Path, mutator: Callable[[dict], dict], *, validator: Callable[[object], dict]) -> dict:
    """Locked read-validate-mutate-validate-write with atomic replace.

    Post-mutation validation failure leaves the file untouched. Concurrent live
    writers fail closed instead of silently clobbering.
    """
    target = Path(path)
    lock_path = target.with_name(target.name + ".lock")
    tmp_path = target.with_name(target.name + ".tmp")
    with StateFileLock(lock_path):
        current = validator(load_json(target))
        updated = validator(mutator(current))
        tmp_path.unlink(missing_ok=True)
        encoded = json.dumps(updated, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        descriptor = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(descriptor, encoded.encode("utf-8"))
        finally:
            os.close(descriptor)
        os.replace(tmp_path, target)
    return updated
