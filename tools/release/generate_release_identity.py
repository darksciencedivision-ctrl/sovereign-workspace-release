#!/usr/bin/env python
"""Generate deterministic release identity documents from retained locks.

The generator never resolves dependencies and never contacts a registry. It reads the
candidate's existing lock inputs plus installed, ignored C2 environments for license
metadata and native-file hashes. Missing metadata is surfaced as UNKNOWN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from email.parser import Parser
from pathlib import Path
from typing import Any, Iterable


SYSTEM_VERSION = "1.0.0-rc.1"
PYTHON_LOCKS = (
    ("sovereign", "modules/sovereign/WORKSPACE-RESOLVED-LOCK.txt", "modules/sovereign/.venv"),
    ("debate", "modules/debate/requirements.lock.txt", "modules/debate/.venv"),
)
NODE_LOCKS = (
    ("sovereign-ui", "modules/sovereign/ui/ui_shell/package-lock.json"),
    ("sow-desktop", "modules/sow/apps/desktop/package-lock.json"),
    ("sow-spike-nonproduct", "modules/sow/tools/spike_compositor/package-lock.json"),
)
NATIVE_ROOTS = tuple(
    Path(item)
    for item in (
        "modules/sovereign/.venv",
        "modules/debate/.venv",
        "modules/sovereign/ui/ui_shell/node_modules",
        "modules/sow/apps/desktop/node_modules",
        "modules/sow/tools/spike_compositor/node_modules",
    )
)
NATIVE_SUFFIXES = {".exe", ".node", ".pyd", ".dll"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_bom_aware_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def parse_python_lock(path: Path) -> list[tuple[str, str]]:
    pins: list[tuple[str, str]] = []
    for raw in read_bom_aware_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([^=<>!~\s]+)==([^\s]+)", line)
        if not match:
            raise ValueError(f"non-exact Python lock entry in {path}: {line!r}")
        pins.append((canonical_python_name(match.group(1)), match.group(2)))
    if not pins:
        raise ValueError(f"empty Python lock: {path}")
    return pins


def python_metadata(venv: Path) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    site_packages = venv / "Lib" / "site-packages"
    if not site_packages.is_dir():
        return result
    for metadata_path in sorted(site_packages.glob("*.dist-info/METADATA")):
        document = Parser().parsestr(metadata_path.read_text(encoding="utf-8", errors="replace"))
        name = canonical_python_name(document.get("Name", ""))
        version = document.get("Version", "").strip()
        if not name or not version:
            continue
        license_value = (
            document.get("License-Expression", "").strip()
            or document.get("License", "").strip()
            or "UNKNOWN"
        )
        result[(name, version)] = {
            "license": " ".join(license_value.split()),
            "homepage": document.get("Home-page", "").strip(),
        }
    return result


def node_package_name(package_path: str, entry: dict[str, Any]) -> str:
    explicit = str(entry.get("name") or "").strip()
    if explicit:
        return explicit
    parts = re.split(r"node_modules/", package_path)
    return parts[-1].rstrip("/")


def add_component(
    table: dict[str, dict[str, Any]],
    *,
    ecosystem: str,
    name: str,
    version: str,
    license_value: str,
    source: str,
) -> None:
    purl_name = name.replace("@", "%40", 1) if ecosystem == "npm" else name
    purl = f"pkg:{ecosystem}/{purl_name}@{version}"
    component = table.setdefault(
        purl,
        {
            "type": "library",
            "bom-ref": purl,
            "name": name,
            "version": version,
            "purl": purl,
            "licenses": [{"license": {"name": license_value or "UNKNOWN"}}],
            "properties": [],
        },
    )
    existing_sources = {
        item["value"]
        for item in component["properties"]
        if item.get("name") == "sovereign:source-lock"
    }
    if source not in existing_sources:
        component["properties"].append(
            {"name": "sovereign:source-lock", "value": source}
        )


def dependency_components(root: Path) -> list[dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for _module, lock_rel, venv_rel in PYTHON_LOCKS:
        lock_path = root / lock_rel
        metadata = python_metadata(root / venv_rel)
        for name, version in parse_python_lock(lock_path):
            details = metadata.get((name, version), {})
            add_component(
                table,
                ecosystem="pypi",
                name=name,
                version=version,
                license_value=details.get("license", "UNKNOWN"),
                source=lock_rel,
            )
    for _module, lock_rel in NODE_LOCKS:
        lock_path = root / lock_rel
        document = json.loads(lock_path.read_text(encoding="utf-8-sig"))
        packages = document.get("packages")
        if not isinstance(packages, dict):
            raise ValueError(f"package lock lacks packages map: {lock_path}")
        for package_path, raw in sorted(packages.items()):
            if not package_path or not isinstance(raw, dict):
                continue
            name = node_package_name(package_path, raw)
            version = str(raw.get("version") or "").strip()
            if not name or not version:
                continue
            add_component(
                table,
                ecosystem="npm",
                name=name,
                version=version,
                license_value=str(raw.get("license") or "UNKNOWN"),
                source=lock_rel,
            )
    components = list(table.values())
    for component in components:
        component["properties"].sort(key=lambda item: item["value"])
    return sorted(components, key=lambda item: item["bom-ref"])


def native_components(root: Path) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for relative_root in NATIVE_ROOTS:
        directory = root / relative_root
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in NATIVE_SUFFIXES:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            rel = path.relative_to(root).as_posix()
            digest = sha256_file(path)
            components.append(
                {
                    "type": "file",
                    "bom-ref": f"native:{rel}:{digest}",
                    "name": path.name,
                    "hashes": [{"alg": "SHA-256", "content": digest}],
                    "properties": [
                        {"name": "sovereign:path", "value": rel},
                        {
                            "name": "sovereign:archive-scope",
                            "value": "ignored-c2-environment; not in source archive",
                        },
                    ],
                }
            )
    return sorted(components, key=lambda item: item["properties"][0]["value"])


def module_versions(root: Path) -> dict[str, str]:
    manifest = json.loads((root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8-sig"))
    modules = manifest.get("modules")
    if not isinstance(modules, dict):
        raise ValueError("RELEASE-MANIFEST.json lacks modules")
    return {
        str(name): str(record.get("version") or "UNKNOWN")
        for name, record in sorted(modules.items())
        if isinstance(record, dict)
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def render_notices(components: Iterable[dict[str, Any]], generated_utc: str) -> str:
    rows = []
    for component in components:
        license_value = component["licenses"][0]["license"]["name"]
        sources = ", ".join(item["value"] for item in component["properties"])
        rows.append(
            f"| `{component['name']}` | `{component['version']}` | "
            f"{license_value.replace('|', '\\|')} | `{sources}` |"
        )
    return "\n".join(
        [
            "# Third-party notices",
            "",
            f"Generated from retained dependency locks and C2 metadata snapshots at {generated_utc}.",
            "This inventory is a candidate record, not legal advice. UNKNOWN entries require canonical notice review before external distribution.",
            "SOW and Distillery Python closures are absent/partial and are named limitations; they are not silently inferred here.",
            "",
            "| Package | Version | Declared license | Retained lock source |",
            "|---|---:|---|---|",
            *rows,
            "",
            "BUILDER CLAIM: no gate submitted for reviewer evaluation; no PASS asserted.",
            "",
        ]
    )


def generate(root: Path, source_commit: str, generated_utc: str) -> tuple[Path, Path, Path]:
    dependencies = dependency_components(root)
    natives = native_components(root)
    versions = module_versions(root)
    version_doc = {
        "system": "sovereign-workspace",
        "version": SYSTEM_VERSION,
        "source_commit": source_commit,
        "modules": versions,
    }
    seed = "\n".join(
        [source_commit, *(item["bom-ref"] for item in dependencies), *(item["bom-ref"] for item in natives)]
    )
    serial = uuid.UUID(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32])
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": generated_utc,
            "component": {
                "type": "application",
                "bom-ref": f"sovereign-workspace@{SYSTEM_VERSION}",
                "name": "sovereign-workspace",
                "version": SYSTEM_VERSION,
                "properties": [
                    {"name": "sovereign:source-commit", "value": source_commit},
                    {"name": "sovereign:c2-python-audit", "value": "unavailable-not-in-lock"},
                    {"name": "sovereign:sow-python-lock", "value": "partial-parked"},
                    {"name": "sovereign:distillery-python-lock", "value": "missing-parked"},
                ],
            },
        },
        "components": dependencies + natives,
    }
    version_path = root / "VERSION.json"
    sbom_path = root / "SBOM.json"
    notices_path = root / "THIRD-PARTY-NOTICES.md"
    write_json(version_path, version_doc)
    write_json(sbom_path, sbom)
    notices_path.write_text(
        render_notices(dependencies, generated_utc),
        encoding="utf-8",
        newline="\n",
    )
    return version_path, sbom_path, notices_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--generated-utc", required=True)
    args = parser.parse_args(argv)
    paths = generate(args.root.resolve(), args.source_commit, args.generated_utc)
    print(
        "generate_release_identity: wrote "
        + ", ".join(str(path.relative_to(args.root.resolve())) for path in paths)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
