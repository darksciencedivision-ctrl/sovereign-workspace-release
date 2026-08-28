from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable

ACTIVE_D_ROOT = "ACTIVE_D_ROOT"
STALE_D_ROOT = "STALE_D_ROOT"
HISTORICAL_E_ROOT = "HISTORICAL_E_ROOT"
NESTED_RUNTIME = "NESTED_RUNTIME"
UNKNOWN_ROOT = "UNKNOWN_ROOT"

ROOT_MARKERS = (
    "broker_v21",
    "phase21",
    "evaluation",
    "cognition",
    "URI",
    "logs",
    "runs",
    "claim_arbitrator.py",
    "evaluation/contract.py",
)
MINIMUM_MARKER_HITS = 4


def normalize_windows_path(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path))).rstrip("\\/")


def _runtime_parts(path: str | Path) -> tuple[str, ...]:
    normalized = normalize_windows_path(path)
    return tuple(part for part in PureWindowsPath(normalized).parts if part not in ("", "."))


def _is_nested_runtime(path: str | Path) -> bool:
    parts = [part.lower() for part in _runtime_parts(path)]
    pairs = list(zip(parts, parts[1:]))
    return ("output", "live_runtime") in pairs


def marker_hits(root: Path) -> list[str]:
    resolved = root.resolve(strict=False)
    return [marker for marker in ROOT_MARKERS if (resolved / marker).exists()]


def _marker_backed_root(path: str | Path) -> Path | None:
    candidate = Path(path)
    resolved = candidate.expanduser().resolve(strict=False)
    start = resolved if resolved.is_dir() else resolved.parent
    for current in (start, *start.parents):
        if len(marker_hits(current)) >= MINIMUM_MARKER_HITS:
            return current
    return None


def classify_root(root: str | Path) -> str:
    normalized = normalize_windows_path(root)

    marker_root = _marker_backed_root(root)
    if marker_root is not None:
        active_root = normalize_windows_path(marker_root)
        if normalized == active_root:
            return ACTIVE_D_ROOT
        relative_text = os.path.relpath(normalized, active_root)
        relative_parts = tuple(part for part in PureWindowsPath(relative_text).parts if part not in (".", ""))
        if len(relative_parts) >= 2 and relative_parts[0].lower() == "output" and relative_parts[1].lower() == "live_runtime":
            return ACTIVE_D_ROOT
        if _is_nested_runtime(relative_text):
            return NESTED_RUNTIME
        return ACTIVE_D_ROOT

    if _is_nested_runtime(root):
        return NESTED_RUNTIME

    return UNKNOWN_ROOT


def reject_historical_e_root(root: str | Path) -> None:
    if classify_root(root) == HISTORICAL_E_ROOT:
        raise ValueError(f"Historical E root is not permitted for active runtime work: {root}")


def detect_root_mismatch(expected: str | Path, observed: str | Path) -> bool:
    return normalize_windows_path(expected) != normalize_windows_path(observed)


def _walk_candidates(start_path: Path) -> Iterable[Path]:
    resolved = start_path.expanduser().resolve(strict=False)
    current = resolved if resolved.is_dir() else resolved.parent
    yield current
    yield from current.parents


def validate_root(root: str | Path) -> dict[str, Any]:
    candidate = Path(root).expanduser()
    errors: list[str] = []
    warnings: list[str] = []

    if not candidate.exists():
        errors.append(f"root does not exist: {candidate}")
        return {
            "status": "FAIL",
            "root": str(candidate),
            "classification": classify_root(candidate),
            "marker_hits": [],
            "marker_count": 0,
            "minimum_marker_hits": MINIMUM_MARKER_HITS,
            "warnings": warnings,
            "errors": errors,
        }

    reject_error = ""
    try:
        reject_historical_e_root(candidate)
    except ValueError as exc:
        reject_error = str(exc)
        errors.append(reject_error)

    resolved = candidate.resolve(strict=True)
    hits = marker_hits(resolved)
    classification = classify_root(resolved)
    if len(hits) < MINIMUM_MARKER_HITS:
        errors.append(
            f"root marker validation failed for {resolved}; found {len(hits)} marker(s), need at least {MINIMUM_MARKER_HITS}"
        )
    if classification != ACTIVE_D_ROOT:
        warnings.append(f"root classification is {classification}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "root": str(resolved),
        "classification": classification,
        "marker_hits": hits,
        "marker_count": len(hits),
        "minimum_marker_hits": MINIMUM_MARKER_HITS,
        "warnings": warnings,
        "errors": errors,
    }


def discover_root(start_path: str | Path | None = None) -> Path:
    start = Path(start_path) if start_path is not None else Path.cwd()
    last_error = ""
    for candidate in _walk_candidates(start):
        validation = validate_root(candidate)
        if validation["status"] == "PASS":
            return Path(validation["root"])
        last_error = "; ".join(validation["errors"])

    # Fail closed.  There is deliberately no machine-specific fallback root:
    # callers must start beneath the marked package or supply the validated
    # root through the product's single root-resolution boundary.
    raise ValueError(f"SOVEREIGN runtime root discovery failed from {start}: {last_error}")
