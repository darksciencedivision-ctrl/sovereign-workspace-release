from __future__ import annotations

"""Canonical version/document identity resolution (F-04).

Single source of truth for the relationship between the software package
version, thesis versions, the specification draft, schema identities,
registry schema versions, and the immutable RC3 snapshot identity. The Git
SHA is resolved at runtime and never pinned in static documents.
"""

import json
import re
import subprocess
from pathlib import Path

from distillery.common import ContractError

MATRIX_PATH = Path("docs/VERSION_MATRIX.json")

#: EPC-01. Every entry point below defaulted `root` to `"."`, so the canonical version matrix
#: resolved against the CALLER'S working directory rather than against this module. Run from
#: modules/distillery that is right by accident; run from the repository root — the
#: whole-product invocation — `./docs/VERSION_MATRIX.json` does not exist and identity
#: resolution died with "canonical version matrix is missing". Two tests failed only in the
#: combined run and passed in isolation.
#:
#: The module root is a fact about where this file lives, not about where someone stood when
#: they called it. `identity.py` sits at <module>/distillery/identity.py, so the root is two
#: parents up.
MODULE_ROOT = Path(__file__).resolve().parents[1]
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_REQUIRED_TOP = {"schema_version", "software_package", "thesis", "specification", "schemas", "snapshot_identity"}
_REQUIRED_SNAPSHOT = {"snapshot_id", "bundle_path", "bundle_sha256"}


def load_version_matrix(root: str | Path | None = None) -> dict:
    root = MODULE_ROOT if root is None else root
    path = Path(root) / MATRIX_PATH
    if not path.is_file():
        raise ContractError(f"canonical version matrix is missing: {MATRIX_PATH}")
    matrix = json.loads(path.read_text(encoding="utf-8"))
    missing = _REQUIRED_TOP - matrix.keys()
    if missing:
        raise ContractError(f"version matrix missing required sections: {sorted(missing)}")
    package = matrix["software_package"]
    if not isinstance(package.get("version"), str) or not package["version"].strip():
        raise ContractError("version matrix does not declare a software package version")
    snapshot = matrix["snapshot_identity"]
    missing_snapshot = _REQUIRED_SNAPSHOT - snapshot.keys()
    if missing_snapshot:
        raise ContractError(f"version matrix snapshot identity incomplete: {sorted(missing_snapshot)}")
    validate_snapshot_identity(snapshot["snapshot_id"], snapshot["bundle_sha256"])
    thesis = matrix["thesis"]
    current = thesis.get("current") or {}
    if not current.get("version") or not current.get("document"):
        raise ContractError("version matrix must declare exactly one current thesis identity")
    if len(thesis.get("historical") or []) != len({row.get("version") for row in thesis.get("historical") or []}):
        raise ContractError("version matrix historical thesis entries contain duplicate versions")
    return matrix


def validate_snapshot_identity(snapshot_id: object, bundle_sha256: object) -> None:
    if not isinstance(snapshot_id, str) or not _HEX40.match(snapshot_id):
        raise ContractError(f"malformed snapshot identity: {snapshot_id!r} is not a 40-hex Git SHA")
    if not isinstance(bundle_sha256, str) or not _HEX64.match(bundle_sha256):
        raise ContractError(f"malformed bundle digest: {bundle_sha256!r} is not a 64-hex SHA-256")


def software_version(root: str | Path | None = None) -> str:
    root = MODULE_ROOT if root is None else root
    matrix = load_version_matrix(root)
    pyproject = Path(root) / "pyproject.toml"
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise ContractError("pyproject.toml does not declare a package version")
    declared = match.group(1)
    if declared != matrix["software_package"]["version"]:
        raise ContractError(
            f"package version contradiction: pyproject.toml declares {declared}, matrix declares {matrix['software_package']['version']}"
        )
    return declared


def git_head(root: str | Path | None = None) -> str:
    root = MODULE_ROOT if root is None else root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ContractError(f"unable to resolve repository HEAD: {exc}") from exc
    head = result.stdout.strip()
    if not _HEX40.match(head):
        raise ContractError(f"malformed repository HEAD: {head!r}")
    return head


def resolve_identity(root: str | Path | None = None) -> dict:
    root = MODULE_ROOT if root is None else root
    root_path = Path(root).resolve()
    matrix = load_version_matrix(root_path)
    snapshot = matrix["snapshot_identity"]
    bundle = root_path / snapshot["bundle_path"]
    if not bundle.is_file():
        raise ContractError(f"snapshot bundle missing: {snapshot['bundle_path']}")
    import hashlib

    observed = hashlib.sha256(bundle.read_bytes()).hexdigest()
    if observed != snapshot["bundle_sha256"]:
        raise ContractError(f"snapshot bundle digest mismatch: expected {snapshot['bundle_sha256']}, observed {observed}")
    for row in matrix["evidence_packages"]:
        if not (root_path / row["path"]).is_file():
            raise ContractError(f"evidence package record missing: {row['path']}")
    return {
        "repository": "ryguy-pixel/Sovereign-Distillery",
        "git_head": git_head(root_path),
        "software_version": software_version(root_path),
        "thesis_current": matrix["thesis"]["current"],
        "thesis_historical": matrix["thesis"]["historical"],
        "specification": matrix["specification"],
        "schemas": matrix["schemas"],
        "registry_schema_versions": matrix["registry_schema_versions"],
        "snapshot": {**snapshot, "bundle_digest_verified": True},
        "evidence_packages": matrix["evidence_packages"],
    }