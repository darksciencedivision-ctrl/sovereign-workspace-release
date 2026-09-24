"""Persistent backend/workload selection for Sovereign local inference.

Designation surface (no temporary shell variables required):

    <runtime state dir>/backend_selection.json   (paths.resolve_runtime_dir; SW-25)

    {
      "schema": "sovereign.backend-selection.v1",
      "default_backend": "llama.cpp",
      "freetoken": {
        "profile": "qwen3-0.6b",
        "port": 1919,
        "workloads": {
          "freetoken-dense": {"profile": "qwen3-0.6b"},
          "freetoken-moe-offload": {"profile": "gpt-oss-20b"}
        }
      }
    }

Precedence for the effective backend:
1. explicit ``SOVEREIGN_INFERENCE_BACKEND`` environment choice (preserved),
2. ``default_backend`` from the selection file,
3. the factory default from runtime_contracts (llama.cpp).

Model-role assignments are never remapped here: production roles stay on the
default local engine unless an operator explicitly designates otherwise.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .paths import resolve_runtime_dir
from .runtime_contracts import DEFAULT_INFERENCE_BACKEND, normalize_inference_backend


SCHEMA_ID = "sovereign.backend-selection.v1"
DEFAULT_FREETOKEN_PROFILE = "qwen3-0.6b"
DEFAULT_FREETOKEN_PORT = 1919


class BackendSelectionError(ValueError):
    """Invalid backend selection document."""


def selection_path(root: Path) -> Path:
    return resolve_runtime_dir(root) / "backend_selection.json"


def load_selection(root: Path) -> dict[str, Any]:
    path = selection_path(root)
    if not path.is_file():
        return {"schema": SCHEMA_ID, "default_backend": DEFAULT_INFERENCE_BACKEND}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise BackendSelectionError(f"unreadable backend selection {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BackendSelectionError("backend selection must be a JSON object")
    schema = str(payload.get("schema") or "").strip()
    if schema and schema != SCHEMA_ID:
        raise BackendSelectionError(f"unsupported backend selection schema: {schema!r}")
    default_backend = payload.get("default_backend")
    if default_backend is not None:
        normalize_inference_backend(str(default_backend))
    freetoken = payload.get("freetoken")
    if freetoken is not None and not isinstance(freetoken, dict):
        raise BackendSelectionError("freetoken selection must be a JSON object")
    return payload


def write_selection(root: Path, payload: dict[str, Any]) -> None:
    document = dict(payload)
    document["schema"] = SCHEMA_ID
    document_text = json.dumps(document, indent=2)
    path = selection_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document_text + "\n", encoding="utf-8")


def resolve_backend(root: Path) -> str:
    """Effective backend: explicit env choice, then file default, then factory."""

    env = str(os.environ.get("SOVEREIGN_INFERENCE_BACKEND") or "").strip()
    if env:
        return normalize_inference_backend(env)
    payload = load_selection(root)
    default_backend = str(payload.get("default_backend") or "").strip()
    if default_backend:
        return normalize_inference_backend(default_backend)
    return DEFAULT_INFERENCE_BACKEND


def resolve_freetoken_profile(root: Path, workload: str | None = None) -> str:
    payload = load_selection(root)
    freetoken = payload.get("freetoken")
    freetoken = freetoken if isinstance(freetoken, dict) else {}
    if workload:
        workloads = freetoken.get("workloads")
        workloads = workloads if isinstance(workloads, dict) else {}
        entry = workloads.get(str(workload).strip())
        if isinstance(entry, dict):
            profile = str(entry.get("profile") or "").strip()
            if profile:
                return profile
        elif isinstance(entry, str) and entry.strip():
            return entry.strip()
    profile = str(freetoken.get("profile") or "").strip()
    return profile or DEFAULT_FREETOKEN_PROFILE


def resolve_freetoken_port(root: Path, workload: str | None = None) -> int:
    payload = load_selection(root)
    freetoken = payload.get("freetoken")
    freetoken = freetoken if isinstance(freetoken, dict) else {}
    if workload:
        workloads = freetoken.get("workloads")
        workloads = workloads if isinstance(workloads, dict) else {}
        entry = workloads.get(str(workload).strip())
        if isinstance(entry, dict):
            try:
                port = int(entry.get("port") or 0)
            except (TypeError, ValueError):
                port = 0
            if 0 < port < 65536:
                return port
    try:
        port = int(freetoken.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    return port if 0 < port < 65536 else DEFAULT_FREETOKEN_PORT
