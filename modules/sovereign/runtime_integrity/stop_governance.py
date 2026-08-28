from __future__ import annotations

from pathlib import Path
from typing import Any

from .root_authority import validate_root


def stop_path(root: str | Path) -> Path:
    resolved = Path(validate_root(root)["root"])
    return resolved / "STOP"


def praxis_stop_path(root: str | Path) -> Path:
    resolved = Path(validate_root(root)["root"])
    return resolved / "praxis" / "STOP"


def is_stop_present(root: str | Path) -> bool:
    return stop_path(root).exists() or praxis_stop_path(root).exists()


def classify_stop_state(root: str | Path) -> dict[str, Any]:
    canonical_stop = stop_path(root)
    praxis_stop = praxis_stop_path(root)
    present = canonical_stop.exists() or praxis_stop.exists()
    warnings: list[str] = []
    if praxis_stop.exists() and not canonical_stop.exists():
        warnings.append("praxis/STOP is present even though the canonical STOP file is absent")
    return {
        "path": str(canonical_stop),
        "present": present,
        "status": "STOP_PRESENT" if present else "STOP_ABSENT",
        "praxis_stop_path": str(praxis_stop),
        "praxis_stop_present": praxis_stop.exists(),
        "warnings": warnings,
    }


def require_stop_absent_for_runtime(root: str | Path) -> dict[str, Any]:
    state = classify_stop_state(root)
    if state["present"]:
        raise RuntimeError(f"STOP governance blocks runtime execution: {state['path']}")
    return state
