from __future__ import annotations

import json
import os
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

from library.utils.safe_io import read_json_bom_safe

ROOT_MARKER_NAME = ".sovereign-root"
ROOT_MARKER_CONTENT = "SOVEREIGN_ROOT_MARKER=1"

_ROOT_OVERRIDE: Path | None = None


class RootResolutionError(RuntimeError):
    """Raised when the SOVEREIGN repository root cannot be resolved safely."""


def validate_repo_root(root: str | Path) -> Path:
    """Validate and resolve a marked package root without mutating process state."""
    return _validate_repo_root(Path(root))


def configure_root(root: str | Path | None) -> Path | None:
    """Explicitly set the active repository root for the current process."""
    global _ROOT_OVERRIDE
    if root is None:
        _ROOT_OVERRIDE = None
        return None
    _ROOT_OVERRIDE = validate_repo_root(root)
    return _ROOT_OVERRIDE


def clear_configured_root() -> None:
    configure_root(None)


def get_repo_root() -> Path:
    """Resolve the active SOVEREIGN repository root."""
    if _ROOT_OVERRIDE is not None:
        return _ROOT_OVERRIDE

    cli_root = _extract_cli_root(sys.argv[1:])
    if cli_root is not None:
        return _validate_repo_root(cli_root)

    env_root = os.environ.get("SOVEREIGN_ROOT", "").strip()
    if env_root:
        return _validate_repo_root(Path(env_root))

    marker_root = _search_for_marker_root()
    if marker_root is not None:
        return marker_root

    # Fail closed: never fabricate or trust an unmarked legacy root.
    raise RootResolutionError(
        "Unable to resolve SOVEREIGN root. Provide --root, set SOVEREIGN_ROOT, "
        f"or run beneath a directory containing {ROOT_MARKER_NAME}."
    )


def get_sandbox_root() -> Path:
    return resolve_under_root(get_repo_root(), "sandbox_agi")


def get_runtime_root() -> Path:
    return resolve_under_root(get_repo_root(), "runtime")


def get_reports_root() -> Path:
    return resolve_under_root(get_sandbox_root(), "reports")


def get_uri_root() -> Path:
    return resolve_under_root(get_repo_root(), "URI")


def get_research_root() -> Path:
    return resolve_under_root(get_repo_root(), "research")


def get_audit_runs_root() -> Path:
    return resolve_under_root(get_repo_root(), "audit_runs")


def is_within_root(path: str | Path, root: str | Path) -> bool:
    root_path = Path(root).resolve()
    try:
        Path(path).resolve().relative_to(root_path)
        return True
    except ValueError:
        return False


def resolve_under_root(root: str | Path, relative_path: str | Path) -> Path:
    root_path = Path(root).resolve()
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError(f"Absolute path is not allowed for resolve_under_root: {candidate}")
    resolved = (root_path / candidate).resolve()
    if not is_within_root(resolved, root_path):
        raise ValueError(f"Path traversal blocked: {relative_path}")
    return resolved


def remap_repo_path(value: str | Path, *, root: str | Path | None = None) -> Path:
    """Map relative or legacy-rooted paths into the active repository root."""
    active_root = Path(root or get_repo_root()).resolve()
    text = str(value).strip()
    if not text:
        return active_root

    placeholder_prefixes = (
        "<SOVEREIGN_ROOT>",
        "${SOVEREIGN_ROOT}",
        "%SOVEREIGN_ROOT%",
    )
    for prefix in placeholder_prefixes:
        if text.startswith(prefix):
            suffix = text[len(prefix) :].lstrip("\\/")
            return active_root / Path(PureWindowsPath(suffix))

    candidate = Path(text)
    if candidate.is_absolute():
        return candidate.resolve()
    return resolve_under_root(active_root, candidate)


def remap_repo_data(payload: Any, *, root: str | Path | None = None) -> Any:
    """Recursively remap any legacy-rooted path strings in a JSON-like payload."""
    active_root = Path(root or get_repo_root()).resolve()
    if isinstance(payload, dict):
        return {key: remap_repo_data(value, root=active_root) for key, value in payload.items()}
    if isinstance(payload, list):
        return [remap_repo_data(item, root=active_root) for item in payload]
    if isinstance(payload, str) and _looks_like_path(payload):
        try:
            return str(remap_repo_path(payload, root=active_root))
        except (RootResolutionError, ValueError):
            return payload
    return payload


def load_rooted_json(path: str | Path, *, root: str | Path | None = None) -> Any:
    data = read_json_bom_safe(path, default={})
    return remap_repo_data(data, root=root)


def describe_root_resolution() -> dict[str, Any]:
    try:
        repo_root = get_repo_root()
    except RootResolutionError as exc:
        return {"status": "BLOCKED_ENVIRONMENT", "reason": str(exc)}
    return {
        "status": "PASS",
        "repo_root": str(repo_root),
        "sandbox_root": str(get_sandbox_root()),
        "runtime_root": str(get_runtime_root()),
        "reports_root": str(get_reports_root()),
        "uri_root": str(get_uri_root()),
        "research_root": str(get_research_root()),
    }


def _validate_repo_root(candidate: Path, *, require_marker: bool = True) -> Path:
    resolved = candidate.resolve()
    marker_path = resolved / ROOT_MARKER_NAME
    if require_marker:
        if not marker_path.exists():
            raise RootResolutionError(f"Missing {ROOT_MARKER_NAME} under {resolved}")
        marker_text = marker_path.read_text(encoding="utf-8", errors="ignore").strip()
        if marker_text != ROOT_MARKER_CONTENT:
            raise RootResolutionError(f"Invalid {ROOT_MARKER_NAME} contents under {resolved}")
    if not (resolved / "sandbox_agi").exists():
        raise RootResolutionError(f"sandbox_agi directory missing under {resolved}")
    if not (resolved / "URI").exists():
        raise RootResolutionError(f"URI directory missing under {resolved}")
    return resolved


def _extract_cli_root(argv: list[str]) -> Path | None:
    for index, token in enumerate(argv):
        if token == "--root" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if token.startswith("--root="):
            return Path(token.split("=", 1)[1])
    return None


def _search_for_marker_root() -> Path | None:
    anchors = {
        Path.cwd().resolve(),
        Path(__file__).resolve(),
        Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else Path.cwd().resolve(),
    }
    for anchor in anchors:
        base = anchor if anchor.is_dir() else anchor.parent
        for candidate in (base, *base.parents):
            marker_path = candidate / ROOT_MARKER_NAME
            if not marker_path.exists():
                continue
            try:
                return _validate_repo_root(candidate)
            except RootResolutionError:
                continue
    return None


def _looks_like_path(text: str) -> bool:
    if not text:
        return False
    if text.startswith(("<SOVEREIGN_ROOT>", "${SOVEREIGN_ROOT}", "%SOVEREIGN_ROOT%")):
        return True
    if text.startswith((".\\", "./", "..\\", "../")):
        return True
    if len(text) >= 3 and text[1] == ":" and text[2] in {"\\", "/"}:
        return True
    return False
