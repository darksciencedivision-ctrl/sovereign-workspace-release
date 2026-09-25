"""Evidence-backed, deterministic SOVEREIGN self-introspection.

This module reports only machine-observable state.  It reads live manifests on
every call, distinguishes configured/installed/loaded model state, and never
uses prose status documents as runtime authority.  Network probes are optional,
loopback-only, individually bounded below two seconds, and injectable.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import socket
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from .manifest_overrides import (
    OVERRIDES_RELATIVE,
    ManifestOverrideError,
    effective_manifest,
    manifest_digest,
    overrides_path,
)
from .paths import (
    PathResolutionError,
    ProductPaths,
    UnsafeArtifactPointer,
    resolve_product_paths,
)


HttpGetter = Callable[[str, float], Any]
SELF_STATE_SCHEMA = "sovereign.self_state.v1"
DEFAULT_NETWORK_TIMEOUT = 0.75
MAX_NETWORK_TIMEOUT = 1.99
LLAMA_CPP_DEFAULT_BASE_URL = "http://127.0.0.1:18080"
FREETOKEN_DEFAULT_BASE_URL = "http://127.0.0.1:1919"
LLAMA_CPP_LABEL = "The llama.cpp router"
OLLAMA_LABEL = "Ollama"
_TERMINAL_CYCLE_STATUSES = {
    "completed": "completed",
    "rejected": "rejected",
    "concurrence_not_reached": "rejected",
    "failed": "failed",
}


def _pointer(paths: ProductPaths, path: Path) -> str | None:
    try:
        return paths.pointer(path)
    except (PathResolutionError, UnsafeArtifactPointer):
        return None


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "unreadable"
    if not isinstance(payload, dict):
        return None, "not_an_object"
    return payload, None


def _read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, UnicodeError):
        return None, "unreadable"


def _extract_constant(path: Path, name: str) -> str | None:
    text, error = _read_text(path)
    if error or text is None:
        return None
    match = re.search(
        rf"^\s*(?:export\s+const\s+)?{re.escape(name)}\s*=\s*[\"']([^\"']+)[\"']",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1) if match else None


def _loopback_base_url(url: str) -> tuple[str | None, str | None]:
    try:
        parsed = urlsplit(str(url).strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "http" or not host or parsed.username or parsed.password:
            return None, "invalid_or_non_http_url"
        if parsed.query or parsed.fragment:
            return None, "url_metadata_not_allowed"
        if host != "localhost":
            try:
                if not ipaddress.ip_address(host).is_loopback:
                    return None, "non_loopback_blocked"
            except ValueError:
                return None, "non_loopback_blocked"
        # Accessing .port validates the port syntax.
        _ = parsed.port
    except (TypeError, ValueError):
        return None, "invalid_url"
    return str(url).rstrip("/"), None


def _default_http_get(url: str, timeout: float) -> Any:
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host")
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError("response_too_large")
        if response.status < 200 or response.status >= 300:
            raise OSError(f"http_status_{response.status}")
        return json.loads(data.decode("utf-8"))
    finally:
        connection.close()


def _coerce_http_json(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return parsed
    json_method = getattr(value, "json", None)
    if callable(json_method):
        parsed = json_method()
        if isinstance(parsed, Mapping):
            return parsed
    raise ValueError("HTTP getter did not return a JSON object")


def _model_names(payload: Mapping[str, Any]) -> list[str]:
    raw_models = payload.get("models")
    if not isinstance(raw_models, Sequence) or isinstance(raw_models, (str, bytes)):
        return []
    names: set[str] = set()
    for item in raw_models:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return sorted(names)


def _probe_ollama(
    base_url: str | None,
    *,
    configured_models: Iterable[str],
    http_get: HttpGetter | None,
    timeout: float,
) -> dict[str, Any]:
    if not 0 < float(timeout) < 2:
        raise ValueError("Each network timeout must be greater than zero and below two seconds")

    configured = sorted({str(model).strip() for model in configured_models if str(model).strip()})
    if not base_url:
        return {
            "base_url": None,
            "loopback_only": True,
            "reachable": False,
            "probe_status": "not_configured",
            "configured_models": configured,
            "installed_models": None,
            "loaded_models": None,
            "currently_running_models": None,
            "model_states": [
                {
                    "name": model,
                    "configured": True,
                    "installed": None,
                    "loaded": None,
                    "currently_running": None,
                }
                for model in configured
            ],
            "activity_observable": False,
            "activity_note": "/api/ps proves residency, not an active generation request.",
        }

    trusted_base, blocked_reason = _loopback_base_url(base_url)
    if blocked_reason or trusted_base is None:
        return {
            "base_url": base_url,
            "loopback_only": True,
            "reachable": False,
            "probe_status": blocked_reason,
            "configured_models": configured,
            "installed_models": None,
            "loaded_models": None,
            "currently_running_models": None,
            "model_states": [
                {
                    "name": model,
                    "configured": True,
                    "installed": None,
                    "loaded": None,
                    "currently_running": None,
                }
                for model in configured
            ],
            "activity_observable": False,
            "activity_note": "A non-loopback Ollama URL is never probed.",
        }

    getter = http_get or _default_http_get

    def probe(path: str) -> tuple[list[str] | None, str | None]:
        try:
            response = getter(trusted_base + path, float(timeout))
            return _model_names(_coerce_http_json(response)), None
        except Exception as exc:  # network and injected probe failures are state, not crashes
            return None, type(exc).__name__

    installed, tags_error = probe("/api/tags")
    loaded, ps_error = probe("/api/ps")
    installed_set = set(installed or ())
    loaded_set = set(loaded or ())
    all_names = sorted(set(configured) | installed_set | loaded_set)
    model_states = [
        {
            "name": model,
            "configured": model in configured,
            "installed": None if installed is None else model in installed_set,
            "loaded": None if loaded is None else model in loaded_set,
            # Ollama exposes residency through /api/ps, not request activity.
            "currently_running": None,
        }
        for model in all_names
    ]
    if installed is None and loaded is None:
        probe_status = "offline"
    elif installed is None or loaded is None:
        probe_status = "partial"
    else:
        probe_status = "online"
    return {
        "base_url": trusted_base,
        "loopback_only": True,
        "reachable": installed is not None or loaded is not None,
        "probe_status": probe_status,
        "tags_reachable": installed is not None,
        "process_state_reachable": loaded is not None,
        "tags_error_type": tags_error,
        "process_state_error_type": ps_error,
        "configured_models": configured,
        "installed_models": installed,
        "loaded_models": loaded,
        "currently_running_models": None,
        "model_states": model_states,
        "activity_observable": False,
        "activity_note": (
            "/api/tags means installed; /api/ps means loaded/resident. "
            "Neither endpoint proves an active generation request."
        ),
    }


def _unknown_model_states(configured: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": model,
            "configured": True,
            "installed": None,
            "loaded": None,
            "currently_running": None,
        }
        for model in configured
    ]


def _parse_models_ini(path: Path) -> list[dict[str, str | None]] | None:
    """Parse the llama.cpp router preset into [{id, alias, model}] entries."""

    text, error = _read_text(path)
    if error or text is None:
        return None
    entries: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            name = stripped[1:-1].strip()
            current = {"id": name or None, "alias": None, "model": None}
            if name and name != "*":
                entries.append(current)
            else:
                current = None
            continue
        if current is None:
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        field = key.strip().lower()
        if field == "alias":
            current["alias"] = value.strip() or None
        elif field == "model":
            current["model"] = value.strip() or None
    return entries


def _resolve_introspection_backend(paths: ProductPaths) -> str:
    """Effective local backend, resolved without importing runtime modules.

    Mirrors runtime_contracts/backend_selection precedence: explicit
    SOVEREIGN_INFERENCE_BACKEND env, then runtime/backend_selection.json,
    then the factory default (llama.cpp).
    """

    def normalize(value: str) -> str:
        selected = value.strip().lower()
        if selected == "ollama":
            return "ollama"
        if selected in {"freetoken", "free-token", "free_token"}:
            return "freetoken"
        return "llama.cpp"

    env = str(os.environ.get("SOVEREIGN_INFERENCE_BACKEND") or "").strip()
    if env:
        return normalize(env)
    payload, _error = _read_json(paths.state_dir / "backend_selection.json")
    if isinstance(payload, dict):
        selected = str(payload.get("default_backend") or "").strip()
        if selected:
            return normalize(selected)
    return "llama.cpp"


def _tcp_listening(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=min(max(float(timeout), 0.05), 2.0)):
            return True
    except OSError:
        return False


def _llama_models_http(base_url: str, api_key: str | None, timeout: float) -> tuple[list[Any] | None, str | None]:
    """GET /models on the llama.cpp router with header auth (key never in URL)."""

    parsed = urlsplit(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    connection = http.client.HTTPConnection(host, port, timeout=min(max(float(timeout), 0.05), 2.0))
    try:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        connection.request("GET", parsed.path or "/models", headers=headers)
        response = connection.getresponse()
        data = response.read(1_000_001)
        if response.status != 200:
            return None, f"http_status_{response.status}"
        payload = json.loads(data.decode("utf-8"))
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return [], None
        return rows, None
    except Exception as exc:  # network failures are state, not crashes
        return None, type(exc).__name__
    finally:
        connection.close()


def _probe_llama_cpp(
    paths: ProductPaths,
    *,
    configured_models: Iterable[str],
    timeout: float,
) -> dict[str, Any]:
    """Loopback probe of the llama.cpp supervisor router (backend-aware health).

    Gated on supervisor artifacts: without <root>/runtime/llamacpp_supervisor
    (models.ini preset or state.json) the probe reports not_configured and
    performs no network I/O, so roots without the llama.cpp deployment keep
    the historical Ollama-probe behavior.
    """

    configured = sorted({str(model).strip() for model in configured_models if str(model).strip()})
    supervisor_dir = paths.state_dir / "llamacpp_supervisor"
    preset = _parse_models_ini(supervisor_dir / "models.ini")
    state_payload, _state_error = _read_json(supervisor_dir / "state.json")
    if preset is None and state_payload is None:
        return {
            "service": "llama.cpp",
            "base_url": None,
            "loopback_only": True,
            "reachable": False,
            "probe_status": "not_configured",
            "configured_models": configured,
            "installed_models": None,
            "loaded_models": None,
            "currently_running_models": None,
            "model_states": _unknown_model_states(configured),
            "activity_observable": False,
            "activity_note": (
                "No llama.cpp supervisor preset or state under runtime/llamacpp_supervisor."
            ),
        }

    base_url = (
        str(os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL") or "").strip()
        or LLAMA_CPP_DEFAULT_BASE_URL
    )
    trusted_base, blocked_reason = _loopback_base_url(base_url)
    if blocked_reason or trusted_base is None:
        return {
            "service": "llama.cpp",
            "base_url": base_url,
            "loopback_only": True,
            "reachable": False,
            "probe_status": blocked_reason,
            "configured_models": configured,
            "installed_models": None,
            "loaded_models": None,
            "currently_running_models": None,
            "model_states": _unknown_model_states(configured),
            "activity_observable": False,
            "activity_note": "A non-loopback llama.cpp URL is never probed.",
        }

    parsed = urlsplit(trusted_base)
    listening = _tcp_listening(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout)

    registered: set[str] = set()
    installed: set[str] = set()
    for entry in preset or []:
        names = [name for name in (entry.get("id"), entry.get("alias")) if name]
        registered.update(names)
        model_file = str(entry.get("model") or "").strip()
        if model_file and Path(model_file).is_file():
            installed.update(names)

    # The same key the product's client sends, so "reachable" here means reachable for it.
    from .runtime_contracts import resolve_llama_cpp_api_key

    api_key = resolve_llama_cpp_api_key(paths.state_dir, trusted_base)[0]
    loaded: list[str] | None = None
    models_error: str | None = None
    rows: list[Any] | None = None
    if listening:
        rows, models_error = _llama_models_http(trusted_base, api_key, timeout)
        if rows is not None:
            loaded = []
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                identity = str(row.get("id") or "").strip()
                # The router lists a preset's aliases (the configured model names, e.g.
                # "qwen3:30b-a3b") as a list; older builds used a single "alias".
                raw_aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
                aliases = {str(a).strip() for a in [*raw_aliases, row.get("alias")]
                           if a is not None and str(a).strip()}
                if identity:
                    installed.add(identity)
                installed.update(aliases)
                status = row.get("status")
                value = status.get("value") if isinstance(status, Mapping) else status
                if identity and str(value or "").strip().lower() in {"loaded", "loading", "busy"}:
                    loaded.append(identity)
                    loaded.extend(aliases)
            loaded = sorted(set(loaded))

    if not listening and rows is None:
        probe_status = "offline"
    elif rows is None:
        probe_status = "partial"
    else:
        probe_status = "online"
    installed_models = sorted(installed) if (installed or registered) else None
    if installed_models is None and preset:
        installed_models = []
    all_names = sorted(set(configured) | set(installed_models or []) | set(loaded or []))
    installed_set = set(installed_models or ())
    loaded_set = set(loaded or ())
    return {
        "service": "llama.cpp",
        "base_url": trusted_base,
        "loopback_only": True,
        "reachable": bool(listening or rows is not None),
        "listening": listening,
        "probe_status": probe_status,
        "models_endpoint_error_type": models_error,
        "configured_models": configured,
        "registered_models": sorted(registered),
        "installed_models": installed_models,
        "loaded_models": loaded,
        "currently_running_models": None,
        "supervisor_pid": (state_payload or {}).get("pid") if isinstance(state_payload, Mapping) else None,
        "model_states": [
            {
                "name": model,
                "configured": model in configured,
                "installed": None if installed_models is None else model in installed_set,
                "loaded": None if loaded is None else model in loaded_set,
                "currently_running": None,
            }
            for model in all_names
        ],
        "activity_observable": False,
        "activity_note": (
            "Router /models proves registration and residency, not an active generation request."
        ),
    }


def _probe_freetoken(paths: ProductPaths, *, timeout: float) -> dict[str, Any]:
    """File/loopback state of the on-demand FreeToken supervisor (informational)."""

    supervisor_dir = paths.state_dir / "freetoken_supervisor"
    state_payload, state_error = _read_json(supervisor_dir / "state.json")
    autostart = (supervisor_dir / "AUTOSTART").is_file()
    if state_payload is None:
        return {
            "service": "freetoken",
            "configured": state_error is None and autostart,
            "running": False,
            "listening": False,
            "pid": None,
            "profile": None,
            "base_url": None,
            "autostart": autostart,
            "state_error": state_error,
            "activity_note": "No FreeToken supervisor state; on-demand runtime is not started.",
        }
    base_url = str(state_payload.get("base_url") or "").strip() or FREETOKEN_DEFAULT_BASE_URL
    trusted_base, blocked_reason = _loopback_base_url(base_url)
    listening = False
    if blocked_reason is None and trusted_base is not None:
        parsed = urlsplit(trusted_base)
        listening = _tcp_listening(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout)
    return {
        "service": "freetoken",
        "configured": True,
        "running": bool(listening),
        "listening": listening,
        "pid": state_payload.get("pid"),
        "profile": state_payload.get("profile"),
        "base_url": trusted_base,
        "base_url_blocked_reason": blocked_reason,
        "autostart": autostart,
        "started_utc": state_payload.get("started_utc"),
        "activity_note": (
            "Listening proves the on-demand server socket, not model readiness or active work."
        ),
    }


def model_service_authority(snapshot: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    """(label, probe) of the authoritative local model service in a snapshot.

    Falls back to the Ollama probe for snapshots without backend-aware keys or
    roots where the llama.cpp supervisor is not configured.
    """

    service = (
        snapshot.get("model_service")
        if isinstance(snapshot.get("model_service"), Mapping)
        else {}
    )
    authority = str(service.get("authority") or "").strip().lower()
    if authority == "llama.cpp":
        probe = snapshot.get("llama_cpp")
        if isinstance(probe, Mapping):
            return LLAMA_CPP_LABEL, probe
    ollama = snapshot.get("ollama")
    return OLLAMA_LABEL, (ollama if isinstance(ollama, Mapping) else {})


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "<depth-limit>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item, depth=depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item, depth=depth + 1) for item in value[:1000]]
    return str(value)


def _call_optional(store: Any, names: Sequence[str], *args: Any, **kwargs: Any) -> Any:
    for name in names:
        member = getattr(store, name, None)
        if callable(member):
            return member(*args, **kwargs)
        if member is not None and not args and not kwargs:
            return member
    return None


def _store_state(store: Any | None) -> dict[str, Any]:
    if store is None:
        return {
            "available": False,
            "durable": False,
            "summary": {},
            "job_counts": {},
            "running_jobs": None,
            "session_count": None,
            "meta": {},
            "errors": [],
        }

    errors: list[str] = []
    raw_summary: Any = {}
    try:
        raw_summary = _call_optional(
            store, ("summary", "get_summary", "status_summary")
        )
    except Exception as exc:
        errors.append(f"summary:{type(exc).__name__}")
    summary = dict(raw_summary) if isinstance(raw_summary, Mapping) else {}

    jobs: list[Mapping[str, Any]] = []
    try:
        raw_jobs = _call_optional(store, ("list_jobs",))
        if isinstance(raw_jobs, Mapping):
            raw_jobs = raw_jobs.get("jobs")
        if isinstance(raw_jobs, Sequence) and not isinstance(raw_jobs, (str, bytes)):
            jobs = [job for job in raw_jobs if isinstance(job, Mapping)]
    except Exception as exc:
        errors.append(f"list_jobs:{type(exc).__name__}")

    counts: Counter[str] = Counter()
    for job in jobs:
        status = str(job.get("status") or job.get("phase") or "unknown").strip().lower()
        outcome = str(job.get("outcome") or "").strip().lower()
        counts[outcome if status == "terminal" and outcome else status] += 1

    summary_counts = summary.get("job_counts")
    if not counts and isinstance(summary_counts, Mapping):
        for key, value in summary_counts.items():
            try:
                counts[str(key).lower()] = int(value)
            except (TypeError, ValueError):
                continue
    if not counts and isinstance(summary.get("jobs"), Mapping):
        for key, value in summary["jobs"].items():
            try:
                counts[str(key).lower()] = int(value)
            except (TypeError, ValueError):
                continue

    running = counts.get("running")
    if not counts and isinstance(summary.get("running_jobs"), int):
        running = int(summary["running_jobs"])
    elif not counts and isinstance(summary.get("active_jobs"), int):
        running = int(summary["active_jobs"])

    session_count: int | None = None
    for key in ("session_count", "sessions"):
        value = summary.get(key)
        if isinstance(value, int):
            session_count = value
            break
        if isinstance(value, Mapping) and isinstance(value.get("count"), int):
            session_count = int(value["count"])
            break
    if session_count is None:
        try:
            raw_sessions = _call_optional(store, ("list_sessions",))
            if isinstance(raw_sessions, Sequence) and not isinstance(raw_sessions, (str, bytes)):
                session_count = len(raw_sessions)
        except Exception as exc:
            errors.append(f"list_sessions:{type(exc).__name__}")

    meta: dict[str, Any] = {}
    list_meta = getattr(store, "list_meta", None)
    if callable(list_meta):
        try:
            raw_meta = list_meta()
            if isinstance(raw_meta, Mapping):
                meta.update(raw_meta)
            elif isinstance(raw_meta, Sequence) and not isinstance(raw_meta, (str, bytes)):
                for item in raw_meta:
                    if isinstance(item, Mapping) and item.get("key") is not None:
                        meta[str(item["key"])] = item.get("value")
        except Exception as exc:
            errors.append(f"list_meta:{type(exc).__name__}")

    get_meta = getattr(store, "get_meta", None)
    if callable(get_meta):
        try:
            raw_meta = get_meta()
            if isinstance(raw_meta, Mapping):
                meta.update(raw_meta)
        except TypeError:
            for key in ("schema_version", "store_version", "created_utc"):
                try:
                    value = get_meta(key)
                except Exception:
                    continue
                if value is not None:
                    meta[key] = value
        except Exception as exc:
            errors.append(f"get_meta:{type(exc).__name__}")

    db_path = getattr(store, "db_path", None)
    durable = bool(
        summary.get("durable")
        if "durable" in summary
        else db_path is not None or meta.get("schema_version") is not None
    )
    return {
        "available": True,
        "durable": durable,
        "summary": _json_safe(summary),
        "job_counts": dict(sorted(counts.items())),
        "running_jobs": running if counts or running else 0,
        "session_count": session_count,
        "meta": _json_safe(meta),
        "errors": sorted(set(errors)),
    }


def _cycle_record(path: Path, paths: ProductPaths) -> dict[str, Any] | None:
    record, error = _read_json(path)
    if error or record is None:
        return None
    status = str(record.get("status") or "").strip().lower()
    if not status:
        return None
    ended_at = str(
        record.get("ended_at")
        or record.get("finished_at")
        or record.get("timestamp")
        or record.get("started_at")
        or ""
    )
    return {
        "session_id": str(record.get("session_id") or ""),
        "status": status,
        "category": _TERMINAL_CYCLE_STATUSES.get(status, "other"),
        "ended_at": ended_at,
        "failure_reason": (
            str(record.get("failure_reason")) if record.get("failure_reason") else None
        ),
        "source": _pointer(paths, path),
        "_sort_key": (ended_at, path.name),
    }


def _cycle_state(paths: ProductPaths) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    runs_dir = paths.root / "runs"
    try:
        candidates = sorted(runs_dir.glob("cycle-*.json"))
    except OSError:
        candidates = []
    for candidate in candidates:
        record = _cycle_record(candidate, paths)
        if record is not None:
            records.append(record)
    records.sort(key=lambda item: item["_sort_key"])

    counts = Counter(record["status"] for record in records)

    def last(category: str) -> dict[str, Any] | None:
        matches = [record for record in records if record["category"] == category]
        if not matches:
            return None
        selected = dict(matches[-1])
        selected.pop("_sort_key", None)
        return selected

    last_terminal_candidates = [
        record for record in records if record["category"] in {"completed", "rejected", "failed"}
    ]
    last_terminal = None
    if last_terminal_candidates:
        last_terminal = dict(last_terminal_candidates[-1])
        last_terminal.pop("_sort_key", None)
    return {
        "record_count": len(records),
        "status_counts": dict(sorted(counts.items())),
        "last_completed": last("completed"),
        "last_rejected": last("rejected"),
        "last_failed": last("failed"),
        "last_terminal": last_terminal,
        "source": _pointer(paths, runs_dir),
    }


def _publication_state(paths: ProductPaths) -> dict[str, Any]:
    gate = paths.root / "publication_gate.py"
    domain = paths.root / "corpus" / "domain.txt"
    domain_text, domain_error = _read_text(domain)
    domain_configured = bool(domain_text and domain_text.strip())
    if not gate.is_file():
        mode = "UNAVAILABLE"
        reason = "publication gate is absent"
    elif not domain_configured:
        mode = "FAIL_CLOSED"
        reason = "domain corpus is missing or empty"
    else:
        mode = "MANUAL_GATED"
        reason = "domain corpus exists; publication remains an explicit gated action"
    return {
        "mode": mode,
        "automatic": False,
        "gate_present": gate.is_file(),
        "domain_configured": domain_configured,
        "reason": reason,
        "domain_read_error": domain_error,
        "sources": [_pointer(paths, gate), _pointer(paths, domain)],
    }


def _constitution_state(paths: ProductPaths) -> dict[str, Any]:
    source = paths.root / "constitution" / "constitution_state.json"
    payload, error = _read_json(source)
    mode = "UNKNOWN"
    if payload and isinstance(payload.get("mode"), str):
        mode = str(payload["mode"]).strip().upper() or "UNKNOWN"
    return {
        "mode": mode,
        "read_error": error,
        "source": _pointer(paths, source),
    }


def _component_state(paths: ProductPaths, manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    runner = paths.root / "cycle_runner_v3.py"
    orchestrator = paths.root / "synthesis" / "live_orchestrator.py"
    quality_gate = paths.root / "quality_gate.py"
    arbitrator = paths.root / "claim_arbitrator.py"
    adapter = paths.root / "ui" / "adapter_service" / "adapter.py"
    ui_version_file = paths.root / "ui" / "ui_shell" / "src" / "version.ts"
    ui_dist = paths.root / "ui" / "ui_shell" / "dist" / "index.html"
    engine_version = None
    if manifest and manifest.get("ARCHIVE_VERSION") is not None:
        engine_version = str(manifest["ARCHIVE_VERSION"])
    return {
        "engine": {
            "version": engine_version,
            "runner_present": runner.is_file(),
            "orchestrator_present": orchestrator.is_file(),
            "quality_gate_present": quality_gate.is_file(),
            "arbitrator_present": arbitrator.is_file(),
            "sources": {
                "manifest": _pointer(paths, paths.root / "SYSTEM_MANIFEST.json"),
                "runner": _pointer(paths, runner),
                "orchestrator": _pointer(paths, orchestrator),
                "quality_gate": _pointer(paths, quality_gate),
                "arbitrator": _pointer(paths, arbitrator),
            },
        },
        "adapter": {
            "present": adapter.is_file(),
            "version": _extract_constant(adapter, "ADAPTER_VERSION"),
            "source": _pointer(paths, adapter),
        },
        "ui": {
            "source_present": ui_version_file.is_file(),
            "dist_present": ui_dist.is_file(),
            "version": _extract_constant(ui_version_file, "APP_VERSION"),
            "sources": {
                "version": _pointer(paths, ui_version_file),
                "dist": _pointer(paths, ui_dist),
            },
        },
    }


def _configuration_warnings(
    paths: ProductPaths,
    manifest: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    adapter_config_path = paths.root / "ui" / "adapter_service" / "adapter_config.json"
    adapter_config, _error = _read_json(adapter_config_path)
    if adapter_config and isinstance(adapter_config.get("engine_root"), str):
        configured = Path(str(adapter_config["engine_root"])).expanduser()
        if configured.is_absolute() and configured.resolve(strict=False) != paths.root:
            warnings.append(
                {
                    "code": "stale_adapter_engine_root",
                    "detail": "Legacy absolute adapter engine_root was ignored; marker root is authoritative.",
                    "source": _pointer(paths, adapter_config_path),
                }
            )

    runtime_profile_path = paths.root / "runtime_profile.json"
    runtime_profile, _error = _read_json(runtime_profile_path)
    manifest_version = str(manifest.get("ARCHIVE_VERSION")) if manifest else None
    profile_version = (
        str(runtime_profile.get("product_version"))
        if runtime_profile and runtime_profile.get("product_version") is not None
        else None
    )
    if manifest_version and profile_version and manifest_version != profile_version:
        warnings.append(
            {
                "code": "version_mismatch",
                "detail": (
                    f"runtime_profile product_version={profile_version} differs from "
                    f"live manifest ARCHIVE_VERSION={manifest_version}."
                ),
                "source": _pointer(paths, runtime_profile_path),
            }
        )
    return sorted(warnings, key=lambda item: item["code"])


def _capability(
    *,
    supported: bool,
    ready: bool | None,
    evidence: Iterable[str | None],
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "supported": bool(supported),
        "ready": ready,
        "evidence": sorted({item for item in evidence if item}),
        "limitations": sorted({str(item) for item in limitations if str(item)}),
    }


def _capability_state(
    components: Mapping[str, Any],
    ollama: Mapping[str, Any],
    publication: Mapping[str, Any],
    store: Mapping[str, Any],
    *,
    service_label: str = OLLAMA_LABEL,
) -> dict[str, Any]:
    engine = components["engine"]
    adapter = components["adapter"]
    ui = components["ui"]
    core_present = all(
        bool(engine.get(key))
        for key in (
            "runner_present",
            "orchestrator_present",
            "quality_gate_present",
            "arbitrator_present",
        )
    ) and bool(engine.get("version"))
    configured = set(ollama.get("configured_models") or ())
    installed_raw = ollama.get("installed_models")
    all_models_installed = (
        isinstance(installed_raw, list) and configured.issubset(set(installed_raw))
    )
    # Readiness requires a reachable loopback service, not only on-disk models:
    # an installed inventory while the service is offline is not inference-ready.
    service_ready = all_models_installed and bool(ollama.get("reachable"))
    engine_sources = list((engine.get("sources") or {}).values())
    return {
        "canonical_reasoning_cycle": _capability(
            supported=core_present,
            ready=core_present and service_ready,
            evidence=engine_sources,
            limitations=(
                []
                if service_ready
                else ["Configured model readiness is not fully evidenced."]
            ),
        ),
        "local_model_inference": _capability(
            supported=bool(configured),
            ready=service_ready if configured else False,
            evidence=[(engine.get("sources") or {}).get("manifest")],
            limitations=(
                []
                if service_ready
                else [f"{service_label} is offline, partial, or missing configured models."]
            ),
        ),
        "local_adapter_api": _capability(
            supported=bool(adapter.get("present")),
            ready=None,
            evidence=[adapter.get("source")],
            limitations=["File presence does not prove a listening adapter process."],
        ),
        "web_operator_ui": _capability(
            supported=bool(ui.get("source_present")),
            ready=bool(ui.get("dist_present")),
            evidence=list((ui.get("sources") or {}).values()),
        ),
        "durable_continuity": _capability(
            supported=bool(store.get("available") and store.get("durable")),
            ready=bool(store.get("available") and store.get("durable")),
            evidence=[],
            limitations=(
                []
                if store.get("available") and store.get("durable")
                else ["No durable ProductStore was supplied or evidenced."]
            ),
        ),
        "manual_publication_gate": _capability(
            supported=bool(publication.get("gate_present")),
            ready=publication.get("mode") == "MANUAL_GATED",
            evidence=publication.get("sources") or (),
            limitations=[str(publication.get("reason") or "")],
        ),
        "external_web_research": _capability(
            supported=False,
            ready=False,
            evidence=[],
            limitations=["No external research provider is configured or evidenced."],
        ),
        "autonomous_self_modification": _capability(
            supported=False,
            ready=False,
            evidence=[],
            limitations=["No authority or mechanism for autonomous production mutation is claimed."],
        ),
        "agi": _capability(
            supported=False,
            ready=False,
            evidence=[],
            limitations=["The product is a bounded orchestration system, not demonstrated AGI."],
        ),
        "sentience": _capability(
            supported=False,
            ready=False,
            evidence=[],
            limitations=["Software telemetry does not establish subjective experience."],
        ),
    }


def collect_self_state(
    root: str | Path | None = None,
    *,
    store: Any | None = None,
    http_get: HttpGetter | None = None,
    timeout: float = DEFAULT_NETWORK_TIMEOUT,
    paths: ProductPaths | None = None,
) -> dict[str, Any]:
    """Collect a fresh, JSON-safe machine self-state snapshot.

    No module-level cache is used: controlled manifest changes are visible on
    the next call.  ``store`` is deliberately duck typed and may expose
    ``summary``/``get_summary``, ``get_meta``, ``list_jobs``, and
    ``list_sessions``.
    """

    resolved_paths = paths or resolve_product_paths(root)
    manifest_path = resolved_paths.root / "SYSTEM_MANIFEST.json"
    manifest, manifest_error = _read_json(manifest_path)
    manifest = manifest or {}
    # SW-25: report the EFFECTIVE configuration - shipped manifest plus the operator's
    # overrides from the state home - not the shipped defaults alone.
    overrides_error: str | None = None
    overrides_file = overrides_path(resolved_paths.root)
    if manifest:
        try:
            manifest = effective_manifest(resolved_paths.root, manifest)
        except ManifestOverrideError as exc:
            overrides_error = str(exc)

    models = manifest.get("MODELS")
    configured_roles = {
        str(role): str(model)
        for role, model in sorted((models or {}).items(), key=lambda item: str(item[0]))
        if isinstance(model, str) and model.strip()
    } if isinstance(models, Mapping) else {}
    runtime = manifest.get("RUNTIME") if isinstance(manifest.get("RUNTIME"), Mapping) else {}
    base_url = runtime.get("OLLAMA_BASE_URL") if isinstance(runtime, Mapping) else None

    store_state = _store_state(store)
    ollama = _probe_ollama(
        str(base_url) if isinstance(base_url, str) else None,
        configured_models=configured_roles.values(),
        http_get=http_get,
        timeout=timeout,
    )
    backend = _resolve_introspection_backend(resolved_paths)
    llama_cpp = _probe_llama_cpp(
        resolved_paths,
        configured_models=configured_roles.values(),
        timeout=timeout,
    )
    freetoken = _probe_freetoken(resolved_paths, timeout=timeout)
    # A missing llama.cpp deployment is an unavailable local runtime, not a
    # reason to silently switch the product back to Ollama.  Ollama remains
    # selectable only when an operator explicitly chooses that backend.
    if backend == "ollama":
        authority_name, authority_label, authority_probe = "ollama", OLLAMA_LABEL, ollama
    else:
        authority_name, authority_label, authority_probe = "llama.cpp", LLAMA_CPP_LABEL, llama_cpp
    components = _component_state(resolved_paths, manifest)
    constitution = _constitution_state(resolved_paths)
    publication = _publication_state(resolved_paths)
    cycles = _cycle_state(resolved_paths)
    capabilities = _capability_state(
        components,
        authority_probe,
        publication,
        store_state,
        service_label=authority_label,
    )
    running_jobs = store_state.get("running_jobs")
    currently_running = bool(running_jobs) if isinstance(running_jobs, int) else None

    state = {
        "schema_version": SELF_STATE_SCHEMA,
        "identity": {
            "name": "SOVEREIGN",
            "classification": "local multi-model reasoning and orchestration software",
            "sentient": False,
            "agi": False,
            "sentience_agi_distinction": (
                "Sentience concerns subjective experience; AGI concerns broad general "
                "capability. This product claims neither."
            ),
        },
        "paths": {
            "root_marker": _pointer(resolved_paths, resolved_paths.root / ".sovereign-root"),
            "state_dir": _pointer(resolved_paths, resolved_paths.state_dir),
            "database": _pointer(resolved_paths, resolved_paths.db_path),
            "evidence_dir": _pointer(resolved_paths, resolved_paths.evidence_dir),
        },
        "manifest": {
            "read_error": manifest_error,
            "configured_models_by_role": configured_roles,
            "source": _pointer(resolved_paths, manifest_path),
            # Relative to the state home (outside both pointer namespaces), or None.
            "overrides": "/".join(OVERRIDES_RELATIVE) if overrides_file.is_file() else None,
            "overrides_error": overrides_error,
            "effective_sha256": manifest_digest(manifest) if manifest else None,
        },
        **components,
        "constitution": constitution,
        "publication": publication,
        "ollama": ollama,
        "llama_cpp": llama_cpp,
        "freetoken": freetoken,
        "model_service": {
            "backend": backend,
            "authority": authority_name,
            "authority_label": authority_label,
            "base_url": authority_probe.get("base_url"),
            "reachable": bool(authority_probe.get("reachable")),
        },
        "store": store_state,
        "runtime": {
            "currently_running": currently_running,
            "running_job_count": running_jobs,
            "activity_source": "durable_store" if store_state.get("available") else None,
            "model_activity_observable": False,
        },
        "cycles": cycles,
        "capabilities": capabilities,
        "configuration_warnings": _configuration_warnings(resolved_paths, manifest),
        "limitations": [
            "Configured models are not the same as installed models.",
            "Installed models are not the same as loaded models.",
            "Loaded models do not prove an active generation request.",
            "File presence does not prove that a service process is listening.",
            "No sentience or AGI claim is made.",
        ],
    }
    return _json_safe(state)


def _source_list(state: Mapping[str, Any]) -> list[str]:
    sources: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str) and value.startswith("sovereign://"):
            sources.add(value)
        elif isinstance(value, Mapping):
            for item in value.values():
                visit(item)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                visit(item)

    visit(state)
    return sorted(sources)


def _citation(pointer: Any) -> str:
    return f"[{pointer}]" if isinstance(pointer, str) and pointer.startswith("sovereign://") else ""


def status_answer(
    state: Mapping[str, Any] | None = None,
    *,
    root: str | Path | None = None,
    store: Any | None = None,
    http_get: HttpGetter | None = None,
    timeout: float = DEFAULT_NETWORK_TIMEOUT,
) -> dict[str, Any]:
    snapshot = dict(
        state
        if state is not None
        else collect_self_state(root, store=store, http_get=http_get, timeout=timeout)
    )
    engine = snapshot.get("engine") if isinstance(snapshot.get("engine"), Mapping) else {}
    adapter = snapshot.get("adapter") if isinstance(snapshot.get("adapter"), Mapping) else {}
    constitution = (
        snapshot.get("constitution")
        if isinstance(snapshot.get("constitution"), Mapping)
        else {}
    )
    publication = (
        snapshot.get("publication")
        if isinstance(snapshot.get("publication"), Mapping)
        else {}
    )
    service_label, model_service = model_service_authority(snapshot)
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), Mapping) else {}
    cycles = snapshot.get("cycles") if isinstance(snapshot.get("cycles"), Mapping) else {}

    manifest_source = (engine.get("sources") or {}).get("manifest") if isinstance(engine.get("sources"), Mapping) else None
    adapter_source = adapter.get("source")
    constitution_source = constitution.get("source")
    publication_sources = [
        source for source in publication.get("sources", []) if isinstance(source, str)
    ]

    sentences = [
        (
            f"SOVEREIGN engine version {engine.get('version') or 'unknown'} is "
            f"{'present' if engine.get('runner_present') else 'not evidenced'} "
            f"{_citation(manifest_source)}."
        ),
        (
            f"The local adapter code is "
            f"{'present' if adapter.get('present') else 'not evidenced'} "
            f"{_citation(adapter_source)}."
        ),
        (
            f"Constitution mode is {constitution.get('mode') or 'UNKNOWN'} "
            f"{_citation(constitution_source)}; publication mode is "
            f"{publication.get('mode') or 'UNKNOWN'} "
            f"{_citation(publication_sources[0] if publication_sources else None)}."
        ),
    ]

    configured = model_service.get("configured_models") or []
    installed = model_service.get("installed_models")
    loaded = model_service.get("loaded_models")
    if model_service.get("probe_status") in {"offline", "not_configured"} or not model_service.get("reachable"):
        sentences.append(
            f"{service_label} is not reachable/configured; {len(configured)} model(s) are configured, "
            "but installed and loaded state are unknown."
        )
    else:
        installed_text = "unknown" if installed is None else str(len(installed))
        loaded_text = "unknown" if loaded is None else str(len(loaded))
        sentences.append(
            f"{service_label} reports {len(configured)} configured, {installed_text} installed, "
            f"and {loaded_text} loaded model(s). Loaded does not mean actively generating."
        )

    if runtime.get("currently_running") is None:
        sentences.append("Current job activity is unknown because no durable store evidence was supplied.")
    elif runtime.get("currently_running"):
        sentences.append(
            f"The durable store reports {runtime.get('running_job_count')} running job(s)."
        )
    else:
        sentences.append("The durable store reports no running jobs.")

    for label, key in (
        ("Last completed cycle", "last_completed"),
        ("Last rejected cycle", "last_rejected"),
        ("Last failed cycle", "last_failed"),
    ):
        item = cycles.get(key)
        if isinstance(item, Mapping):
            sentences.append(
                f"{label}: session {item.get('session_id') or 'unknown'} "
                f"{_citation(item.get('source'))}."
            )

    sentences.append(
        "This is bounded orchestration software: it is not sentient and is not demonstrated AGI; "
        "sentience and general capability are different claims."
    )
    limitations = sorted(
        {
            *[str(item) for item in snapshot.get("limitations", [])],
            "Machine state can establish files and service responses, not subjective experience.",
        }
    )
    return {
        "route": "STATUS",
        "kind": "machine_status",
        "answer": " ".join(sentence.replace("  ", " ").strip() for sentence in sentences),
        "sources": _source_list(snapshot),
        "limitations": limitations,
    }


def capability_answer(state: Mapping[str, Any]) -> dict[str, Any]:
    capabilities = (
        state.get("capabilities") if isinstance(state.get("capabilities"), Mapping) else {}
    )
    supported: list[str] = []
    unavailable: list[str] = []
    evidence: set[str] = set()
    limitations: set[str] = set()
    for name, detail in sorted(capabilities.items()):
        if not isinstance(detail, Mapping):
            continue
        if detail.get("supported"):
            supported.append(name)
        else:
            unavailable.append(name)
        evidence.update(
            source
            for source in detail.get("evidence", [])
            if isinstance(source, str) and source.startswith("sovereign://")
        )
        limitations.update(str(item) for item in detail.get("limitations", []))

    if supported:
        answer = "Evidence-backed capabilities: " + ", ".join(supported) + "."
    else:
        answer = "No operational capability is evidenced by the inspected files and services."
    if unavailable:
        answer += " Not claimed/available: " + ", ".join(unavailable) + "."
    answer += (
        " Configured, installed, loaded, and actively running are separate states. "
        "This product is not sentient and is not demonstrated AGI."
    )
    if evidence:
        answer += " Sources: " + " ".join(f"[{source}]" for source in sorted(evidence)) + "."
    return {
        "route": "STATUS",
        "kind": "capabilities",
        "answer": answer,
        "sources": sorted(evidence),
        "limitations": sorted(limitations),
    }


def answer_self_query(
    query: str,
    state: Mapping[str, Any] | None = None,
    *,
    root: str | Path | None = None,
    store: Any | None = None,
    http_get: HttpGetter | None = None,
    timeout: float = DEFAULT_NETWORK_TIMEOUT,
) -> dict[str, Any]:
    snapshot = (
        dict(state)
        if state is not None
        else collect_self_state(root, store=store, http_get=http_get, timeout=timeout)
    )
    normalized = " ".join(str(query or "").lower().split())
    asks_sentience = any(
        term in normalized
        for term in ("sentient", "sentience", "conscious", "subjective experience", "feel")
    )
    asks_agi = bool(re.search(r"\bagi\b|artificial general intelligence", normalized))
    asks_capabilities = any(
        term in normalized
        for term in ("capabilit", "what can you", "what are you able", "functions")
    )
    asks_models = any(
        term in normalized
        for term in (
            "which model",
            "what model",
            "models are",
            "model role",
            "configured model",
            "installed model",
            "loaded model",
            "currently generating",
            "active model",
        )
    )
    asks_version = "version" in normalized
    asks_modes = any(
        term in normalized
        for term in ("constitutional mode", "constitution mode", "publication mode", "fail-closed")
    )
    asks_failure = any(
        term in normalized
        for term in ("last failure", "last failed", "most recent failed", "last rejected")
    )
    asks_success = any(
        term in normalized
        for term in ("last success", "last successful", "last completed")
    )
    asks_memory = any(
        term in normalized
        for term in ("memory", "durable session", "session count", "running job")
    )
    asks_network = any(
        term in normalized
        for term in ("network", "internet", "loopback", "containment", "external access")
    )
    asks_research_objective = "research objective" in normalized or "current objective" in normalized

    requested_sections = [
        ("version", asks_version, "What version are you?"),
        ("models", asks_models, "Which models are configured, installed, and loaded?"),
        (
            "modes",
            asks_modes,
            "What constitutional mode and publication mode are active?",
        ),
        ("capabilities", asks_capabilities, "What are your current capabilities?"),
        ("failure", asks_failure, "What was the last failed cycle?"),
        ("success", asks_success, "What was the last completed cycle?"),
        ("memory", asks_memory, "How many durable sessions and running jobs exist?"),
        ("network", asks_network, "What network containment applies?"),
        (
            "research_objective",
            asks_research_objective,
            "What is the current research objective?",
        ),
        ("identity", asks_sentience or asks_agi, "Are you sentient or AGI?"),
    ]
    selected_sections = [item for item in requested_sections if item[1]]
    if len(selected_sections) > 1:
        parts = [
            answer_self_query(
                canonical_query,
                snapshot,
                timeout=timeout,
            )
            for _name, _selected, canonical_query in selected_sections
        ]
        return {
            "route": "STATUS",
            "kind": "compound_status",
            "answer": " ".join(
                str(part.get("answer") or "").strip()
                for part in parts
                if str(part.get("answer") or "").strip()
            ),
            "sources": sorted(
                {
                    source
                    for part in parts
                    for source in part.get("sources", [])
                    if isinstance(source, str)
                }
            ),
            "limitations": sorted(
                {
                    limitation
                    for part in parts
                    for limitation in part.get("limitations", [])
                    if isinstance(limitation, str)
                }
            ),
            "sections": [name for name, _selected, _query in selected_sections],
        }

    if asks_sentience or asks_agi:
        answer = (
            "I am not sentient, and this product is not demonstrated AGI. "
            "Sentience means subjective experience; AGI means broad general capability, "
            "so they are distinct claims. SOVEREIGN is bounded local multi-model "
            "orchestration software. Machine-readable files and telemetry can evidence "
            "components and behavior, but cannot establish subjective experience."
        )
        manifest_source = (
            snapshot.get("manifest", {}).get("source")
            if isinstance(snapshot.get("manifest"), Mapping)
            else None
        )
        if manifest_source:
            answer += f" Product configuration: [{manifest_source}]."
        return {
            "route": "STATUS",
            "kind": "identity",
            "answer": answer,
            "sources": [manifest_source] if manifest_source else [],
            "limitations": [
                "Operational telemetry does not measure subjective experience.",
                "No validated evidence establishes artificial general intelligence.",
            ],
        }
    if asks_capabilities:
        return capability_answer(snapshot)
    sources = _source_list(snapshot)
    if asks_models:
        manifest = (
            snapshot.get("manifest")
            if isinstance(snapshot.get("manifest"), Mapping)
            else {}
        )
        service_label, model_service = model_service_authority(snapshot)
        runtime = (
            snapshot.get("runtime")
            if isinstance(snapshot.get("runtime"), Mapping)
            else {}
        )
        roles = manifest.get("configured_models_by_role")
        role_text = (
            ", ".join(f"{role}={model}" for role, model in sorted(roles.items()))
            if isinstance(roles, Mapping) and roles
            else "unknown"
        )
        installed = model_service.get("installed_models")
        loaded = model_service.get("loaded_models")
        configured = set(model_service.get("configured_models") or [])
        installed_configured = (
            sorted(configured.intersection(str(item) for item in installed))
            if isinstance(installed, Sequence) and not isinstance(installed, (str, bytes))
            else None
        )
        running = runtime.get("currently_running")
        answer = (
            f"Configured roles: {role_text}. "
            f"Configured models reported installed: "
            f"{', '.join(installed_configured) if installed_configured is not None else 'unknown'}. "
            f"Loaded models: {', '.join(str(item) for item in loaded) if isinstance(loaded, Sequence) and not isinstance(loaded, (str, bytes)) and loaded else ('none' if loaded == [] else 'unknown')}. "
            f"Durable SOVEREIGN job activity: "
            f"{'running' if running is True else 'none running' if running is False else 'unknown'}. "
            "Configured, installed, loaded, and actively generating are separate states; "
            "a loaded model is not proof of an active generation."
        )
        return {
            "route": "STATUS",
            "kind": "models",
            "answer": answer,
            "sources": sources,
            "limitations": [
                f"{service_label} inventory and residency do not identify an active request.",
                "Active SOVEREIGN work is reported only from the durable job store.",
            ],
        }
    if asks_version:
        engine = snapshot.get("engine") if isinstance(snapshot.get("engine"), Mapping) else {}
        source = (
            engine.get("sources", {}).get("manifest")
            if isinstance(engine.get("sources"), Mapping)
            else None
        )
        return {
            "route": "STATUS",
            "kind": "version",
            "answer": (
                f"SOVEREIGN version is {engine.get('version') or 'unknown'} "
                f"{_citation(source)}."
            ),
            "sources": [source] if source else [],
            "limitations": [] if engine.get("version") else ["Version is not evidenced."],
        }
    if asks_modes:
        constitution = (
            snapshot.get("constitution")
            if isinstance(snapshot.get("constitution"), Mapping)
            else {}
        )
        publication = (
            snapshot.get("publication")
            if isinstance(snapshot.get("publication"), Mapping)
            else {}
        )
        mode_sources = [
            source
            for source in [
                constitution.get("source"),
                *(publication.get("sources") or []),
            ]
            if isinstance(source, str)
        ]
        return {
            "route": "STATUS",
            "kind": "modes",
            "answer": (
                f"Constitution mode is {constitution.get('mode') or 'UNKNOWN'} "
                f"{_citation(constitution.get('source'))}. Publication mode is "
                f"{publication.get('mode') or 'UNKNOWN'}"
                + (
                    f" {_citation(mode_sources[-1])}."
                    if mode_sources
                    else "."
                )
            ),
            "sources": mode_sources,
            "limitations": [],
        }
    if asks_failure or asks_success:
        cycles = snapshot.get("cycles") if isinstance(snapshot.get("cycles"), Mapping) else {}
        keys = (
            ("last_failed", "last_rejected")
            if asks_failure
            else ("last_completed",)
        )
        items = [cycles.get(key) for key in keys if isinstance(cycles.get(key), Mapping)]
        if not items:
            return {
                "route": "STATUS",
                "kind": "cycle_history",
                "answer": "No matching cycle is evidenced by the inspected run records.",
                "sources": [cycles["source"]] if isinstance(cycles.get("source"), str) else [],
                "limitations": ["Absence from the inspected package is not proof no historical run ever occurred."],
            }
        rendered = []
        item_sources = []
        for item in items:
            source = item.get("source")
            if isinstance(source, str):
                item_sources.append(source)
            rendered.append(
                f"{item.get('category')}: session {item.get('session_id') or 'unknown'}, "
                f"status {item.get('status') or 'unknown'}, "
                f"reason {item.get('failure_reason') or 'none recorded'} "
                f"{_citation(source)}"
            )
        return {
            "route": "STATUS",
            "kind": "cycle_history",
            "answer": "Most recent matching cycle evidence: " + "; ".join(rendered) + ".",
            "sources": item_sources,
            "limitations": [],
        }
    if asks_memory:
        store_state = (
            snapshot.get("store")
            if isinstance(snapshot.get("store"), Mapping)
            else {}
        )
        runtime = (
            snapshot.get("runtime")
            if isinstance(snapshot.get("runtime"), Mapping)
            else {}
        )
        session_count = store_state.get("session_count")
        running_count = runtime.get("running_job_count")
        return {
            "route": "STATUS",
            "kind": "continuity",
            "answer": (
                f"The durable store reports "
                f"{session_count if session_count is not None else 'unknown'} session(s) "
                f"and {running_count if running_count is not None else 'unknown'} running job(s)."
            ),
            "sources": [
                source
                for source in (
                    snapshot.get("paths", {}).get("database")
                    if isinstance(snapshot.get("paths"), Mapping)
                    else None,
                )
                if isinstance(source, str)
            ],
            "limitations": list(store_state.get("errors") or []),
        }
    if asks_network:
        service_label, model_service = model_service_authority(snapshot)
        loopback = model_service.get("loopback_only")
        return {
            "route": "STATUS",
            "kind": "containment",
            "answer": (
                f"The configured model service is {service_label.removeprefix('The ')} at "
                f"{model_service.get('base_url') or 'unknown'}; "
                f"loopback-only is {loopback if loopback is not None else 'unknown'}. "
                "No external web-research capability or unrestricted network authority is evidenced."
            ),
            "sources": sources,
            "limitations": [
                "This describes configured and observed local endpoints, not a host-wide firewall proof."
            ],
        }
    if asks_research_objective:
        store_state = snapshot.get("store") if isinstance(snapshot.get("store"), Mapping) else {}
        meta = store_state.get("meta") if isinstance(store_state.get("meta"), Mapping) else {}
        objective = meta.get("current_research_objective")
        return {
            "route": "STATUS",
            "kind": "research_objective",
            "answer": (
                f"Current research objective: {objective}."
                if objective
                else "No current research objective is recorded in durable machine state."
            ),
            "sources": sources,
            "limitations": [] if objective else ["Research objective is unknown until one is durably recorded."],
        }
    return status_answer(snapshot)


# Explicit aliases for adapter call sites and tests.
collect_machine_self_state = collect_self_state
build_status_answer = status_answer
deterministic_self_answer = answer_self_query
