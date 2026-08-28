"""Node configuration loaders: directive, role, permission profile (Plan section 7-P3).

Fail closed on everything ambiguous: missing file, empty file, unparseable JSON, schema
violation, node-class mismatch, non-deny default stance. A node that cannot load a
complete, valid configuration must not run (Buildout Directive section 4). Loaded
content is hashed so downstream records can pin exactly what the node ran under.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
_PERMISSION_SCHEMA = json.loads((_SCHEMA_DIR / "permission.schema.json").read_text(encoding="utf-8"))

DIRECTIVE_FILE = "DIRECTIVE.md"
ROLE_FILE = "ROLE.md"
PERMISSION_FILE = "permission_profile.json"


class LoaderError(Exception):
    """Any configuration defect. Nodes must treat this as fatal (fail closed)."""


@dataclass(frozen=True)
class NodeConfig:
    node_class: str
    directive_text: str
    role_text: str
    permission_profile: dict[str, Any]
    hashes: dict[str, str]  # filename -> sha256 of the exact bytes loaded


def _load_required_text(config_dir: Path, name: str) -> tuple[str, str]:
    path = config_dir / name
    if not path.is_file():
        raise LoaderError(f"missing required config file: {path}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        # nodes treat LoaderError as the fatal fail-closed signal; don't leak a raw codec error
        raise LoaderError(f"config file is not valid UTF-8: {path} ({exc})") from exc
    if not text.strip():
        raise LoaderError(f"config file is empty: {path}")
    return text, hashlib.sha256(raw).hexdigest()


def load_node_config(config_dir: Path, expected_node_class: str) -> NodeConfig:
    config_dir = Path(config_dir)
    if not config_dir.is_dir():
        raise LoaderError(f"config dir does not exist: {config_dir}")

    directive_text, directive_hash = _load_required_text(config_dir, DIRECTIVE_FILE)
    role_text, role_hash = _load_required_text(config_dir, ROLE_FILE)
    profile_text, profile_hash = _load_required_text(config_dir, PERMISSION_FILE)

    try:
        profile = json.loads(profile_text)
    except json.JSONDecodeError as exc:
        raise LoaderError(f"permission profile is not valid JSON: {exc}") from exc
    try:
        jsonschema.validate(profile, _PERMISSION_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise LoaderError(f"permission profile violates permission@1.0: {exc.message}") from exc

    if profile["node_class"] != expected_node_class:
        raise LoaderError(
            f"permission profile is for node_class={profile['node_class']!r}, "
            f"node is {expected_node_class!r} — refusing to run under a foreign profile"
        )
    if profile["default_stance"] != "deny":  # schema const already enforces; belt-and-braces
        raise LoaderError("permission profile default_stance must be 'deny'")

    return NodeConfig(
        node_class=expected_node_class,
        directive_text=directive_text,
        role_text=role_text,
        permission_profile=profile,
        hashes={DIRECTIVE_FILE: directive_hash, ROLE_FILE: role_hash, PERMISSION_FILE: profile_hash},
    )
