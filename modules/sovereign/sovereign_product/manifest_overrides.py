"""Operator overrides layered over the shipped, immutable SYSTEM_MANIFEST.json (SW-25).

Before SW-25, assigning a model rewrote the shipped ``SYSTEM_MANIFEST.json`` in the install tree, so a
read-only install could not assign models, an upgrade silently discarded the operator's choices, and a
tracked release file changed at runtime. Now the shipped manifest is never written. Operator choices
live in ``<state home>/config/manifest.overrides.json``::

    {"schema": 1, "MODELS": {"PRIMARY_REASONER": "qwen3:14b"}, "updated_utc": "..."}

and are applied on top of the shipped manifest wherever the manifest is loaded
(``system_manifest.load_system_manifest``, introspection). Only ``MODELS`` roles that the shipped
manifest already defines may be overridden; anything else fails closed, so the override file cannot
redefine runtime limits, thresholds or URLs.

This module deliberately does not import ``system_manifest`` (which imports it); validation errors
are ``ManifestOverrideError`` (a ``ValueError``) and the loader converts them.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .paths import resolve_state_home

OVERRIDES_RELATIVE = ("config", "manifest.overrides.json")
OVERRIDABLE_SECTIONS = ("MODELS",)
_ALLOWED_TOP_LEVEL = {"schema", "updated_utc", "source", *OVERRIDABLE_SECTIONS}
SCHEMA = 1

_WRITE_LOCK = threading.Lock()


class ManifestOverrideError(ValueError):
    """The operator override file is malformed or tries to override something it may not."""


def overrides_path(root: str | os.PathLike[str] | Path) -> Path:
    return resolve_state_home(root).joinpath(*OVERRIDES_RELATIVE)


def _validate(payload: Any, shipped: Mapping[str, Any], source: Path) -> dict[str, dict[str, str]]:
    if not isinstance(payload, dict):
        raise ManifestOverrideError(f"{source} must be a JSON object")
    unknown = set(payload) - _ALLOWED_TOP_LEVEL
    if unknown:
        raise ManifestOverrideError(
            f"{source} may only override {', '.join(OVERRIDABLE_SECTIONS)}; "
            f"refusing key(s): {', '.join(sorted(map(str, unknown)))}"
        )
    if "source" in payload and not isinstance(payload["source"], str):
        raise ManifestOverrideError(f"{source}.source must be a string")
    if payload.get("schema", SCHEMA) != SCHEMA:
        raise ManifestOverrideError(f"{source} schema {payload.get('schema')!r} is not supported")
    result: dict[str, dict[str, str]] = {}
    for section in OVERRIDABLE_SECTIONS:
        values = payload.get(section, {})
        if not isinstance(values, dict):
            raise ManifestOverrideError(f"{source}.{section} must be an object")
        shipped_section = shipped.get(section)
        allowed = set(shipped_section) if isinstance(shipped_section, Mapping) else set()
        cleaned: dict[str, str] = {}
        for key, value in values.items():
            if key not in allowed:
                raise ManifestOverrideError(
                    f"{source}.{section}.{key} is not a role the shipped manifest defines"
                )
            if not isinstance(value, str) or not value.strip():
                raise ManifestOverrideError(f"{source}.{section}.{key} must be a non-empty string")
            cleaned[str(key)] = value.strip()
        result[section] = cleaned
    return result


def load_overrides(
    root: str | os.PathLike[str] | Path,
    shipped: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    """The validated overrides (empty sections when the file is absent)."""

    path = overrides_path(root)
    if not path.is_file():
        return {section: {} for section in OVERRIDABLE_SECTIONS}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestOverrideError(f"{path} is unreadable: {exc}") from exc
    return _validate(payload, shipped, path)


def apply_overrides(
    shipped: Mapping[str, Any],
    overrides: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """A NEW manifest: the shipped one with each override section merged in."""

    effective = dict(shipped)
    for section in OVERRIDABLE_SECTIONS:
        values = overrides.get(section) or {}
        if values:
            merged = dict(shipped.get(section) or {})
            merged.update(values)
            effective[section] = merged
    return effective


def effective_manifest(
    root: str | os.PathLike[str] | Path,
    shipped: Mapping[str, Any],
) -> dict[str, Any]:
    return apply_overrides(shipped, load_overrides(root, shipped))


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Canonical sha256 of a manifest mapping (records WHICH effective configuration ran)."""

    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_model_overrides(
    root: str | os.PathLike[str] | Path,
    shipped: Mapping[str, Any],
    updates: Mapping[str, str],
) -> dict[str, dict[str, str]]:
    """Merge ``updates`` into the MODELS overrides and write them atomically.

    A role set back to its shipped value is dropped from the file, so the override file only ever
    records real departures from the shipped defaults. Returns the overrides now in force.
    """

    path = overrides_path(root)
    with _WRITE_LOCK:
        current = load_overrides(root, shipped)
        models = dict(current.get("MODELS") or {})
        shipped_models = shipped.get("MODELS") if isinstance(shipped.get("MODELS"), Mapping) else {}
        for key, value in updates.items():
            if shipped_models.get(key) == value:
                models.pop(key, None)
            else:
                models[key] = value
        payload = {"schema": SCHEMA, "MODELS": dict(sorted(models.items())),
                   "updated_utc": _utc_now()}
        validated = _validate(payload, shipped, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return validated
