from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterator

import requests

from .runtime_contracts import RuntimeControlError, validate_loopback_origin


SCHEMA = "sovereign.gpu-occupancy.v2"
DEFAULT_LLAMA_ORIGIN = "http://127.0.0.1:18080"
DEFAULT_FREETOKEN_ORIGIN = "http://127.0.0.1:1919"
OWNERS = frozenset({"llama.cpp", "freetoken"})

# In-process re-entrancy bookkeeping for transition_lock.
_HELD_LOCKS: dict[str, int] = {}
_HELD_LOCKS_GUARD = threading.Lock()

# Bounded drain windows: wait this long for owned active work to finish before a
# GPU ownership transition forces residency down. Transitions stay failure-aware:
# a drain timeout is recorded and the transition proceeds deliberately.
DRAIN_TIMEOUT_SECONDS = 30.0
DRAIN_POLL_SECONDS = 0.5
LOCK_WAIT_SECONDS = 180.0
LOCK_STALE_SECONDS = 300.0


def occupancy_path(root: Path) -> Path:
    return root / "runtime" / "gpu_occupancy.json"


def lock_path(root: Path) -> Path:
    return root / "runtime" / "gpu_occupancy.lock"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_occupancy(root: Path) -> dict[str, Any] | None:
    path = occupancy_path(root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def gpu_owner(root: Path) -> str | None:
    payload = read_occupancy(root)
    if payload is None:
        return None
    owner = str(payload.get("owner") or "").strip()
    return owner if owner in OWNERS else None


def write_occupancy(root: Path, owner: str, *, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    if owner not in OWNERS:
        raise RuntimeControlError(f"unknown GPU owner: {owner!r}")
    payload = {
        "schema": SCHEMA,
        "owner": owner,
        "updated_utc": _utc_now(),
        "detail": dict(detail or {}),
    }
    path = occupancy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def clear_occupancy(root: Path, owner: str) -> None:
    current = read_occupancy(root)
    if current is None:
        return
    if str(current.get("owner") or "") != owner:
        return
    path = occupancy_path(root)
    if path.is_file():
        path.unlink()


@contextmanager
def transition_lock(root: Path, owner: str) -> Iterator[None]:
    """Serialize GPU ownership transitions.

    One transition (drain -> release other residency -> acquire) at a time.
    Re-entrant within this process (claim paths stop/release the other runtime
    through the same lock). Stale locks (crashed holder) are taken over after
    LOCK_STALE_SECONDS so a failed transition cannot wedge recovery forever.
    """

    path = lock_path(root)
    key = str(path)
    with _HELD_LOCKS_GUARD:
        depth = _HELD_LOCKS.get(key, 0)
        _HELD_LOCKS[key] = depth + 1
    if depth > 0:
        try:
            yield
        finally:
            with _HELD_LOCKS_GUARD:
                _HELD_LOCKS[key] -= 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    fd: int | None = None
    try:
        while True:
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                stale = False
                try:
                    age = time.time() - path.stat().st_mtime
                    stale = age > LOCK_STALE_SECONDS
                except OSError:
                    stale = True
                if stale:
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise RuntimeControlError(
                        "GPU transition lock held too long; another ownership transition is in progress"
                    )
                time.sleep(0.25)
        os.write(fd, json.dumps({"owner": owner, "pid": os.getpid(), "utc": _utc_now()}).encode("utf-8"))
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            path.unlink()
        except OSError:
            pass
        with _HELD_LOCKS_GUARD:
            _HELD_LOCKS[key] -= 1


def _session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def llama_cpp_api_key(root: Path) -> str | None:
    env = str(os.environ.get("SOVEREIGN_LLAMA_CPP_API_KEY") or "").strip()
    if env:
        return env
    path = root / "runtime" / "llamacpp_supervisor" / "api_key"
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def _llama_origin(root: Path) -> str:
    return validate_loopback_origin(
        str(os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL") or DEFAULT_LLAMA_ORIGIN)
    )


def _llama_headers(root: Path) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = llama_cpp_api_key(root)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _llama_model_rows(session: requests.Session, origin: str, headers: dict[str, str]) -> list[dict[str, Any]] | None:
    """Return router /models rows, or None when the runtime is unreachable."""

    try:
        response = session.get(
            f"{origin}/models",
            headers=headers,
            timeout=(3.0, 10.0),
            allow_redirects=False,
        )
    except requests.RequestException:
        return None
    if int(response.status_code) != 200:
        raise RuntimeControlError(
            f"llama.cpp router returned HTTP {response.status_code} during GPU transition"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeControlError("llama.cpp router returned invalid JSON during GPU transition") from exc
    rows = payload.get("data") if isinstance(payload, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _llama_row_state(entry: dict[str, Any]) -> tuple[str, str]:
    identity = str(entry.get("id") or "").strip()
    status = entry.get("status")
    value = status.get("value") if isinstance(status, dict) else status
    return identity, str(value or "").strip().lower()


def unload_llama_cpp_gpu(root: Path, *, drain_timeout: float = DRAIN_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Drain owned active work, then release llama.cpp GPU model residency.

    Failure-aware: raises RuntimeControlError when models are still resident
    after the unload attempt, so the claiming transition aborts instead of
    starting a second engine on top of live VRAM.
    """

    origin = _llama_origin(root)
    headers = _llama_headers(root)
    session = _session()
    result: dict[str, Any] = {"origin": origin, "unloaded": [], "drained": True}
    rows = _llama_model_rows(session, origin, headers)
    if rows is None:
        result.update({"reachable": False, "reason": "router unreachable; no residency to release"})
        return result
    result["reachable"] = True

    # 1) Drain: wait for in-flight work to finish before forcing residency down.
    drain_deadline = time.monotonic() + max(0.0, drain_timeout)
    while True:
        busy = [
            identity
            for identity, state in (_llama_row_state(row) for row in rows)
            if identity and state == "busy"
        ]
        if not busy or time.monotonic() >= drain_deadline:
            result["busy_at_drain_end"] = busy
            result["drained"] = not busy
            if busy:
                result["drain_timeout"] = True
            break
        time.sleep(DRAIN_POLL_SECONDS)
        rows = _llama_model_rows(session, origin, headers)
        if rows is None:
            result.update({"reachable": False, "reason": "router went away during drain"})
            return result

    # 2) Release residency for every loaded/loading model.
    for row in rows:
        identity, state = _llama_row_state(row)
        if not identity or state not in {"loaded", "loading", "busy"}:
            continue
        try:
            response = session.post(
                f"{origin}/models/unload",
                json={"model": identity},
                headers=headers,
                timeout=(3.0, 30.0),
                allow_redirects=False,
            )
            result["unloaded"].append({"model": identity, "status": int(response.status_code)})
        except requests.RequestException as exc:
            result["unloaded"].append({"model": identity, "error": str(exc)})

    # 3) Verify: residency must actually be gone before another engine acquires.
    deadline = time.monotonic() + 15.0
    while True:
        rows = _llama_model_rows(session, origin, headers)
        if rows is None:
            result["verified"] = True
            result["verify_note"] = "router unreachable after unload; no residency"
            return result
        resident = [
            identity
            for identity, state in (_llama_row_state(row) for row in rows)
            if identity and state in {"loaded", "loading", "busy"}
        ]
        if not resident:
            result["verified"] = True
            return result
        if time.monotonic() >= deadline:
            raise RuntimeControlError(
                f"GPU transition aborted: llama.cpp models still resident after unload: {resident}"
            )
        time.sleep(DRAIN_POLL_SECONDS)


def _freetoken_origin(root: Path) -> str:
    from . import freetoken_service

    state = freetoken_service.read_state(root) or {}
    base_url = str(state.get("base_url") or "").strip()
    if base_url:
        return validate_loopback_origin(base_url)
    env = str(os.environ.get("SOVEREIGN_FREETOKEN_BASE_URL") or "").strip()
    return validate_loopback_origin(env or DEFAULT_FREETOKEN_ORIGIN)


def _freetoken_active_requests(origin: str) -> int | None:
    """In-flight request count from GET /v1/stats, or None when unavailable."""

    session = _session()
    try:
        response = session.get(
            f"{origin}/v1/stats",
            headers={"Accept": "application/json"},
            timeout=(3.0, 10.0),
            allow_redirects=False,
        )
    except requests.RequestException:
        return None
    if int(response.status_code) != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    requests_doc = payload.get("requests") if isinstance(payload, dict) else None
    if not isinstance(requests_doc, dict):
        return None
    try:
        return int(requests_doc.get("active") or 0)
    except (TypeError, ValueError):
        return None


def drain_freetoken(root: Path, *, drain_timeout: float = DRAIN_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Wait (bounded) for FreeToken's owned active requests to complete."""

    origin = _freetoken_origin(root)
    deadline = time.monotonic() + max(0.0, drain_timeout)
    active = _freetoken_active_requests(origin)
    result: dict[str, Any] = {"origin": origin, "initial_active": active}
    if active is None:
        result.update({"drained": None, "reason": "stats endpoint unavailable"})
        return result
    while active and time.monotonic() < deadline:
        time.sleep(DRAIN_POLL_SECONDS)
        active = _freetoken_active_requests(origin)
    result["final_active"] = active
    result["drained"] = not bool(active)
    if active:
        result["drain_timeout"] = True
    return result


def stop_freetoken_if_owned(
    root: Path,
    *,
    drain_timeout: float = DRAIN_TIMEOUT_SECONDS,
    intentional_stop: bool = False,
) -> dict[str, Any]:
    """Drain, then stop FreeToken so llama.cpp can acquire GPU resources.

    Failure-aware: raises when the process survives the stop attempt.
    """

    from . import freetoken_service

    status = freetoken_service.cmd_status(root)
    if not status.get("running"):
        return {"stopped": False, "reason": "not running"}
    drained = drain_freetoken(root, drain_timeout=drain_timeout)
    stopped = freetoken_service.cmd_stop(root, disable_autostart=not intentional_stop)
    if stopped.get("pid_alive"):
        raise RuntimeControlError(
            f"GPU transition aborted: freetoken PID {stopped.get('pid')} survived stop"
        )
    stopped["drain"] = drained
    stopped["intentional_stop_for_other_engine"] = True
    return stopped


def claim_gpu(root: Path, owner: str) -> dict[str, Any]:
    """Serialized, failure-aware GPU ownership transition.

    Drains the other runtime's owned active work, releases its GPU residency,
    then records ownership. Raises RuntimeControlError when residency cannot be
    released; no ownership is written on failure.
    """

    if owner not in OWNERS:
        raise RuntimeControlError(f"unknown GPU owner: {owner!r}")
    with transition_lock(root, owner):
        released: dict[str, Any] = {}
        if owner == "freetoken":
            released = unload_llama_cpp_gpu(root)
        elif owner == "llama.cpp":
            released = stop_freetoken_if_owned(root, intentional_stop=True)
        occupancy = write_occupancy(root, owner, detail={"released": released})
        return {"owner": owner, "occupancy": occupancy, "released": released}


def release_gpu(root: Path, owner: str) -> None:
    with transition_lock(root, owner):
        clear_occupancy(root, owner)
