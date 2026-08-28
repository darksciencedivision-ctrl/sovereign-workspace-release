from __future__ import annotations

import hashlib
from pathlib import Path

from distillery.common import ContractError, sha256_value, write_new_json


COMPONENTS = {"model", "quantization", "system_prompt", "tool_schemas", "retrieval", "memory", "serving"}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assemble_bundle(version: str, component_paths: dict[str, str | Path], output_dir: str | Path) -> dict:
    if set(component_paths) != COMPONENTS:
        raise ContractError(f"bundle requires exact components: {sorted(COMPONENTS)}")
    components = {}
    for name in sorted(COMPONENTS):
        path = Path(component_paths[name]).resolve()
        if not path.is_file():
            raise ContractError(f"missing bundle component: {name}")
        components[name] = {"path": str(path), "sha256": _file_hash(path)}
    body = {"schema_version": "1.1", "bundle_version": version, "components": components}
    manifest = {**body, "bundle_hash": sha256_value(body)}
    write_new_json(Path(output_dir) / manifest["bundle_hash"] / "bundle.json", manifest)
    return manifest


def verify_bundle(manifest: dict) -> bool:
    if set(manifest.get("components", {})) != COMPONENTS:
        raise ContractError("bare or incomplete deployment bundle rejected")
    body = {key: manifest[key] for key in ("schema_version", "bundle_version", "components")}
    if sha256_value(body) != manifest.get("bundle_hash"):
        raise ContractError("bundle manifest hash mismatch")
    for name, record in manifest["components"].items():
        path = Path(record["path"])
        if not path.is_file() or _file_hash(path) != record["sha256"]:
            raise ContractError(f"bundle component is missing or mutated: {name}")
    return True
