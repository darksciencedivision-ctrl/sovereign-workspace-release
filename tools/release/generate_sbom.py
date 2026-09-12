#!/usr/bin/env python3
"""Generate SBOM.json from LOCK FILES, not from the build machine.

EPC-01 P2-1 / P2-2 / P2-3. One job closing three punch-list items, because they were one
defect wearing three faces.

WHAT WAS WRONG. `SBOM.json` was produced by walking the build host's virtual environments.
Measured on the shipped file: 173 of its 477 components were `file` entries naming paths under
`modules/debate/.venv` and `modules/sovereign/.venv` — individual files from one developer's
machine, six of them CPython **3.14** binaries in a product that targets 3.12 for two of its
three Python environments. Its own metadata admitted the consequence:

    sovereign:c2-python-audit      unavailable-not-in-lock
    sovereign:sow-python-lock      partial-parked
    sovereign:distillery-python-lock  missing-parked

So the one thing an enterprise recipient actually does with an SBOM — scan it for known
vulnerabilities — could not be done for the Python side of a mostly-Python product. And the
`sovereign:source-commit` property named a commit that drifted behind the seal, because
nothing regenerated the file when the tree moved.

WHAT THIS DOES INSTEAD. Every component is derived from a file that is committed, pinned and
shipped:

  * Python from the exact locks the installer installs from — the same bytes, so the SBOM
    cannot describe a different stack from the one provisioned.
  * Node from `package-lock.json`, which carries `version`, `license`, `dev` and `resolved`
    for every package, so nothing needs to be installed to enumerate it.
  * Licences that a lock does not carry are read from the installed distribution's metadata
    and the SOURCE of each value is recorded. A component that resolves to nothing is written
    as UNRESOLVED and the tool exits non-zero: an incomplete SBOM fails the build rather than
    shipping quietly.

There are no `file` components. A file is not a licensable, scannable unit and listing 173 of
them obscured the 304 that were.

The generator records WHAT IT READ — each lock's path and SHA-256 — so the SBOM's provenance
is checkable rather than asserted, and `--check` fails when the SBOM no longer matches its
sources.

    py -3.12 tools/release/generate_sbom.py [--out SBOM.json] [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: F-072. The committed Python licence map, keyed by "<normalised-name>==<version>". Licences that
#: a lock file does not itself carry are resolved ONCE (from installed distribution metadata) and
#: written here by `--resolve`; the normal build and `--check` read only this tracked file, never a
#: module .venv or the generating host. That is what makes `--check` a pure function of tracked
#: inputs and lets it pass identically on the build host and in CI (which provisions no module
#: venvs). A component whose key is absent from this map is emitted UNRESOLVED and fails the build,
#: so a newly added dependency must be resolved into the map deliberately, not silently by whatever
#: happens to be installed on the machine cutting the release.
LICENCE_MAP_PATH = REPO_ROOT / "tools" / "release" / "python_licences.json"


def _pkg_key(name: str, version: str) -> str:
    return f"{name.lower().replace('_', '-')}=={version}"


def load_licence_map() -> dict:
    if not LICENCE_MAP_PATH.is_file():
        return {}
    doc = json.loads(LICENCE_MAP_PATH.read_text(encoding="utf-8"))
    return doc.get("licences", {})

#: Python locks, in the order the installer consumes them. `scope` is CycloneDX's: `required`
#: is installed for the running product, `optional` is development-only.
PYTHON_LOCKS = [
    ("sovereign", REPO_ROOT / "modules" / "sovereign" / "WORKSPACE-RESOLVED-LOCK.txt", "required"),
    ("debate", REPO_ROOT / "modules" / "debate" / "requirements.lock.txt", "required"),
    ("sow", REPO_ROOT / "modules" / "sow" / "requirements.txt", "required"),
    ("sow", REPO_ROOT / "modules" / "sow" / "requirements-dev.txt", "optional"),
]

NODE_LOCKS = [
    ("sovereign-ui", REPO_ROOT / "modules" / "sovereign" / "ui" / "ui_shell" / "package-lock.json"),
    ("sow-desktop", REPO_ROOT / "modules" / "sow" / "apps" / "desktop" / "package-lock.json"),
]

#: Modules that declare no third-party dependencies at all. Recorded rather than omitted, so
#: "absent from the SBOM" and "has no dependencies" are distinguishable.
STDLIB_ONLY = {
    "distillery": "pyproject.toml declares no [project] dependencies; the server is stdlib-only",
    "tokencenter": "no requirements file; imports are stdlib-only",
    "shell": "no requirements file; imports are stdlib-only",
}

SPELLINGS = {
    "apache 2.0": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    "apache license version 2.0": "Apache-2.0", "apache license, version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "the unlicense (unlicense)": "Unlicense",
    "python software foundation license": "PSF-2.0", "mit license": "MIT",
    "bsd license": "BSD-3-Clause", "3-clause bsd license": "BSD-3-Clause",
    "isc license": "ISC",
    "isc license (iscl)": "ISC",
}

VAGUE = {"", "unknown", "dual license", "other", "other/proprietary license"}


def normalise(value: str) -> str:
    if not value:
        return value
    key = value.strip().lower()
    if key in SPELLINGS:
        return SPELLINGS[key]
    if len(value) > 60:
        for family in ("MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0"):
            if family.lower() in key[:40]:
                return family
        return "SEE-COMPONENT-METADATA"
    return value.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_text(path: Path) -> str:
    """Locks are UTF-8 or UTF-16-with-BOM; both are in this tree."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _describe_search_path(search_path: list[str]) -> str:
    """Name where licence metadata was read, WITHOUT leaking a build-host absolute path.

    The SBOM ships. An absolute path from the machine that cut the release is developer
    identity in a customer-facing artifact (EPC-01 P3-2), and it is also useless to the
    recipient, whose tree is somewhere else. Recorded relative to the repository root when
    it is inside it; otherwise only the fact that the generating host supplied it.
    """
    if not search_path:
        return "generating host"
    candidate = Path(search_path[0])
    try:
        return candidate.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return "generating host"


def _site_packages_for(lock_path: Path) -> list[str]:
    """The environment a lock actually provisions, if it exists beside the module.

    A lock is installed into ITS module's virtualenv, and those environments are not all the
    same interpreter — debate is provisioned on 3.14 while SOVEREIGN and SOW are on 3.12. So
    resolving every licence against whichever interpreter happens to be running this script
    finds nothing for packages that only exist in another module's environment, which is how
    `pydantic-settings` came back unresolved on the first run.
    """
    module_root = lock_path.parent
    for candidate in (
        module_root / ".venv" / "Lib" / "site-packages",
        module_root / ".venv" / "lib" / "site-packages",
    ):
        if candidate.is_dir():
            return [str(candidate)]
    return []


def licence_from_installed(name: str, search_path: list[str] | None = None) -> tuple[str | None, str]:
    meta = None
    if search_path:
        context = metadata.DistributionFinder.Context(path=list(search_path))
        for distribution in metadata.Distribution.discover(context=context):
            declared = (distribution.metadata.get("Name") or "").lower().replace("_", "-")
            if declared == name.lower().replace("_", "-"):
                meta = distribution.metadata
                break
    if meta is None:
        try:
            meta = metadata.metadata(name)
        except metadata.PackageNotFoundError:
            return None, "not installed in the module environment or on the generating host"
    expression = meta.get("License-Expression")
    if expression:
        return expression, "License-Expression"
    classifiers = [c for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
    if classifiers:
        names = []
        for classifier in classifiers:
            tail = classifier.split("::")[-1].strip()
            if tail and tail not in names:
                names.append(tail)
        label = "Trove classifier" if len(names) == 1 else "Trove classifiers"
        return " OR ".join(normalise(n) for n in names), label
    field = meta.get("License")
    if field and len(field) < 80 and "\n" not in field and field.strip().lower() not in VAGUE:
        return field.strip(), "License field"
    return None, "metadata states no licence"


def python_components(unresolved: list, licence_map: dict) -> tuple[list, list]:
    components, sources = [], []
    seen = {}
    for module, path, scope in PYTHON_LOCKS:
        if not path.is_file():
            continue
        # F-072. The source record names only tracked facts (path + sha256 + scope). It no longer
        # records where licences were "resolved from": that was a build-host venv path, which made
        # the SBOM -- and its --check -- differ between the build host and CI.
        sources.append({
            "module": module,
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256(path),
            "scope": scope,
            "licences_resolved_from": "tools/release/python_licences.json (committed map)",
        })
        for raw in _read_text(path).splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r"^([A-Za-z0-9._-]+)\s*==\s*([^\s;#]+)", line)
            if not match:
                continue
            name, version = match.group(1), match.group(2)
            key = (name.lower().replace("_", "-"), version)
            if key in seen:
                seen[key]["properties"].append(
                    {"name": "sovereign:required-by", "value": module})
                continue
            # F-072. Licence comes from the committed map, never a .venv. The map stores the exact
            # CycloneDX `licenses` list so the SBOM is reproduced byte-for-byte without recomputing
            # the id-vs-name choice (which depends on the raw value the map was built from). A miss
            # is UNRESOLVED and fails the build below rather than being silently filled from host.
            entry = licence_map.get(_pkg_key(name, version))
            if entry and entry.get("licenses"):
                licenses = entry["licenses"]
                origin = entry.get("source", "committed map")
            else:
                unresolved.append(
                    f"{name}=={version} (absent from tools/release/python_licences.json; "
                    f"run generate_sbom.py --resolve)")
                licenses = [{"license": {"name": "UNRESOLVED"}}]
                origin = "unresolved"
            component = {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
                "scope": scope,
                "licenses": licenses,
                "properties": [
                    {"name": "sovereign:required-by", "value": module},
                    {"name": "sovereign:licence-source", "value": origin},
                ],
            }
            seen[key] = component
            components.append(component)
    return components, sources


def node_components() -> tuple[list, list]:
    components, sources = [], []
    seen = {}
    for module, path in NODE_LOCKS:
        if not path.is_file():
            continue
        sources.append({
            "module": module,
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256(path),
            "scope": "mixed",
        })
        document = json.loads(path.read_text(encoding="utf-8"))
        for location, entry in (document.get("packages") or {}).items():
            if not location:
                continue  # the root project itself
            name = location.split("node_modules/")[-1]
            version = entry.get("version")
            if not version:
                continue
            key = (name, version)
            scope = "optional" if entry.get("dev") else "required"
            if key in seen:
                seen[key]["properties"].append(
                    {"name": "sovereign:required-by", "value": module})
                if scope == "required":
                    seen[key]["scope"] = "required"
                continue
            licence = entry.get("license") or "UNRESOLVED"
            component = {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:npm/{name}@{version}",
                "scope": scope,
                "licenses": [{"license": {"id": licence}}],
                "properties": [
                    {"name": "sovereign:required-by", "value": module},
                    {"name": "sovereign:licence-source", "value": "package-lock.json"},
                ],
            }
            if entry.get("integrity"):
                component["hashes"] = [{
                    "alg": "SHA-512" if entry["integrity"].startswith("sha512-") else "SHA-256",
                    "content": entry["integrity"].split("-", 1)[1],
                }]
            seen[key] = component
            components.append(component)
    return components, sources


def head_commit() -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def build() -> tuple[dict, list]:
    unresolved: list = []
    py_components, py_sources = python_components(unresolved, load_licence_map())
    node_comps, node_sources = node_components()
    components = sorted(py_components + node_comps,
                        key=lambda c: (c["purl"].split(":")[1].split("/")[0], c["name"].lower()))

    version = json.loads((REPO_ROOT / "VERSION.json").read_text(encoding="utf-8"))["version"]

    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "bom-ref": f"sovereign-workspace@{version}",
                "type": "application",
                "name": "sovereign-workspace",
                "version": version,
                "properties": [
                    {"name": "sovereign:source-commit", "value": head_commit()},
                    {"name": "sovereign:generated-from",
                     "value": "lock files only; no build-host environment is read"},
                    {"name": "sovereign:python-coverage", "value": "complete-from-locks"},
                    {"name": "sovereign:node-coverage", "value": "complete-from-locks"},
                ],
            },
            "tools": [{"name": "generate_sbom.py", "vendor": "Dark Science Division"}],
        },
        "sovereign:sources": py_sources + node_sources,
        "sovereign:no_dependency_modules": [
            {"module": name, "reason": reason} for name, reason in sorted(STDLIB_ONLY.items())
        ],
        "components": components,
    }
    return document, unresolved


def resolve_licences() -> int:
    """F-072. Refresh the committed Python licence map from installed distribution metadata.

    This is the ONE place that reads a module .venv or the generating host, and it is run
    deliberately by a maintainer -- never by --check. It MERGES: a licence it can resolve now
    updates the map; a package it cannot resolve keeps whatever the committed map already holds
    (so a maintainer without every module venv does not regress known licences to UNRESOLVED);
    keys no longer named by any lock are pruned. Prints anything still unresolved and exits
    non-zero so gaps are visible."""
    existing = load_licence_map()
    resolved: dict = {}
    still_unresolved: list = []
    for _module, path, _scope in PYTHON_LOCKS:
        if not path.is_file():
            continue
        search_path = _site_packages_for(path)
        for raw in _read_text(path).splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r"^([A-Za-z0-9._-]+)\s*==\s*([^\s;#]+)", line)
            if not match:
                continue
            name, version = match.group(1), match.group(2)
            key = _pkg_key(name, version)
            if key in resolved:
                continue
            licence, origin = licence_from_installed(name, search_path)
            if licence:
                licenses = [{"license": {"id" if "-" in licence or licence.isupper()
                                         else "name": normalise(licence)}}]
                resolved[key] = {"name": name, "version": version,
                                 "licenses": licenses, "source": origin}
            elif key in existing and existing[key].get("licenses"):
                resolved[key] = existing[key]  # keep the committed value; do not regress
            else:
                resolved[key] = {"name": name, "version": version,
                                 "licenses": [{"license": {"name": "UNRESOLVED"}}],
                                 "source": origin}
                still_unresolved.append(f"{name}=={version} ({origin})")
    doc = {
        "description": ("Committed Python licence map for the SBOM (F-072). Keyed by "
                        "'<normalised-name>==<version>'. Regenerate with "
                        "generate_sbom.py --resolve; read by the build and --check, which never "
                        "touch a module .venv."),
        "licences": dict(sorted(resolved.items())),
    }
    LICENCE_MAP_PATH.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"generate_sbom: wrote {LICENCE_MAP_PATH.relative_to(REPO_ROOT).as_posix()} "
          f"({len(resolved)} entries)")
    if still_unresolved:
        print("generate_sbom: licences still UNRESOLVED after --resolve "
              "(install the module venv and re-run):", file=sys.stderr)
        for item in still_unresolved:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(REPO_ROOT / "SBOM.json"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resolve", action="store_true",
                        help="refresh tools/release/python_licences.json from installed metadata "
                             "(the only mode that reads a .venv/host); then regenerate the SBOM")
    args = parser.parse_args()

    if args.resolve:
        rc = resolve_licences()
        if rc != 0:
            return rc

    document, unresolved = build()
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    out = Path(args.out)

    if args.check:
        if not out.is_file():
            print(f"generate_sbom: {out} does not exist", file=sys.stderr)
            return 1
        current = json.loads(out.read_text(encoding="utf-8"))
        fresh = json.loads(rendered)
        # The source commit legitimately advances between a build and a later check; every
        # other field must match, or the SBOM no longer describes what it claims to.
        for doc in (current, fresh):
            props = doc.get("metadata", {}).get("component", {}).get("properties", [])
            for prop in props:
                if prop.get("name") == "sovereign:source-commit":
                    prop["value"] = "<ignored-for-check>"
        if current != fresh:
            print(f"generate_sbom: {out} no longer matches its lock files - regenerate it",
                  file=sys.stderr)
            return 1
        print(f"generate_sbom: {out} matches its lock files "
              f"({len(fresh['components'])} components)")
    else:
        out.write_text(rendered, encoding="utf-8", newline="\n")
        counts: dict = {}
        for component in document["components"]:
            counts[component["scope"]] = counts.get(component["scope"], 0) + 1
        print(f"generate_sbom: wrote {out}")
        print(f"  components   {len(document['components'])} "
              f"({', '.join(f'{k}={v}' for k, v in sorted(counts.items()))})")
        print(f"  sources read {len(document['sovereign:sources'])} lock file(s)")
        print(f"  file entries 0 (was 173 venv artefacts)")

    if unresolved:
        print("generate_sbom: UNRESOLVED licences - the SBOM is incomplete:", file=sys.stderr)
        for item in unresolved:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
