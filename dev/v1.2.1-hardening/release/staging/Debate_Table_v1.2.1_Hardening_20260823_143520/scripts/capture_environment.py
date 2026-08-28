"""Capture the interpreter and the resolved dependency closure this baseline
was validated against.

Written for the v1.2-phase1-baseline snapshot. Run it with the SAME interpreter
that runs app.py -- the whole point is to record what that interpreter actually
resolved, not what some other Python has installed.

    python scripts/capture_environment.py

Writes:
    snapshot/ENVIRONMENT.json   host, interpreter, and resolved closure
    requirements.lock.txt       == pins for every distribution in the closure

This deliberately does NOT shell out to `pip freeze`. A bare freeze captures every
package installed on the host, including ones this project never imports, and
pinning those would make the lockfile both wrong and unreproducible. Instead the
transitive requirement closure of the roots declared in requirements.txt is walked
through importlib.metadata, with environment markers evaluated for the running
interpreter.

Only reads. Installs nothing, changes no dependency.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import sys
from importlib.metadata import PackageNotFoundError, distribution

from packaging.markers import UndefinedEnvironmentName
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
ENVIRONMENT_JSON = REPO_ROOT / "snapshot" / "ENVIRONMENT.json"
LOCKFILE = REPO_ROOT / "requirements.lock.txt"


def host_and_interpreter() -> dict:
    """Everything about where and with what this was captured."""
    return {
        "sys_version": sys.version,
        "sys_version_info": list(sys.version_info),
        "sys_executable": sys.executable,
        "platform_platform": platform.platform(),
        "platform_machine": platform.machine(),
        "platform_python_implementation": platform.python_implementation(),
        "os_name": os.name,
    }


def parse_roots(path: pathlib.Path) -> list[Requirement]:
    """Read the human-facing declaration. Extras (uvicorn[standard]) are kept."""
    roots = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            roots.append(Requirement(line))
    return roots


def walk_closure(roots: list[Requirement]) -> tuple[dict, list]:
    """Breadth-first walk of the transitive requirement closure.

    Returns (resolved, excluded).

    `resolved` maps canonical name -> record of what is actually installed.
    `excluded` records requirements skipped because their environment marker is
    false on THIS interpreter -- these are the platform-specific holes in the
    lockfile and are reported rather than silently dropped.
    """
    resolved: dict[str, dict] = {}
    excluded: list[dict] = []
    missing: list[dict] = []

    # queue entries are (Requirement, requested_by)
    queue = [(r, "requirements.txt") for r in roots]
    seen_with_extras: set[tuple[str, frozenset]] = set()

    while queue:
        req, requested_by = queue.pop(0)
        name = canonicalize_name(req.name)
        key = (name, frozenset(req.extras))
        if key in seen_with_extras:
            continue
        seen_with_extras.add(key)

        try:
            dist = distribution(req.name)
        except PackageNotFoundError:
            missing.append({"name": req.name, "requested_by": requested_by})
            continue

        record = resolved.setdefault(
            name,
            {
                "name": dist.metadata["Name"] or req.name,
                "version": dist.version,
                "extras_requested": [],
                "requested_by": [],
                "requires": [],
            },
        )
        record["extras_requested"] = sorted(
            set(record["extras_requested"]) | set(req.extras)
        )
        if requested_by not in record["requested_by"]:
            record["requested_by"].append(requested_by)

        for dep_str in dist.requires or []:
            dep = Requirement(dep_str)
            keep = False
            if dep.marker is None:
                keep = True
            else:
                # Evaluate once per requested extra, plus with no extra at all.
                for extra in sorted(req.extras) or [None]:
                    try:
                        if dep.marker.evaluate(
                            {"extra": extra} if extra is not None else {}
                        ):
                            keep = True
                            break
                    except UndefinedEnvironmentName:
                        continue
                if not keep and req.extras:
                    try:
                        if dep.marker.evaluate({}):
                            keep = True
                    except UndefinedEnvironmentName:
                        pass

            if keep:
                if dep_str not in record["requires"]:
                    record["requires"].append(dep_str)
                queue.append((dep, record["name"]))
            else:
                excluded.append(
                    {
                        "requirement": dep_str,
                        "required_by": record["name"],
                        "reason": "environment marker evaluated false on this "
                                  "interpreter/platform",
                    }
                )

    return resolved, excluded, missing


def write_environment_json(info, resolved, excluded, missing, roots, commit):
    payload = {
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "captured_at_commit": commit,
        "host": info,
        "declared_roots": [str(r) for r in roots],
        "resolution_method": (
            "transitive requirement closure of declared_roots walked via "
            "importlib.metadata, environment markers evaluated for the "
            "interpreter recorded in host. Not pip freeze."
        ),
        "resolved_count": len(resolved),
        "resolved": [resolved[k] for k in sorted(resolved)],
        "excluded_by_marker": excluded,
        "missing_from_environment": missing,
    }
    ENVIRONMENT_JSON.parent.mkdir(exist_ok=True)
    ENVIRONMENT_JSON.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return payload


def write_lockfile(info, resolved, excluded, commit):
    lines = [
        "# requirements.lock.txt -- reproducible pins for the Debate Table baseline",
        "#",
        f"# Captured at commit : {commit}",
        f"# Interpreter        : {info['sys_version'].splitlines()[0]}",
        f"# Interpreter path   : {info['sys_executable']}",
        f"# Platform           : {info['platform_platform']} ({info['platform_machine']})",
        "#",
        "# requirements.txt remains the human-facing declaration of what this",
        "# project depends on. THIS file is the reproducible pin: the exact",
        "# distribution versions the baseline was validated against. The two",
        "# coexist -- do not delete or edit requirements.txt to match this.",
        "#",
        "# Generated by scripts/capture_environment.py. Do not hand-edit.",
    ]
    if excluded:
        lines += [
            "#",
            "# PLATFORM CAVEAT: this closure was resolved on the platform named",
            "# above. Requirements whose environment markers are false there are",
            "# absent from these pins. On another platform some of them apply.",
            "# See snapshot/ENVIRONMENT.json -> excluded_by_marker for the full",
            "# list. Notable exclusions:",
        ]
        for e in excluded:
            if "sys_platform" in e["requirement"] or "platform_system" in e["requirement"]:
                lines.append(f"#   {e['requirement']}  (via {e['required_by']})")
    lines.append("")
    for key in sorted(resolved):
        rec = resolved[key]
        lines.append(f"{rec['name']}=={rec['version']}")
    LOCKFILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", default="d03a1b7",
        help="commit the capture is attributed to (recorded in both outputs)",
    )
    args = parser.parse_args()

    info = host_and_interpreter()
    roots = parse_roots(REQUIREMENTS)
    resolved, excluded, missing = walk_closure(roots)
    payload = write_environment_json(
        info, resolved, excluded, missing, roots, args.commit
    )
    write_lockfile(info, resolved, excluded, args.commit)

    print(f"interpreter : {info['sys_executable']}")
    print(f"version     : {info['sys_version'].splitlines()[0]}")
    print(f"platform    : {info['platform_platform']} ({info['platform_machine']})")
    print(f"roots       : {[str(r) for r in roots]}")
    print(f"resolved    : {payload['resolved_count']} distributions")
    for k in sorted(resolved):
        print(f"    {resolved[k]['name']}=={resolved[k]['version']}")
    print(f"excluded by marker : {len(excluded)}")
    for e in excluded:
        print(f"    {e['requirement']}  (via {e['required_by']})")
    if missing:
        print(f"MISSING from environment: {missing}")
        return 1
    print(f"wrote {ENVIRONMENT_JSON}")
    print(f"wrote {LOCKFILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
